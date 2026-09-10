#!/usr/bin/env bash
#
# fleet-inventory.sh — Atlas POS program, capability A (DISCOVER + INVENTORY)
# ---------------------------------------------------------------------------
# Runs ON pos-hub (the always-on hub). Enumerates the Tailscale tailnet and,
# for every peer, READ-ONLY-probes the ports that identify an DoPos box
# (MySQL :3306), an Odoo instance (:8069) and SMB file sharing (:445). It then
# joins what it finds against the declarative client registry (registry.yml)
# and the on-hub program state (twins, dumps, Odoo DBs) to classify each client
# as discovered / enrolled / mirrored / migrated.
#
# Output:
#   * machine-readable JSON  -> <STATE_DIR>/fleet-inventory.json  (+ stdout if -j)
#   * human-readable table   -> stdout
#
# SAFETY / DESIGN NOTES (these are hard constraints, not preferences):
#   * 100% READ-ONLY. This script never writes to, logs into, or mutates any
#     client terminal. It only checks TCP reachability of ports over the tailnet.
#     A port probe is a connect()+close() — it sends no credentials and no SQL.
#   * Terminals power off often. Unreachable == a normal state, reported as
#     "offline", never an error. The script always exits 0 on a clean run so it
#     is safe to drive from cron / a systemd timer.
#   * Tailscale is the sole transport. We never probe public IPs.
#   * No secrets are read or required by this script.
#
# Exit codes:
#   0  ran successfully (regardless of how many terminals were offline)
#   2  a hard prerequisite is missing (tailscale / jq not installed)
#   3  bad invocation / unwritable state dir
#
# Dependencies: bash 4+, tailscale, jq. (nc/bash-/dev/tcp used for probes.)
# ---------------------------------------------------------------------------

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration (override via environment; sensible hub defaults otherwise)
# ----------------------------------------------------------------------------
POSOPS_ROOT="${POSOPS_ROOT:-/opt/atlas-pos}"
REGISTRY_FILE="${REGISTRY_FILE:-${POSOPS_ROOT}/registry.yml}"
CLIENTS_DIR="${CLIENTS_DIR:-${POSOPS_ROOT}/clients}"
STATE_DIR="${STATE_DIR:-${POSOPS_ROOT}/state}"
OUT_JSON="${OUT_JSON:-${STATE_DIR}/fleet-inventory.json}"

# Ports we fingerprint. Keep these in one place.
PORT_MYSQL="${PORT_MYSQL:-3306}"   # DoPos local MySQL
PORT_ODOO="${PORT_ODOO:-8069}"     # Odoo web/xmlrpc
PORT_SMB="${PORT_SMB:-445}"        # SMB file share

# Per-probe TCP connect timeout (seconds). Terminals on home internet are slow.
PROBE_TIMEOUT="${PROBE_TIMEOUT:-4}"
# tailscale ping timeout per node.
PING_TIMEOUT="${PING_TIMEOUT:-5}"

EMIT_JSON_STDOUT=0   # -j : also print the JSON document to stdout
QUIET=0              # -q : suppress the human table (JSON/file only)

# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
log()  { [[ "$QUIET" -eq 1 ]] && return 0; printf '%s\n' "$*" >&2; }
die()  { printf 'fleet-inventory: %s\n' "$*" >&2; exit "${2:-3}"; }

usage() {
  cat >&2 <<EOF
Usage: ${0##*/} [-j] [-q] [-o OUT_JSON]

Enumerates the Tailscale tailnet, read-only-probes each node for DoPos
(MySQL :${PORT_MYSQL}), Odoo (:${PORT_ODOO}) and SMB (:${PORT_SMB}), and writes a
fleet inventory (JSON + human table). Always read-only; never touches a terminal.

Options:
  -j            also print the JSON document to stdout
  -q            quiet: skip the human-readable table
  -o OUT_JSON   path for the JSON output (default: ${OUT_JSON})
  -h            this help

Environment overrides: POSOPS_ROOT, REGISTRY_FILE, CLIENTS_DIR, STATE_DIR,
OUT_JSON, PORT_MYSQL, PORT_ODOO, PORT_SMB, PROBE_TIMEOUT, PING_TIMEOUT.
EOF
}

while getopts ":jqo:h" opt; do
  case "$opt" in
    j) EMIT_JSON_STDOUT=1 ;;
    q) QUIET=1 ;;
    o) OUT_JSON="$OPTARG" ;;
    h) usage; exit 0 ;;
    \?) die "unknown option -$OPTARG (use -h)" 3 ;;
    :)  die "option -$OPTARG needs an argument" 3 ;;
  esac
done

# ----------------------------------------------------------------------------
# Prerequisites
# ----------------------------------------------------------------------------
command -v tailscale >/dev/null 2>&1 || die "tailscale not found in PATH" 2
command -v jq        >/dev/null 2>&1 || die "jq not found in PATH" 2

mkdir -p "$STATE_DIR" 2>/dev/null || die "cannot create STATE_DIR=$STATE_DIR" 3
[[ -w "$STATE_DIR" ]] || die "STATE_DIR not writable: $STATE_DIR" 3

# ----------------------------------------------------------------------------
# TCP port probe — read-only connect() test.
#   Prefers nc if present (cleanest), else falls back to bash /dev/tcp.
#   Returns 0 = open, 1 = closed/filtered/timeout. Never sends data.
# ----------------------------------------------------------------------------
probe_port() {
  local host="$1" port="$2"
  if command -v nc >/dev/null 2>&1; then
    # -z zero-I/O (scan), -w timeout. Discard all output.
    nc -z -w "$PROBE_TIMEOUT" "$host" "$port" >/dev/null 2>&1
    return $?
  fi
  # Fallback: bash builtin /dev/tcp wrapped in `timeout` so a filtered port
  # cannot hang us. Subshell so the redirection target is closed immediately.
  if command -v timeout >/dev/null 2>&1; then
    timeout "$PROBE_TIMEOUT" bash -c "exec 3<>/dev/tcp/$host/$port" >/dev/null 2>&1
    return $?
  fi
  # Last resort: no timeout available — still safe, just slower on filtered ports.
  ( exec 3<>"/dev/tcp/$host/$port" ) >/dev/null 2>&1
}

# ----------------------------------------------------------------------------
# Registry lookup (best-effort, dependency-light).
#   registry.yml is NON-secret client topology. We extract, per client, the
#   declared tailnet host/IP and the friendly client name. We DO NOT require a
#   YAML parser: a tiny awk reader handles the flat "clients:" mapping shape
#   described in the design. If yq is installed we prefer it for robustness.
#
# Expected (illustrative) registry.yml shape:
#   clients:
#     venue_a:
#       name: "Venue A"
#       host: "192.0.2.10"        # tailnet IP or MagicDNS name
#       node: "venue-a-till"
#       enabled: true
#     venue_b:
#       name: "Venue B"
#       host: "192.0.2.10"
#       node: "venue-b-till"
#       enabled: true
#
# We map a discovered tailnet node to a registry client by matching either the
# node's tailnet IP or its hostname against host/node fields.
# ----------------------------------------------------------------------------

# Emits NDJSON: {"client","name","host","node","enabled"} one per registry entry.
read_registry() {
  [[ -f "$REGISTRY_FILE" ]] || return 0

  if command -v yq >/dev/null 2>&1; then
    # Robust path when yq (v4) is available.
    yq -o=json '.clients // {}' "$REGISTRY_FILE" 2>/dev/null \
      | jq -c 'to_entries[] | {
          client: .key,
          name:   (.value.name   // .key),
          host:   (.value.host   // ""),
          node:   (.value.node   // ""),
          enabled:(.value.enabled // true)
        }' 2>/dev/null
    return 0
  fi

  # Fallback flat-YAML reader: handles 2-space-indented "clients:" mapping.
  awk '
    function flush(  ) {
      if (cur != "") {
        printf "{\"client\":\"%s\",\"name\":\"%s\",\"host\":\"%s\",\"node\":\"%s\",\"enabled\":%s}\n",
               cur, (name==""?cur:name), host, node, (enabled==""?"true":enabled)
      }
      cur=""; name=""; host=""; node=""; enabled=""
    }
    /^[[:space:]]*#/ { next }
    /^clients:[[:space:]]*$/ { inclients=1; next }
    inclients && /^[^[:space:]]/ { inclients=0; flush() }   # left the clients block
    inclients && /^  [A-Za-z0-9_]+:[[:space:]]*$/ {
      flush()
      line=$0; sub(/:[[:space:]]*$/,"",line); sub(/^[[:space:]]+/,"",line); cur=line; next
    }
    inclients && /^    [A-Za-z0-9_]+:[[:space:]]*.*/ {
      key=$0; sub(/^[[:space:]]+/,"",key); sub(/:.*$/,"",key)
      val=$0; sub(/^[[:space:]]*[A-Za-z0-9_]+:[[:space:]]*/,"",val)
      gsub(/^["'"'"']|["'"'"']$/,"",val)   # strip surrounding quotes
      if (key=="name")    name=val
      else if (key=="host") host=val
      else if (key=="node") node=val
      else if (key=="enabled") enabled=(val=="true"||val=="True"||val=="yes"?"true":"false")
    }
    END { flush() }
  ' "$REGISTRY_FILE" 2>/dev/null || true
}

# ----------------------------------------------------------------------------
# On-hub program state — used to decide "mirrored" and "migrated".
#   mirrored : a per-client twin dump exists under clients/<c>/dumps/*.sql.gz
#   migrated : an Odoo Postgres DB named after the client exists in atlas-odoo-db
# Both are best-effort and degrade gracefully (absence -> false, never error).
# ----------------------------------------------------------------------------

client_is_mirrored() {
  local c="$1"
  local d="${CLIENTS_DIR}/${c}/dumps"
  [[ -d "$d" ]] || return 1
  # any non-empty .sql.gz dump means we have pulled this client at least once
  compgen -G "${d}/*.sql.gz" >/dev/null 2>&1
}

# Returns last-success dump epoch (0 if none).
client_last_pull_epoch() {
  local c="$1"
  local d="${CLIENTS_DIR}/${c}/dumps"
  [[ -d "$d" ]] || { echo 0; return; }
  # newest .sql.gz mtime
  local newest
  newest="$(ls -1t "${d}"/*.sql.gz 2>/dev/null | head -n1 || true)"
  [[ -n "$newest" ]] || { echo 0; return; }
  date -r "$newest" +%s 2>/dev/null || stat -c %Y "$newest" 2>/dev/null || echo 0
}

# Best-effort check whether an Odoo DB for this client exists on the hub.
# Uses the atlas-odoo-db Postgres container if reachable; never fails the run.
client_is_migrated() {
  local c="$1"
  command -v docker >/dev/null 2>&1 || return 1
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'atlas-odoo-db' || return 1
  # List databases; match the client technical name exactly (venue_b pattern).
  docker exec atlas-odoo-db psql -U odoo -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${c}'" 2>/dev/null | grep -qx 1
}

# ----------------------------------------------------------------------------
# 1) Pull the tailnet peer list as JSON from the local tailscaled.
# ----------------------------------------------------------------------------
log "==> querying tailnet status"
TS_JSON="$(tailscale status --json 2>/dev/null || true)"
if [[ -z "$TS_JSON" ]]; then
  die "could not read 'tailscale status --json' (is tailscaled up and are we logged in?)" 2
fi

# Normalize peers (and Self) into a flat list of {host, ip, online, os}.
# We take the FIRST tailnet IP of each node. Self is included so the hub shows up.
NODES_JSON="$(
  printf '%s' "$TS_JSON" | jq -c '
    [ (.Self // empty), (.Peer // {} | .[]) ]
    | map({
        host:   (.HostName // .DNSName // "unknown"),
        dns:    (.DNSName // ""),
        ip:     ((.TailscaleIPs // [])[0] // ""),
        online: (.Online // false),
        os:     (.OS // "")
      })
    | map(select(.ip != ""))
  '
)"

# ----------------------------------------------------------------------------
# 2) Load registry into an assoc structure for matching, plus a JSON array.
# ----------------------------------------------------------------------------
REGISTRY_NDJSON="$(read_registry || true)"
REGISTRY_JSON="$( { printf '%s\n' "$REGISTRY_NDJSON" | grep -v '^$' || true; } | jq -s '.' 2>/dev/null || echo '[]')"

# Map a node (ip/host) -> registry client object (or null). Pure jq join.
match_client() {
  local ip="$1" host="$2"
  printf '%s' "$REGISTRY_JSON" | jq -c --arg ip "$ip" --arg host "$host" '
    map(select(
        (.host == $ip) or (.node == $host) or
        (.host == $host) or
        ($host | ascii_downcase) == ((.node // "") | ascii_downcase)
    )) | (.[0] // null)
  '
}

NOW_EPOCH="$(date -u +%s)"

# ----------------------------------------------------------------------------
# 3) Iterate nodes, probe ports, classify. Build a JSON array of node records.
# ----------------------------------------------------------------------------
log "==> probing nodes (read-only TCP: ${PORT_MYSQL}/${PORT_ODOO}/${PORT_SMB})"

node_records=()   # accumulate JSON objects

# Track which registry clients were matched to a live node, so we can also
# emit registry-only clients (declared but not seen on the tailnet => offline).
declare -A SEEN_CLIENT=()

while IFS= read -r node; do
  [[ -n "$node" ]] || continue
  host="$(jq -r '.host'   <<<"$node")"
  ip="$(jq -r '.ip'       <<<"$node")"
  online="$(jq -r '.online' <<<"$node")"
  os="$(jq -r '.os'       <<<"$node")"

  # Identify the registry client this node belongs to (if any).
  cli_obj="$(match_client "$ip" "$host")"
  client="$(jq -r 'if .==null then "" else .client end' <<<"$cli_obj")"
  cname="$(jq -r  'if .==null then "" else .name   end' <<<"$cli_obj")"
  [[ -n "$client" ]] && SEEN_CLIENT["$client"]=1

  # Reachability gate: if Tailscale already reports the node offline, treat it
  # as offline and SKIP port probes entirely (don't waste timeouts on a dead box).
  reachable=false
  if [[ "$online" == "true" ]]; then
    if tailscale ping -c1 --timeout "${PING_TIMEOUT}s" "$ip" >/dev/null 2>&1; then
      reachable=true
    fi
  fi

  mysql_open=false; odoo_open=false; smb_open=false
  if [[ "$reachable" == "true" ]]; then
    probe_port "$ip" "$PORT_MYSQL" && mysql_open=true
    probe_port "$ip" "$PORT_ODOO"  && odoo_open=true
    probe_port "$ip" "$PORT_SMB"   && smb_open=true
  fi

  # --- classification ------------------------------------------------------
  # enrolled : node is on our tailnet (true for everything we can see here)
  # discovered : enrolled but NOT yet present in registry.yml (unknown client)
  # has_dopos : MySQL :3306 reachable
  # has_odoo       : Odoo  :8069 reachable
  # mirrored : we hold at least one twin dump for the client on the hub
  # migrated : an Odoo DB for the client exists on atlas-odoo-db
  enrolled=true
  discovered=true
  in_registry=false
  if [[ -n "$client" ]]; then in_registry=true; fi

  mirrored=false; migrated=false; last_pull_epoch=0
  if [[ -n "$client" ]]; then
    if client_is_mirrored "$client"; then mirrored=true; fi
    last_pull_epoch="$(client_last_pull_epoch "$client")"
    if client_is_migrated "$client"; then migrated=true; fi
  fi

  status="offline"
  [[ "$reachable" == "true" ]] && status="online"

  rec="$(jq -nc \
    --arg host "$host" --arg ip "$ip" --arg os "$os" \
    --arg client "$client" --arg cname "$cname" \
    --arg status "$status" \
    --argjson reachable "$reachable" \
    --argjson in_registry "$in_registry" \
    --argjson enrolled "$enrolled" \
    --argjson discovered "$discovered" \
    --argjson mysql_open "$mysql_open" \
    --argjson odoo_open "$odoo_open" \
    --argjson smb_open "$smb_open" \
    --argjson mirrored "$mirrored" \
    --argjson migrated "$migrated" \
    --argjson last_pull_epoch "${last_pull_epoch:-0}" \
    '{
      host: $host, ip: $ip, os: $os,
      client: (if $client=="" then null else $client end),
      client_name: (if $cname=="" then null else $cname end),
      status: $status,
      reachable: $reachable,
      in_registry: $in_registry,
      enrolled: $enrolled,
      discovered: $discovered,
      ports: { mysql_3306: $mysql_open, odoo_8069: $odoo_open, smb_445: $smb_open },
      has_dopos: $mysql_open,
      has_odoo: $odoo_open,
      mirrored: $mirrored,
      migrated: $migrated,
      last_pull_epoch: $last_pull_epoch
    }')"
  node_records+=("$rec")
done < <(printf '%s' "$NODES_JSON" | jq -c '.[]')

# ----------------------------------------------------------------------------
# 4) Add registry clients that were NOT seen on the tailnet at all.
#    These are declared-but-absent (powered off, or not currently enrolled).
#    Marked enrolled=false when they have no tailnet host yet, else offline.
# ----------------------------------------------------------------------------
while IFS= read -r r; do
  [[ -n "$r" ]] || continue
  c="$(jq -r '.client' <<<"$r")"
  [[ -n "$c" ]] || continue
  [[ -n "${SEEN_CLIENT[$c]:-}" ]] && continue   # already represented by a node

  cname="$(jq -r '.name' <<<"$r")"
  chost="$(jq -r '.host' <<<"$r")"
  cnode="$(jq -r '.node' <<<"$r")"

  mirrored=false; migrated=false; last_pull_epoch=0
  if client_is_mirrored "$c"; then mirrored=true; fi
  last_pull_epoch="$(client_last_pull_epoch "$c")"
  if client_is_migrated "$c"; then migrated=true; fi

  # If the registry gives a tailnet host, it's enrolled-but-offline; otherwise
  # it's a known client not yet on the tailnet (discovery target).
  enrolled=true
  [[ -z "$chost" && -z "$cnode" ]] && enrolled=false

  rec="$(jq -nc \
    --arg host "${cnode:-$chost}" --arg ip "$chost" \
    --arg client "$c" --arg cname "$cname" \
    --argjson enrolled "$enrolled" \
    --argjson mirrored "$mirrored" \
    --argjson migrated "$migrated" \
    --argjson last_pull_epoch "${last_pull_epoch:-0}" \
    '{
      host: $host, ip: $ip, os: "",
      client: $client, client_name: $cname,
      status: "offline", reachable: false,
      in_registry: true, enrolled: $enrolled, discovered: true,
      ports: { mysql_3306: false, odoo_8069: false, smb_445: false },
      has_dopos: false, has_odoo: false,
      mirrored: $mirrored, migrated: $migrated,
      last_pull_epoch: $last_pull_epoch
    }')"
  node_records+=("$rec")
done < <(printf '%s' "$REGISTRY_NDJSON" | grep -v '^$' || true)

# ----------------------------------------------------------------------------
# 5) Assemble the final document and write it atomically.
# ----------------------------------------------------------------------------
NODES_ARRAY="$(printf '%s\n' "${node_records[@]:-}" | grep -v '^$' | jq -s '.' 2>/dev/null || echo '[]')"

DOC="$(jq -n \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg hub "pos-hub" \
  --argjson now_epoch "$NOW_EPOCH" \
  --argjson nodes "$NODES_ARRAY" \
  '{
    generated_at: $generated_at,
    hub: $hub,
    now_epoch: $now_epoch,
    summary: {
      nodes_total:        ($nodes | length),
      online:             ($nodes | map(select(.reachable)) | length),
      with_dopos:    ($nodes | map(select(.has_dopos)) | length),
      with_odoo:          ($nodes | map(select(.has_odoo)) | length),
      enrolled:           ($nodes | map(select(.enrolled)) | length),
      mirrored:           ($nodes | map(select(.mirrored)) | length),
      migrated:           ($nodes | map(select(.migrated)) | length),
      discovered_unknown: ($nodes | map(select(.in_registry|not)) | length)
    },
    nodes: $nodes
  }')"

tmp="${OUT_JSON}.tmp.$$"
printf '%s\n' "$DOC" > "$tmp"
mv -f "$tmp" "$OUT_JSON"
log "==> wrote $OUT_JSON"

[[ "$EMIT_JSON_STDOUT" -eq 1 ]] && printf '%s\n' "$DOC"

# ----------------------------------------------------------------------------
# 6) Human-readable table.
#    Columns: CLIENT  HOST  IP  STATUS  POS(3306)  ODOO(8069)  SMB(445)  PHASE
#    PHASE is the program lifecycle: migrated > mirrored > enrolled > discovered
# ----------------------------------------------------------------------------
if [[ "$QUIET" -ne 1 ]]; then
  {
    echo
    echo "Atlas POS Fleet Inventory  —  $(date -u +%Y-%m-%dT%H:%M:%SZ)  (hub: pos-hub)"
    echo "Read-only tailnet probe. 'offline' = terminal not reachable (normal for intermittent boxes)."
    echo
    printf '%s\n' "$DOC" | jq -r '
      def yn(b): if b then "yes" else "-" end;
      def phase(n):
        if   n.migrated  then "migrated"
        elif n.mirrored  then "mirrored"
        elif (n.in_registry|not) then "discovered"
        elif n.enrolled  then "enrolled"
        else "known" end;
      ( ["CLIENT","HOST","IP","STATUS","POS","ODOO","SMB","PHASE"]
      , ["------","----","--","------","---","----","---","-----"]
      , ( .nodes
          | sort_by([( .client // "zzz" ), .host])
          | .[]
          | [ (.client_name // .client // "(unknown)")
            , (.host // "-")
            , (.ip // "-")
            , .status
            , yn(.ports.mysql_3306)
            , yn(.ports.odoo_8069)
            , yn(.ports.smb_445)
            , phase(.)
            ] )
      ) | @tsv
    ' | column -t -s "$(printf '\t')"
    echo
    printf '%s\n' "$DOC" | jq -r '
      .summary
      | "Summary: \(.nodes_total) nodes  |  \(.online) online  |  "
        + "\(.with_dopos) DoPos  |  \(.with_odoo) Odoo  |  "
        + "\(.mirrored) mirrored  |  \(.migrated) migrated  |  "
        + "\(.discovered_unknown) unknown(not in registry)"
    '
    echo
  } >&2
fi

exit 0
