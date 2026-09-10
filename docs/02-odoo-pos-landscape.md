# The Odoo POS Landscape & Pin Vandaag Integration for Worldline Yomani Terminals

**Prepared for:** Atlas Corporation (AI-ops + Odoo ERP, Tilburg NL)
**Context:** Odoo 19 **Community** Point of Sale for small NL hospitality/retail clients running **Worldline YOMANI** card terminals.
**Date:** 2026-06-30
**Bottom line:** Native integrated payment terminals in Odoo POS are Enterprise- and/or IoT-gated. For Odoo 19 **Community** + existing **Worldline Yomani** terminals, the only realistic integrated route is a **third-party cloud REST koppeling — Pin Vandaag (Tilburg)** — which ships a free, Community-installable Odoo module (`pos_pinvandaag`, Odoo 15–19, LGPL-3) over a cloud API with no IoT box and no same-network requirement.

> **Citation note:** Every factual section ends with the source URLs it relies on. Items marked **[UNCERTAIN]** could not be fully verified and must be confirmed before being put in front of a paying client.

---

## 1. Executive summary

1. **The core POS engine is identical in Community and Enterprise.** The open-source `point_of_sale` module (orders, products, sessions, cash, and a *manual* non-integrated card method) ships in both editions. The edition difference is a set of **Enterprise-only add-on modules** (license `OEEL-1`) in the closed `odoo/enterprise` repository.
2. **Integrated card terminals are the key gated capability.** Modules that auto-push the amount to a terminal and read back the result (`pos_adyen`, `pos_stripe`, `pos_six`, `pos_worldline`/`pos_iot`, `pos_mercado_pago`, etc.) are not in the Community `odoo/odoo` repo for the IoT-based ones — hence Atlas's clients are stuck with a **manual** card method today.
3. **Important correction to the "all Enterprise-only" premise:** `pos_adyen` and `pos_stripe` were deliberately extracted into the **Community** codebase and use a **cloud Terminal API with no IoT box** ([odoo/odoo PR #35702](https://github.com/odoo/odoo/pull/35702)). But they only drive **Adyen/Stripe** terminals — you cannot point them at a Worldline Yomani. So the accurate statement is: *there is no native, Community, no-extra-hardware way to drive a **Worldline/CCV CTAP** terminal from Odoo POS.*
4. **Native Worldline is doubly gated.** Odoo's own docs: *"Connecting a Worldline payment terminal to Odoo requires an IoT system."* The IoT system (IoT Box / virtual IoT) is an **Enterprise** feature (~US$30/month/box) and implies same-LAN hardware coupling. Worldline native covers **Yomani XR + Yoximo** via the CTEP protocol, restricted to **BE/NL/LU**.
5. **Pin Vandaag fills exactly this gap.** A cloud-initiated REST API (kassa initiates → amount appears on the Yomani automatically), no IoT box, no same-network requirement, plus a **free, published, Community-compatible** Odoo Apps Store module `pos_pinvandaag` (Odoo 15–19, LGPL-3, core-only deps).
6. **One load-bearing unknown remains:** Odoo 19 **Community** compatibility of the published module is plausible (pure cloud REST, no Enterprise dep) and the Apps Store lists a 19.0 build, but should be **confirmed directly with Pin Vandaag** and the downloaded `__manifest__.py` checked before promising clients. **[UNCERTAIN]**

---

## 2. Odoo POS: Community vs Enterprise

### 2.1 What is the same

The server-side core is one module — `point_of_sale` — shipped in both editions. In any edition you can create a POS payment method (*Point of Sale → Configuration → Payment Methods*). A method backed by a Cash or Bank journal works fully in Community: this is the **"manual" card method** Atlas uses today — the cashier keys the amount into the Yomani by hand, then marks the order paid in Odoo. **There is no link between Odoo and the terminal.**

Stable core data models across versions: `pos.config` (register), `pos.payment.method` (a tender; carries an *Integration* selection — Manual vs Terminal — and a `use_payment_terminal` field naming the provider), `pos.order` / `pos.order.line`, `pos.payment`, `pos.session`. `product.template` / `product.product` feed POS via "Available in POS" flags.

Sources: <https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals.html>, <https://www.odoo.com/forum/help-1/difference-between-enterprise-and-community-for-the-pos-module-220572>

### 2.2 What is Enterprise-gated

The edition difference for POS is **add-on modules** under license `OEEL-1` (Odoo Enterprise Edition License v1.0) in the closed `odoo/enterprise` repo (license status corroborated via Odoo's public issue tracker: <https://github.com/odoo/odoo/issues/194532>, <https://github.com/odoo/odoo/issues/142518>). The Cybrosys edition comparison states it plainly for Odoo 18: *"Odoo Community is not a strong choice for companies that accept a variety of payment methods because it lacks direct connectivity with any payment terminal."*

**Enterprise-only (or only via paid/third-party add-ons in Community) POS capabilities:**

1. **Integrated payment terminals** (Adyen, Stripe, SIX, Worldline, Ingenico, Viva, Mercado Pago, Razorpay…) — *the central one for Atlas*
2. **IoT Box / IoT app** (printers, scales, scanners, cash drawers, customer display, and the IoT-based terminals above)
3. **Customer Display** (second screen) — "exclusively available to Enterprise users"
4. **Restaurant Floor & Table management**
5. **Bill splitting**
6. **Preparation / Kitchen display**
7. **Self-Order / Kiosk** (QR self-ordering, kiosk PWA)
8. **Loyalty / gift cards / vouchers**
9. **Robust offline mode**
10. **Advanced POS reporting/analytics**

Several of these (floor/table, basic kitchen printing, loyalty-like) have **unofficial Community third-party** equivalents on the Apps Store, but none provide a vendor-backed integrated Worldline/CTAP terminal coupling.

Sources: <https://www.cybrosys.com/blog/what-are-the-differences-between-community-enterprise-in-odoo-18-pos>, <https://www.farishtatech.com/odoo-community-edition-pos-point-of-sale-features-required-modules/>, <https://www.odoo.com/page/editions>, <https://www.odoo.com/app/iot>

---

## 3. Why Community is stuck with a manual card method (the central fact)

- **INTEGRATED** terminals (Odoo pushes the amount, reads back success/failure) are implemented by separate provider modules: `pos_adyen`, `pos_stripe`, `pos_six`, `pos_mercado_pago`, `pos_razorpay`, `pos_viva_wallet`, `pos_worldline` / `pos_iot`, etc.
- For the **IoT-based** ones (Worldline, SIX, Ingenico/Telium) these ship in `odoo/enterprise` and require an Enterprise subscription **and** an IoT Box.
- For the **cloud-API** ones (`pos_adyen`, `pos_stripe`) the modules live in the **Community** codebase — but they only talk to Adyen/Stripe, not Worldline.

**Net:** There is no native, Community, no-extra-hardware way to drive a **Worldline/CCV CTAP** terminal from Odoo POS. That is the precise gap a third-party cloud API (Pin Vandaag) fills.

Sources: <https://github.com/odoo/odoo/pull/35702>, <https://www.cybrosys.com/blog/what-are-the-differences-between-community-enterprise-in-odoo-18-pos>

---

## 4. The Worldline-specific reality (most relevant to Atlas)

Odoo's native Worldline support is **doubly gated**:

- Official Odoo 19 doc: **"Connecting a Worldline payment terminal to Odoo requires an IoT system."** Only by installing the IoT app does Worldline (and Ingenico BENELUX) become selectable as a payment-terminal option.
- The **IoT app / IoT Box is also Enterprise-only**: community sources state it "cannot be used with the Odoo Community edition," and connecting a box to a production database auto-adds a **~US$30/month/box** subscription on the Enterprise contract. **[UNCERTAIN — verify live pricing before quoting a client.]**
- Native Worldline supported models: **Yomani XR and Yoximo**, using the **CTEP** protocol (configured as "ECR protocol": hostname + port; port 9001 for IoT Box, 9050 for Windows virtual IoT; technician menu pwd 1235789). Availability restricted to **Belgium, Netherlands, Luxembourg**.

**Implication for Atlas:** Even buying Enterprise would not be "free + cloud" — it forces an on-site IoT Box and same-network coupling. The native path and the Pin Vandaag path solve the same problem with **opposite architectures** (local hardware bridge vs cloud REST).

Sources: <https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals/worldline.html>, <https://www.odoo.com/documentation/17.0/nl/applications/sales/point_of_sale/payment_methods/terminals/worldline.html>, <https://www.odooskillz.com/blog/odoo-skillz-insights-1/odoo-pos-iot-box-alternatives-2026-275>, <https://www.odoo.com/app/iot-faq>, <https://www.odoo.com/forum/help-1/how-to-connect-windows-virtual-iot-with-the-odoo-18-community-version-265867>

---

## 5. POS evolution across Odoo 16 / 17 / 18 / 19 (the migration risk)

**Data model:** stable across versions (`pos.config`, `pos.payment.method`, `pos.order(.line)`, `pos.payment`, `pos.session`). A custom payment provider is implemented by adding a value to `pos.payment.method`'s payment-terminal selection plus a matching OWL JS `PaymentInterface` class — the integration point any Pin Vandaag-style module hooks into.

**Frontend architecture (the big break):**
- **16 → 17:** incremental OWL changes.
- **17 → 18:** **MAJOR POS frontend refactor.** OWL 2 reactivity (no manual `this.render()`); many JS classes/methods and XML templates replaced; `ProductItem.js/.xml` and screen structure rewritten. Custom POS modules generally **must be rewritten** 16/17 → 18. Dedicated PWAs introduced (POS, Kiosk, Shop Floor).
- **18 → 19:** UX overhaul — preset POS configurations, dark mode, revamped kiosk UI, **quick one-click payment buttons**, combo/menu improvements, restaurant presets (eat-in/takeaway/delivery), free QR mobile menus with allergens, course firing, minimal access rights for seasonal staff. 19.x ships on a faster .1/.2/.3 cadence.

**Takeaway for Atlas:** Any Pin Vandaag Odoo module **must be version-pinned**. A v19 deployment needs a v19-built module; do **not** assume a v17 community payment module runs on v19 — the 17→18 break means substantial rework, and 19 added further UI changes.

Sources: <https://www.odoo.com/odoo-19-release-notes>, <https://www.odoo.com/odoo-18-release-notes>, <https://www.odoo.com/forum/help-1/pos-customization-app-upgrade-from-odoo-16-to-18-272799>, <https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/payment_methods.html>

---

## 6. Community-capable options for Worldline/CCV/CTAP terminals

| Option | Runs on Community? | Keeps Yomani? | Cloud / no-IoT? | Verdict |
|---|---|---|---|---|
| **A. Manual method** (status quo) | Yes | Yes | n/a | Double entry, keying errors, no auto-reconciliation |
| **B. Odoo native Worldline (CTEP)** | **No** (Enterprise+IoT) | Yes | No (same-LAN IoT) | Not viable on Community |
| **C. Cloud native `pos_adyen`/`pos_stripe`** | Yes | **No** | Yes | Wrong acquirer — needs Adyen/Stripe terminals |
| **D. OCA `pos_payment_terminal`** | Yes | Partial | **No** (POSbox/IoT bridge, same-LAN, Telium-centric) | Fallback only; no clean 19.0, no Yomani-cloud |
| **E. Pin Vandaag cloud REST + module** | **Yes** | **Yes** | **Yes** | **Recommended fit** |

**Option E is the only path that satisfies all four constraints** (Community, keep Yomani, cloud auto-amount, no IoT).

**What a Community integration must replicate (the generic contract):**
`createPaymentRequest(amount, ref)` → terminal lights up; `pollStatus(ref)` → success/failed/pending; `cancel(ref)`; `refund(amount)`. Pin Vandaag's API maps 1:1 onto this.

Sources: <https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals/worldline.html>, <https://github.com/odoo/odoo/pull/35702>, <https://apps.odoo-community.org/shop/pos-payment-terminal-1859>

---

## 7. The GitHub / OCA / community module ecosystem

### Tier 1 — The direct-fit repo

**`coopiteasy/pinvandaag-odoo`** — <https://github.com/coopiteasy/pinvandaag-odoo>
- Module `pos_pinvandaag`: *"Make payments happen with CCV/WorldLine terminals inside the POS."* Depends only on `point_of_sale`. **LGPL-3.** Author: Pin Vandaag B.V. (committers: coopiteasy / huguesdk).
- **THE** source-available module that bridges Odoo POS to Worldline/CCV CTAP without Enterprise.
- **Stale on GitHub:** default/only branch `16.0`, 3 commits, last push **2024-02-12**, 0 stars / 2 forks.
- **Architecture (verified from `const.py` + `models/pos_payment_method.py`):** pure **cloud REST**, no IoT box, no same-network requirement. `API_URL = https://rest-api.pinvandaag.com/V1/`. Cloud-initiated create → **poll** status (synchronous HTTP POST, 60s timeout) until done; also `cancel`, `refund`, `getLatestTransaction`, `mailreceipt`, `terminal/status`, `terminal/ctmp`. Per payment method you configure **Terminal ID** (`pinvandaag_terminal_identifier`) + **API Key** (`pinvandaag_api_key`), plus an optional auto-confirm boolean.
- **Forks (both inactive/non-upgrading):** `jurcello/pinvandaag-odoo` (16.0 + a 16.0 routing bugfix branch, activity Sep 2025 — most recent community activity, NOT a version upgrade); `Therp/pinvandaag-odoo` (dormant, no public upgrade branch found). **[UNCERTAIN — Therp branches not directly inspected.]**

**Odoo Apps Store — `pos_pinvandaag`** — <https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag> (also 15.0/16.0/17.0/18.0)
- This is where Atlas should get the **19.0 build**: FREE, LGPL-3, publisher **PIN Vandaag B.V.**, supports **Worldline + CCV**, deployable On-Premise / Online / .sh (Community-installable). The Apps Store carries 15.0–19.0; GitHub does not.
- ~910 LOC; the 17.0 listing names **core-only** deps (`account`, `point_of_sale`, `mail`, `stock`) — **no** Enterprise IoT dependency, consistent with the cloud architecture. Onboarding: **helpdesk@pinvandaag.nl**.
- **[UNCERTAIN]** The **19.0** store listing names extra deps (Invoicing/Discuss/Inventory) vs the lean `point_of_sale`-only 16.0 GitHub manifest — verify the actual 19.0 `__manifest__.py` after download.

### Tier 2 — OCA (generic, but NOT CTAP/Worldline)

**`OCA/pos`** — <https://github.com/OCA/pos> (341★, AGPL-3, default 18.0, actively maintained)
- **`pos_payment_terminal`** (in 16.0 and 18.0; **absent from 17.0**; no 19.0 build): generic "Send"/"Start Transaction" button pushing amount/currency/mode to a **POSbox/IoTBox/pywebdriver**. Beta. README documents **Ingenico/Telium (France) only** — **no** Worldline/CCV/CTAP, **no** cloud API. C-TAP is the same protocol *family* as CCV/Worldline, but support is local-bridge and Telium-centric.
- `hw_telium_payment_terminal`: POSbox-side Telium/Ingenico driver — irrelevant to a cloud/CTAP setup.
- `pos_payment_method_cashdro`: CashDro **cash** machines — not card terminals, not Yomani.
- **Net:** OCA gives generic plumbing + France-centric Ingenico drivers, nothing for Worldline/CCV CTAP, nothing cloud-API-based, no 19.0 terminal build.

**`OCA/l10n-netherlands`** — <https://github.com/OCA/l10n-netherlands>: Dutch localization only (postcode, provinces, BTW, NUTS). **No** POS payment modules.

### Tier 3 — Adjacent / IoT-box alternatives

**`dieg0-a/posagentpro`** — <https://github.com/dieg0-a/posagentpro>: a free C++ Windows "software IoT box" for Odoo Community POS — **printers + cash drawers ONLY, explicitly NO card terminals.** Complementary to Pin Vandaag (Pin Vandaag = card; PosAgentPro = printer/drawer), not a substitute.

**`coopiteasy/addons`** — <https://github.com/coopiteasy/addons>: Coop IT Easy's general repo (AGPL-3, active). Payment modules are **SEPA Direct Debit only** — no POS/Worldline/CCV terminal modules. Same maintainer org as the Pin Vandaag mirror, so a credible NL/BE partner to engage.

Sources: <https://github.com/coopiteasy/pinvandaag-odoo>, <https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/const.py>, <https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/models/pos_payment_method.py>, <https://github.com/jurcello/pinvandaag-odoo/branches/all>, <https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag>, <https://apps.odoo.com/apps/modules/17.0/pos_pinvandaag>, <https://github.com/OCA/pos>, <https://raw.githubusercontent.com/OCA/pos/18.0/pos_payment_terminal/README.rst>, <https://github.com/OCA/pos/tree/17.0>, <https://github.com/OCA/l10n-netherlands>, <https://github.com/dieg0-a/posagentpro>, <https://github.com/coopiteasy/addons>

---

## 8. Pin Vandaag — full technical detail

**Vendor:** Pin Vandaag (pinvandaag.nl), a **Pin Voordeel BV** brand based in **Tilburg**. Cloud-initiated "kassa koppeling" for CTAP terminals: the POS calls the REST API; Pin Vandaag pushes the amount to the terminal over the cloud; the amount appears automatically with **no manual entry** and **no same-network requirement** (terminal can even be on 4G).

### 8.1 Supported terminals (CTAP) — confirmed

- **Worldline (CTAP):** Yomani, Yoximo, **Valina** (kassa-koppeling page).
- **CCV (CTAP):** Pax A77, Pax A920, Verifone V400m, Verifone P400, Verifone Vx680 (**WiFi only**).
- The **Odoo-koppeling** page lists a slightly narrower set (Worldline Yomani/Yoximo; CCV Pax A77/A920, Verifone V400m/Vx680) — **[UNCERTAIN]** Valina and Verifone P400 appear on the general list but are not explicitly named on the Odoo page, so their support *specifically via the Odoo module* (vs raw API) is slightly ambiguous.

### 8.2 REST API — two versions

**V1** — base `https://rest-api.pinvandaag.com/V1/instore` — `terminalId` + `key` as form params. Endpoints (POST): `/transactions/create` (amount in **cents**; optional `callbackUrl`, `ownReference`, `returnUrl`), `/transactions/status`, `/terminal/cancel` (**Worldline only**), `/transactions/mailreceipt`, `/transactions/refund` (**Worldline only**), `/terminal/ctmp` (**Worldline only**), `/transactions/date`. Create response e.g. `{"transactionId":"2405102","status":"started","amount":1,"terminal":"50303253",...}`.

**V2 (recommended)** — base `https://rest-api.pinvandaag.com/V2` — auth via **`X-API-KEY` header** (legacy OAuth2 Basic also supported); returns proper HTTP status codes (200/400/404/500). Endpoints:
- `POST /instore/transactions/start` — `terminal_id`, `amount` (cents); optional `callbackUrl`, `ownReference`, `ReturnUrl` (CCV only). Returns `transactionId`, `status:"started"`.
- `POST /instore/transactions/status` — `terminal_id`, `transaction_id`. State machine **started → success | failed | unknown**; returns receipt + `errorMsg`/incident code. **CCV status refreshes at most every ~30s.**
- `POST /instore/transactions/stop` — cancel. **CCV limited to ~3 cancel attempts/transaction.**
- `POST /instore/transactions/refund` — **Worldline only.**
- `POST /instore/transactions/mail` — email receipt.
- `POST /instore/transactions/last_transaction`; `GET /instore/transactions_dashboard/search` (reporting); `POST /services/iban/name-check`.
- **Partner endpoint** `POST /instore/clients/create` — onboard a sub-merchant programmatically (KVK, IBAN, UBO) — how a kassa-partner like Atlas provisions clients.

**Cloud-initiated "happy flow":** POS POSTs amount + `terminal_id` to `/start` → Pin Vandaag activates the terminal, amount appears on the Yomani → customer taps/inserts → POS receives a **webhook** at `callbackUrl` OR **polls** `/status` → resolves success/failed; receipt available; refund via `/refund` (Worldline).

### 8.3 Pricing

- **Module + REST API: FREE** to integrate. Cloud-based, so the terminal need **not** be on the same network as the POS.
- **Coupling fee: ~€2.50/month per terminal** + per-transaction fees.
- **Test-terminal deposit (borg, refundable on return):** Yomani **€275**, Pax A77 **€399**, Verifone P400 **€499**. Two months free testing; then **€5/month** per terminal if not returned.
- Buying a Yomani XR/ML outright listed at €450 (was €599), optional €15/month service contract. **[UNCERTAIN — verify current rates before any client quote.]**

### 8.4 GitHub / SDK

Pin Vandaag's GitHub org (`Pin-Voordeel-Bv`) has **no Odoo repo** — only PHP libraries, notably **`pinvandaag-pin-php-sdk`** (the V2 PHP SDK), the best reference for replicating V2 endpoints from Odoo's Python.

### 8.5 Contacts / onboarding

- General: **helpdesk@pinvandaag.nl**, **+31 85 5601201**. Developer/API support: **085 5601203** (per V1 docs).
- Module registration: <https://aanmelden.pinportal.nl/external/register-form>.
- Partner program: <https://www.pinvandaag.nl/partners/> (Kassa Partners include Taurus, Bos Systemen, WaiterOne, Optimum POS, etc.; terminal suppliers CCV/Worldline/Ingenico/Sepay). **[UNCERTAIN — exact commission/revenue-share terms not published; request the partner agreement directly. The `samenwerken` page 404'd and the BE kassa-partner page 522'd at fetch time.]**

Sources: <https://www.pinvandaag.nl/odoo-koppeling/>, <https://www.pinvandaag.nl/kassa-koppeling/>, <https://www.pinvandaag.nl/docs/rest-api/>, <https://www.pinvandaag.nl/docs/rest-api-2/>, <https://www.pinvandaag.nl/partners/>, <https://www.pinvandaag.nl/product/worldline-yomani-xr-ml/>, <https://github.com/orgs/Pin-Voordeel-Bv/repositories>, <https://apps.odoo.com/apps/modules/17.0/pos_pinvandaag>

---

## 9. How to combine Odoo POS + Pin Vandaag (integration plan)

**Path 1 — Use Pin Vandaag's ready-made Odoo module (fastest; recommended for a pilot).**
Register → get API key + `terminal_id` → install `pos_pinvandaag` (19.0 from the Apps Store) → set the POS payment method to use the Pin Vandaag terminal. Cost: module free; ~€2.50/mo per terminal. **Verify Odoo 19 Community compatibility and the 19.0 `__manifest__.py` first. [UNCERTAIN]**

**Path 2 — Build a thin Atlas-branded Community module (control + margin).**
A small Odoo 19 Community addon subclassing the POS `PaymentInterface` (same generic interface `pos_adyen` uses), calling the REST API instead of an IoT device:
- `send_payment_request` → `POST /start` (`amount*100`, `terminal_id`, `ownReference` = POS order ref, `callbackUrl` to an Odoo controller).
- poll loop → `POST /status` until success/failed (respect CCV ~30s cache).
- `send_payment_cancel` → `POST /stop`; refund → `POST /refund` (Worldline).
- Store `transactionId` on `pos.payment`; map receipt into the POS payment line.
Use the 16.0 GitHub source (`const.py`, `models/pos_payment_method.py`) and the `pinvandaag-pin-php-sdk` as endpoint references. This replicates the Enterprise `pos_iot` contract over HTTP with zero IoT hardware.

**Partner angle:** `/instore/clients/create` lets Atlas onboard client sub-merchants programmatically and manage terminals via `clients`-scoped dashboard queries — combine with the Kassa Partner program for margin.

Sources: <https://www.pinvandaag.nl/odoo-koppeling/>, <https://github.com/odoo/odoo/pull/35702>, <https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/models/pos_payment_method.py>

---

## 10. Community practitioner notes & gotchas

- **Practitioners DO self-build** `pos.payment.method` integrations. Yenthe Van Ginneken: *"We've done a pretty similar thing for Atos (Worldline)… add an extra button in the POS which then calls a C++ function,"* and notes *"there are very little payment provider connectors in the Odoo POS."* Others bridged via a Windows service + ajax. (forum #129599)
- **Webhook is single-fire (no robust retry yet)** → **polling `/status` is mandatory** as the primary/fallback mechanism, or transactions hang in "started."
- **CCV polling cached ~30s** → don't poll faster; UX feels slow on CCV. **Worldline behaves better.**
- **CCV cancellation limited to ~3 attempts/transaction.**
- **Refund endpoint is Worldline-only** → good for Atlas's Yomani clients; for CCV, refunds are a manual/credit-note workaround.
- **Odoo POS refund math bug history:** card-only configs can choke on refunds because validation does `Math.abs(total - paid)` and demands a cash method ([odoo/odoo#33752](https://github.com/odoo/odoo/issues/33752)). Common workaround: keep a Cash method enabled, or process refunds as credit notes. (Refunds are a chronic weak spot across *all* terminal integrations, incl. Stripe — forum #244499.)
- **Developer mode often required** to expose terminal-config fields on payment methods (forum #205767).
- **Amounts are in cents (integer)** → classic off-by-100 / float-rounding bug source when wiring Odoo float totals into the API.
- **Provider response shapes differ** between CCV and Worldline despite identical status labels — test per provider.

Sources: <https://www.odoo.com/forum/help-1/payment-terminal-with-odoo-pos-129599>, <https://github.com/odoo/odoo/issues/33752>, <https://www.odoo.com/forum/help-1/pos-how-to-give-refund-with-stripe-terminal-244499>, <https://www.odoo.com/forum/help-1/pin-payment-terminal-205767>, <https://www.pinvandaag.nl/docs/rest-api-2/>

---

## 11. Recommendation for Atlas

For NL hospitality/retail clients on **Odoo 19 Community** with existing **Worldline Yomani** terminals, **Pin Vandaag (Option E)** is the clear best fit and the only path satisfying all four constraints (Community, keep Yomani, cloud auto-amount, no IoT).

1. **Pilot via Path 1** — deploy `pos_pinvandaag` 19.0 to validate Odoo 19 Community compatibility on a real register.
2. **Then consider Path 2** — an Atlas-branded thin module + the Kassa Partner program for control and margin; budget for self-maintaining a 19.0 fork since the public GitHub mirror stalled at 16.0 in 2024.
3. **Avoid Option B** (Enterprise + IoT economics); treat **Option D (OCA)** as a fallback only if a same-LAN self-hosted POSbox is acceptable.
4. **Build in:** polling fallback (don't rely on webhooks), cents handling, Developer-mode config, and a refund/credit-note workflow.

---

## 12. Open items to confirm before committing clients **[UNCERTAIN]**

1. **Odoo 19 *Community* compatibility** of `pos_pinvandaag` — architecturally fine (pure cloud REST, core-only deps) and a 19.0 Apps Store listing exists, but confirm directly with Pin Vandaag and inspect the downloaded 19.0 `__manifest__.py` (the 19.0 listing names extra deps vs the lean 16.0 manifest).
2. **Partner commission / revenue-share** euro terms — not published; request the agreement (085 5601203).
3. **Live pricing** (€2.50/mo coupling, ~US$30/mo IoT box, test-terminal borg) — verify before any client quote.
4. **Auto-reconciliation into Odoo accounting** (vs only marking the POS payment line) — not documented; test.
5. **Module refund flow in the POS UI** (whether the Worldline-only API refund is surfaced or needs a manual credit note) — confirm by reading module source after install.
6. **`odoo/enterprise` manifests** could not be read directly (private repo); `OEEL-1`/Enterprise-only status is established via Odoo's public issue tracker and documented behavior, not a verbatim manifest quote.
