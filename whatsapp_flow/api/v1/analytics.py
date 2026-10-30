"""Analytics API for the SPA dashboard.

Aggregates over Issue (conversations), WhatsApp Message (volume) and Bulk
WhatsApp Message (campaigns). Read-only; visible to any agent.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, getdate, nowdate


@frappe.whitelist()
def overview():
    today = nowdate()
    start_today = f"{today} 00:00:00"

    # Conversations = WhatsApp-sourced Issues.
    issue_filters = {}
    total_conv = frappe.db.count("Issue", issue_filters)
    open_conv = frappe.db.count("Issue", {"status": ["in", ["Open", "Replied"]]})
    resolved_conv = frappe.db.count("Issue", {"status": ["in", ["Resolved", "Closed"]]})

    # Messages.
    msgs_today = frappe.db.count("WhatsApp Message", {"creation": [">=", start_today]})
    incoming = frappe.db.count("WhatsApp Message", {"type": "Incoming"})
    outgoing = frappe.db.count("WhatsApp Message", {"type": "Outgoing"})

    # Templates & campaigns.
    templates = frappe.db.count("WhatsApp Templates")
    approved_templates = frappe.db.count("WhatsApp Templates", {"status": "APPROVED"})
    campaigns = frappe.db.count("Bulk WhatsApp Message")
    active_campaigns = frappe.db.count(
        "Bulk WhatsApp Message", {"status": ["in", ["Queued", "In Progress", "Scheduled"]]}
    )

    return {
        "cards": [
            {"key": "conversations", "label": "Conversations", "value": total_conv, "accent": "#16a34a"},
            {"key": "open", "label": "Open now", "value": open_conv, "accent": "#f59e0b"},
            {"key": "resolved", "label": "Resolved", "value": resolved_conv, "accent": "#2563eb"},
            {"key": "msgs_today", "label": "Messages today", "value": msgs_today, "accent": "#0891b2"},
            {"key": "templates", "label": "Approved templates", "value": approved_templates, "sub": f"of {templates}", "accent": "#7c3aed"},
            {"key": "campaigns", "label": "Campaigns", "value": campaigns, "sub": f"{active_campaigns} active", "accent": "#db2777"},
        ],
        "io": {"incoming": incoming, "outgoing": outgoing},
    }


@frappe.whitelist()
def volume_series(days: int = 7):
    days = int(days)
    buckets = []
    for i in range(days - 1, -1, -1):
        d = getdate(add_to_date(nowdate(), days=-i))
        start = f"{d} 00:00:00"
        end = f"{d} 23:59:59"
        incoming = frappe.db.count(
            "WhatsApp Message", {"type": "Incoming", "creation": ["between", [start, end]]}
        )
        outgoing = frappe.db.count(
            "WhatsApp Message", {"type": "Outgoing", "creation": ["between", [start, end]]}
        )
        buckets.append(
            {"date": str(d), "label": d.strftime("%a"), "incoming": incoming, "outgoing": outgoing}
        )
    return {"series": buckets}


@frappe.whitelist()
def status_breakdown():
    rows = frappe.db.sql(
        "select status, count(name) as n from `tabIssue` group by status order by n desc",
        as_dict=True,
    )
    return {"rows": [{"status": r.status or "—", "count": r.n} for r in rows]}


@frappe.whitelist()
def campaign_results(limit: int = 8):
    rows = frappe.get_all(
        "Bulk WhatsApp Message",
        fields=["name", "title", "status", "recipient_count", "sent_count", "wd_skipped_count", "modified"],
        order_by="modified desc",
        limit=int(limit),
    )
    return {"rows": rows}
