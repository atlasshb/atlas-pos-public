# Atlas POS Program — Technical Architecture

**Twin / Mirror / Backup (capability B) + Per-client Odoo Community replacement (capability C)**

Status: design, ground-truth-aligned (no greenfield). Control plane = `pos-hub`.
Date: 2026-06-30. Owner: Atlas / Atlas Corporation (NL).

---

## 0. Scope and the one rule that shapes everything

This document is the technical architecture for two intertwined capabilities of the Atlas POS program:

- **(B) Twin / Mirror / Backup** — continuously and safely pull each client's live OptimumPOS MySQL up to `pos-hub` as a queryable read-twin plus versioned, encrypted, offsite backups.
- **(C) Replace** — stand up a per-client Odoo 19 Community POS and migrate the OptimumPOS data into it via an idempotent ETL, parallel-run, then cut over per client.

It covers: data flows, where each piece runs (containers, ports, volumes, networks), storage / retention / encryption, the `restic → Backblaze B2` backup tier, and the explicit **multi-DB-Odoo vs per-client-container** decision with rationale.

**THE RULE that constrains every box and arrow below:** client POS terminals are LIVE card-payment systems on intermittent home/shop internet. The ETL and all migration work read the **hub-side twin**, never the live terminal. The only thing that ever touches a terminal is capability B's read-only PULL, hub-initiated, per-site, in that client's quiet window. There is no fleet-wide automated sweep on live terminals — ever.

---

## 1. The big picture — end-to-end data flow

```
  CLIENT SITE (live, intermittent)                 TAILSCALE                 pos-hub  (always-on hub / single source of truth)
  ================================            (WireGuard mesh)              =====================================================

  +--------------------------------+                                       +-----------------------------------------------------+
  |  Windows POS terminal          |                                       |  HUB CONTROL PLANE                                   |
  |  - OptimumPOS (vendor app)     |                                       |                                                     |
  |  - local MySQL :3306           |          (B) read-only PULL           |  +-----------------------------------------------+  |
  |    products/categories/prices  | =============================>        |  | pos-mirror.sh (per-client, systemd timer)     |  |
  |    BTW/taxes/payments/tickets  |     tailnet IP : 3306                  |  |  reachability gate -> mysqldump -> twin load   |  |
  |  - Worldline YOMANI (card)     |     mysqldump --single-transaction    |  |  --single-transaction (read-only) -> restic    |  |
  |    STANDALONE - PAN never      |     read-only SELECT user             |  +----------------------+------------------------+  |
  |    enters MySQL/twin           |                                       |                         |                           |
  +--------------------------------+                                       |        atomic publish   v                           |
                                                                           |  +-------------------------------+                  |
  Venue A    venue-a-till  192.0.2.10 : 3306  (restaurant, live)     |  | dumps/<client>/*.sql.gz       |  versioned history |
  Venue B     venue-b-till      192.0.2.10  : 3306  (tailor, often off)   |  | + SHA256SUMS manifest         |                  |
  Venue C (not yet tailnet-enrolled)                                   |  +---------------+---------------+                  |
                                                                           |                  | load (drop+recreate)            |
                                                                           |                  v                                  |
                                                                           |  +-------------------------------+                  |
                                                                           |  | atlas-mariadb-<client>        |  queryable        |
                                                                           |  |  (per-client READ-TWIN)       |  read-twin        |
                                                                           |  +-------+---------------+-------+                  |
                                                                           |          |               |                          |
                                                          (C) ETL reads    |          |               | restic backup            |
                                                          the TWIN, never  |          v               v                          |
                                                          the terminal     |  +----------------------+   +-------------------+   |
                                                                           |  | optimumpos_to_odoo.py|   | restic -> B2      |   |
                                                                           |  | XML-RPC upsert       |   | per-client repo   |   |
                                                                           |  +----------+-----------+   +---------+---------+   |
                                                                           |          |  :8069               |                  |
                                                                           |          v                      |  encrypted,      |
                                                                           |  +-------------------------+     |  offsite         |
                                                                           |  | atlas-odoo (Odoo 19 CE) |     v                  |
                                                                           |  | multi-DB, one DB/client |   [ Backblaze B2 EU ]  |
                                                                           |  |  venue_b / venuea /... |                        |
                                                                           |  +-----------+-------------+                        |
                                                                           |              | SQL                                 |
                                                                           |              v                                     |
                                                                           |  +-------------------------+                       |
                                                                           |  | atlas-odoo-db (Postgres)|                       |
                                                                           |  +-------------------------+                       |
                                                                           +-----------------------------------------------------+
                                                                                          ^   ingress = Caddy (sole) :443
                                                                                          |   per-client vhost -> db-filter
                                                                              operator / client browsers (HTTPS)
```

**Reading the flow, left to right:**

1. **Terminal → Tailscale (B, read-only).** `scripts/pos-mirror.sh` on the hub connects over the tailnet to the terminal's MySQL `:3306` using a dedicated read-only account and runs `mysqldump --single-transaction`. WireGuard encrypts in transit. The terminal runs nothing of ours and is never written to.
2. **Tailscale → pos-hub dump archive.** The dump lands as a timestamped, gzipped, checksummed file under `clients/<client>/dumps/`. Atomic publish (`.partial` → final via `mv`) means there is never a half-written dump.
3. **Dump → twin.** The same `scripts/pos-mirror.sh` run drops and recreates `atlas-mariadb-<client>` from the dump it just took — an idempotent full refresh. (Pull and twin-load are one combined script; there is no separate load step.) This is the queryable read-twin: the hub's live view of the client's business context.
4. **Twin → Odoo (C, ETL).** `migration/optimumpos_to_odoo.py` reads the **twin** (never the terminal), transforms OptimumPOS entities to Odoo, and upserts over **XML-RPC** into that client's Postgres database inside the shared `atlas-odoo` container.
5. **Everything → B2.** `restic` encrypts and ships the dump tree (and pre-ETL `pg_dump`s) to a per-client Backblaze B2 repo for disaster recovery.

The two capabilities meet at exactly one place: the **twin is B's output and C's input**. That boundary is what keeps the risky migration work off the live card-payment box.

---

## 2. Where each piece runs — containers, ports, volumes, networks

Everything in this section runs on **`pos-hub`** (Ubuntu VPS; Tailscale `192.0.2.10`, public `<VPS-IP>`). Terminals host nothing of ours.

### 2.1 Container inventory (this program's additions + reused existing)

| Component | Container | Image | Listens | Reached by | Notes |
|---|---|---|---|---|---|
| Read-twin (per client) | `atlas-mariadb-<client>` e.g. `atlas-mariadb-venuea`, `atlas-mariadb-venue_b` | `mariadb:11` | `3306` (internal net only) | `pos-mirror.sh`, `optimumpos_to_odoo.py`, operator queries | One container per client. **No host port published** — internal Docker network only. |
| Odoo app (shared) | `atlas-odoo` (existing) | Odoo 19 Community | `8069` (http), `8072` (longpolling) | Caddy, `optimumpos_to_odoo.py` (XML-RPC) | Multi-DB; one Postgres DB per client. Venue B already lives here. |
| Odoo DB (shared) | `atlas-odoo-db` (existing) | `postgres:16` | `5432` (internal) | `atlas-odoo` only | Holds `venue_b`, `venuea`, `venue_c`, ... as separate databases. |
| Ingress | `caddy` (existing) | Caddy 2 | `443`/`80` (public) | Internet | **Sole** public ingress. Per-client vhost → Odoo with pinned `db-filter`. |
| Backup engine | run as job (not a long-lived container) | `restic` | — | systemd timers | Talks to B2 over TLS. |
| Verify sandbox | `atlas-mariadb-verify` (ephemeral) | `mariadb:11` | `3306` (internal, throwaway) | weekly verify timer | Spun up to restore-drill a dump, asserted, then destroyed. |
| Push / alerting | `atlas-ntfy` (existing) | ntfy | (existing) | freshness/backup jobs | `pos-terminals`, `pos-mirror`, `pos-backup` topics. |
| LLM gateway (optional, schema-mapping) | `litellm` (existing) | litellm | (existing) | ETL schema-map helper | Per-tenant keys; only for LLM-assisted mapping suggestions. |
| Automation (optional) | `atlas-n8n` (existing) | n8n | (existing) | cron flows | Pull scheduling / freshness / inventory writes if not pure systemd. |

### 2.2 Docker networks

- **`atlas-pos-twins`** (internal bridge, `internal: true` — no egress, no host ports): every `atlas-mariadb-<client>` and the verify sandbox attach here. The ETL worker (`optimumpos_to_odoo.py`) and `pos-mirror.sh`'s twin-load step reach the twins on this network by container name. **No twin MySQL port is ever published to the host or the internet** — twins are reachable only from inside the hub.
- **`atlas-core`** (existing bridge): `atlas-odoo` ↔ `atlas-odoo-db` ↔ `caddy`. The ETL worker also attaches here (or runs on the host) to reach Odoo's `:8069` for XML-RPC.
- **Tailscale** is the transport from the hub OUT to the terminals (host-level `tailscale0`), not a Docker network. The pull job runs on the host (or a host-network container) so it can use the tailnet directly.

Per-tenant isolation is enforced at three layers: a **separate twin container** per client, a **separate Postgres database** per client, and the internal-only network so no twin is reachable cross-tenant or publicly.

### 2.3 Volumes

| Volume / path | Holds | Backed up | Permissions |
|---|---|---|---|
| `/opt/atlas-pos/clients/<client>/dumps/` | versioned gzipped logical dumps + `SHA256SUMS` | yes (restic → B2) | dir `0700` |
| `/opt/atlas-pos/clients/<client>/env` | per-tenant flags + read-only MySQL creds (`MIRROR_ENABLED`, `DPA_SIGNED`, `QUIET_WINDOW`, `MYSQL_*`) | yes (separate locked B2 secrets path) | file **`0600`**, gitignored |
| `/opt/atlas-pos/clients/<client>/twin.pw` | generate-once twin (`atlas-mariadb-<client>`) root password, written by `pos-mirror.sh` | yes (locked B2 secrets path) | file **`0600`**, gitignored |
| `/opt/atlas-pos/clients/<client>/status.json` | last-run freshness/result (written atomically by `pos-mirror.sh`) | no (regenerated each run) | `0600` |
| `/opt/atlas-pos/clients/<client>/logs/` | per-run dump logs (`dump-<ts>.log`) | rotated locally | `0700` |
| named volume `atlas-twin-<client>` | the live twin datadir | no (twin is rebuildable from dumps) | docker-managed |
| existing Odoo PG volume | all per-client Odoo databases | yes (per-DB `pg_dump` → restic → B2) | docker-managed |
| `/opt/atlas-pos/registry.yml` | **non-secret** topology (IP, port, db, quiet-window, enabled) | yes (in git) | `0644` |

Key decision: the twin datadir is **not** backed up directly — it is disposable and always reconstructable from the latest dump. We back up the **dumps** (the immutable point-in-time history) and the Odoo **`pg_dump`s**. This keeps the backup set small and the restore path unambiguous.

### 2.4 On-disk layout (the working tree, moved by git)

This is the actual shipped tree (the git repo at `/opt/atlas-pos`, staged on the VPS):

```
/opt/atlas-pos/                 # the program git repo (this tree)
  ARCHITECTURE.md PROGRAM.md ROADMAP.md PREP-RUNBOOK.md   # docs; IN GIT
  registry.yml                # non-secret topology; IN GIT (created from the template)
  scripts/
    fleet-inventory.sh        # capability A: read-only tailnet discovery + inventory
    pos-mirror.sh             # capability B: COMBINED pull + twin-load + restic (per client)
    pos-verify.sh             # capability B: weekly restore-drill (restore newest dump, assert)
    odoo-provision-client.sh  # capability C: build a per-client Odoo 19 CE POS DB + module
  migration/
    optimumpos_to_odoo.py     # capability C: twin -> Odoo XML-RPC upsert (idempotent ETL)
    MAPPING.md                # OptimumPOS -> Odoo entity/field map
  governance/
    INTEGRATION.md            # Mind gate / policy.json / GDPR / ntfy topics
  systemd/
    pos-mirror@.service       # ExecStart=/opt/atlas-pos/scripts/pos-mirror.sh %i
    pos-mirror@.timer         # per-client quiet-window + opportunistic catch-up
  clients/                    # RUNTIME state, created per client (secrets gitignored)
    _TEMPLATE/env.example     # copy to clients/<client>/env, then chmod 600 + fill in
    venue_a/
      env                     # 0600, gitignored: the ONE per-client secrets file
                              #   (MIRROR_ENABLED/DPA_SIGNED/QUIET_WINDOW, MYSQL_*, RESTIC_*,
                              #    B2_*, and the ETL's TWIN_MYSQL_*/ODOO_* — both halves share it)
      twin.pw                 # 0600, gitignored  (generate-once twin root pw)
      status.json  dumps/  logs/
    venue_b/
      env  twin.pw  status.json  dumps/  logs/
    venue_c/              # inert until tailnet-enrolled + DPA signed
  state/
    fleet-inventory.json      # written by fleet-inventory.sh
  runbooks/
    create-readonly-mysql-user.sql   # the L1 read-only MySQL user (run once per terminal)
    create-readonly-mysql-user.md    # how/when to run it + read-only verification
  clients/<client>.yml        # capability C per-client descriptor: db, company, lang,
                              #   country, btw_rate_default, kvk, btw, pos_name, module
```

Related dirs on pos-hub referenced by the scripts (outside this git repo): `/root/odoo_migration/addons/` holds the generated `atlas_<client>_pos` modules (template `atlas_pos_seed`), and `/root/pos_kb/` holds the canonical OptimumPOS schema map.

`registry.yml` (topology) is in git. `clients/<client>/env` (the single per-client secrets file, shared by the mirror and the ETL) and `clients/<client>/twin.pw` are `0600` and gitignored. Code moves by git; secrets are never committed and never bulk-copied to terminals.

---

## 3. Capability B — Twin / Mirror / Backup, in detail

### 3.1 Mechanism: scheduled logical dump, NOT replica / binlog CDC

Decision: the primary mirror mechanism is **`mysqldump --single-transaction`**, a scheduled read-only logical dump. Rejected alternatives and why:

- **MySQL replica (source→replica):** requires enabling binlog + a replication user + GTID on each LIVE, vendor-owned OptimumPOS box, and a replica that must reconnect cleanly after every power-off. Intrusive config change to a live payment system; fragile across constant power cycles. **Rejected.**
- **Binlog / CDC (Debezium, maxwell):** same binlog prerequisite on the live box, plus a stateful connector that breaks across power cycles and needs binlog retention the box may not have. Overkill at this data scale. **Rejected.**
- **Scheduled `mysqldump --single-transaction` (chosen):** read-only, **zero server-config change** on the live box, consistent point-in-time snapshot on InnoDB, naturally idempotent, trivially resumable after an outage (just run the next window). POS DBs at this scale (products, categories, prices, BTW, payment methods, tickets, staff) are small — full logical dumps are cheap and bulletproof.

We add binlog-based incremental only later, per-client, if a specific client's ticket volume makes full dumps too heavy — and only with that client's go.

### 3.2 The mirror job (concrete)

The shipped script is `scripts/pos-mirror.sh <client>`, driven by `registry.yml` + the per-client
`clients/<client>/env`. Pull, twin-load, and restic backup are **one combined script** (there is no
separate `pos_load_twin.sh`). It additionally enforces a mechanical fail-closed gate
(`MIRROR_ENABLED=1`, `DPA_SIGNED=1`, optional `QUIET_WINDOW`) and a tailnet-IP assertion before it
will connect. The skeleton below is what it does:

```sh
set -euo pipefail
C="$1"; source /opt/atlas-pos/clients/$C/env   # MIRROR_ENABLED DPA_SIGNED QUIET_WINDOW MYSQL_HOST/USER/PW/DB

# 0. fail-closed gate — refuse (clean skip) unless explicitly enabled + DPA on file + in window
[ "${MIRROR_ENABLED:-0}" = 1 ] || { echo "$C not enabled, skip"; exit 0; }
[ "${DPA_SIGNED:-0}"     = 1 ] || { echo "$C no DPA, skip";     exit 0; }
# (tailnet-IP assertion: MYSQL_HOST must be in 100.64.0.0/10, else refuse)

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=/opt/atlas-pos/clients/$C/dumps/$C-$TS.sql.gz

# 1. reachability gate — terminal-off is a CLEAN SKIP, not a failure
tailscale ping -c1 --timeout 5s "$MYSQL_HOST" >/dev/null 2>&1 || { echo "$C offline, skip"; exit 0; }
mysqladmin --defaults-extra-file="$cnf" ping  >/dev/null 2>&1 || { echo "$C MySQL down, skip"; exit 0; }

# 2. consistent, READ-ONLY logical dump (never locks the live POS)
mysqldump --defaults-extra-file="$cnf" \
   --single-transaction --quick --routines --triggers --events \
   --set-gtid-purged=OFF --no-tablespaces --skip-lock-tables \
   "$MYSQL_DB" | gzip > "$OUT.partial"
mv "$OUT.partial" "$OUT"                         # atomic publish; never a half-file

# 3. checksum + manifest
sha256sum "$OUT" >> /opt/atlas-pos/clients/$C/dumps/SHA256SUMS

# 4. refresh the queryable twin from this dump (same script: drop+recreate atlas-mariadb-$C)
#    twin root pw is generate-once and persisted in clients/$C/twin.pw (chmod 600)

# 5. encrypted offsite backup of this client's dump tree
restic -r b2:atlas-pos-backups:/$C backup /opt/atlas-pos/clients/$C/dumps
```

Critical flags: `--single-transaction` (consistent InnoDB snapshot, no write lock), `--skip-lock-tables` (do NOT lock the live POS), `--quick` (stream rows). The MySQL user is a dedicated read-only account (`GRANT SELECT, SHOW VIEW, TRIGGER, EVENT`) so the mirror **physically cannot mutate** the live box.

> **Engine caveat (verify per site):** `--single-transaction` only gives a consistent snapshot for **InnoDB**. If a terminal's OptimumPOS uses **MyISAM**, those tables are non-transactional; with `--skip-lock-tables` they could be read mid-write. Detect the engine per table on first inspection; for any MyISAM table, run the dump only inside the closed-hours quiet window (when there are no writes) so eventual consistency is exact.

### 3.3 Scheduling — systemd timers + quiet windows

Per-client templated units, fired in that client's quiet window — never a fleet-wide sweep:

```
systemd/pos-mirror@.service   ExecStart=/opt/atlas-pos/scripts/pos-mirror.sh %i
systemd/pos-mirror@.timer      OnCalendar=<per client>, Persistent=true, RandomizedDelaySec=...
   (installed to /etc/systemd/system/, e.g. via systemctl link or a copy from the repo)

systemctl enable --now pos-mirror@venue_a.timer   # e.g. OnCalendar=*-*-* 03:30 (restaurant closed)
systemctl enable --now pos-mirror@venue_b.timer    # Persistent=true; fires on next boot if missed
```

`Persistent=true` + the reachability gate makes "terminal off" fully handled: a missed quiet-window run fires as soon as the box next appears, and a still-off box exits 0 cleanly. An **opportunistic every-30-min catch-up timer** also runs each client, but proceeds only if the box is reachable AND the last successful dump is older than the target interval — so a box that is only on during business hours still gets mirrored even though it is never on at 03:30.

### 3.4 Storage, retention, encryption — restic → B2

- **Versioning:** every dump is a timestamped immutable file. The twin is "latest"; `dumps/` is the history.
- **Retention (restic policy, run after each backup):** `--keep-last 14 --keep-daily 14 --keep-weekly 8 --keep-monthly 12`, then `restic forget --prune`. Local `dumps/` pruned to the last ~14 to bound hub disk; B2 holds the long tail. **Fiscal split:** NL `Belastingdienst` requires 7-year retention for fiscal records — operational snapshots rotate short (90d point-in-time), with monthly archival snapshots kept to satisfy the 7-year fiscal obligation.
- **Encryption at rest:** restic repos are encrypted by design. **Per-client repo** `b2:atlas-pos-backups:/<client>` with a **per-tenant repo password** — per-tenant isolation extends into the backup tier; a breach is contained to one client.
- **Encryption in transit:** Tailscale / WireGuard hub↔terminal; TLS hub↔B2. Prefer the **EU B2 region** for GDPR data residency.
- **Integrity / proof of restorability:** sha256 manifest at dump time, plus a **weekly verify timer** running `scripts/pos-verify.sh` that does (a) `restic check --read-data-subset=10%` per repo and (b) a **restore drill** — restore the newest dump into the throwaway `atlas-mariadb-verify` container and assert row counts on key tables (products, sales/tickets) are non-zero and within expected delta of the live twin. A backup that can't be restored is not a backup; this drill is the proof.

### 3.5 Querying live business context from the hub

1. **Direct twin query:** `docker exec atlas-mariadb-venuea mysql -e "SELECT ... FROM products"`. Each twin is a real, refreshed MySQL.
2. **Consolidated read layer (optional, later):** a small DuckDB/Metabase on the hub attaching all twins read-only for cross-client questions ("today's catalog + prices per client", "which clients still on OptimumPOS"). Fed from twins, never from live boxes. Deferred until twins are live for ≥2 clients.
3. **Freshness surfacing:** each `pos-mirror.sh` run writes last-success timestamp + a table/row-count sample to `clients/<client>/status.json` (atomically); `atlas-ntfy` (topic `pos-mirror`) pushes if any client's twin goes stale beyond threshold (e.g. >48h), so the operator knows a terminal has been off too long.

---

## 4. Capability C — Per-client Odoo Community replacement

### 4.1 Architecture decision: ONE multi-DB Odoo, database-per-client — NOT a container per client

**Decision: run the replacement on the EXISTING `atlas-odoo` container as one multi-DB Odoo 19 with a Postgres database per client (`venue_b`, `venuea`, `venue_c`, ...). Do NOT run a separate Odoo container per client.**

The `venue_b` database already runs exactly this pattern on `atlas-odoo` `:8069`, so this is the **proven path, not a new invention**.

**Rationale — why database-per-client wins here:**

| Dimension | Multi-DB (one Odoo, DB-per-client) — CHOSEN | Container-per-client — rejected as default |
|---|---|---|
| Tenant isolation | Postgres-DB boundary already gives separate CoA, users, `pos.config`, and per-DB `pg_dump` backups. Satisfies the hard per-tenant-isolation constraint. | Process-level isolation, but unnecessary for tiny single-till clients. |
| Cost / RAM | Near-zero marginal cost. One image, one worker/gunicorn set shared. Fits intermittent, tiny clients. | N × RAM (each Odoo its own worker set + gunicorn). Wasteful at this scale. |
| Upgrade surface | **One** image to patch, **one** upgrade run. | N upgrade runs, N chances for version drift. |
| Backup | Per-DB `pg_dump` → one restic flow. | N restic targets. |
| Ingress | One Caddy backend; per-client vhost pins `db-filter`. | N Caddy backends. |
| Blast radius | Contained at the DB boundary; staged rollout + per-DB `pg_dump` pre-change limit a bad migration. | Smaller per-client blast radius — the one genuine advantage. |

There is **no scale pressure** (single-till clients on intermittent hardware) that justifies hard process isolation. DB-per-DB already satisfies per-tenant isolation, encrypted at rest via the host volume + restic → B2.

**Container-per-client is kept in reserve** for the one case it is actually warranted: a client that needs a **conflicting Odoo version** or a **custom OCA module set** that would destabilize the shared image. That is the documented escape hatch, not the default.

**Isolation enforcement:** disable the DB selector and pin each client URL to exactly one database. Either run Odoo with `--db-filter=^%h$` and a host-per-client, or have Caddy reverse-proxy each subdomain to `/web?db=<client>`. A bad ETL or upgrade on one client cannot reach another's accounting.

### 4.2 Per-client module — generated from the proven Venue B template

Each client gets `atlas_<client>_pos`, cloned from the hard-won `atlas_pos_seed` template. The template's correctness is kept verbatim:

- product `type ∈ {consu, service, combo}` (no `detailed_type`); `pos_categ_ids` is M2M (plural); `available_in_pos = True`; `taxes_id` **omitted** so products inherit the company 21% BTW default.
- payment methods created with `noupdate="1"`, journals linked by **SEARCH(company_id, type)** in `post_init_hook`.
- UI language activated via `res.lang._activate_lang` (NOT the broken legacy `base.language.install` XML).
- **No `pos_six` / `pos_adyen` / `pos_iot` anywhere** — these are Enterprise-only and would make a Community install fail.
- `l10n_nl` + default-tax confirmation are documented **MANUAL** steps.

**Parameterized per client** via `generator/clients/<client>.yml` (technical name, company name, receipt header/footer with KvK/BTW, **UI language as a per-client flag** — Venue B `tr_TR`; Venue A / Venue C likely `nl_NL` only — seed catalogue, `pos.config` name). Adding a client = editing one YAML, not hand-writing XML. The module ships only a SMALL hand-curated seed (so a bare install is demoable); the REAL catalogue comes from the ETL, reconciled by stable keys so the two never duplicate.

### 4.3 ETL — OptimumPOS (via the twin) → Odoo 19, idempotent

- **SOURCE = the read-twin on `pos-hub` (capability B), NOT the live terminal.** This is the single most important safety rule of capability C: the ETL hits a hub-side mirror, so an ETL bug can never lock tables or slow a live card-payment terminal, and the ETL runs **any time** (no quiet window needed — it does not touch the client).
- **TRANSPORT into Odoo = XML-RPC** (`button_immediate_install/upgrade`, `search`/`create`/`write`, journal-by-SEARCH), proven in the template's `setup_via_xmlrpc.py`. No filesystem access to live Odoo needed; works over the tailnet to `:8069`.
- **IDEMPOTENCY:** every migrated record carries a stable source key — product `default_code = OPT-<sourcePK>` (or a dedicated `x_optimum_id`). The ETL upserts: search by key → write (refresh only safe fields) or create. Re-running converges and never duplicates. Human-edited prices in Odoo are NOT clobbered on re-run (only name/category/availability re-asserted).

**Entity mapping (OptimumPOS MySQL → Odoo 19):**

| OptimumPOS | Odoo 19 | Notes |
|---|---|---|
| product / article | `product.template` | `type=consu` (goods) / `service` (labour); `available_in_pos=True`; `default_code=OPT-<pk>`; `list_price` from source. |
| product category | `pos.category` (+ `product.category` internal) | mapped by name + source key. |
| price | `product.template.list_price` | Odoo `list_price` is tax-**exclusive**. **If OptimumPOS stores tax-inclusive prices, convert** `list_price = gross / (1 + rate)` and set the matching tax. **Verify inclusive/exclusive per site.** |
| BTW rate | company `account.tax` | map by RATE via SEARCH on the company's `l10n_nl` taxes (21% → "21% BTW", 9%, 0%). **Never a hardcoded `l10n_nl` xmlid** (they are per-company). Set `taxes_id` only when the product's rate differs from the company default. |
| payment method | `pos.payment.method` | Cash → `type=cash`; **every** card / pin / Worldline variant → ONE manual "Pinnen / Worldline kaart" bank method (`use_payment_terminal` unset). No integrated terminal methods. |
| staff / cashier | `hr.employee` (recommended) | map names for attribution; **do NOT bulk-import logins** (secrets/PII constraint, GDPR). |
| open orders / parked tickets | `pos.order` + `pos.order.line` | ONLY currently-open tickets at cutover, ONLY if the client wants them. **Default = skip** (start the till clean). |

**Historical sales: DEFAULT = archive-in-twin only, NOT replayed into `pos.order`.** Replaying closed tickets would fabricate `pos.session` / `account.move` journal entries in the live Dutch CoA — a fiscal hazard and a violation of "don't touch accounting". The twin is already the queryable system-of-record + DR for history. An OPT-IN history import can load sales as a read-only reporting dataset (`x_optimum_sale` model or CSV→BI), separate from accounting, if a client needs trend reports inside Odoo.

**Validation (the ETL must prove itself):** after each run, compute and assert against the twin — `#products migrated == #active source articles`; each `pos.category` non-empty; every `available_in_pos` product resolves to a known BTW rate; a money check (Σ `list_price` sampled vs source). Emit a per-client reconciliation report (counts, mismatches, unmapped categories/taxes) to ntfy / the Mind ledger. **A non-empty mismatch list blocks cutover.**

### 4.4 Localization and hardware

- **Dutch BTW everywhere** (business is NL). **Turkish is UI-only and per-client** (Venue B yes; others probably `nl_NL`). `l10n_nl` install + default-tax = documented manual step, confirmed **before the first posted journal entry** (Odoo 19 forbids changing the fiscal package after a posted entry).
- **Worldline YOMANI = standalone → MANUAL card `pos.payment.method`.** The cashier runs the physical terminal; Odoo records the tendered amount. **PAN never enters OptimumPOS or the twin** — this keeps Atlas out of PCI-DSS scope. No IoT/ePOS terminal integration (Community can't).
- **Receipt printer = browser/PDF baseline** (any Windows printer, zero config, unbreakable on a blind build). ePOS direct-print (`other_devices` + `epson_printer_ip` + trusted self-signed cert) is a documented **per-site on-site** step, never scripted blind.

### 4.5 Cutover and rollback (per client)

```
 1. B mirrors terminal -> twin is fresh (mandatory pre-cutover refresh + final diff).
 2. Generate atlas_<client>_pos, install on the client DB.
 3. Run ETL from twin -> Odoo (XML-RPC), validate totals (gate).
 4. PARALLEL RUN: new Odoo till open ALONGSIDE live OptimumPOS; OptimumPOS stays system of record.
    Reconcile end-of-day Z-totals both ways for a real business cycle (>=14 days incl. a weekend).
 5. On the client's explicit go, in a quiet window: final delta ETL -> set Odoo as system of record
    -> switch the terminal's default till to Odoo. Worldline standalone => card flow unaffected.
 6. WATCH first full trading day; then DECOMMISSION only after a clean week: archive final OptimumPOS
    dump to B2, retire OptimumPOS, repurpose that client's puller to back up the new Odoo DB.
```

**Rollback is clean at every step:** the client keeps running OptimumPOS until step 5; a pre-ETL `pg_dump` is taken so a wrong Odoo DB can be dropped/restored; nothing on the live terminal is ever modified, and card payments never depend on the switch (standalone Worldline). Decommission is the only point of no easy return — gated on a clean trading week + final archive + client sign-off.

---

## 5. End-to-end worked example — "mirror Venue A tonight, migrate tomorrow"

```
03:30  systemd fires pos-mirror@venue_a  ->  scripts/pos-mirror.sh venue_a
       -> gate OK (MIRROR_ENABLED=1, DPA_SIGNED=1, in QUIET_WINDOW, tailnet IP)
       -> tailscale ping 192.0.2.10 OK -> mysqladmin ping OK
       -> mysqldump --single-transaction (read-only) over WireGuard
       -> clients/venue_a/dumps/venue_a-20260701T013000Z.sql.gz  (atomic publish)
       -> sha256 appended to SHA256SUMS
       -> same script: drop+recreate atlas-mariadb-venue_a from this dump (twin.pw)
       -> restic -r b2:atlas-pos-backups:/venue_a backup dumps/   (encrypted, EU region)
       -> clients/venue_a/status.json updated; freshness OK -> no ntfy
       Zero human touches, zero terminal writes, fully reversible.

daytime  migration/optimumpos_to_odoo.py --client venue_a  (reads the TWIN, never the terminal)
       -> XML-RPC into Odoo db 'venuea': upsert products by OPT-<pk>, map BTW by rate,
          one manual Worldline card method, hr.employee for cashiers
       -> reconciliation report -> ntfy / Mind ledger.  Mismatch list empty => cutover-eligible.
```

A **cutover** for Venue A, by contrast, is L1: it stops at the Mind gate, pushes an approve button to Atlas's phone, and refuses to fire outside the restaurant's declared closed hours even after approval.

---

## 6. Ports / endpoints quick reference

| Where | Port | Exposure | Purpose |
|---|---|---|---|
| Terminal MySQL | `3306` | tailnet only (never public) | read-only source for the pull |
| Terminal SMB | `445` | tailnet only | discovery/inventory only |
| `atlas-odoo` | `8069` / `8072` | internal + via Caddy `443` | Odoo web + XML-RPC |
| `atlas-odoo-db` | `5432` | internal only | Odoo Postgres |
| `atlas-mariadb-<client>` | `3306` | **internal Docker net only** (no host port) | queryable twin |
| Caddy | `443` / `80` | **sole** public ingress | per-client vhost → db-filter |
| Tailscale (hub) | `192.0.2.10` | tailnet | transport hub↔terminals |
| B2 | `443` (TLS) | egress | encrypted offsite backups |

---

## 7. Open items that pin this architecture down per site

- Exact **quiet window** (closed hours) per client for the pull `OnCalendar` and for cutover.
- **MySQL engine + version** per OptimumPOS instance (InnoDB vs MyISAM) and TLS support — decides whether `--single-transaction` suffices or per-table locking in the closed window is needed.
- **Tax-inclusive vs tax-exclusive** pricing in OptimumPOS per site — decides the ETL price conversion and `taxes_id` handling.
- The actual **OptimumPOS schema** (table/column names) — the entity map above is by role; exact columns must be pinned against the real twin schema before the ETL is trusted (reverse-engineer once into `/root/pos_kb`).
- **Tailnet enrollment** of Venue C and other unenrolled clients — capability B is blocked on it; capability C is blocked on B.
- **Venue B adoption:** how much is already migrated in db `venue_b`, and whether to adopt or reset it as the template instance.
- Whether to build the **consolidated cross-client read layer** now or defer until ≥2 twins are live.

---

## Appendix A — Design invariants (the constraints every box above respects)

1. Client POS terminals are LIVE card-payment systems → any terminal touch is per-site, with that client's explicit go, in a quiet window. **Never a fleet-wide automated sweep on live terminals.**
2. Terminals are intermittent / powered off often → design for offline: reachability gate, `Persistent=true`, opportunistic staleness-gated catch-up.
3. Additive, idempotent, reversible. Parallel-run (old + new) before any cutover. Always have rollback.
4. Code moves by git; secrets never bulk-copied; per-tenant isolation (twin container + Postgres DB + B2 repo + repo password); encrypted at rest + in transit.
5. Odoo **Community**: integrated payment-terminal modules (`pos_six`/`pos_adyen`) are Enterprise-only → Worldline is a **manual** card method. Business is NL → Dutch BTW, not `l10n_tr`.
6. **Tailscale is the sole transport** between hub and terminals; MySQL/RDP are never publicly exposed.
