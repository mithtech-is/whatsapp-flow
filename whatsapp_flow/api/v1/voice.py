"""Voice API for the SPA (#1-#12). Consent + call list are always available; the Meta Calling
round-trip (place/accept/terminate) is feature-flagged behind WA Settings.wd_voice_enabled."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from whatsapp_flow.endpoints.chat import _can_access_contact, _is_manager
from whatsapp_flow.wa_core import meta_client
from whatsapp_flow.wa_voice import calls


def _fmt_dur(seconds) -> str:
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


@frappe.whitelist()
def set_consent(contact: str, granted: int = 1, source: str = "agent"):
    if not _can_access_contact(contact):
        raise frappe.PermissionError(_("Not allowed."))
    frappe.db.set_value("WhatsApp Contact", contact, {
        "wd_call_consent": 1 if int(granted) else 0,
        "wd_call_consent_on": now_datetime(),
        "wd_call_consent_source": source,
    }, update_modified=False)
    return {"contact": contact, "consent": bool(int(granted))}


@frappe.whitelist()
def list_calls(contact: str | None = None, limit: int = 50):
    filters = {"medium": "WhatsApp"}
    if contact:
        if not _can_access_contact(contact):
            raise frappe.PermissionError(_("Not allowed."))
        filters["wd_contact"] = contact
    return frappe.get_all("Call Log", filters=filters,
                          fields=["name", "type", "status", "`from`", "`to`", "duration",
                                  "start_time", "recording_url", "call_received_by"],
                          order_by="creation desc", limit_page_length=frappe.utils.cint(limit) or 50)


@frappe.whitelist()
def calls_overview(limit: int = 100):
    """Stats + an enriched call feed + IVR (Graph) flows for the SPA Calls screen."""
    rows = frappe.get_all(
        "Call Log",
        filters={"medium": "WhatsApp"},
        fields=["name", "type", "status", "`from`", "`to`", "duration", "start_time",
                "recording_url", "call_received_by", "wd_contact", "wd_ivr_flow", "creation"],
        order_by="creation desc",
        limit_page_length=cint(limit) or 100,
    )

    cmap = {}
    cids = list({r.wd_contact for r in rows if r.wd_contact})
    if cids:
        for c in frappe.get_all("WhatsApp Contact", filters={"name": ["in", cids]},
                                fields=["name", "contact_name", "wd_call_consent"]):
            cmap[c.name] = c

    feed = []
    for r in rows:
        c = cmap.get(r.wd_contact)
        number = r.get("from") if r.type == "Incoming" else r.get("to")
        feed.append({
            "name": r.name, "type": r.type, "status": r.status, "number": number,
            "duration": r.duration, "duration_fmt": _fmt_dur(r.duration),
            "start_time": r.start_time, "recording_url": r.recording_url,
            "agent": r.call_received_by, "contact": r.wd_contact,
            "contact_name": (c.contact_name if c else None),
            "consent": bool(c.wd_call_consent) if c else None,
            "ivr_flow": r.wd_ivr_flow, "creation": r.creation,
        })

    total = len(rows)
    inbound = sum(1 for r in rows if r.type == "Incoming")
    missed = sum(1 for r in rows if r.status in ("No Answer", "Busy", "Failed"))
    completed = [r for r in rows if r.status == "Completed" and r.duration]
    avg = round(sum(r.duration for r in completed) / len(completed)) if completed else 0

    flows = frappe.get_all(
        "WhatsApp Chatbot Flow", filters={"wd_mode": "Graph"},
        fields=["name", "flow_name", "wd_published", "enabled"], order_by="modified desc",
    )

    return {
        "voice_enabled": calls.voice_enabled(),
        "cards": [
            {"key": "total", "label": "Total calls", "value": total, "accent": "#16a34a"},
            {"key": "inbound", "label": "Inbound", "value": inbound, "accent": "#2563eb"},
            {"key": "outbound", "label": "Outbound", "value": total - inbound, "accent": "#7c3aed"},
            {"key": "missed", "label": "Missed / failed", "value": missed, "accent": "#dc2626"},
            {"key": "avg", "label": "Avg duration", "value": _fmt_dur(avg), "accent": "#0891b2"},
            {"key": "consent", "label": "Consented contacts", "value": frappe.db.count("WhatsApp Contact", {"wd_call_consent": 1}), "accent": "#db2777"},
        ],
        "calls": feed,
        "ivr_flows": flows,
    }


def _require_voice():
    if not calls.voice_enabled():
        frappe.throw(_("Voice is not enabled (WhatsApp Settings → Enable Voice)."))


@frappe.whitelist()
def place_call(contact: str, sdp: str | None = None):
    """Outbound call via Meta Calling API. Requires consent + voice enabled."""
    _require_voice()
    if not _can_access_contact(contact):
        raise frappe.PermissionError(_("Not allowed."))
    number = frappe.db.get_value("WhatsApp Contact", contact, "mobile_no")
    if not calls.can_call(number):
        frappe.throw(_("No recorded call consent for this contact."))
    acc = meta_client.get_account()
    payload = {"messaging_product": "whatsapp", "to": number, "action": "connect"}
    if sdp:
        payload["session"] = {"sdp_type": "offer", "sdp": sdp}
    resp = meta_client.post(f"{acc.phone_id}/calls", payload)
    call_id = (resp or {}).get("calls", [{}])[0].get("id") if isinstance(resp, dict) else None
    calls.log_call(call_id, number, "outbound", status="Ringing", account=acc.name)
    return {"call_id": call_id, "response": resp}


@frappe.whitelist()
def terminate_call(call_name: str):
    _require_voice()
    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))
    cl = frappe.get_doc("Call Log", call_name)
    acc = meta_client.get_account(cl.get("wd_whatsapp_account"))
    meta_client.post(f"{acc.phone_id}/calls",
                     {"messaging_product": "whatsapp", "call_id": cl.wd_meta_call_id, "action": "terminate"})
    frappe.db.set_value("Call Log", call_name, "status", "Completed", update_modified=False)
    return {"ok": True}
