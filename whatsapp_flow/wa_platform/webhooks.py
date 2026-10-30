"""Outbound webhook SSRF hardening (#66).

Native Frappe `Webhook` handles outbound webhooks on doc events. We add an SSRF check on save —
scoped to Webhooks targeting WhatsApp Flow doctypes, so we never interfere with other apps'
webhooks on this site.
"""

from __future__ import annotations

from whatsapp_flow.wa_core import ssrf

WA_WEBHOOK_DOCTYPES = {
    "WhatsApp Message", "WhatsApp Contact", "Issue", "WhatsApp Agent Transfer",
    "WA Flow Response", "Bulk WhatsApp Message",
}


def validate_webhook(doc, method=None):
    if doc.get("webhook_doctype") in WA_WEBHOOK_DOCTYPES and doc.get("request_url"):
        ssrf.validate(doc.request_url)
