"""Log retention (daily scheduler).

Deletes WhatsApp Notification Log rows older than WhatsApp Settings.wd_retention_days.
No-op when retention is unset/<= 0. Refined in Phase 5 (platform).
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime


def run_retention() -> None:
    try:
        days = frappe.db.get_single_value("WhatsApp Settings", "wd_retention_days")
    except Exception:
        return
    if not days or int(days) <= 0:
        return

    cutoff = add_to_date(now_datetime(), days=-int(days))
    if frappe.db.exists("DocType", "WhatsApp Notification Log"):
        frappe.db.delete("WhatsApp Notification Log", {"creation": ["<", cutoff]})
        frappe.db.commit()
