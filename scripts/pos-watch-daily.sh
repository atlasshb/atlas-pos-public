#!/bin/bash
# pos-watch-daily.sh — dagelijkse POS-status-samenvatting per client (mail + ntfy)
# Loopt via cron op pos-hub. Leest de watch-state.json van elke client en stuurt
# een statusmail. Toggle off per client met DAILY_MAIL=0 in clients/<client>/env.
#
# Gebruik:
#   pos-watch-daily.sh            # alle clients met clients/<slug>/
#   pos-watch-daily.sh venue_b    # specifieke client
set -u
POSOPS_ROOT="${POSOPS_ROOT:-/opt/atlas-pos}"
CLIENTS_DIR="${CLIENTS_DIR:-${POSOPS_ROOT}/clients}"
NOTIFY="/opt/atlas/notify/atlas_notify.py"
NOW_EPOCH="$(date -u +%s)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

declare -a SLUGS
if [[ $# -ge 1 ]]; then
  SLUGS=("$@")
else
  SLUGS=($(find "$CLIENTS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort))
fi

report=""
for slug in "${SLUGS[@]}"; do
  [[ "$slug" =~ ^[a-z0-9_]+$ ]] || continue
  state="$CLIENTS_DIR/$slug/watch-state.json"
  envf="$CLIENTS_DIR/$slug/env"
  daily=1
  if [[ -f "$envf" ]]; then
    set -a; source "$envf"; set +a
    [[ -n "${DAILY_MAIL:-}" ]] && daily="$DAILY_MAIL"
  fi
  if [[ "$daily" != "1" ]]; then
    continue
  fi
  if [[ ! -s "$state" ]]; then
    report+="* $slug: geen status bekend (nog nooit gecheckt)\n"
    continue
  fi
  last=$(jq -r '.last_status // "unknown"' "$state" 2>/dev/null || echo unknown)
  chg=$(jq -r '.last_change_at // ""' "$state" 2>/dev/null || echo "")
  chg_epoch=$(jq -r '.last_change_epoch // 0' "$state" 2>/dev/null || echo 0)
  [[ "$chg_epoch" =~ ^[0-9]+$ ]] || chg_epoch=0
  ago=""
  if [[ "$chg_epoch" -gt 0 ]]; then
    secs=$(( NOW_EPOCH - chg_epoch ))
    if [[ "$secs" -ge 86400 ]]; then
      ago="$(( secs / 86400 ))d $(( (secs % 86400) / 3600 ))h geleden"
    elif [[ "$secs" -ge 3600 ]]; then
      ago="$(( secs / 3600 ))h $(( (secs % 3600) / 60 ))m geleden"
    else
      ago="$(( secs / 60 ))m geleden"
    fi
  fi
  report+="* $slug: $last (veranderd $chg ${ago})"$'\n'
done

if [[ -z "$report" ]]; then
  report="Geen clients geconfigureerd of alle daily-mail uit."
fi

if [[ -x "$NOTIFY" ]]; then
  "$NOTIFY" "POS dagelijkse status ($TS)" "$report" normal >/dev/null 2>&1
fi
echo "$report"
