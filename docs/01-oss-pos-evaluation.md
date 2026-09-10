# 01 — Open-source POS evaluation

Atlas evaluated the practical open-source options for running a hospitality /
retail counter with an integrated card terminal. This is the summary; the raw
landscape notes are in `02-odoo-pos-landscape.md` and the OCA specifics in
`03-oca-pos-ecosystem.md`.

## Systems evaluated

| System | Stack | Card terminal integration | Verdict |
|---|---|---|---|
| **Odoo 19 Community** | Python / PostgreSQL / JS | **Plugin registry**; vendor modules (e.g. Pin Vandaag, Adyen, Stripe, Mollie) drive cloud terminals | **Chosen.** Only OSS POS with a maintained Dutch terminal integration and the accounting in the same database. |
| Odoo 19 Enterprise | + IoT | Native certified-terminal + IoT box, KDS | Not chosen: per-user licensing, and the IoT layer is what we wanted to avoid. |
| **ERPNext + URY** | Python / MariaDB | URY provides a POS; no first-class NL Worldline/CCV module | Closest full-ERP alternative; rejected on terminal integration. |
| **UniCenta oPOS** | Java (JavaPOS) | None (REST exists but no cloud terminal layer) | Rejected: JavaPOS-era printing, separate bookkeeping. |
| **ChromisPOS** | Java (Openbravo/UniCenta fork) | None | Rejected: same family, kitchen-display focus. |
| **FloreantPOS** | Java | None | Rejected: restaurant-oriented, discontinued momentum. |
| **OpenSourcePOS / OSPOS** | PHP / MySQL | None | Considered for a lightweight venue; rejected as a bookkeeping silo. |
| `restaurant-pos` (ahmedali5530) | Web | None | Prototype-quality; rejected. |
| Kasirku | Web | None | Not evaluated in depth; rejected on maturity. |

## Why Odoo Community

- **POS is in Community.** `point_of_sale` and `pos_restaurant` (floors, tables,
  takeaway) are Community modules in 19.0. Only the IoT/certified-hardware layer
  and some regional terminal drivers are Enterprise.
- **The terminal plugin registry is the decider.** A payment method can select a
  terminal backend that talks to a cloud PSP. That is exactly the seam the
  Pin Vandaag module uses, so no IoT box is needed.
- **One database for counter and books.** No nightly export into a second
  system; the POS closes into the same ledger that produces the VAT return.
- **Modules are the extension point.** Rather than fork core, we add a thin
  per-venue seed pack and, where needed, community modules under LGPL-3.

## What we deliberately did *not* do

- Build a POS front-end from scratch — the Odoo POS web UI is good and
  maintained.
- Buy into Enterprise just for the IoT box — the cloud-API route removes the
  need.
- Adopt a Java desktop POS — it would have re-created the very silo we were
  eliminating.

## Licensing note

Odoo Community and OCA modules are LGPL-3. The Pin Vandaag module is LGPL-3.
Our own modules are released under LGPL-3 so they can be linked with the Odoo
framework without friction.
