"""Assignment + bot→human handoff (plan §5.3).

Uses native ToDo (via frappe.desk.form.assign_to) on the Issue (the conversation), and mirrors
the assignee onto WhatsApp Contact.email so whatsapp_chat's realtime chat bubble notifies the
agent. Handoff is driven by the WhatsApp Agent Transfer doc_event.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as _assign_add
from frappe.desk.form.assign_to import remove as _assign_remove

from whatsapp_flow.wa_desk import teams


def _contact_for_issue(issue: str) -> str | None:
    return frappe.db.get_value("Issue", issue, "wd_whatsapp_contact")


def assign(issue: str, agent: str, description: str | None = None) -> None:
    """Assign an Issue (conversation) to an agent: ToDo + mirror to Contact.email."""
    if not issue or not agent:
        return
    already = frappe.get_all(
        "ToDo",
        filters={"reference_type": "Issue", "reference_name": issue, "allocated_to": agent, "status": "Open"},
        limit=1,
    )
    if not already:
        _assign_add(
            {
                "doctype": "Issue",
                "name": issue,
                "assign_to": [agent],
                "description": description or _("WhatsApp conversation"),
            }
        )
    contact = _contact_for_issue(issue)
    if contact:
        frappe.db.set_value("WhatsApp Contact", contact, "email", agent, update_modified=False)


def unassign(issue: str, agent: str) -> None:
    if issue and agent:
        try:
            _assign_remove("Issue", issue, agent)
        except Exception:
            pass


def auto_assign(issue: str, team: str | None = None) -> str | None:
    """Pick an agent from the team and assign. Returns the chosen agent (or None if queue empty)."""
    contact = _contact_for_issue(issue)
    team = team or (frappe.db.get_value("WhatsApp Contact", contact, "wd_team") if contact else None)
    if not team:
        return None
    agent = teams.pick_agent(team)
    if agent:
        assign(issue, agent)
    return agent


def on_agent_transfer(doc, method=None) -> None:
    """WhatsApp Agent Transfer after_insert: pause the bot, set team, assign (or queue)."""
    try:
        issue = doc.get("wd_issue")
        team = doc.get("wd_team")
        contact = _contact_for_issue(issue) if issue else None
        if contact:
            frappe.db.set_value(
                "WhatsApp Contact", contact,
                {"wd_bot_active": 0, "wd_team": team}, update_modified=False,
            )
        if not issue:
            return
        agent = auto_assign(issue, team)
        doc.db_set("wd_picked_up_by", agent, update_modified=False)
        doc.db_set("wd_queue_status", "Assigned" if agent else "Queued", update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: on_agent_transfer failed")


def resolve_conversation(issue: str) -> None:
    """Mark the Issue resolved and re-activate the bot for that contact."""
    if not issue:
        return
    frappe.db.set_value("Issue", issue, "status", "Resolved")
    contact = _contact_for_issue(issue)
    if contact:
        frappe.db.set_value("WhatsApp Contact", contact, "wd_bot_active", 1, update_modified=False)
