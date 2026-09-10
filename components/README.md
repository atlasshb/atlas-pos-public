# Components — the non-Odoo parts of the stack

The `addons/` modules are Odoo. These components are everything around them:
the code that runs **on the POS PC**, on the **fleet hub**, and on the
**Windows till**. They are independent of Odoo and reusable on their own.

> De-identified export. No credentials, client data or live addresses. Examples
> use placeholders (`<BEARER_TOKEN>`, `192.0.2.10`, `venue_a`).

## What's here

| Component | Runs on | What it does |
|---|---|---|
| [`agent/`](agent) | POS PC (Windows) | Lightweight HTTP agent exposing terminal health + a read-only DB view to the fleet collector. |
| [`collector/`](collector) | Fleet hub | FastAPI multi-tenant collector: enrolls terminals, polls health/totals, stores a PAN-scrubbed mirror, serves a cockpit. |
| [`kassa-odoo-sync/`](kassa-odoo-sync) | POS PC | One-way, idempotent push from an incumbent POS MySQL DB into Odoo (customers, products). |
| [`windows-harness/`](windows-harness) | Windows till | Launcher/harness for the agent so it starts headless on the till. |
| [`onboarding/`](onboarding) | Operator | Bootstrap script that installs the agent package on a new till. |
| [`pci-scan/`](pci-scan) | Operator | Card-data scanner + Luhn PAN masker used to keep the POS out of PCI scope. |

## Design notes

- **Read-only toward the live POS.** The agent and collector read the incumbent
  database; nothing writes to it.
- **PAN never leaves.** `pci-scan/mask_pan.py` and `collector/journal_chain.py`
  scrub Luhn-valid card numbers and record a tamper-evident hash chain.
- **Per-terminal bearer tokens**, not a shared all-clients secret.
- **One agent, many venues** — the collector is multi-tenant by `customer_id`.

## Related

- The newer fleet program (watch / mirror / verify / provision) lives in
  [`../scripts/`](../scripts) and [`../program/`](../program).
- Odoo modules: [`../addons/`](../addons).
