# atlas_theme_restaurant

A venue-neutral takeaway / restaurant ordering theme for Odoo 19 `website_sale`.

This is the generalised version of the per-venue themes that were previously written one at a
time. Nothing branded is baked in: a venue is configured, not forked.

## What it adds

- A **pickup-time selector** on the cart, with slots generated in the browser from the venue's
  **configured** opening hours (not hardcoded), respecting a lead time and handling venues that
  close after midnight.
- The chosen slot is stored on `sale.order.atlas_pickup_time` and shown on the confirmation page.
- A small neutral skin driven entirely by CSS custom properties.

## Configuration

Settings → Technical → System Parameters:

| Parameter | Meaning | Default |
|---|---|---|
| `atlas_restaurant.open_from` | first pickup slot, `HH:MM` | `17:00` |
| `atlas_restaurant.open_to` | last pickup slot, `HH:MM` | `22:00` |
| `atlas_restaurant.slot_minutes` | minutes between slots | `15` |
| `atlas_restaurant.lead_minutes` | earliest slot from now | `20` |
| `atlas_restaurant.cta_label` | product button label | `Bestellen` |
| `atlas_restaurant.brand_primary` | primary colour | `#b4232a` |
| `atlas_restaurant.brand_ink` | heading colour | `#1c1c1c` |

## Routes

- `POST /atlas/pickup-time` — store the chosen slot on the current cart
- `POST /atlas/pickup-config` — opening hours and slot spacing, for the browser

Both are `type='jsonrpc'`. In Odoo 19 `type='json'` still works but is a deprecated alias.

## Notes for anyone extending this

The first draft also inherited `website_sale.product` to restyle the add-to-cart anchor via
`//a[@id='add_to_cart']`. **That xpath does not match the Odoo 19 template** and made the module
fail to install. The button is styled from CSS instead. Guessing at an xpath is the quickest way
to make a theme uninstallable — verify against the running version first.
