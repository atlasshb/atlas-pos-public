"""Atlas POS-Ops agent (atlas-posd) — read-only Phase 0 prototype.

Runs on the POS terminal. Binds to the Tailscale interface only. Exposes
read-only JSON endpoints that the central collector (pos-hub) polls. All ops
are append-only logged. No raw SQL accepted from clients — only typed ops.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))

NODE_ID = CFG["node_id"]
BIND_HOST = CFG["bind_host"]
BIND_PORT = int(CFG["bind_port"])
TOKEN = CFG["bearer_token"]
MYSQL = CFG["mysql"]
BACKUP_DIR = Path(CFG["backup_dir"])
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
MYSQLDUMP = CFG.get("mysqldump", r"C:\xampp\mysql\bin\mysqldump.exe")

AUDIT = HERE / "audit.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(AUDIT, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("atlas-posd")

app = FastAPI(title="atlas-posd", version="0.1.0")
START = time.time()


def auth(authorization: str = Header(None)):
    if not authorization or authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad bearer")
    return True


@contextmanager
def conn():
    c = pymysql.connect(
        host=MYSQL["host"], port=int(MYSQL["port"]),
        user=MYSQL["user"], password=MYSQL["password"], database=MYSQL["database"],
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )
    try:
        yield c
    finally:
        c.close()


def cents(v): return round((v or 0) / 100.0, 2)


@app.get("/health")
def health():
    kassa_running = False
    try:
        out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq kassa.exe", "/FO", "CSV", "/NH"], timeout=4, text=True)
        kassa_running = "kassa.exe" in out
    except Exception:
        pass
    db_ok = False
    db_err = None
    versie = None
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute("SELECT V_DB FROM versie WHERE V_ID=1")
            row = cur.fetchone()
            versie = row["V_DB"] if row else None
            db_ok = True
    except Exception as exc:
        db_err = str(exc)[:200]
    return {
        "node_id": NODE_ID,
        "hostname": socket.gethostname(),
        "agent_version": "0.1.0",
        "uptime_s": round(time.time() - START, 1),
        "now": dt.datetime.now().isoformat(timespec="seconds"),
        "kassa_running": kassa_running,
        "db_reachable": db_ok,
        "db_error": db_err,
        "db_version": versie,
    }


@app.get("/day-totals")
def day_totals(date: str = Query(None, description="YYYY-MM-DD, defaults to today"), _: bool = Depends(auth)):
    target = date or dt.date.today().isoformat()
    sql = """
        SELECT
          COUNT(*) AS bestelling_count,
          COALESCE(SUM(B_BEDRAG),0) AS total_cents,
          COALESCE(SUM(B_BETAALD_CASH),0) AS cash_cents,
          COALESCE(SUM(B_BEDRAG) - SUM(B_BETAALD_CASH),0) AS pin_cents
        FROM bestelling
        WHERE B_DATUM = %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (target,))
        r = cur.fetchone() or {}
        cur.execute(
            "SELECT HOUR(B_TIJD) hour, COUNT(*) n, COALESCE(SUM(B_BEDRAG),0) cents "
            "FROM bestelling WHERE B_DATUM=%s GROUP BY HOUR(B_TIJD) ORDER BY hour",
            (target,),
        )
        per_hour = [{"hour": x["hour"], "count": x["n"], "eur": cents(x["cents"])} for x in cur.fetchall()]
    log.info("day-totals date=%s count=%s total_eur=%.2f", target, r.get("bestelling_count"), cents(r.get("total_cents")))
    return {
        "date": target,
        "bestelling_count": r.get("bestelling_count", 0),
        "total_eur": cents(r.get("total_cents")),
        "cash_eur": cents(r.get("cash_cents")),
        "pin_eur": cents(r.get("pin_cents")),
        "per_hour": per_hour,
    }


@app.get("/menu")
def menu(_: bool = Depends(auth)):
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM artikel")
        artikel_count = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM artikelgroep")
        groep_count = cur.fetchone()["n"]
        cur.execute("SELECT AG_ID, AG_NAAM, AG_SORT FROM artikelgroep ORDER BY AG_SORT, AG_ID")
        groepen = cur.fetchall()
        cur.execute("SELECT BTW_ID, BTW_NAAM, BTW_TARIEF FROM btwtabel ORDER BY BTW_ID")
        btw = [{"id": x["BTW_ID"], "naam": x["BTW_NAAM"], "tarief_pct": (x["BTW_TARIEF"] or 0) / 100.0} for x in cur.fetchall()]
    return {"artikel_count": artikel_count, "groep_count": groep_count, "groepen": groepen, "btw": btw}


@app.get("/journal/tail")
def journal_tail(limit: int = Query(20, ge=1, le=200), _: bool = Depends(auth)):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT B_ID, B_DATUM, B_TIJD, B_TAFELNAAM, B_KLANTNAAM, B_BEDRAG, B_BETAALD, B_BETAALD_CASH "
            "FROM bestelling ORDER BY B_ID DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    return {
        "rows": [
            {
                "id": r["B_ID"],
                "datum": r["B_DATUM"].isoformat() if r["B_DATUM"] else None,
                "tijd": r["B_TIJD"].isoformat() if r["B_TIJD"] else None,
                "tafel": r["B_TAFELNAAM"],
                "klant": r["B_KLANTNAAM"],
                "bedrag_eur": cents(r["B_BEDRAG"]),
                "betaald_eur": cents(r["B_BETAALD"]),
                "cash_eur": cents(r["B_BETAALD_CASH"]),
            }
            for r in rows
        ]
    }


@app.post("/snapshot")
def snapshot(mirror: bool = False, _: bool = Depends(auth)):
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"{NODE_ID}_{ts}.sql.gz"
    tmp = BACKUP_DIR / f"{NODE_ID}_{ts}.sql"
    cmd = [
        MYSQLDUMP,
        f"-h{MYSQL['host']}", f"-P{MYSQL['port']}",
        f"-u{MYSQL['user']}", f"-p{MYSQL['password']}",
        "--single-transaction", "--quick", "--routines", "--triggers",
        MYSQL["database"],
    ]
    try:
        with tmp.open("wb") as f:
            subprocess.run(cmd, check=True, stdout=f, stderr=subprocess.PIPE, timeout=120)
        import gzip, shutil
        with tmp.open("rb") as fin, gzip.open(out, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        tmp.unlink(missing_ok=True)
        body = out.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        size = len(body)
        log.info("snapshot path=%s size=%s sha256=%s", out, size, sha)
        result = {"path": str(out), "size": size, "sha256": sha, "node_id": NODE_ID, "taken_at": ts}
        if mirror and "collector_url" in CFG and "customer_id" in CFG:
            import urllib.request
            url = f"{CFG['collector_url']}/api/mirror/{CFG['customer_id']}/{NODE_ID}"
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/gzip",
                    "X-SHA256": sha,
                    "X-Taken-At": ts,
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result["mirror"] = json.loads(resp.read().decode("utf-8"))
            log.info("mirror push ok size=%s", size)
        return result
    except subprocess.CalledProcessError as exc:
        log.exception("snapshot failed")
        return JSONResponse({"error": "mysqldump failed", "stderr": exc.stderr.decode("utf-8", "ignore")[:400]}, 500)
    except Exception as exc:
        log.exception("snapshot failed")
        return JSONResponse({"error": str(exc)}, 500)


if __name__ == "__main__":
    import uvicorn
    log.info("atlas-posd node_id=%s binding %s:%s", NODE_ID, BIND_HOST, BIND_PORT)
    uvicorn.run(app, host=BIND_HOST, port=BIND_PORT, log_level="warning", access_log=False)
