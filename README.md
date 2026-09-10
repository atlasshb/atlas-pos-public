# Atlas POS — open-source research & components

Research, architecture and reusable components from Atlas Corporation's work on
building a **Point-of-Sale platform on Odoo 19 Community**, integrated with
**Pin Vandaag / Worldline** card terminals, for small hospitality and retail
venues in the Netherlands.

We are publishing this because a lot of the "can Odoo Community really run a
shop?" question has already been answered the hard way. Sharing it is cheaper
for everyone than rediscovering it.

> This repository is a **curated, de-identified export**. It contains no
> credentials, no API keys and no customer data. Client-specific values have
> been replaced with generic placeholders (`venue_a`, `192.0.2.10`, …).

## What is in here

| Path | What it is |
|---|---|
| `docs/` | Research and design notes: Odoo POS landscape (Community vs Enterprise), the OCA POS ecosystem, Pin Vandaag/Worldline integration, payments architecture, migration strategy, POS scope & compliance. |
| `docs/11-oss-pos-projects.md` | A worldwide list of open-source POS projects with upstream URLs and our verdict on each. |
| `docs/12-payments-landscape.md` | Card terminals, PSPs, SoftPOS and open banking — integration routes and compliance boundaries. |
| `docs/13-world-pos-payments-trends.md` | Market-level POS/payments trends (indicative figures, public sources). |
| `docs/infra/` | De-identified engineering notes from running a self-hosted stack: right-sizing, reversible migrations, backups that restore, SSO front door, hardening, silent-failure ops, LLM routing, incident lessons. |
| `addons/` | Standalone Odoo 19 Community modules: a POS catalogue/config **seed pack**, a backend/login **theme template**, and the ported **Pin Vandaag** payment-terminal module. |
| `migration/` | An idempotent **OptimumPOS → Odoo 19** ETL and the entity mapping notes. |
| `program/` | The "discover → read-only mirror → replace" program docs: architecture, roadmap, prep runbook, connection pack and a fleet registry template. |
| `scripts/` | Field-proven shell/Python tooling: fleet discovery, health watch, read-only mirror, restore-drill verify, PAN scrubbing, and a tamper-evident order journal. |
| `systemd/` | Templated `pos-watch@` / `pos-mirror@` units. |
| `runbooks/` | The least-privilege **read-only MySQL user** runbook. |

## The short version of our findings

- **Odoo 19 Community is the only open-source POS we found with a real
  payment-terminal plugin registry.** Restaurant mode (`pos_restaurant`) ships
  in Community 19 — it is not Enterprise-only any more. The Enterprise-only
  parts are the IoT box and the certified hardware integration layer.
- **The terminal integration already exists.** PIN Vandaag B.V. publishes a free,
  LGPL-3 Odoo module (`pos_pinvandaag`) that drives Worldline/CCV cloud
  terminals over a REST API — no IoT box, no Enterprise. We forked it and ported
  it from 17.0 to the Odoo 19 `payment_interface` API (see `addons/pos_pinvandaag_atlas`).
- **OCA/pos is thin on 19.0.** It is worth watching, but 19.0 has only a handful
  of modules; 17.0/18.0 are much richer. Plan on porting modules, not consuming
  them as-is.
- **The Java desktop POS family** (UniCenta oPOS, ChromisPOS, FloreantPOS) is a
  poor fit: JavaPOS-era printing, no REST terminal layer, and it splits your
  bookkeeping from your POS. We evaluated them and moved on.
- **ERPNext + URY** is the closest full-ERP alternative but does not give you a
  maintained Dutch card-terminal integration.

See `docs/01-oss-pos-evaluation.md` for the full comparison.

## Modules

| Module | Purpose | License |
|---|---|---|
| `addons/pos_pinvandaag_atlas` | Odoo 19 POS payment terminal via Pin Vandaag REST API v2 (Worldline/CCV). Forked from the official `pos_pinvandaag` 17.0 and ported to Odoo 19. | LGPL-3 |
| `addons/atlas_pos_seed` | Additive, idempotent POS provisioning pack: bilingual categories, goods/services, cash + manual card payment methods, receipt config, language activation. | LGPL-3 |
| `addons/atlas_pos_theme` | Backend + login theme scaffold (SCSS variables), meant to be re-branded per venue. | LGPL-3 |

## Attribution

`addons/pos_pinvandaag_atlas` is derived from **`pos_pinvandaag` by PIN Vandaag
B.V.**, licensed LGPL-3. The original module targets Odoo 15–17; this fork ports
the frontend to the Odoo 19 `PaymentInterface` / `register_payment_method` API.
All credit for the API design and the original module belongs upstream. See
`NOTICE.md`.

## Contact

Atlas Corporation — Tilburg, NL — <https://atlascorporation.nl>

## License

See `LICENSE` (MIT for Atlas-authored documentation and tooling) and the
per-module `LICENSE` files. The POS-adjacent Odoo modules are LGPL-3, as is the
upstream Pin Vandaag module they derive from.
