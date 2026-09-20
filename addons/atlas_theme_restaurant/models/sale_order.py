from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    atlas_pickup_time = fields.Char(
        string='Requested pickup time',
        help='Pickup slot the customer chose on the website. Free text, because '
             'the venue decides the slot format; an empty value means "as soon '
             'as possible".',
    )
