# 15 — DoBizzz / DoPos — incumbent research

Research on **DoBizzz** and its **DoPos** kassa software: the incumbent system
Atlas migrates takeaway/delivery venues *off of*, onto Odoo 19 Community.

> **Sources:** company website `dobizzz.nl` (Home, Functies, Onze Pakketten,
> FAQ pages, retrieved 2026-09). Claims about users/orders/savings are
> **vendor-stated** and unverified. Our own observations are marked *(Atlas)*.
> Nothing here is confidential to any client.

## 1. Company

| | |
|---|---|
| Legal name | **DoBizzz The Easy Way B.V.** |
| Address | Hanzeweg 45H, 7418 AV Deventer, NL |
| Phone | 085-2500705 |
| KvK | 82612676 |
| BTW | NL862538944B01 |
| Website | https://www.dobizzz.nl/ |
| Product name | **DoPos** ("Gratis DoPos Kassa software") |
| Focus | Afhaal-, bezorgrestaurants en horeca (takeaway, delivery, restaurants) |
| Copyright line | © 2021 |

## 2. Product & editions

DoPos is a **free** kassa (POS) application for takeaway/delivery restaurants,
sold in three editions — all listed at "Gratis":

| Edition | Deployment | Database | Notes |
|---|---|---|---|
| **Portable** | Single Windows PC, run from USB storage | SQLite (file) | "Werk vanuit iedere Windows computer" |
| **Business** | Windows network | server DB | Unlimited terminals/couplings; adds All-You-Can-Eat |
| **Linux** | Linux network | server DB | Same as Business, on Linux |

All editions ship: a responsive website/webshop, an app (Android / iPhone /
Windows), Track & Trace, order status, webshop coupling, and an optional
coupling with **Thuisbezorgd** (Takeaway.com). Business/Linux add the
**All-You-Can-Eat** module.

## 3. Features (as stated by the vendor)

- **POS / kassa** — order capture tuned for peak takeaway.
- **Responsive website + webshop**, coupled to the kassa (real-time orders).
- **App** for Android, iPhone and Windows.
- **Track & Trace** and **order status** — the customer sees received/underway.
- **Delivery-driver tracking** — follow couriers; real-time payment/delivery
  updates. (Android app id `com.dobizzz.dotrace` — "DoTrace".)
- **Agenda** — restaurant reservations + staff scheduling; reservations via the
  website; reserved tables marked on the floor map.
- **All-You-Can-Eat** module (Business/Linux).
- **Webshop coupling** and optional **Thuisbezorgd** coupling.
- **Kitchen dispatch** — incoming orders sent automatically and grouped to the
  kitchen.

## 4. Business model

DoPos is advertised as **free software**, with **no contract** ("je kunt ieder
moment stoppen") and free updates/maintenance. The obvious question — *how can
it be free?* — is answered only with "we did market research". The revenue
mechanism is therefore indirect and **not disclosed on the site**.

*(Atlas)* Our own notes record a **per-order commission of €0.50/order** on
own-webshop orders, plus per-table/per-delivery commissions, and the couplings
(webshop, Thuisbezorgd). So while the licence is €0, the **transaction/order
rail is the product**: the venue pays by volume, and the vendor owns the
channel. This is the classic "free POS, monetised on payments/orders" play.

Vendor-stated marketing numbers (unverified): 600+ users, 2M+ orders, €4M+
savings, rating 9.7; "gemiddeld €8.000/jaar" saving; a €26.000/12-month example.

## 5. Technics & support

- **SQLite (Portable)** or a network server DB (Business/Linux).
- Remote support via third-party tooling: **Splashtop** (team deployment),
  **AnyDesk** (Linux), and a **DoBizzz SOS** executable (`sos.exe`).
- Delivery tracking via the **DoTrace** Android app.

*(Atlas)* The remote-support channel is worth noting: vendor staff can reach
the till over Splashtop/AnyDesk. That is convenient for support and also a
security/governance consideration (who can reach the machine, and when).

## 6. Why venues (and Atlas) care

- The **cost model scales with success** — more orders, more commission.
- **Data ownership**: the menu, customers, orders and website are on the
  vendor's rail; extracting them cleanly is not a published capability.
- **Architecture**: desktop/SQLite roots make cloud reporting, multi-venue
  consolidation and modern delivery dispatch harder.
- **Lock-in**: the webshop/app/Track & Trace are the venue's public face, so
  leaving is a customer-facing project, not just a software swap.

## 7. Open questions (confirm per venue, do not assume)

- Which edition is each venue on? (SQLite portable vs network.)
- Exact **database schema** for orders, menu, customers, delivery status.
- Is there an **export** (CSV/Excel/backup) the venue can trigger?
- Thuisbezorgd coupling: API or manual portal?
- Contract/commission terms actually in force (verbally vs in writing).
- Can historical orders be exported for Odoo accounting, or only reporting?

These are answered during discovery, on a read-only copy — never on the live
system. See `17-dopos-to-odoo-migration.md`.
