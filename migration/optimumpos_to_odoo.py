#!/usr/bin/env python3
# =============================================================================
# optimumpos_to_odoo.py
# Atlas POS Program — capability C (REPLACE), ETL side.
#
# Idempotent, re-runnable ETL: read a client's OptimumPOS data from the
# MIRRORED READ-TWIN on pos-hub (capability B), transform, and load into the
# target per-client Odoo 19 Community DB via XML-RPC.
#
# WHAT IT MIGRATES (in order):
#   1. product categories  -> pos.category (+ optionally product.category)
#   2. taxes (BTW rates)   -> mapped to the company's existing account.tax
#   3. products / articles -> product.template
#   4. payment methods     -> pos.payment.method (Worldline collapses to ONE
#                             MANUAL card method; cash -> cash method)
#   5. (optional) sales history -> read-only reporting dataset, NOT pos.order
#                             (default OFF; see --with-history)
#   6. validation          -> count + total reconciliation report
#
# HARD SAFETY RULES (per MEMORY.md):
#   * SOURCE IS THE READ-TWIN, NEVER THE LIVE TERMINAL. This ETL connects to a
#     MariaDB/MySQL twin on the hub that capability B keeps synced. An ETL bug
#     can therefore never lock tables or slow a live card-payment terminal, and
#     the ETL needs no quiet window because it doesn't touch the client.
#   * IDEMPOTENT UPSERT keyed on a stable source PK carried into Odoo as
#     default_code = "OPT-<sourcePK>". Re-running converges; never duplicates.
#     Human-edited prices are NOT clobbered on re-run (only safe fields are
#     re-asserted: name, category membership, availability).
#   * HISTORICAL SALES are NOT replayed into pos.order/account.move by default
#     (that would fabricate journal entries in the live Dutch CoA — a fiscal
#     hazard). The twin is the system-of-record for history.
#   * Worldline = MANUAL card method (Community has no integrated terminal).
#   * Dutch BTW: source rates are matched to the company's l10n_nl taxes BY
#     RATE via search — NEVER a hardcoded xmlid (they're per-company).
#
# DRY-RUN: --dry-run plans and validates against a THROWAWAY/STAGING reasoning
#   path: it reads the twin and computes every upsert, but performs NO writes to
#   Odoo and prints the reconciliation report. Always dry-run first.
#
# CONFIG (env, never committed — per-tenant env file, chmod 600):
#   TWIN_MYSQL_HOST / TWIN_MYSQL_PORT / TWIN_MYSQL_USER / TWIN_MYSQL_PW / TWIN_MYSQL_DB
#   ODOO_URL / ODOO_DB / ODOO_USER / ODOO_PW
#   Or pass --client <slug> to load migration/clients/<slug>.env
#
# USAGE:
#   python optimumpos_to_odoo.py --client venue_b --dry-run
#   python optimumpos_to_odoo.py --client venue_b            # real load
#   python optimumpos_to_odoo.py --client venuea --with-history --dry-run
#
# DEPENDENCIES: PyMySQL (or mysql-connector-python). xmlrpc.client is stdlib.
# =============================================================================

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import logging
import xmlrpc.client
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

# PyMySQL is the lightest pure-python driver; fall back gracefully if absent.
try:
    import pymysql  # type: ignore
    _HAVE_MYSQL = True
except ImportError:  # pragma: no cover
    _HAVE_MYSQL = False


LOG = logging.getLogger("optimumpos_etl")


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class TwinConfig:
    """Connection to the per-client OptimumPOS READ-TWIN on pos-hub."""
    host: str
    port: int
    user: str
    password: str
    db: str


@dataclass
class OdooConfig:
    """Connection to the target per-client Odoo 19 Community DB via XML-RPC."""
    url: str
    db: str
    user: str
    password: str


@dataclass
class RunConfig:
    client: str
    dry_run: bool = True
    with_history: bool = False
    tolerance_pct: Decimal = Decimal("0.5")   # acceptable price-sum drift %
    # Default OptimumPOS prices are assumed tax-INCLUSIVE until confirmed per
    # site. If True, we convert gross -> net = gross / (1 + rate). MUST verify.
    prices_tax_inclusive: bool = True
    # The company's DEFAULT sale BTW rate (NL standard 21%). A product whose
    # source rate equals this inherits the company default (taxes_id omitted);
    # any other rate is set explicitly via taxes_id.
    company_default_btw_rate: Decimal = Decimal("21")
    batch_size: int = 200
    # Local id-map state file (keyed by OPT-<pk>) for categories, so renames /
    # name-collisions in the source can't duplicate or merge pos.category rows.
    state_path: Optional[str] = None


# Stable-key prefix written into Odoo default_code for idempotent upsert.
OPT_KEY_PREFIX = "OPT"


def opt_key(source_pk: Any) -> str:
    """The stable idempotency key carried into Odoo (product default_code)."""
    return f"{OPT_KEY_PREFIX}-{source_pk}"


# Hostnames that are unambiguously the LOCAL hub twin (loopback / this box).
_LOCAL_TWIN_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def assert_twin_is_hub(host: str) -> None:
    """HARD precondition (per MEMORY.md safety rules): the ETL source MUST be the
    hub read-twin, never a live OptimumPOS terminal.

    A live terminal is reachable over the tailnet at a 100.x address (e.g. Le
    Venue A 192.0.2.10, Venue B 192.0.2.10). The twin lives on the hub and is
    addressed as localhost / 127.0.0.1 / ::1, or via the internal docker network
    (a private RFC1918 address or a docker service hostname).

    We REFUSE any host that resolves to a CGNAT 100.64.0.0/10 tailnet address, or
    any other public/non-private address — so a misconfigured env can never point
    the ETL at a live card-payment terminal.
    """
    h = (host or "").strip().lower()
    if not h:
        raise SystemExit("TWIN_MYSQL_HOST is empty — refusing (must be the hub twin).")

    if h in _LOCAL_TWIN_HOSTNAMES:
        return

    # Try to interpret the host as a literal IP. If it isn't an IP literal it's a
    # hostname (e.g. a docker-compose service name like `mysql`/`twin`) — those
    # resolve on the internal docker network and are allowed; a tailnet terminal
    # is always referenced by its 100.x literal, not a hostname here.
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        # Non-IP hostname: treat as internal docker service name. Reject anything
        # that smells like a fully-qualified public name out of caution.
        if "." in h and not h.endswith(".local") and not h.endswith(".internal"):
            raise SystemExit(
                f"TWIN_MYSQL_HOST={host!r} looks like a public FQDN — refusing. "
                "The source must be the hub twin (localhost / internal docker net)."
            )
        return

    if ip.is_loopback:
        return

    # The tailnet CGNAT range carries the live terminals — the cardinal hazard.
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        raise SystemExit(
            f"TWIN_MYSQL_HOST={host!r} is a 100.x tailnet address — that is a LIVE "
            "OptimumPOS terminal, not the hub read-twin. Refusing to run the ETL "
            "against a live terminal (see MEMORY.md safety rules)."
        )

    # Private (RFC1918) addresses are the internal docker network → allowed.
    if ip.is_private:
        return

    raise SystemExit(
        f"TWIN_MYSQL_HOST={host!r} is not a recognised hub-twin address "
        "(expected localhost / 127.0.0.1 / internal docker net). Refusing."
    )


# =============================================================================
# OptimumPOS schema map  --  THE CRITICAL TODO SURFACE
# -----------------------------------------------------------------------------
# These names are PLACEHOLDERS. The real OptimumPOS MySQL schema is vendor-
# defined and was NOT captured in this session. Before trusting this ETL you
# MUST inspect the actual twin schema per site (Venue A 192.0.2.10, Venue B
# 192.0.2.10) and pin every table/column below.
#
# Inspect with, against the TWIN (never the live box):
#   SHOW TABLES;
#   SHOW CREATE TABLE <table>;
#   SELECT * FROM <table> LIMIT 5;
#
# Confirm specifically:
#   - product table + PK + name + price column(s) + category FK + tax FK/rate
#   - whether price is tax-INCLUSIVE or EXCLUSIVE  (sets prices_tax_inclusive)
#   - category table + PK + name
#   - tax table OR an inline rate column on products (rate as 21.0 / 0.21 / id)
#   - payment-method table + how card vs cash is distinguished
#   - the table engine per table (InnoDB vs MyISAM) — affects capability B, not
#     this ETL, but note MyISAM history tables for the twin's consistency.
# =============================================================================
SCHEMA: Dict[str, Dict[str, str]] = {
    # TODO(schema): confirm against real OptimumPOS dump.
    "product": {
        "table":      "tblArticle",          # TODO confirm
        "pk":         "ArticleID",            # TODO confirm
        "name":       "ArticleName",          # TODO confirm
        "price":      "SalePrice",            # TODO confirm (incl or excl tax?)
        "category_fk":"CategoryID",           # TODO confirm
        "tax_rate":   "VatRate",              # TODO confirm: rate value or FK
        "active":     "IsActive",             # TODO confirm (may not exist)
        "is_service": "IsService",            # TODO confirm (else all 'consu')
    },
    "category": {
        "table": "tblCategory",               # TODO confirm
        "pk":    "CategoryID",                # TODO confirm
        "name":  "CategoryName",              # TODO confirm
    },
    "payment_method": {
        "table":   "tblPaymentType",          # TODO confirm
        "pk":      "PaymentTypeID",           # TODO confirm
        "name":    "PaymentTypeName",         # TODO confirm
        "is_cash": "IsCash",                  # TODO confirm (else infer by name)
    },
    "sales": {                                 # only read with --with-history
        "table":      "tblSale",              # TODO confirm
        "pk":         "SaleID",               # TODO confirm
        "datetime":   "SaleDateTime",         # TODO confirm
        "total":      "TotalAmount",          # TODO confirm
        "line_table": "tblSaleLine",          # TODO confirm
        "line_fk":    "SaleID",               # TODO confirm
        "line_article_fk": "ArticleID",       # TODO confirm
        "line_qty":   "Quantity",             # TODO confirm
        "line_price": "LinePrice",            # TODO confirm
    },
}


# =============================================================================
# Twin (MySQL) access layer — READ ONLY
# =============================================================================
class Twin:
    def __init__(self, cfg: TwinConfig):
        if not _HAVE_MYSQL:
            raise RuntimeError(
                "PyMySQL not installed. `pip install pymysql`. "
                "The ETL reads the read-twin, never the live terminal."
            )
        self.cfg = cfg
        self._conn = None

    def connect(self):
        LOG.info("Connecting to read-twin %s:%s/%s (READ ONLY)",
                 self.cfg.host, self.cfg.port, self.cfg.db)
        self._conn = pymysql.connect(
            host=self.cfg.host, port=self.cfg.port,
            user=self.cfg.user, password=self.cfg.password,
            database=self.cfg.db, charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            # Read-only intent: we never issue DML. The twin user should itself
            # be GRANT SELECT only, but we add a session guard for defence.
            init_command="SET SESSION TRANSACTION READ ONLY",
            read_timeout=30, connect_timeout=15,
        )
        return self

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        assert self._conn is not None, "call connect() first"
        with self._conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ---- typed readers (use the SCHEMA map; all read-only) ----------------- #
    def read_categories(self) -> List[Dict[str, Any]]:
        s = SCHEMA["category"]
        return self.query(
            f"SELECT `{s['pk']}` AS pk, `{s['name']}` AS name FROM `{s['table']}`"
        )

    def read_products(self) -> List[Dict[str, Any]]:
        s = SCHEMA["product"]
        # NOTE: active/is_service columns may not exist on every site; the
        # column list here MUST be reconciled with the confirmed schema.
        cols = (
            f"`{s['pk']}` AS pk, `{s['name']}` AS name, `{s['price']}` AS price, "
            f"`{s['category_fk']}` AS category_fk, `{s['tax_rate']}` AS tax_rate"
        )
        # TODO(schema): add active / is_service to SELECT once confirmed they exist.
        return self.query(f"SELECT {cols} FROM `{s['table']}`")

    def read_payment_methods(self) -> List[Dict[str, Any]]:
        s = SCHEMA["payment_method"]
        return self.query(
            f"SELECT `{s['pk']}` AS pk, `{s['name']}` AS name FROM `{s['table']}`"
        )

    def read_sales_summary(self) -> Dict[str, Any]:
        """Aggregate totals for reconciliation; cheap, read-only."""
        s = SCHEMA["sales"]
        try:
            rows = self.query(
                f"SELECT COUNT(*) AS cnt, COALESCE(SUM(`{s['total']}`),0) AS total "
                f"FROM `{s['table']}`"
            )
            return rows[0] if rows else {"cnt": 0, "total": 0}
        except Exception as exc:  # sales table may be absent / named differently
            LOG.warning("Could not read sales summary (schema TODO): %s", exc)
            return {"cnt": 0, "total": 0}


# =============================================================================
# Odoo (XML-RPC) access layer
# =============================================================================
class Odoo:
    """Thin XML-RPC wrapper with upsert-by-default_code helpers."""

    def __init__(self, cfg: OdooConfig, dry_run: bool):
        self.cfg = cfg
        self.dry_run = dry_run
        self.uid: Optional[int] = None
        self._common = None
        self._models = None
        # Cache: company id + resolved tax ids by rate, to avoid re-searching.
        self.company_id: Optional[int] = None
        self._tax_by_rate: Dict[str, int] = {}

    def connect(self):
        LOG.info("Connecting to Odoo %s db=%s as %s", self.cfg.url, self.cfg.db, self.cfg.user)
        self._common = xmlrpc.client.ServerProxy(f"{self.cfg.url}/xmlrpc/2/common")
        self.uid = self._common.authenticate(self.cfg.db, self.cfg.user, self.cfg.password, {})
        if not self.uid:
            raise RuntimeError("Odoo authentication failed — check ODOO_USER/ODOO_PW/ODOO_DB.")
        self._models = xmlrpc.client.ServerProxy(f"{self.cfg.url}/xmlrpc/2/object")
        self.company_id = self._resolve_company()
        LOG.info("Authenticated uid=%s company_id=%s", self.uid, self.company_id)
        return self

    # ---- low-level execute_kw ---------------------------------------------- #
    def execute(self, model: str, method: str, args: list, kwargs: Optional[dict] = None):
        return self._models.execute_kw(
            self.cfg.db, self.uid, self.cfg.password, model, method, args, kwargs or {}
        )

    def search(self, model: str, domain: list, **kw) -> List[int]:
        return self.execute(model, "search", [domain], kw)

    def search_read(self, model: str, domain: list, fields: List[str], **kw) -> List[dict]:
        return self.execute(model, "search_read", [domain], {"fields": fields, **kw})

    def create(self, model: str, vals: dict) -> Optional[int]:
        if self.dry_run:
            LOG.info("[DRY-RUN] create %s %s", model, _trunc(vals))
            return None
        return self.execute(model, "create", [vals])

    def write(self, model: str, ids: List[int], vals: dict) -> bool:
        if self.dry_run:
            LOG.info("[DRY-RUN] write %s %s %s", model, ids, _trunc(vals))
            return True
        return self.execute(model, "write", [ids, vals])

    # ---- helpers ----------------------------------------------------------- #
    def _resolve_company(self) -> int:
        ids = self.search("res.company", [], limit=1)
        if not ids:
            raise RuntimeError("No res.company in target DB — provision the DB first.")
        return ids[0]

    def assert_nl_btw_taxes(self) -> None:
        """HARD precondition (per MAPPING.md): the target company MUST have
        resolvable NL BTW sale taxes for the standard product rates 21 / 9 / 0.
        If any is missing we REFUSE (raise) rather than warn-and-continue, so the
        ETL can't silently load products onto a company with no usable taxes.
        Rate 0 may legitimately mean 'no tax' so we accept either a 0% account.tax
        OR confirmation that the chart simply has no 0-rate line.
        """
        required = [Decimal("21"), Decimal("9")]
        missing = [str(r) for r in required if self.tax_for_rate(r) is None]
        if missing:
            raise SystemExit(
                "Tax precondition FAILED: company {} has no resolvable NL BTW sale "
                "tax for rate(s) {}%. Refusing (see MAPPING.md). Provision l10n_nl "
                "taxes before running the ETL.".format(self.company_id, ", ".join(missing))
            )
        # 0% is optional but log its resolution status for the report trail.
        if self.tax_for_rate(Decimal("0")) is None:
            LOG.info("No explicit 0%% sale tax found; 0-rate products will carry no tax line.")
        LOG.info("NL BTW tax precondition OK (21%% and 9%% resolved for company %s).",
                 self.company_id)

    def tax_for_rate(self, rate: Decimal) -> Optional[int]:
        """Map a source BTW rate to the company's existing account.tax BY RATE.
        NEVER use a hardcoded l10n_nl xmlid — taxes are per-company.
        """
        key = str(rate)
        if key in self._tax_by_rate:
            return self._tax_by_rate[key]
        ids = self.search("account.tax", [
            ("amount", "=", float(rate)),
            ("type_tax_use", "=", "sale"),
            ("company_id", "=", self.company_id),
        ], limit=1)
        tax_id = ids[0] if ids else None
        if tax_id is None:
            LOG.warning("No sale account.tax matching %s%% in company %s — "
                        "product will inherit company default tax.", rate, self.company_id)
        self._tax_by_rate[key] = tax_id  # cache misses too (as None)
        return tax_id

    def upsert_by_default_code(
        self, model: str, code: str, create_vals: dict, update_vals: dict
    ) -> Tuple[str, Optional[int]]:
        """Idempotent upsert keyed on default_code == code.
        On match: write ONLY update_vals (safe fields) — never clobber price.
        On miss : create with create_vals (which includes default_code=code).
        Returns (action, id) where action in {created, updated}.
        """
        existing = self.search(model, [("default_code", "=", code)], limit=1)
        if existing:
            self.write(model, existing, update_vals)
            return ("updated", existing[0])
        rec_id = self.create(model, create_vals)
        return ("created", rec_id)

    def upsert_by_name(self, model: str, name: str, create_vals: dict) -> Tuple[str, Optional[int]]:
        """Upsert keyed on name (for payment methods, which have no source PK)."""
        existing = self.search(model, [("name", "=", name)], limit=1)
        if existing:
            return ("exists", existing[0])
        return ("created", self.create(model, create_vals))

    def _has_field(self, model: str, field_name: str) -> bool:
        """Whether `model` exposes `field_name` (cached). Used to detect whether
        x_optimum_id has been provisioned on pos.category in the target DB."""
        cache = getattr(self, "_field_cache", None)
        if cache is None:
            cache = {}
            self._field_cache = cache
        ck = (model, field_name)
        if ck in cache:
            return cache[ck]
        try:
            fields = self.execute(model, "fields_get", [[field_name]], {"attributes": ["type"]})
            present = field_name in (fields or {})
        except Exception:
            present = False
        cache[ck] = present
        return present

    def upsert_by_source_key(
        self,
        model: str,
        source_key: str,
        create_vals: dict,
        update_vals: dict,
        state_map: Dict[str, int],
    ) -> Tuple[str, Optional[int]]:
        """Idempotent upsert keyed on a STABLE source key (OPT-<pk>), so source
        renames or name-collisions never duplicate or merge rows (MAPPING.md).

        Resolution order:
          1. local id-map state file (state_map[source_key] -> odoo id), then
             confirm the row still exists;
          2. the x_optimum_id field on the model, if provisioned;
          3. otherwise create.

        On create/update, x_optimum_id is set when the field exists, and the
        state_map is updated so the binding persists across runs even if the
        field is absent.
        """
        has_xid = self._has_field(model, "x_optimum_id")

        # 1. Try the durable local id-map first.
        existing_id = state_map.get(source_key)
        if existing_id is not None:
            still = self.search(model, [("id", "=", existing_id)], limit=1)
            if still:
                self.write(model, [existing_id], update_vals)
                return ("updated", existing_id)
            # Stale binding (row deleted in Odoo) — fall through to rediscover.
            state_map.pop(source_key, None)

        # 2. Try the x_optimum_id field if the DB has it.
        if has_xid:
            found = self.search(model, [("x_optimum_id", "=", source_key)], limit=1)
            if found:
                self.write(model, found, update_vals)
                state_map[source_key] = found[0]
                return ("updated", found[0])

        # 3. Create. Stamp x_optimum_id when available.
        cvals = dict(create_vals)
        if has_xid:
            cvals["x_optimum_id"] = source_key
        rec_id = self.create(model, cvals)
        if rec_id is not None:
            state_map[source_key] = rec_id
        return ("created", rec_id)


# =============================================================================
# Transform + Load stages
# =============================================================================
@dataclass
class Report:
    """Reconciliation report accumulated across stages; printed at the end."""
    categories_created: int = 0
    categories_existing: int = 0
    products_created: int = 0
    products_updated: int = 0
    products_skipped: int = 0
    payment_methods_created: int = 0
    payment_methods_existing: int = 0
    unmapped_categories: List[Any] = field(default_factory=list)
    unmapped_taxes: List[Any] = field(default_factory=list)
    source_product_count: int = 0
    loaded_product_count: int = 0
    source_price_sum: Decimal = Decimal("0")
    loaded_price_sum: Decimal = Decimal("0")
    source_sales_count: int = 0
    source_sales_total: Decimal = Decimal("0")
    errors: List[str] = field(default_factory=list)

    def ok(self, tolerance_pct: Decimal) -> bool:
        if self.errors:
            return False
        if self.unmapped_taxes:
            return False
        # Product count must match: active source articles actually loaded
        # (source minus those skipped on error) vs. read-back of OPT-* in Odoo.
        if (self.source_product_count - self.products_skipped) != self.loaded_product_count:
            return False
        # Money check: loaded GROSS sum (read back from Odoo, re-grossed by tax)
        # within tolerance of the independently re-grossed SOURCE gross. These
        # are two separate measurements, so a tax incl/excl error can FAIL here.
        if self.source_price_sum > 0:
            drift = abs(self.loaded_price_sum - self.source_price_sum) / self.source_price_sum * 100
            if drift > tolerance_pct:
                return False
        return True


def _to_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _normalize_rate(raw: Any) -> Decimal:
    """OptimumPOS may store a BTW rate as 21, 21.0, 0.21, or a tax-table id.
    We normalize the common numeric forms to a percentage (21.0). A value <=1
    is treated as a fraction (0.21 -> 21). A value that looks like an id (e.g.
    a small integer that is NOT a known NL rate) is a TODO to resolve via the
    source tax table.
    """
    d = _to_decimal(raw)
    if d == 0:
        return Decimal("0")
    if d <= 1:
        return (d * 100).quantize(Decimal("0.01"))
    return d.quantize(Decimal("0.01"))


def stage_categories(
    twin: Twin, odoo: Odoo, rep: Report, state: Dict[str, Dict[str, int]]
) -> Dict[Any, int]:
    """Load source categories -> pos.category, keyed on the STABLE source key
    OPT-<pk> (per MAPPING.md) — NOT by name. Source renames or name-collisions
    therefore never duplicate or merge categories. Returns source_pk -> id."""
    LOG.info("== Stage 1: categories ==")
    mapping: Dict[Any, int] = {}
    cat_state = state.setdefault("pos.category", {})
    for row in twin.read_categories():
        pk = row["pk"]
        key = opt_key(pk)                       # OPT-<pk>, the stable source key
        name = str(row["name"]).strip()
        action, cid = odoo.upsert_by_source_key(
            "pos.category", key,
            create_vals={"name": name},
            update_vals={"name": name},         # name is safe to re-assert
            state_map=cat_state,
        )
        if action == "created":
            rep.categories_created += 1
        else:
            rep.categories_existing += 1
        if cid is not None:
            mapping[pk] = cid
    LOG.info("categories: %d created, %d existing", rep.categories_created, rep.categories_existing)
    return mapping


def stage_payment_methods(twin: Twin, odoo: Odoo, rep: Report) -> None:
    """Collapse every card/Worldline variant into ONE manual card method;
    map cash to a cash method. Community has no integrated terminal method.
    """
    LOG.info("== Stage 2: payment methods ==")
    saw_card = False
    saw_cash = False
    for row in twin.read_payment_methods():
        name = str(row["name"]).strip().lower()
        # Heuristic until is_cash is confirmed in SCHEMA.
        if any(k in name for k in ("cash", "contant", "kas")):
            saw_cash = True
        else:
            saw_card = True  # pin, card, worldline, maestro, etc. all collapse

    if saw_card:
        # NOTE: journal linkage + use_payment_terminal are set by the client
        # module's post_init_hook (journal-by-SEARCH). We only ensure the method
        # EXISTS here; we deliberately do NOT set use_payment_terminal -> manual.
        action, _ = odoo.upsert_by_name(
            "pos.payment.method", "Pinnen / Worldline kaart",
            {"name": "Pinnen / Worldline kaart"},
        )
        if action == "created":
            rep.payment_methods_created += 1
        else:
            rep.payment_methods_existing += 1
    if saw_cash:
        action, _ = odoo.upsert_by_name(
            "pos.payment.method", "Contant", {"name": "Contant"}
        )
        if action == "created":
            rep.payment_methods_created += 1
        else:
            rep.payment_methods_existing += 1
    LOG.info("payment methods: %d created, %d existing (card collapsed to 1 manual method)",
             rep.payment_methods_created, rep.payment_methods_existing)


def stage_products(
    twin: Twin, odoo: Odoo, rep: Report, cat_map: Dict[Any, int], run: RunConfig
) -> None:
    """Upsert products by OPT-<pk>. Re-asserts only safe fields on update."""
    LOG.info("== Stage 3: products ==")
    rows = twin.read_products()
    rep.source_product_count = len(rows)

    for row in rows:
        pk = row["pk"]
        code = opt_key(pk)
        name = str(row["name"]).strip()
        gross = _to_decimal(row["price"])
        rate = _normalize_rate(row.get("tax_rate"))

        # Resolve tax. If the rate isn't the company default, set taxes_id
        # explicitly to the matched tax; otherwise omit so it inherits.
        tax_id = odoo.tax_for_rate(rate) if rate > 0 else None
        if rate > 0 and tax_id is None:
            rep.unmapped_taxes.append({"product_pk": pk, "rate": str(rate)})

        rate_factor = Decimal("1") + rate / Decimal("100")

        # SOURCE side of the money check: the customer-facing GROSS the OptimumPOS
        # terminal charged, derived from the source figure under the declared
        # convention, via its OWN independent formula:
        #   * source tax-INCLUSIVE -> the figure already IS the gross;
        #   * source tax-EXCLUSIVE -> gross = figure * (1 + rate).
        # This is computed SEPARATELY from `net` below. The LOADED side
        # (validate()) reads `net` back from Odoo and re-grosses it by Odoo's
        # resolved tax. The two are therefore independent measurements: a bug in
        # the net derivation (e.g. converting in the WRONG tax direction) makes
        # the loaded re-gross diverge from this source gross -> drift the check
        # can FAIL on. When everything is correct, net * (1 + rate) reconstructs
        # this gross and they agree within tolerance.
        if rate > 0 and not run.prices_tax_inclusive:
            source_gross = (gross * rate_factor).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            source_gross = gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Price: Odoo list_price is tax-EXCLUSIVE. If source is inclusive,
        # convert net = gross / (1 + rate/100).  MUST confirm per site.
        if run.prices_tax_inclusive and rate > 0:
            net = (gross / rate_factor).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            net = gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        pos_categ_id = cat_map.get(row.get("category_fk"))
        if row.get("category_fk") is not None and pos_categ_id is None:
            rep.unmapped_categories.append(row.get("category_fk"))

        # type: 'consu' for goods, 'service' for labour. TODO: use is_service.
        prod_type = "consu"

        # Fields SAFE to re-assert on every run (never includes list_price):
        update_vals: Dict[str, Any] = {
            "name": name,
            "available_in_pos": True,
        }
        if pos_categ_id is not None:
            update_vals["pos_categ_ids"] = [(6, 0, [pos_categ_id])]  # M2M, plural

        # Fields used only at CREATE (price set once; humans may edit later):
        create_vals: Dict[str, Any] = dict(update_vals)
        create_vals.update({
            "default_code": code,                 # the idempotency key
            "type": prod_type,                    # NO detailed_type in v19
            "list_price": float(net),
            "company_id": odoo.company_id,
        })
        # taxes_id only when the product's BTW rate DIFFERS from the company
        # default (e.g. a 9%/0% item in a 21%-default company). When it matches
        # the default we OMIT taxes_id so the product inherits the company tax.
        if tax_id is not None and rate > 0 and rate != run.company_default_btw_rate:
            create_vals["taxes_id"] = [(6, 0, [tax_id])]

        try:
            action, _ = odoo.upsert_by_default_code(
                "product.template", code, create_vals, update_vals)
            if action == "created":
                rep.products_created += 1
            else:
                rep.products_updated += 1
            # SOURCE side: accumulate the independently re-grossed source total.
            # The LOADED side is NOT summed here from the same value — it is read
            # back from Odoo in validate() (sum of OPT-* list_price re-grossed by
            # their tax), so the two are independent measurements.
            rep.source_price_sum += source_gross
        except Exception as exc:
            rep.errors.append(f"product {code}: {exc}")
            rep.products_skipped += 1
            LOG.error("product %s failed: %s", code, exc)

    LOG.info("products: %d created, %d updated, %d skipped",
             rep.products_created, rep.products_updated, rep.products_skipped)


def stage_history(twin: Twin, odoo: Odoo, rep: Report, run: RunConfig) -> None:
    """OPTIONAL, default OFF. Loads sales as a READ-ONLY reporting dataset, NOT
    as pos.order/account.move. Replaying closed tickets as live Odoo orders
    would double-count revenue and corrupt the Dutch CoA / BTW reporting.

    Default implementation only AGGREGATES history for the reconciliation
    report. A real read-only import target (a custom x_optimum_sale model or a
    CSV->BI export) is a per-client decision — see TODO.
    """
    LOG.info("== Stage 4: history (read-only summary; NOT replayed into pos.order) ==")
    summ = twin.read_sales_summary()
    rep.source_sales_count = int(summ.get("cnt", 0) or 0)
    rep.source_sales_total = _to_decimal(summ.get("total", 0))
    LOG.info("history summary: %d sales totalling %s (archived in twin; not posted)",
             rep.source_sales_count, rep.source_sales_total)
    # TODO(per-client): if a client needs history visible in Odoo, load into a
    # dedicated x_optimum_sale read model here — NEVER into pos.order. Keep it
    # separate from accounting so no journal entries are fabricated.


# =============================================================================
# Validation / reconciliation
# =============================================================================
def _tax_amounts(odoo: Odoo, tax_ids: List[int]) -> Dict[int, Decimal]:
    """Resolve account.tax ids -> percentage amount (e.g. 21.0). Cached lookups."""
    if not tax_ids:
        return {}
    rows = odoo.search_read("account.tax", [("id", "in", tax_ids)], ["amount"])
    return {r["id"]: _to_decimal(r.get("amount")) for r in rows}


def validate(odoo: Odoo, rep: Report, run: RunConfig) -> bool:
    """Assert reconciliation invariants. A failure BLOCKS cutover.

    Defines the LOADED side of both checks as independent READ-BACKS from Odoo:
      * loaded_product_count = number of ACTIVE OPT-* product.template rows;
      * loaded_price_sum     = sum of those rows' list_price, each RE-GROSSED by
        its own tax (taxes_id when set, else the company default BTW rate).
    Because the source side is re-grossed independently from the source figures,
    a tax inclusive/exclusive error produces real drift the check can FAIL on.
    """
    LOG.info("== Validation ==")

    # On dry-run there is nothing in Odoo to read back; mirror the source so the
    # planned reconciliation can still be shown (count == source, sum == source).
    if odoo.dry_run:
        rep.loaded_product_count = rep.source_product_count - rep.products_skipped
        rep.loaded_price_sum = rep.source_price_sum
        return rep.ok(run.tolerance_pct)

    # LOADED read-back: active OPT-* products with their list_price + taxes.
    loaded_rows = odoo.search_read(
        "product.template",
        [("default_code", "like", f"{OPT_KEY_PREFIX}-%"), ("active", "=", True)],
        ["list_price", "taxes_id"],
    )
    rep.loaded_product_count = len(loaded_rows)

    # Resolve every referenced tax id to its percentage once.
    all_tax_ids = sorted({tid for r in loaded_rows for tid in (r.get("taxes_id") or [])})
    amounts = _tax_amounts(odoo, all_tax_ids)
    default_rate = run.company_default_btw_rate

    loaded_sum = Decimal("0")
    for r in loaded_rows:
        net = _to_decimal(r.get("list_price"))
        tids = r.get("taxes_id") or []
        # A product may carry an explicit tax; otherwise it inherits the company
        # default BTW rate (we omit taxes_id for default-rate products on create).
        rate = sum((amounts.get(t, Decimal("0")) for t in tids), Decimal("0")) if tids else default_rate
        loaded_sum += (net * (Decimal("1") + rate / Decimal("100"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
    rep.loaded_price_sum = loaded_sum

    # Product-count invariant: active source articles loaded vs. read back.
    expected = rep.source_product_count - rep.products_skipped
    if rep.loaded_product_count != expected:
        rep.errors.append(
            f"product count mismatch: expected {expected} OPT-* "
            f"(source {rep.source_product_count} - skipped {rep.products_skipped}), "
            f"Odoo has {rep.loaded_product_count}")

    return rep.ok(run.tolerance_pct)


def print_report(rep: Report, run: RunConfig, passed: bool) -> None:
    line = "=" * 60
    print(line)
    print(f"  Atlas POS ETL — reconciliation report  [client={run.client}]")
    print(f"  mode: {'DRY-RUN (no writes)' if run.dry_run else 'LOAD'}   "
          f"history: {'on' if run.with_history else 'off (twin-archive only)'}")
    print(line)
    print(f"  categories      : {rep.categories_created} created, {rep.categories_existing} existing")
    print(f"  payment methods : {rep.payment_methods_created} created, {rep.payment_methods_existing} existing")
    print(f"  products        : {rep.products_created} created, {rep.products_updated} updated, "
          f"{rep.products_skipped} skipped")
    print(f"  source products : {rep.source_product_count}")
    print(f"  loaded products : {rep.loaded_product_count}")
    print(f"  price sum (gross): source={rep.source_price_sum} (re-grossed from source)  "
          f"loaded={rep.loaded_price_sum} (read back from Odoo, re-grossed by tax)")
    if run.with_history:
        print(f"  sales history   : {rep.source_sales_count} sales, total {rep.source_sales_total} "
              f"(archived in twin; NOT posted to Odoo)")
    if rep.unmapped_categories:
        print(f"  UNMAPPED categories ({len(rep.unmapped_categories)}): "
              f"{sorted(set(map(str, rep.unmapped_categories)))[:20]}")
    if rep.unmapped_taxes:
        print(f"  UNMAPPED taxes ({len(rep.unmapped_taxes)}): {rep.unmapped_taxes[:20]}")
    if rep.errors:
        print(f"  ERRORS ({len(rep.errors)}):")
        for e in rep.errors[:20]:
            print(f"    - {e}")
    print(line)
    print(f"  RESULT: {'PASS — eligible for parallel-run' if passed else 'FAIL — cutover BLOCKED'}")
    print(line)


# =============================================================================
# Config loading
# =============================================================================
def _trunc(vals: dict, n: int = 120) -> str:
    s = str(vals)
    return s if len(s) <= n else s[: n - 3] + "..."


def load_state(path: Optional[str]) -> Dict[str, Dict[str, int]]:
    """Load the local id-map state file (OPT-<pk> -> odoo id, per model).
    Shape: {"pos.category": {"OPT-7": 12, ...}}. Missing/corrupt -> empty."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k): {str(kk): int(vv) for kk, vv in (v or {}).items()}
                    for k, v in data.items() if isinstance(v, dict)}
    except Exception as exc:
        LOG.warning("Could not read id-map state %s (%s) — starting fresh.", path, exc)
    return {}


def save_state(path: Optional[str], state: Dict[str, Dict[str, int]], dry_run: bool) -> None:
    """Persist the id-map state file. Skipped on dry-run (no writes happened)."""
    if not path or dry_run:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
        LOG.info("Wrote id-map state to %s", path)
    except Exception as exc:
        LOG.warning("Could not write id-map state %s (%s).", path, exc)


def load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a per-tenant env file into os.environ.
    Secrets live here (chmod 600), never in git.
    """
    if not os.path.isfile(path):
        return
    LOG.info("Loading env from %s", path)
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def build_configs(args: argparse.Namespace) -> Tuple[TwinConfig, OdooConfig, RunConfig]:
    # Per-client env file convention; CLI/explicit env override it.
    if args.client:
        here = os.path.dirname(os.path.abspath(__file__))
        load_env_file(os.path.join(here, "clients", f"{args.client}.env"))

    def req(name: str) -> str:
        v = os.environ.get(name)
        if not v and not args.dry_run:
            raise SystemExit(f"Missing required env var: {name}")
        return v or ""

    twin_host = os.environ.get("TWIN_MYSQL_HOST", "127.0.0.1")
    # HARD precondition: refuse to run unless the source is the hub twin (not a
    # 100.x tailnet terminal). Enforced even on --dry-run, before any connect.
    assert_twin_is_hub(twin_host)

    twin = TwinConfig(
        host=twin_host,
        port=int(os.environ.get("TWIN_MYSQL_PORT", "3306")),
        user=os.environ.get("TWIN_MYSQL_USER", "readonly"),
        password=req("TWIN_MYSQL_PW"),
        db=os.environ.get("TWIN_MYSQL_DB", args.client or ""),
    )
    odoo = OdooConfig(
        url=os.environ.get("ODOO_URL", "http://localhost:8069"),
        db=os.environ.get("ODOO_DB", args.client or ""),
        user=os.environ.get("ODOO_USER", "admin"),
        password=req("ODOO_PW"),
    )
    here = os.path.dirname(os.path.abspath(__file__))
    client_slug = args.client or odoo.db or "default"
    state_path = os.environ.get("ETL_STATE_PATH") or os.path.join(
        here, "state", f"{client_slug}-idmap.json")

    run = RunConfig(
        client=args.client or odoo.db,
        dry_run=args.dry_run,
        with_history=args.with_history,
        tolerance_pct=Decimal(str(args.tolerance)),
        prices_tax_inclusive=not args.prices_tax_exclusive,
        company_default_btw_rate=Decimal(str(args.default_btw_rate)),
        state_path=state_path,
    )
    return twin, odoo, run


# =============================================================================
# Entry point
# =============================================================================
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Idempotent OptimumPOS(read-twin) -> Odoo 19 Community ETL.")
    p.add_argument("--client", help="client slug; loads clients/<slug>.env and "
                                     "defaults TWIN_MYSQL_DB / ODOO_DB to it.")
    p.add_argument("--dry-run", action="store_true",
                   help="read + plan + validate, NO writes to Odoo (always do this first).")
    p.add_argument("--with-history", action="store_true",
                   help="also summarize sales history (read-only; never posted to pos.order).")
    p.add_argument("--tolerance", default="0.5",
                   help="acceptable price-sum drift percent for reconciliation (default 0.5).")
    p.add_argument("--prices-tax-exclusive", action="store_true",
                   help="source prices are tax-EXCLUSIVE (default: assumed INCLUSIVE — "
                        "CONFIRM per site before trusting prices).")
    p.add_argument("--default-btw-rate", default="21",
                   help="company default sale BTW rate; products at this rate inherit "
                        "the company tax (NL standard 21%%).")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    twin_cfg, odoo_cfg, run = build_configs(args)

    LOG.info("Client=%s dry_run=%s with_history=%s prices_tax_inclusive=%s",
             run.client, run.dry_run, run.with_history, run.prices_tax_inclusive)
    if run.prices_tax_inclusive:
        LOG.warning("Assuming source prices are TAX-INCLUSIVE. CONFIRM against the "
                    "real OptimumPOS schema/dump before trusting migrated prices.")

    rep = Report()
    twin = Twin(twin_cfg)
    odoo = Odoo(odoo_cfg, dry_run=run.dry_run)

    state = load_state(run.state_path)

    try:
        twin.connect()
        odoo.connect()

        # HARD precondition (MAPPING.md): refuse unless NL BTW taxes resolve.
        odoo.assert_nl_btw_taxes()

        cat_map = stage_categories(twin, odoo, rep, state)
        stage_payment_methods(twin, odoo, rep)
        stage_products(twin, odoo, rep, cat_map, run)
        if run.with_history:
            stage_history(twin, odoo, rep, run)

        passed = validate(odoo, rep, run)
        save_state(run.state_path, state, run.dry_run)
        print_report(rep, run, passed)
        # Non-zero exit on validation failure so callers / the Mind gate can
        # block cutover automatically.
        return 0 if passed else 2

    except Exception as exc:  # surface a clean failure to the orchestrator
        LOG.exception("ETL failed: %s", exc)
        rep.errors.append(str(exc))
        print_report(rep, run, passed=False)
        return 1
    finally:
        twin.close()


if __name__ == "__main__":
    raise SystemExit(main())
