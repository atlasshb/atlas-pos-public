# Atlas POS Program — Master Document

**Owner:** Atlas, Atlas Corporation (NL)
**Control plane:** pos-hub (always-on Ubuntu VPS — Tailscale `192.0.2.10`, public `<VPS-IP>`)
**Status:** Active program. Venue B migration in progress; Venue A and others queued.
**Last updated:** 2026-06-30

> ## ‼️ CURRENT PHASE = PREPARATION + TESTING ONLY
> Operator standing rule (2026-06-30): **NO cutover, NO go-live, NO stopping/replacing any live OptimumPOS,
> NO real payment processing — until explicit, per-client consent in a quiet window.**
> Allowed now: read-only mirror/twin/backup, building per-client Odoo, ETL into **staging** DBs (`--dry-run`
> first), and config validation. Every cutover step in the ROADMAP is FROZEN behind that consent gate.

---

## 1. Goal

Replace the incumbent commercial Windows POS ("OptimumPOS") across every Atlas hospitality/retail
client with an **Atlas-owned Odoo 19 Community POS**, while continuously mirroring each client's live
business data up to the VPS as a queryable twin and disaster-recovery backup.

In one line: **discover every client POS, twin it to the hub, then replace it with Odoo — client by
client, safely, reversibly.**

End state, per client:
- The client runs an Atlas-operated Odoo Community POS (Dutch BTW, manual Worldline card method).
- OptimumPOS is retired.
- pos-hub holds a live read-twin + encrypted offsite backups of that client's business data.

---

## 2. Vision

Today each client's business reality lives trapped inside a vendor-owned MySQL database on a single
Windows terminal in a shop — invisible to Atlas, un-backed-up, and locked to a POS Atlas does not
control. That is operationally fragile (one dead PC = the shop's catalog and sales history gone) and
strategically dead-ended (no leverage to improve, automate, or consolidate).

The program turns that around:

- **pos-hub becomes the brain.** Every client's live catalog, prices, BTW, payment methods and sales
  context is mirrored to the hub, queryable from one place, backed up offsite, encrypted per tenant.
  Even a client who never migrates gets real disaster recovery out of this.
- **Atlas owns the POS.** Migrating each client onto Odoo Community puts the till, the catalog, the
  tax setup and the receipts under Atlas control — one image, one upgrade surface, per-client
  isolation at the database boundary.
- **Nothing is greenfield.** This is built *on top of* the stack already running on pos-hub
  (Odoo 19, restic→B2, Tailscale, Caddy, ntfy, n8n, the Mind approval/ledger). We extend what exists;
  we do not reinvent it.

---

## 3. Principles (non-negotiable)

These are the hard constraints. A design that violates any of them is wrong.

1. **Live terminals are sacred.** Client POS boxes are LIVE card-payment systems. Anything that
   touches one is per-site, with that client's explicit go, inside a **quiet window** (closed hours).
   **Never a fleet-wide automated sweep on live terminals.**
2. **Design for offline.** Terminals power off often and sit on home/shop internet. Intermittency is
   the normal case, not an error: a pull that finds a box down simply skips and retries.
3. **Additive, idempotent, reversible.** Every action can re-run without harm and be undone.
   Parallel-run (old + new together) before any cutover. Always have a rollback path.
4. **Per-tenant isolation, secrets never bulk-copied.** Code moves by git; secrets are issued at the
   hub and scoped down, never `scp`-ed between sites. One blast radius per client — separate twin DB,
   Odoo DB, vault namespace, and B2 repo.
5. **Encrypted at rest and in transit.** Tailscale/WireGuard hub↔terminal; restic-encrypted B2;
   per-tenant repo passwords.
6. **Community reality.** Odoo Community has **no** integrated payment-terminal modules
   (`pos_six`/`pos_adyen` are Enterprise-only). The standalone Worldline Yomani is a **manual** card
   payment method. The business is NL → Dutch BTW (`l10n_nl`), never `l10n_tr` (Turkish is UI-only,
   per-client).
7. **Tailscale is the only transport.** MySQL `:3306` / RDP / Odoo `:8069` are reachable on the
   tailnet, never publicly exposed.
8. **Governed by the Mind gate.** Every action is an *intent* classified L0 (auto, read-only/off-
   terminal) or L1 (human-approved: anything touching a live terminal, money, or cutover), recorded
   in the append-only ledger.

---

## 4. The Three Capabilities

The program is three intertwined capabilities, run per client.

### A. Discover + Inventory
Find every client and every POS terminal in the fleet — including sites not yet on the tailnet.
- Read-only, network-level only. Probe `:3306` / `:445` / `:8069` reachability over the tailnet.
- For unenrolled sites (Venue C and likely others), this is a **consent + hardware** step:
  the operator/client agrees to install Tailscale during a visit or remote-assisted session — never
  a network sweep.
- Output: one git-versioned inventory record per client (tailnet node/IP, OptimumPOS version, MySQL
  endpoint, quiet window, hardware models, BTW registration, migration phase).

### B. Twin / Mirror / Backup — the safety spine
Continuously and read-only pull each client's OptimumPOS MySQL up to pos-hub.
- **Mechanism:** scheduled logical `mysqldump --single-transaction` (read-only, no server-config
  change on the live box, consistent InnoDB snapshot, naturally idempotent, trivially resumable after
  a power-off). **Not** a MySQL replica and **not** binlog/CDC — both require intrusive config on a
  live, intermittent, vendor-owned payment box.
- **Hub-initiated PULL** over Tailscale. Terminals run nothing. A box that's down is a clean skip.
- **Per-client isolated twin:** each client gets its own `atlas-mariadb-<client>` container holding
  the queryable read-twin, refreshed from the latest dump. Plus a versioned dump archive.
- **restic → Backblaze B2**, per-client encrypted repos with per-tenant passwords. Retention policy +
  weekly **restore-drill** (a backup you have never restored is not a backup).
- Runs continuously from day one — immediate DR value, and it lets all the risky ETL/parallel-run
  work happen against the hub-side twin instead of the live terminal.

### C. Replace — per-client Odoo Community POS + ETL
Stand up the replacement and migrate the data.
- **One multi-DB Odoo, database-per-client** on the existing `atlas-odoo` container — not a container
  per client. Venue B already proves this (db `venue_b` on `:8069`). The Postgres-DB boundary gives
  per-tenant isolation (separate CoA, users, `pos.config`, backups) at near-zero marginal cost.
- **Per-client module** generated from the proven `atlas_pos_seed` template via a `clients/<client>.yml`
  (name, UI language, KvK/BTW, receipt text, seed catalogue). UI language is a per-client flag
  (Venue B = `tr_TR`; Venue A / Venue C likely `nl_NL` only).
- **Idempotent ETL** reads **the twin** (capability B), never the live terminal. XML-RPC into Odoo,
  upserting by a stable `OPT-<sourcePK>` key so re-runs converge and never duplicate. Maps catalog →
  `product.template`, categories → `pos.category`, prices → `list_price`, BTW rates → the company's
  `account.tax` by rate, payment methods → one manual "Pinnen / Worldline" `pos.payment.method`.
- **Historical sales are archived in the twin, NOT replayed** into `pos.order`/`account.move`
  (replaying would fabricate journal entries in the live Dutch CoA — a fiscal hazard). Only currently-
  open/parked tickets are optionally migrated; default is to start the till clean.
- **Validation gate:** every ETL run emits a reconciliation report (product counts, price sums, tax
  totals, unmapped categories). A non-empty mismatch list blocks cutover.

---

## 5. High-Level Architecture

```
                        ┌────────────────────────── pos-hub (the hub / control plane) ──────────────────────────┐
                        │                                                                                          │
  CLIENT SITES          │   GOVERNANCE            CAPABILITY B (twin)        CAPABILITY C (replace)                │
  (Tailscale tailnet)   │   ┌──────────────┐      ┌──────────────────┐       ┌───────────────────────────┐        │
                        │   │ Mind gate    │      │ pos-mirror.sh    │       │ atlas-odoo (Odoo 19 CE)    │        │
  Venue A   ──┐        │   │ + policy.json│      │  (per-client)    │       │  db: venue_b / venuea /   │        │
  192.0.2.10 │  PULL  │   │ L0 / L1      │◄────►│ atlas-mariadb-   │──ETL─►│      venue_c / ...     │        │
  MySQL :3306  ├───────►│   │ + ledger     │      │  <client> twins  │ (XML  │  atlas_<client>_pos module │        │
                        │   └──────┬───────┘      └────────┬─────────┘  RPC) │  (from venue_b template)   │        │
  Venue B   ──┤  (read- │          │                       │                  └────────────┬──────────────┘        │
  192.0.2.10 │  only, │   ┌──────▼───────┐      ┌────────▼─────────┐                     │                       │
  MySQL :3306  │  quiet │   │ atlas-ntfy   │      │ restic → B2       │       ┌────────────▼──────────────┐        │
  (+Odoo:8069) │  window│   │ pos-terminals│      │ per-client repos  │       │ Caddy (sole ingress)      │        │
                        │   │ pos-mirror   │      │ + restore-drill   │       │  per-client vhost/db-filter│        │
  Venue C ─┘        │   │ pos-backup   │      └───────────────────┘       └───────────────────────────┘        │
  (not yet enrolled)    │   └──────────────┘                                                                       │
                        │   n8n (scheduling/heartbeat)   litellm (LLM cost gw)   langfuse (trace)   fleet.yaml     │
                        └──────────────────────────────────────────────────────────────────────────────────────┘
```

**Flow of a routine mirror (L0, no human):** n8n cron emits a `mirror/pull <client>` intent → Mind
gate classifies L0 → `scripts/pos-mirror.sh <client>` checks the fail-closed gate
(`MIRROR_ENABLED`/`DPA_SIGNED`/`QUIET_WINDOW`) + reachability (terminal off = clean skip) → read-only
`mysqldump` over Tailscale → atomic publish + sha256 → refresh `atlas-mariadb-<client>` twin → restic
to B2 → ledger append → `fleet.yaml.last_pull` updated. Zero human touches, zero terminal writes,
fully reversible.

**Flow of a cutover (L1, human + quiet window):** the same intent path stops at the gate as L1, refuses
to fire outside the client's declared closed hours, and pushes an approve/deny button to Atlas's phone
via ntfy. The tap is itself a ledger-signed event. Card payments never depend on the switch (standalone
Worldline), so any rollback leaves payments working.

---

## 6. How It Fits pos-hub

The program reuses, not replaces, what is already running:

| Existing on pos-hub | Role in the POS program |
|---|---|
| `atlas-odoo` + `atlas-odoo-db` (Odoo 19 CE) | Multi-DB host: one Postgres DB per client (venue_b already live) |
| restic → Backblaze B2 | Per-client encrypted backup repos + weekly restore-drill |
| Tailscale (`192.0.2.10`) | Sole transport hub↔terminal; no public MySQL/RDP exposure |
| Caddy (sole ingress) | Per-client vhost pinning each client URL to its own Odoo DB |
| atlas-ntfy | Push alerts: terminal up/down, twin freshness, backup result; actionable L1 approvals |
| atlas-n8n | Cron scheduling, reachability/heartbeat, freshness computation, inventory writes |
| Mind approval/ledger + `policy.json` | L0/L1 classification, quiet-window enforcement, append-only audit |
| litellm (per-tenant keys) | LLM-assisted schema mapping (cost-controlled, per tenant) |
| langfuse | Tracing/audit of LLM-assisted steps |
| `/root/{atlaspos,posops,pos_kb,odoo_migration,odoo_sync,venuec}` | The program's working tree (populated via git, not ad-hoc copies) |

**Working-tree layout (as shipped):**
```
/opt/atlas-pos/                        # the program git repo
  registry.yml | fleet.yaml          # non-secret client topology + living fleet record (git)
  scripts/fleet-inventory.sh         # capability A: read-only discovery + inventory
  scripts/pos-mirror.sh              # capability B: COMBINED pull + twin-load + restic (per client)
  scripts/pos-verify.sh              # capability B: weekly restore-drill
  scripts/odoo-provision-client.sh   # capability C: build per-client Odoo DB + module
  migration/optimumpos_to_odoo.py    # capability C: twin -> Odoo XML-RPC ETL (idempotent)
  migration/MAPPING.md               # OptimumPOS -> Odoo entity/field map
  governance/INTEGRATION.md          # Mind gate / policy.json / GDPR / ntfy topics
  systemd/pos-mirror@.{service,timer}# per-client timer units for pos-mirror.sh
  clients/<client>/                  # runtime: env(600), twin.pw(600), status.json, dumps/, logs/
  clients/<client>.yml               # capability C per-client descriptor (db/company/lang/btw/...)
/root/odoo_migration/addons/         # generated atlas_<client>_pos modules (template atlas_pos_seed)
/root/pos_kb/                        # canonical OptimumPOS schema map (reusable across sites)
```

Secrets live in per-client env files (`chmod 600`, gitignored), referenced never committed, backed up
to a single locked-down encrypted B2 path so a hub rebuild can recover them.

---

## 7. The Fleet (current ground truth)

| Client | Tailnet node | What's there | Status |
|---|---|---|---|
| **Venue A** | `venue-a-till` (`192.0.2.10`) | OptimumPOS, MySQL `:3306`, SMB `:445`. Live restaurant. | Highest live-risk; migrate second |
| **Venue B** | `venue-b-till` (`192.0.2.10`) | OptimumPOS MySQL `:3306` **and** Odoo 19 CE on `:8069` (db `venue_b`). Turkish tailor, powered off often. | Mid-migration; finish first |
| **Venue C** | not confirmed on tailnet | Known client, node not yet enrolled | Discovery + enrollment pending |
| **Others** | unknown | Likely exist, not yet enrolled | Discovery is part of the job |

---

## 8. What This Document Is / Is Not

- **Is:** the master statement of goal, principles, capabilities, architecture, and how the program sits
  on pos-hub.
- **Is not:** the execution plan. Sequencing, phase entry/exit criteria, the per-client cutover playbook,
  rollback at each step, timeline, and the "needs operator/client" items live in **ROADMAP.md** alongside
  this file.
