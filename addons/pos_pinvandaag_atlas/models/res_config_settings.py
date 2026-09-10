# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_pos_pinvandaag = fields.Boolean(
        string="Pin Vandaag Terminal",
        help="The transactions are processed by payment terminal. "
             "Set your terminal credentials on the related payment method.",
        config_parameter="pos_pinvandaag.module_pos_pinvandaag",
    )
