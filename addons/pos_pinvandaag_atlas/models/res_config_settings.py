# SPDX-License-Identifier: LGPL-3.0-only
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pinvandaag_base_url = fields.Char(
        string="Pin Vandaag API base URL",
        help="REST API v2 base URL. Leave empty for production "
             "(https://rest-api.pinvandaag.com/V2). Point it at a sandbox / "
             "simulator to test without a live terminal.",
        config_parameter="pos_pinvandaag_atlas.base_url",
    )
