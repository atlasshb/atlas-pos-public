"""Direct-MySQL poll + mirror for POS terminals that have no atlas-posd agent.

Used for boxes we cannot install software on (e.g. Venue A / venue-a-till),
but whose kassa MySQL is reachable over Tailscale via the remote@% user. The
collector calls probe_direct() for any fleet terminal carrying a `direct_mysql`
block, and mirror_direct() produces a PAN-scrubbed logical dump into the vault.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import re
import sqlite3
from pathlib import Path

import pymysql

PAN_RE = re.compile(rb"\d{13,19}")


def _luhn_ok(b: bytes) -> bool:
    s, alt = 0, False
    for ch in reversed(b):
        d = ch - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0


def scrub_pan(data: bytes) -> tuple[bytes, int]:
    """Replace any Luhn-valid 13-19 digit run with a redaction token.
    Leaves masked PANs (broken by 'x'), tokens/PAR/AID (Luhn-invalid) intact."""
    n = [0]

    def repl(m):
        run = m.group()
        # A real PAN passes Luhn AND has digit diversity. All-same-digit runs
        # (e.g. 0000000000000 template padding) pass Luhn trivially but are not
        # card numbers — never redact them (would corrupt a faithful backup).
        if len(set(run)) > 1 and _luhn_ok(run):
            n[0] += 1
            return b"[REDACTED-PAN%d]" % len(run)
        return run

    return PAN_RE.sub(repl, data), n[0]


def _conn(cfg: dict):
    return pymysql.connect(
        host=cfg["host"], port=int(cfg.get("port", 3306)),
        user=cfg["user"], password=cfg["password"], database=cfg["database"],
        charset="utf8mb4", connect_timeout=6, read_timeout=20,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _cents(v):
    return round(float(v or 0) / 100.0, 2)


def probe_direct(term: dict) -> dict:
    """Return the same shape as the agent collector probe: health/day_totals/journal."""
    cfg = term["direct_mysql"]
    out = {"polled_at": dt.datetime.now().isoformat(timespec="seconds"), "last_error": None}
    try:
        conn = _conn(cfg)
    except Exception as exc:
        out["last_error"] = f"connect: {exc}"
        return out
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT V_DB FROM versie WHERE V_ID=1")
            row = cur.fetchone()
            dbver = row["V_DB"] if row else None
            cur.execute("SELECT @@hostname AS h")
            host = cur.fetchone()["h"]
            out["health"] = {
                "node_id": term["node_id"], "hostname": host,
                "agent_version": "direct-poll", "uptime_s": 0,
                "now": dt.datetime.now().isoformat(timespec="seconds"),
                "kassa_running": None, "db_reachable": True, "db_error": None, "db_version": dbver,
            }
            today = dt.date.today().isoformat()
            cur.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(B_BEDRAG),0) tot, COALESCE(SUM(B_BETAALD_CASH),0) cash "
                "FROM bestelling WHERE B_DATUM=%s", (today,))
            r = cur.fetchone()
            out["day_totals"] = {
                "date": today, "bestelling_count": r["n"],
                "total_eur": _cents(r["tot"]), "cash_eur": _cents(r["cash"]),
                "pin_eur": _cents((r["tot"] or 0) - (r["cash"] or 0)), "per_hour": [],
            }
            cur.execute(
                "SELECT B_ID,B_DATUM,B_TIJD,B_TAFELNAAM,B_KLANTNAAM,B_BEDRAG,B_BETAALD,B_BETAALD_CASH "
                "FROM bestelling ORDER BY B_ID DESC LIMIT 10")
            out["journal"] = {"rows": [{
                "id": x["B_ID"],
                "datum": x["B_DATUM"].isoformat() if x["B_DATUM"] else None,
                "tijd": x["B_TIJD"].isoformat() if x["B_TIJD"] else None,
                "tafel": x["B_TAFELNAAM"], "klant": x["B_KLANTNAAM"],
                "bedrag_eur": _cents(x["B_BEDRAG"]), "betaald_eur": _cents(x["B_BETAALD"]),
                "cash_eur": _cents(x["B_BETAALD_CASH"]),
            } for x in cur.fetchall()]}
    except Exception as exc:
        out["last_error"] = f"query: {exc}"
    finally:
        conn.close()
    return out


def mirror_direct(term: dict, vault_root: Path, ledger: Path, customer_id: str) -> dict:
    """Logical dump (CREATE + INSERT) of the kassa DB, PAN-scrubbed, gzipped to vault."""
    cfg = term["direct_mysql"]
    node = term["node_id"]
    conn = _conn(cfg)
    buf = bytearray()
    buf += f"-- Atlas POS-Ops direct mirror of {cfg['database']} @ {cfg['host']}\n".encode()
    buf += f"-- taken {dt.datetime.now().isoformat()}  (PAN-scrubbed)\n".encode()
    buf += b"SET FOREIGN_KEY_CHECKS=0;\n"
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tcol = list(cur.fetchone().keys())[0]
            cur.execute("SHOW TABLES")
            tables = [r[tcol] for r in cur.fetchall()]
            for t in tables:
                cur.execute(f"SHOW CREATE TABLE `{t}`")
                ddl = cur.fetchone()["Create Table"]
                buf += f"\nDROP TABLE IF EXISTS `{t}`;\n".encode() + ddl.encode() + b";\n"
                cur.execute(f"SELECT * FROM `{t}`")
                rows = cur.fetchall()
                if not rows:
                    continue
                cols = list(rows[0].keys())
                collist = ",".join(f"`{c}`" for c in cols)
                for row in rows:
                    vals = []
                    for c in cols:
                        v = row[c]
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        elif isinstance(v, (bytes, bytearray)):
                            vals.append("0x" + v.hex())
                        else:
                            s = str(v).replace("\\", "\\\\").replace("'", "\\'")
                            vals.append("'" + s + "'")
                    buf += f"INSERT INTO `{t}` ({collist}) VALUES (".encode() + ",".join(vals).encode() + b");\n"
        buf += b"SET FOREIGN_KEY_CHECKS=1;\n"
    finally:
        conn.close()

    scrubbed, n_redacted = scrub_pan(bytes(buf))
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{node}_{ts}.sql.gz"
    dest_dir = vault_root / customer_id / node
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fname
    gz = gzip.compress(scrubbed)
    dest.write_bytes(gz)
    sha = hashlib.sha256(gz).hexdigest()
    c = sqlite3.connect(ledger)
    try:
        c.execute(
            "INSERT INTO mirrors (customer_id,node_id,filename,path,size_bytes,sha256,received_at,source_taken_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (customer_id, node, fname, str(dest), len(gz), sha, dt.datetime.now().isoformat(timespec="seconds"), ts),
        )
        c.commit()
    finally:
        c.close()
    return {"path": str(dest), "size_bytes": len(gz), "sha256": sha, "pans_redacted": n_redacted, "tables": len(tables)}
