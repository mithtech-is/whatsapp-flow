"""Agent tools for the SPA (Phase 1): private notes, canned responses, tags.

Notes use native Comment on the Issue (#34). Tags use native Tag on WhatsApp Contact (#36).
Canned responses are the WA Canned Response DocType (#35) with simple placeholder rendering.
"""

from __future__ import annotations

import frappe
from frappe import _

from whatsapp_flow.endpoints.chat import _can_access_contact


def _guard(contact: str) -> None:
    if not _can_access_contact(contact):
        raise frappe.PermissionError(_("Not allowed to access this conversation."))


def _issue_for(contact: str) -> str | None:
    return frappe.db.get_value("WhatsApp Contact", contact, "wd_open_issue")


# --------------------------------------------------------------------------- notes
@frappe.whitelist()
def add_note(contact: str, content: str):
    _guard(contact)
    issue = _issue_for(contact)
    if not issue:
        frappe.throw(_("No open conversation to note against."))
    c = frappe.get_doc("Issue", issue).add_comment("Comment", content)
    return {"name": c.name, "content": content, "owner": frappe.session.user, "creation": str(c.creation)}


@frappe.whitelist()
def list_notes(contact: str):
    _guard(contact)
    issue = _issue_for(contact)
    if not issue:
        return []
    return frappe.get_all(
        "Comment",
        filters={"reference_doctype": "Issue", "reference_name": issue, "comment_type": "Comment"},
        fields=["name", "content", "owner", "creation"],
        order_by="creation desc",
    )


# --------------------------------------------------------------------------- canned
@frappe.whitelist()
def list_canned(team: str | None = None):
    rows = frappe.get_all(
        "WA Canned Response",
        filters={"enabled": 1},
        fields=["name", "title", "shortcut", "message", "team"],
        order_by="title asc",
    )
    # team-scoped responses only show for their team (or when unscoped)
    return [r for r in rows if not r.team or not team or r.team == team]


@frappe.whitelist()
def render_canned(contact: str, shortcut: str):
    _guard(contact)
    row = frappe.db.get_value(
        "WA Canned Response", {"shortcut": shortcut, "enabled": 1}, ["message"], as_dict=True
    )
    if not row:
        frappe.throw(_("Unknown shortcut {0}").format(shortcut))
    c = frappe.db.get_value("WhatsApp Contact", contact, ["contact_name", "mobile_no"], as_dict=True) or {}
    msg = row.message or ""
    msg = msg.replace("{{ contact_name }}", c.get("contact_name") or "")
    msg = msg.replace("{{contact_name}}", c.get("contact_name") or "")
    msg = msg.replace("{{ number }}", c.get("mobile_no") or "")
    msg = msg.replace("{{number}}", c.get("mobile_no") or "")
    return {"message": msg}


# --------------------------------------------------------------------------- tags
@frappe.whitelist()
def add_tag(contact: str, tag: str):
    _guard(contact)
    from frappe.desk.doctype.tag.tag import add_tag as _add

    _add(tag, "WhatsApp Contact", contact)
    return {"tag": tag}


@frappe.whitelist()
def remove_tag(contact: str, tag: str):
    _guard(contact)
    from frappe.desk.doctype.tag.tag import remove_tag as _remove

    _remove(tag, "WhatsApp Contact", contact)
    return {"tag": tag}


@frappe.whitelist()
def list_tags(contact: str):
    _guard(contact)
    return frappe.get_all(
        "Tag Link",
        filters={"document_type": "WhatsApp Contact", "document_name": contact},
        pluck="tag",
    )
