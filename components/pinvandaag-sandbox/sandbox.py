#!/usr/bin/env python3
"""Atlas Pin Vandaag REST v2 sandbox.

A deterministic stand-in for https://rest-api.pinvandaag.com/V2 so the
pos_pinvandaag_atlas terminal driver can be exercised end to end without a
real terminal, a real API key, or a real card. Binds loopback by default; set PINVANDAAG_SANDBOX_BIND to a Docker bridge
gateway when the Odoo server runs in a container (inside a container
127.0.0.1 is the container itself, not the host).

Scenario is chosen by the cent amount so a test is reproducible:
    ...00  approve after APPROVE_AFTER polls   (normal sale)
    ...13  decline on the first status poll    (card refused)
    ...99  stay 'started' forever              (drives the driver's 2-min timeout)
Any other amount approves immediately.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

BIND = os.environ.get("PINVANDAAG_SANDBOX_BIND", "127.0.0.1")
PORT = int(os.environ.get("PINVANDAAG_SANDBOX_PORT", "7810"))
APPROVE_AFTER = 2          # status polls before a normal sale turns 'success'
TX = {}                    # transaction_id -> dict


def _receipt(tx):
    return json.dumps({
        "merchant": "AtlasPOS Sandbox",
        "terminal": tx["terminal_id"],
        "amount_cents": tx["amount"],
        "card": "SANDBOX **** 0000",
        "method": "Maestro",
        "result": tx["status"].upper(),
        "stamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[sandbox] " + fmt % args, flush=True)

    def _send(self, body, code=200):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        path = self.path.strip("/")

        # The driver must send the key server-side; refuse if it is missing.
        if not self.headers.get("x-api-key"):
            return self._send({"success": False, "status": "error",
                               "message": "missing x-api-key"}, 401)

        if path.endswith("instore/transactions/start"):
            amount = int(form.get("amount", 0))
            tx_id = "SBX%d" % (int(time.time() * 1000) % 10_000_000)
            TX[tx_id] = {"terminal_id": form.get("terminal_id"), "amount": amount,
                         "status": "started", "polls": 0}
            print("[sandbox] START %s amount=%s cents" % (tx_id, amount), flush=True)
            return self._send({"success": True, "status": "started", "transactionId": tx_id})

        if path.endswith("instore/transactions/status"):
            tx_id = form.get("transaction_id")
            tx = TX.get(tx_id)
            if not tx:
                return self._send({"success": False, "status": "error",
                                   "message": "unknown transaction"}, 404)
            tx["polls"] += 1
            # A cancelled/declined transaction is terminal: never re-evaluate it,
            # otherwise the 'never settles' scenario would undo a real cancel.
            if tx["status"] in ("failed", "cancelled"):
                out = {"success": True, "status": tx["status"], "transactionId": tx_id,
                       "receipt": _receipt(tx)}
                print("[sandbox] STATUS %s terminal -> %s" % (tx_id, tx["status"]), flush=True)
                return self._send(out)
            cents = tx["amount"] % 100
            if cents == 13:
                tx["status"] = "failed"
            elif cents == 99:
                tx["status"] = "started"          # never settles, on purpose
            elif tx["polls"] >= APPROVE_AFTER:
                tx["status"] = "success"
            print("[sandbox] STATUS %s poll=%d -> %s" % (tx_id, tx["polls"], tx["status"]), flush=True)
            out = {"success": True, "status": tx["status"], "transactionId": tx_id}
            if tx["status"] in ("success", "failed"):
                out["receipt"] = _receipt(tx)
            return self._send(out)

        if path.endswith("instore/transactions/stop"):
            tx = TX.get(form.get("transaction_id"))
            if tx:
                tx["status"] = "failed"
            print("[sandbox] STOP %s" % form.get("transaction_id"), flush=True)
            return self._send({"success": True, "status": "cancelled"})

        if path.endswith("instore/transactions/last_transaction"):
            last = list(TX.items())[-1] if TX else None
            if not last:
                return self._send({"success": True, "status": "unknown"})
            tx_id, tx = last
            return self._send({"success": True, "status": tx["status"],
                               "transactionId": tx_id, "receipt": _receipt(tx)})

        if path.endswith("instore/transactions/refund"):
            print("[sandbox] REFUND terminal=%s amount=%s" % (
                form.get("terminal_id"), form.get("amount")), flush=True)
            return self._send({"success": True, "status": "success",
                               "transactionId": "SBXREF%d" % (int(time.time()) % 100000)})

        return self._send({"success": False, "status": "error",
                           "message": "unknown endpoint %s" % path}, 404)


if __name__ == "__main__":
    print("[sandbox] Pin Vandaag REST v2 sandbox on %s:%d" % (BIND, PORT), flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
