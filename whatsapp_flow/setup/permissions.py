"""RBAC: Custom DocPerms for WA Admin / WA Manager / WA Agent (#59).

Idempotent. Grants role access across the three apps' DocTypes + Issue using Frappe's
permission API so these travel as Custom DocPerms (and can be exported as fixtures).

  WA Admin   — full (read/write/create/delete) on all WhatsApp + conversation DocTypes
  WA Manager — read/write/create (no delete) on the same
  WA Agent   — read/write on conversations & messages; read-only on templates & flows
"""

from __future__ import annotations

import frappe
from frappe.permissions import add_permission, update_permission_property

FULL = {"read": 1, "write": 1, "create": 1, "delete": 1}
RWC = {"read": 1, "write": 1, "create": 1, "delete": 0}
RW = {"read": 1, "write": 1, "create": 0, "delete": 0}
RO = {"read": 1, "write": 0, "create": 0, "delete": 0}

CONVERSATION_DTS = [
    "WhatsApp Message",
    "WhatsApp Contact",
    "Issue",
    "WhatsApp Agent Transfer",
]
CONTENT_DTS = [
    "WhatsApp Templates",
    "WhatsApp Chatbot Flow",
]

# role -> {doctype: rights}
MATRIX: dict[str, dict[str, dict]] = {
    "WA Admin": {dt: FULL for dt in CONVERSATION_DTS + CONTENT_DTS + ["User Group"]},
    "WA Manager": {dt: RWC for dt in CONVERSATION_DTS + CONTENT_DTS + ["User Group"]},
    "WA Agent": {
        **{dt: RW for dt in CONVERSATION_DTS},
        **{dt: RO for dt in CONTENT_DTS},
    },
}


def create() -> None:
    for role, doctypes in MATRIX.items():
        if not frappe.db.exists("Role", role):
            continue
        for doctype, rights in doctypes.items():
            if not frappe.db.exists("DocType", doctype):
                continue
            # Ensure a permission row exists at permlevel 0, then set each right.
            try:
                add_permission(doctype, role, 0)
            except Exception:
                pass
            for ptype, value in rights.items():
                try:
                    update_permission_property(doctype, role, 0, ptype, value, validate=False)
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(), f"whatsapp_flow: docperm {role}/{doctype}/{ptype}"
                    )
