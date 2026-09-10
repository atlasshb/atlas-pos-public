# Odoo modules

Thin Odoo 19 Community modules for the Atlas POS stack. All are **LGPL-3** (see
each module's `LICENSE`), matching Odoo and the upstream Pin Vandaag module.

| Module | Purpose |
|---|---|
| `pos_pinvandaag_atlas` | POS payment terminal via the Pin Vandaag REST API v2 (Worldline/CCV). Fork of the official `pos_pinvandaag` 17.0, ported to the Odoo 19 `payment_interface` API. |
| `atlas_pos_seed` | Additive, idempotent POS provisioning pack: bilingual categories, goods/services, cash + manual card payment methods, receipt config, language activation. |
| `atlas_pos_theme` | Re-brandable backend + login theme scaffold (SCSS variables). |

## Install

Place the folders in an Odoo `addons_path`, restart Odoo, enable developer mode,
*Apps → Update Apps List*, then install. See `docs/04-pinvandaag-integration.md`
and the wiki `Deployment` page.

## Attribution

`pos_pinvandaag_atlas` derives from **`pos_pinvandaag` by PIN Vandaag B.V.**
(LGPL-3). See the repository `NOTICE.md`. The upstream copyright is preserved in
the source file headers.
