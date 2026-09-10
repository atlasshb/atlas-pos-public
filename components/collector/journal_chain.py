"""Atlas POS-Ops — tamper-evident append-only journal hash-chain.

Independent witness for kassa-eisen 2.0 'journaal completeness / no silent
deletion'. The kassa MySQL itself is mutable (root can DELETE a sale). This
builds a SHA256 hash chain over every order, stored append-only on pos-hub.
On each run it:
  - appends new orders to the chain,
  - re-verifies already-chained orders still exist and are unchanged,
  - raises DELETION alarms for chained orders gone from MySQL,
  - raises TAMPER alarms for chained orders whose content changed.

Chain store: a SQLite DB, INSERT-only (never UPDATE/DELETE in code). Each entry
links to the previous via prev_hash, so any retro-edit of the store breaks the
chain head, which is periodically anchored (exported with a timestamp).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
from pathlib import Path

import pymysql

GENESIS = "0" * 64


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def _conn(cfg: dict):
    return pymysql.connect(
        host=cfg["host"], port=int(cfg.get("port", 3306)),
        user=cfg["user"], password=cfg["password"], database=cfg["database"],
        charset="utf8mb4", connect_timeout=6, read_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
    )


def init_chain(db: Path):
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS journal_chain (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            b_id INTEGER NOT NULL,
            b_datum TEXT,
            bedrag_cents INTEGER,
            record_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            UNIQUE(customer_id, node_id, b_id)
        );
        CREATE TABLE IF NOT EXISTS journal_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT, node_id TEXT,
            head_seq INTEGER, head_hash TEXT, entries INTEGER,
            anchored_at TEXT
        );
        CREATE TABLE IF NOT EXISTS journal_alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT, node_id TEXT, b_id INTEGER,
            kind TEXT,            -- 'DELETION' | 'TAMPER'
            detail TEXT, raised_at TEXT
        );
    """)
    c.commit()
    c.close()


def _record_hash(cur, b_id: int, row: dict) -> str:
    """Canonical hash of an order's immutable content + its lines + pinbon."""
    core = _sha(
        b_id, row.get("B_DATUM"), row.get("B_TIJD"),
        row.get("B_BEDRAG"), row.get("B_BETAALD"),
        row.get("B_BETAALD_CASH"), row.get("B_BETAALD_APIC"),
    )
    pinbon = row.get("B_PINBON") or ""
    pinbon_hash = _sha(pinbon)
    cur.execute(
        "SELECT BD_ID,BD_ARTIKEL,BD_NAAM,BD_AANTAL,BD_BEDRAG,BD_BTW_TARIEF "
        "FROM bestelling_detail WHERE BD_BESTELLING=%s ORDER BY BD_ID", (b_id,))
    lines = cur.fetchall()
    lines_hash = _sha(*[_sha(l["BD_ID"], l["BD_ARTIKEL"], l["BD_NAAM"], l["BD_AANTAL"], l["BD_BEDRAG"], l["BD_BTW_TARIEF"]) for l in lines])
    return _sha(core, pinbon_hash, lines_hash, len(lines))


def _fetch_orders(cur) -> dict[int, dict]:
    """All orders across live + history, keyed by B_ID."""
    out = {}
    for tbl in ("bestelling", "bestelling_h"):
        cur.execute(f"SELECT B_ID,B_DATUM,B_TIJD,B_BEDRAG,B_BETAALD,B_BETAALD_CASH,B_BETAALD_APIC,B_PINBON FROM {tbl}")
        for r in cur.fetchall():
            out.setdefault(r["B_ID"], r)  # live wins if duplicated
    return out


def run_chain(customer_id: str, node_id: str, term: dict, db: Path) -> dict:
    init_chain(db)
    cfg = term["direct_mysql"]
    mysql = _conn(cfg)
    result = {"new": 0, "verified": 0, "tampered": [], "deleted": [], "head_hash": None, "entries": 0}
    try:
        with mysql.cursor() as cur:
            orders = _fetch_orders(cur)
            store = sqlite3.connect(db)
            try:
                # current chained state
                chained = {row[0]: (row[1], row[2]) for row in store.execute(
                    "SELECT b_id, record_hash, entry_hash FROM journal_chain WHERE customer_id=? AND node_id=? ORDER BY seq",
                    (customer_id, node_id))}
                head = store.execute(
                    "SELECT entry_hash FROM journal_chain WHERE customer_id=? AND node_id=? ORDER BY seq DESC LIMIT 1",
                    (customer_id, node_id)).fetchone()
                prev_hash = head[0] if head else GENESIS

                # 1. verify existing + detect tamper/deletion
                now = dt.datetime.now().isoformat(timespec="seconds")
                for b_id, (stored_record, _eh) in chained.items():
                    if b_id not in orders:
                        result["deleted"].append(b_id)
                        store.execute("INSERT INTO journal_alarms(customer_id,node_id,b_id,kind,detail,raised_at) VALUES(?,?,?,?,?,?)",
                                      (customer_id, node_id, b_id, "DELETION", "chained order missing from kassa DB", now))
                        continue
                    cur_record = _record_hash(cur, b_id, orders[b_id])
                    if cur_record != stored_record:
                        result["tampered"].append(b_id)
                        store.execute("INSERT INTO journal_alarms(customer_id,node_id,b_id,kind,detail,raised_at) VALUES(?,?,?,?,?,?)",
                                      (customer_id, node_id, b_id, "TAMPER", f"content changed (was {stored_record[:12]}, now {cur_record[:12]})", now))
                    else:
                        result["verified"] += 1

                # 2. append new orders (sorted by B_ID for determinism)
                for b_id in sorted(k for k in orders if k not in chained):
                    rec = _record_hash(cur, b_id, orders[b_id])
                    entry = _sha(prev_hash, rec, b_id)
                    store.execute(
                        "INSERT INTO journal_chain(customer_id,node_id,b_id,b_datum,bedrag_cents,record_hash,prev_hash,entry_hash,captured_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (customer_id, node_id, b_id,
                         str(orders[b_id].get("B_DATUM")), orders[b_id].get("B_BEDRAG"),
                         rec, prev_hash, entry, now))
                    prev_hash = entry
                    result["new"] += 1

                # 3. anchor the head
                cnt = store.execute("SELECT COUNT(*), MAX(seq) FROM journal_chain WHERE customer_id=? AND node_id=?",
                                    (customer_id, node_id)).fetchone()
                result["entries"] = cnt[0]
                result["head_hash"] = prev_hash
                store.execute("INSERT INTO journal_anchors(customer_id,node_id,head_seq,head_hash,entries,anchored_at) VALUES(?,?,?,?,?,?)",
                              (customer_id, node_id, cnt[1], prev_hash, cnt[0], now))
                store.commit()
            finally:
                store.close()
    finally:
        mysql.close()
    return result


def verify_chain(customer_id: str, node_id: str, db: Path) -> dict:
    """Recompute entry_hash links across the stored chain to prove the store
    itself hasn't been retro-edited. Independent of MySQL."""
    store = sqlite3.connect(db)
    try:
        rows = store.execute(
            "SELECT b_id, record_hash, prev_hash, entry_hash FROM journal_chain WHERE customer_id=? AND node_id=? ORDER BY seq",
            (customer_id, node_id)).fetchall()
    finally:
        store.close()
    prev = GENESIS
    for b_id, rec, stored_prev, stored_entry in rows:
        if stored_prev != prev:
            return {"ok": False, "break_at_b_id": b_id, "reason": "prev_hash mismatch"}
        if _sha(prev, rec, b_id) != stored_entry:
            return {"ok": False, "break_at_b_id": b_id, "reason": "entry_hash mismatch"}
        prev = stored_entry
    return {"ok": True, "entries": len(rows), "head_hash": prev}
