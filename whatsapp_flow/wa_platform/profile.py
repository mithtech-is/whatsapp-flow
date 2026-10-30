"""WhatsApp Business profile get/update via Meta (#63)."""

from __future__ import annotations

import frappe
from frappe import _

from whatsapp_flow.wa_core import meta_client

PROFILE_FIELDS = "about,address,description,email,profile_picture_url,websites,vertical"


def _guard():
    from whatsapp_flow.endpoints.chat import _is_manager

    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))


@frappe.whitelist()
def get_profile(account: str | None = None):
    _guard()
    acc = meta_client.get_account(account)
    resp = meta_client.get(f"{acc.phone_id}/whatsapp_business_profile",
                           account=acc.name, params={"fields": PROFILE_FIELDS})
    data = (resp or {}).get("data") or []
    return data[0] if data else {}


@frappe.whitelist()
def update_profile(account: str | None = None, **fields):
    _guard()
    acc = meta_client.get_account(account)
    allowed = {"about", "address", "description", "email", "vertical", "websites"}
    payload = {"messaging_product": "whatsapp"}
    payload.update({k: v for k, v in fields.items() if k in allowed})
    return meta_client.post(f"{acc.phone_id}/whatsapp_business_profile", payload, account=acc.name)
