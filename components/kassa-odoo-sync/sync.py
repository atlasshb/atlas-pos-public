"""Atlas POS -> Odoo sync daemon.

Reads the local kassa MySQL DB and pushes customers/products to pos-hub Odoo
via XML-RPC. Idempotent via Odoo's ir.model.data external IDs (one per kassa row).

Run with --once for a single pass, --loop to repeat forever. Default is dry-run
(no writes). Set [sync] apply=1 in config.ini to enable writes.
"""

import argparse
import configparser
import json
import logging
import sys
import time
import xmlrpc.client
from pathlib import Path

import pymysql

HERE = Path(__file__).resolve().parent
CFG_PATH = HERE / "config.ini"
STATE_PATH = HERE / "state.json"

log = logging.getLogger("atlas-sync")


def load_config():
    if not CFG_PATH.exists():
        sys.exit(f"missing config: {CFG_PATH}")
    cp = configparser.ConfigParser()
    cp.read(CFG_PATH, encoding="utf-8")
    return cp


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def connect_mysql(cfg):
    s = cfg["kassa_mysql"]
    return pymysql.connect(
        host=s["host"],
        port=int(s["port"]),
        user=s["user"],
        password=s["password"],
        database=s["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


class Odoo:
    """Thin XML-RPC wrapper with upsert-by-external-id support."""

    def __init__(self, url, db, user, password, module):
        self.url, self.db, self.user, self.password = url, db, user, password
        self.module = module
        self.uid = None
        self.models = None

    def login(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        info = common.version()
        log.info("Odoo at %s reports version %s", self.url, info.get("server_version"))
        self.uid = common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise RuntimeError("Odoo auth failed - check user/password/db in config.ini")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
        log.info("Authenticated as uid=%s on db=%s", self.uid, self.db)

    def call(self, model, method, *args, **kwargs):
        return self.models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kwargs)

    def upsert(self, model, ext_id_name, values, dry_run):
        """Upsert via ir.model.data. Returns (action, odoo_id) or (action, None) in dry-run."""
        full_ext_id = f"{self.module}.{ext_id_name}"
        existing = self.call(
            "ir.model.data", "search_read",
            [["module", "=", self.module], ["name", "=", ext_id_name]],
            ["res_id", "model"], limit=1,
        )
        if existing:
            res_id = existing[0]["res_id"]
            if dry_run:
                return "would-update", res_id
            self.call(model, "write", [res_id], values)
            return "updated", res_id
        if dry_run:
            return "would-create", None
        new_id = self.call(model, "create", values)
        self.call(
            "ir.model.data", "create",
            {"module": self.module, "name": ext_id_name, "model": model, "res_id": new_id, "noupdate": False},
        )
        return "created", new_id


def fmt_addr(row):
    parts = [row.get("ADRES"), row.get("ADRESNR"), row.get("ADRESTOEV")]
    return " ".join(p for p in parts if p)


def cents_to_float(v):
    return round((v or 0) / 100.0, 2)


def sync_customers(mysql_conn, odoo, dry_run, state):
    last_id = state.get("klanten_last_id", 0)
    with mysql_conn.cursor() as cur:
        cur.execute(
            "SELECT KLANTID, NAAMPERSOON, EMAIL, TELEFOONNRREST, POSTCODE, PLAATS, "
            "ADRES, ADRESNR, ADRESTOEV, INFOEXTERN "
            "FROM klanten WHERE KLANTID > %s ORDER BY KLANTID",
            (last_id,),
        )
        rows = cur.fetchall()
    log.info("klanten: %d new rows since id=%s", len(rows), last_id)
    new_last = last_id
    for r in rows:
        ext_id = f"klant_{r['KLANTID']}"
        vals = {
            "name": (r["NAAMPERSOON"] or f"Kassa klant {r['KLANTID']}")[:255],
            "ref": ext_id,
            "email": r.get("EMAIL"),
            "phone": r.get("TELEFOONNRREST"),
            "street": fmt_addr(r) or None,
            "zip": r.get("POSTCODE"),
            "city": r.get("PLAATS"),
            "comment": r.get("INFOEXTERN"),
            "customer_rank": 1,
        }
        vals = {k: v for k, v in vals.items() if v is not None}
        action, oid = odoo.upsert("res.partner", ext_id, vals, dry_run)
        log.info("  klant %s -> %s (odoo id=%s)", r["KLANTID"], action, oid)
        new_last = max(new_last, r["KLANTID"])
    state["klanten_last_id"] = new_last


def sync_products(mysql_conn, odoo, dry_run, state):
    last_id = state.get("artikel_last_id", 0)
    with mysql_conn.cursor() as cur:
        cur.execute(
            "SELECT A_ID, A_CODE, A_BARCODE, A_NAAM, A_OMSCHRIJVING, "
            "A_PRIJS, A_BTW_TARIEF, A_ARTIKELGROEP "
            "FROM artikel WHERE A_ID > %s ORDER BY A_ID",
            (last_id,),
        )
        rows = cur.fetchall()
    log.info("artikel: %d new rows since id=%s", len(rows), last_id)
    new_last = last_id
    for r in rows:
        ext_id = f"artikel_{r['A_ID']}"
        vals = {
            "name": (r["A_NAAM"] or f"Kassa artikel {r['A_ID']}")[:255],
            "default_code": r.get("A_CODE") or ext_id,
            "barcode": r.get("A_BARCODE"),
            "list_price": cents_to_float(r.get("A_PRIJS")),
            "description_sale": r.get("A_OMSCHRIJVING"),
            "type": "product",
            "sale_ok": True,
            "purchase_ok": False,
            "available_in_pos": True,
        }
        vals = {k: v for k, v in vals.items() if v is not None}
        action, oid = odoo.upsert("product.template", ext_id, vals, dry_run)
        log.info("  artikel %s -> %s (odoo id=%s)", r["A_ID"], action, oid)
        new_last = max(new_last, r["A_ID"])
    state["artikel_last_id"] = new_last


SYNCERS = {"customers": sync_customers, "products": sync_products}


def run_once(cfg):
    apply = cfg.getboolean("sync", "apply", fallback=False)
    dry_run = not apply
    entities = [e.strip() for e in cfg["sync"]["entities"].split(",") if e.strip()]
    state = load_state()

    mysql_conn = connect_mysql(cfg)
    try:
        odoo = Odoo(
            cfg["odoo"]["url"], cfg["odoo"]["db"],
            cfg["odoo"]["user"], cfg["odoo"]["password"],
            cfg["sync"]["external_id_module"],
        )
        odoo.login()
        log.info("MODE: %s", "APPLY" if apply else "DRY-RUN (no writes)")
        for e in entities:
            fn = SYNCERS.get(e)
            if not fn:
                log.warning("unknown entity: %s", e)
                continue
            fn(mysql_conn, odoo, dry_run, state)
        if apply:
            save_state(state)
    finally:
        mysql_conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single sync pass and exit (default)")
    parser.add_argument("--loop", action="store_true", help="run forever, sleeping interval_seconds between passes")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config()

    if args.loop:
        interval = cfg.getint("sync", "interval_seconds", fallback=300)
        log.info("loop mode: every %ss. Ctrl+C to stop.", interval)
        while True:
            try:
                run_once(cfg)
            except Exception as exc:
                log.exception("pass failed: %s", exc)
            time.sleep(interval)
    else:
        run_once(cfg)


if __name__ == "__main__":
    main()
