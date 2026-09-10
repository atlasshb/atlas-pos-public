"""Atlas POS-Ops collector + cockpit (multi-tenant, Phase 0.5).

Customers (res.partner-equivalent) own terminals. Each terminal runs atlas-posd
over Tailscale. The collector polls health/totals from each, mirrors backups to
local disk + a SQLite ledger, and serves a tenant-grouped cockpit.

Endpoints (cockpit auth: HTTP Basic 'atlas' / cockpit_password from fleet.json):
  GET  /                            HTML cockpit (auto-refresh 10s)
  GET  /healthz                     liveness
  GET  /api/snapshot                full state (tokens stripped)
  GET  /api/mirrors/{customer_id}   mirror ledger for one customer
  POST /api/mirror/{c}/{n}          ingest a *.sql.gz uploaded by an agent
                                    Auth: Bearer <terminal_token>; Header X-SHA256
  POST /api/enroll                  add a new terminal to fleet.json
                                    Auth: Bearer <enrollment.token>
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
import secrets
import sqlite3
from pathlib import Path

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

HERE = Path(__file__).resolve().parent
FLEET_PATH = HERE / "fleet.json"
SECRETS_PATH = HERE / "secrets.json"
MIRROR_ROOT = Path("/srv/atlas-posops/mirrors")
LEDGER = HERE / "mirrors.sqlite"
AUDIT = HERE / "audit.log"

MIRROR_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(AUDIT, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("atlas-collector")


def load_fleet() -> dict:
    return json.loads(FLEET_PATH.read_text(encoding="utf-8"))


def save_fleet(fleet: dict) -> None:
    tmp = FLEET_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fleet, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FLEET_PATH)


def load_secrets() -> dict:
    if SECRETS_PATH.exists():
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    s = {"cockpit_user": "atlas", "cockpit_password": "<COCKPIT_PW>"}
    SECRETS_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")
    os.chmod(SECRETS_PATH, 0o600)
    return s


SECRETS = load_secrets()


def init_ledger():
    conn = sqlite3.connect(LEDGER)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mirrors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            received_at TEXT NOT NULL,
            source_taken_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mirrors_cust_node ON mirrors(customer_id, node_id, received_at);
    """)
    conn.commit()
    conn.close()


init_ledger()


# ---------------------------------------------------------------------------
# Cockpit auth. Two ways in:
#   1. Authentik SSO via Caddy: the trusted reverse proxy injects a shared
#      X-Atlas-Proxy secret AFTER Authentik has authenticated the user.
#   2. Direct Tailscale access to :8087: HTTP Basic (single operator account).
# ---------------------------------------------------------------------------
basic = HTTPBasic(auto_error=False)
PROXY_SECRET = SECRETS.get("proxy_secret")
# Authentik groups whose members see the WHOLE fleet (internal staff/admins).
INTERNAL_GROUPS = set(SECRETS.get("internal_groups", ["Atlas Staff", "authentik Admins"]))


def _parse_groups(raw: str) -> set:
    if not raw:
        return set()
    out = set()
    for part in raw.replace("|", ",").split(","):
        p = part.strip()
        if p:
            out.add(p)
    return out


def require_cockpit(request: Request, creds: HTTPBasicCredentials = Depends(basic)):
    """Returns the caller's access context: {internal: bool, groups: set, who: str}.
    Internal => sees the whole fleet. Otherwise => only customers whose access_groups
    intersect the caller's Authentik groups (third-party / per-customer access)."""
    # 1. trusted SSO proxy (Authentik already authenticated the user)
    if PROXY_SECRET:
        hdr = request.headers.get("x-atlas-proxy", "")
        if hdr and secrets.compare_digest(hdr, PROXY_SECRET):
            groups = _parse_groups(request.headers.get("x-authentik-groups", ""))
            who = request.headers.get("x-authentik-username") or request.headers.get("x-authentik-email") or "sso-user"
            return {"internal": bool(groups & INTERNAL_GROUPS), "groups": groups, "who": who}
    # 2. direct Basic auth (operator fallback) -> full internal
    if creds and secrets.compare_digest(creds.username, SECRETS["cockpit_user"]) \
            and secrets.compare_digest(creds.password, SECRETS["cockpit_password"]):
        return {"internal": True, "groups": set(), "who": "basic-auth"}
    raise HTTPException(401, "bad cockpit auth", headers={"WWW-Authenticate": "Basic"})


def _visible_customers(fleet: dict, ctx: dict) -> list:
    if ctx["internal"]:
        return fleet["customers"]
    g = ctx["groups"]
    return [c for c in fleet["customers"] if g & set(c.get("access_groups", []))]


# ---------------------------------------------------------------------------
# Poller
# ---------------------------------------------------------------------------
app = FastAPI(title="atlas-posops-collector", version="0.5.0")
CACHE: dict[str, dict] = {}  # node_id -> probe result


async def probe(terminal: dict) -> dict:
    base = f"http://{terminal['tailnet_ip']}:{terminal['port']}"
    headers = {"Authorization": f"Bearer {terminal['token']}"}
    out = {"polled_at": dt.datetime.now().isoformat(timespec="seconds"), "last_error": None}
    async with httpx.AsyncClient(timeout=6) as cli:
        try:
            r = await cli.get(f"{base}/health"); r.raise_for_status()
            out["health"] = r.json()
        except Exception as exc:
            out["last_error"] = f"health: {exc}"
            return out
        for path, key in (("/day-totals", "day_totals"), ("/journal/tail?limit=10", "journal")):
            try:
                r = await cli.get(f"{base}{path}", headers=headers); r.raise_for_status()
                out[key] = r.json()
            except Exception as exc:
                out.setdefault("last_error", f"{key}: {exc}")
    return out


async def probe_any(terminal: dict) -> dict:
    """Dispatch: agent terminals over HTTP, agent-less terminals via direct MySQL."""
    if "direct_mysql" in terminal:
        import posops_direct
        return await asyncio.to_thread(posops_direct.probe_direct, terminal)
    return await probe(terminal)


async def poll_loop():
    while True:
        fleet = load_fleet()
        terminals = [t for c in fleet["customers"] for t in c["terminals"]]
        if terminals:
            results = await asyncio.gather(*[probe_any(t) for t in terminals], return_exceptions=False)
            for t, r in zip(terminals, results):
                CACHE[t["node_id"]] = r
        await asyncio.sleep(30)


MIRROR_ROOT = Path("/srv/atlas-posops/mirrors")
MIRROR_MAX_AGE_H = 20  # take a fresh mirror if the latest is older than this
CHAIN_DB = HERE / "journal_chain.sqlite"
CHAIN_INTERVAL_S = 900  # extend/verify the tamper-evident journal chain every 15 min


def chain_status(customer_id: str, node_id: str) -> dict | None:
    if not CHAIN_DB.exists():
        return None
    try:
        c = sqlite3.connect(CHAIN_DB)
        try:
            head = c.execute("SELECT entry_hash, COUNT(*) OVER () FROM journal_chain WHERE customer_id=? AND node_id=? ORDER BY seq DESC LIMIT 1",
                             (customer_id, node_id)).fetchone()
            entries = c.execute("SELECT COUNT(*) FROM journal_chain WHERE customer_id=? AND node_id=?", (customer_id, node_id)).fetchone()[0]
            alarms = c.execute("SELECT COUNT(*) FROM journal_alarms WHERE customer_id=? AND node_id=?", (customer_id, node_id)).fetchone()[0]
            last_anchor = c.execute("SELECT anchored_at FROM journal_anchors WHERE customer_id=? AND node_id=? ORDER BY id DESC LIMIT 1", (customer_id, node_id)).fetchone()
        finally:
            c.close()
        if not entries:
            return None
        return {"entries": entries, "head_hash": head[0] if head else None,
                "open_alarms": alarms, "last_anchor": last_anchor[0] if last_anchor else None}
    except Exception:
        return None


async def chain_loop():
    import journal_chain
    while True:
        fleet = load_fleet()
        for c in fleet["customers"]:
            for t in c["terminals"]:
                if "direct_mysql" not in t:
                    continue
                try:
                    r = await asyncio.to_thread(journal_chain.run_chain, c["id"], t["node_id"], t, CHAIN_DB)
                    if r["new"] or r["tampered"] or r["deleted"]:
                        log.info("chain %s/%s: +%d new, %d verified, tampered=%s deleted=%s head=%s",
                                 c["id"], t["node_id"], r["new"], r["verified"], r["tampered"], r["deleted"], (r["head_hash"] or "")[:12])
                    if r["tampered"] or r["deleted"]:
                        log.warning("JOURNAL ALARM %s/%s tampered=%s deleted=%s", c["id"], t["node_id"], r["tampered"], r["deleted"])
                except Exception as exc:
                    log.warning("chain failed %s/%s: %s", c["id"], t["node_id"], exc)
        await asyncio.sleep(CHAIN_INTERVAL_S)


def _hours_since_last_mirror(customer_id: str, node_id: str) -> float:
    last = mirror_last(customer_id, node_id)
    if not last:
        return 1e9
    try:
        t = dt.datetime.fromisoformat(last["received_at"])
        return (dt.datetime.now() - t).total_seconds() / 3600.0
    except Exception:
        return 1e9


async def mirror_loop():
    """Daily off-site mirror for agent-less (direct_mysql) terminals."""
    import posops_direct
    while True:
        fleet = load_fleet()
        for c in fleet["customers"]:
            for t in c["terminals"]:
                if "direct_mysql" not in t:
                    continue  # agent terminals push their own mirror via /api/mirror
                if _hours_since_last_mirror(c["id"], t["node_id"]) < MIRROR_MAX_AGE_H:
                    continue
                try:
                    res = await asyncio.to_thread(
                        posops_direct.mirror_direct, t, MIRROR_ROOT, LEDGER, c["id"])
                    log.info("auto-mirror %s/%s size=%s redacted=%s",
                             c["id"], t["node_id"], res["size_bytes"], res["pans_redacted"])
                except Exception as exc:
                    log.warning("auto-mirror failed %s/%s: %s", c["id"], t["node_id"], exc)
        await asyncio.sleep(3600)  # re-check hourly; mirror only when >20h old


@app.on_event("startup")
async def _startup():
    log.info("collector starting")
    asyncio.create_task(poll_loop())
    asyncio.create_task(mirror_loop())
    asyncio.create_task(chain_loop())


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    fleet = load_fleet()
    return {"ok": True, "customers": len(fleet["customers"]), "terminals": sum(len(c["terminals"]) for c in fleet["customers"]), "cached": len(CACHE)}


@app.get("/api/snapshot")
def snapshot(ctx=Depends(require_cockpit)):
    fleet = load_fleet()
    customers = []
    for c in _visible_customers(fleet, ctx):
        terminals = []
        for t in c["terminals"]:
            safe = {k: v for k, v in t.items() if k != "token"}
            # Never leak DB credentials to the cockpit: redact direct_mysql to host/db only
            if "direct_mysql" in safe:
                dm = safe["direct_mysql"]
                safe["direct_mysql"] = {"host": dm.get("host"), "database": dm.get("database"), "mode": "direct-poll"}
            safe["cache"] = CACHE.get(t["node_id"])
            safe["mirror_last"] = mirror_last(c["id"], t["node_id"])
            safe["chain"] = chain_status(c["id"], t["node_id"])
            terminals.append(safe)
        customers.append({"id": c["id"], "name": c["name"], "tier": c.get("tier"), "color": c.get("color"), "odoo_partner_id": c.get("odoo_partner_id"), "terminals": terminals})
    return {"customers": customers, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "viewer": {"who": ctx["who"], "internal": ctx["internal"], "scope": "fleet" if ctx["internal"] else "own"}}


def mirror_last(customer_id: str, node_id: str) -> dict | None:
    conn = sqlite3.connect(LEDGER)
    try:
        cur = conn.execute(
            "SELECT received_at, size_bytes, sha256 FROM mirrors WHERE customer_id=? AND node_id=? ORDER BY received_at DESC LIMIT 1",
            (customer_id, node_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"received_at": row[0], "size_bytes": row[1], "sha256": row[2]}
    finally:
        conn.close()


@app.get("/api/mirrors/{customer_id}")
def mirrors_list(customer_id: str, ctx=Depends(require_cockpit)):
    fleet = load_fleet()
    allowed = {c["id"] for c in _visible_customers(fleet, ctx)}
    if customer_id not in allowed:
        raise HTTPException(403, "not your customer")
    conn = sqlite3.connect(LEDGER)
    try:
        cur = conn.execute(
            "SELECT node_id, filename, size_bytes, sha256, received_at FROM mirrors WHERE customer_id=? ORDER BY received_at DESC LIMIT 200",
            (customer_id,),
        )
        return {"customer_id": customer_id, "rows": [
            {"node_id": r[0], "filename": r[1], "size_bytes": r[2], "sha256": r[3], "received_at": r[4]}
            for r in cur.fetchall()
        ]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Mirror upload (agent -> collector)
# ---------------------------------------------------------------------------
def find_terminal(customer_id: str, node_id: str):
    fleet = load_fleet()
    for c in fleet["customers"]:
        if c["id"] != customer_id:
            continue
        for t in c["terminals"]:
            if t["node_id"] == node_id:
                return c, t
    return None, None


@app.post("/api/mirror/{customer_id}/{node_id}")
async def mirror_ingest(customer_id: str, node_id: str, request: Request,
                        authorization: str = Header(None),
                        x_sha256: str | None = Header(None),
                        x_taken_at: str | None = Header(None)):
    cust, term = find_terminal(customer_id, node_id)
    if not term:
        raise HTTPException(404, "unknown terminal")
    if authorization != f"Bearer {term['token']}":
        raise HTTPException(401, "bad bearer")
    body = await request.body()
    if not body:
        raise HTTPException(400, "empty body")
    sha = hashlib.sha256(body).hexdigest()
    if x_sha256 and x_sha256.lower() != sha:
        raise HTTPException(400, f"sha256 mismatch (got {sha}, header {x_sha256})")
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{node_id}_{ts}.sql.gz"
    dest_dir = MIRROR_ROOT / customer_id / node_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fname
    dest.write_bytes(body)
    conn = sqlite3.connect(LEDGER)
    try:
        conn.execute(
            "INSERT INTO mirrors (customer_id, node_id, filename, path, size_bytes, sha256, received_at, source_taken_at) VALUES (?,?,?,?,?,?,?,?)",
            (customer_id, node_id, fname, str(dest), len(body), sha, dt.datetime.now().isoformat(timespec="seconds"), x_taken_at),
        )
        conn.commit()
    finally:
        conn.close()
    log.info("mirror ingest customer=%s node=%s size=%s sha=%s", customer_id, node_id, len(body), sha)
    return {"ok": True, "path": str(dest), "size_bytes": len(body), "sha256": sha}


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------
@app.post("/api/enroll")
def enroll(body: dict = Body(...), authorization: str = Header(None)):
    fleet = load_fleet()
    if authorization != f"Bearer {fleet['enrollment']['token']}":
        raise HTTPException(401, "bad enrollment token")
    customer_id = body.get("customer_id")
    if not customer_id:
        raise HTTPException(400, "customer_id required")
    cust = next((c for c in fleet["customers"] if c["id"] == customer_id), None)
    if not cust:
        # Auto-create customer record on first enrollment
        cust = {"id": customer_id, "name": body.get("customer_name") or customer_id, "tier": "external",
                "color": "#9ad0ff", "odoo_partner_id": body.get("odoo_partner_id"), "terminals": []}
        fleet["customers"].append(cust)

    node_id = body.get("node_id") or f"{customer_id}-{secrets.token_hex(3)}"
    tailnet_ip = body.get("tailnet_ip")
    if not tailnet_ip:
        raise HTTPException(400, "tailnet_ip required")

    existing = next((t for t in cust["terminals"] if t["node_id"] == node_id), None)
    token = secrets.token_hex(32)
    record = {
        "node_id": node_id,
        "label": body.get("label") or node_id,
        "tailnet_ip": tailnet_ip,
        "port": int(body.get("port") or 8765),
        "token": token,
        "enrolled_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    if existing:
        existing.update(record)
    else:
        cust["terminals"].append(record)
    save_fleet(fleet)
    log.info("enroll customer=%s node=%s ip=%s", customer_id, node_id, tailnet_ip)
    return {"ok": True, "node_id": node_id, "customer_id": customer_id, "token": token,
            "collector_url": "http://192.0.2.10:8087", "agent_port": record["port"]}


# ---------------------------------------------------------------------------
# Cockpit HTML
# ---------------------------------------------------------------------------
COCKPIT_HTML = """<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><title>Atlas POS-Ops cockpit</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:#0b1020; --card:#141a30; --ink:#e6ecf6; --muted:#8a93a8; --line:#1f2742; --ok:#2ecc71; --warn:#f4b740; --bad:#ff5670; --stale:#a06bff; }
* { box-sizing:border-box; } body { margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--ink); }
header { padding:18px 24px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); }
header h1 { margin:0; font-weight:600; font-size:18px; letter-spacing:.3px; }
header .stamp { color:var(--muted); font-variant-numeric:tabular-nums; font-size:12px; }
.tenant { padding:8px 24px 0; }
.tenant h2 { margin:18px 0 8px; font-size:13px; letter-spacing:.6px; text-transform:uppercase; color:var(--muted); display:flex; align-items:center; gap:10px; }
.tenant h2 .name { color:var(--ink); font-size:15px; letter-spacing:.2px; text-transform:none; }
.tenant h2 .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:10.5px; background:#1c2444; color:var(--muted); }
.tenant h2 .odoo { font-size:11px; color:var(--muted); text-decoration:none; border:1px solid var(--line); padding:2px 6px; border-radius:4px; }
.tenant h2 .odoo:hover { color:var(--ink); border-color:#5cc8ff; }
.grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); padding-bottom:6px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; border-left:3px solid var(--accent, #5cc8ff); }
.card h3 { margin:0 0 4px; font-size:15px; font-weight:600; display:flex; align-items:center; gap:8px; }
.card .sub { color:var(--muted); font-size:11.5px; margin-bottom:10px; }
.dot { width:9px; height:9px; border-radius:50%; display:inline-block; flex-shrink:0; }
.dot.ok { background:var(--ok); } .dot.warn { background:var(--warn); } .dot.bad { background:var(--bad); } .dot.stale { background:var(--stale); }
.kpi { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:6px 0 10px; }
.kpi div { background:#0e1428; border:1px solid #1c2444; border-radius:7px; padding:8px 10px; }
.kpi label { display:block; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.5px; margin-bottom:1px; }
.kpi b { font-size:16px; font-variant-numeric:tabular-nums; }
.mirror { display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-top:1px solid #1c2444; margin-top:8px; font-size:11.5px; color:var(--muted); }
.mirror b { color:var(--ink); font-weight:500; }
table { width:100%; border-collapse:collapse; margin-top:8px; font-size:12px; }
th,td { text-align:left; padding:5px 6px; border-bottom:1px solid #1c2444; }
th { color:var(--muted); font-weight:500; font-size:10.5px; text-transform:uppercase; letter-spacing:.5px; }
.err { color:var(--bad); font-family:ui-monospace,monospace; font-size:11.5px; white-space:pre-wrap; margin:4px 0 8px; }
.mut { color:var(--muted); }
footer { padding:14px 24px; color:var(--muted); font-size:11.5px; border-top:1px solid var(--line); margin-top:18px; }
</style></head><body>
<header><h1>Atlas POS-Ops <span class="mut">· cockpit</span></h1><div class="stamp" id="stamp">loading…</div></header>
<div id="tenants"></div>
<footer>Phase 0.5 · multi-tenant prototype · polls every 30 s · cockpit refreshes every 10 s · <span id="meta"></span></footer>
<script>
const EUR = n => "€" + (n||0).toFixed(2).replace(".",",");
const AGO = iso => { if(!iso) return "—"; const d=new Date(iso); const s=(Date.now()-d.getTime())/1000; if(s<90) return Math.round(s)+"s"; if(s<5400) return Math.round(s/60)+"m"; if(s<172800) return Math.round(s/3600)+"h"; return Math.round(s/86400)+"d"; };
const KB = n => n>=1024*1024 ? (n/1024/1024).toFixed(1)+" MB" : Math.round(n/1024)+" KB";

function dot(t){
  const c = t.cache; if(!c) return '<span class="dot stale" title="never polled"></span>';
  if(c.last_error) return '<span class="dot bad" title="'+c.last_error+'"></span>';
  if(!c.health?.db_reachable) return '<span class="dot bad" title="db"></span>';
  if(!c.health?.kassa_running) return '<span class="dot warn" title="kassa.exe off"></span>';
  return '<span class="dot ok"></span>';
}

function renderTerminal(t, color){
  const c = t.cache || {}, h = c.health || {}, d = c.day_totals || {}, j = c.journal?.rows || [];
  const m = t.mirror_last;
  const errBox = c.last_error ? `<div class="err">⚠ ${c.last_error}</div>` : "";
  const rows = j.slice(0,5).map(r => `<tr><td>${r.tijd?.slice(11,16)||""}</td><td>${r.tafel ?? r.klant ?? "—"}</td><td style="text-align:right">${EUR(r.bedrag_eur)}</td></tr>`).join("") || `<tr><td colspan="3" class="mut">(geen bestellingen vandaag)</td></tr>`;
  const mirrorRow = m
    ? `<div class="mirror"><span>laatste mirror <b>${AGO(m.received_at)}</b> geleden · ${KB(m.size_bytes)}</span><span class="mut" title="${m.sha256}">${m.sha256.slice(0,8)}…</span></div>`
    : `<div class="mirror"><span>geen mirror ontvangen</span></div>`;
  return `<div class="card" style="--accent:${color}">
    <h3>${dot(t)} ${t.node_id} <span class="mut" style="font-weight:400;font-size:12px">· ${t.label||""}</span></h3>
    <div class="sub">${h.hostname||"—"} · DB v${h.db_version??"?"} · agent ${h.agent_version||"?"} · uptime ${Math.round((h.uptime_s||0)/60)}m · gepoll'd ${AGO(c.polled_at)} geleden</div>
    ${errBox}
    <div class="kpi"><div><label>Vandaag</label><b>${EUR(d.total_eur)}</b></div><div><label>Cash</label><b>${EUR(d.cash_eur)}</b></div><div><label>Pin</label><b>${EUR(d.pin_eur)}</b></div></div>
    <table><thead><tr><th>tijd</th><th>tafel/klant</th><th style="text-align:right">bedrag</th></tr></thead><tbody>${rows}</tbody></table>
    ${mirrorRow}
  </div>`;
}

function renderTenant(c){
  const odoo = c.odoo_partner_id
    ? `<a class="odoo" href="https://192.0.2.10:8069/odoo/contacts/${c.odoo_partner_id}" target="_blank">Odoo #${c.odoo_partner_id} ↗</a>`
    : "";
  return `<section class="tenant">
    <h2><span class="name">${c.name}</span><span class="pill">${c.tier||"-"}</span><span class="mut">${c.terminals.length} terminal${c.terminals.length===1?"":"s"}</span>${odoo}</h2>
    <div class="grid">${c.terminals.map(t => renderTerminal(t, c.color||"#5cc8ff")).join("") || '<div class="mut" style="padding:8px">geen terminals</div>'}</div>
  </section>`;
}

async function tick(){
  try {
    const r = await fetch('/api/snapshot');
    if(!r.ok){ document.getElementById('stamp').textContent = "auth?"; return; }
    const d = await r.json();
    document.getElementById('tenants').innerHTML = d.customers.map(renderTenant).join("");
    document.getElementById('stamp').textContent = d.generated_at;
    const nTerm = d.customers.reduce((s,c)=>s+c.terminals.length,0);
    document.getElementById('meta').textContent = `${d.customers.length} customer(s) · ${nTerm} terminal(s)`;
  } catch(e){ document.getElementById('stamp').textContent = "fetch failed"; }
}
tick(); setInterval(tick, 10000);
</script></body></html>
"""


@app.get("/", response_class=HTMLResponse)
def cockpit(_=Depends(require_cockpit)):
    return COCKPIT_HTML


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8087, log_level="warning", access_log=False)
