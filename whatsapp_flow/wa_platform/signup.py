"""Embedded Signup + Coexistence (#62): create a WhatsApp Account from the signup exchange.

The SPA runs Meta's Embedded Signup JS and sends back the short-lived `code`, the selected
`waba_id` and `phone_number_id`. We exchange the code for a token and create a WhatsApp Account.
The actual exchange needs the Meta app (Tech Provider) id/secret in WA Settings; guarded so it
fails clearly when not configured.
"""

from __future__ import annotations

import frappe
from frappe import _

from whatsapp_flow.wa_core import meta_client


@frappe.whitelist()
def exchange(code: str, waba_id: str, phone_number_id: str, account_name: str | None = None):
    from whatsapp_flow.endpoints.chat import _is_manager

    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))

    app_id = frappe.db.get_single_value("WhatsApp Settings", "wd_meta_app_id")
    app_secret = None
    try:
        app_secret = frappe.get_doc("WhatsApp Settings").get_password("wd_meta_app_secret", raise_exception=False)
    except Exception:
        pass
    if not app_id or not app_secret:
        frappe.throw(_("Configure Meta App ID/Secret in WhatsApp Settings for Embedded Signup."))

    # Exchange the code for a business token.
    from frappe.integrations.utils import make_get_request

    token_resp = make_get_request(
        "https://graph.facebook.com/v21.0/oauth/access_token",
        params={"client_id": app_id, "client_secret": app_secret, "code": code},
    )
    access_token = (token_resp or {}).get("access_token")
    if not access_token:
        frappe.throw(_("Token exchange failed."))

    name = account_name or f"WA {phone_number_id}"
    if frappe.db.exists("WhatsApp Account", name):
        doc = frappe.get_doc("WhatsApp Account", name)
    else:
        doc = frappe.new_doc("WhatsApp Account")
        doc.account_name = name
    doc.phone_id = phone_number_id
    doc.business_id = waba_id
    doc.token = access_token
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_permissions = True
    doc.save()
    return {"account": doc.name}
