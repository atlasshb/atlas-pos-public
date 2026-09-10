# Pin Vandaag x Odoo 19 Community POS - Worldline Yomani Integration Design

**Author:** Atlas Corporation (info@example.com)
**Date:** 2026-06-30
**Status:** Engineering design / decision record
**Scope:** Concrete design for driving clients' Worldline Yomani card terminals from Odoo 19 **Community** POS via Pin Vandaag's cloud REST API, with no Enterprise subscription and no IoT Box.

---

## 0. TL;DR (the recommendation up front)

- **Native Odoo Worldline is not an option on Community.** Odoo's own v19 docs state "Connecting a Worldline payment terminal to Odoo requires an IoT system," the IoT app/IoT Box is Enterprise-gated (~US$30/month/box) and forces same-LAN hardware. That is the wall Atlas hits today and why clients are stuck on the **manual** card method.
  - Source: https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals/worldline.html
  - Source: https://www.odoo.com/app/iot-faq
- **Pin Vandaag is the right fit.** It is a cloud-initiated REST koppeling (kassa -> Pin Vandaag cloud -> terminal): the amount auto-appears on the Yomani, no IoT Box, no same-network requirement, and it keeps the client's existing Worldline hardware.
  - Source: https://www.pinvandaag.nl/kassa-koppeling/
  - Source: https://www.pinvandaag.nl/odoo-koppeling/
- **There is a real, published, Community-installable Odoo module:** `pos_pinvandaag` by PIN Vandaag B.V. on the Odoo Apps Store, LGPL-3, listed for Odoo 15.0-19.0, deployable On-Premise, core dependencies only (no Enterprise IoT dependency).
  - Source: https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag
  - Source (17.0 listing with deploy/licence detail): https://apps.odoo.com/apps/modules/17.0/pos_pinvandaag
- **Recommendation:** **Pilot with Pin Vandaag's own `pos_pinvandaag` 19.0 module first (Path 1).** It is free and LGPL-3, so legally modifiable and redistributable. Use the public 16.0 GitHub source as the reference implementation. Only if the 19.0 build proves incompatible, unmaintained, or insufficiently branded do we fall back to building a thin Atlas-owned `pos.payment.method` provider against the V2 REST API (Path 2). Wrap the module/provider inside each `atlas_<client>_pos` module via dependency + data, never by forking the payment logic per client.
- **One load-bearing unknown to confirm before promising clients:** that the **19.0** store build actually installs and runs on **Odoo 19 Community** (the store lists it, but architecturally-clean does not guarantee a clean 19.0 manifest). Exact question list in section 9.

---

## 1. Why this design exists (problem statement)

Atlas runs **Odoo 19 Community** POS for small NL hospitality/retail clients in the Tilburg region. Those clients own **Worldline Yomani** CTAP terminals. Odoo's native integrated-terminal modules (`pos_six`, `pos_adyen`, `pos_stripe`, and the IoT-based `pos_worldline`) are either Enterprise-only or require the Enterprise IoT system:

- The core `point_of_sale` app is identical in Community and Enterprise; only the integrated-terminal **add-ons** differ. Manual (non-integrated) card methods work on Community, which is the double-entry, error-prone status quo.
- The Worldline native path specifically requires the IoT system (CTEP protocol, Yomani XR/Yoximo, BE/NL/LU only) and that system is Enterprise-gated + same-LAN.
  - Source: https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals.html
  - Source: https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals/worldline.html

Pin Vandaag (Tilburg, Pin Voordeel B.V.) offers a **cloud REST API** that initiates payments from the kassa and pushes the amount to the terminal automatically, with no IoT Box and no same-network constraint - exactly the architecture Community needs.

---

## 2. Integration architecture

### 2.1 High-level topology

```
+---------------------------+        HTTPS (X-API-KEY)         +-----------------------+        Pin Vandaag        +------------------+
|  Odoo 19 Community POS     |  ---- POST /start (cents) ---->  |  Pin Vandaag Cloud    |  --- activates terminal -> |  Worldline Yomani |
|  (browser PWA + server)    |  <--- webhook callbackUrl -----  |  rest-api.pinvandaag  |  <-- card tap/insert ----- |  (any network/4G) |
|  pos.payment.method ->     |  ---- POST /status (poll) ---->  |  .com / V2            |                            |                  |
|  Pin Vandaag provider      |                                  |                       |                            |                  |
+---------------------------+                                  +-----------------------+                            +------------------+
```

Key property: the **terminal does not need to be on the same network as the POS**. The POS talks only to Pin Vandaag's cloud; Pin Vandaag talks to the terminal over its own network (which can even be 4G/mobile for outdoor use).
- Source: https://www.pinvandaag.nl/kassa-koppeling/

### 2.2 API base, versions, auth

| | V1 (legacy) | **V2 (recommended)** |
|---|---|---|
| Base URL | `https://rest-api.pinvandaag.com/V1/instore` | `https://rest-api.pinvandaag.com/V2` |
| Auth | `terminalId` + `key` form params per POST | **`X-API-KEY` header** (or legacy OAuth2 Basic `base64(apikey:secret)`) |
| HTTP status codes | inconsistent | proper 200/400/404/500 |

- V1 docs: https://www.pinvandaag.nl/docs/rest-api/
- V2 docs: https://www.pinvandaag.nl/docs/rest-api-2/

**Design decision:** target **V2** for any Atlas-built code. Note the published GitHub module (16.0) still calls **V1** (`https://rest-api.pinvandaag.com/V1/`); if we adopt and later fork it, migrate it to V2 for the better auth + status semantics. Reference for V2 endpoint shapes: the official PHP SDK `pinvandaag/pin-php-sdk` (also published as `pinvandaag-pin-php-sdk`).
- Source (16.0 module uses V1): https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/const.py
- Source (PHP SDK org): https://github.com/orgs/Pin-Voordeel-Bv/repositories

### 2.3 Endpoints used (V2)

| Action | Endpoint (POST unless noted) | Required params | Notes |
|---|---|---|---|
| **Start payment** | `/instore/transactions/start` | `terminal_id`, `amount` (in **cents**) | optional `callbackUrl` (webhook), `ownReference` (POS order ref), `ReturnUrl` (CCV only). Returns `transactionId`, `status:"started"`. This is the cloud push that auto-shows the amount. |
| **Poll status** | `/instore/transactions/status` | `terminal_id`, `transaction_id` | returns `status` (`success`/`failed`/`unknown`), receipt, `errorMsg`. **CCV cached ~30s**; Worldline near-real-time. |
| **Cancel/void** | `/instore/transactions/stop` | `terminal_id` (Worldline) / `transaction_id` (CCV) | CCV limited to ~3 cancel attempts/transaction. |
| **Refund** | `/instore/transactions/refund` | `terminal_id`, `amount` (cents) | **Worldline ONLY** - good for Atlas's Yomani clients; not available for CCV. |
| **Email receipt** | `/instore/transactions/mail` | `terminal_id`, `transaction_id`, `email` | successful tx only. |
| **Last transaction** | `/instore/transactions/last_transaction` | `terminal_id` | recovery/reconciliation aid. |
| **Force config pull** | `/instore/transactions/ctmp` | `terminal_id` | **Worldline ONLY**. |
| **Reporting** | `GET /instore/transactions_dashboard/search` | terminals, clients, datefrom/dateto (UNIX), amount range, type | daily reconciliation. |
| **Onboard sub-merchant** | `/instore/clients/create` | KVK, IBAN, UBO etc. | **partner** endpoint - Atlas can provision clients programmatically. |

Source: https://www.pinvandaag.nl/docs/rest-api-2/

### 2.4 State machine

```
            POST /start
   (idle) --------------> [started] --- card approved ---> [success]  -> mark POS line paid, store transactionId + receipt
                              |    \--- card declined ----> [failed]   -> reject POS line, allow retry
                              |    \--- timeout/no answer -> [unknown] -> poll /status / /last_transaction before deciding
                              |
                              \--- POST /stop -------------> [cancelled]
```

The generic contract any provider must implement (identical to what Enterprise `pos_iot`/`pos_adyen` implement, just over HTTP):
`send_payment_request(amount, ref)` -> terminal lights up; `poll_status(ref)` -> success/failed/pending; `send_payment_cancel(ref)`; `refund(amount)`. Pin Vandaag's API maps 1:1 onto this.
- Source (pos_adyen extracted a generic cloud payment interface, no IoT): https://github.com/odoo/odoo/pull/35702

---

## 3. Decision: use Pin Vandaag's module vs. build a thin custom provider

### Path 1 - Adopt `pos_pinvandaag` (RECOMMENDED for the pilot)

**What it is:** A published Odoo Apps Store module, `pos_pinvandaag`, by **PIN Vandaag B.V.**, **LGPL-3**, listed for Odoo **15.0-19.0**, deployable On-Premise / Online / .sh, dependencies are **core modules only** (no Enterprise IoT). It configures, per payment method, a **Terminal ID** + **API Key**, then does cloud create-then-poll - matching the marketing claim "amount appears on the terminal automatically."
- Source: https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag
- Source: https://apps.odoo.com/apps/modules/17.0/pos_pinvandaag
- Reference source (16.0 GitHub, verified architecture): https://github.com/coopiteasy/pinvandaag-odoo
  - `const.py` (API base, V1): https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/const.py
  - `models/pos_payment_method.py` (Terminal ID + API Key fields, create/poll/cancel/refund calls): https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/models/pos_payment_method.py

**Pros:** Fastest to a working pilot; vendor-maintained; LGPL-3 means we can legally read, modify and redistribute; already implements start/status/cancel/refund/webhook for Yomani.

**Cons / risks:**
- GitHub mirror is **stale (16.0 only, last push 2024-02-12, 0 stars/2 forks)**; the 19.0 build ships only as an Apps Store zip, so we cannot diff it in Git before download. No active community fork has carried it past 16.0.
  - Source: https://github.com/coopiteasy/pinvandaag-odoo
  - Source (forks, both inactive/16.0 only): https://github.com/coopiteasy/pinvandaag-odoo/forks
- The 19.0 store listing names **extra deps (Invoicing/Discuss/Inventory)** vs. the lean `point_of_sale`-only 16.0 manifest - must verify the real 19.0 `__manifest__.py` after download.
- 16.0 build uses **V1** API; whether the 19.0 build moved to V2 is unverified.

### Path 2 - Build a thin Atlas-owned provider (`atlas_pos_pinvandaag`)

A small Odoo 19 Community addon that subclasses the POS `PaymentInterface` (the same generic interface `pos_adyen` uses) and calls Pin Vandaag **V2** directly:
- `send_payment_request` -> `POST /start` (`amount*100`, `terminal_id`, `ownReference = pos.order ref`, `callbackUrl` -> Odoo controller).
- poll loop -> `POST /status` until `success`/`failed` (respect CCV 30s cache; for Yomani poll ~1-2s).
- `send_payment_cancel` -> `POST /stop`.
- refund -> `POST /refund` (Worldline).
- store `transactionId` + receipt on `pos.payment`.

**Pros:** Full control, V2 from day one, Atlas-branded, version-pinned to 19, no dependency on vendor release cadence, integrates cleanly with the partner `/instore/clients/create` onboarding for white-label margin.

**Cons:** Engineering + maintenance cost; must re-implement edge cases (`unknown` recovery, webhook + polling, cents rounding) that the vendor module already handles; carries the full 17->18 OWL 2 refactor + 19 UI risk on Atlas's shoulders.

### Verdict

**Pilot on Path 1; keep Path 2 as the productionization/branding track.** Concretely:
1. Install `pos_pinvandaag` 19.0 from the Apps Store on a 19 Community test DB. Validate end-to-end with a borrowed test Yomani.
2. Inspect its real 19.0 `__manifest__.py` and confirm core-only deps + V1-vs-V2.
3. If it passes: ship it to pilot clients, layering Atlas config via `atlas_<client>_pos` (section 4).
4. If it fails or lags Odoo 19.x point releases: fork it (LGPL-3 permits this) or build `atlas_pos_pinvandaag` against V2 using the 16.0 source + PHP SDK as references.

---

## 4. How it slots into the per-client Odoo and `atlas_<client>_pos`

Atlas already structures each client deployment as an `atlas_<client>_pos` module. The Pin Vandaag integration is **a shared dependency, configured per client via data**, never re-implemented per client:

```
atlas_pos_pinvandaag/            # shared: the provider (Path 2) OR a thin wrapper/pin of pos_pinvandaag (Path 1)
  __manifest__.py                # depends: ['point_of_sale']; version: '19.0.x'; license LGPL-3
  models/pos_payment_method.py   # Terminal ID + API Key fields + V2 calls (or inherits pos_pinvandaag)
  static/src/js/payment_pinvandaag.js   # OWL 2 PaymentInterface subclass (19.x build)
  controllers/webhook.py         # /pinvandaag/callback route -> resolves pos.payment by ownReference

atlas_<client>_pos/              # per-client: NO payment logic, only config + data
  __manifest__.py                # depends: ['atlas_pos_pinvandaag', ...client modules]
  data/pos_payment_method.xml    # one pos.payment.method per client terminal:
                                 #   use_payment_terminal = 'pinvandaag'
                                 #   pinvandaag_terminal_identifier = <client's terminal_id>
                                 #   pinvandaag_api_key = <client key>  (store as ir.config_parameter / Settings, not VCS)
  data/pos_config.xml            # attach the method to the client's POS register(s)
```

**Rules of engagement:**
- **Never commit API keys / terminal IDs to the `atlas_<client>_pos` repo.** Store keys in Odoo Settings (`ir.config_parameter`) or per-DB system parameters; keep only placeholders in version-controlled data.
- **Version-pin everything to 19.** The 17->18 OWL 2 POS refactor means a 16/17 JS provider will NOT run on 19; the JS `PaymentInterface` subclass must be the 19.x flavour.
  - Source: https://www.odoo.com/odoo-19-release-notes
  - Source: https://www.odoo.com/forum/help-1/pos-customization-app-upgrade-from-odoo-16-to-18-272799
- **Developer mode** is frequently required to expose terminal-config fields on the payment method form - document this in the client runbook.
  - Source: https://www.odoo.com/forum/help-1/pin-payment-terminal-205767
- **Keep a Cash method enabled** on each POS config to avoid the well-known card-only refund/validation bug (`Math.abs(total - paid)` tripping on negative totals).
  - Source: https://github.com/odoo/odoo/issues/33752

---

## 5. Data & reconciliation flow

### 5.1 Per-transaction (real time)

1. Cashier hits **Pay** on the Pin Vandaag method -> JS provider POSTs `/start` with `amount*100` (integer cents), `terminal_id`, `ownReference = pos.order` reference, `callbackUrl`.
2. Amount auto-appears on the Yomani; customer taps/inserts.
3. Resolution arrives via **webhook** (`callbackUrl`) AND/OR **polling** `/status`. **Polling is the primary mechanism** because the webhook is **single-delivery with no robust retry** ("retry under development").
   - Source: https://www.pinvandaag.nl/docs/rest-api/ (webhook single-fire), https://www.pinvandaag.nl/docs/rest-api-2/
4. On `success`: mark the `pos.payment` line paid; persist `transactionId` and the receipt blob on the payment line. On `failed`: reject and allow retry. On `unknown`: query `/status` then `/last_transaction` before deciding; do not silently mark paid.

### 5.2 End-of-day / accounting reconciliation

- Each `pos.payment` carries the Pin Vandaag `transactionId`; the `ownReference` ties it back to the `pos.order`.
- For daily matching, pull `GET /instore/transactions_dashboard/search` (filter by terminal + date range, UNIX timestamps) and reconcile against the POS session's payment lines.
- Pin Vandaag markets "automatic end-of-day reconciliation," but **whether the module auto-writes settlement into Odoo accounting (vs. only marking the POS payment line) is unconfirmed** - validate during the pilot.
  - Source: https://www.pinvandaag.nl/odoo-koppeling/

### 5.3 Cents / rounding discipline

Amounts cross the wire as **integer cents**. Convert from Odoo float totals with explicit rounding (`int(round(amount * 100))`) to avoid the classic off-by-100 / float-rounding bug. Unit-test boundary values (e.g. 0.10, 19.99, 100.005).

---

## 6. Cost, borg, and partner / test-terminal steps

### 6.1 Costs (verify live before quoting clients)

| Item | Stated cost | Source |
|---|---|---|
| `pos_pinvandaag` Odoo module | **Free** (LGPL-3) | https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag |
| REST API integration | **Free** | https://www.pinvandaag.nl/odoo-koppeling/ |
| Per-terminal coupling fee (koppelingskosten) | **~EUR 2.50 / month / terminal** + per-transaction fees | https://www.pinvandaag.nl/odoo-koppeling/ , https://www.pinvandaag.nl/kassa-koppeling/ |
| Test-terminal borg (deposit, refundable) | Yomani **EUR 275**; Pax A77 EUR 399; Verifone P400 EUR 499 | https://www.pinvandaag.nl/kassa-koppeling/ |
| Test-terminal retention | 2 months free, then **EUR 5/month** if not returned | https://www.pinvandaag.nl/kassa-koppeling/ |
| Buy a Yomani XR/ML outright | EUR 450 (was 599), optional EUR 15/mo service | https://www.pinvandaag.nl/product/worldline-yomani-xr-ml/ |
| Odoo Enterprise IoT (the avoided cost) | ~US$30/month/box + Enterprise sub | https://www.odoo.com/app/iot-faq |

### 6.2 Onboarding / partner steps

1. **Register** for an API key + terminal_id via Pin Vandaag's portal: https://aanmelden.pinportal.nl/external/register-form (linked from the Odoo page). Module onboarding contact: **helpdesk@pinvandaag.nl**.
2. **Order a test terminal** (Yomani) to validate the full loop before touching a client: https://www.pinportal.nl/oud/forms/quote/4cf85bdf9d45e0dd735a7b7b21d09798?styled=1
3. **Partner program** - Atlas should enroll as a Kassa Partner for margin + programmatic client provisioning (`/instore/clients/create`): https://www.pinvandaag.nl/partners/ . Existing kassa-partners listed include Taurus, Bos Systemen, WaiterOne, etc.
4. **Developer / API support line:** 085 5601203 (per V1 docs); general helpdesk +31 85 5601201.
   - Source: https://www.pinvandaag.nl/docs/rest-api/

---

## 7. Gotchas to bake into the implementation & client runbook

- **Webhook is single-fire** - polling `/status` is mandatory as the safe primary; never rely on the callback alone or transactions hang in `started`.
  - Source: https://www.pinvandaag.nl/docs/rest-api/
- **CCV status cached ~30s; CCV refund unsupported; CCV cancel max ~3 attempts.** Atlas's fleet is **Worldline Yomani**, which is the better-behaved provider (near-real-time status, refund supported, ctmp supported) - but if any client adds CCV, surface these limits in the UX.
  - Source: https://www.pinvandaag.nl/docs/rest-api-2/
- **Amounts in cents** - off-by-100 risk (section 5.3).
- **Developer mode** needed to expose terminal config fields.
  - Source: https://www.odoo.com/forum/help-1/pin-payment-terminal-205767
- **Refund / card-only POS bug** - keep a Cash method enabled or process refunds via credit notes.
  - Source: https://github.com/odoo/odoo/issues/33752
- **Odoo 17->18 OWL 2 break + 19 UI changes** - version-pin the JS provider to 19; do not assume a 16/17 module runs on 19.
  - Source: https://www.odoo.com/odoo-19-release-notes
- **CTAP vs CTEP** - Pin Vandaag markets "CTAP"; Odoo native uses "CTEP". Related Worldline ECR protocol families; the exact end-to-end protocol Pin Vandaag's cloud uses was not deeply confirmed but is not load-bearing for the integration (we only speak HTTP to Pin Vandaag).

---

## 8. Risks & unknowns

| # | Risk / unknown | Impact | Mitigation |
|---|---|---|---|
| R1 | **19.0 store build's real compatibility with Odoo 19 Community** is not provable from public Git (only a zip). 19.0 listing names extra deps vs lean 16.0 manifest. | Could block the whole pilot. | Install on a 19 Community test DB FIRST; inspect downloaded `__manifest__.py`. Ask Pin Vandaag directly (Q1). |
| R2 | **GitHub stalled at 16.0 since 2024**; no active fork past 16.0. | Future Odoo 19.x point releases may break the module with no upstream fix. | LGPL-3 lets Atlas self-maintain a fork; budget for it. Path 2 removes the dependency entirely. |
| R3 | 16.0 module uses **V1 API**; 19.0 build's API version unverified. | V1 auth is weaker (form key). | Confirm with Pin Vandaag (Q3); migrate to V2 if forking. |
| R4 | **Accounting auto-reconciliation depth** unknown (marketing claims it; module behavior unverified). | Manual reconciliation effort per client. | Test during pilot; ask Q4. |
| R5 | **Partner commission / white-label terms** not retrievable (samenwerken page 404'd, BE partner page 522'd). | Margin model unknown. | Request partner agreement directly (Q5). |
| R6 | Webhook reliability / `unknown`-state recovery semantics not fully documented. | Hung or mis-marked transactions. | Polling-primary + `/last_transaction` recovery; test failure injection. |
| R7 | No independent (Reddit/NL practitioner) reviews of the Odoo koppeling surfaced; sentiment is vendor-stated. | Unknown real-world reliability. | Pilot with low-volume client first; monitor before fleet rollout. |

---

## 9. Exact questions to ask Pin Vandaag (helpdesk@pinvandaag.nl / +31 85 5601201 / dev 085 5601203)

1. **Q1 (load-bearing):** Does the published `pos_pinvandaag` 19.0 build install and run on **Odoo 19 Community** (not just Enterprise/Online)? Which exact 19.x series is supported, and what is your update cadence against Odoo 19 point releases?
2. **Q2:** What are the **exact module dependencies** in the 19.0 `__manifest__.py`? The store page lists Invoicing/Discuss/Inventory - are any of those Enterprise-only, or all core/Community?
3. **Q3:** Does the 19.0 module call REST **V1 or V2**? If V1, is a V2 migration planned?
4. **Q4:** Does the module **auto-reconcile settlements into Odoo accounting**, or does it only mark the `pos.payment` line? How is end-of-day reconciliation surfaced in Odoo?
5. **Q5 (partner):** What are the **Kassa Partner** commission / revenue-share terms and white-label options for a POS integrator like Atlas? Can we provision client sub-merchants via `/instore/clients/create` under our partner account?
6. **Q6:** Is there a **sandbox/test API environment**, or must testing use a physical test terminal (borg)?
7. **Q7:** For Yomani, what **polling cadence** do you recommend, and what is the documented behavior/retry for the `unknown` status and for webhook re-delivery?
8. **Q8:** Is the module's **refund flow exposed inside the Odoo POS UI** for Worldline, or does it require a manual credit note?

---

## 10. Next actions (Atlas)

1. **Register** at https://aanmelden.pinportal.nl/external/register-form to obtain an API key + terminal_id; email helpdesk@pinvandaag.nl referencing Odoo 19 Community.
2. **Order a test Yomani** (EUR 275 borg) via the quote form; or use a client's terminal under controlled conditions.
3. **Stand up a clean Odoo 19 Community test DB**; install `pos_pinvandaag` 19.0 from the Apps Store; inspect the real `__manifest__.py`.
4. **Run the end-to-end loop** (start -> tap -> success; decline; cancel; refund) and verify pos.payment data + reconciliation.
5. **Send Pin Vandaag the Q1-Q8 list** (section 9) in writing before committing any client.
6. **If green:** build `atlas_pos_pinvandaag` as a thin shared layer (or pin the vendor module) and wire per-client config into each `atlas_<client>_pos` via data files; pilot with one low-volume client.
7. **If the module is unsuitable:** build the Path 2 V2 provider, using the 16.0 source (`const.py`, `pos_payment_method.py`) and the `pinvandaag/pin-php-sdk` as endpoint references.
8. **Enroll in the Kassa Partner program** for margin and programmatic client onboarding.

---

## 11. Source list

- Odoo 19 terminals doc: https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals.html
- Odoo 19 Worldline doc (requires IoT): https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/payment_methods/terminals/worldline.html
- Odoo IoT FAQ (Enterprise/paid): https://www.odoo.com/app/iot-faq
- Odoo 19 release notes: https://www.odoo.com/odoo-19-release-notes
- pos_adyen generic cloud interface (no IoT): https://github.com/odoo/odoo/pull/35702
- Odoo card-only refund bug: https://github.com/odoo/odoo/issues/33752
- Odoo 16->18 POS upgrade pain: https://www.odoo.com/forum/help-1/pos-customization-app-upgrade-from-odoo-16-to-18-272799
- Developer-mode terminal config: https://www.odoo.com/forum/help-1/pin-payment-terminal-205767
- Pin Vandaag kassa-koppeling: https://www.pinvandaag.nl/kassa-koppeling/
- Pin Vandaag odoo-koppeling: https://www.pinvandaag.nl/odoo-koppeling/
- Pin Vandaag REST API V1: https://www.pinvandaag.nl/docs/rest-api/
- Pin Vandaag REST API V2: https://www.pinvandaag.nl/docs/rest-api-2/
- Pin Vandaag partners: https://www.pinvandaag.nl/partners/
- Pin Vandaag Yomani product: https://www.pinvandaag.nl/product/worldline-yomani-xr-ml/
- pos_pinvandaag 19.0 Apps Store: https://apps.odoo.com/apps/modules/19.0/pos_pinvandaag
- pos_pinvandaag 17.0 Apps Store: https://apps.odoo.com/apps/modules/17.0/pos_pinvandaag
- pos_pinvandaag GitHub (16.0): https://github.com/coopiteasy/pinvandaag-odoo
- pos_pinvandaag const.py (V1 base): https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/const.py
- pos_pinvandaag payment method model: https://raw.githubusercontent.com/coopiteasy/pinvandaag-odoo/16.0/pos_pinvandaag/models/pos_payment_method.py
- Pin Voordeel B.V. GitHub (PHP SDK): https://github.com/orgs/Pin-Voordeel-Bv/repositories
- OCA/pos (generic, IoT-based, no CTAP): https://github.com/OCA/pos
