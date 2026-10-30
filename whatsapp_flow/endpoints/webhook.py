"""Secured webhook override (§2.1).

Replaces `frappe_whatsapp.utils.webhook.webhook` via override_whitelisted_methods. The URL is
unchanged (Meta keeps posting to the same path); only the handler differs.

Upstream problems fixed here:
  * No signature check          -> HMAC verify, fail closed.
  * Synchronous processing in   -> verify + log + enqueue to background, return 200 fast,
    Meta's request                 then reuse the upstream parser off-request.

GET (verification handshake) is delegated to the upstream `get()` unchanged.
"""

from __future__ import annotations

import frappe
from werkzeug.wrappers import Response

from whatsapp_flow.wa_core import signature

WA_WEBHOOK_QUEUE = "default"


@frappe.whitelist(allow_guest=True)
def webhook():
    if frappe.request.method == "GET":
        # Reuse upstream verification (hub.challenge / verify_token) as-is.
        from frappe_whatsapp.utils.webhook import get

        return get()
    return _post()


def _post():
    raw = frappe.request.get_data()  # raw bytes — required for an exact HMAC
    header = frappe.get_request_header("X-Hub-Signature-256")

    if not signature.verify(raw, header):
        # Fail closed. Log minimally (no body) and return 403.
        frappe.log_error("Rejected: bad or missing X-Hub-Signature-256", "whatsapp_flow webhook")
        return Response("forbidden", status=403)

    # Signature OK — snapshot the parsed payload, enqueue, and ack immediately.
    data = dict(frappe.local.form_dict)
    data.pop("cmd", None)

    frappe.enqueue(
        "whatsapp_flow.endpoints.webhook.process_webhook",
        queue=WA_WEBHOOK_QUEUE,
        enqueue_after_commit=False,
        data=data,
    )
    return Response("ok", status=200)


def process_webhook(data: dict) -> None:
    """Background worker: reuse the upstream parser to create WhatsApp Message(s).

    The upstream `post()` reads `frappe.local.form_dict`, so we repopulate it in the worker
    and delegate — keeping their (tolerant) parsing and status handling, and letting our
    doc_events fire on the created messages.
    """
    from frappe_whatsapp.utils import webhook as upstream

    try:
        frappe.local.form_dict = frappe._dict(data)
        upstream.post()
        _touch_webhook_last_seen(data)
        _route_calls(data)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: webhook processing failed")


def _route_calls(data: dict) -> None:
    """Dispatch any `calls` change values to the voice handler (#1-#12)."""
    try:
        from whatsapp_flow.wa_voice.calls import on_calls_webhook

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("calls"):
                    on_calls_webhook(value)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: calls routing failed")


def _touch_webhook_last_seen(data: dict) -> None:
    try:
        phone_id = (
            data.get("entry", [{}])[0]
            .get("changes", [{}])[0]
            .get("value", {})
            .get("metadata", {})
            .get("phone_number_id")
        )
        if not phone_id:
            return
        name = frappe.db.get_value("WhatsApp Account", {"phone_id": phone_id})
        if name:
            frappe.db.set_value(
                "WhatsApp Account", name, "wd_webhook_last_seen", frappe.utils.now_datetime(),
                update_modified=False,
            )
    except Exception:
        pass
