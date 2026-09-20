from odoo import http
from odoo.http import request

# Keys and their defaults. Anything a venue re-brands lives here, so the module
# itself carries no venue-specific value.
DEFAULTS = {
    'open_from': '17:00',
    'open_to': '22:00',
    'slot_minutes': '15',
    'lead_minutes': '20',
    'cta_label': 'Bestellen',
    'brand_primary': '#b4232a',
    'brand_ink': '#1c1c1c',
}


def setting(name):
    value = request.env['ir.config_parameter'].sudo().get_param(
        'atlas_restaurant.%s' % name)
    return (value or DEFAULTS[name]).strip()


class AtlasRestaurant(http.Controller):

    @http.route('/atlas/pickup-time', type='jsonrpc', auth='public', website=True, csrf=False)
    def set_pickup_time(self, value=None):
        """Store the customer's chosen pickup slot on the current cart."""
        order = request.cart or request.website._create_cart()
        value = (value or '').strip()[:64]
        if order:
            order.sudo().write({'atlas_pickup_time': value})
        return {'ok': bool(order), 'value': value}

    @http.route('/atlas/pickup-config', type='jsonrpc', auth='public', website=True, csrf=False)
    def pickup_config(self):
        """Opening hours and slot spacing, so the browser can build the slots."""
        return {k: setting(k) for k in
                ('open_from', 'open_to', 'slot_minutes', 'lead_minutes')}
