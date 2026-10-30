"""Conversation wiring: link every WhatsApp Message to an ERPNext Issue (the episode).

Runs as `after_insert` on WhatsApp Message, LAST in install order — so whatsapp_chat has
already created/updated the WhatsApp Contact (its `last_message` hook) by the time we run.

Responsibilities (Phase 0):
  * find/open the Issue for the contact and stamp WhatsApp Message.wd_issue
  * on inbound: open/renew the 24h window, bump unread, honour STOP/START opt-out keywords
Assignment, SLA and team realtime are layered on in Phase 1/2. Never raises — a failure here
must not break the message save.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

OPT_OUT_KEYWORDS = {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
OPT_IN_KEYWORDS = {"START", "SUBSCRIBE", "UNSTOP"}
OPEN_ISSUE_STATES = {"Open", "Replied", "On Hold"}


def on_message(doc, method=None) -> None:
    try:
        _on_message(doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: conversation wiring failed")


def _on_message(doc) -> None:
    is_incoming = getattr(doc, "type", None) == "Incoming"
    mobile_no = doc.get("from") if is_incoming else doc.get("to")
    if not mobile_no:
        return

    contact_name = frappe.db.get_value("WhatsApp Contact", {"mobile_no": mobile_no})
    if not contact_name:
        return  # whatsapp_chat normally creates it first; nothing to link to otherwise.
    contact = frappe.get_doc("WhatsApp Contact", contact_name)

    if is_incoming:
        _handle_opt_keywords(contact, doc)
        _renew_window(contact)
        _bump_unread(contact)

    issue = _find_or_open_issue(contact, doc, is_incoming)
    if issue:
        frappe.db.set_value("WhatsApp Message", doc.name, "wd_issue", issue, update_modified=False)

    _publish_update(contact, doc, is_incoming)


def _publish_update(contact, doc, is_incoming: bool) -> None:
    """Push a realtime event so the SPA inbox updates live (team realtime, #44).

    Targeted at the current assignee (WhatsApp Contact.email). The SPA also polls as a
    fallback, so delivery is best-effort here.
    """
    try:
        payload = {
            "contact": contact.name,
            "contact_name": contact.get("contact_name"),
            "direction": "in" if is_incoming else "out",
            "preview": (doc.get("message") or doc.get("attach") or "")[:120],
            "unread": contact.get("wd_unread_count") or 0,
        }
        assignee = contact.get("email")
        frappe.publish_realtime(
            "whatsapp_flow:update", payload, user=assignee or None, after_commit=True
        )
    except Exception:
        pass


def _handle_opt_keywords(contact, doc) -> None:
    text = (doc.get("message") or "").strip().upper()
    if not text:
        return
    if text in OPT_OUT_KEYWORDS and not contact.get("wd_marketing_opt_out"):
        contact.db_set("wd_marketing_opt_out", 1, update_modified=False)
        contact.db_set("wd_opt_out_on", now_datetime(), update_modified=False)
        contact.db_set("wd_opt_out_source", "keyword", update_modified=False)
    elif text in OPT_IN_KEYWORDS and contact.get("wd_marketing_opt_out"):
        contact.db_set("wd_marketing_opt_out", 0, update_modified=False)
        contact.db_set("wd_opt_out_on", None, update_modified=False)
        contact.db_set("wd_opt_out_source", "keyword:opt-in", update_modified=False)


def _renew_window(contact) -> None:
    contact.db_set(
        "wd_window_expires_at", add_to_date(now_datetime(), hours=24), update_modified=False
    )


def _bump_unread(contact) -> None:
    contact.db_set("wd_unread_count", (contact.get("wd_unread_count") or 0) + 1, update_modified=False)


def _find_or_open_issue(contact, doc, is_incoming: bool) -> str | None:
    open_issue = contact.get("wd_open_issue")
    if open_issue:
        status = frappe.db.get_value("Issue", open_issue, "status")
        if status in OPEN_ISSUE_STATES:
            return open_issue

    # Outbound messages don't themselves open an episode unless one is already open.
    if not is_incoming:
        return None

    issue = frappe.new_doc("Issue")
    issue.subject = f"WhatsApp: {contact.get('contact_name') or contact.get('mobile_no')}"
    issue.wd_whatsapp_contact = contact.name
    issue.wd_account = contact.get("wd_whatsapp_account")
    issue.wd_source = "inbound"
    if contact.get("email"):
        issue.raised_by = contact.get("email")
    issue.flags.ignore_permissions = True
    issue.flags.ignore_mandatory = True
    issue.insert()

    contact.db_set("wd_open_issue", issue.name, update_modified=False)
    return issue.name
