# -*- coding: utf-8 -*-
{
    'name': 'Atlas POS Seed Pack',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'license': 'LGPL-3',
    'author': 'Atlas Corporation',
    'website': 'https://atlascorporation.nl',
    'summary': 'Additive, idempotent Odoo 19 Community POS seed pack for a small '
               'retail / tailor venue (bilingual UI, manual card method).',
    'description': """
Atlas POS Seed Pack
===================

A minimal, additive and idempotent Point-of-Sale configuration pack used as the
starting template for a new venue on Odoo 19 Community.

What this pack ships
--------------------
* **POS catalogue** — bilingual (Dutch primary, second language in parentheses)
  POS categories, product categories and a small goods/services set.
* **Two POS payment methods** — *Contant* (Cash) and a MANUAL card method for a
  standalone wired terminal. Their journals are resolved by SEARCH in the
  post-init hook, never by a hard-coded xmlid.
* **POS receipt configuration** — browser/PDF baseline with a custom
  header/footer. ePOS direct printing is left OFF and documented as an on-site
  step.
* **Second UI language** — activated and merged (overwrite=False) in the
  post-init hook. Currency and fiscal localization stay Dutch.

Safety / scope
--------------
* **Additive and idempotent.** Re-installing or upgrading never wipes or
  overwrites company data, the chart of accounts, taxes or journals.
* **No integrated terminal / IoT modules are pulled in** — for automated card
  payments install `pos_pinvandaag_atlas` alongside this pack.

This is a de-identified template. Replace the sample categories, products and
receipt text with the venue's own before going live.
""",
    'depends': [
        'base',
        'web',
        'point_of_sale',
        'account',
    ],
    'data': [
        'data/pos_category.xml',
        'data/product_category.xml',
        'data/product_template.xml',
        'data/product_services.xml',
        'data/pos_payment_method.xml',
        'data/pos_config.xml',
        'data/res_lang_tr.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': False,
    'installable': True,
    'auto_install': False,
}
