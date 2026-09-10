# Runbook — create the read-only MySQL user on an OptimumPOS terminal (L1)

**What:** create the dedicated, read-only MySQL user that `scripts/pos-mirror.sh`
uses to pull a client's OptimumPOS database up to the hub. This is the one
**manual L1 step** every mirror depends on — the mirror cannot run until it
exists, and it must be provably unable to write or escalate.

**When:** once per terminal, before flipping `MIRROR_ENABLED=1` for that client.
Do it with the client's consent — it touches a live card-payment box (read-only,
but still their machine).

**Touches a client terminal?** Yes — this is the only per-terminal write in the
whole mirror path (a one-time `CREATE USER`). Everything `pos-mirror.sh` does
afterwards is strictly read-only.

---

## Steps

1. **On the terminal**, open a MySQL admin shell (as `root` / an admin user):

   ```sh
   mysql -u root -p
   ```

2. **Edit and run** [`create-readonly-mysql-user.sql`](./create-readonly-mysql-user.sql).
   Replace the placeholders first:
   - `<OPTIMUM_DB>` — the OptimumPOS database name (confirm with `SHOW DATABASES;`).
   - `<RO_PASSWORD>` — a strong random password. This becomes `MYSQL_PW` in the
     client's env file.

   The user is created as `'atlas_ro'@'100.%.%.%'` — pinned to the Tailscale
   CGNAT range, so the credential only works from the hub over the tailnet, never
   from the open LAN.

3. **Record the credentials** in the client's env file on the hub (NOT in git):

   ```
   clients/<client>/env        # chmod 600
     MYSQL_HOST=<terminal tailnet IP>
     MYSQL_USER=atlas_ro
     MYSQL_PW=<RO_PASSWORD>
     MYSQL_DB=<OPTIMUM_DB>
   ```

   See `clients/_TEMPLATE/env.example` for the full file.

---

## Verify it is truly read-only (do not skip)

Run the checks at the bottom of the `.sql` file. In short:

- **Inspect the grants** — they must list only
  `SELECT, SHOW VIEW, TRIGGER, EVENT, EXECUTE ON \`<OPTIMUM_DB>\`.*` (plus a
  `USAGE` line). There must be **no** `ALL PRIVILEGES`, **no** `*.*`, **no**
  `WITH GRANT OPTION`, and **no** `INSERT/UPDATE/DELETE/DROP/CREATE`:

  ```sql
  SHOW GRANTS FOR 'atlas_ro'@'100.%.%.%';
  ```

- **Negative tests, connected AS `atlas_ro`** (not as root). Every one of these
  MUST fail with `ERROR 1142` (or `1044`):
  - any `INSERT` / `UPDATE` / `DELETE` / `CREATE TABLE` / `DROP TABLE` in the db
  - `GRANT ... TO 'atlas_ro'...` (escalation must be denied)
  - `SELECT * FROM mysql.user` (other schemas must be invisible)

- **Positive test** — a `SELECT COUNT(*)` against a real table MUST succeed, so
  you know the mirror will actually be able to read.

  Connect as the new user to run these:

  ```sh
  mysql -h <terminal tailnet IP> -u atlas_ro -p <OPTIMUM_DB>
  ```

If any write/grant test **succeeds**, the user is over-privileged. Drop it and
recreate:

```sql
DROP USER 'atlas_ro'@'100.%.%.%';
FLUSH PRIVILEGES;
```

---

## After this runbook

The read-only user existing is necessary but **not sufficient** to start
mirroring. `pos-mirror.sh` still fails closed until, in `clients/<client>/env`:

- `MIRROR_ENABLED=1` (operator opted this client in), **and**
- `DPA_SIGNED=1` (GDPR/AVG data-processing agreement on file), **and**
- the pull is inside `QUIET_WINDOW`.

Only then will a pull run — read-only, over Tailscale, during closed hours.
