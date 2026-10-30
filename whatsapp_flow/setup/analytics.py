"""Phase 4 analytics (#54-#57), native-first.

Creates native Number Cards, Dashboard Charts, a Query Report and a Workspace that target the
WhatsApp/Issue data. Idempotent; guarded so a failure never blocks install/migrate.
"""

from __future__ import annotations

import json

import frappe

WA_ISSUE_FILTER = [["Issue", "wd_whatsapp_contact", "is", "set"]]


def ensure_analytics() -> None:
    try:
        _number_cards()
        _charts()
        _agent_report()
        _audit_report()
        _workspace()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: ensure_analytics failed")


def _nc(label, doctype, function, filters, aggregate_field=None):
    # Number Card autonames from `label`, so the label IS the record name.
    if frappe.db.exists("Number Card", label):
        return
    doc = frappe.new_doc("Number Card")
    doc.label = label
    doc.type = "Document Type"
    doc.document_type = doctype
    doc.function = function
    if aggregate_field:
        doc.aggregate_function_based_on = aggregate_field
    doc.filters_json = json.dumps(filters)
    doc.is_public = 1
    doc.show_percentage_stats = 1
    doc.flags.ignore_permissions = True
    doc.insert()


def _number_cards() -> None:
    _nc("WA Open Conversations", "Issue", "Count",
        {"wd_whatsapp_contact": ["is", "set"], "status": "Open"})
    _nc("WA Resolved Issues", "Issue", "Count",
        {"wd_whatsapp_contact": ["is", "set"], "status": ["in", ["Resolved", "Closed"]]})
    _nc("WA Unread", "WhatsApp Contact", "Sum", {}, aggregate_field="wd_unread_count")
    _nc("WA Contacts", "WhatsApp Contact", "Count", {})


def _chart(name, label, doctype, chart_type, filters, **kw):
    if frappe.db.exists("Dashboard Chart", name):
        return
    doc = frappe.new_doc("Dashboard Chart")
    doc.chart_name = name
    doc.label = label
    doc.chart_type = chart_type
    doc.document_type = doctype
    doc.is_public = 1
    doc.filters_json = json.dumps(filters)
    for k, v in kw.items():
        setattr(doc, k, v)
    doc.flags.ignore_permissions = True
    doc.insert()


def _charts() -> None:
    # conversations opened per day (last 30 days)
    _chart("WA Conversations Over Time", "WhatsApp Conversations", "Issue", "Count",
           {"wd_whatsapp_contact": ["is", "set"]},
           based_on="creation", time_interval="Daily", timespan="Last Month", type="Line")
    # conversations grouped by status
    _chart("WA Conversations by Status", "Conversations by Status", "Issue", "Group By",
           {"wd_whatsapp_contact": ["is", "set"]},
           group_by_type="Count", group_by_based_on="status", type="Donut")


def _agent_report() -> None:
    name = "WA Agent Performance"
    if frappe.db.exists("Report", name):
        return
    doc = frappe.new_doc("Report")
    doc.report_name = name
    doc.ref_doctype = "Issue"
    doc.report_type = "Query Report"
    doc.is_standard = "No"
    doc.query = """
        SELECT td.allocated_to AS "Agent:Link/User:200",
               COUNT(DISTINCT i.name) AS "Conversations:Int:120",
               SUM(CASE WHEN i.status IN ('Resolved','Closed') THEN 1 ELSE 0 END) AS "Resolved:Int:100",
               ROUND(AVG(i.first_response_time)/60, 1) AS "Avg First Response (min):Float:160"
        FROM `tabToDo` td
        JOIN `tabIssue` i ON i.name = td.reference_name AND td.reference_type = 'Issue'
        WHERE i.wd_whatsapp_contact IS NOT NULL AND i.wd_whatsapp_contact != ''
        GROUP BY td.allocated_to
        ORDER BY Conversations DESC
    """
    doc.flags.ignore_permissions = True
    doc.insert()


def _audit_report() -> None:
    """Audit trail (#61) over native Version rows for WhatsApp Flow doctypes."""
    name = "WA Audit Trail"
    if frappe.db.exists("Report", name):
        return
    doc = frappe.new_doc("Report")
    doc.report_name = name
    doc.ref_doctype = "Version"
    doc.report_type = "Query Report"
    doc.is_standard = "No"
    doc.query = """
        SELECT v.creation AS "When:Datetime:180",
               v.ref_doctype AS "DocType:Data:150",
               v.docname AS "Document:Data:200",
               v.owner AS "By:Link/User:180"
        FROM `tabVersion` v
        WHERE v.ref_doctype IN ('WhatsApp Message','WhatsApp Contact','Issue',
                                'WhatsApp Templates','WA Canned Response','WA Custom Action',
                                'WA Segment','Bulk WhatsApp Message','WhatsApp Chatbot Flow')
        ORDER BY v.creation DESC
    """
    doc.flags.ignore_permissions = True
    doc.insert()


def _workspace() -> None:
    name = "WhatsApp Flow"
    if frappe.db.exists("Workspace", name):
        return
    doc = frappe.new_doc("Workspace")
    doc.name = name
    doc.title = name
    doc.label = name
    doc.public = 1
    doc.module = "WhatsApp Flow"
    doc.icon = "message"
    doc.append("links", {"type": "Card Break", "label": "WhatsApp Flow"})
    for dt in ("WhatsApp Contact", "Issue", "WA Canned Response", "WA Custom Action",
               "WA Segment", "Bulk WhatsApp Message", "WhatsApp Chatbot Flow"):
        doc.append("links", {"type": "Link", "link_type": "DocType", "label": dt, "link_to": dt})
    doc.append("links", {"type": "Link", "link_type": "Report", "label": "WA Agent Performance",
                         "link_to": "WA Agent Performance", "is_query_report": 1})
    for card in ("WA Open Conversations", "WA Resolved Issues", "WA Unread", "WA Contacts"):
        doc.append("number_cards", {"number_card_name": card, "label": card})
    for chart in ("WA Conversations Over Time", "WA Conversations by Status"):
        doc.append("charts", {"chart_name": chart, "label": chart})
    doc.content = json.dumps([
        {"type": "header", "data": {"text": "WhatsApp Flow", "level": 4}},
        {"type": "number_card", "data": {"number_card_name": "WA Open Conversations", "col": 3}},
        {"type": "number_card", "data": {"number_card_name": "WA Resolved Issues", "col": 3}},
        {"type": "number_card", "data": {"number_card_name": "WA Unread", "col": 3}},
        {"type": "number_card", "data": {"number_card_name": "WA Contacts", "col": 3}},
        {"type": "chart", "data": {"chart_name": "WA Conversations Over Time", "col": 8}},
        {"type": "chart", "data": {"chart_name": "WA Conversations by Status", "col": 4}},
    ])
    doc.flags.ignore_permissions = True
    doc.insert()
