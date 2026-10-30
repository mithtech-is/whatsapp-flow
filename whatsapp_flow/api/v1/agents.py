"""Agent presence, teams, and manual assignment API for the SPA (Phase 1)."""

from __future__ import annotations

import frappe
from frappe import _

from whatsapp_flow.endpoints.chat import _is_manager
from whatsapp_flow.wa_desk import assignment, teams

AVAILABILITY = ("Online", "Away", "Offline")


@frappe.whitelist()
def set_availability(availability: str):
    """Set the CURRENT user's WhatsApp availability, then re-sync their teams' rules."""
    if availability not in AVAILABILITY:
        frappe.throw(_("Invalid availability."))
    user = frappe.session.user
    frappe.db.set_value("User", user, "wd_wa_availability", availability, update_modified=False)
    for t in frappe.get_all("User Group Member", filters={"user": user}, pluck="parent"):
        teams.sync_team(t)
    return {"user": user, "availability": availability}


@frappe.whitelist()
def my_status():
    user = frappe.session.user
    return {
        "user": user,
        "availability": frappe.db.get_value("User", user, "wd_wa_availability") or "Offline",
        "is_manager": _is_manager(),
    }


@frappe.whitelist()
def list_teams():
    out = []
    for g in frappe.get_all("User Group", pluck="name"):
        mem = teams.members(g)
        out.append({"team": g, "members": len(mem), "online": len(teams.online_agents(g))})
    return out


@frappe.whitelist()
def team_agents(team: str):
    rows = []
    for u in teams.members(team):
        info = frappe.db.get_value("User", u, ["full_name", "wd_wa_availability"], as_dict=True) or {}
        rows.append(
            {
                "user": u,
                "full_name": info.get("full_name"),
                "availability": info.get("wd_wa_availability") or "Offline",
                "load": teams.open_load(u),
            }
        )
    return rows


def _issue_for_contact(contact: str) -> str | None:
    return frappe.db.get_value("WhatsApp Contact", contact, "wd_open_issue")


@frappe.whitelist()
def assign_conversation(contact: str, agent: str | None = None):
    """Assign a conversation. Agents may self-assign; assigning to others needs a manager."""
    agent = agent or frappe.session.user
    if agent != frappe.session.user and not _is_manager():
        raise frappe.PermissionError(_("Only managers can assign to other agents."))
    issue = _issue_for_contact(contact)
    if not issue:
        frappe.throw(_("No open conversation for this contact."))
    assignment.assign(issue, agent)
    # Taking a conversation pauses the bot for it.
    frappe.db.set_value("WhatsApp Contact", contact, "wd_bot_active", 0, update_modified=False)
    return {"issue": issue, "agent": agent}


@frappe.whitelist()
def resolve_conversation(contact: str):
    from whatsapp_flow.endpoints.chat import _can_access_contact

    if not _can_access_contact(contact):
        raise frappe.PermissionError(_("Not allowed."))
    issue = _issue_for_contact(contact)
    assignment.resolve_conversation(issue)
    return {"issue": issue, "status": "Resolved"}
