# 16 — DoPos vs Odoo: comparison

A feature-and-fit comparison between **DoBizzz DoPos** (the incumbent) and
**Atlas POS on Odoo 19 Community**. This is analysis, not marketing.

Legend: ✅ native · 🟡 partial / needs config or a module · ⚪ not included
(build or integrate) · — not applicable.

## Licensing & ownership

| | DoPos (DoBizzz) | Atlas POS (Odoo CE) |
|---|---|---|
| Software licence cost | €0 ("gratis") | €0 (LGPL-3) |
| Where the money is | **Per-order / per-delivery commission + couplings** *(Atlas)* | Your own hosting/support; **no per-order commission** |
| Source availability | Closed | Open (LGPL-3) |
| Data ownership | Vendor rail | **You own the database** |
| Contract | None advertised | None |
| Exit path | Not published | SQL dump; no lock-in |

## Core POS

| Capability | DoPos | Odoo 19 CE |
|---|---|---|
| Order capture (takeaway/restaurant) | ✅ | ✅ (`point_of_sale`, `pos_restaurant`) |
| Offline tolerance | ✅ (desktop-local) | ✅ (offline-first POS) |
| Tables / floors | ✅ (agenda/floor map) | ✅ (`pos_restaurant`) |
| All-You-Can-Eat | ✅ (Business/Linux) | ⚪ build a thin module |
| Kitchen ticket / grouped dispatch | ✅ | 🟡 printer routing; KDS is Enterprise |
| Multi-terminal | ✅ (network editions) | ✅ (POS config / multi-session) |
| Multi-venue | — (per-site) | ✅ (per-company DB, consolidated accounting) |

## Delivery & customer-facing

| Capability | DoPos | Odoo 19 CE |
|---|---|---|
| Responsive website + webshop | ✅ vendor-hosted | ✅ (Odoo Website/eCommerce) |
| Own-webshop order flow into POS | ✅ | ✅ (`pos_sale` / online payment) |
| Android / iPhone / Windows app | ✅ | 🟡 PWA / third-party |
| Track & Trace | ✅ | ⚪ build/integrate |
| Delivery-driver tracking | ✅ (DoTrace) | ⚪ integrate (self-order + delivery module) |
| Order-status notifications | ✅ | 🟡 email/SMS/WhatsApp integration |
| Thuisbezorgd (Takeaway.com) coupling | ✅ optional | ⚪ integrate via aggregator API |
| Reservations (agenda) | ✅ | 🟡 website appointment module |

## Payments & accounting

| Capability | DoPos | Odoo 19 CE |
|---|---|---|
| Card acceptance | via coupling | ✅ cloud terminal (Pin Vandaag/Worldline) — see `12-payments-landscape.md` |
| Card data in POS | none (terminal) | none (terminal) |
| Bookkeeping / VAT | ❌ (separate) | ✅ same database, Dutch BTW |
| Invoicing | ❌ | ✅ |
| Reconciliation / reporting | limited | ✅ |

## The honest trade-off

- **DoPos wins on**: it is free, live today, has delivery/track-and-trace/app
  out of the box, and needs no operator to run it. For a takeaway that just
  wants orders flowing, it is low-friction.
- **Odoo CE wins on**: data ownership, no per-order commission, one database
  for counter + books, multi-venue consolidation, open source, and an exit
  path. What it does **not** give you free is the delivery/track-and-trace/app
  layer — that is the build/integrate work.

**Where the value is** *(Atlas)*: eliminate the per-order commission and the
vendor channel while keeping the venue's customer-facing experience. That is
the whole point of the migration — and the reason the delivery/track-and-trace
gap must be solved, not ignored.

## Decision

For venues that primarily **take orders and deliver**, moving to Odoo means
replacing a *product* (order rail + website + app) with a *platform* you own.
That is only worth it if (a) volume is high enough that commission matters, and
(b) the delivery/website/app experience is preserved. See
`17-dopos-to-odoo-migration.md` for the phased plan.
