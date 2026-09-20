{
    'name': 'Atlas Restaurant Theme',
    'summary': 'Re-brandable takeaway/restaurant ordering theme for Odoo 19 website_sale',
    'description': """
Atlas Restaurant Theme
======================

The venue-neutral version of the per-venue themes Atlas has been writing one at
a time. Everything a takeaway needs on top of `website_sale`, with nothing
branded baked in:

* a pickup-time selector on the cart, with slots generated from **configured**
  opening hours rather than hardcoded ones;
* the chosen time carried onto the order and shown on the confirmation page;
* an ordering-oriented call to action instead of "Add to cart";
* a small neutral skin driven entirely by CSS custom properties, so a venue is
  re-branded by setting a handful of config parameters - not by forking this
  module.

Configuration (Settings > Technical > System Parameters):

===================================== ============================== =========
Parameter                             Meaning                        Default
===================================== ============================== =========
atlas_restaurant.open_from            first pickup slot, HH:MM       17:00
atlas_restaurant.open_to              last pickup slot, HH:MM        22:00
atlas_restaurant.slot_minutes         minutes between slots          15
atlas_restaurant.lead_minutes         earliest slot from now         20
atlas_restaurant.cta_label            product button label           Bestellen
atlas_restaurant.brand_primary        primary colour                 #b4232a
atlas_restaurant.brand_ink            heading colour                 #1c1c1c
===================================== ============================== =========
""",
    'version': '19.0.1.0.0',
    'category': 'Website',
    'author': 'Atlas Corporation',
    'website': 'https://atlascorporation.nl',
    'license': 'LGPL-3',
    'depends': ['website', 'website_sale'],
    'data': [
        'views/cart_pickup.xml',
        'views/brand.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'atlas_theme_restaurant/static/src/scss/restaurant.scss',
            'atlas_theme_restaurant/static/src/js/pickup.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
