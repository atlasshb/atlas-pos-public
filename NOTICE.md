# NOTICE

## Third-party components and attribution

### Pin Vandaag Odoo module (`addons/pos_pinvandaag_atlas`)

This module is a modified fork of **`pos_pinvandaag`** published by
**PIN Vandaag B.V.** under the GNU Lesser General Public License v3.0 (LGPL-3.0).

- Upstream vendor: PIN Vandaag B.V. (NL) — <https://www.pinvandaag.nl>
- Upstream license: LGPL-3.0
- Nature of modification: the frontend payment widget was ported from the
  original Odoo 15–17 `PosPaymentInterface` API to the Odoo 19
  `PaymentInterface` + `register_payment_method()` API (modelled on
  `pos_adyen` 19.0), plus minor manifest/asset-path changes.

Per LGPL-3.0, this modified version remains under LGPL-3.0. The upstream
copyright notice is retained. No endorsement by PIN Vandaag B.V. is implied.

### Odoo

These modules run on **Odoo Community Edition** (LGPL-3.0).
<https://www.odoo.com>

### OCA

Where OCA modules are referenced in `docs/`, they are from
<https://github.com/OCA/pos> (LGPL-3.0) unless stated otherwise.

## De-identification notice

This public export was scrubbed of client-identifying data, internal IP
addresses, hostnames, terminal identifiers and any credential material.
Placeholders used:

- `venue_a`, `venue_b`, … — client venues
- `192.0.2.10` — an example tailnet address (RFC 5737 documentation range)
- `<VPS-IP>`, `<VPS-VIP>`, `<HOSTING-IP>` — infrastructure addresses
- `<TERMINAL-ID>` — a card terminal identifier
- `example.com` subdomains — internal service hostnames

No API keys, passwords, tokens or personal customer data are included.
