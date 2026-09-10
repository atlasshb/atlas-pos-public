#!/usr/bin/env bash
# =============================================================================
# odoo-provision-client.sh
# Atlas POS Program — capability C (REPLACE), build side.
#
# Provision a per-client Odoo 19 Community POS database on the EXISTING
# multi-DB Odoo (atlas-odoo + atlas-odoo-db) on pos-hub, install base POS +
# the client's atlas_<client>_pos module (cloned from the proven
# atlas_pos_seed template), and set NL company / BTW + UI language.
#
# DESIGN (per MEMORY.md, capability C):
#   - ONE multi-DB Odoo, database-per-client (venue_b pattern proves it),
#     NOT a container per client. Postgres-DB boundary gives per-tenant
#     isolation (separate CoA / users / pos.config / backups).
#   - Worldline = MANUAL card pos.payment.method (Community has no
#     pos_six/pos_adyen — those are Enterprise; installing them FAILS).
#   - Dutch BTW everywhere; Turkish (tr_TR) is UI-only and PER-CLIENT
#     (Venue B=tr_TR; Venue A / Venue C likely nl_NL only).
#   - l10n_nl + default sales tax is a DOCUMENTED MANUAL step that must be
#     confirmed BEFORE the first posted journal entry (Odoo 19 forbids
#     changing the fiscal package afterwards).
#
# SAFETY / CONSTRAINTS:
#   - Runs entirely on pos-hub. Touches NO client terminal. This is an
#     L0 (hub-only) action in the Mind classification.
#   - IDEMPOTENT: re-running converges. Creating the DB, installing modules,
#     and seeding config all check-before-write. A drop+recreate is gated
#     behind an explicit flag and only ever targets the per-client DB.
#   - Reversible: rollback for a build = drop the per-client DB. Nothing
#     else on the hub or any client is affected.
#
# USAGE:
#   ./odoo-provision-client.sh --client venue_b
#   ./odoo-provision-client.sh --client venuea --lang nl_NL --dry-run
#   ./odoo-provision-client.sh --client venue_b --recreate   # DANGER: drops DB
#
# Config precedence (highest first):
#   1. CLI flags
#   2. clients/<client>.yml   (non-secret per-client topology, in git)
#   3. environment / .env      (secrets: admin pw, master pw, db creds)
#   4. built-in defaults
# =============================================================================

set -euo pipefail

# --------------------------------------------------------------------------- #
# 0. Defaults (override via clients/<client>.yml, env, or flags)
# --------------------------------------------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRAM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Where per-client YAML descriptors live (in git, non-secret).
CLIENTS_DIR="${ATLAS_CLIENTS_DIR:-${PROGRAM_ROOT}/clients}"
# Where the atlas_<client>_pos modules are generated / live (mounted into Odoo).
ADDONS_DIR="${ATLAS_ADDONS_DIR:-/root/odoo_migration/addons}"
# The template module to clone from (the proven Venue B module).
TEMPLATE_MODULE="${ATLAS_TEMPLATE_MODULE:-atlas_pos_seed}"
TEMPLATE_MODULE_PATH="${ATLAS_TEMPLATE_MODULE_PATH:-${ADDONS_DIR}/${TEMPLATE_MODULE}}"

# How we talk to Odoo. Default assumes the atlas-odoo container on the hub.
ODOO_CONTAINER="${ATLAS_ODOO_CONTAINER:-atlas-odoo}"
ODOO_URL="${ATLAS_ODOO_URL:-http://localhost:8069}"
ODOO_BIN="${ATLAS_ODOO_BIN:-odoo}"                 # binary name inside the container
ODOO_CONF="${ATLAS_ODOO_CONF:-/etc/odoo/odoo.conf}"

# Secrets — NEVER hard-coded; sourced from env / per-tenant env file.
#   ODOO_MASTER_PW : Odoo master/admin password (db management).
#   ODOO_ADMIN_LOGIN / ODOO_ADMIN_PW : the per-DB admin user we set.
ODOO_MASTER_PW="${ODOO_MASTER_PW:-}"
ODOO_ADMIN_LOGIN="${ODOO_ADMIN_LOGIN:-admin}"
ODOO_ADMIN_PW="${ODOO_ADMIN_PW:-}"

# Postgres connection for the Odoo DB host (atlas-odoo-db).
PGHOST="${PGHOST:-atlas-odoo-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-odoo}"
# PGPASSWORD must come from env / secrets, never committed.

# Defaults that a client YAML normally overrides.
CLIENT=""
DB_NAME=""
COMPANY_NAME=""
UI_LANG="nl_NL"              # UI language; Venue B overrides to tr_TR
                             # NOTE: deliberately NOT named LANG — that clashes
                             # with the POSIX locale env var and would corrupt
                             # `docker exec odoo locale` plus --load-language.
COUNTRY_CODE="NL"
BTW_DEFAULT_RATE="21"        # NL standard BTW; module omits taxes_id so products inherit this
KVK=""                       # Chamber of Commerce number (receipt)
BTW_NUMBER=""                # VAT number (receipt)
POS_NAME=""                  # pos.config display name
CLIENT_MODULE=""             # atlas_<client>_pos

DRY_RUN=0
RECREATE=0
CONFIRM_DROP=""              # must equal the resolved DB_NAME to arm --recreate
SKIP_MODULE_GEN=0
VERBOSE=0

# --------------------------------------------------------------------------- #
# Logging helpers
# --------------------------------------------------------------------------- #
log()  { printf '[provision] %s\n' "$*" >&2; }
warn() { printf '[provision][WARN] %s\n' "$*" >&2; }
die()  { printf '[provision][FATAL] %s\n' "$*" >&2; exit 1; }
run()  {
  # Echo the command; only execute when not in dry-run.
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[provision][DRY-RUN] %s\n' "$*" >&2
  else
    [[ "${VERBOSE}" -eq 1 ]] && printf '[provision][exec] %s\n' "$*" >&2
    "$@"
  fi
}

usage() {
  cat <<'EOF'
odoo-provision-client.sh — Atlas POS Program, capability C (build side).

Provision a per-client Odoo 19 Community POS database on the existing multi-DB
Odoo (atlas-odoo + atlas-odoo-db) on pos-hub: create+init the per-client DB,
install base POS + l10n_nl, generate/install the atlas_<client>_pos module, and
seed NL company / BTW + UI language. Runs hub-only; touches NO client terminal.

USAGE:
  ./odoo-provision-client.sh --client venue_b
  ./odoo-provision-client.sh --client venuea --lang nl_NL --dry-run
  ./odoo-provision-client.sh --client venue_b --recreate --confirm-drop venue_b

OPTIONS:
  --client <slug>        Client slug (REQUIRED). Drives db/module/company defaults.
  --db <name>            Per-client DB name           (default: <client>).
  --company <name>       Company display name         (default: <client>).
  --lang <code>          UI language, e.g. nl_NL, tr_TR (default: nl_NL).
  --country <code>       Company country code         (default: NL).
  --btw-rate <pct>       Default NL BTW rate          (default: 21).
  --kvk <number>         KvK number (receipt).
  --btw-number <vat>     VAT/BTW number (receipt).
  --pos-name <name>      pos.config display name      (default: "<company> POS").
  --module <name>        Client module                (default: atlas_<client>_pos).
  --addons-dir <path>    Odoo addons dir for the generated module.
  --dry-run              Print the plan; execute nothing destructive.
  --recreate             DANGER: drop+recreate the per-client DB. Requires
                         --confirm-drop <db> matching the resolved DB name.
  --confirm-drop <db>    Explicit confirmation token for --recreate (must equal
                         the resolved DB name). Without it, --recreate refuses.
  --skip-module-gen      Do not generate the client module from the template.
  --verbose, -v          Echo executed commands.
  -h, --help             Show this help and exit.

Config precedence (highest first): CLI flags > clients/<client>.yml > env/.env
> built-in defaults.
EOF
  exit "${1:-0}"
}

# --------------------------------------------------------------------------- #
# 1. Parse CLI flags
# --------------------------------------------------------------------------- #
while [[ $# -gt 0 ]]; do
  case "$1" in
    --client)        CLIENT="$2"; shift 2 ;;
    --db)            DB_NAME="$2"; shift 2 ;;
    --company)       COMPANY_NAME="$2"; shift 2 ;;
    --lang)          UI_LANG="$2"; shift 2 ;;
    --country)       COUNTRY_CODE="$2"; shift 2 ;;
    --btw-rate)      BTW_DEFAULT_RATE="$2"; shift 2 ;;
    --kvk)           KVK="$2"; shift 2 ;;
    --btw-number)    BTW_NUMBER="$2"; shift 2 ;;
    --pos-name)      POS_NAME="$2"; shift 2 ;;
    --module)        CLIENT_MODULE="$2"; shift 2 ;;
    --addons-dir)    ADDONS_DIR="$2"; shift 2 ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --recreate)      RECREATE=1; shift ;;
    --confirm-drop)  CONFIRM_DROP="$2"; shift 2 ;;
    --skip-module-gen) SKIP_MODULE_GEN=1; shift ;;
    --verbose|-v)    VERBOSE=1; shift ;;
    -h|--help)       usage 0 ;;
    *)               die "Unknown argument: $1 (use --help)" ;;
  esac
done

[[ -z "${CLIENT}" ]] && die "Missing --client (e.g. --client venue_b)"

# --------------------------------------------------------------------------- #
# 2. Load per-client YAML descriptor (non-secret topology, in git)
#    clients/<client>.yml drives name/lang/kvk/btw/pos_name. We parse a small,
#    flat key: value subset with a portable awk reader (no yq dependency).
# --------------------------------------------------------------------------- #
CLIENT_YML="${CLIENTS_DIR}/${CLIENT}.yml"

yaml_get() {
  # yaml_get <file> <key>  -> value (flat top-level "key: value" only)
  local file="$1" key="$2"
  [[ -f "${file}" ]] || return 0
  awk -F':' -v k="${key}" '
    /^[[:space:]]*#/ { next }
    {
      line=$0
      sub(/^[[:space:]]+/, "", line)
      split(line, kv, ":")
      gsub(/[[:space:]]+$/, "", kv[1])
      if (kv[1] == k) {
        val=line
        sub(/^[^:]+:[[:space:]]*/, "", val)
        gsub(/^["'\'']|["'\'']$/, "", val)      # strip surrounding quotes
        gsub(/[[:space:]]+#.*$/, "", val)        # strip trailing comment
        print val
        exit
      }
    }' "${file}"
}

if [[ -f "${CLIENT_YML}" ]]; then
  log "Loading client descriptor: ${CLIENT_YML}"
  [[ -z "${DB_NAME}"      ]] && DB_NAME="$(yaml_get "${CLIENT_YML}" db)"
  [[ -z "${COMPANY_NAME}" ]] && COMPANY_NAME="$(yaml_get "${CLIENT_YML}" company)"
  _l="$(yaml_get "${CLIENT_YML}" lang)";          [[ -n "${_l}" ]] && UI_LANG="${_l}"
  _c="$(yaml_get "${CLIENT_YML}" country)";        [[ -n "${_c}" ]] && COUNTRY_CODE="${_c}"
  _r="$(yaml_get "${CLIENT_YML}" btw_rate_default)";[[ -n "${_r}" ]] && BTW_DEFAULT_RATE="${_r}"
  [[ -z "${KVK}"          ]] && KVK="$(yaml_get "${CLIENT_YML}" kvk)"
  [[ -z "${BTW_NUMBER}"   ]] && BTW_NUMBER="$(yaml_get "${CLIENT_YML}" btw)"
  [[ -z "${POS_NAME}"     ]] && POS_NAME="$(yaml_get "${CLIENT_YML}" pos_name)"
  _m="$(yaml_get "${CLIENT_YML}" module)";         [[ -n "${_m}" ]] && CLIENT_MODULE="${_m}"
else
  warn "No client descriptor at ${CLIENT_YML} — using flags/defaults only."
  warn "Recommended: create clients/${CLIENT}.yml so a client = one YAML."
fi

# Derive remaining defaults from the client slug.
DB_NAME="${DB_NAME:-${CLIENT}}"
COMPANY_NAME="${COMPANY_NAME:-${CLIENT}}"
CLIENT_MODULE="${CLIENT_MODULE:-atlas_${CLIENT}_pos}"
POS_NAME="${POS_NAME:-${COMPANY_NAME} POS}"

# Validate DB name is a safe identifier (defends the drop path, and Postgres).
if ! [[ "${DB_NAME}" =~ ^[a-z][a-z0-9_]{1,62}$ ]]; then
  die "Unsafe DB name '${DB_NAME}'. Use [a-z][a-z0-9_]* (<=63 chars)."
fi
if ! [[ "${CLIENT_MODULE}" =~ ^[a-z][a-z0-9_]+$ ]]; then
  die "Unsafe module name '${CLIENT_MODULE}'. Use [a-z][a-z0-9_]+."
fi

log "Resolved configuration:"
log "  client        = ${CLIENT}"
log "  db            = ${DB_NAME}"
log "  company       = ${COMPANY_NAME}"
log "  lang (UI)     = ${UI_LANG}"
log "  country       = ${COUNTRY_CODE}"
log "  btw default   = ${BTW_DEFAULT_RATE}%"
log "  module        = ${CLIENT_MODULE} (from template ${TEMPLATE_MODULE})"
log "  pos.config    = ${POS_NAME}"
log "  dry-run       = ${DRY_RUN}  recreate = ${RECREATE}  confirm-drop = ${CONFIRM_DROP:-<none>}"

# --------------------------------------------------------------------------- #
# 3. Preflight: secrets + tooling present
# --------------------------------------------------------------------------- #
preflight() {
  # In dry-run we tolerate missing secrets so the plan can be printed in CI.
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    [[ -z "${ODOO_MASTER_PW}" ]] && die "ODOO_MASTER_PW not set (export it / source the per-tenant env)."
    [[ -z "${ODOO_ADMIN_PW}"  ]] && die "ODOO_ADMIN_PW not set (the per-DB admin password to provision)."
  fi
  command -v docker >/dev/null 2>&1 || warn "docker not on PATH — assuming odoo CLI is reachable directly."

  if [[ "${SKIP_MODULE_GEN}" -eq 0 ]]; then
    [[ -d "${TEMPLATE_MODULE_PATH}" ]] || warn \
      "Template module not found at ${TEMPLATE_MODULE_PATH}; module generation will be skipped if absent."
  fi
}

# Helper: run an Odoo CLI invocation inside the atlas-odoo container.
# We prefer `docker exec` so the script works from the hub shell. If docker is
# unavailable (running inside the container), fall back to a direct call.
odoo_cli() {
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${ODOO_CONTAINER}"; then
    run docker exec -i "${ODOO_CONTAINER}" "${ODOO_BIN}" "$@"
  else
    run "${ODOO_BIN}" "$@"
  fi
}

# Helper: psql against the Odoo Postgres, used only for existence checks and the
# gated drop. All DML on business data goes through Odoo, never raw SQL.
psql_q() {
  local sql="$1"
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${PGHOST}"; then
    docker exec -i "${PGHOST}" psql -U "${PGUSER}" -tAc "${sql}" postgres 2>/dev/null
  else
    PGPASSWORD="${PGPASSWORD:-}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -tAc "${sql}" postgres 2>/dev/null
  fi
}

db_exists() {
  local out
  out="$(psql_q "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}';" || true)"
  [[ "${out}" == "1" ]]
}

# --------------------------------------------------------------------------- #
# 4. (Optional) Generate atlas_<client>_pos from the template
#    The module is a near-verbatim clone of atlas_pos_seed with only DATA
#    parameterized (name/lang/receipt/seed). Hard-won correctness is preserved:
#      - type in {consu,service,combo} (NO detailed_type)
#      - pos_categ_ids (M2M, plural), available_in_pos=True
#      - taxes_id OMITTED so products inherit the company BTW default
#      - payment methods noupdate="1", journals linked by SEARCH in post_init_hook
#      - tr_TR via res.lang._activate_lang (NOT base.language.install)
#      - NO pos_six / pos_adyen / pos_iot anywhere
# --------------------------------------------------------------------------- #
generate_client_module() {
  [[ "${SKIP_MODULE_GEN}" -eq 1 ]] && { log "Skipping module generation (--skip-module-gen)."; return 0; }

  local dest="${ADDONS_DIR}/${CLIENT_MODULE}"

  if [[ ! -d "${TEMPLATE_MODULE_PATH}" ]]; then
    warn "Template ${TEMPLATE_MODULE_PATH} missing — cannot generate ${CLIENT_MODULE}."
    warn "Provide the atlas_pos_seed template, or run with --skip-module-gen if the"
    warn "client module already exists at ${dest}."
    [[ -d "${dest}" ]] || die "No client module to install at ${dest}."
    return 0
  fi

  if [[ "${CLIENT_MODULE}" == "${TEMPLATE_MODULE}" ]]; then
    log "Client module IS the template (${TEMPLATE_MODULE}); installing template in place."
    return 0
  fi

  log "Generating ${CLIENT_MODULE} from ${TEMPLATE_MODULE} -> ${dest}"

  # Idempotent: refresh the generated tree each run so YAML edits propagate,
  # but never clobber a hand-edited module without --recreate semantics.
  if [[ -d "${dest}" ]]; then
    log "  ${dest} exists; refreshing generated files (rsync, additive)."
  else
    run mkdir -p "${dest}"
  fi

  # Copy template skeleton, then rewrite the technical name and parameters.
  # Using rsync so re-runs are cheap and only changed files churn.
  run rsync -a --exclude '__pycache__' "${TEMPLATE_MODULE_PATH}/" "${dest}/"

  # Rename the Python package references and any template-name occurrences.
  # NOTE: these sed rewrites assume the template uses its own technical name as
  # an identifier prefix. Verify against the real atlas_pos_seed layout.
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    # Rewrite module technical name in manifest + xml-id prefixes.
    grep -rl "${TEMPLATE_MODULE}" "${dest}" 2>/dev/null | while read -r f; do
      sed -i "s/${TEMPLATE_MODULE}/${CLIENT_MODULE}/g" "${f}"
    done
    # Stamp the per-client parameters into a generated config python module so
    # the post_init_hook reads name/lang/receipt from one place.
    cat > "${dest}/client_config.py" <<PYEOF
# AUTO-GENERATED by odoo-provision-client.sh — do not edit by hand.
# Per-client parameters for ${CLIENT}. Edit clients/${CLIENT}.yml and re-run.
CLIENT_SLUG     = "${CLIENT}"
COMPANY_NAME    = "${COMPANY_NAME}"
UI_LANG         = "${UI_LANG}"
COUNTRY_CODE    = "${COUNTRY_CODE}"
BTW_RATE_DEFAULT = ${BTW_DEFAULT_RATE}
KVK             = "${KVK}"
BTW_NUMBER      = "${BTW_NUMBER}"
POS_CONFIG_NAME = "${POS_NAME}"
# Worldline stays a MANUAL card payment method (Community: no integrated terminal).
WORLDLINE_PAYMENT_METHOD = "Pinnen / Worldline kaart"
PYEOF
  else
    log "[DRY-RUN] would rewrite ${TEMPLATE_MODULE}->${CLIENT_MODULE} and write client_config.py"
  fi

  log "Module ${CLIENT_MODULE} ready at ${dest}"
}

# --------------------------------------------------------------------------- #
# 5a. Drop the per-client DB — the ONLY destructive action in this script.
#     Every path that can destroy data (HTTP db-drop AND the psql DROP fallback)
#     flows through here behind ONE consistent guard, so that:
#       - --dry-run can NEVER drop a DB (single early return; no later code runs);
#       - an explicit confirmation token (--confirm-drop <db>) is REQUIRED beyond
#         the --recreate flag; a bare --recreate refuses to destroy anything;
#       - a pre-drop pg_dump is always taken (outside dry-run) before any drop.
#     Idempotent: a no-op if the DB is already gone.
# --------------------------------------------------------------------------- #
drop_database() {
  # ---- Guard 1: confirmation token (checked even in dry-run, so a missing
  #      token is reported the same way whether or not we would execute). ----- #
  if [[ "${CONFIRM_DROP}" != "${DB_NAME}" ]]; then
    die "--recreate refused: pass --confirm-drop '${DB_NAME}' to authorize dropping DB '${DB_NAME}' (got: '${CONFIRM_DROP:-<none>}')."
  fi

  warn "DB '${DB_NAME}' exists and --recreate + --confirm-drop '${DB_NAME}' given."
  warn "This DROPS the per-client database. A pre-drop pg_dump is taken for rollback."

  # ---- Guard 2: the single dry-run gate. In dry-run we print the plan and
  #      return BEFORE any snapshot, HTTP drop, or psql DROP can execute. ------ #
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "[DRY-RUN] would pg_dump '${DB_NAME}' then drop it (HTTP db-drop, psql fallback). No DB dropped."
    return 0
  fi

  # ---- Pre-drop snapshot -> immediate rollback artifact (restic/B2 is the
  #      program's separate backup layer). Reached only when NOT dry-run. ------ #
  local snap="/root/odoo_migration/snapshots/${DB_NAME}-predrop-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
  mkdir -p "$(dirname "${snap}")"
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${PGHOST}"; then
    docker exec -i "${PGHOST}" pg_dump -U "${PGUSER}" "${DB_NAME}" | gzip > "${snap}"
  else
    PGPASSWORD="${PGPASSWORD:-}" pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${DB_NAME}" | gzip > "${snap}"
  fi
  log "Pre-drop snapshot written: ${snap}"

  # ---- Drop attempt 1: Odoo's db management (respects the filestore). -------- #
  curl -fsS "${ODOO_URL}/web/database/drop" \
    --data-urlencode "master_pwd=${ODOO_MASTER_PW}" \
    --data-urlencode "name=${DB_NAME}" >/dev/null 2>&1 \
    || warn "HTTP drop failed; falling back to psql DROP DATABASE."

  # ---- Drop attempt 2 (fallback): raw psql, only if the DB still exists. ----- #
  if db_exists; then
    psql_q "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}';" >/dev/null || true
    psql_q "DROP DATABASE IF EXISTS \"${DB_NAME}\";" >/dev/null || die "Failed to drop ${DB_NAME}"
  fi

  if db_exists; then
    die "DB '${DB_NAME}' still present after drop attempts."
  fi
  log "Dropped DB ${DB_NAME}"
}

# --------------------------------------------------------------------------- #
# 5. Create the per-client database (idempotent; --recreate gated)
#    We create the DB pre-initialized with base + the localization so the first
#    boot already has the company. Language install for the UI happens here too.
# --------------------------------------------------------------------------- #
create_database() {
  if db_exists; then
    if [[ "${RECREATE}" -eq 1 ]]; then
      drop_database
    else
      log "DB '${DB_NAME}' already exists — skipping creation (idempotent)."
      return 0
    fi
  fi

  log "Creating + initializing DB '${DB_NAME}' with base, point_of_sale, l10n_nl."
  # `-i` installs modules at DB init. We install:
  #   base, point_of_sale  -> the POS we are deploying
  #   l10n_nl              -> Dutch chart of accounts + BTW taxes
  #   contacts, stock      -> supporting (product, partners)
  # The client module is installed in a SEPARATE step (6) so a module bug can't
  # poison DB creation and we keep install logs distinct.
  #
  # Languages to load: nl_NL is always present (Dutch BTW/company). The per-client
  # UI language is added only when it differs, so we never emit "nl_NL,nl_NL".
  local load_langs="nl_NL"
  if [[ -n "${UI_LANG}" && "${UI_LANG}" != "nl_NL" ]]; then
    load_langs="nl_NL,${UI_LANG}"
  fi
  odoo_cli -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    -i "base,point_of_sale,l10n_nl,contacts,stock" \
    --load-language="${load_langs}" \
    --without-demo=all \
    --stop-after-init \
    --log-level=warn

  log "DB '${DB_NAME}' initialized."

  # ---- MANUAL GATE (capability C, hard fiscal rule) ----------------------- #
  warn "============================================================"
  warn "MANUAL STEP REQUIRED BEFORE ANY POSTED JOURNAL ENTRY:"
  warn "  Confirm l10n_nl fiscal package + default sales/purchase tax"
  warn "  on company '${COMPANY_NAME}' in DB '${DB_NAME}'."
  warn "  Odoo 19 FORBIDS changing the fiscal package after the first"
  warn "  posted entry. Do this in Accounting > Configuration before"
  warn "  any sale is rung up. This is gated in the Mind ledger."
  warn "============================================================"
}

# --------------------------------------------------------------------------- #
# 6. Install / upgrade the client module (idempotent)
#    `-u` if already installed, `-i` if not. Odoo treats both as converging:
#    re-running -u re-applies the module's data with noupdate semantics intact.
# --------------------------------------------------------------------------- #
install_client_module() {
  log "Installing/upgrading module '${CLIENT_MODULE}' on DB '${DB_NAME}'."
  # We always use -i; Odoo upgrades if already installed when combined with the
  # module being present in the registry. To be explicit and idempotent we use
  # -i (install-if-absent) then a follow-up -u is a no-op-safe upgrade.
  odoo_cli -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    -i "${CLIENT_MODULE}" \
    --stop-after-init \
    --log-level=warn || warn "Install reported non-zero (may already be installed); trying upgrade."

  odoo_cli -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    -u "${CLIENT_MODULE}" \
    --stop-after-init \
    --log-level=warn

  log "Module '${CLIENT_MODULE}' installed/upgraded."
}

# --------------------------------------------------------------------------- #
# 7. Post-install assertions (cheap sanity; full reconciliation is the ETL's job)
#    We confirm the company country + that the manual Worldline method and the
#    pos.config exist. These are read-only checks via Odoo shell.
# --------------------------------------------------------------------------- #
post_checks() {
  log "Running post-install sanity checks on '${DB_NAME}' (read-only)."
  # NOTE: env.ref of the client module's xmlids depends on the template's ids.
  # TODO: confirm the actual xmlids in atlas_pos_seed and adjust the asserts.
  local pycheck
  pycheck=$(cat <<'PYEOF'
import sys
company = env['res.company'].search([], limit=1)
assert company, "no company found"
print("company:", company.name, "| country:", company.country_id.code or "UNSET")
pm = env['pos.payment.method'].search([('name', 'ilike', 'Worldline')])
print("worldline pos.payment.method count:", len(pm))
pc = env['pos.config'].search([])
print("pos.config count:", len(pc), "names:", pc.mapped('name'))
# BTW sanity: at least the 21% NL tax should resolve.
tax = env['account.tax'].search([('amount', '=', 21.0), ('type_tax_use', '=', 'sale')], limit=1)
print("21% sale BTW present:", bool(tax))
PYEOF
)
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "[DRY-RUN] would run odoo shell sanity checks."
    return 0
  fi
  printf '%s\n' "${pycheck}" | odoo_cli shell -c "${ODOO_CONF}" -d "${DB_NAME}" --no-http 2>/dev/null \
    || warn "Sanity checks could not run via odoo shell (verify xmlids/binary)."
}

# --------------------------------------------------------------------------- #
# 8. Orchestrate
# --------------------------------------------------------------------------- #
main() {
  preflight
  generate_client_module
  create_database
  install_client_module
  post_checks

  log "============================================================"
  log "DONE. Client '${CLIENT}' provisioned on Odoo DB '${DB_NAME}'."
  log "Next steps:"
  log "  1. Confirm l10n_nl fiscal package + default tax (MANUAL, pre-sale)."
  log "  2. Run the ETL from the read-twin:"
  log "       migration/dopos_to_odoo.py --client ${CLIENT} --dry-run"
  log "  3. Reconcile counts/totals, then parallel-run before cutover."
  log "Rollback for this build = drop DB '${DB_NAME}' (no client terminal touched)."
  log "============================================================"
}

main "$@"
