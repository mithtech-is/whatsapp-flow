"""Throttled per-recipient sender (scheduled by the Bulk override)."""

from __future__ import annotations

import frappe


def send_recipient(bulk_name: str, recipient: dict) -> None:
    try:
        doc = frappe.get_doc("Bulk WhatsApp Message", bulk_name)
        doc.create_single_message(recipient)  # our override: pause/cancel/opt-out guards
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: throttled bulk send failed")
