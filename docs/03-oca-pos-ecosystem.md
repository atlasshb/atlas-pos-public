# OCA / Open-Source POS-ecosysteem — verkenning 2026-09-04 (Odoo 19 CE)

Aanleiding: operator wil de Odoo-POS-front-end zoals die voor restaurants hoort te
zijn, met volledig beeld van OCA/forks/versies als alternatieven.

## 1. Core Odoo 19 CE (image atlas-odoo:19-eo) — POS-modules aanwezig
(alle onderstaande staan in de image-addons; point_of_sale is CE)
- point_of_sale, pos_restaurant (restaurantmodus: vloeren/tafels/takeaway)
- pos_sale, pos_sale_margin, pos_sale_loyalty, pos_hr, pos_hr_restaurant
- pos_loyalty, pos_discount, pos_sms, pos_event(+sale), pos_repair, pos_mrp
- Betalen: pos_mollie, pos_stripe, pos_adyen, pos_viva_com, pos_online_payment,
  pos_online_payment_self_order, pos_self_order (+sale/adyen/stripe/pine_labs/
  qfpay/razorpay/viva_com), pos_restaurant_adyen/stripe/loyalty + regionale
  (pos_cashdro, pos_cashmatic, pos_glory_cash, pos_imin, pos_dpopay, pos_qfpay,
  pos_pine_labs, pos_mercado_pago, pos_safaricom, pos_razorpay, pos_account_tax_python)
- Geverifieerd: odoo/odoo 19.0/addons/pos_restaurant = 200 (CE) — restaurantmodus
  is in v19 geen Enterprise-only feature.

## 2. OCA/pos (github.com/OCA/pos) — branches + modules
- Branches: 7.0 … 17.0, 18.0, 19.0 (19.0 bestaat maar is DUN: 6 top-dirs)
- Module-aantallen: 19.0 = 6 | 18.0 = 28 | 17.0 = 42
- 19.0 o.a.: pos_edit_order_line
- 18.0 o.a.: pos_display_order_number, pos_display_total_quantity,
  pos_divide_order_summary, pos_early_receipt_printing, pos_order_remove_line,
  pos_order_to_sale_order, pos_product_display_default_code
- 17.0 o.a.: + pos_category_vertical_display, pos_order_attachment, pos_order_copy,
  pos_order_line_customer_history, pos_order_line_show_product_info,
  pos_order_split_invoice, pos_receipt_gift_card
- Geen restaurant-layout-modules in OCA/pos — vloer/tafel-UI zit in core (pos_restaurant).
- Licentie OCA: LGPL-3 → veilig te klonen; 19.0-port per module nodig.

## 3. Kitchen Display / KDS
- pos_restaurant_preparation_display bestaat NIET in OCA/pos (404 op 18.0 en 19.0)
- GitHub-zoekopdracht: alleen unrelated/dead projecten (easacc_ksd e.d.)
- Conclusie: KDS = core-printflow (keukenbon per categorie naar netwerkprinter) of
  eigen/derde partij.

## 4. Forks / andere Odoo-POS-repo's (GitHub search, top-stars)
- Alleen studenten/dead forks (posRestaurantQrOdoo8, Odoo-Cafe-POS e.d.) — geen
  productiekwaliteit; afgeraden.

## 5. Standalone open-source restaurant-POS (niet-Odoo; context)
- UniCenta oPOS (Java, GPLv3, REST, KDS), Chromis POS (Openbravo-fork),
  FloreantPOS (GPLv3, restaurant-gericht) — zie ook council_pos.md.
- Los-van-Odoo = dubbele administratie; niet relevant nu CE de restaurantmodus dekt.

## 6. Besluit/actie voor de tenants
- venued: pos_restaurant geïnstalleerd; pos.config module_pos_restaurant=True,
  floor 'Zaal' (id2) + 10 tafels → POS opent in restaurantmodus.
- Nog aan te zetten in image: pos_self_order (+_sale) = QR/kiosk zelfbestellen
  (self_ordering_*-velden bestaan al op pos.config); pos_mollie/pos_stripe zodra
  pay-API-spoor B eraan toe is.
- OCA alleen voor specifieke gaten; 19.0 is te dun → anders 18.0-module porten (LGPL).
