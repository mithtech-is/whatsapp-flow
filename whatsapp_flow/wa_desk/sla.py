"""SLA escalation ladder + auto-close (#33).

ERPNext applies the WhatsApp SLA to our Issues natively (response_by / sla_resolution_by /
agreement_status). This module adds what native SLA doesn't: an escalation ladder (WA
Escalation Level rows on the SLA) driven by a scheduled tick, and auto-close of resolved
conversations.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime, get_datetime

OPEN_STATES = ("Open", "Replied", "On Hold")


def tick() -> None:
    """Hourly: escalate WhatsApp Issues that have breached response/resolution + a level's delay."""
    levels = _escalation_levels()
    if not levels:
        return
    now = now_datetime()
    issues = frappe.get_all(
        "Issue",
        filters={"status": ["in", OPEN_STATES], "wd_whatsapp_contact": ["is", "set"]},
        fields=["name", "response_by", "sla_resolution_by", "agreement_status",
                "first_responded_on", "wd_escalation_level"],
    )
    for iss in issues:
        current = iss.wd_escalation_level or 0
        for lvl in levels:
            if lvl["level"] <= current:
                continue
            due = iss.response_by if lvl["basis"] == "Response" else iss.sla_resolution_by
            if not due:
                continue
            # Response levels only fire if there's been no first response yet.
            if lvl["basis"] == "Response" and iss.first_responded_on:
                continue
            threshold = add_to_date(get_datetime(due), minutes=lvl["minutes_after_due"])
            if now >= threshold:
                _apply(iss.name, lvl)
                frappe.db.set_value("Issue", iss.name, "wd_escalation_level", lvl["level"],
                                    update_modified=False)
    frappe.db.commit()


def _escalation_levels() -> list[dict]:
    """Escalation rows from any enabled SLA that has them (sorted by level)."""
    slas = frappe.get_all("Service Level Agreement", filters={"enabled": 1}, pluck="name")
    rows = []
    for sla in slas:
        for r in frappe.get_all(
            "WA Escalation Level",
            filters={"parent": sla, "parenttype": "Service Level Agreement"},
            fields=["level", "basis", "minutes_after_due", "action", "escalate_to"],
        ):
            rows.append(r)
    return sorted(rows, key=lambda r: r["level"])


def _apply(issue: str, lvl: dict) -> None:
    from whatsapp_flow.wa_desk import assignment

    try:
        contact = frappe.db.get_value("Issue", issue, "wd_whatsapp_contact")
        assignee = frappe.db.get_value("WhatsApp Contact", contact, "email") if contact else None
        if lvl["action"] == "Reassign":
            if lvl.get("escalate_to"):
                assignment.assign(issue, lvl["escalate_to"], description="SLA escalation")
            else:
                assignment.auto_assign(issue)
        else:
            target = assignee if lvl["action"] == "Notify Assignee" else _manager_of(contact)
            _notify(target, issue, lvl)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: escalation apply failed")


def _manager_of(contact: str | None) -> str | None:
    """A WA Manager on the contact's team, else any WA Manager."""
    team = frappe.db.get_value("WhatsApp Contact", contact, "wd_team") if contact else None
    if team:
        from whatsapp_flow.wa_desk import teams

        for u in teams.members(team):
            if "WA Manager" in frappe.get_roles(u):
                return u
    mgrs = frappe.get_all("Has Role", filters={"role": "WA Manager", "parenttype": "User"}, pluck="parent")
    return mgrs[0] if mgrs else None


def _notify(user: str | None, issue: str, lvl: dict) -> None:
    if not user:
        return
    frappe.get_doc(
        {
            "doctype": "Notification Log",
            "for_user": user,
            "type": "Alert",
            "subject": f"SLA escalation (L{lvl['level']}) on WhatsApp conversation {issue}",
            "document_type": "Issue",
            "document_name": issue,
        }
    ).insert(ignore_permissions=True)


def auto_close() -> None:
    """Daily: close resolved WhatsApp Issues untouched for WA Settings.wd_auto_close_days."""
    try:
        days = frappe.db.get_single_value("WhatsApp Settings", "wd_auto_close_days")
    except Exception:
        days = None
    if not days or int(days) <= 0:
        return
    cutoff = add_to_date(now_datetime(), days=-int(days))
    stale = frappe.get_all(
        "Issue",
        filters={"status": "Resolved", "wd_whatsapp_contact": ["is", "set"],
                 "modified": ["<", cutoff]},
        pluck="name",
    )
    for name in stale:
        frappe.db.set_value("Issue", name, "status", "Closed")
    if stale:
        frappe.db.commit()
