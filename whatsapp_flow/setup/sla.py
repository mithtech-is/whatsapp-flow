"""Default Service Level Agreement for WhatsApp conversations (#33, native-first).

Creates one ERPNext Service Level Agreement (document_type=Issue) that applies ONLY to
WhatsApp Issues via a condition on `wd_source`, so it never hijacks other Issues on the site.
Idempotent and guarded — a failure here never blocks install/migrate.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate, nowdate

SLA_NAME = "WhatsApp SLA"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# response / resolution targets per Issue Priority, in seconds
TARGETS = {
    "High": (15 * 60, 2 * 3600),
    "Medium": (60 * 60, 8 * 3600),
    "Low": (4 * 3600, 24 * 3600),
}


def ensure_default_sla() -> None:
    try:
        if not frappe.db.exists("DocType", "Service Level Agreement"):
            return
        if frappe.db.exists("Service Level Agreement", {"service_level": SLA_NAME}):
            return

        # SLA on Issue requires ERPNext's Support Settings toggle to be on.
        if frappe.db.exists("DocType", "Support Settings"):
            frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)

        # On a bare ERPNext (no setup wizard run) the Issue Priority records may not
        # exist yet. Seed the ones we target so the SLA's priority links validate.
        available = _ensure_issue_priorities()
        if not available:
            # Nothing to attach priorities to — a valid Issue SLA can't be built.
            return
        default_prio = "Medium" if "Medium" in available else available[0]

        doc = frappe.new_doc("Service Level Agreement")
        doc.service_level = SLA_NAME
        doc.document_type = "Issue"
        doc.enabled = 1
        doc.default_service_level_agreement = 0
        doc.default_priority = default_prio
        doc.apply_sla_for_resolution = 1
        # Applies only to WhatsApp Issues (wd_source set), never other Issues.
        doc.condition = "doc.get('wd_source')"

        for prio, (resp, reso) in TARGETS.items():
            if prio in available:
                doc.append(
                    "priorities",
                    {
                        "priority": prio,
                        "response_time": resp,
                        "resolution_time": reso,
                        "default_priority": 1 if prio == default_prio else 0,
                    },
                )
        for status in ("Resolved", "Closed"):
            doc.append("sla_fulfilled_on", {"status": status})
        # Pause the clock while we're waiting on the customer.
        for status in ("Replied", "On Hold"):
            doc.append("pause_sla_on", {"status": status})

        # Mandatory on ERPNext SLA: holiday list + working hours (24/7 by default).
        doc.holiday_list = _default_holiday_list()
        for day in WEEKDAYS:
            doc.append("support_and_resolution",
                       {"workday": day, "start_time": "00:00:00", "end_time": "23:59:59"})

        doc.flags.ignore_permissions = True
        doc.insert()
        # Caller (install _setup) commits; left uncommitted so tests can roll back.
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: ensure_default_sla failed")


def _ensure_issue_priorities() -> list[str]:
    """Return the Issue Priorities we target, seeding any that are missing.

    A bare ERPNext install (no setup wizard) has no Issue Priority records, which
    would make the SLA's priority links fail. Issue Priority autonames by Prompt,
    so the name is supplied via __newname.
    """
    if not frappe.db.exists("DocType", "Issue Priority"):
        return []
    available = []
    for prio in TARGETS:  # Low / Medium / High
        if not frappe.db.exists("Issue Priority", prio):
            try:
                frappe.get_doc({"doctype": "Issue Priority", "__newname": prio}).insert(
                    ignore_permissions=True
                )
            except Exception:
                frappe.clear_last_message()
        if frappe.db.exists("Issue Priority", prio):
            available.append(prio)
    return available


def _default_holiday_list() -> str:
    existing = frappe.get_all("Holiday List", limit=1, pluck="name")
    if existing:
        return existing[0]
    year = getdate(nowdate()).year
    hl = frappe.new_doc("Holiday List")
    hl.holiday_list_name = "WhatsApp Flow Holidays"
    hl.from_date = f"{year}-01-01"
    hl.to_date = f"{year}-12-31"
    hl.flags.ignore_permissions = True
    hl.insert()
    return hl.name
