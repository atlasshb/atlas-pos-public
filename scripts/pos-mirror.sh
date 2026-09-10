#!/usr/bin/env bash
#
# pos-mirror.sh — Atlas POS program, capability B (TWIN / MIRROR / BACKUP)
# ---------------------------------------------------------------------------
# Runs ON pos-hub (the always-on hub). For ONE client, this does a hub-
# initiated PULL of that client's live OptimumPOS MySQL over Tailscale and:
#
#   1. gates on reachability  (terminal off => clean skip, exit 0, no error)
#   2. takes a READ-ONLY, consistent logical dump (mysqldump --single-transaction)
#   3. publishes it atomically as a versioned, timestamped, gzipped backup
#   4. records a sha256 in a per-client manifest
#   5. loads it into the per-client queryable TWIN (atlas-mariadb-<client>)
#   6. ships the dump tree to Backblaze B2 with restic (encrypted at rest)
#   7. writes a freshness/status file and pushes ntfy on success/failure
#
# It is designed to be driven from cron or a systemd timer, once per client:
#     pos-mirror.sh venue_a
#     pos-mirror.sh venue_b
#
# WHY THIS SHAPE (hard design constraints — see program design docs):
#   * Hub-initiated PULL only. The terminal runs nothing and is touched as
#     little as possible. It is a LIVE card-payment box.
#   * READ-ONLY against the terminal. We connect with a dedicated read-only
#     MySQL user and use --single-transaction (consistent InnoDB snapshot, no
#     write lock) + --skip-lock-tables so we never lock the live POS.
#   * Terminals power off often. Unreachable is a NORMAL outcome: we skip and
#     exit 0 so the timer simply retries next window. It is never an error.
#   * Additive, idempotent, reversible. Each dump is an immutable timestamped
#     file; the twin is a full refresh from the latest dump (drop+recreate).
#   * Secrets via per-client env file (chmod 600), NEVER hardcoded, never in git.
#   * Per-tenant isolation: own dump dir, own twin container, own restic repo.
#
# Exit codes:
#   0  success OR clean skip (terminal offline / MySQL down) — safe for timers
#   2  missing prerequisite (mysqldump / docker / restic / config)
#   3  bad invocation (no client / no env file)
#   4  the pull or load FAILED while the terminal WAS reachable (real error)
#
# Per-client config is sourced from:  ${CLIENTS_DIR}/<client>/env  (chmod 600)
# Required env vars in that file:
#     MYSQL_HOST   tailnet IP or MagicDNS name of the terminal (e.g. 192.0.2.10)
#     MYSQL_USER   dedicated read-only MySQL user
#     MYSQL_PW     its password
#     MYSQL_DB     the OptimumPOS database name to mirror
# Optional:
#     MYSQL_PORT             (default 3306)
#     TWIN_CONTAINER         (default atlas-mariadb-<client>)
#     TWIN_ROOT_PW           root pw for the twin container (default from env or generated-once)
#     RESTIC_REPOSITORY      (default b2:atlas-pos-backups:/<client>)
#     RESTIC_PASSWORD / RESTIC_PASSWORD_FILE   per-tenant repo password
#     B2_ACCOUNT_ID / B2_ACCOUNT_KEY           Backblaze creds (or via env/file)
#     NTFY_URL               (default http://192.0.2.10:8136/ -> topic pos-mirror;
#                             atlas-ntfy publishes only on the tailnet-bound host IP,
#                             not a docker-DNS hostname or loopback — verified 2026-07-01)
#     LOCAL_KEEP             how many local dumps to keep (default 14)
# ---------------------------------------------------------------------------

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration (hub defaults; per-client env file overrides most of this)
# ----------------------------------------------------------------------------
POSOPS_ROOT="${POSOPS_ROOT:-/opt/atlas-pos}"
CLIENTS_DIR="${CLIENTS_DIR:-${POSOPS_ROOT}/clients}"
TWIN_NETWORK="${TWIN_NETWORK:-atlas-pos-twins}"   # internal docker net for twins
MARIADB_IMAGE="${MARIADB_IMAGE:-mariadb:11}"
PING_TIMEOUT="${PING_TIMEOUT:-5}"                 # tailscale ping timeout (s)
MYSQL_CONNECT_TIMEOUT="${MYSQL_CONNECT_TIMEOUT:-10}"
NTFY_DEFAULT_URL="${NTFY_URL:-http://192.0.2.10:8136/}"
NTFY_TOPIC="${NTFY_TOPIC:-pos-mirror}"

PROG="${0##*/}"

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
CLIENT=""    # set after parse; used by log prefix
ts()   { date -u +%Y-%m-%dT%H:%M:%SZ; }
log()  { printf '%s [%s] %s\n' "$(ts)" "${CLIENT:-?}" "$*"; }
warn() { printf '%s [%s] WARN: %s\n' "$(ts)" "${CLIENT:-?}" "$*" >&2; }
die()  { printf '%s [%s] ERROR: %s\n' "$(ts)" "${CLIENT:-?}" "$*" >&2; exit "${2:-3}"; }

usage() {
  cat >&2 <<EOF
Usage: ${PROG} <client>

Pulls <client>'s OptimumPOS MySQL up to pos-hub over Tailscale, stores a
versioned encrypted backup, refreshes the per-client read-twin, and ships to
Backblaze B2. Read-only against the terminal. If the terminal is offline it
skips cleanly (exit 0) — safe to run from cron / a systemd timer.

Config (chmod 600): ${CLIENTS_DIR}/<client>/env
EOF
}

[[ $# -ge 1 ]] || { usage; exit 3; }
CLIENT="$1"
# sanitize client token (used in paths/container/db names)
[[ "$CLIENT" =~ ^[a-z0-9_]+$ ]] || die "client must match [a-z0-9_]+ (got: $CLIENT)" 3

CLIENT_DIR="${CLIENTS_DIR}/${CLIENT}"
ENV_FILE="${CLIENT_DIR}/env"
DUMP_DIR="${CLIENT_DIR}/dumps"
LOG_DIR="${CLIENT_DIR}/logs"
STATUS_FILE="${CLIENT_DIR}/status.json"
MANIFEST="${DUMP_DIR}/SHA256SUMS"

# Concurrency guard: two timers (quiet-window + opportunistic) can fire for the
# same client. Take a non-blocking per-client lock; if held, exit cleanly.
LOCK="${TMPDIR:-/tmp}/posmirror-${CLIENT}.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(ts) [$CLIENT] another mirror run in progress — exiting" >&2
  exit 0
fi

# ----------------------------------------------------------------------------
# ntfy helper — best-effort; never let a notification failure fail the run.
#   prio: 1=min .. 5=max ; tags: comma list of ntfy emoji shortcodes
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

# Write a machine-readable status/freshness file atomically (for the staleness
# monitor + fleet inventory). result: success|skip|error.
write_status() {
  local result="$1" detail="$2" dump="${3:-}" rows="${4:-0}" bytes="${5:-0}"
  local tmp="${STATUS_FILE}.tmp.$$"
  if command -v jq >/dev/null 2>&1; then
    jq -n \
      --arg client "$CLIENT" \
      --arg result "$result" \
      --arg detail "$detail" \
      --arg at "$(ts)" \
      --arg dump "$dump" \
      --argjson epoch "$(date -u +%s)" \
      --argjson rows "${rows:-0}" \
      --argjson bytes "${bytes:-0}" \
      '{client:$client, result:$result, detail:$detail, at:$at,
        epoch:$epoch, last_dump:$dump, twin_rows_sample:$rows, dump_bytes:$bytes}' \
      > "$tmp" 2>/dev/null && mv -f "$tmp" "$STATUS_FILE" && return 0
  fi
  # Fallback without jq.
  printf '{"client":"%s","result":"%s","detail":"%s","at":"%s","epoch":%s}\n' \
    "$CLIENT" "$result" "$detail" "$(ts)" "$(date -u +%s)" > "$tmp" \
    && mv -f "$tmp" "$STATUS_FILE"
}

# ----------------------------------------------------------------------------
# Prerequisites + config
# ----------------------------------------------------------------------------
[[ -f "$ENV_FILE" ]] || die "missing per-client env file: $ENV_FILE (chmod 600, not in git)" 3

# Refuse a group/other-readable secrets file — fail closed (check BOTH group and other digits).
perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '')"
if [[ -n "$perm" && ( "${perm: -1}" != "0" || "${perm: -2:1}" != "0" ) ]]; then
  die "env file $ENV_FILE is group/other-readable (mode $perm) — refusing. Run: chmod 600 $ENV_FILE" 3
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${MYSQL_HOST:?MYSQL_HOST not set in $ENV_FILE}"
: "${MYSQL_USER:?MYSQL_USER not set in $ENV_FILE}"
: "${MYSQL_PW:?MYSQL_PW not set in $ENV_FILE}"
: "${MYSQL_DB:?MYSQL_DB not set in $ENV_FILE}"
MYSQL_PORT="${MYSQL_PORT:-3306}"

TWIN_CONTAINER="${TWIN_CONTAINER:-atlas-mariadb-${CLIENT}}"
TWIN_ROOT_PW="${TWIN_ROOT_PW:-}"
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-b2:atlas-pos-backups:/${CLIENT}}"
LOCAL_KEEP="${LOCAL_KEEP:-14}"

# ----------------------------------------------------------------------------
# MECHANICAL SAFETY GATE — fail closed. This mirror touches a LIVE card-payment
# terminal (read-only), so it runs ONLY when the operator has explicitly opted
# THIS client in AND the data-processing agreement is recorded. This makes the
# "preparation / consent" rule enforced in CODE, not just in the docs.
#   Set in the per-client env file (chmod 600) when ready, per client:
#     MIRROR_ENABLED=1            # operator opted this client in
#     DPA_SIGNED=1                # GDPR/AVG data-processing agreement on file
#     QUIET_WINDOW=01:00-06:00    # optional: only pull inside this local window
# Anything unset => REFUSE (clean skip, timer-safe).
# ----------------------------------------------------------------------------
if [[ "${MIRROR_ENABLED:-0}" != "1" ]]; then
  log "mirror NOT enabled for ${CLIENT} (set MIRROR_ENABLED=1 when ready) — refusing (fail-closed)"
  write_status "skip" "mirror-not-enabled"; exit 0
fi
if [[ "${DPA_SIGNED:-0}" != "1" ]]; then
  log "no DPA on file for ${CLIENT} (set DPA_SIGNED=1) — refusing to hold client data (GDPR/AVG)"
  write_status "skip" "dpa-unsigned"; exit 0
fi
# Transport assertion: Tailscale only, tailnet CGNAT 100.64.0.0/10 host only.
command -v tailscale >/dev/null 2>&1 || die "tailscale CLI required (Tailscale is the only transport)" 2
if [[ ! "$MYSQL_HOST" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\. ]]; then
  die "MYSQL_HOST=$MYSQL_HOST is not a tailnet (100.64.0.0/10) address — refusing off-tailnet connect" 3
fi
# Optional quiet-window enforcement (string-compares HH:MM; handles midnight wrap).
if [[ -n "${QUIET_WINDOW:-}" ]]; then
  now="$(date +%H:%M)"; qstart="${QUIET_WINDOW%-*}"; qend="${QUIET_WINDOW#*-}"; in_window=0
  if [[ "$qstart" < "$qend" ]]; then
    [[ "$now" > "$qstart" && "$now" < "$qend" ]] && in_window=1
  else
    [[ "$now" > "$qstart" || "$now" < "$qend" ]] && in_window=1
  fi
  if [[ "$in_window" -ne 1 ]]; then
    log "outside quiet window ${QUIET_WINDOW} (now ${now}) — skipping (will retry in-window)"
    write_status "skip" "outside-quiet-window"; exit 0
  fi
fi

mkdir -p "$DUMP_DIR" "$LOG_DIR"
chmod 700 "$CLIENT_DIR" 2>/dev/null || true

# mysqldump + mysql client are required for the pull.
command -v mysqldump  >/dev/null 2>&1 || die "mysqldump not found in PATH" 2
command -v mysqladmin >/dev/null 2>&1 || die "mysqladmin not found in PATH" 2

# A private defaults-file keeps the password OUT of the process list / ps output.
MYSQL_CNF="$(mktemp "${TMPDIR:-/tmp}/posmirror-${CLIENT}.XXXXXX.cnf")"
chmod 600 "$MYSQL_CNF"
cleanup() { rm -f "$MYSQL_CNF" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
cat > "$MYSQL_CNF" <<EOF
[client]
host=${MYSQL_HOST}
port=${MYSQL_PORT}
user=${MYSQL_USER}
password=${MYSQL_PW}
connect-timeout=${MYSQL_CONNECT_TIMEOUT}
EOF

log "mirror start  host=${MYSQL_HOST}:${MYSQL_PORT} db=${MYSQL_DB} twin=${TWIN_CONTAINER}"

# ----------------------------------------------------------------------------
# 1) Reachability gate. Terminal off => clean skip (exit 0). NOT an error.
#    Two independent checks: Tailscale ping, then a MySQL ping.
# ----------------------------------------------------------------------------
if command -v tailscale >/dev/null 2>&1; then
  if ! tailscale ping --c 1 --timeout "${PING_TIMEOUT}s" "$MYSQL_HOST" >/dev/null 2>&1; then
    log "terminal unreachable on tailnet — skipping (will retry next window)"
    write_status "skip" "tailnet-unreachable"
    notify "POS mirror skipped: ${CLIENT}" "Terminal offline on tailnet; will retry." 2 "zzz"
    exit 0
  fi
else
  warn "tailscale CLI not found; relying on MySQL ping for reachability"
fi

if ! mysqladmin --defaults-extra-file="$MYSQL_CNF" ping >/dev/null 2>&1; then
  log "MySQL not answering on ${MYSQL_HOST}:${MYSQL_PORT} — skipping (terminal up but DB down/closed)"
  write_status "skip" "mysql-down"
  notify "POS mirror skipped: ${CLIENT}" "Terminal reachable but MySQL not answering." 2 "warning"
  exit 0
fi

# ----------------------------------------------------------------------------
# 2) Consistent, READ-ONLY logical dump.
#    --single-transaction : consistent InnoDB snapshot, no write lock
#    --skip-lock-tables   : never lock the live POS tables
#    --quick              : stream rows (low memory)
#    --routines/--triggers/--events : capture full schema behavior
#    --set-gtid-purged=OFF / --no-tablespaces : portability into the twin
#  From this point a failure means the terminal WAS reachable -> real error (exit 4).
# ----------------------------------------------------------------------------
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${DUMP_DIR}/${CLIENT}-${TS}.sql.gz"
PART="${OUT}.partial"
DUMP_LOG="${LOG_DIR}/dump-${TS}.log"

log "dumping (single-transaction, read-only) -> ${OUT##*/}"
set +e
mysqldump --defaults-extra-file="$MYSQL_CNF" \
  --single-transaction --quick --routines --triggers --events \
  --set-gtid-purged=OFF --no-tablespaces --skip-lock-tables \
  --hex-blob --default-character-set=utf8mb4 \
  "$MYSQL_DB" 2>"$DUMP_LOG" | gzip > "$PART"
# capture pipe status: [0]=mysqldump [1]=gzip
dump_rc=${PIPESTATUS[0]}; gzip_rc=${PIPESTATUS[1]}
set -e

if [[ "$dump_rc" -ne 0 || "$gzip_rc" -ne 0 ]]; then
  rm -f "$PART"
  err="$(tail -n 3 "$DUMP_LOG" 2>/dev/null | tr '\n' ' ')"
  warn "mysqldump failed (mysqldump rc=$dump_rc gzip rc=$gzip_rc): $err"
  write_status "error" "mysqldump-failed rc=${dump_rc}/${gzip_rc}"
  notify "POS mirror FAILED: ${CLIENT}" "mysqldump rc=${dump_rc} gzip=${gzip_rc}. ${err}" 5 "rotating_light"
  exit 4
fi

# Sanity: a real OptimumPOS dump is never tiny. Guard against a truncated/empty file.
dump_bytes="$(stat -c %s "$PART" 2>/dev/null || echo 0)"
if [[ "$dump_bytes" -lt 200 ]]; then
  rm -f "$PART"
  warn "dump suspiciously small (${dump_bytes} bytes) — treating as failure"
  write_status "error" "dump-too-small ${dump_bytes}b"
  notify "POS mirror FAILED: ${CLIENT}" "Dump only ${dump_bytes} bytes — aborting." 5 "rotating_light"
  exit 4
fi

# 2b) Atomic publish: only a complete file ever appears as the canonical dump.
mv -f "$PART" "$OUT"
log "dump published (${dump_bytes} bytes)"

# ----------------------------------------------------------------------------
# 3) Checksum manifest.
# ----------------------------------------------------------------------------
if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$DUMP_DIR" && sha256sum "$(basename "$OUT")" >> "$MANIFEST" )
  log "checksum recorded in ${MANIFEST##*/}"
fi

# ----------------------------------------------------------------------------
# 4) Refresh the per-client queryable TWIN (atlas-mariadb-<client>).
#    Idempotent: ensure the container exists, then DROP+CREATE the db and load
#    the latest dump. The twin is always "the latest pull". If docker/restic are
#    absent we still keep the versioned dump (backup is never blocked on the twin).
# ----------------------------------------------------------------------------
load_twin() {
  command -v docker >/dev/null 2>&1 || { warn "docker not found; skipping twin load (dump still saved)"; return 1; }

  # ensure the internal twin network exists (idempotent)
  docker network inspect "$TWIN_NETWORK" >/dev/null 2>&1 \
    || docker network create "$TWIN_NETWORK" >/dev/null 2>&1 || true

  # generate-once root pw; persist in a SEPARATE file (never mutate the human-authored env)
  if [[ -z "$TWIN_ROOT_PW" ]]; then
    local pwfile="${CLIENT_DIR}/twin.pw"
    if [[ -s "$pwfile" ]]; then
      TWIN_ROOT_PW="$(cat "$pwfile")"
    else
      TWIN_ROOT_PW="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 28)"
      ( umask 077; printf '%s' "$TWIN_ROOT_PW" > "$pwfile" )
      log "generated and stored TWIN_ROOT_PW in ${pwfile##*/} (chmod 600)"
    fi
  fi

  # ensure the twin container is running (idempotent: start if stopped, create if absent)
  if docker ps --format '{{.Names}}' | grep -qx "$TWIN_CONTAINER"; then
    : # already running
  elif docker ps -a --format '{{.Names}}' | grep -qx "$TWIN_CONTAINER"; then
    log "starting existing twin container ${TWIN_CONTAINER}"
    docker start "$TWIN_CONTAINER" >/dev/null
  else
    log "creating twin container ${TWIN_CONTAINER} (volume atlas-twin-${CLIENT})"
    docker run -d --name "$TWIN_CONTAINER" \
      --network "$TWIN_NETWORK" \
      --restart unless-stopped \
      -e MARIADB_ROOT_PASSWORD="$TWIN_ROOT_PW" \
      -v "atlas-twin-${CLIENT}:/var/lib/mysql" \
      "$MARIADB_IMAGE" >/dev/null
  fi

  # wait for the twin to accept connections (bounded)
  local i
  for i in $(seq 1 30); do
    if docker exec "$TWIN_CONTAINER" mariadb-admin -uroot -p"$TWIN_ROOT_PW" ping >/dev/null 2>&1 \
       || docker exec "$TWIN_CONTAINER" mysqladmin -uroot -p"$TWIN_ROOT_PW" ping >/dev/null 2>&1; then
      break
    fi
    sleep 1
    [[ "$i" -eq 30 ]] && { warn "twin ${TWIN_CONTAINER} not ready after 30s; dump saved, twin not refreshed"; return 1; }
  done

  # pick whichever client binary the image ships (mariadb vs mysql)
  local TWIN_CLI="mariadb"
  docker exec "$TWIN_CONTAINER" sh -c 'command -v mariadb >/dev/null 2>&1' || TWIN_CLI="mysql"

  # DROP + CREATE the target db, then stream the gzipped dump in. Full refresh.
  log "loading dump into twin db '${MYSQL_DB}' via ${TWIN_CLI}"
  docker exec -i "$TWIN_CONTAINER" "$TWIN_CLI" -uroot -p"$TWIN_ROOT_PW" \
    -e "DROP DATABASE IF EXISTS \`${MYSQL_DB}\`; CREATE DATABASE \`${MYSQL_DB}\` CHARACTER SET utf8mb4;" \
    || { warn "twin recreate failed"; return 1; }

  if ! gunzip -c "$OUT" | docker exec -i "$TWIN_CONTAINER" "$TWIN_CLI" -uroot -p"$TWIN_ROOT_PW" "$MYSQL_DB"; then
    warn "twin load failed; the versioned dump is still safe on disk"
    return 1
  fi

  # quick sanity: count tables loaded
  local ntab
  ntab="$(docker exec "$TWIN_CONTAINER" "$TWIN_CLI" -uroot -p"$TWIN_ROOT_PW" -N -B \
    -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${MYSQL_DB}';" 2>/dev/null || echo 0)"
  log "twin refreshed: ${ntab} tables in '${MYSQL_DB}'"
  TWIN_TABLES="$ntab"
  return 0
}

TWIN_TABLES=0
twin_ok=1
load_twin || twin_ok=0

# ----------------------------------------------------------------------------
# 5) Encrypted offsite backup with restic -> Backblaze B2 (per-client repo).
#    The dump tree is encrypted at rest by restic. If restic isn't configured
#    we keep the local versioned dump and just warn (backup is best-effort here,
#    but a missing offsite copy is surfaced via ntfy).
# ----------------------------------------------------------------------------
backup_restic() {
  command -v restic >/dev/null 2>&1 || { warn "restic not found; offsite backup skipped"; return 1; }
  # restic reads RESTIC_REPOSITORY + RESTIC_PASSWORD(_FILE) + B2 creds from env
  export RESTIC_REPOSITORY
  # init repo if it doesn't exist yet (idempotent)
  if ! restic snapshots >/dev/null 2>&1; then
    log "initializing restic repo ${RESTIC_REPOSITORY}"
    restic init >/dev/null 2>&1 || { warn "restic init failed (check RESTIC_PASSWORD / B2 creds)"; return 1; }
  fi
  log "restic backup -> ${RESTIC_REPOSITORY}"
  if ! restic backup --tag "pos-mirror" --tag "$CLIENT" "$DUMP_DIR" >/dev/null 2>&1; then
    warn "restic backup failed"
    return 1
  fi
  # retention: keep recent history offsite; prune the rest.
  restic forget --tag "$CLIENT" \
    --keep-last 14 --keep-daily 14 --keep-weekly 8 --keep-monthly 12 \
    --prune >/dev/null 2>&1 || warn "restic forget/prune reported an issue (non-fatal)"
  return 0
}

restic_ok=1
backup_restic || restic_ok=0

# ----------------------------------------------------------------------------
# 6) Local dump retention — bound disk on the hub. Keep newest LOCAL_KEEP.
#    The long tail lives in B2. Manifest is left intact.
# ----------------------------------------------------------------------------
prune_local() {
  local keep="$LOCAL_KEEP"
  mapfile -t all < <(ls -1t "${DUMP_DIR}"/*.sql.gz 2>/dev/null || true)
  local n=${#all[@]}
  if (( n > keep )); then
    local i
    for (( i=keep; i<n; i++ )); do
      rm -f "${all[$i]}" && log "pruned old local dump ${all[$i]##*/}"
    done
  fi
}
prune_local

# ----------------------------------------------------------------------------
# 7) Status + notify. Success even if twin/restic were degraded, because the
#    primary artifact (a consistent versioned dump) exists. We DO downgrade the
#    notification priority / message so the operator knows the state.
# ----------------------------------------------------------------------------
write_status "success" \
  "twin_ok=${twin_ok} restic_ok=${restic_ok} tables=${TWIN_TABLES}" \
  "$(basename "$OUT")" "$TWIN_TABLES" "$dump_bytes"

if [[ "$twin_ok" -eq 1 && "$restic_ok" -eq 1 ]]; then
  log "mirror OK (dump + twin + offsite all good)"
  notify "POS mirror OK: ${CLIENT}" \
    "Dump ${dump_bytes}B, twin ${TWIN_TABLES} tables, offsite B2 done." 2 "white_check_mark"
else
  log "mirror completed WITH WARNINGS (twin_ok=${twin_ok} restic_ok=${restic_ok})"
  notify "POS mirror PARTIAL: ${CLIENT}" \
    "Dump saved (${dump_bytes}B) but twin_ok=${twin_ok} restic_ok=${restic_ok}. Investigate." 4 "warning"
fi

exit 0
