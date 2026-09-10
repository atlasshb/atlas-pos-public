# kassa-odoo-sync — POS database → Odoo

One-way push from an incumbent POS `kassa` MySQL database to an Odoo
`res.partner` / `product.template` set. Runs on the POS PC, reads the local
database, and writes to Odoo over XML-RPC.

Entities synced:

- `klanten` → `res.partner` (idempotent by `ref=klant_{KLANTID}`)
- `artikel` → `product.template` (idempotent by `default_code=A_CODE`)

Idempotency uses `ir.model.data` external IDs in a module namespace, so re-runs
update existing rows instead of duplicating them. A `state.json` next to
`sync.py` tracks `last_id` per table so each pass only scans new rows.

## Configuration

Copy `config.ini.example` to `config.ini` and fill it in. **Do not commit
`config.ini`.** Put the Odoo login and password in the config or, preferably,
read them from environment variables:

```
ODOO_URL=http://127.0.0.1:8069
ODOO_DB=odoo
ODOO_USER=<api-user>
ODOO_PASSWORD=<from your secret store>
```

Use a dedicated Odoo API user with only the access this sync needs — never the
`admin` account.

## First run

1. `py -3 -m pip install -r requirements.txt`
2. Fill in `config.ini` (or the environment variables above).
3. Dry-run: `run_once.bat`. Confirm the output reads `MODE: DRY-RUN` and shows
   `would-create` / `would-update`.
4. Flip `apply = 1` in `config.ini`, run `run_once.bat` again.
5. For continuous sync, run `run_loop.bat` (every 5 min by default).

## Notes

- Prices in `artikel.A_PRIJS` are stored as eurocents (integer); the daemon
  divides by 100 for `list_price`.
- VAT mapping is **not** implemented — products land with Odoo's default tax.
  Add VAT mapping (`A_BTW_TARIEF` → Odoo `account.tax.id`) before going live on
  real bookkeeping.
- Orders (`bestelling` + `bestelling_detail`) are deliberately not synced —
  they need a POS session model in Odoo plus VAT mapping.
- The private-network connection to the Odoo host must be up.
