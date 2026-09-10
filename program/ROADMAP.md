# Atlas POS Program — Roadmap

**Companion to:** PROGRAM.md (goal, principles, architecture).
**Control plane:** pos-hub. **Last updated:** 2026-06-30.

This is the execution plan: a 5-phase program, a per-client sequencing decision, a fixed 9-step
cutover playbook, rollback at every step, a realistic timeline, and the items that need the operator
or the client.

> ## ‼️ CURRENT PHASE = PREPARATION + TESTING ONLY
> Every **cutover / go-live** step below is FROZEN until explicit per-client consent in a quiet window.
> Run now only: inventory, read-only mirror/twin/backup, per-client Odoo build, ETL `--dry-run` into staging,
> config validation. Do not stop/replace any live DoPos or process real payments without consent.

---

## 1. Phased Plan (entry / exit criteria)

Every phase is run from pos-hub. Phases 0–3 never touch a live terminal except capability B's
read-only pull (which is itself treated as a terminal touch and quiet-windowed on first run).

### Phase 0 — Program Foundation (hub-only, zero client risk)
**Entry:** today's reality (Venue B mid-migration, Venue A live, others undiscovered).
**Work (all on pos-hub):**
- Reverse-engineer the DoPos MySQL schema **once** into a documented canonical map in
  `/root/pos_kb` (products, categories, prices, taxes/BTW, payment methods, tickets, staff). Reusable
  across every same-build client.
- Build the reusable idempotent ETL toolkit in `/root/odoo_migration` (external-ID-keyed upserts,
  dry-run mode → throwaway Odoo DB → reconciliation report).
- Build the mirror pipeline skeleton in `/root/odoo_sync` + `/opt/atlas-pos/bin` (`pos_pull.sh`,
  `pos_load_twin.sh`), pull-based and offline-tolerant.
- Stand up the per-client Odoo Community template from `atlas_pos_seed`: `l10n_nl` + BTW groups,
  POS, Worldline as a **manual** card method, browser/PDF receipt baseline. UI language as a
  per-client flag.
- Wire the Mind: `policy.json` `pos_program` ruleset (L0/L1, quiet-window, parallel-run constraints);
  ntfy actionable approvals.
**Exit:** canonical schema map done; ETL dry-run green against a sample dump; mirror skeleton runs;
Odoo template boots with NL BTW + manual Worldline; rollback trivial (nothing touched a client).

### Phase 1 — Discover + Inventory (capability A)
**Entry:** Phase 0 exit.
**Work (read-only, network-level):**
- Inventory every client + terminal; record tailnet-enrolled (Venue A, Venue B) vs not (Venue C
  + unknowns).
- For unenrolled sites: a **consent + hardware** step (agree to install Tailscale on a visit/remote
  session), never a sweep. Capture DoPos version, MySQL `:3306` reachability over tailnet,
  SMB `:445`, receipt-printer model, Worldline model, business hours (→ quiet window), BTW reg,
  catalog size.
- Output one git-versioned inventory record per client under `/opt/atlas-pos`.
**Exit:** every known client has an inventory record; enrollment status known for all; quiet windows
captured; per-site consent obtained before any deeper access.

### Phase 2 — Twin / Mirror / Backup (capability B) — the safety spine
**Entry:** client is tailnet-enrolled + consented + inventoried + (for first mirror) DPA signed.
**Work (read-only against the live terminal):**
- First full pull during a quiet window (a full dump can briefly load the box). Subsequent pulls are
  small and run anytime the box is online.
- Land as (1) a queryable `atlas-mariadb-<client>` twin and (2) versioned restic snapshots to B2.
- Tolerate intermittency: missed pull = retry next time up; never block, never false-alert on an
  expected power-off.
- Runs continuously from here through parallel-run and as ongoing DR until DoPos is
  decommissioned.
**Exit:** client's twin is current on pos-hub; restic snapshot verified-restorable (restore-drill);
incremental pull stable across several on/off cycles.

### Phase 3 — Build Odoo + Data ETL (capability C, build side — no cutover)
**Entry:** client twin is live (Phase 2 exit).
**Work (on pos-hub, against the twin — ZERO live-terminal contact):**
- Instantiate the client's Odoo DB from the template (NL BTW, POS, manual Worldline). For Venue B,
  adopt/normalize the existing db `venue_b` rather than rebuild.
- Run the ETL from the twin: catalog → products/categories, prices, BTW-mapped taxes, payment
  methods, staff (→ `hr.employee` only, no bulk logins). Sales history loaded as read-only reference,
  not replayable orders.
- **Reconciliation gate:** automated twin-vs-Odoo report (product count, price sums per category, tax
  totals, payment-method coverage). Operator signs off in the Mind ledger.
- Receipt + Worldline manual-method dry test on a **bench** terminal, not the live one.
**Exit:** Odoo reconciles against the twin within tolerance; hardware dry test passes; operator
sign-off recorded.

### Phase 4 — Parallel Run → Cutover → Decommission (capability C, go-live)
**Entry:** Phase 3 exit + explicit client go + a chosen quiet window.
(Detailed step-by-step in the per-client cutover playbook, §3.)
**Exit (per client):** DoPos retired on that site; client running Atlas-owned Odoo POS; new Odoo
DB under restic/B2 backup.

---

## 2. Per-Client Sequencing (lowest live-risk first)

1. **Venue B — first.** Already has Odoo 19 CE `:8069` db `venue_b` (migration in progress). Powered
   off often = low live-transaction risk. Retail clothing = simpler catalog, fewer modifiers than a
   restaurant. Use it to harden the whole playbook + ETL toolkit; its frequent-off nature also
   stress-tests intermittency handling.
2. **Venue A — second.** Live restaurant = highest risk (busy, modifiers/courses, real-time card
   flow, downtime hurts most). Only after the playbook is battle-tested on Venue B. May need
   `pos.floor`/`pos.table` seeding (restaurant variant) and a longer parallel run. Quiet window =
   restaurant closed hours.
3. **Venue C + newly-discovered clients — third onward.** Sequence by (a) consent/enrollment
   readiness and (b) transaction volume/complexity, lowest first. Each repeats the same playbook; the
   toolkit is now mature, so each is faster.

---

## 3. Per-Client Cutover Playbook (the 9 steps)

Run per site. Steps 1–5 are hub-side and reversible; the live-terminal touches (8–9) are L1, quiet-
window-gated, with the client present/consenting.

1. **Discover** — inventory record exists; enrollment + consent confirmed (capability A).
2. **Enroll tailnet** — Tailscale installed on the terminal if not already (L1, new trust boundary;
   DPA signed before first mirror).
3. **Mirror** — twin is live and fresh; restic snapshot verified-restorable (capability B).
4. **Build Odoo** — per-client Odoo DB instantiated from template; module installed (capability C).
5. **ETL** — run from the twin; reconciliation report green; operator sign-off in the Mind ledger.
6. **Parallel run** — install Odoo POS alongside DoPos (or on a second till). DoPos stays
   system of record. Staff shadow-ring on Odoo. Nightly: re-pull twin + delta-load Odoo; compare
   end-of-day Z-totals. Run a real business cycle (≥1–2 weeks incl. a weekend); the Mind gate will not
   surface the cutover approval until ≥14 days of reconciled parallel-run is recorded.
7. **Train** — staff use the real new till on real orders during the parallel run, old till as safety
   net.
8. **Cutover** (quiet window, closed hours, client consenting, operator on the box): final delta ETL
   from a fresh quiet-window dump → set Odoo as system of record → switch the terminal's default till
   to Odoo. Worldline stays standalone (manual method) so card payments are unaffected. Keep
   DoPos installed but demoted as the rollback path. Then **watch** the first full trading day
   with the operator reachable; ntfy alerts on errors; compare that day's Z-total against expectation.
9. **Decommission** (only after a clean trading week on Odoo): final DoPos dump archived to B2,
   DoPos uninstalled / license released, terminal left running Atlas Odoo only. The client's
   mirror puller is repurposed to back up the new Odoo DB.

---

## 4. Rollback at Every Step

| Stage | If it goes wrong | Rollback |
|---|---|---|
| Phase 0–1 (discovery) | n/a | Read-only; don't enroll a reluctant client. No terminal state changed. |
| Phase 2 (mirror) | Pull misbehaves | Stop the puller, delete the twin schema. Terminal untouched; DoPos runs as before. |
| Phase 3 (build/ETL) | Odoo wrong | Drop/rebuild the client Odoo DB from template; re-run ETL from the immutable twin snapshot. Fully hub-local. |
| Step 6 (parallel run) | Odoo inaccurate | Just stop using Odoo — DoPos was always system of record → zero impact. |
| Step 8 (cutover, day 1) | Day-1 failure | Flip default till back to the still-installed DoPos (data current to the quiet-window dump); re-mirror; investigate on the hub. Card payments never depended on the switch. |
| Step 9 (decommission) | Point of no easy return | Gated on a clean trading week + final archive + client sign-off before this step is allowed. |

A pre-ETL `pg_dump` of each client Odoo DB is taken before every ETL run, so even a bad migration is a
clean restore. Nothing on a live terminal is ever modified before step 8.

---

## 5. Timeline (realistic, consent-gated)

| Milestone | Estimate | Note |
|---|---|---|
| Phase 0 foundation | ~1–2 weeks | Hub work, reusable forever |
| Phase 1 discovery | Ongoing / overlapping | Known clients ~days; unenrolled gated on visit/consent |
| **Venue B** cutover | ~4–6 weeks from foundation done | Already mid-migration; low live-risk |
| **Venue A** cutover | ~8–12 weeks | Longer parallel run for a live restaurant; needs a genuinely quiet window |
| **Fleet "DoPos retired"** | ~5–7 months | Dominated by client consent/scheduling and discovery of unenrolled sites, not by engineering |

The schedule is driven by client consent windows and enrollment, not by code. Engineering is the
fast part; access and quiet windows are the constraint.

---

## 6. Needs Operator / Client

These are the human-gated inputs the program cannot proceed without:

- **Per-client written consent** before ANY terminal access beyond inventory.
- **Per-client DPA** (verwerkersovereenkomst) signed **before first mirror** — the Mind gate refuses a
  mirror intent for a site whose inventory `dpa` is unsigned.
- **A confirmed quiet window** (closed hours) per client for: the first full mirror dump, and cutover.
  Venue A (restaurant) and Venue B (often-off tailor) differ — both need explicit confirmed windows.
- **Tailscale install** on unenrolled terminals (Venue C + undiscovered) — a visit or
  remote-assisted session.
- **Hardware confirmation per site:** Worldline model (stays standalone) and receipt-printer model
  (for Odoo print config).
- **BTW / company registration** details per client for correct NL tax setup (and confirmation that
  `l10n_nl` + default tax is set **before** the first posted entry — Odoo 19 forbids changing the
  fiscal package afterwards).
- **Staff availability** for training during the parallel run.
- **Operator sign-off in the Mind ledger** at each gate: ETL reconciliation, cutover go, decommission
  go.

---

## 7. Open Questions Carried Into Execution

These need answering per client as the program runs; they do not block starting Phase 0.

- Is DoPos the **same build/schema** on every site, or per-site variants (determines whether the
  canonical schema map is reusable or needs deltas)?
- What is Venue B's current db `venue_b` state — how much is already migrated, and is it clean enough
  to adopt as the template instance or should it be reset?
- Does DoPos store prices **tax-inclusive or tax-exclusive**? (Determines whether the ETL divides
  by `(1+BTW)` and how `taxes_id` is set.)
- What MySQL **engine** per site (InnoDB vs MyISAM)? MyISAM breaks `--single-transaction` consistency
  → may need closed-window per-table locking.
- Does any client run **multiple terminals** per site (multi-till)? Changes parallel-run topology and
  system-of-record handling.
- Does Venue A need **restaurant features** (floors/tables/split bills), i.e. does the single-counter
  Venue B `pos.config` template generalize or need a hospitality variant?
- Is **sales history required inside Odoo** for any client's reporting/legal retention, or is the
  twin-as-archive sufficient for their accountant?
- Are DoPos **licenses** cleanly releasable on decommission, or is there contractual lock-in /
  exit cost per client?
- **Target freshness** per client: is nightly twin refresh enough, or is intra-day (e.g. every 2h)
  catalog/sales freshness needed? Drives timer cadence.
