# MANUAL CHECKLIST — Venue B POS by hand (Odoo 19 Community)

Use this if the scripts can't run, or to finish/verify any step by hand.
Click-by-click for **Odoo 19.0 Community**, DB **`venue_b`**, at **http://192.0.2.10:8069**.

Work top to bottom. Each box is one action. `→` means "then click".

---

## 0. Log in + enable Developer Mode

- [ ] Open **http://192.0.2.10:8069** → log in as an **admin** user.
- [ ] **Settings** → scroll to bottom → **Developer Tools** → **Activate the developer mode**.
  (Needed for "Update Apps List" and to see some technical fields.)

---

## 1. Language — make the POS UI Turkish (tr_TR)

> Turkish is the **UI language only**. Accounting stays Dutch (Section 5).

- [ ] **Settings** → **Translations** → **Languages** → **+ New** (or **Add Languages**).
- [ ] Select **Türkçe / Turkish (tr_TR)** → **Add** / **Load**. Wait for it to finish.
- [ ] Confirm it shows as **Active**.

Set it for the owner's user:

- [ ] **Settings** → **Users & Companies** → **Users** → open the **owner's user**.
- [ ] **Preferences** tab → **Language = Türkçe (tr_TR)** → **Save**.
- [ ] Log out and back in as that user → the menus should now be Turkish.

(Optional) make Turkish the default for new users:

- [ ] **Settings** → **Users & Companies** → ensure the default language is Türkçe if desired.

---

## 2. Company & VAT prerequisites (DUTCH — do this BEFORE posting any entry)

> Critical: the fiscal localization can only be chosen **while no journal entry has been posted**. Do it early.

- [ ] **Settings** → **Users & Companies** → **Companies** → open the company → **Country = Netherlands** → **Save**.
- [ ] **Apps** → remove the "Apps" filter → search **`l10n_nl`** → install **"Netherlands - Accounting"** (if not already installed).
- [ ] **Accounting** → **Configuration** → **Settings** → **Fiscal Localization** → package = **Netherlands** (Save).
- [ ] Same Settings page → **Taxes → Default Taxes** → **Sales Tax = 21% BTW** → **Save**.
- [ ] **Accounting** → **Configuration** → **Taxes**: confirm **21% BTW**, **9% BTW**, **0% BTW** exist (sale + purchase).

> Do **NOT** install `l10n_tr` (Turkish accounting). That would give a Dutch company the wrong VAT.

---

## 3. Journals (needed for the payment methods)

- [ ] **Accounting** → **Configuration** → **Journals**.
- [ ] Confirm there is a **Cash** journal (Type = Cash). If missing → **New** → Type **Cash** → name e.g. "Kas (Contant)" → Save.
- [ ] Confirm there is a **Bank** journal (Type = Bank). If missing → **New** → Type **Bank** → name e.g. "Bank / Pin" → Save.

---

## 4. POS payment methods

### 4a. Cash — "Contant"

- [ ] **Point of Sale** → **Configuration** → **Payment Methods** → **New**.
- [ ] **Method** (name) = **Contant**.
- [ ] **Journal** = the **Cash** journal (Type Cash).
  → Leaving the journal as Cash makes this a cash/drawer method automatically.
- [ ] **Identify Customer** = OFF (leave unchecked).
- [ ] Leave **Intermediary Account** / outstanding accounts blank (defaults).
- [ ] **Do NOT** touch any "type" / "cash count" field — they compute themselves.
- [ ] **Save**.

### 4b. Manual card — "Pinnen / Worldline kaart" (the standalone Worldline YOMANI)

- [ ] **Point of Sale** → **Configuration** → **Payment Methods** → **New**.
- [ ] **Method** (name) = **Pinnen / Worldline kaart**.
- [ ] **Journal** = the **Bank** journal (Type Bank).
- [ ] **Use a Payment Terminal** = **leave EMPTY / blank**.
  → In Community 19 this dropdown has **no options**; an empty value = a **manual, non-integrated** card method. This is correct. The cashier runs the physical Worldline by hand and confirms the amount in POS.
- [ ] **Identify Customer** = OFF.
- [ ] **Save**.

> Do not try to "connect" the Worldline terminal via IoT / Connected Devices — integrated terminals are Enterprise + IoT only. The manual bank method above is the supported Community way.

### 4c. Attach both methods to the shop

- [ ] **Point of Sale** → **Configuration** → **Point of Sale** → open your shop config (e.g. "Shop" / "Venue B").
- [ ] **Payment** section → **Payment Methods** → add **Contant** and **Pinnen / Worldline kaart**.
  (Make sure the methods' company matches the POS config's company.)
- [ ] **Save**.

---

## 5. Receipt printer + receipt text

### 5a. Header / footer (always do this)

- [ ] **Point of Sale** → **Configuration** → **Point of Sale** → open your shop config.
- [ ] **Bills & Receipts** section → enable **Header & Footer** (a.k.a. "Custom Header & Footer").
- [ ] **Receipt Header** (example):
  ```
  Venue B
  <straat + nr>, Tilburg
  KvK: <nr>   BTW: <NL...B..>
  ```
- [ ] **Receipt Footer** (example):
  ```
  Bedankt! / Teşekkürler
  ```
- [ ] Leave **"Basic Receipt"** OFF (a tailor needs prices on the ticket).
- [ ] **Save**.

### 5b. Printing path — default (browser/PDF, works with any Windows printer)

- [ ] Leave **ePos Printer** (Connected Devices) **OFF**.
- [ ] Leave **automatic receipt printing** OFF for now (`Print Automatically` unchecked).
- [ ] At checkout you'll press **Print**, and the **browser print dialog** opens → pick the Windows receipt printer.

### 5c. (OPTIONAL, on-site only) Epson ePOS LAN printer — skip unless the shop has one

> Only for an **Epson ePOS** network printer (e.g. TM-m30). Non-Epson / USB / Star printers do **not** work this way — use 5b.

- [ ] Give the printer a **static IP** (reserve it on the router).
- [ ] **Point of Sale** → **Configuration** → **Point of Sale** → shop config → **Connected Devices** → enable **ePos Printer**.
- [ ] **Epson Receipt Printer IP Address** = the printer's static LAN IP → **Save**.
- [ ] In a browser on the POS PC, open **https://&lt;printer-ip&gt;** and **trust the printer's self-signed certificate** (import into Windows Trusted Root) — otherwise printing is silently blocked.
- [ ] (Optional) enable **Print Automatically** for hands-free printing.

---

## 6. POS categories (5)

**Point of Sale** → **Configuration** → **PoS Product Categories** (a.k.a. POS Categories) → **New** for each:

- [ ] **Galajurken (Abiye)**
- [ ] **Kostuums (Takım Elbise)**
- [ ] **Kleding (Giyim)**
- [ ] **Accessoires (Aksesuar)**
- [ ] **Vermaak & Reparatie (Tadilat & Onarım)**

---

## 7. Products (16)

For **each** product: **Point of Sale** → **Products** → **Products** → **New**.
Set the fields below; **leave Taxes empty** so each inherits the company default **21% BTW**.

Common settings for every product:
- [ ] **Point of Sale** tab → **Available in POS = ON**.
- [ ] **Point of Sale** tab → **POS Category** = the matching category from Section 6.
- [ ] **Taxes** = leave default (do not set a tax manually).

### Goods — set **Product Type = Goods** (`consu`), leave "Track Inventory" OFF

| Name | Sales Price | POS Category |
|------|------------:|--------------|
| Galajurk (Abiye) - Standaard | 199.00 | Galajurken (Abiye) |
| Galajurk (Abiye) - Luxe | 349.00 | Galajurken (Abiye) |
| Galajurk Kind (Çocuk Abiye) | 99.00 | Galajurken (Abiye) |
| Kostuum 2-delig (Takım Elbise 2 parça) | 249.00 | Kostuums (Takım Elbise) |
| Kostuum 3-delig (Takım Elbise 3 parça) | 299.00 | Kostuums (Takım Elbise) |
| Colbert (Ceket) | 129.00 | Kostuums (Takım Elbise) |
| Pantalon (Pantolon) | 69.00 | Kostuums (Takım Elbise) |
| Overhemd (Gömlek) | 39.00 | Kleding (Giyim) |
| Rok (Etek) | 49.00 | Kleding (Giyim) |
| Stropdas (Kravat) | 19.00 | Accessoires (Aksesuar) |
| Sjaal (Şal) | 24.00 | Accessoires (Aksesuar) |
| Riem (Kemer) | 29.00 | Accessoires (Aksesuar) |

### Services — set **Product Type = Service**

| Name | Sales Price | POS Category |
|------|------------:|--------------|
| Vermaak (Tadilat) - prijs per opdracht | 0.00 | Vermaak & Reparatie (Tadilat & Onarım) |
| Reparatie (Onarım) - prijs per opdracht | 0.00 | Vermaak & Reparatie (Tadilat & Onarım) |
| Inkorten broek/jurk (Boy kısaltma) | 15.00 | Vermaak & Reparatie (Tadilat & Onarım) |
| Rits vervangen (Fermuar değiştirme) | 20.00 | Vermaak & Reparatie (Tadilat & Onarım) |

> Product Type only has **Goods / Service / Combo** in v19. There is no "Storable"/"detailed type". Services can't be storable.

---

## 8. Per-job price override for alterations (one-time setting)

- [ ] **Point of Sale** → **Configuration** → **Point of Sale** → shop config → **Pricing** section.
- [ ] Ensure price editing at the counter is **allowed** (do NOT enable any price restriction/lock).
- [ ] If cashier PINs / restricted rights are used, grant the price-edit right to whoever rings up alterations.

At the counter for an alteration: tap the order line → press **Price** (or `p`) → type the agreed amount → confirm.

---

## 9. Final smoke test (same as README)

- [ ] Open a POS session.
- [ ] Ring up **Galajurk (Abiye) - Standaard** (€199) → check **21% BTW**.
- [ ] Ring up **Vermaak (Tadilat)** (€0) → press **Price** → type **25.00** → check it becomes €25.00 @ 21% BTW.
- [ ] **Payment** → **Pinnen / Worldline kaart** → run the physical Worldline → accept amount → **Validate** (no integrated-terminal prompt, no error).
- [ ] **Print** the receipt → browser dialog → Windows printer → receipt shows **header/footer + priced lines + total**.

**All boxes ticked = Venue B POS is live.**
