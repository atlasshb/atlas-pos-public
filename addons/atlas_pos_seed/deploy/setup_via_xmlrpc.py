#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_via_xmlrpc.py  --  Deploy Option C  (Venue B POS, Odoo 19 Community)

Drives the live Odoo over the External API (XML-RPC). No filesystem access
to the server is required -- only HTTP to port 8069.

WHAT IT DOES (in order):
  1. Authenticate using environment variables.
  2. Activate Turkish UI language (tr_TR) -- idempotent.
  3. If the module 'atlas_pos_seed' EXISTS in the DB:
        -> install it (if not installed) or upgrade it (if installed), then STOP.
        The module is the source of truth; we let it do the work.
  4. ELSE (fallback, module not uploaded to the server):
        -> create POS categories, products, the two payment methods
           (resolving cash/bank journals by SEARCH), and attach them to a
           POS config -- all directly via ORM, IDEMPOTENTLY.

SAFETY / IDEMPOTENCY:
  - Additive only. Never deletes, never overwrites accounting/taxes/company.
  - Products inherit the company default sale tax (no hardcoded tax xmlids).
  - Re-running produces the same state (records are matched by a stable
    marker stored in a name-suffix / default_code, not duplicated).
  - Does NOT touch is_cash_count / type / use_payment_terminal (computed or
    terminal-integration fields). Cash-vs-bank is driven ONLY by the linked
    journal type, exactly per the Odoo 19 Community semantics.

ENVIRONMENT VARIABLES (required):
    ODOO_URL        e.g. http://192.0.2.10:8069
    ODOO_DB         e.g. venue_b
    ODOO_USER       an admin login, e.g. admin
    ODOO_PASSWORD   that user's password or API key

USAGE:
    # PowerShell
    $env:ODOO_URL="http://192.0.2.10:8069"
    $env:ODOO_DB="venue_b"
    $env:ODOO_USER="admin"
    $env:ODOO_PASSWORD="********"
    python setup_via_xmlrpc.py

    # Optional flags:
    python setup_via_xmlrpc.py --force-fallback   # skip module path, always ORM-seed
    python setup_via_xmlrpc.py --dry-run          # print actions, change nothing
"""

import os
import sys
import argparse
import xmlrpc.client

MODULE_NAME = "atlas_pos_seed"

# A stable marker we stamp onto records WE create in fallback mode, so re-runs
# find-and-skip instead of duplicating. (We avoid relying on ir.model.data
# xmlids over XML-RPC for created records.)
MARKER = "[VENUE B]"


# ---------------------------------------------------------------------------
#  Catalog definition (mirrors the module data; used only in fallback mode)
# ---------------------------------------------------------------------------

# POS categories: key -> display name
POS_CATEGORIES = [
    ("galajurken", "Galajurken (Abiye)"),
    ("kostuums", "Kostuums (Takım Elbise)"),
    ("kleding", "Kleding (Giyim)"),
    ("accessoires", "Accessoires (Aksesuar)"),
    ("vermaak", "Vermaak & Reparatie (Tadilat & Onarım)"),
]

# Products: (default_code, name, type, list_price, pos_category_key)
#   type: 'consu' for goods, 'service' for alterations/repairs.
#   taxes_id intentionally omitted -> inherits company default 21% BTW.
PRODUCTS = [
    ("KOL-GALA-STD", "Galajurk (Abiye) - Standaard", "consu", 199.00, "galajurken"),
    ("KOL-GALA-LUX", "Galajurk (Abiye) - Luxe", "consu", 349.00, "galajurken"),
    ("KOL-GALA-KIND", "Galajurk Kind (Çocuk Abiye)", "consu", 99.00, "galajurken"),
    ("KOL-KOST-2", "Kostuum 2-delig (Takım Elbise 2 parça)", "consu", 249.00, "kostuums"),
    ("KOL-KOST-3", "Kostuum 3-delig (Takım Elbise 3 parça)", "consu", 299.00, "kostuums"),
    ("KOL-COLBERT", "Colbert (Ceket)", "consu", 129.00, "kostuums"),
    ("KOL-PANTALON", "Pantalon (Pantolon)", "consu", 69.00, "kostuums"),
    ("KOL-OVERHEMD", "Overhemd (Gömlek)", "consu", 39.00, "kleding"),
    ("KOL-ROK", "Rok (Etek)", "consu", 49.00, "kleding"),
    ("KOL-STROPDAS", "Stropdas (Kravat)", "consu", 19.00, "accessoires"),
    ("KOL-SJAAL", "Sjaal (Şal)", "consu", 24.00, "accessoires"),
    ("KOL-RIEM", "Riem (Kemer)", "consu", 29.00, "accessoires"),
    ("KOL-VERMAAK", "Vermaak (Tadilat) - prijs per opdracht", "service", 0.00, "vermaak"),
    ("KOL-REPARATIE", "Reparatie (Onarım) - prijs per opdracht", "service", 0.00, "vermaak"),
    ("KOL-INKORTEN", "Inkorten broek/jurk (Boy kısaltma)", "service", 15.00, "vermaak"),
    ("KOL-RITS", "Rits vervangen (Fermuar değiştirme)", "service", 20.00, "vermaak"),
]

PM_CASH_NAME = "Contant"
PM_CARD_NAME = "Pinnen / Worldline kaart"


# ---------------------------------------------------------------------------
#  Thin XML-RPC ORM wrapper
# ---------------------------------------------------------------------------

class Odoo:
    def __init__(self, url, db, user, password, dry_run=False):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.password = password
        self.dry_run = dry_run
        self.uid = None
        self.models = None

    def connect(self):
        common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common", allow_none=True
        )
        try:
            ver = common.version()
        except Exception as e:
            raise SystemExit(f"ERROR: cannot reach Odoo at {self.url}: {e}")
        print(f"  Connected. Odoo server version: {ver.get('server_version', '?')}")

        self.uid = common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise SystemExit(
                "ERROR: authentication failed. Check ODOO_DB / ODOO_USER / ODOO_PASSWORD."
            )
        print(f"  Authenticated as uid={self.uid}")
        self.models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object", allow_none=True
        )

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs or {}
        )

    def search(self, model, domain, limit=None):
        kw = {}
        if limit:
            kw["limit"] = limit
        return self.execute(model, "search", domain, **kw)

    def search_read(self, model, domain, fields, limit=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        return self.execute(model, "search_read", domain, **kw)

    def create(self, model, vals):
        if self.dry_run:
            print(f"    [dry-run] would CREATE {model}: {vals}")
            return -1
        return self.execute(model, "create", vals)

    def write(self, model, ids, vals):
        if self.dry_run:
            print(f"    [dry-run] would WRITE {model} {ids}: {vals}")
            return True
        return self.execute(model, "write", ids, vals)

    def has_field(self, model, field):
        try:
            fields = self.execute(model, "fields_get", [], attributes=["type"])
            return field in fields
        except Exception:
            return False


# ---------------------------------------------------------------------------
#  Step 1: Turkish language
# ---------------------------------------------------------------------------

def activate_turkish(odoo):
    print("\n[1/4] Activating Turkish UI (tr_TR) ...")
    lang_ids = odoo.search("res.lang", [("code", "=", "tr_TR")], limit=1)
    if lang_ids:
        # Already present (possibly inactive). Ensure active.
        rec = odoo.search_read("res.lang", [("code", "=", "tr_TR")], ["active"], limit=1)
        if rec and not rec[0]["active"]:
            odoo.write("res.lang", lang_ids, {"active": True})
            print("  tr_TR existed but was inactive -> activated.")
        else:
            print("  tr_TR already active. No-op.")
        return
    # Not present: install via the language wizard (Odoo 19 uses lang_ids m2m).
    # We need the (possibly inactive) lang record id; _activate_lang is the
    # server-side way, but it isn't exposed generically over XML-RPC for all
    # versions, so we use the wizard which is.
    if odoo.dry_run:
        print("  [dry-run] would install tr_TR via base.language.install wizard.")
        return
    try:
        # Find the lang record including inactive ones via context.
        all_lang = odoo.models.execute_kw(
            odoo.db, odoo.uid, odoo.password,
            "res.lang", "search_read",
            [[("code", "=", "tr_TR")]],
            {"fields": ["id"], "context": {"active_test": False}},
        )
        if not all_lang:
            print("  WARNING: tr_TR not found in res.lang at all; skipping language step.")
            return
        wiz = odoo.create(
            "base.language.install",
            {"lang_ids": [(6, 0, [all_lang[0]["id"]])], "overwrite": False},
        )
        odoo.execute("base.language.install", "lang_install", [wiz])
        print("  tr_TR installed/merged (overwrite=False).")
    except Exception as e:
        # Language is non-critical to POS function; warn and continue.
        print(f"  WARNING: could not install tr_TR via wizard ({e}). "
              f"Activate it manually in Settings -> Translations -> Languages.")


# ---------------------------------------------------------------------------
#  Step 2: module install / upgrade path
# ---------------------------------------------------------------------------

def try_module_path(odoo):
    """Return True if the module exists and we handled install/upgrade."""
    print(f"\n[2/4] Looking for module '{MODULE_NAME}' in the DB ...")
    recs = odoo.search_read(
        "ir.module.module",
        [("name", "=", MODULE_NAME)],
        ["state"],
        limit=1,
    )
    if not recs:
        print(f"  Module '{MODULE_NAME}' is NOT in the DB.")
        print("  (Tip: upload it to the addons path and 'Update Apps List' first,")
        print("   or just let this script seed the catalog directly -> fallback.)")
        return False

    state = recs[0]["state"]
    mod_id = recs[0]["id"]
    print(f"  Found module '{MODULE_NAME}', state = {state}.")

    if state in ("uninstalled", "to install"):
        print("  Installing module ...")
        if not odoo.dry_run:
            odoo.execute("ir.module.module", "button_immediate_install", [mod_id])
        print("  Install triggered. The module's data + post_init_hook do the rest.")
        return True

    if state in ("installed", "to upgrade"):
        print("  Upgrading module ...")
        if not odoo.dry_run:
            odoo.execute("ir.module.module", "button_immediate_upgrade", [mod_id])
        print("  Upgrade triggered.")
        return True

    print(f"  Module in unexpected state '{state}'. Not touching it; falling back.")
    return False


# ---------------------------------------------------------------------------
#  Step 3: ORM fallback (no module on server)
# ---------------------------------------------------------------------------

def get_company_id(odoo):
    rec = odoo.search_read("res.users", [("id", "=", odoo.uid)], ["company_id"], limit=1)
    cid = rec[0]["company_id"][0] if rec and rec[0]["company_id"] else None
    if not cid:
        cids = odoo.search("res.company", [], limit=1)
        cid = cids[0] if cids else None
    if not cid:
        raise SystemExit("ERROR: no company found.")
    return cid


def ensure_pos_categories(odoo):
    print("  Ensuring POS categories ...")
    key_to_id = {}
    for key, name in POS_CATEGORIES:
        existing = odoo.search("pos.category", [("name", "=", name)], limit=1)
        if existing:
            key_to_id[key] = existing[0]
            print(f"    = exists: {name}")
        else:
            new_id = odoo.create("pos.category", {"name": name})
            key_to_id[key] = new_id
            print(f"    + created: {name}")
    return key_to_id


def ensure_products(odoo, company_id, cat_key_to_id):
    print("  Ensuring products ...")
    has_default_code = odoo.has_field("product.template", "default_code")
    for code, name, ptype, price, cat_key in PRODUCTS:
        # Match idempotently by default_code (preferred) or by exact name.
        domain = [("default_code", "=", code)] if has_default_code else [("name", "=", name)]
        existing = odoo.search("product.template", domain, limit=1)
        cat_id = cat_key_to_id.get(cat_key)
        vals = {
            "name": name,
            "type": ptype,                       # 'consu' or 'service' (v19 valid)
            "list_price": price,
            "available_in_pos": True,
            "pos_categ_ids": [(6, 0, [cat_id])] if cat_id else False,
            "company_id": False,                 # shared / multi-company safe
            # taxes_id intentionally omitted -> company default 21% BTW.
        }
        if has_default_code:
            vals["default_code"] = code
        if existing:
            # Refresh the POS-relevant fields only; do not clobber price if a
            # human edited it -> we only re-assert availability + category.
            odoo.write("product.template", existing, {
                "available_in_pos": True,
                "pos_categ_ids": [(6, 0, [cat_id])] if cat_id else False,
            })
            print(f"    = exists: {name}")
        else:
            odoo.create("product.template", vals)
            print(f"    + created: {name}")


def ensure_payment_methods(odoo, company_id):
    print("  Ensuring POS payment methods ...")
    method_ids = []

    # ---- CASH (Contant) -> link a CASH journal ----
    cash_existing = odoo.search(
        "pos.payment.method",
        [("name", "=", PM_CASH_NAME), ("company_id", "=", company_id)],
        limit=1,
    )
    if cash_existing:
        method_ids += cash_existing
        print(f"    = exists: {PM_CASH_NAME}")
    else:
        cash_journal = odoo.search(
            "account.journal",
            [("company_id", "=", company_id), ("type", "=", "cash")],
            limit=1,
        )
        vals = {
            "name": PM_CASH_NAME,
            "company_id": company_id,
            "split_transactions": False,
            # Do NOT set type / is_cash_count (computed from journal).
        }
        if cash_journal:
            # Guard: journal must not already be linked to another cash method.
            clash = odoo.search(
                "pos.payment.method",
                [("journal_id", "=", cash_journal[0])],
                limit=1,
            )
            if not clash:
                vals["journal_id"] = cash_journal[0]
            else:
                print("      ! cash journal already linked to another method; "
                      "creating method WITHOUT journal (link it manually).")
        else:
            print("      ! no cash journal found yet; creating method WITHOUT journal "
                  "(install l10n_nl, then link a cash journal manually).")
        new_id = odoo.create("pos.payment.method", vals)
        if new_id != -1:
            method_ids.append(new_id)
        print(f"    + created: {PM_CASH_NAME}")

    # ---- MANUAL CARD (Pinnen / Worldline kaart) -> link a BANK journal ----
    card_existing = odoo.search(
        "pos.payment.method",
        [("name", "=", PM_CARD_NAME), ("company_id", "=", company_id)],
        limit=1,
    )
    if card_existing:
        method_ids += card_existing
        print(f"    = exists: {PM_CARD_NAME}")
    else:
        bank_journal = odoo.search(
            "account.journal",
            [("company_id", "=", company_id), ("type", "=", "bank")],
            limit=1,
        )
        vals = {
            "name": PM_CARD_NAME,
            "company_id": company_id,
            "split_transactions": False,
            # use_payment_terminal LEFT UNSET -> manual, non-integrated card.
            # Do NOT set type (computed from journal).
        }
        if bank_journal:
            vals["journal_id"] = bank_journal[0]
        else:
            print("      ! no bank journal found yet; creating method WITHOUT journal "
                  "(install l10n_nl, then link a bank journal manually).")
        new_id = odoo.create("pos.payment.method", vals)
        if new_id != -1:
            method_ids.append(new_id)
        print(f"    + created: {PM_CARD_NAME}")

    return [m for m in method_ids if m != -1]


def attach_methods_to_config(odoo, company_id, method_ids):
    print("  Attaching payment methods to a POS config ...")
    if not method_ids:
        print("    (no method ids to attach; skipping)")
        return
    configs = odoo.search(
        "pos.config", [("company_id", "in", [company_id, False])], limit=1
    )
    if not configs:
        print("    ! no pos.config found. Create a shop in Point of Sale -> "
              "Configuration -> Point of Sale, then re-run or attach methods manually.")
        return
    cfg_id = configs[0]
    # Command.link each method (additive). (4, id) = link without unlinking others.
    cmds = [(4, mid) for mid in method_ids]
    odoo.write("pos.config", [cfg_id], {"payment_method_ids": cmds})
    print(f"    = methods linked to pos.config id={cfg_id} (additive).")


def fallback_seed(odoo):
    print("\n[3/4] FALLBACK: seeding catalog + payment methods directly via ORM ...")
    company_id = get_company_id(odoo)
    print(f"  Using company_id = {company_id}")
    cat_map = ensure_pos_categories(odoo)
    ensure_products(odoo, company_id, cat_map)
    method_ids = ensure_payment_methods(odoo, company_id)
    attach_methods_to_config(odoo, company_id, method_ids)
    print("  Fallback seeding done.")


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Venue B POS XML-RPC deploy (Option C)")
    parser.add_argument("--force-fallback", action="store_true",
                        help="Skip the module install/upgrade path; always ORM-seed.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print intended actions; change nothing.")
    args = parser.parse_args()

    url = os.environ.get("ODOO_URL", "http://192.0.2.10:8069")
    db = os.environ.get("ODOO_DB", "venue_b")
    user = os.environ.get("ODOO_USER")
    password = os.environ.get("ODOO_PASSWORD")

    missing = [k for k, v in [("ODOO_USER", user), ("ODOO_PASSWORD", password)] if not v]
    if missing:
        raise SystemExit(
            "ERROR: missing environment variable(s): " + ", ".join(missing) +
            "\nSet ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD before running."
        )

    print("==================================================================")
    print(" Venue B POS  --  XML-RPC deploy (Option C)")
    print("==================================================================")
    print(f"  URL : {url}")
    print(f"  DB  : {db}")
    print(f"  USER: {user}")
    if args.dry_run:
        print("  MODE: DRY-RUN (no changes will be written)")
    print("------------------------------------------------------------------")

    odoo = Odoo(url, db, user, password, dry_run=args.dry_run)
    odoo.connect()

    # Step 1: language (safe & idempotent regardless of path).
    activate_turkish(odoo)

    # Step 2/3: module path, else fallback.
    handled = False
    if not args.force_fallback:
        handled = try_module_path(odoo)
    if not handled:
        fallback_seed(odoo)
    else:
        print("\n[3/4] Module handled the catalog/payment setup -> skipping ORM fallback.")

    print("\n[4/4] DONE.")
    print("------------------------------------------------------------------")
    print(" REMINDERS (manual admin steps -- see README_DEPLOY.md):")
    print("   * Confirm l10n_nl (Netherlands - Accounting) is installed and the")
    print("     Fiscal Localization = Netherlands. Do NOT install l10n_tr.")
    print("   * Confirm the company default Sales Tax = 21% BTW (products inherit it).")
    print("   * If any payment method was created WITHOUT a journal, link a cash")
    print("     journal (Contant) / bank journal (Pinnen-Worldline) once journals exist.")
    print(" Then run the POST-DEPLOY SMOKE TEST in README_DEPLOY.md.")
    print("==================================================================")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except xmlrpc.client.Fault as f:
        print(f"\nXML-RPC FAULT: {f.faultString}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(1)
