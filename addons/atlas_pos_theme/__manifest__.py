# -*- coding: utf-8 -*-
{
    'name': 'Atlas POS Theme',
    'version': '19.0.1.0.0',
    'summary': 'Re-brandable Odoo 19 backend + login theme scaffold',
    'description': 'A small SCSS theme scaffold for the Odoo 19 backend and login '
                   'screen: primary colour, heading colour, white background and a '
                   'dark logo. Intended to be re-branded per venue.',
    'category': 'Theme/Backend',
    'author': 'Atlas Corporation',
    'website': 'https://atlascorporation.nl',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web._assets_primary_variables': [
            'atlas_pos_theme/static/src/scss/_pos_variables.scss',
        ],
        'web.assets_backend': [
            'atlas_pos_theme/static/src/scss/pos_backend.scss',
        ],
        'web.assets_frontend': [
            'atlas_pos_theme/static/src/scss/pos_login.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
