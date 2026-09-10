# atlas_pos_seed — DEPLOY KIT

Deploy / configure the **Venue B POS** pack onto the live Odoo server.

| Item | Value |
|------|-------|
| Odoo version | **19.0 Community Edition** (build 20260513) |
| Server URL | http://192.0.2.10:8069 |
| Database | `venue_b` |
| Module technical name | `atlas_pos_seed` |
| Host | Windows |
| POS UI language | **Turkish (tr_TR)** — UI only |
| Accounting / VAT | **Dutch (BTW)** — see assumption below |

---

## ⚠️ READ FIRST — LOCALIZATION / VAT ASSUMPTION (the one thing that can go wrong)

**Venue B is a Dutch-registered business. Accounting and VAT MUST be Dutch (BTW 21% / 9% / 0%). Turkish is the screen language ONLY.**

This pack is **deliberately built to NOT touch your chart of accounts, company, or taxes.** It is:

- **Idempotent** — safe to run / upgrade repeatedly.
- **Additive only** — it creates POS categories, products, two payment methods and (optionally) a POS config. It never edits or deletes existing records.
- **Non-destructive to accounting** — it does **not** depend on `l10n_nl`, does **not** install a chart of accounts, and does **not** create or overwrite any tax.

Because of that, **two things are MANUAL admin steps you (or the installer) must confirm on the live DB**, ideally **before any invoice/journal entry is posted**:

1. **Dutch fiscal localization (`l10n_nl`) is installed and selected.**
   `Apps → install "Netherlands - Accounting" (l10n_nl)`, then
   `Accounting → Configuration → Settings → Fiscal Localization = Netherlands`.
   > Odoo 19 hard rule: the fiscal package can only be selected/changed **while no journal entry has been posted**. Do this early.

2. **The company default Sales Tax = "21% BTW".**
   `Accounting → Configuration → Settings → Default Taxes → Sales Tax = 21% BTW`.
   Every Venue B product inherits this default (the products ship with **no** hard-coded tax), so if this is wrong, every product gets the wrong tax.

> **Do NOT install `l10n_tr` (Turkish accounting).** It would give a Dutch company Turkish VAT. Turkish is the UI language, nothing more.

Why it's done this way: force-loading `l10n_nl` from a module's `depends` onto a DB that already has a chart of accounts can raise a foreign-key error (`res_company_transfer_account_id_fkey`) and abort the whole install. Keeping it manual is what makes this pack **safe to apply blind**.

---

## What the pack installs

- **Turkish UI** activated via a `post_init_hook` (`res.lang._activate_lang('tr_TR')` + translation pack, `overwrite=False`). Idempotent, no-op if already active.
- **POS categories** (bilingual NL/TR): Galajurken (Abiye), Kostuums (Takım Elbise), Kleding (Giyim), Accessoires (Aksesuar), Vermaak & Reparatie (Tadilat & Onarım).
- **16 products** — dresses/suits/clothing/accessories as `type='consu'`; alterations/repairs as `type='service'` (price keyed per job at the counter). All `available_in_pos=True`, all inherit the company 21% BTW default tax.
- **2 POS payment methods**
  - **Contant** (cash) — linked to a **cash** journal → drawer/closing-count behaviour.
  - **Pinnen / Worldline kaart** (manual card) — linked to a **bank** journal, **no integrated terminal** (`use_payment_terminal` left empty). The cashier runs the physical Worldline YOMANI by hand and confirms the amount in POS.
- Journal linking is done **defensively in the `post_init_hook`** (searches for cash/bank journals, skips gracefully if none exist yet), so the pack installs cleanly even on a bare DB.

> **The Worldline YOMANI is a standalone wired terminal.** In Odoo 19 **Community**, integrated terminals (Worldline/SIX/Adyen/Stripe) are **Enterprise + IoT only** and the integration dropdown is empty. The correct, supported Community representation is exactly this **manual bank card method**. Do not try to "integrate" the terminal.

> **Receipt printing** defaults to the **browser/PDF print dialog**, which works with any Windows-installed printer with zero config. ePOS direct LAN printing (Epson only) stays **off** in the committed data because the printer IP is unknown at build time — enabling it with a wrong/empty IP would break printing. See the on-site upgrade note in `MANUAL_CHECKLIST.md`.

---

## THREE WAYS TO DEPLOY

Pick **one**. They lead to the same result. Option A is the cleanest; Option C is the safe fallback if you cannot reach the server filesystem.

### Option A — Copy the module over SMB, then install in the UI (recommended)

Use this when you can reach the Windows Odoo host's addons folder over the network.

1. Edit the **TODO placeholders** at the top of `deploy/install_via_smb.ps1` (the share path / addons path and, if needed, credentials — **never hardcode a password in the file**).
2. Run it from a Windows PowerShell on a machine that can reach `\\192.0.2.10`:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\deploy\install_via_smb.ps1
   ```
3. It copies the whole `atlas_pos_seed` folder into the addons path. Then in Odoo:
   `Apps → (developer mode) → Update Apps List → search "atlas_pos_seed" → Install`.
4. After install, run the **smoke test** below.

### Option B — Place the module manually + restart + install

Use this when you have direct (RDP/console) access to the Odoo host.

1. Copy the `atlas_pos_seed` folder into one of Odoo's `addons_path` directories (check `odoo.conf` for `addons_path`; typically `...\server\odoo\addons` or a custom addons dir).
2. Restart the Odoo service (Windows: `services.msc` → restart the Odoo service, or restart from the command line).
3. In Odoo, enable developer mode, then `Apps → Update Apps List → install "atlas_pos_seed"`.
4. Run the **smoke test** below.

### Option C — XML-RPC external API (no filesystem access needed)

Use this when you can only reach Odoo over HTTP (port 8069), not the host filesystem.

1. Set environment variables (do **not** put the password in a committed file):
   ```powershell
   $env:ODOO_URL="http://192.0.2.10:8069"
   $env:ODOO_DB="venue_b"
   $env:ODOO_USER="admin"          # an admin login
   $env:ODOO_PASSWORD="********"    # that user's password or API key
   python .\deploy\setup_via_xmlrpc.py
   ```
2. The script:
   - Authenticates.
   - **If the module `atlas_pos_seed` is already in the DB**, it installs/upgrades it via the ORM and stops.
   - **Otherwise (fallback)**, it creates the catalog (POS categories + products), the two payment methods (resolving cash/bank journals by search), and attaches them to a POS config — all directly via ORM, **idempotently** (re-running changes nothing).
   - Activates Turkish (`tr_TR`).
3. Run the **smoke test** below.

> Option C's fallback is for when you cannot get the module file onto the server at all. If you *can* deploy the module (A or B), prefer that — the module is the source of truth.

---

## POST-DEPLOY SMOKE TEST (do this every time, ~3 minutes)

Confirms the four things that matter: UI language, products, the manual Worldline card payment, and receipt printing.

**Pre-check (once):**
- [ ] `Settings → Users → (your user) → Preferences → Language = Türkçe (tr_TR)`. Log out/in if the UI is still English.
- [ ] `Accounting → Configuration → Settings`: Fiscal Localization = **Netherlands**, Default Sales Tax = **21% BTW** (see the assumption section).
- [ ] `Point of Sale → Configuration → Payment Methods`: **Contant** and **Pinnen / Worldline kaart** both exist; Contant is linked to a **cash** journal, the card method to a **bank** journal with **no** payment terminal selected.

**Ring up a real sample order:**
1. `Point of Sale → open your shop session (Yeni Oturum / New Session)`.
2. Add a **gala dress**: tap **Galajurken (Abiye)** → **Galajurk (Abiye) - Standaard** (€199). Confirm it lands on the order with **21% BTW**.
3. Add an **alteration**: tap **Vermaak & Reparatie** → **Vermaak (Tadilat) - prijs per opdracht** (starts at €0). Select the line → press **Price** (or `p`) → type the agreed amount, e.g. **25.00** → confirm. The line should now read €25.00 with 21% BTW.
4. Press **Payment / Betalen**.
5. Choose **Pinnen / Worldline kaart**. Run the physical **Worldline YOMANI** by hand for the order total; once the terminal approves, accept the amount in Odoo and **Validate**.
   - (Optionally test **Contant** on a second order to confirm cash/drawer behaviour.)
6. **Print the receipt**: on the receipt screen press **Print / Afdrukken**. The browser print dialog opens → pick the Windows receipt printer → print. The receipt should show the **Venue B header/footer** and the **priced lines** (gala dress + the €25 alteration) with **BTW 21%** and a total.

**Pass criteria:**
- [ ] POS UI is in Turkish.
- [ ] Gala dress and alteration both ring up at 21% BTW; alteration price was editable at the counter.
- [ ] Payment via the manual **Pinnen / Worldline kaart** method validates the order (no integrated-terminal prompt, no error about an empty terminal selection).
- [ ] Receipt prints with header/footer and prices.

If any step fails, fall back to `deploy/MANUAL_CHECKLIST.md` and finish that item by hand.

---

## File map

```
atlas_pos_seed/
├── README_DEPLOY.md            ← this file
├── deploy/
│   ├── install_via_smb.ps1     ← Option A: copy module over SMB
│   ├── setup_via_xmlrpc.py     ← Option C: install/upgrade or ORM fallback
│   └── MANUAL_CHECKLIST.md     ← click-by-click UI fallback
├── __manifest__.py             ← depends: base, web, point_of_sale, account (NOT l10n_nl / l10n_tr)
├── __init__.py                 ← post_init_hook: activate tr_TR + link journals
└── data/                       ← pos.category, products, payment methods, pos.config
```

> The pack **does not** depend on `l10n_nl`, `l10n_tr`, `pos_iot`, `pos_six`, `pos_worldline`, `pos_adyen` or `pos_stripe`. None of those exist / apply in this Community setup, and depending on them would break the install.
