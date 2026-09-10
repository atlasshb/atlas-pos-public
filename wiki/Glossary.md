# Glossary

| Term | Meaning |
|---|---|
| **POS** | Point of Sale — the counter system that rings up sales. |
| **PSP** | Payment Service Provider — processes card/online payments (e.g. Pin Vandaag, Adyen, Mollie). |
| **Acquirer** | The bank/network side that settles card transactions (e.g. Worldline, CCV). |
| **Terminal** | The physical card reader at the counter. |
| **Cloud terminal** | A terminal driven by a cloud API rather than a local (IoT) integration. |
| **SoftPOS / Tap to Pay** | Using an Android phone's NFC as the card acceptor. |
| **PAN** | Primary Account Number — the card number. Never store it. |
| **PCI DSS / SAQ B-IP** | Card-industry security standard; a POS that never touches card data can be out of scope. |
| **CTAP / CTEP** | Worldline terminal protocols used by Odoo's Enterprise IoT integration. |
| **Odoo CE / EE** | Odoo Community Edition (LGPL-3) vs Enterprise (paid). |
| **`point_of_sale`** | Odoo's core POS module (Community). |
| **`pos_restaurant`** | Restaurant mode: floors, tables, courses, takeaway (Community). |
| **IoT box** | Odoo Enterprise hardware that bridges local devices/terminals. |
| **`pos.payment.method`** | Odoo model for a POS payment method; `use_payment_terminal` selects the backend. |
| **OCA** | Odoo Community Association — publishes community modules (`github.com/OCA`). |
| **Twin** | A read-only copy of an incumbent POS database, kept for ETL. |
| **ETL** | Extract-Transform-Load — moving/mapping data between systems. |
| **DPA** | Data Processing Agreement (GDPR/AVG). |
| **PSD2 / AIS / PIS** | EU open-banking rules; AIS = account info, PIS = payment initiation. |
| **BNPL** | Buy Now, Pay Later (often interest-bearing). |
