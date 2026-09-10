# Atlas POS — Wiki

Welcome. This wiki is a condensed companion to the repository documentation.

**Atlas POS** is an open-source Point-of-Sale stack built on **Odoo 19
Community**, with card acceptance via **Pin Vandaag / Worldline** cloud
terminals (no Odoo Enterprise, no IoT box).

> This is a **de-identified public** project. No credentials, client data or
> internal infrastructure details are included.

## Start here

| Page | What you'll find |
|---|---|
| [[Architecture]] | How the pieces fit: Odoo, modules, PSP, terminal |
| [[Payments]] | Card-terminal routes, providers, compliance boundaries |
| [[Deployment]] | Installing the modules on Odoo 19 Community |
| [[Migration]] | Moving a venue off an incumbent POS safely |
| [[Glossary]] | POS / payments / Odoo terms |
| [[FAQ]] | Common questions |
| [[Troubleshooting]] | Known failure modes and fixes |

## Repository

- Source: the `atlas-pos-public` repository (`docs/`, `addons/`, `migration/`,
  `scripts/`).
- Full docs index: `docs/00-overview.md`.
- Diagrams: `docs/14-architecture-diagrams.md`.

## The one-paragraph summary

Odoo 19 Community is the only open-source POS we found with a real
payment-terminal plugin registry. We extend it with a thin per-venue seed pack,
a theme, and a ported Pin Vandaag payment module that drives Worldline/CCV
terminals over a cloud REST API. Migration is bridge-first: mirror the incumbent
database read-only to a queryable twin, ETL it into Odoo, and run both until the
venue is happy.

## License

MIT for docs/tooling; LGPL-3 for the Odoo modules. See `LICENSE` and `NOTICE.md`.
