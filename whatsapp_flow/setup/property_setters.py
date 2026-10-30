"""Property Setters (idempotent).

Appends Select options without forking the upstream DocTypes:
  * WhatsApp Templates.header_type   += VIDEO
  * WhatsApp AI Context.context_type += External API   (consumed in Phase 3)
Also enables track_changes on key DocTypes for the audit trail (#61).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# (doctype, fieldname, option_to_ensure)
SELECT_OPTIONS = [
    ("WhatsApp Templates", "header_type", "VIDEO"),
    ("WhatsApp AI Context", "context_type", "External API"),
    ("Bulk WhatsApp Message", "status", "Paused"),
    ("Bulk WhatsApp Message", "status", "Cancelled"),
]

TRACK_CHANGES = ["WhatsApp Message", "Issue", "WhatsApp Contact", "WhatsApp Templates"]

# (doctype, fieldname, property, value, property_type)
FIELD_PROPERTIES = [
    # Graph-mode chatbot flows don't use the Steps table; the controller still enforces
    # steps for Steps mode in validate_steps(), so dropping reqd is safe.
    ("WhatsApp Chatbot Flow", "steps", "reqd", "0", "Check"),
]


# This app's module — stamped on every Property Setter so these customizations
# are owned by whatsapp_flow (exported with it, removed on uninstall) rather than
# attributed to the upstream apps' modules.
APP_MODULE = "WhatsApp Flow"


def _ps(*args, **kwargs):
    """make_property_setter + stamp the owning module to this app."""
    ps = make_property_setter(*args, **kwargs)
    try:
        if ps is not None:
            frappe.db.set_value("Property Setter", ps.name, "module", APP_MODULE, update_modified=False)
    except Exception:
        pass
    return ps


def create() -> None:
    for doctype, fieldname, option in SELECT_OPTIONS:
        _ensure_select_option(doctype, fieldname, option)
    for doctype, fieldname, prop, value, ptype in FIELD_PROPERTIES:
        if frappe.db.exists("DocType", doctype) and frappe.get_meta(doctype).get_field(fieldname):
            _ps(doctype, fieldname, prop, value, ptype, validate_fields_for_doctype=False)
    for doctype in TRACK_CHANGES:
        if frappe.db.exists("DocType", doctype):
            _ps(doctype, None, "track_changes", 1, "Check", for_doctype=True,
                validate_fields_for_doctype=False)


def _ensure_select_option(doctype: str, fieldname: str, option: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        return
    meta = frappe.get_meta(doctype)
    field = meta.get_field(fieldname)
    if not field or field.fieldtype != "Select":
        return
    options = [o for o in (field.options or "").split("\n")]
    if option in options:
        return
    options.append(option)
    _ps(
        doctype,
        fieldname,
        "options",
        "\n".join(options),
        "Text",
        validate_fields_for_doctype=False,
    )
