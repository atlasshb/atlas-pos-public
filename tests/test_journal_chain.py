import sqlite3
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

jc = load_module("components/collector/journal_chain.py")


def _build_chain(db, rows, mutate=None):
    jc.init_chain(db)
    con = sqlite3.connect(db)
    prev = jc.GENESIS
    for i, (cid, nid, b_id, datum, cents) in enumerate(rows):
        rec = jc._sha(b_id, datum, cents)
        entry = jc._sha(prev, rec, b_id)
        if mutate and i == mutate[0]:
            entry = mutate[1]
        con.execute(
            "INSERT INTO journal_chain(customer_id,node_id,b_id,b_datum,bedrag_cents,"
            "record_hash,prev_hash,entry_hash,captured_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (cid, nid, b_id, datum, cents, rec, prev, entry, "2026-01-01T00:00:00"),
        )
        prev = entry
    con.commit()
    con.close()
    return prev


ROWS = [
    ("cust", "node1", 1, "2026-01-01", 1000),
    ("cust", "node1", 2, "2026-01-02", 2500),
    ("cust", "node1", 3, "2026-01-03", 400),
]


def test_sha_is_deterministic_and_order_sensitive():
    assert jc._sha("a", "b") == jc._sha("a", "b")
    assert jc._sha("a", "b") != jc._sha("b", "a")


def test_verify_chain_ok(tmp_path):
    db = tmp_path / "chain.db"
    _build_chain(db, ROWS)
    result = jc.verify_chain("cust", "node1", db)
    assert result["ok"] is True
    assert result["entries"] == 3


def test_verify_chain_detects_tamper(tmp_path):
    db = tmp_path / "chain.db"
    _build_chain(db, ROWS)
    con = sqlite3.connect(db)
    con.execute("UPDATE journal_chain SET record_hash='deadbeef' WHERE b_id=2")
    con.commit()
    con.close()
    result = jc.verify_chain("cust", "node1", db)
    assert result["ok"] is False
    assert result["break_at_b_id"] == 2
