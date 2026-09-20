// SPDX-License-Identifier: LGPL-3.0-only
// Copyright (c) PIN Vandaag B.V. — original pos_pinvandaag module (LGPL-3.0)
// Modified by Atlas Corporation (2026): Odoo 19 port + REST API v2 contract fixes.
/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";

const MAX_POLLS = 80;          // ~2 minutes at 1.5 s
const POLL_INTERVAL = 1500;
const MAX_POLL_ERRORS = 3;     // F3: consecutive failed status calls before giving up

export class PaymentPinvandaag extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.transaction_id = null;
        this.continue_on_success = false;
        // Odoo 19 PaymentInterface.setup() defaults supports_reversals to false,
        // and the POS uses that flag to decide whether to offer the reversal UI
        // at all. Implementing sendPaymentReversal without raising this leaves
        // the method permanently unreachable -- which is what F1 originally
        // shipped. Verified against point_of_sale/static/src/app/utils/payment/
        // payment_interface.js in the running 19.0 image.
        this.supports_reversals = true;
        // F2: set by _cancelRequest so the poll loop can stop itself. Without
        // it the poller kept running after a cashier cancel and reported the
        // terminal's resulting `failed` as "Transaction failed", which reads
        // to the cashier as a declined card rather than their own cancel.
        this.cancelled = false;
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

    // F1: both were missing. Refunds were reachable only by calling
    // sendPaymentRequest with a negative amount, which is not the contract
    // the POS reversal flow uses, and close() had no implementation at all.
    sendPaymentReversal(uuid) {
        super.sendPaymentReversal?.(uuid);
        return this._processRefund(uuid);
    }

    close() {
        super.close?.();
        this.cancelled = true;
        this.transaction_id = null;
    }

    _pendingPinvandaagLine() {
        return this.pos.getPendingPaymentLine("pinvandaag");
    }

    _callPinvandaag(data) {
        return this.pos.data
            .silentCall("pos.payment.method", "terminal_request", [[this.payment_method_id.id], data])
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    // F3: the poll loop needs an RPC that does NOT pop a dialog on every
    // failure; the caller decides when enough consecutive failures is enough.
    _callPinvandaagSilent(data) {
        return this.pos.data.silentCall(
            "pos.payment.method", "terminal_request", [[this.payment_method_id.id], data]
        );
    }

    _transactionId(res) {
        // REST v2 returns camelCase `transactionId`; tolerate the snake_case
        // variant used by some older responses.
        // F4: the status path already tolerates a `transaction` wrapper, but
        // this did not, so a nested create response left line.transaction_id
        // null and every following status call failed server-side with
        // "TransactionId is required" -- surfaced to the cashier as a bogus
        // "Could not connect to the Odoo server".
        const inner = res?.transaction || res?.data || {};
        return (
            res?.transactionId ||
            res?.transaction_id ||
            inner?.transactionId ||
            inner?.transaction_id ||
            null
        );
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
                const started = res?.status === "started" || res?.status === "start";
                if (!started) {
                    this._showError(
                        res?.error || res?.message || _t("Could not start transaction. Contact Pin Vandaag")
                    );
                    line.setPaymentStatus("retry");
                    return false;
                }
                const txId = this._transactionId(res);
                line.transaction_id = txId;
                this.transaction_id = txId;
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
                if (res?.success === false || res?.status === "error") {
                    this._showError(
                        res?.error || res?.message || _t("Could not start transaction (refund). Contact Pin Vandaag")
                    );
                    return false;
                }
                if (res?.status === "started" || res?.status === "start") {
                    const txId = this._transactionId(res);
                    line.transaction_id = txId;
                    this.transaction_id = txId;
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
        let polls = 0;
        let consecutiveErrors = 0;
        this.cancelled = false;

        return new Promise((resolve, reject) => {
            const Poller = async () => {
                // F2: a cashier cancel ends the loop here, quietly -- the
                // cancel already told the terminal to stop.
                if (this.cancelled) {
                    line.setPaymentStatus("retry");
                    return resolve(false);
                }
                if (polls++ >= MAX_POLLS) {
                    line.setPaymentStatus("retry");
                    return reject({ timeout: true });
                }
                await new Promise((res) => setTimeout(res, POLL_INTERVAL));
                await this._callPinvandaagSilent({
                    SaleToTerminal: {
                        TerminalID: line.payment_method_id.pinvandaag_terminal_identifier,
                        RequestType: "status",
                        PaymentDetails: { TransactionId: line.transaction_id },
                    },
                })
                    .then((respData) => {
                        consecutiveErrors = 0;
                        // REST v2 returns the transaction flat; older/some
                        // responses wrap it in `transaction`.
                        const transaction = respData?.transaction || respData;
                        if (!transaction) {
                            return Poller();
                        }
                        switch (transaction.status) {
                            case "success":
                                line.transaction_id =
                                    this._transactionId(transaction) || line.transaction_id;
                                line.setPaymentStatus("done");
                                line.which_api = transaction.which_api;
                                line.setReceiptInfo(
                                    this._receiptToHtml(transaction.receipt, transaction.which_api)
                                );
                                return resolve(true);
                            case "failed":
                                line.setPaymentStatus("retry");
                                return reject(respData);
                            case "started":
                            case "start":
                            case "pending":
                            case "unknown":
                                this.transaction_id =
                                    this._transactionId(transaction) || this.transaction_id;
                                line.transaction_id =
                                    this._transactionId(transaction) || line.transaction_id;
                                line.setPaymentStatus("waiting");
                                return Poller();
                            default:
                                return Poller();
                        }
                    })
                    .catch(() => {
                        // F3: this used to re-poll on any error while the
                        // shared connection handler popped a dialog each
                        // time -- a dead Odoo server meant up to 80 dialogs
                        // over two minutes. Give up after MAX_POLL_ERRORS
                        // with a single message.
                        if (++consecutiveErrors >= MAX_POLL_ERRORS) {
                            line.setPaymentStatus("retry");
                            return reject({ connection: true });
                        }
                        return Poller();
                    });
            };
            return Poller();
        })
            .catch((err) => {
                line.setPaymentStatus("retry");
                if (err?.connection) {
                    this._showError(
                        _t("Lost contact with the terminal service while waiting for the payment. Check the terminal before retrying."),
                        _t("Pinvandaag Error")
                    );
                } else if (err?.timeout) {
                    this._showError(
                        _t("The terminal did not respond in time. Check the terminal and try again."),
                        _t("Pinvandaag Error")
                    );
                } else {
                    this._showError(
                        _t("Transaction failed. Please try again."),
                        _t("Pinvandaag Error")
                    );
                }
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
        // F2: raise the flag first, so the in-flight poll loop stops even if
        // the stop call below is slow or fails.
        this.cancelled = true;
        if (!line) {
            return;
        }
        try {
            await this._callPinvandaagSilent({
                SaleToTerminal: {
                    TerminalID: line.payment_method_id.pinvandaag_terminal_identifier,
                    RequestType: "cancel",
                    PaymentDetails: { TransactionId: line.transaction_id },
                },
            });
        } catch {
            // The cashier already decided to cancel; a failed stop call must
            // not reject out of sendPaymentCancel.
            this._showError(
                _t("Could not reach the terminal to cancel. Check the terminal itself."),
                _t("Pinvandaag Error")
            );
            return false;
        }
        return true;
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
