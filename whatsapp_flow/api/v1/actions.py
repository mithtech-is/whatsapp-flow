"""Custom inbox actions (#42): Webhook / URL / Client Script buttons in the conversation.

Webhook actions POST/GET to a URL (SSRF-guarded) with conversation context. URL actions
return a resolved link for the client to open. Client Script actions are listed only (they run
in the SPA).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.integrations.utils import make_get_request, make_post_request

from whatsapp_flow.endpoints.chat import _can_access_contact
from whatsapp_flow.wa_core import ssrf


@frappe.whitelist()
def list_actions(team: str | None = None):
    rows = frappe.get_all(
        "WA Custom Action",
        filters={"enabled": 1},
        fields=["name", "title", "action_type", "url", "http_method", "open_in_new_tab", "team"],
        order_by="title asc",
    )
    return [r for r in rows if not r.team or not team or r.team == team]


def _context(contact: str) -> dict:
    c = frappe.db.get_value(
        "WhatsApp Contact", contact, ["mobile_no", "wd_open_issue", "contact_name"], as_dict=True
    ) or {}
    return {"contact": contact, "number": c.get("mobile_no"), "issue": c.get("wd_open_issue"),
            "contact_name": c.get("contact_name")}


def _render(template: str, ctx: dict) -> str:
    out = template or ""
    for k, v in ctx.items():
        out = out.replace("{{ %s }}" % k, str(v or "")).replace("{{%s}}" % k, str(v or ""))
    return out


@frappe.whitelist()
def execute_action(action: str, contact: str):
    if not _can_access_contact(contact):
        raise frappe.PermissionError(_("Not allowed."))
    act = frappe.get_doc("WA Custom Action", action)
    if not act.enabled:
        frappe.throw(_("Action is disabled."))
    ctx = _context(contact)

    if act.action_type == "URL":
        return {"type": "URL", "url": _render(act.url, ctx), "new_tab": bool(act.open_in_new_tab)}

    if act.action_type == "Webhook":
        url = _render(act.url, ctx)
        ssrf.validate(url)
        if (act.http_method or "POST") == "POST":
            payload = json.loads(_render(act.payload_template, ctx)) if act.payload_template else ctx
            resp = make_post_request(url, data=json.dumps(payload),
                                     headers={"Content-Type": "application/json"})
        else:
            resp = make_get_request(url, params=ctx)
        return {"type": "Webhook", "ok": True, "response": resp}

    # Client Script runs in the SPA; nothing to do server-side.
    return {"type": act.action_type}
