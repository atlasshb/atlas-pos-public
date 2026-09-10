/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";

export class PaymentPinvandaag extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.transaction_id = null;
        this.continue_on_success = false;
        this.terminal_id = this.payment_method_id?.pinvandaag_terminal_identifier || null;
    }

    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(uuid);
        return this._processPinvandaag(uuid);
    }

    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(order, uuid);
        return this._cancelRequest();
    }

    _pendingPinvandaagLine() {
        return this.pos.getPendingPaymentLine("pinvandaag");
    }

    _callPinvandaag(data) {
        return this.pos.data
            .silentCall("pos.payment.method", "terminal_request", [[this.payment_method_id.id], data])
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    async _processPinvandaag(uuid) {
        const order = this.pos.getOrder();
        const line = order.getSelectedPaymentline();

        if (!line) {
            this._showError(_t("Payment line not found"));
            return;
        }
        if (line.amount === 0) {
            this._showError(_t("Select an amount above 0"));
            return;
        }
        if (line.amount < 0) {
            return this._processRefund(uuid);
        }

        this.terminal_id = this.payment_method_id.pinvandaag_terminal_identifier;
        this.continue_on_success = this.payment_method_id.pinvandaag_confirm_order_on_payment;

        return this._callPinvandaag({
            SaleToTerminal: {
                TerminalID: this.terminal_id,
                PaymentDetails: { Amount: line.amount },
                RequestType: "create",
            },
        })
            .then(async (res) => {
                if (!res?.success && res?.status !== "started") {
                    this._showError(res?.error || _t("Could not start transaction. Contact Pin Vandaag"));
                    line.setPaymentStatus("retry");
                    return false;
                }
                line.transaction_id = res.transaction_id;
                this.transaction_id = res.transaction_id;
                line.setPaymentStatus("waiting");
                return this._pollTransaction(uuid);
            })
            .catch(() => {
                line.setPaymentStatus("retry");
                this._showError(
                    _t("Could not start transaction. Please try again."),
                    _t("Pinvandaag Error")
                );
            });
    }

    async _processRefund(uuid) {
        const order = this.pos.getOrder();
        const line = order.getSelectedPaymentline();
        if (!line) {
            return;
        }
        this.terminal_id = this.payment_method_id.pinvandaag_terminal_identifier;

        return this._callPinvandaag({
            SaleToTerminal: {
                TerminalID: this.terminal_id,
                PaymentDetails: { Amount: line.amount },
                RequestType: "refund",
            },
        })
            .then(async (res) => {
                if (res?.success === false) {
                    this._showError(res.error || _t("Could not start transaction (refund). Contact Pin Vandaag"));
                    return false;
                }
                if (res?.status === "started" || res?.status === "start") {
                    line.transaction_id = res.transaction_id;
                    this.transaction_id = res.transaction_id;
                    line.setPaymentStatus("waiting");
                    return this._pollTransaction(uuid);
                }
                return false;
            })
            .catch(() => {
                line.setPaymentStatus("retry");
                this._showError(
                    _t("Could not start transaction. Please try again."),
                    _t("Pinvandaag Error")
                );
            });
    }

    async _pollTransaction(uuid) {
        const order = this.pos.getOrder();
        const line = order.getSelectedPaymentline();

        return new Promise((resolve, reject) => {
            const Poller = async () => {
                await new Promise((res) => setTimeout(res, 1500));
                await this._callPinvandaag({
                    SaleToTerminal: {
                        TerminalID: line.payment_method_id.pinvandaag_terminal_identifier,
                        RequestType: "status",
                        PaymentDetails: { TransactionId: line.transaction_id },
                    },
                })
                    .then((respData) => {
                        const transaction = respData?.transaction;
                        if (!transaction) {
                            return Poller();
                        }
                        switch (transaction.status) {
                            case "success":
                                if (transaction.which_api && !transaction.receipt) {
                                    line.setPaymentStatus("retry");
                                    return reject(respData);
                                }
                                line.transaction_id = transaction.transaction_id || line.transaction_id;
                                line.setPaymentStatus("done");
                                line.which_api = transaction.which_api;
                                line.setReceiptInfo(this._receiptToHtml(transaction.receipt, transaction.which_api));
                                return resolve(true);
                            case "failed":
                                line.setPaymentStatus("retry");
                                return reject(respData);
                            case "started":
                            case "pending":
                            case "unknown":
                                this.transaction_id = transaction.transaction_id || this.transaction_id;
                                line.transaction_id = transaction.transaction_id || line.transaction_id;
                                line.setPaymentStatus("waiting");
                                return Poller();
                            default:
                                return Poller();
                        }
                    })
                    .catch(() => Poller());
            };
            return Poller();
        })
            .catch(() => {
                line.setPaymentStatus("retry");
                this._showError(
                    _t("Transaction failed. Please try again."),
                    _t("Pinvandaag Error")
                );
                return false;
            });
    }

    _receiptToHtml(receipt, which_api) {
        if (!receipt) {
            return "";
        }
        let decoded;
        try {
            decoded = typeof receipt === "string" ? JSON.parse(receipt) : receipt;
        } catch (e) {
            return String(receipt);
        }
        if (decoded?.customer) {
            decoded = decoded.customer.split("\n");
        }
        if (!Array.isArray(decoded)) {
            return String(receipt);
        }
        return decoded
            .map((item) => {
                let row;
                try {
                    row = typeof item === "string" ? JSON.parse(item) : item;
                } catch (e) {
                    row = [item];
                }
                if (Array.isArray(row)) {
                    if (which_api === "Worldline") {
                        return row.map((i) => `${Array.isArray(i) ? i[1] : i}`).join("") + "<br/>";
                    }
                    return row.join("") + "<br/>";
                }
                return `${row}<br/>`;
            })
            .join("")
            .replace(/\r/g, "");
    }

    async _cancelRequest() {
        const order = this.pos.getOrder();
        const line = order.getSelectedPaymentline();
        if (!line) {
            return;
        }
        await this._callPinvandaag({
            SaleToTerminal: {
                TerminalID: line.payment_method_id.pinvandaag_terminal_identifier,
                RequestType: "cancel",
                PaymentDetails: { TransactionId: line.transaction_id },
            },
        });
    }

    _showError(msg, title) {
        this.env.services.dialog.add(AlertDialog, {
            title: title || _t("Pinvandaag Error"),
            body: msg,
        });
    }

    _handleOdooConnectionFailure(data = {}) {
        const line = this._pendingPinvandaagLine();
        if (line) {
            line.setPaymentStatus("retry");
        }
        this._showError(
            _t("Could not connect to the Odoo server, please check your internet connection and try again.")
        );
        return Promise.reject(data);
    }
}

register_payment_method("pinvandaag", PaymentPinvandaag);
