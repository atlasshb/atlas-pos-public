# 07 — DoPos gap analysis

What the incumbent (**DoBizzz DoPos**) does that a venue expects, and how Odoo
19 Community closes each gap. Companion to `16-dopos-vs-odoo.md` (comparison)
and `17-dopos-to-odoo-migration.md` (migration plan).

The question behind this document: **if we move a takeaway/delivery venue off
DoPos, what must we match so the switch is invisible to its customers and
painless for its staff?**

## Gap matrix

| DoPos capability | Odoo 19 CE coverage | Action |
|---|---|---|
| Order capture at peak | ✅ `point_of_sale` | Configure |
| Tables / floors | ✅ `pos_restaurant` | Configure |
| Menu + prices + BTW | ✅ products / `account.tax` | Migrate + map |
| Multi-terminal | ✅ POS config | Configure |
| All-You-Can-Eat | ⚪ | Thin module or config |
| Kitchen dispatch / tickets | 🟡 printer routing | Configure; KDS is Enterprise |
| Own webshop + online orders | ✅ Odoo Website/eCommerce + `pos_sale` | Build + brand |
| Track & Trace | ⚪ | Build tracking page / integrate |
| Delivery driver app | ⚪ | Integrate or keep 3rd party |
| Order-status notifications | 🟡 | Email/SMS/WhatsApp integration |
| Reservations / agenda | 🟡 | Website appointment module |
| Thuisbezorgd coupling | ⚪ | Aggregator integration |
| Card payments | ✅ cloud terminal (`pos_pinvandaag_atlas`) | Configure |
| Accounting / VAT / invoices | ✅ (superior: same DB) | Configure `l10n_nl` |
| Reporting / consolidation | ✅ (superior) | Configure |

## Bridge-vs-replace rules

1. **Keep the customer experience.** The website, ordering, status and tracking
   are the venue's public face. Do not cut them over until parity is real.
2. **Own the data.** Every migrated domain must land in a database the venue
   controls and can export.
3. **No per-order commission.** The whole point of leaving DoPos is to remove
   the volume-based rail. Odoo gives that; the delivery/website work is the
   price.
4. **Thin modules, not forks.** Extend Odoo with small LGPL-3 modules; never
   fork core.
5. **Mirror read-only.** Never touch the live DoPos system.

## Where Odoo is clearly better

- One database for counter **and** books (VAT, invoices, reconciliation).
- Multi-venue consolidation via per-company databases.
- No per-order commission; no vendor lock on the order rail.
- Open source (LGPL-3), auditable, with an exit path that is just a SQL dump.

## Where DoPos is ahead (be honest)

- Delivery, Track & Trace, driver app and Track & Trace are **out of the box**;
  in Odoo they are build/integrate work.
- Zero operator effort — it is a managed product; Odoo is a platform you run.

## Realism memo

Migrating a high-volume delivery venue is a **project**, not a settings change.
Sequence: (1) parity on selling, (2) books in the same DB, (3) website/orders,
(4) delivery/tracking, (5) cutover. Ship each phase behind a working rollback.
If a venue cannot tolerate the delivery/website build, keep a third-party
delivery platform during the transition rather than drop the experience.

## Required extensions (engineering backlog)

- `pos_ayce` — All-You-Can-Eat pricing/rules.
- Delivery + tracking page + status notifications.
- Thuisbezorgd / aggregator connector.
- Reservation/agenda page.
- Driver app or PWA.

Each is a candidate for its own small LGPL-3 module in `addons/`.
