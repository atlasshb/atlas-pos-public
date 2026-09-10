# 11 — Open-source POS projects (worldwide)

A working list of the open-source (and open-core) point-of-sale projects we
looked at while choosing a backbone. URLs are the canonical upstreams; where a
project has no active upstream we say so.

> This is engineering research, not legal advice. **Verify each project's
> license before commercial use** — several use licenses that are unsuitable
> for white-labelling.

## Full ERP + POS

| Project | Stack | License | Repo / site | Notes |
|---|---|---|---|---|
| **Odoo Community** | Python / PostgreSQL / JS | LGPL-3 | https://github.com/odoo/odoo | The only OSS POS we found with a **payment-terminal plugin registry**. `point_of_sale` and `pos_restaurant` ship in Community; IoT/certified-hardware layer is Enterprise. **Our chosen backbone.** |
| **ERPNext** (+ Frappe) | Python / MariaDB | GPL-3 | https://github.com/frappe/erpnext | Full open-source ERP with a POS module. No terminal abstraction — an integrated card terminal needs a custom driver. |
| **URY** | Frappe / Python | GPL-3 | https://github.com/ury-erp/ury | Restaurant extension for ERPNext (KDS, tables). Same terminal limitation. |
| **Dolibarr** | PHP / MySQL | GPL-3 | https://github.com/Dolibarr/dolibarr | ERP/CRM with a POS module; lighter than Odoo/ERPNext. |

## Dedicated (single-purpose) POS

| Project | Stack | License | Repo / site | Notes |
|---|---|---|---|---|
| **Open Source Point of Sale (OSPOS)** | PHP / MySQL | MIT | https://github.com/opensourcepos/opensourcepos | Mature retail POS, Docker image, full inventory/customers/reporting. Retail-oriented; **no true offline mode**. |
| **UniCenta oPOS** | Java (JavaPOS) | GPL-3 | https://unicenta.com/ (community forks e.g. https://github.com/herbiehp/unicenta) | Commercial-grade, since 2010, desktop + browser. JavaPOS-era printing; no cloud terminal layer. |
| **ChromisPOS** | Java / NetBeans | GPL-3 | https://github.com/ChromisPos/ChromisPOS | Openbravo/UniCenta lineage; kitchen-display add-on. Same Java-desktop constraints. |
| **Floreant POS** | Java / Swing | MPL / MRPL | https://github.com/fat-tire/floreantpos | Restaurant-focused. The license is awkward for white-labelling. |
| **POSper** | Java | GPL | SourceForge (dormant) | Older Java POS; little recent activity. |
| **restaurant-pos** (ahmedali5530) | React / SurrealDB | — | https://github.com/ahmedali5530/restaurant-pos | Modern stack, KDS, nice UI; small project — evaluate maturity. |
| **Kasirku** (rezadrian01) | Laravel / React | — | https://github.com/rezadrian01/Kasirku | Indonesian POS with digital menu, thermal printing, Midtrans payments. |

## Commercial cloud POS (context / competitors)

Not open source, listed because they define the market and the pricing
benchmark: **Square**, **Lightspeed Restaurant**, **Toast**, **Clover**,
**Shopify POS**, **Zettle**, **Loyverse** (free tier but closed). They are
ecosystem-locked, and several have region-gated or contract-locked offerings.

## What we concluded

Two structural reasons eliminated most of the field:

1. **Retail-only / no offline** — OSPOS and similar work online but don't give
   you a resilient offline counter.
2. **Java desktop with no REST/cloud payment-terminal layer** — UniCenta,
   ChromisPOS, FloreantPOS, POSper. Printing is JavaPOS-era; card acceptance
   isn't API-driven.

The decisive feature for us was the **terminal plugin registry**: the ability for
a POS payment method to select a backend that talks to a cloud PSP over HTTP.
Odoo Community has it; the Pin Vandaag module uses it. See
`04-pinvandaag-integration.md` and `12-payments-landscape.md`.

## Finding more

- GitHub topic: <https://github.com/topics/point-of-sale>
- GitHub topic: <https://github.com/topics/pos>
- Awesome self-hosted (general, no POS section):
  <https://github.com/awesome-selfhosted/awesome-selfhosted>
