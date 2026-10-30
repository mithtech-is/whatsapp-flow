"""Campaign controls API for the SPA (#46-#49): list/create + pause/resume/cancel + segments."""

from __future__ import annotations

import json

import frappe
from frappe import _

from whatsapp_flow.endpoints.chat import _is_manager
from whatsapp_flow.wa_campaign import segments

LIST_FIELDS = [
    "name",
    "title",
    "status",
    "template",
    "whatsapp_account",
    "recipient_type",
    "recipient_list",
    "wd_segment",
    "recipient_count",
    "sent_count",
    "wd_skipped_count",
    "scheduled_time",
    "modified",
]


def _guard_manager():
    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))


@frappe.whitelist()
def list_campaigns():
    return frappe.get_all(
        "Bulk WhatsApp Message", fields=LIST_FIELDS, order_by="modified desc"
    )


@frappe.whitelist()
def get_campaign(name: str):
    doc = frappe.get_doc("Bulk WhatsApp Message", name)
    return doc.as_dict()


@frappe.whitelist()
def new_campaign_options():
    """Templates, segments, recipient lists and accounts for the broadcast composer."""
    return {
        "templates": frappe.get_all(
            "WhatsApp Templates",
            filters={"status": "APPROVED"},
            fields=["name", "template_name", "language_code", "category"],
            order_by="template_name",
        ),
        "all_templates": frappe.get_all(
            "WhatsApp Templates",
            fields=["name", "template_name", "status", "language_code"],
            order_by="template_name",
        ),
        "segments": frappe.get_all(
            "WA Segment", filters={"enabled": 1}, fields=["name", "title"], order_by="title"
        ),
        "recipient_lists": frappe.get_all(
            "WhatsApp Recipient List", fields=["name", "list_name"], order_by="list_name"
        ),
        "accounts": frappe.get_all(
            "WhatsApp Account", fields=["name", "account_name"], order_by="account_name"
        ),
    }


@frappe.whitelist()
def create_campaign(payload):
    """Create a Bulk WhatsApp Message (campaign) in Draft or Scheduled state."""
    _guard_manager()
    if isinstance(payload, str):
        payload = json.loads(payload)

    doc = frappe.new_doc("Bulk WhatsApp Message")
    doc.title = payload.get("title")
    doc.whatsapp_account = payload.get("whatsapp_account")
    doc.use_template = 1 if payload.get("template") else 0
    doc.template = payload.get("template")

    # Template body parameters ({{1}}, {{2}} …) — same values for every recipient.
    tvars = payload.get("template_variables")
    if tvars:
        if isinstance(tvars, (dict, list)):
            tvars = json.dumps(tvars)
        doc.variable_type = "Common"
        doc.template_variables = tvars

    seg = payload.get("wd_segment")
    rlist = payload.get("recipient_list")
    if seg:
        doc.wd_segment = seg
        doc.recipient_type = "Recipient List"
    elif rlist:
        doc.recipient_type = "Recipient List"
        doc.recipient_list = rlist
    else:
        doc.recipient_type = "Recipient List"

    doc.wd_respect_opt_out = 1 if payload.get("wd_respect_opt_out", True) else 0
    doc.wd_throttle_per_min = int(payload.get("wd_throttle_per_min") or 0)

    sched = payload.get("scheduled_time")
    if sched:
        doc.scheduled_time = sched
        doc.status = "Scheduled"
    else:
        doc.status = "Draft"

    doc.insert()
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def pause_campaign(name: str):
    _guard_manager()
    frappe.get_doc("Bulk WhatsApp Message", name).wd_pause()
    return {"status": "Paused"}


@frappe.whitelist()
def resume_campaign(name: str):
    _guard_manager()
    frappe.get_doc("Bulk WhatsApp Message", name).wd_resume()
    return {"status": "Queued"}


@frappe.whitelist()
def cancel_campaign(name: str):
    _guard_manager()
    frappe.get_doc("Bulk WhatsApp Message", name).wd_cancel()
    return {"status": "Cancelled"}


@frappe.whitelist()
def list_segments():
    return frappe.get_all("WA Segment", filters={"enabled": 1},
                          fields=["name", "title", "source_doctype"], order_by="title asc")


@frappe.whitelist()
def preview_segment(segment: str):
    _guard_manager()
    return {"count": len(segments.resolve(segment))}


@frappe.whitelist()
def build_recipient_list(segment: str, list_name: str | None = None):
    _guard_manager()
    return segments.build_recipient_list(segment, list_name)
