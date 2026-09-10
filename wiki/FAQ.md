# FAQ

**Is this a fork of Odoo?**
No. It's a set of thin modules and research that run on top of stock Odoo 19
Community. We extend; we don't fork core.

**Do I need Odoo Enterprise?**
No, for the cloud-terminal route. Community supports the payment-terminal
plugin pattern the Pin Vandaag module uses. Enterprise is only needed for the
IoT box / certified-hardware layer and some regional drivers.

**Which terminals are supported?**
Worldline (Yomani/Yoximo/Valina), CCV, PAX (A77/A920/A960/A35), Ingenico
(DX8000/RX5000), Verifone (V400m/P400/Vx680/Vx820), and Sunmi Android
terminals — via the Pin Vandaag cloud API.

**Can I use a different PSP?**
Yes. The architecture is PSP-agnostic; the payment method selects a terminal
backend. We ship the Pin Vandaag backend because it's free and LGPL-3.

**Does the POS store card numbers?**
No. Card data is captured on the terminal and never reaches the POS. That keeps
the POS out of PCI scope.

**Is it white-label / multi-venue?**
Yes. Use one Odoo database + company per venue; the seed and theme modules are
templates you re-brand per venue.

**Is the data real?**
No. This is a de-identified export. Client and infrastructure values are
placeholders. See `NOTICE.md`.

**Can I contribute?**
Yes — issues and PRs welcome, especially corrections, extra open-source POS
projects, and Odoo 19 port fixes. Keep contributions free of secrets and
personal data.

**What license?**
MIT for docs/tooling, LGPL-3 for the modules. The Pin Vandaag module derives
from an LGPL-3 upstream (see `NOTICE.md`).
