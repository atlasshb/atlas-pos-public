# Deployment

Installing Atlas POS modules on **Odoo 19 Community**.

## Prerequisites

- Odoo 19 Community (on-premise), a database per venue.
- Dutch fiscal localization (`l10n_nl`) for correct BTW (21%/9%/0%).
- For card payments: a Pin Vandaag partner account + terminal + API key.

## 1. Copy the modules

Place the module folders into an Odoo `addons_path` directory:

```
addons/atlas_pos_seed
addons/pos_pinvandaag_atlas
addons/atlas_pos_theme
```

Restart Odoo, enable **developer mode**, then *Apps → Update Apps List*.

## 2. Install `atlas_pos_seed`

- Search "Atlas POS Seed Pack" → **Install**.
- The post-init hook links the Cash/Card payment methods to journals by
  **search** (never a hard-coded xmlid) and activates the second UI language.
- Then set the venue's own categories, products and receipt text.

## 3. Install `pos_pinvandaag_atlas` (optional, for card payments)

- Search "POS Pin Vandaag" → **Install**.
- In *Point of Sale → Payment Methods*, set the method's terminal type to
  **Pin Vandaag**, and enter the **terminal id** and **API key**.
- `docs/04-pinvandaag-integration.md` has the full walkthrough.

## 4. Theme (optional)

Install `atlas_pos_theme` and edit the SCSS variables to the venue's brand.

## 5. Verify

- Open the POS; confirm products/categories load and the language is correct.
- For card payments, run a **test transaction** on a test terminal before
  going live. Never test with real money on an untested path.

## Configuration notes

- Products omit `taxes_id` so they inherit the company default BTW.
- The seed pack never touches `l10n_nl` or the chart of accounts.
- Sessions access the POS UI through the normal Odoo login; keep a local admin
  fallback if you use SSO.

## Rollback

- Uninstall the seed pack: it is additive and does not delete company data.
- Keep a database backup before installing anything in production.
