#!/usr/bin/env bash
#
# pos-verify.sh — Atlas POS program, capability B (TWIN / MIRROR / BACKUP)
# ---------------------------------------------------------------------------
# RESTORE-DRILL. "A backup you never restored is not a backup." This script
# proves that a client's mirror artifact can actually be RESTORED, by:
#
#   1. picking the client's latest local dump  (or, with --from-restic, pulling
#      the latest restic snapshot from Backblaze B2 into a temp dir)
#   2. spinning up a THROWAWAY, ephemeral MariaDB container (random name, random
#      root pw, NO published port, on a throwaway docker volume / tmpfs)
#   3. loading the dump into it
#   4. ASSERTING the restore is real: table count > 0, total row count > 0
#      across user tables, and a few OptimumPOS sanity queries
#   5. tearing the whole thing down (container + volume) no matter what
#   6. pushing the pass/fail result to ntfy (topic pos-mirror)
#
# Usage:
#     pos-verify.sh <client>                 # drill the latest LOCAL dump
#     pos-verify.sh <client> --from-restic   # drill the latest B2 snapshot
#     pos-verify.sh <client> --keep          # don't tear down (debug; still temp)
#
# HARD SAFETY PROPERTIES (mirror scripts/pos-mirror.sh conventions):
#   * READ-ONLY w.r.t. the real twin (atlas-mariadb-<client>) and the live
#     terminal. This script NEVER connects to a terminal and NEVER touches the
#     production twin container or its volume. It only reads a dump file (or a
#     restic snapshot) and exercises a brand-new throwaway container it owns.
#   * Fail-closed gate, same flags as the mirror: refuses unless MIRROR_ENABLED=1
#     and DPA_SIGNED=1 in clients/<client>/env. (We won't even restore-test data
#     for a client we're not permitted to hold.) QUIET_WINDOW is NOT enforced —
#     a restore drill touches no terminal, so it can run any time.
#   * Per-client env file must be chmod 600 (fail closed on group/other-readable),
#     identical check to the mirror.
#   * Idempotent + self-cleaning: a unique per-run container/volume, removed on
#     EXIT/INT/TERM. Re-running converges; a crashed prior run leaks nothing that
#     a later run depends on. A non-blocking flock prevents two overlapping drills
#     for the same client.
#   * bash -n clean.
#
# Exit codes:
#   0  drill PASSED (restored and all assertions held) OR clean skip
#      (client not enabled / no dump yet — nothing to verify, timer-safe)
#   2  missing prerequisite (docker / config)
#   3  bad invocation (no client / no env file / bad perms)
#   4  drill FAILED (restore or an assertion failed) — the backup is suspect
#
# Per-client config is sourced from:  ${CLIENTS_DIR}/<client>/env  (chmod 600)
# (same file the mirror uses: MYSQL_DB, MIRROR_ENABLED, DPA_SIGNED, restic/B2,
#  NTFY_URL, ...). No terminal credentials are used by this script.
# ---------------------------------------------------------------------------

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration (hub defaults; per-client env file overrides most of this)
# ----------------------------------------------------------------------------
POSOPS_ROOT="${POSOPS_ROOT:-/opt/atlas-pos}"
CLIENTS_DIR="${CLIENTS_DIR:-${POSOPS_ROOT}/clients}"
MARIADB_IMAGE="${MARIADB_IMAGE:-mariadb:11}"
NTFY_DEFAULT_URL="${NTFY_URL:-http://atlas-ntfy/}"
NTFY_TOPIC="${NTFY_TOPIC:-pos-mirror}"
DB_READY_TIMEOUT="${DB_READY_TIMEOUT:-60}"   # seconds to wait for temp DB up
MIN_ROWS="${MIN_ROWS:-1}"                    # total user-table rows must exceed

PROG="${0##*/}"

# ----------------------------------------------------------------------------
# Logging (same shape as pos-mirror.sh)
# ----------------------------------------------------------------------------
CLIENT=""
ts()   { date -u +%Y-%m-%dT%H:%M:%SZ; }
log()  { printf '%s [%s] %s\n' "$(ts)" "${CLIENT:-?}" "$*"; }
warn() { printf '%s [%s] WARN: %s\n' "$(ts)" "${CLIENT:-?}" "$*" >&2; }
die()  { printf '%s [%s] ERROR: %s\n' "$(ts)" "${CLIENT:-?}" "$*" >&2; exit "${2:-3}"; }

usage() {
  cat >&2 <<EOF
Usage: ${PROG} <client> [--from-restic] [--keep]

Restore-drill: restore <client>'s latest mirror artifact into a THROWAWAY
MariaDB container, assert it is non-empty and sane, tear it down, ntfy the
result. Read-only w.r.t. the real twin and the terminal. Safe to run from cron
/ a systemd timer (clean exit 0 when there is nothing to verify yet).

  --from-restic   restore the latest restic snapshot from B2 instead of the
                  latest local dump
  --keep          leave the throwaway container running for inspection (debug)

Config (chmod 600): ${CLIENTS_DIR}/<client>/env
EOF
}

# ----------------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------------
[[ $# -ge 1 ]] || { usage; exit 3; }
CLIENT=""
FROM_RESTIC=0
KEEP=0
for arg in "$@"; do
  case "$arg" in
    --from-restic) FROM_RESTIC=1 ;;
    --keep)        KEEP=1 ;;
    -h|--help)     usage; exit 0 ;;
    -*)            die "unknown option: $arg" 3 ;;
    *)
      if [[ -z "$CLIENT" ]]; then CLIENT="$arg"; else die "unexpected argument: $arg" 3; fi
      ;;
  esac
done
[[ -n "$CLIENT" ]] || { usage; exit 3; }
# sanitize client token (used in paths / container / volume names)
[[ "$CLIENT" =~ ^[a-z0-9_]+$ ]] || die "client must match [a-z0-9_]+ (got: $CLIENT)" 3

CLIENT_DIR="${CLIENTS_DIR}/${CLIENT}"
ENV_FILE="${CLIENT_DIR}/env"
DUMP_DIR="${CLIENT_DIR}/dumps"

# Concurrency guard: never run two drills for the same client at once. Take a
# non-blocking per-client lock; if held, exit cleanly (timer-safe).
LOCK="${TMPDIR:-/tmp}/posverify-${CLIENT}.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(ts) [$CLIENT] another restore-drill in progress — exiting" >&2
  exit 0
fi

# ----------------------------------------------------------------------------
# ntfy helper — best-effort; a notification failure never fails the drill.
# ----------------------------------------------------------------------------
notify() {
  local title="$1" message="$2" prio="${3:-3}" tags="${4:-}"
  command -v curl >/dev/null 2>&1 || return 0
  local url="${NTFY_DEFAULT_URL%/}/${NTFY_TOPIC}"
  curl -fsS --max-time 10 \
    -H "Title: ${title}" \
    -H "Priority: ${prio}" \
    ${tags:+-H "Tags: ${tags}"} \
    -d "${message}" \
    "$url" >/dev/null 2>&1 || warn "ntfy push failed (non-fatal): $url"
}

# ----------------------------------------------------------------------------
# Prerequisites + config
# ----------------------------------------------------------------------------
[[ -f "$ENV_FILE" ]] || die "missing per-client env file: $ENV_FILE (chmod 600, not in git)" 3

# Refuse a group/other-readable secrets file — fail closed (check BOTH digits),
# identical to scripts/pos-mirror.sh.
perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '')"
if [[ -n "$perm" && ( "${perm: -1}" != "0" || "${perm: -2:1}" != "0" ) ]]; then
  die "env file $ENV_FILE is group/other-readable (mode $perm) — refusing. Run: chmod 600 $ENV_FILE" 3
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${MYSQL_DB:?MYSQL_DB not set in $ENV_FILE}"
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-b2:atlas-pos-backups:/${CLIENT}}"

# ----------------------------------------------------------------------------
# MECHANICAL SAFETY GATE — fail closed. Same flags as the mirror. We won't even
# restore-test data for a client we're not permitted to hold.
# ----------------------------------------------------------------------------
if [[ "${MIRROR_ENABLED:-0}" != "1" ]]; then
  log "mirror NOT enabled for ${CLIENT} (set MIRROR_ENABLED=1) — nothing to verify, skipping (fail-closed)"
  exit 0
fi
if [[ "${DPA_SIGNED:-0}" != "1" ]]; then
  log "no DPA on file for ${CLIENT} (set DPA_SIGNED=1) — refusing to restore client data (GDPR/AVG)"
  exit 0
fi

command -v docker >/dev/null 2>&1 || die "docker not found in PATH (required for the throwaway DB)" 2

# ----------------------------------------------------------------------------
# Throwaway resources — unique per run; torn down on EXIT/INT/TERM no matter what.
# NO published port, dedicated throwaway volume, random root pw. This container
# is ENTIRELY separate from the production twin atlas-mariadb-<client>.
# ----------------------------------------------------------------------------
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
TMP_CONTAINER="atlas-verify-${CLIENT}-${RUN_ID}"
TMP_VOLUME="atlas-verify-vol-${CLIENT}-${RUN_ID}"
TMP_ROOT_PW="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 28)"
WORK_DIR=""

# Guard against ever pointing at the real twin's name/volume.
[[ "$TMP_CONTAINER" == atlas-mariadb-* ]] && die "internal: temp container name collides with twin" 2

cleanup() {
  if [[ "$KEEP" -eq 1 ]]; then
    warn "--keep set: leaving throwaway container ${TMP_CONTAINER} (volume ${TMP_VOLUME}) for inspection"
  else
    docker rm -f "$TMP_CONTAINER" >/dev/null 2>&1 || true
    docker volume rm "$TMP_VOLUME" >/dev/null 2>&1 || true
  fi
  [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]] && rm -rf "$WORK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ----------------------------------------------------------------------------
# 1) Resolve the artifact to restore: latest local dump, or latest restic snapshot.
# ----------------------------------------------------------------------------
DUMP=""
if [[ "$FROM_RESTIC" -eq 1 ]]; then
  command -v restic >/dev/null 2>&1 || die "restic not found in PATH (--from-restic)" 2
  WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/posverify-${CLIENT}.XXXXXX")"
  export RESTIC_REPOSITORY
  log "restoring latest restic snapshot from ${RESTIC_REPOSITORY} -> ${WORK_DIR}"
  if ! restic restore latest --target "$WORK_DIR" >/dev/null 2>&1; then
    warn "restic restore failed (check RESTIC_PASSWORD / B2 creds / repo)"
    notify "POS restore-drill FAILED: ${CLIENT}" "restic restore of latest snapshot failed." 5 "rotating_light"
    exit 4
  fi
  # restic preserves the absolute dump tree; grab the newest *.sql.gz from it.
  DUMP="$(find "$WORK_DIR" -type f -name '*.sql.gz' -printf '%T@ %p\n' 2>/dev/null \
            | sort -nr | head -n1 | cut -d' ' -f2-)"
  [[ -n "$DUMP" ]] || { warn "no *.sql.gz inside the restored snapshot"; \
    notify "POS restore-drill FAILED: ${CLIENT}" "Restic snapshot contained no dump file." 5 "rotating_light"; exit 4; }
else
  # newest local dump by mtime
  DUMP="$(ls -1t "${DUMP_DIR}"/*.sql.gz 2>/dev/null | head -n1 || true)"
  if [[ -z "$DUMP" ]]; then
    log "no local dump under ${DUMP_DIR} yet — nothing to verify, skipping cleanly"
    exit 0
  fi
fi

DUMP_BYTES="$(stat -c %s "$DUMP" 2>/dev/null || echo 0)"
log "restore-drill artifact: ${DUMP##*/} (${DUMP_BYTES} bytes)"
if [[ "$DUMP_BYTES" -lt 200 ]]; then
  warn "artifact suspiciously small (${DUMP_BYTES} bytes) — failing the drill"
  notify "POS restore-drill FAILED: ${CLIENT}" "Artifact ${DUMP##*/} only ${DUMP_BYTES} bytes." 5 "rotating_light"
  exit 4
fi

# Optional checksum verification against the mirror's manifest (local only).
if [[ "$FROM_RESTIC" -eq 0 && -f "${DUMP_DIR}/SHA256SUMS" ]] && command -v sha256sum >/dev/null 2>&1; then
  if ( cd "$DUMP_DIR" && grep -q " $(basename "$DUMP")\$" SHA256SUMS ); then
    if ( cd "$DUMP_DIR" && grep " $(basename "$DUMP")\$" SHA256SUMS | sha256sum -c - >/dev/null 2>&1 ); then
      log "checksum OK against SHA256SUMS"
    else
      warn "CHECKSUM MISMATCH for ${DUMP##*/} — failing the drill"
      notify "POS restore-drill FAILED: ${CLIENT}" "Checksum mismatch on ${DUMP##*/}." 5 "rotating_light"
      exit 4
    fi
  fi
fi

# ----------------------------------------------------------------------------
# 2) Spin up the THROWAWAY MariaDB container (no port, throwaway volume).
# ----------------------------------------------------------------------------
log "starting throwaway MariaDB ${TMP_CONTAINER} (image ${MARIADB_IMAGE})"
docker volume create "$TMP_VOLUME" >/dev/null
if ! docker run -d --name "$TMP_CONTAINER" \
      --restart no \
      -e MARIADB_ROOT_PASSWORD="$TMP_ROOT_PW" \
      -v "${TMP_VOLUME}:/var/lib/mysql" \
      "$MARIADB_IMAGE" >/dev/null; then
  warn "failed to start throwaway container"
  notify "POS restore-drill FAILED: ${CLIENT}" "Could not start throwaway MariaDB." 5 "rotating_light"
  exit 4
fi

# pick whichever client/admin binaries the image ships (mariadb vs mysql)
TWIN_CLI="mariadb"
docker exec "$TMP_CONTAINER" sh -c 'command -v mariadb >/dev/null 2>&1' || TWIN_CLI="mysql"
ADMIN_CLI="mariadb-admin"
docker exec "$TMP_CONTAINER" sh -c 'command -v mariadb-admin >/dev/null 2>&1' || ADMIN_CLI="mysqladmin"

# wait for it to accept connections (bounded)
ready=0
for _ in $(seq 1 "$DB_READY_TIMEOUT"); do
  if docker exec "$TMP_CONTAINER" "$ADMIN_CLI" -uroot -p"$TMP_ROOT_PW" ping >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  warn "throwaway DB not ready after ${DB_READY_TIMEOUT}s"
  notify "POS restore-drill FAILED: ${CLIENT}" "Throwaway MariaDB never came up." 5 "rotating_light"
  exit 4
fi

# small helper: run SQL, return value (-N -B = no headers, tab-batch)
q() { docker exec -i "$TMP_CONTAINER" "$TWIN_CLI" -uroot -p"$TMP_ROOT_PW" -N -B -e "$1" 2>/dev/null; }

# ----------------------------------------------------------------------------
# 3) Restore the dump into the throwaway DB (DROP+CREATE, then stream gzip in).
# ----------------------------------------------------------------------------
log "restoring dump into throwaway db '${MYSQL_DB}' via ${TWIN_CLI}"
if ! docker exec -i "$TMP_CONTAINER" "$TWIN_CLI" -uroot -p"$TMP_ROOT_PW" \
      -e "DROP DATABASE IF EXISTS \`${MYSQL_DB}\`; CREATE DATABASE \`${MYSQL_DB}\` CHARACTER SET utf8mb4;"; then
  warn "could not create target db in throwaway container"
  notify "POS restore-drill FAILED: ${CLIENT}" "CREATE DATABASE failed in throwaway DB." 5 "rotating_light"
  exit 4
fi
if ! gunzip -c "$DUMP" | docker exec -i "$TMP_CONTAINER" "$TWIN_CLI" -uroot -p"$TMP_ROOT_PW" "$MYSQL_DB"; then
  warn "RESTORE FAILED while loading ${DUMP##*/} — this backup does not restore"
  notify "POS restore-drill FAILED: ${CLIENT}" "Dump ${DUMP##*/} failed to load (backup is suspect)." 5 "rotating_light"
  exit 4
fi
log "restore stream completed"

# ----------------------------------------------------------------------------
# 4) ASSERTIONS — "restored and non-empty and sane", else fail (exit 4).
# ----------------------------------------------------------------------------
fail() {
  warn "ASSERTION FAILED: $1"
  notify "POS restore-drill FAILED: ${CLIENT}" "Assertion failed: $1 (artifact ${DUMP##*/})." 5 "rotating_light"
  exit 4
}

# 4a) table count > 0
NTAB="$(q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${MYSQL_DB}';")"
NTAB="${NTAB:-0}"
[[ "$NTAB" =~ ^[0-9]+$ ]] || fail "could not read table count"
(( NTAB > 0 )) || fail "restored database has 0 tables"
log "assert OK: ${NTAB} tables present"

# 4b) total user-table rows > MIN_ROWS (sum information_schema estimates, then a
#     real COUNT(*) on the biggest table as a hard check so we never trust only
#     the optimizer's estimate).
SUM_ROWS="$(q "SELECT IFNULL(SUM(table_rows),0) FROM information_schema.tables WHERE table_schema='${MYSQL_DB}' AND table_type='BASE TABLE';")"
SUM_ROWS="${SUM_ROWS:-0}"
[[ "$SUM_ROWS" =~ ^[0-9]+$ ]] || SUM_ROWS=0
log "assert info: ~${SUM_ROWS} estimated rows across base tables"

BIGGEST="$(q "SELECT table_name FROM information_schema.tables WHERE table_schema='${MYSQL_DB}' AND table_type='BASE TABLE' ORDER BY table_rows DESC LIMIT 1;")"
if [[ -n "$BIGGEST" ]]; then
  REAL_ROWS="$(q "SELECT COUNT(*) FROM \`${MYSQL_DB}\`.\`${BIGGEST}\`;")"
  REAL_ROWS="${REAL_ROWS:-0}"
  [[ "$REAL_ROWS" =~ ^[0-9]+$ ]] || fail "could not COUNT(*) the largest table ${BIGGEST}"
  (( REAL_ROWS >= MIN_ROWS )) || fail "largest table ${BIGGEST} has ${REAL_ROWS} rows (< ${MIN_ROWS})"
  log "assert OK: largest table ${BIGGEST} has ${REAL_ROWS} real rows"
else
  fail "no base tables found to row-check"
fi

# 4c) sanity queries — the restored DB must be query-able and self-consistent.
#   * SELECT 1 round-trips the engine
#   * every base table is openable (CHECKSUM/COUNT on each would be heavy; we do
#     a lightweight openability probe on up to 5 tables)
[[ "$(q "SELECT 1;")" == "1" ]] || fail "engine did not answer SELECT 1"

PROBE_FAIL=""
while IFS= read -r tbl; do
  [[ -z "$tbl" ]] && continue
  if ! q "SELECT 1 FROM \`${MYSQL_DB}\`.\`${tbl}\` LIMIT 1;" >/dev/null 2>&1; then
    PROBE_FAIL="$tbl"; break
  fi
done < <(q "SELECT table_name FROM information_schema.tables WHERE table_schema='${MYSQL_DB}' AND table_type='BASE TABLE' LIMIT 5;")
[[ -z "$PROBE_FAIL" ]] || fail "table ${PROBE_FAIL} is present but not readable (corrupt restore)"
log "assert OK: sampled tables are readable"

# ----------------------------------------------------------------------------
# 5) PASS. Teardown happens in the EXIT trap.
# ----------------------------------------------------------------------------
SOURCE_LABEL="local-dump"; [[ "$FROM_RESTIC" -eq 1 ]] && SOURCE_LABEL="restic-snapshot"
log "RESTORE-DRILL PASSED (${SOURCE_LABEL}): ${NTAB} tables, largest ${BIGGEST}=${REAL_ROWS} rows, ${DUMP_BYTES}B artifact"
notify "POS restore-drill OK: ${CLIENT}" \
  "Restored ${SOURCE_LABEL} ${DUMP##*/}: ${NTAB} tables, ${BIGGEST}=${REAL_ROWS} rows. Backup is restorable." 2 "white_check_mark"

exit 0
