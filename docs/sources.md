# Sources — Odoo POS Landscape & Pin Vandaag Integration

Deduplicated, categorized list of every source URL gathered. Date compiled: 2026-06-30.

---

## A. Odoo official documentation (POS, terminals, IoT, releases)

- <https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals.html> — Odoo 19 POS payment-terminal overview (list of supported integrated terminals).
- <https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals/worldline.html> — Odoo 19 Worldline doc; states native Worldline **requires an IoT system**, CTEP protocol, Yomani XR/Yoximo, BE/NL/LU only.
- <https://www.odoo.com/documentation/17.0/nl/applications/sales/point_of_sale/payment_methods/terminals/worldline.html> — Odoo 17 (NL) Worldline doc; Worldline option appears only after installing the IoT app.
- <https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/payment_methods.html> — Odoo 18 POS payment-methods doc (Manual vs Terminal integration field).
- <https://www.odoo.com/odoo-19-release-notes> — Odoo 19 release notes (POS presets, dark mode, quick payment buttons, kiosk, QR menus, course firing).
- <https://www.odoo.com/odoo-18-release-notes> — Odoo 18 release notes (OWL 2 POS refactor, PWAs).
- <https://www.odoo.com/app/iot> — Odoo IoT app page (IoT Box, peripherals incl. payment terminals).
- <https://www.odoo.com/app/iot-faq> — IoT FAQ; IoT Box not in free Community; subscription per box.
- <https://www.odoo.com/page/editions> — Odoo Community vs Enterprise editions comparison.

## B. Odoo forums (practitioner sentiment & config gotchas)

- <https://www.odoo.com/forum/help-1/difference-between-enterprise-and-community-for-the-pos-module-220572> — Community lacks official payment-terminal integrations.
- <https://www.odoo.com/forum/help-1/payment-terminal-with-odoo-pos-129599> — practitioners self-building terminal integrations (Yenthe Van Ginneken on Atos/Worldline; Windows-service+ajax; C-TAP commercial module).
- <https://www.odoo.com/forum/help-1/pin-payment-terminal-205767> — Developer mode needed to expose terminal config fields.
- <https://www.odoo.com/forum/help-1/pos-how-to-give-refund-with-stripe-terminal-244499> — refunds are a chronic weak spot across terminal integrations.
- <https://www.odoo.com/forum/help-1/connect-iotbox-to-odoo-community-212760> — cannot use IoT Box with Community; must move to Enterprise.
- <https://www.odoo.com/forum/help-1/how-to-connect-windows-virtual-iot-with-the-odoo-18-community-version-265867> — Windows virtual IoT and Community limitations.
- <https://www.odoo.com/forum/help-1/pos-customization-app-upgrade-from-odoo-16-to-18-272799> — 16→18 POS frontend break; custom modules need rewriting.

## C. Odoo GitHub (issues, PRs)

- <https://github.com/odoo/odoo/pull/35702> — extracts a generic payment interface from `pos_iot` so cloud terminals (Adyen) work **without IoT** in Community.
- <https://github.com/odoo/odoo/issues/194532> — corroborates `OEEL-1` (Enterprise) licensing of enterprise-only modules.
- <https://github.com/odoo/odoo/issues/142518> — enterprise module licensing context.
- <https://github.com/odoo/odoo/issues/33752> — POS refund math bug (`Math.abs(total-paid)`) on card-only configs; keep a cash method / use credit notes.

## D. Pin Vandaag — product, docs, API, partners

- <https://www.pinvandaag.nl/odoo-koppeling/> — the Odoo koppeling page (free module, cloud, CCV+Worldline, no same-network requirement).
- <https://www.pinvandaag.nl/kassa-koppeling/> — kassa koppeling page; full CTAP terminal list (Worldline Yomani/Yoximo/Valina; CCV Pax/Verifone).
- <https://www.pinvandaag.nl/docs/rest-api/> — REST API **V1** docs (base /V1/instore; create/status/cancel/refund/ctmp/mailreceipt/date).
- <https://www.pinvandaag.nl/docs/rest-api-2/> — REST API **V2** docs (X-API-KEY; /start, /status, /stop, /refund, /mail, /last_transaction, dashboard search, iban name-check).
- <https://www.pinvandaag.nl/partners/> — partner program (Kassa Partners, resellers, terminal suppliers).
- <https://www.pinvandaag.nl/samenwerken/> — partner/"work with us" page (**404 at fetch time — partner terms not retrievable**).
- <https://www.pinvandaag.nl/product/worldline-yomani-xr-ml/> — Yomani XR/ML product page ("Kassa koppeling mogelijk: Ja"; ECR cable; pricing).
- <https://aanmelden.pinportal.nl/external/register-form> — module/terminal registration portal.
- <https://github.com/orgs/Pin-Voordeel-Bv/repositories> — Pin Vandaag GitHub org; **PHP libs only, no Odoo repo**.
- <https://github.com/Pin-Voordeel-Bv/rest-api> — bare REST-API repo (README fails to load; last updated 2022).
- Contact: helpdesk@pinvandaag.nl, +31 85 5601201; developer/API line 085 5601203.

## E. The Pin Vandaag Odoo module (`pos_pinvandaag`)

- <https://github.com/coopiteasy/pinvandaag-odoo> — source-available mirror; **16.0 only**, last push 2024-02-12, LGPL-3; the reference implementation.
- <https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/__manifest__.py> — 16.0 manifest (lean, `point_of_sale`-only dep).
- <https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/const.py> — `API_URL = https://rest-api.pinvandaag.com/V1/`; endpoint constants.
- <https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/models/pos_payment_method.py> — create→poll cloud flow; Terminal ID + API Key config fields.
- <https://api.github.com/repos/coopiteasy/pinvandaag-odoo> — repo metadata (stars/forks/branch).
- <https://github.com/coopiteasy/pinvandaag-odoo/forks> — fork list.
- <https://github.com/jurcello/pinvandaag-odoo/branches/all> — fork with a 16.0 routing bugfix branch (Sep 2025, most recent community activity).
- <https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag> — **Apps Store 19.0 build** (FREE, LGPL-3, Worldline+CCV, On-Premise/Online/.sh).
- <https://apps.odoo.com/apps/modules/17.0/pos_pinvandaag> — Apps Store 17.0 build (core-only deps: account, point_of_sale, mail, stock; ~910 LOC).

## F. OCA & other community/GitHub modules

- <https://github.com/OCA/pos> — OCA POS repo (341★, AGPL-3, default 18.0). Generic terminal module, no Worldline/CCV/CTAP.
- <https://raw.githubusercontent.com/OCA/pos/18.0/pos_payment_terminal/README.rst> — `pos_payment_terminal` README; Ingenico/Telium (France) via POSbox; no cloud API.
- <https://github.com/OCA/pos/tree/17.0> — confirms `pos_payment_terminal` is **absent** from the 17.0 branch.
- <https://apps.odoo-community.org/shop/pos-payment-terminal-1859> — OCA `pos_payment_terminal` Apps Store listing (POSbox/local).
- <https://apps.odoo.com/apps/modules/8.0/pos_payment_terminal> — older OCA terminal module listing (Start-Transaction button pattern).
- <https://apps.odoo.com/apps/modules/13.0/pos_payment_terminal> — OCA terminal module (13.0).
- <https://apps.odoo.com/apps/modules/browse?search=pos_payment_terminal> — Apps Store search (18.0 listed; no 19.0).
- <https://github.com/OCA/l10n-netherlands> — Dutch localization; no POS payment modules.
- <https://github.com/dieg0-a/posagentpro> — free Windows "software IoT box" for Community; printers + cash drawers only, **no card terminals**.
- <https://github.com/coopiteasy/addons> — Coop IT Easy addons; SEPA Direct Debit payment modules only (no terminal bridge).

## G. Third-party edition comparisons & IoT analysis

- <https://www.cybrosys.com/blog/what-are-the-differences-between-community-enterprise-in-odoo-18-pos> — Odoo 18 Community-vs-Enterprise POS feature breakdown; "Community… lacks direct connectivity with any payment terminal."
- <https://www.farishtatech.com/odoo-community-edition-pos-point-of-sale-features-required-modules/> — Community POS features/limitations; no official terminal integrations.
- <https://www.odooskillz.com/blog/odoo-skillz-insights-1/odoo-pos-iot-box-alternatives-2026-275> — IoT Box alternatives; IoT Box not usable on Community, ~US$30/mo/box on Enterprise.

---

## Uncertain / unretrievable at fetch time

- <https://www.pinvandaag.nl/samenwerken/> — **404**; partner commission/revenue-share terms not retrievable.
- BE kassa-partner page — **522** at fetch time; partner terms not retrievable.
- `odoo/enterprise` raw manifests (`pos_adyen`/`pos_six` etc.) — **private repo, 404**; `OEEL-1` status inferred via issue tracker + documented behavior, not a verbatim manifest quote.
- Odoo 19 `pos_pinvandaag` exact `__manifest__.py` — Apps Store distributes a zip (not a public Git branch); 19.0 listing names extra deps vs the lean 16.0 manifest — verify after download.
