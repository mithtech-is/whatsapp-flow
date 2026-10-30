"""WhatsApp Templates API for the SPA.

Thin wrapper over the upstream `WhatsApp Templates` DocType. Creating/saving a
template doc triggers the upstream controller to submit it to Meta; the approval
`status` is then updated by Meta via the webhook, so `list_templates` reflects
live state.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

from whatsapp_flow.endpoints.chat import _is_manager

# WhatsApp body/header placeholders: {{1}}, {{2}} or named {{ customer_name }}.
VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

LIST_FIELDS = [
    "name",
    "template_name",
    "actual_name",
    "status",
    "category",
    "language_code",
    "header_type",
    "whatsapp_account",
    "modified",
]


def _guard_manager():
    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))


@frappe.whitelist()
def list_templates():
    rows = frappe.get_all(
        "WhatsApp Templates", fields=LIST_FIELDS, order_by="modified desc"
    )
    return rows


@frappe.whitelist()
def get_template(name: str):
    doc = frappe.get_doc("WhatsApp Templates", name)
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "actual_name": doc.actual_name,
        "status": doc.status,
        "category": doc.category,
        "language_code": doc.language_code,
        "language": doc.language,
        "header_type": doc.header_type,
        "header": doc.header,
        "template": doc.template,
        "footer": doc.footer,
        "sample_values": doc.sample_values,
        "whatsapp_account": doc.whatsapp_account,
        "buttons": [
            {"button_type": b.get("button_type"), "button_text": b.get("button_text")}
            for b in (doc.buttons or [])
        ],
    }


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


@frappe.whitelist()
def template_detail(name: str):
    """Body text + the ordered list of body placeholders, for the param-fill UI."""
    doc = frappe.get_doc("WhatsApp Templates", name)
    body = _strip_html(doc.template or "")
    variables = []
    for token in VAR_RE.findall(body):
        if token not in variables:
            variables.append(token)
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "body": body,
        "header": doc.header if doc.header_type == "TEXT" else "",
        "header_type": doc.header_type,
        "footer": doc.footer,
        "language_code": doc.language_code,
        "variables": variables,
    }


@frappe.whitelist()
def accounts():
    """WhatsApp Accounts and the known language codes, for template form selects."""
    return {
        "accounts": frappe.get_all(
            "WhatsApp Account", fields=["name", "account_name", "status"], order_by="account_name"
        ),
        "categories": ["TRANSACTIONAL", "MARKETING", "OTP", "UTILITY", "AUTHENTICATION"],
        "header_types": ["", "TEXT", "DOCUMENT", "IMAGE", "VIDEO"],
    }


@frappe.whitelist()
def save_template(payload):
    """Create a new WhatsApp Templates doc (submits to Meta via upstream controller)."""
    _guard_manager()
    if isinstance(payload, str):
        payload = json.loads(payload)

    name = payload.get("name")
    if name and frappe.db.exists("WhatsApp Templates", name):
        doc = frappe.get_doc("WhatsApp Templates", name)
    else:
        doc = frappe.new_doc("WhatsApp Templates")

    for f in (
        "template_name",
        "category",
        "language_code",
        "header_type",
        "header",
        "template",
        "footer",
        "sample_values",
        "whatsapp_account",
    ):
        if payload.get(f) is not None:
            doc.set(f, payload[f])

    if not doc.get("language") and payload.get("language_code"):
        # Language link defaults to the code when a matching Language row exists.
        if frappe.db.exists("Language", payload["language_code"]):
            doc.language = payload["language_code"]

    doc.save()
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def delete_template(name: str):
    _guard_manager()
    frappe.delete_doc("WhatsApp Templates", name)
    frappe.db.commit()
    return {"deleted": name}
