# Pin Vandaag REST v2 sandbox

A deterministic stand-in for the Pin Vandaag `instore/transactions/*` endpoints, so the
`pos_pinvandaag_atlas` terminal driver can be exercised end to end without a real terminal,
a real API key or a real card.

    python3 sandbox.py                                   # 127.0.0.1:7810
    PINVANDAAG_SANDBOX_BIND=172.17.0.1 python3 sandbox.py  # reachable from a container

Then set the Odoo config parameter `pos_pinvandaag_atlas.base_url` to that address. Clearing
the parameter returns the module to the real API.

Bind address and port come from `PINVANDAAG_SANDBOX_BIND` / `PINVANDAAG_SANDBOX_PORT`.
When Odoo runs in a container, bind the Docker bridge gateway rather than loopback —
inside a container `127.0.0.1` is the container itself, not the host.

## Scenarios

Chosen by the cent amount, so a test is reproducible:

| Amount ends in | Behaviour |
|---|---|
| `...00` | approves after 2 status polls |
| `...13` | declines on the first status poll |
| `...99` | never settles — exercises the driver's 80-poll / ~2-minute timeout |

Implements `start`, `status`, `stop`, `last_transaction` and `refund`. Requests without an
`x-api-key` header are rejected, so the driver's server-side key handling is exercised too.
A cancelled or declined transaction is terminal and is never re-evaluated by a later poll.

Contains no credentials and no customer data.
