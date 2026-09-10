# 12 — Payments landscape (card terminals, PSPs, open banking)

Notes on the payment providers and rails relevant to a small-venue POS in the
Netherlands/EU, and the architectural choices they force. All prices are
**indicative, vendor-published figures** collected mid-2026 — verify at source
before quoting anyone. No reseller or negotiated terms are included here.

## The two integration routes for card acceptance

1. **Native / certified-integration route** — the POS drives a terminal through
   the vendor's certified integration. In Odoo this is the IoT box + CTAP/CTEP
   layer, and it is **Enterprise-only**. It is the most robust but locks you into
   the Enterprise subscription and the supported acquirer.
2. **Cloud-terminal / REST route** — the POS calls the PSP's cloud API, which
   drives a paired terminal. This works on **Community** and with third-party
   terminals. It is the route we chose.

> Rule of thumb we adopted: **integrate the payment, never become the acquirer.**
> The POS must never hold funds, store PANs, or orchestrate settlement.

## Providers we evaluated

| Provider | What they offer | Integration route | Notes |
|---|---|---|---|
| **Pin Vandaag / Pin Voordeel B.V.** (NL, Tilburg) | Cloud card acceptance; worldline/CCV/PAX/Ingenico/Verifone terminals; SoftPOS; free LGPL-3 **Odoo module** | REST API v2 (`X-API-KEY`), cloud-terminal | Our chosen Community route. Same group as Optimum POS. Terminals: PAX A77/A920/A35, Ingenico DX8000/RX5000, Verifone V400m/P400/Vx680, Worldline Yomani/Yoximo. Transaction processing roughly €0.06/debit txn; credit ~1.6%; SoftPOS ~€2/mo + per-txn. |
| **Worldline** | Acquirer + terminals (Yomani/Yoximo/Valina); CTEP/CTAP | Native Odoo = Enterprise + IoT box; cloud = via Pin Vandaag | Owner of the Yomani/CTEP toolchain. |
| **CCV** | NL acquirer + terminals (PAX, Verifone); ITS/Cloud Connect | Cloud + ITS; some integrations "in development" | Debit ~€0.06–0.07/txn; credit ~1.6%; terminal rental from ~€25/mo. Some models excluded from third-party takeover. |
| **Adyen** | Global PSP + terminals + webhooks | Native Odoo `pos_adyen` exists (different acquirer); also API | Enterprise-grade; minimum monthly commitments make it heavy for a single small venue. Good for scaled multi-venue later. |
| **Stripe / Stripe Terminal** | Global PSP + terminal SDK | Odoo `pos_stripe` (cloud); raw-body webhook verification | Strong APIs and webhooks; acquirer/region caveats for EU in-person. |
| **Mollie** | NL/EU online PSP (iDEAL, card, SEPA, links) | Odoo `payment_mollie` | Excellent for **online** orders/invoicing; not an in-person terminal rail. |
| **SumUp** | Simple POS + payments bundles | Not natively integrated | ~€58/mo bundle + ~1–1.5%; self-service, low setup. |
| **myPOS** | Terminals + acquiring; reseller-friendly | Not natively integrated | Low per-txn debit; hardware margin for resellers. |
| **MultiSafepay / Buckaroo / Pay.nl / PayT** | NL online PSPs | Various | Appear in the NL market and via aggregators; check terminal support. |
| **Zettle / Square** | Cheap entry POS/payments | Closed ecosystems | Popular for micro-merchants; limited openness. |

## Terminal hardware (agnostic)

PAX (A77/A920/A960/A35), Ingenico (DX8000/RX5000), Verifone
(V400m/P400/Vx680/Vx820), Worldline (Yomani/Yoximo/Valina), Sunmi Android
terminals. All are PCI PTS approved; the meaningful differences are **who
certifies the integration** and **which cloud API namespace** they speak.

## SoftPOS / Tap to Pay

Android + NFC only (no dedicated terminal). Useful as an extra mobile payment
point during peak hours. iOS is not an acceptor platform for these products.
Pricing is typically a low monthly fee + per-transaction + credit percentage.

## PSD2 / open banking

For payouts and bank reconciliation, open-banking APIs (AIS for account
information, PIS for credit transfers) are the modern route. Note that some
providers stopped onboarding new AIS clients, so plan for provider churn. Keep
operator approval + SCA in the loop for any payout action.

## Compliance boundaries we set

- **Never store card data.** Truncated PANs only, if at all. The POS is out of
  PCI scope when the terminal/PSP owns card capture (SAQ B-IP class).
- **Never hold funds / run payouts.** Settlement belongs to the PSP/bank.
- **Verify webhooks** (raw-body signature) and reconcile against settlement
  reports; treat the PSP as the source of truth for payment status.
- **No BNPL** where the operator's policy forbids interest-bearing products.

## Odoo specifics

Payment terminals in Odoo are a **payment-method type** (`pos.payment.method`
with `use_payment_terminal`), not a `payment.provider`. Community supports the
cloud-terminal pattern (see `pos_adyen`, `pos_mollie`, `pos_stripe`); the
certified Worldline/CCV hardware path needs Enterprise + IoT. Our fork of the
Pin Vandaag module ports that cloud pattern to Odoo 19
(`addons/pos_pinvandaag_atlas`).
