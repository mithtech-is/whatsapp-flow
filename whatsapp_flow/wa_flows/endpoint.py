"""Secured encrypted Flows data-exchange endpoint (§2.1, #64).

Replaces the upstream stub (which read plaintext and never decrypted). Decrypts Meta's request
with the business RSA private key (WhatsApp Settings.wd_flows_private_key), processes the action,
stores a WA Flow Response, and returns the AES-GCM encrypted response Meta expects.
"""

from __future__ import annotations

import json

import frappe
from werkzeug.wrappers import Response

from whatsapp_flow.wa_flows import crypto


@frappe.whitelist(allow_guest=True)
def handle_flow_request():
    if frappe.request.method == "GET":
        return {"status": "ok"}

    body = frappe.request.get_json(silent=True) or {}

    # Encrypted path (production). Fall back to plaintext only in dev (no crypto fields).
    if body.get("encrypted_flow_data"):
        pem = _private_key()
        if not pem:
            return Response("private key not configured", status=500)
        try:
            data, aes_key, iv = crypto.decrypt_request(body, pem)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "whatsapp_flow: flow decrypt failed")
            return Response("decryption failed", status=421)  # Meta: refresh public key
        response = _process(data)
        return Response(crypto.encrypt_response(response, aes_key, iv), status=200,
                        mimetype="text/plain")

    # Plaintext dev fallback
    return _process(body)


def _private_key() -> str | None:
    try:
        return frappe.get_doc("WhatsApp Settings").get_password(
            "wd_flows_private_key", raise_exception=False
        )
    except Exception:
        return None


def _process(data: dict) -> dict:
    action = data.get("action")
    if action == "ping":
        return {"data": {"status": "active"}}

    flow_token = data.get("flow_token")
    screen = data.get("screen")
    form = data.get("data", {})

    if action in ("data_exchange", "INIT", "complete") and flow_token:
        _save(flow_token, action, screen, form)

    # Minimal navigation: acknowledge. Real screen routing is per-flow (Phase 3b+).
    if action == "complete" or form.get("flow_action") == "complete":
        return {"screen": "SUCCESS", "data": {}}
    return {"screen": screen or "SUCCESS", "data": {}}


def _save(flow_token, action, screen, form) -> None:
    try:
        number = form.get("number") or form.get("phone")
        frappe.get_doc(
            {
                "doctype": "WA Flow Response",
                "flow_token": flow_token,
                "action": action,
                "screen": screen,
                "number": number,
                "response_json": json.dumps(form),
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: WA Flow Response save failed")
