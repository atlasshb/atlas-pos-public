# -*- coding: utf-8 -*-
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessDenied

_logger = logging.getLogger(__name__)

TIMEOUT = 10


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    def _get_payment_terminal_selection(self):
        return super(PosPaymentMethod, self)._get_payment_terminal_selection() + [
            ('pinvandaag', 'Pin Vandaag')
        ]

    pinvandaag_terminal_identifier = fields.Char(
        string="Terminal ID",
        help="The ID of the terminal",
        copy=False,
    )
    pinvandaag_api_key = fields.Char(
        string="API key",
        help="The API key to use to connect with Pin Vandaag",
        copy=False,
        groups='base.group_erp_manager',
    )
    pinvandaag_confirm_order_on_payment = fields.Boolean(
        string="Directly send to receipt",
        help="After payment is completed send to the receipt page",
        copy=False,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ['pinvandaag_terminal_identifier', 'pinvandaag_confirm_order_on_payment']
        return params

    @api.constrains('pinvandaag_terminal_identifier')
    def _check_pinvandaag_terminal_identifier(self):
        for payment_method in self:
            if not payment_method.pinvandaag_terminal_identifier:
                continue
            existing_payment_method = self.sudo().search([
                ('id', '!=', payment_method.id),
                ('pinvandaag_terminal_identifier', '=', payment_method.pinvandaag_terminal_identifier),
            ], limit=1)
            if existing_payment_method:
                raise ValidationError(
                    _('Terminal %(terminal)s is already used on payment method %(payment_method)s.',
                      terminal=payment_method.pinvandaag_terminal_identifier,
                      payment_method=existing_payment_method.display_name))

    _possibles_cases = [
        "create",
        "status",
        "cancel",
        "getLastTransaction",
        "refund",
    ]

    _host = "https://rest-api.pinvandaag.com/V2"

    def _pinvandaag_post(self, endpoint, payload, api_key):
        try:
            answer = requests.post(
                f"{self._host}/{endpoint}",
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "x-api-key": api_key,
                },
                timeout=TIMEOUT,
            )
            answer.raise_for_status()
            return answer.json()
        except Exception as e:
            _logger.error("Pin Vandaag %s error: %s", endpoint, e)
            return {"success": False, "error": str(e)}

    def _convert_amount(self, amount):
        return int(float(amount) * 100)

    def _start_transaction(self, terminal_id, amount, api_key):
        return self._pinvandaag_post(
            "instore/transactions/start",
            {"terminal_id": terminal_id, "amount": self._convert_amount(amount)},
            api_key,
        )

    def _poll_transaction(self, terminal_id, transaction_id, api_key):
        return self._pinvandaag_post(
            "instore/transactions/status",
            {"transaction_id": transaction_id, "terminal_id": terminal_id},
            api_key,
        )

    def _cancel_transaction(self, terminal_id, transaction_id, api_key):
        return self._pinvandaag_post(
            "instore/transactions/stop",
            {"transaction_id": transaction_id, "terminal_id": terminal_id},
            api_key,
        )

    def _last_transaction(self, terminal_id, api_key):
        return self._pinvandaag_post(
            "instore/transactions/last_transaction",
            {"terminal_id": terminal_id},
            api_key,
        )

    def _refund_transaction(self, terminal_id, api_key, amount):
        amount_str = str(amount).replace("-", "")
        return self._pinvandaag_post(
            "instore/transactions/refund",
            {"terminal_id": terminal_id, "amount": self._convert_amount(amount_str)},
            api_key,
        )

    def terminal_request(self, data, operation=False):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessDenied()

        if not data or 'SaleToTerminal' not in data:
            raise ValidationError(_("Invalid data format"))

        terminal_id = data["SaleToTerminal"]["TerminalID"]
        request_type = data["SaleToTerminal"].get("RequestType")
        if not request_type:
            raise ValidationError(_("RequestType is required"))

        terminal = self.env["pos.payment.method"].search(
            [("pinvandaag_terminal_identifier", "=", terminal_id)], limit=1)
        if not terminal:
            raise ValidationError(_("No payment method found for terminal %s", terminal_id))
        if not terminal.pinvandaag_terminal_identifier:
            raise ValidationError(_("No terminal identifier found for terminal %s", terminal_id))
        if not terminal.pinvandaag_api_key:
            raise ValidationError(_("No API key found for terminal %s", terminal_id))

        if request_type not in self._possibles_cases:
            raise ValidationError(_("Invalid request type"))

        details = data["SaleToTerminal"].get("PaymentDetails") or {}

        if request_type == "create":
            amount = details.get("Amount")
            if not amount:
                raise ValidationError(_("Amount is required"))
            return self._start_transaction(terminal_id, amount, terminal.pinvandaag_api_key)

        if request_type == "status":
            transaction_id = details.get("TransactionId")
            if not transaction_id:
                raise ValidationError(_("TransactionId is required"))
            return self._poll_transaction(terminal_id, transaction_id, terminal.pinvandaag_api_key)

        if request_type == "cancel":
            transaction_id = details.get("TransactionId")
            if not transaction_id:
                raise ValidationError(_("TransactionId is required"))
            return self._cancel_transaction(terminal_id, transaction_id, terminal.pinvandaag_api_key)

        if request_type == "getLastTransaction":
            return self._last_transaction(terminal_id, terminal.pinvandaag_api_key)

        if request_type == "refund":
            amount = details.get("Amount")
            if not amount:
                raise ValidationError(_("Amount is required"))
            return self._refund_transaction(terminal_id, terminal.pinvandaag_api_key, amount)

        raise ValidationError(_("Invalid request type"))
