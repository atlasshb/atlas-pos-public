{
    "name": "POS Pin Vandaag (Atlas fork, Odoo 19)",
    "summary": "Pay with CCV/Worldline terminals from the Odoo 19 POS via the Pin Vandaag REST API v2",
    "website": "https://www.pinvandaag.nl",
    "version": "19.0.0.1",
    "category": "Sales/Point of Sale",
    "description": "Atlas fork of the official pos_pinvandaag module (PIN Vandaag B.V., LGPL-3). Ported from the Odoo 17.0 payment API to the Odoo 19 payment_interface API. Drives Worldline/CCV cloud terminals over the Pin Vandaag REST API v2 (start / status / stop / refund / last_transaction). No IoT box and no Enterprise required.",
    "sequence": 6,
    "depends": ["base_setup", "point_of_sale"],
    "data": [
        "views/pos_payment_method_views.xml",
        "views/res_config_settings_view.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_pinvandaag_atlas/static/src/**/*",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
}
