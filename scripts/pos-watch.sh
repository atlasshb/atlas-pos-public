#!/usr/bin/env bash
#
# pos-watch.sh — Atlas POS program, reachability WATCHER (read-only monitoring)
# ---------------------------------------------------------------------------
# Runs ON pos-hub (the always-on hub). For ONE client, this does a hub-side
# READ-ONLY reachability check of that client's terminal over Tailscale:
#
#   1. tailscale ping  (is the box up on the tailnet at all)
#   2. TCP port probe on MYSQL_PORT (default 3306) and/or ODOO_PORT (default 8069)
#
# It NEVER logs in to anything, NEVER opens a MySQL/Odoo session, and makes NO
# writes of any kind TO THE TERMINAL (it does write a local state file + an ntfy
# push, but both stay entirely on the hub side). It is pure network probing —
# same risk class as fleet-inventory.sh's probes, which already run unattended.
# This is why, unlike pos-mirror.sh, it carries NO MIRROR_ENABLED/DPA_SIGNED
# gate: read-only reachability monitoring is not "touching a live terminal" in
# the sense PROGRAM.md principle #1 means (no data pulled, no session opened).
#
# It is designed to be driven from cron or a systemd timer, frequently, once
# per client:
#     pos-watch.sh venue_a
#     pos-watch.sh venue_b
#
# WHY THIS SHAPE:
#   * Read-only, hub-initiated, Tailscale-only. Never touches the terminal
#     beyond an ICMP-over-WireGuard ping and a bare TCP connect() probe.
#   * Idempotent + stateful. Tracks last-known status per client so we only
#     notify on a TRANSITION (offline<->online), never spam on steady state.
#   * Own flock, own lock name — deliberately distinct from pos-mirror.sh's
#     lock so a slow mirror run and a frequent watch tick never block each
#     other.
#   * Safe for a tight timer cadence (every few minutes): each run is a bounded
#     handful of network probes, nothing more.
#
# Exit codes:
#   0  always, on any normal outcome (online, offline, no-op skip) — timer-safe
#   2  missing prerequisite (tailscale CLI / jq)
#   3  bad invocation (no client)
#
# Per-client config is sourced from:  ${CLIENTS_DIR}/<client>/env  (chmod 600)
# if present; every value has a sensible default so pos-watch.sh runs even
# before a client's env file exists.
#   Optional (read from clients/<client>/env if present):
#     MYSQL_HOST   tailnet IP or MagicDNS name of the terminal (default: unset -> skip probe)
#     MYSQL_PORT   (default 3306)
#     ODOO_PORT    (default 8069)
#   Optional watcher-specific overrides (env or shell):
#     WATCH_HOST           override host to probe (falls back to MYSQL_HOST)
#     PROBE_TIMEOUT        TCP connect timeout, seconds (default 5)
#     PING_TIMEOUT         tailscale ping timeout, seconds (default 5)
#     HEARTBEAT_AFTER_H    hours offline before a daily low-prio heartbeat (default 24)
#     NTFY_URL             (default http://192.0.2.10:8136/ -> topic pos-mirror;
#                           atlas-ntfy publishes only on the tailnet-bound host IP,
#                           not a docker-DNS hostname or loopback — verified 2026-07-01)
#     NTFY_TOPIC           (default pos-mirror)
# ---------------------------------------------------------------------------

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration (hub defaults; per-client env file overrides most of this)
# ----------------------------------------------------------------------------
POSOPS_ROOT="${POSOPS_ROOT:-/opt/atlas-pos}"
CLIENTS_DIR="${CLIENTS_DIR:-${POSOPS_ROOT}/clients}"
PING_TIMEOUT="${PING_TIMEOUT:-5}"                 # tailscale ping timeout (s)
PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}"               # TCP connect probe timeout (s)
HEARTBEAT_AFTER_H="${HEARTBEAT_AFTER_H:-24}"      # hrs offline before a daily heartbeat
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

READ-ONLY reachability watcher for <client>'s terminal over Tailscale:
tailscale ping + TCP port probes on MYSQL_PORT/ODOO_PORT. No login, no
mysql/xmlrpc session, no writes to the terminal at all. Pushes ntfy only on
an OFFLINE<->ONLINE transition (plus an optional daily heartbeat while
offline past HEARTBEAT_AFTER_H hours). Safe to run every few minutes from a
timer.

Config (optional, chmod 600): ${CLIENTS_DIR}/<client>/env
State written to:             ${CLIENTS_DIR}/<client>/watch-state.json
EOF
}

[[ $# -ge 1 ]] || { usage; exit 3; }
CLIENT="$1"
# sanitize client token (used in paths)
[[ "$CLIENT" =~ ^[a-z0-9_]+$ ]] || die "client must match [a-z0-9_]+ (got: $CLIENT)" 3

CLIENT_DIR="${CLIENTS_DIR}/${CLIENT}"
ENV_FILE="${CLIENT_DIR}/env"
STATE_FILE="${CLIENT_DIR}/watch-state.json"

# Concurrency guard: own lock, own name — distinct from pos-mirror's
# "posmirror-<client>.lock" so a mirror pull and a watch tick never contend.
LOCK="${TMPDIR:-/tmp}/poswatch-${CLIENT}.lock"
exec 8>"$LOCK"
if ! flock -n 8; then
  echo "$(ts) [$CLIENT] another watch run in progress — exiting" >&2
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
  # Mail copy of every transition alert to the operator (best-effort; uses
  # the Atlas unified notifier -> smtp.json -> atlas@example.com).
  # Toggle off per-client with MAIL_NOTIFY=0 in clients/<client>/env.
  if [[ "${MAIL_NOTIFY:-1}" == "1" ]] && command -v python3 >/dev/null 2>&1 && \
     [[ -x /opt/atlas/notify/atlas_notify.py ]]; then
    /opt/atlas/notify/atlas_notify.py "POS watch: ${title}" \
      "${message}" "${MAIL_PRIO:-normal}" >/dev/null 2>&1 \
      || warn "atlas_notify (mail) failed (non-fatal)"
  fi
}

# ----------------------------------------------------------------------------
# Prerequisites
# ----------------------------------------------------------------------------
command -v tailscale >/dev/null 2>&1 || die "tailscale not found in PATH" 2

mkdir -p "$CLIENT_DIR" 2>/dev/null || die "cannot create CLIENT_DIR=$CLIENT_DIR" 3

# ----------------------------------------------------------------------------
# Optional per-client config. Unlike pos-mirror.sh this file is NOT required:
# the watcher degrades to sensible defaults (tailscale MagicDNS name = client
# slug) so monitoring can run before a client's env is fully provisioned.
# ----------------------------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
  perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '')"
  if [[ -n "$perm" && ( "${perm: -1}" != "0" || "${perm: -2:1}" != "0" ) ]]; then
    die "env file $ENV_FILE is group/other-readable (mode $perm) — refusing. Run: chmod 600 $ENV_FILE" 3
  fi
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
else
  log "no env file at $ENV_FILE — using defaults (MagicDNS host = ${CLIENT})"
fi

MYSQL_PORT="${MYSQL_PORT:-3306}"
ODOO_PORT="${ODOO_PORT:-8069}"
# WATCH_HOST wins if set; else MYSQL_HOST from env; else fall back to the
# client slug as a Tailscale MagicDNS name (works if the node is named that).
WATCH_HOST="${WATCH_HOST:-${MYSQL_HOST:-$CLIENT}}"

# ----------------------------------------------------------------------------
# TCP port probe — read-only connect() test. Never sends data.
#   Prefers nc if present, else falls back to bash /dev/tcp (same pattern as
#   fleet-inventory.sh's probe_port, kept local here so this script has no
#   dependency on another script's internals).
#   Returns 0 = open, 1 = closed/filtered/timeout.
# ----------------------------------------------------------------------------
probe_port() {
  local host="$1" port="$2"
  if command -v nc >/dev/null 2>&1; then
    nc -z -w "$PROBE_TIMEOUT" "$host" "$port" >/dev/null 2>&1
    return $?
  fi
  if command -v timeout >/dev/null 2>&1; then
    timeout "$PROBE_TIMEOUT" bash -c "exec 3<>/dev/tcp/$host/$port" >/dev/null 2>&1
    return $?
  fi
  ( exec 3<>"/dev/tcp/$host/$port" ) >/dev/null 2>&1
}

# ----------------------------------------------------------------------------
# Read previous state (best-effort; missing/corrupt state = treat as unknown).
# ----------------------------------------------------------------------------
prev_status="unknown"
prev_change_epoch=0
prev_heartbeat_epoch=0
if [[ -s "$STATE_FILE" ]]; then
  if command -v jq >/dev/null 2>&1; then
    prev_status="$(jq -r '.last_status // "unknown"' "$STATE_FILE" 2>/dev/null || echo unknown)"
    prev_change_epoch="$(jq -r '.last_change_epoch // 0' "$STATE_FILE" 2>/dev/null || echo 0)"
    prev_heartbeat_epoch="$(jq -r '.last_heartbeat_epoch // 0' "$STATE_FILE" 2>/dev/null || echo 0)"
  else
    # Dependency-light fallback parse (no jq): grep the flat keys we wrote.
    prev_status="$(grep -o '"last_status"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATE_FILE" 2>/dev/null \
      | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/' | head -n1)"
    [[ -z "$prev_status" ]] && prev_status="unknown"
    prev_change_epoch="$(grep -o '"last_change_epoch"[[:space:]]*:[[:space:]]*[0-9]*' "$STATE_FILE" 2>/dev/null \
      | grep -o '[0-9]*$' | head -n1)"
    [[ -z "$prev_change_epoch" ]] && prev_change_epoch=0
    prev_heartbeat_epoch="$(grep -o '"last_heartbeat_epoch"[[:space:]]*:[[:space:]]*[0-9]*' "$STATE_FILE" 2>/dev/null \
      | grep -o '[0-9]*$' | head -n1)"
    [[ -z "$prev_heartbeat_epoch" ]] && prev_heartbeat_epoch=0
  fi
fi
[[ "$prev_change_epoch" =~ ^[0-9]+$ ]] || prev_change_epoch=0
[[ "$prev_heartbeat_epoch" =~ ^[0-9]+$ ]] || prev_heartbeat_epoch=0

# ----------------------------------------------------------------------------
# Probe (read-only): tailnet ping, then TCP reachability on MySQL/Odoo ports.
# "online" = tailscale ping answers AND at least one of the two ports is open.
# (A box can be up on the tailnet with both services down; we still count
# that as reachable-but-degraded = online for THIS watcher's purpose, since
# our job is terminal reachability, not service health.)
# ----------------------------------------------------------------------------
tailnet_up=0
if tailscale ping --c 1 --timeout "${PING_TIMEOUT}s" "$WATCH_HOST" >/dev/null 2>&1; then
  tailnet_up=1
fi

mysql_open=0
odoo_open=0
if [[ "$tailnet_up" -eq 1 ]]; then
  probe_port "$WATCH_HOST" "$MYSQL_PORT" && mysql_open=1 || mysql_open=0
  probe_port "$WATCH_HOST" "$ODOO_PORT"  && odoo_open=1  || odoo_open=0
fi

now_epoch="$(date -u +%s)"
if [[ "$tailnet_up" -eq 1 && ( "$mysql_open" -eq 1 || "$odoo_open" -eq 1 ) ]]; then
  cur_status="online"
else
  cur_status="offline"
fi

log "probe host=${WATCH_HOST} tailnet_up=${tailnet_up} mysql:${MYSQL_PORT}=${mysql_open} odoo:${ODOO_PORT}=${odoo_open} -> ${cur_status}"

# ----------------------------------------------------------------------------
# Write state atomically. last_change_at only moves on an actual transition.
# ----------------------------------------------------------------------------
write_state() {
  local status="$1" change_epoch="$2" heartbeat_epoch="$3"
  local tmp="${STATE_FILE}.tmp.$$"
  if command -v jq >/dev/null 2>&1; then
    jq -n \
      --arg client "$CLIENT" \
      --arg last_status "$status" \
      --arg last_change_at "$(date -u -d "@${change_epoch}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || ts)" \
      --argjson last_change_epoch "$change_epoch" \
      --arg checked_at "$(ts)" \
      --argjson checked_epoch "$now_epoch" \
      --argjson last_heartbeat_epoch "$heartbeat_epoch" \
      --argjson tailnet_up "$tailnet_up" \
      --argjson mysql_open "$mysql_open" \
      --argjson odoo_open "$odoo_open" \
      --arg host "$WATCH_HOST" \
      '{client:$client, last_status:$last_status, last_change_at:$last_change_at,
        last_change_epoch:$last_change_epoch, checked_at:$checked_at,
        checked_epoch:$checked_epoch, last_heartbeat_epoch:$last_heartbeat_epoch,
        host:$host, tailnet_up:($tailnet_up==1), mysql_open:($mysql_open==1),
        odoo_open:($odoo_open==1)}' \
      > "$tmp" 2>/dev/null && mv -f "$tmp" "$STATE_FILE" && return 0
  fi
  # Fallback without jq.
  printf '{"client":"%s","last_status":"%s","last_change_epoch":%s,"checked_at":"%s","checked_epoch":%s,"last_heartbeat_epoch":%s,"host":"%s"}\n' \
    "$CLIENT" "$status" "$change_epoch" "$(ts)" "$now_epoch" "$heartbeat_epoch" "$WATCH_HOST" > "$tmp" \
    && mv -f "$tmp" "$STATE_FILE"
}

# ----------------------------------------------------------------------------
# Transition + heartbeat logic. Silent on steady-state to avoid spam.
# ----------------------------------------------------------------------------
change_epoch="$prev_change_epoch"
heartbeat_epoch="$prev_heartbeat_epoch"

if [[ "$prev_status" != "$cur_status" ]]; then
  change_epoch="$now_epoch"
  heartbeat_epoch=0   # reset heartbeat clock on any transition

  if [[ "$prev_status" == "unknown" ]]; then
    # First-ever observation: record state, don't alarm the operator.
    log "first observation for ${CLIENT}: ${cur_status} (no notification)"
  elif [[ "$cur_status" == "online" ]]; then
    log "transition OFFLINE -> ONLINE"
    notify "POS watch: ${CLIENT} back online" \
      "${CLIENT} is back online (reachable on tailnet, host ${WATCH_HOST})." 3 "green_circle,online"
  else
    log "transition ONLINE -> OFFLINE"
    notify "POS watch: ${CLIENT} offline" \
      "${CLIENT} went offline (unreachable on tailnet, host ${WATCH_HOST})." 3 "red_circle,offline"
  fi
else
  # Same state as last check — stay silent, except an optional low-priority
  # daily heartbeat if we've been offline for a long stretch.
  if [[ "$cur_status" == "offline" && "$change_epoch" -gt 0 ]]; then
    offline_secs=$(( now_epoch - change_epoch ))
    offline_hours=$(( offline_secs / 3600 ))
    heartbeat_age_secs=$(( now_epoch - heartbeat_epoch ))
    if [[ "$offline_hours" -ge "$HEARTBEAT_AFTER_H" && "$heartbeat_age_secs" -ge 86400 ]]; then
      log "still offline after ${offline_hours}h — sending low-priority daily heartbeat"
      notify "POS watch: ${CLIENT} still offline" \
        "${CLIENT} has been offline for ~${offline_hours}h (since $(date -u -d "@${change_epoch}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown))." \
        1 "zzz"
      heartbeat_epoch="$now_epoch"
    fi
  fi
fi

write_state "$cur_status" "$change_epoch" "$heartbeat_epoch"

exit 0
