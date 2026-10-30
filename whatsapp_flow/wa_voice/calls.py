"""WhatsApp voice calls (#1-#12), native-first on Frappe Call Log.

Inbound/outbound calls are logged as Call Log rows (medium="WhatsApp"). Inbound calls are
routed to an available agent via the contact's team (ring rotation reuses teams.pick_agent).
Outbound calls require recorded consent (WhatsApp Contact.wd_call_consent). The actual Meta
Calling API round-trip (SDP offer/answer) lives in api/v1/voice.py and is feature-flagged.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

MEDIUM = "WhatsApp"


def voice_enabled() -> bool:
    try:
        return bool(frappe.db.get_single_value("WhatsApp Settings", "wd_voice_enabled"))
    except Exception:
        return False


def can_call(number: str) -> bool:
    """Outbound calling requires recorded consent (#11 call permission)."""
    name = frappe.db.get_value("WhatsApp Contact", {"mobile_no": number})
    return bool(name and frappe.db.get_value("WhatsApp Contact", name, "wd_call_consent"))


def log_call(meta_call_id, number, direction, status="Ringing", account=None, duration=None):
    """Create or update a Call Log for a WhatsApp call. Returns the Call Log name."""
    existing = frappe.db.get_value("Call Log", {"wd_meta_call_id": meta_call_id}) if meta_call_id else None
    contact = frappe.db.get_value("WhatsApp Contact", {"mobile_no": number})
    issue = frappe.db.get_value("WhatsApp Contact", contact, "wd_open_issue") if contact else None

    if existing:
        doc = frappe.get_doc("Call Log", existing)
    else:
        doc = frappe.new_doc("Call Log")
        doc.id = meta_call_id or frappe.generate_hash(length=12)
        doc.medium = MEDIUM
        doc.type = "Incoming" if direction == "inbound" else "Outgoing"
        if direction == "inbound":
            doc.set("from", number)
        else:
            doc.to = number
        doc.wd_meta_call_id = meta_call_id
        doc.wd_whatsapp_account = account
        doc.wd_contact = contact
        doc.wd_issue = issue
    doc.status = status
    if duration is not None:
        doc.duration = duration
    if status in ("Completed", "Failed", "Busy", "No Answer", "Cancelled"):
        doc.end_time = now_datetime()
    elif not doc.get("start_time"):
        doc.start_time = now_datetime()
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.save()
    return doc.name


def route_inbound(call_name, number):
    """Ring rotation: assign an available agent on the contact's team to the inbound call."""
    from whatsapp_flow.wa_desk import teams

    contact = frappe.db.get_value("WhatsApp Contact", {"mobile_no": number})
    team = frappe.db.get_value("WhatsApp Contact", contact, "wd_team") if contact else None
    agent = teams.pick_agent(team) if team else None
    if agent:
        frappe.db.set_value("Call Log", call_name, "call_received_by", agent, update_modified=False)
    return agent


# Map Meta calling-event statuses to Call Log statuses.
_STATUS = {
    "ringing": "Ringing", "initiated": "Ringing", "connect": "In Progress", "accepted": "In Progress",
    "in_progress": "In Progress", "completed": "Completed", "terminated": "Completed",
    "failed": "Failed", "rejected": "No Answer", "busy": "Busy", "missed": "No Answer",
}


def on_calls_webhook(value: dict) -> None:
    """Handle the `calls` array in a Meta webhook change value."""
    try:
        account = None
        meta = value.get("metadata", {})
        phone_id = meta.get("phone_number_id")
        if phone_id:
            account = frappe.db.get_value("WhatsApp Account", {"phone_id": phone_id})
        for call in value.get("calls", []):
            call_id = call.get("id")
            status = _STATUS.get((call.get("status") or call.get("event") or "").lower(), "Ringing")
            direction = "inbound" if call.get("direction", "inbound") == "inbound" else "outbound"
            number = call.get("from") or call.get("to")
            name = log_call(call_id, number, direction, status=status, account=account,
                            duration=call.get("duration"))
            if direction == "inbound" and status == "Ringing":
                route_inbound(name, number)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: on_calls_webhook failed")
