# Atlas POS Program — Prep Runbook (PREPARATION + TESTING ONLY)

**Companion to:** PROGRAM.md, ARCHITECTURE.md, ROADMAP.md, governance/INTEGRATION.md.
**Runs on:** pos-hub (`/opt/atlas-pos`, the program git repo). **Last updated:** 2026-06-30.

> ## ‼️ CUTOVER IS FROZEN
> This runbook covers ONLY what is allowed right now: **read-only mirror / twin / backup,
> per-client Odoo build, and ETL `--dry-run` into staging.** It does **NOT** cover cutover, go-live,
> stopping/replacing any live OptimumPOS, or processing real payments. Every one of those is FROZEN
> behind explicit, per-client written consent in a quiet window (see ROADMAP.md §3–§4). Nothing in
> this document touches a live terminal except (1) the one-time read-only MySQL user creation
> (`runbooks/create-readonly-mysql-user.sql`, an L1 step done with client consent) and (2) the
> read-only `mysqldump` pull. There is **no fleet-wide automated sweep on live terminals — ever.**

This is the single ordered, copy-pasteable list of "do these now" steps. Targets this cycle:
**venue_b** and **venue_a** (both already tailnet-enrolled). Run from the repo root on pos-hub:

```sh
cd /opt/atlas-pos
```

The script names below are the ACTUAL shipped layout (combined mirror script; no separate
`pos_pull.sh` / `pos_load_twin.sh` / `optimum_etl.py`):

| Capability | Script | What it does |
|---|---|---|
| A Discover | `scripts/fleet-inventory.sh` | read-only tailnet probe + inventory |
| B Mirror | `scripts/pos-mirror.sh <client>` | **combined** pull + twin-load + restic→B2 (fail-closed gate) |
| B Verify | `scripts/pos-verify.sh <client>` | restore-drill: restore newest dump into a throwaway container, assert |
| C Build | `scripts/odoo-provision-client.sh --client <c>` | build the per-client Odoo 19 CE POS DB + module |
| C ETL | `migration/optimumpos_to_odoo.py` | twin → Odoo XML-RPC upsert (idempotent; `--dry-run` first) |
| B timer | `systemd/pos-mirror@.{service,timer}` | per-client scheduling for `pos-mirror.sh` |

---

## Step 1 — Fleet inventory (capability A, read-only, zero risk)

Confirm what the tailnet sees and where each client sits in the lifecycle. This is a pure read-only
TCP probe — it sends no credentials and no SQL, and exits 0 even when terminals are offline.

```sh
# one-time: create the non-secret registry from the template if you haven't already
[ -f registry.yml ] || cp registry.yml.example registry.yml
# edit registry.yml so venue_a + venue_b have the right tailnet_host / node / optimum_db

# run the read-only discovery (writes state/fleet-inventory.json + prints a table)
scripts/fleet-inventory.sh
```

Read the table: `venue_a` and `venue_b` should show on the tailnet (status `online` when their box is
up; `offline` is normal for the often-off Venue B tailor). Note the `POS(3306)` column — that is the
OptimumPOS MySQL we will mirror.

---

## Step 2 — Mirror each client (capability B): venue_b, then venue_a

Do the full sequence below **per client**. It is written for `venue_b` first (lower live-risk, often
off → good intermittency test), then repeat verbatim for `venue_a`. The mirror is **fail-closed**:
it refuses (clean skip) until you explicitly enable it, so it is safe to set up before you are ready.

### 2a. Create the per-client env from the template

```sh
C=venue_b            # then repeat the whole step with  C=venue_a
mkdir -p clients/$C
cp clients/_TEMPLATE/env.example clients/$C/env
chmod 600 clients/$C/env       # REQUIRED — pos-mirror.sh fails closed on any
                               # group/other-readable secrets file
```

Now edit `clients/$C/env` and fill in the real values. Leave the safety gate **OFF** for now
(`MIRROR_ENABLED=0`, `DPA_SIGNED=0`) — you flip those only in step 2d when truly ready:

- `MYSQL_HOST` — the terminal's **tailnet** IP (must be `100.64.0.0/10`; the mirror refuses anything
  else). Venue B = `192.0.2.10`, Venue A = `192.0.2.10`.
- `MYSQL_USER=atlas_ro`, `MYSQL_PW=<the password you set in step 2b>`, `MYSQL_DB=<OptimumPOS db>`.
- `RESTIC_REPOSITORY=b2:atlas-pos-backups:/$C`, `RESTIC_PASSWORD=<per-tenant>`, `B2_ACCOUNT_ID/KEY`.
- `TWIN_MYSQL_*` / `ODOO_*` — used by the ETL in step 4; can be filled now or then.
- Leave `TWIN_ROOT_PW` unset — `pos-mirror.sh` generates it once into `clients/$C/twin.pw` (0600).

### 2b. Create the read-only MySQL user on the terminal (one-time, L1, client-consented)

This is the only per-terminal write in the whole mirror path (a one-time `CREATE USER`). Do it with
the client present/consenting. Full procedure + read-only verification is in
[`runbooks/create-readonly-mysql-user.md`](./runbooks/create-readonly-mysql-user.md); the SQL is
[`runbooks/create-readonly-mysql-user.sql`](./runbooks/create-readonly-mysql-user.sql).

On the terminal, as a MySQL admin, after replacing `<OPTIMUM_DB>` and `<RO_PASSWORD>`:

```sql
-- from runbooks/create-readonly-mysql-user.sql
CREATE USER IF NOT EXISTS 'atlas_ro'@'100.%.%.%' IDENTIFIED BY '<RO_PASSWORD>';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, EXECUTE ON `<OPTIMUM_DB>`.* TO 'atlas_ro'@'100.%.%.%';
FLUSH PRIVILEGES;
SHOW GRANTS FOR 'atlas_ro'@'100.%.%.%';   -- must show ONLY the read grants above (+ USAGE)
```

Then run the negative tests in that runbook **connected as `atlas_ro`** — every `INSERT/UPDATE/DELETE/
CREATE/DROP/GRANT` MUST fail (`ERROR 1142/1044`) and `SELECT * FROM mysql.user` MUST be denied. A
`SELECT COUNT(*)` on a real table MUST succeed. Do not proceed if any write/grant test succeeds —
the user is over-privileged; drop and recreate.

### 2c. (Recommended) confirm the DPA is signed and recorded

`pos-mirror.sh` will not hold a client's data without `DPA_SIGNED=1`. The DPA
(verwerkersovereenkomst) must be signed **before the first mirror** (GDPR/AVG; see
governance/INTEGRATION.md §6). Record the date in `registry.yml` (`dpa_signed_date:`) for the
fleet record — that field is declarative; the **enforcing** flag is `DPA_SIGNED` in the env file.

### 2d. Flip the gate ON — only when ready — and run the mirror

Only now, once the read-only user is verified, the DPA is signed, and you are inside (or will set) the
client's quiet window, enable the client in `clients/$C/env`:

```sh
# in clients/$C/env, set:
#   MIRROR_ENABLED=1
#   DPA_SIGNED=1
#   QUIET_WINDOW=01:00-06:00     # keep to the client's closed hours
```

Run the combined mirror (pull → twin-load → restic). It is read-only against the terminal, skips
cleanly if the box is offline or outside the quiet window, and is safe to re-run:

```sh
scripts/pos-mirror.sh $C
```

On success it writes a timestamped dump to `clients/$C/dumps/`, appends a sha256 to `SHA256SUMS`,
drops+recreates the `atlas-mariadb-$C` twin from that dump, ships the dump tree to B2 with restic, and
writes `clients/$C/status.json`. A green run pushes ntfy topic `pos-mirror`.

> If it prints "not enabled / no DPA / outside quiet window / unreachable" it is **skipping cleanly by
> design** (exit 0) — fix the named condition and re-run. That is the fail-closed gate working.

### 2e. Verify the backup is actually restorable (restore-drill)

A backup you have never restored is not a backup. This restores the newest dump into a **throwaway**
container, asserts it is non-empty and sane, then tears it down. It never touches the real twin or the
terminal:

```sh
scripts/pos-verify.sh $C                 # drills the latest LOCAL dump
# scripts/pos-verify.sh $C --from-restic # optional: drill the latest B2 snapshot instead
```

Exit 0 = drill passed (or nothing to verify yet). Exit 4 = the backup is suspect — investigate before
relying on it.

### 2f. (Optional) schedule the mirror via systemd

Once a manual run + verify is green, install the per-client timer so mirroring continues
hands-off (still gated by the env flags, still quiet-windowed):

```sh
cp systemd/pos-mirror@.service systemd/pos-mirror@.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pos-mirror@venue_b.timer
systemctl enable --now pos-mirror@venue_a.timer
```

**Now repeat all of Step 2 for `C=venue_a`.** Venue A is a live restaurant — its quiet window is the
restaurant's closed hours; keep `MIRROR_ENABLED=0` until you are genuinely in a closed-hours window
with consent.

---

## Step 3 — Build the per-client Odoo + ETL DRY-RUN (capability C, hub-only, no terminal contact)

Everything here runs on pos-hub against the **twin**, never a terminal. Rollback for the whole step is
"drop the per-client Odoo DB". Do `venue_b` first (adopt/normalize its existing db `venue_b`), then
`venue_a`.

### 3a. Provision the client's Odoo DB + module

Create `clients/<client>.yml` (the capability-C descriptor: `db`, `company`, `lang`, `country`,
`btw_rate_default`, `kvk`, `btw`, `pos_name`, `module`) — see
`scripts/odoo-provision-client.sh` header for the keys. Then:

```sh
# print the plan first (no writes) — tolerates missing secrets so you can review it
scripts/odoo-provision-client.sh --client venue_a --lang nl_NL --dry-run

# then build for real (needs ODOO_MASTER_PW + ODOO_ADMIN_PW exported / in the per-tenant env)
scripts/odoo-provision-client.sh --client venue_a --lang nl_NL
```

This builds the DB with `base, point_of_sale, l10n_nl, contacts, stock`, then installs
`atlas_<client>_pos` (cloned from the proven `atlas_pos_seed` template). Venue B already runs db
`venue_b` on `:8069` — provision it idempotently (it converges; only use `--recreate` deliberately,
and it takes a pre-drop `pg_dump` first).

> **MANUAL fiscal gate (do NOT skip):** confirm the `l10n_nl` fiscal package + default sales/purchase
> tax on the company **before any posted journal entry**. Odoo 19 forbids changing the fiscal package
> after the first posted entry. The provision script prints this warning; it is a real manual step.

### 3b. Run the ETL as a DRY-RUN and read the reconciliation report

The ETL reads the **hub twin** (it hard-refuses a `100.x` tailnet/terminal address as its source) and
on `--dry-run` performs **no writes** to Odoo — it computes every upsert and prints the reconciliation
report. The single per-client `clients/<client>/env` already holds the `TWIN_MYSQL_*` and `ODOO_*`
values; export it and run without `--client` so the one consolidated env file is the source of truth:

```sh
C=venue_a
set -a; source clients/$C/env; set +a          # load TWIN_MYSQL_* + ODOO_* into the environment
python migration/optimumpos_to_odoo.py --dry-run
```

Read the printed reconciliation report carefully: product counts (migrated vs active source articles),
per-category price sums, BTW/tax totals mapped by rate, and payment-method coverage (every card/pin
variant collapses to ONE manual "Pinnen / Worldline kaart" method; cash → cash). **A non-empty
mismatch list means do NOT proceed** — it is the gate that would block any future cutover. Re-run is
idempotent (keyed on `OPT-<sourcePK>`); it never duplicates and never clobbers human-edited prices.

Only after the dry-run report is clean would you run the ETL for real (`python
migration/optimumpos_to_odoo.py` without `--dry-run`) into the **staging** Odoo DB — still hub-only,
still not a cutover.

---

## Where it stops

After Step 3 you have, per client: a fresh read-only twin on the hub, a verified-restorable encrypted
backup in B2, a built per-client Odoo POS DB, and a clean ETL reconciliation report. That is the
entire allowed scope right now.

**The next phases — parallel run, cutover, decommission (ROADMAP.md §3 steps 6–9) — are FROZEN.** They
require explicit per-client written consent, a confirmed quiet window, ≥14 days of reconciled
parallel-run, and operator sign-off in the Mind ledger. Do not start them from this runbook.
