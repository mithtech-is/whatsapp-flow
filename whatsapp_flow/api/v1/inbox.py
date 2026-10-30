"""Inbox API for the /whatsapp SPA (Phase 1).

Scoped conversation list (left pane) + contact detail (right panel). Messages and sending reuse
the secured whatsapp_chat endpoints (whatsapp_flow.endpoints.chat). Phone numbers are masked
here when WhatsApp Settings.wd_phone_masking is on (#41).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from whatsapp_flow.endpoints.chat import _is_manager

OPEN_STATES = ("Open", "Replied", "On Hold")


def _masking() -> bool:
    try:
        return bool(frappe.db.get_single_value("WhatsApp Settings", "wd_phone_masking"))
    except Exception:
        return False


def mask_number(number: str | None, mask: bool | None = None) -> str:
    if not number:
        return ""
    if mask is None:
        mask = _masking()
    if not mask or len(number) <= 4:
        return number or ""
    return "•••••" + number[-4:]


def _agent_contact_filter() -> dict | None:
    """None => manager (see all). Otherwise a filter restricting to the agent's own contacts."""
    if _is_manager():
        return None
    return {"email": frappe.session.user}


@frappe.whitelist()
def list_conversations(status: str = "Open", search: str | None = None, limit: int = 50):
    """Left-pane list. Managers see all; agents see contacts assigned to them (Contact.email)."""
    mask = _masking()
    contact_filters: dict = {}
    agent_filter = _agent_contact_filter()
    if agent_filter:
        contact_filters.update(agent_filter)
    if search:
        contact_filters["contact_name"] = ["like", f"%{search}%"]

    contacts = frappe.get_all(
        "WhatsApp Contact",
        filters=contact_filters,
        fields=[
            "name", "contact_name", "mobile_no", "email", "last_message", "is_read",
            "wd_open_issue", "wd_unread_count", "wd_window_expires_at", "wd_team",
            "wd_bot_active", "modified",
        ],
        order_by="modified desc",
        limit_page_length=frappe.utils.cint(limit) or 50,
    )

    now = now_datetime()
    rows = []
    for c in contacts:
        issue_status = None
        if c.wd_open_issue:
            issue_status = frappe.db.get_value("Issue", c.wd_open_issue, "status")
        if status and status != "All":
            # "Open" = has an open issue in an open state; "Unassigned" = open issue, no email
            if status == "Open" and issue_status not in OPEN_STATES:
                continue
            if status == "Resolved" and issue_status not in ("Resolved", "Closed"):
                continue
        rows.append(
            {
                "contact": c.name,
                "contact_name": c.contact_name,
                "number": mask_number(c.mobile_no, mask),
                "issue": c.wd_open_issue,
                "status": issue_status,
                "last_message": c.last_message,
                "unread": c.wd_unread_count or 0,
                "is_read": c.is_read,
                "assignee": c.email,
                "team": c.wd_team,
                "bot_active": c.wd_bot_active,
                "window_open": bool(c.wd_window_expires_at and c.wd_window_expires_at > now),
                "window_expires_at": c.wd_window_expires_at,
                "modified": c.modified,
            }
        )
    return rows


@frappe.whitelist()
def get_contact(contact: str):
    """Right-panel contact detail. Permission-checked via the same rule as the chat endpoints."""
    from whatsapp_flow.endpoints.chat import _can_access_contact

    if not _can_access_contact(contact):
        raise frappe.PermissionError(_("Not allowed to view this contact."))

    c = frappe.get_doc("WhatsApp Contact", contact)
    mask = _masking()
    data = {
        "contact": c.name,
        "contact_name": c.contact_name,
        "number": mask_number(c.mobile_no, mask),
        "raw_number": c.mobile_no if not mask else None,
        "email": c.get("email"),
        "assignee": c.get("email"),
        "team": c.get("wd_team"),
        "bot_active": c.get("wd_bot_active"),
        "marketing_opt_out": c.get("wd_marketing_opt_out"),
        "language": c.get("wd_language"),
        "window_expires_at": c.get("wd_window_expires_at"),
        "open_issue": c.get("wd_open_issue"),
        "profile": c.get("wd_profile"),
        "tags": frappe.get_all(
            "Tag Link",
            filters={"document_type": "WhatsApp Contact", "document_name": c.name},
            pluck="tag",
        ),
        "custom_data": c.get("wd_custom_data"),
    }
    if c.get("wd_open_issue"):
        issue = frappe.db.get_value(
            "Issue", c.wd_open_issue,
            ["name", "status", "priority", "agreement_status", "response_by", "sla_resolution_by"],
            as_dict=True,
        )
        data["issue"] = issue
    return data


@frappe.whitelist()
def get_messages(contact: str, limit: int = 200):
    """Message thread for a contact (permission-checked). Resolves the number server-side so
    the masked client never needs the raw number."""
    from whatsapp_flow.endpoints.chat import _guard_contact

    _guard_contact(contact)
    number = frappe.db.get_value("WhatsApp Contact", contact, "mobile_no")
    if not number:
        return []
    return frappe.get_all(
        "WhatsApp Message",
        or_filters=[{"from": number}, {"to": number}],
        fields=[
            "name", "creation", "type", "`from`", "`to`", "message", "attach", "content_type",
            "message_type", "template", "buttons", "status", "message_id",
            "reply_to_message_id", "is_reply", "wd_agent",
        ],
        order_by="creation asc",
        limit_page_length=frappe.utils.cint(limit) or 200,
    )


@frappe.whitelist()
def send_message(contact: str, content: str | None = None, template: str | None = None,
                 buttons=None, attachment: str | None = None, reaction_to: str | None = None,
                 body_param=None):
    """Send from the SPA by contact name. Resolves the number and delegates to the secured
    chat.send (which goes through the WhatsApp Message send guard)."""
    from whatsapp_flow.endpoints.chat import send as chat_send

    number = frappe.db.get_value("WhatsApp Contact", contact, "mobile_no")
    if not number:
        frappe.throw(_("Contact has no mobile number."))
    return chat_send(
        content=content, user=frappe.session.user, room=contact, user_no=number,
        attachment=attachment, template=template, buttons=buttons, reaction_to=reaction_to,
        body_param=body_param,
    )


@frappe.whitelist()
def list_templates():
    """Approved WhatsApp templates available to send from the composer (#38)."""
    rows = frappe.get_all(
        "WhatsApp Templates",
        filters={"status": "APPROVED"},
        fields=["name", "template_name", "actual_name", "language_code", "header_type",
                "sample_values", "field_names"],
        order_by="template_name asc",
    )
    for r in rows:
        params = (r.get("field_names") or r.get("sample_values") or "")
        r["params"] = [p.strip() for p in params.split(",") if p.strip()] if params else []
        r.pop("sample_values", None)
        r.pop("field_names", None)
    return rows


@frappe.whitelist()
def counts():
    """Badge counts for the inbox tabs (scoped)."""
    rows = list_conversations(status="All", limit=500)
    return {
        "open": sum(1 for r in rows if r["status"] in OPEN_STATES),
        "unread": sum(1 for r in rows if (r["unread"] or 0) > 0),
        "mine": sum(1 for r in rows if r["assignee"] == frappe.session.user),
    }
