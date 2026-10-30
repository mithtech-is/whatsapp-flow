"""v0.0.1 data patches (run via patches.txt, post_model_sync)."""

from __future__ import annotations

import frappe


def add_indexes() -> None:
    """Indexes on upstream tables we query heavily."""
    # WhatsApp Message.wd_issue is created with search_index=1, but add explicitly in case
    # the custom field pre-existed without the index.
    try:
        frappe.db.add_index("WhatsApp Message", ["wd_issue"])
    except Exception:
        pass


def backfill_issues() -> None:
    """Open an Issue for every WhatsApp Contact that has messages but no open conversation.

    Idempotent: skips contacts that already have wd_open_issue. Links the contact's existing
    messages to the new Issue. Safe to re-run.
    """
    if not frappe.db.has_column("WhatsApp Contact", "wd_open_issue"):
        return

    contacts = frappe.get_all(
        "WhatsApp Contact",
        filters={"wd_open_issue": ["in", [None, ""]]},
        fields=["name", "contact_name", "mobile_no", "wd_whatsapp_account", "email"],
    )
    for c in contacts:
        has_msg = frappe.db.exists(
            "WhatsApp Message", {"from": c.mobile_no}
        ) or frappe.db.exists("WhatsApp Message", {"to": c.mobile_no})
        if not has_msg:
            continue

        issue = frappe.new_doc("Issue")
        issue.subject = f"WhatsApp: {c.contact_name or c.mobile_no}"
        issue.wd_whatsapp_contact = c.name
        issue.wd_account = c.wd_whatsapp_account
        issue.wd_source = "inbound"
        if c.email:
            issue.raised_by = c.email
        issue.flags.ignore_permissions = True
        issue.flags.ignore_mandatory = True
        issue.insert()

        frappe.db.set_value("WhatsApp Contact", c.name, "wd_open_issue", issue.name, update_modified=False)
        frappe.db.sql(
            """update `tabWhatsApp Message` set wd_issue=%s
               where (`from`=%s or `to`=%s) and (wd_issue is null or wd_issue='')""",
            (issue.name, c.mobile_no, c.mobile_no),
        )
    frappe.db.commit()
