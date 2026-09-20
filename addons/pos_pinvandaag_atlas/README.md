# pos_pinvandaag_atlas

Odoo 19 POS payment-terminal driver for **Pin Vandaag REST API v2** cloud terminals
(CCV and Worldline). LGPL-3 fork of the official `pos_pinvandaag` module by PIN Vandaag B.V.,
ported by Atlas Corporation to the Odoo 19 `payment_interface` API.

No Worldline or CCV partnership is required: Pin Vandaag resells both and this talks to their
REST API.

## Install

The module lives in `/opt/atlas-odoo/addons`, which **nine containers share** — including live
client tenants. Being present there does not install it; install per database:

    docker exec <container> odoo -c /etc/odoo/odoo.conf -d <db> \
        -i pos_pinvandaag_atlas --stop-after-init --no-http

`--no-http` is required when the container's own Odoo is already running.

## Configure

Point of Sale → Configuration → Payment Methods → new method:

- **Use a Payment Terminal** → `Pin Vandaag`
- **Terminal ID** — from Pin Portal
- **API key** — from Pin Portal. Restricted to `base.group_erp_manager` and stored server-side;
  it is never loaded into the POS frontend.

Odoo refuses to edit a payment method while a POS session is open. Close the session first.

## Sandbox

Set the config parameter `pos_pinvandaag_atlas.base_url` to a mock server and no real terminal,
key or card is needed. Atlas runs one at `/opt/atlas/pinvandaag-sandbox/sandbox.py`
(172.26.0.1:7810). Clear the parameter to return to `https://rest-api.pinvandaag.com/V2`.

Scenario by cent amount: `...00` approves, `...13` declines, `...99` never settles.

## Behaviour

- Polls `instore/transactions/status` every 1.5 s, at most 80 times (~2 min), then reports a
  timeout.
- A cashier cancel raises a flag that stops the poll loop, so a cancel is not reported as a
  decline.
- Three consecutive failed status calls abort with one message rather than a dialog per poll.
- Refunds go through `sendPaymentReversal`.

## Status

Exercised end to end against the sandbox: sale, decline, cancel, refund, last transaction.

**Not yet confirmed against the Odoo 19 upstream source**: the `PaymentInterface` method
signatures, the `_load_pos_data_fields` hook, and the inherited view xmlids
(`point_of_sale.pos_payment_method_view_form`, block `pos_payment_terminals_section`).
A wrong xmlid makes the module fail to install. Confirm these before installing at a venue.

See `/opt/atlas/docs/atlaspos-terminal-handoff.md` (internal) for the full picture.

## Verified against the Odoo 19 source

Confirmed by reading `point_of_sale` in a running 19.0 image, not assumed:

| Item | Result |
|---|---|
| `@point_of_sale/app/utils/payment/payment_interface` | exists at that path |
| `setup(pos, payment_method_id)` | matches |
| `sendPaymentRequest(uuid)` | matches |
| `sendPaymentCancel(order, uuid)` | matches |
| `sendPaymentReversal(uuid)` | matches |
| `close()` | matches |
| `register_payment_method(use_payment_terminal, Impl)` exported from `pos_store` | yes |
| `this.env` available on a PaymentInterface | yes — `setup()` sets `this.env = pos.env` |
| `_load_pos_data_fields(self, config)` returning a list | yes |
| `_get_payment_terminal_selection()` returning a list | yes |
| `pos.getPendingPaymentLine(terminalName)` | exists |
| `pos.data.silentCall(model, method, args, kwargs, queue)` | exists |
| `point_of_sale.pos_payment_method_view_form` | present in `ir_model_data` |
| both inherited views apply | active with arch in the DB |

**One defect this check found.** `PaymentInterface.setup()` defaults
`this.supports_reversals = false`, and the POS uses that flag to decide whether to offer the
reversal UI at all. Implementing `sendPaymentReversal` without raising it leaves the method
permanently unreachable. The module now sets `supports_reversals = true`.
