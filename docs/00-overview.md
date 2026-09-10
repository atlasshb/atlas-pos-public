# 00 — Overview

This documentation set records how Atlas Corporation approached building a
**Point-of-Sale platform on open source**, and what we actually shipped.

## The problem

Small Dutch venues (cafés, restaurants, tailors, take-aways) run on closed
Windows POS packages with a wired card terminal. The workflow is fine; the
problems are ownership, per-seat licensing, no API, and an off-site
bookkeeping silo. We wanted the same counter experience on a stack we control,
with the accounting in one place.

## The approach

1. **Open-source POS landscape scan** — see `01-oss-pos-evaluation.md` and
   `02-odoo-pos-landscape.md`.
2. **Pick a backbone** — Odoo 19 Community, because it is the only OSS POS with
   a payment-terminal plugin registry and it already contains the accounting.
3. **Solve payments without Enterprise** — PIN Vandaag's free LGPL-3 module
   drives Worldline/CCV cloud terminals over REST. We forked and ported it to
   Odoo 19 (`addons/pos_pinvandaag_atlas`).
4. **Provision per venue** — an additive, idempotent seed module
   (`addons/atlas_pos_seed`) plus a theme (`addons/atlas_pos_theme`).
5. **Migrate, don't rip out** — mirror the incumbent POS database read-only to a
   queryable twin on a hub, ETL it into Odoo, run both until the venue is happy.
   See `program/` and `migration/`.
6. **Operate it** — health watch, restore-drill verification and a
   tamper-evident journal (`scripts/`).

## Why publish

The hard parts are not secret: which open-source POS actually supports a card
terminal, what Odoo Community leaves out, how to migrate a venue without
downtime, and how to keep terminals locked down. Publishing the reusable parts
makes the ecosystem a little less wasteful — and it is useful to the payment
and hardware partners we work with.

## Reading order

| Doc | Topic |
|---|---|
| `01-oss-pos-evaluation.md` | The open-source systems we compared |
| `02-odoo-pos-landscape.md` | Odoo POS, Community vs Enterprise, terminals |
| `03-oca-pos-ecosystem.md` | What OCA/pos actually has per version |
| `04-pinvandaag-integration.md` | Pin Vandaag REST API v2 integration |
| `05-payments-architecture.md` | Payment provider boundaries, never-store-PAN |
| `06-migration-strategy.md` | Bridge-first, read-only-twin migration |
| `07-optimumpos-gap-analysis.md` | What an incumbent POS does that we had to match |
| `08-system-context.md` | Actors and ownership boundaries |
| `09-security-compliance.md` | Security & compliance requirements |
| `10-device-printing.md` | Terminals, printers, peripherals |
| `11-oss-pos-projects.md` | Open-source POS projects worldwide + verdicts |
| `12-payments-landscape.md` | Card terminals, PSPs, SoftPOS, open banking |
| `13-world-pos-payments-trends.md` | Market-level trends (indicative) |
| `14-architecture-diagrams.md` | Mermaid architecture diagrams |
| `infra/` | Self-hosted infrastructure patterns & incident lessons (de-identified) |
| `sources.md` | Source links |
