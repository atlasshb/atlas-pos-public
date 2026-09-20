{
    "name": "POS Pin Vandaag (Atlas)",
    "summary": "Take CCV / Worldline card payments from Odoo POS via the Pin Vandaag REST API v2",
    "website": "https://www.pinvandaag.nl",
    "author": "PIN Vandaag B.V. / Atlas Corporation",
    "version": "19.0.0.2",
    "category": "Sales/Point of Sale",
    "description": """
Odoo POS payment terminal integration for Pin Vandaag REST API v2 cloud
terminals (CCV, Worldline). Fork of the official LGPL-3 pos_pinvandaag module,
ported to the Odoo 19 payment_interface API.

Atlas changes (19.0.0.2): correct REST v2 response handling
(transactionId / status / receipt); bounded polling with a clear timeout
instead of an infinite loop; configurable API base URL
(pos_pinvandaag_atlas.base_url) so the same module can point at a sandbox or
simulator without code changes; the API key is read server-side only and is
never loaded into the POS frontend payload.
""",
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
