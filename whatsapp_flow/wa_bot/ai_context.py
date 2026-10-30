"""External API AI context (#14) + AI tools helpers (#16).

`external_api_context` is called from the patched AIResponder.build_context: it fetches text
from any enabled WhatsApp AI Context of type "External API" (SSRF-guarded) and returns it to
append to the LLM context.
"""

from __future__ import annotations

import json

import frappe


def external_api_context(phone_number: str | None = None) -> str:
    rows = frappe.get_all(
        "WhatsApp AI Context",
        filters={"enabled": 1, "context_type": "External API"},
        fields=["name", "title", "wd_api_url", "wd_api_method", "wd_api_headers", "wd_response_path"],
    )
    parts = []
    for row in rows:
        val = _fetch(row, phone_number)
        if val:
            parts.append(f"{row.title or row.name}:\n{val}")
    return "\n\n".join(parts)


def _fetch(row, phone_number):
    from frappe.integrations.utils import make_get_request, make_post_request

    from whatsapp_flow.wa_core import ssrf

    url = (row.get("wd_api_url") or "").replace("{{ number }}", phone_number or "").replace(
        "{{number}}", phone_number or ""
    )
    if not url:
        return None
    try:
        ssrf.validate(url)
        headers = {}
        if row.get("wd_api_headers"):
            try:
                headers = json.loads(row.wd_api_headers)
            except Exception:
                headers = {}
        if (row.get("wd_api_method") or "GET").upper() == "POST":
            resp = make_post_request(url, headers=headers, data=json.dumps({"number": phone_number}))
        else:
            resp = make_get_request(url, headers=headers)
        path = row.get("wd_response_path")
        if path and isinstance(resp, dict):
            for key in path.split("."):
                resp = resp.get(key) if isinstance(resp, dict) else None
        return resp if isinstance(resp, str) else json.dumps(resp)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: external api context fetch failed")
        return None


def available_tools() -> list[dict]:
    """ERP functions the LLM may call (#16), from enabled WA AI Tool rows."""
    if not frappe.db.exists("DocType", "WA AI Tool"):
        return []
    tools = []
    for t in frappe.get_all("WA AI Tool", filters={"enabled": 1},
                            fields=["name", "tool_name", "description", "parameters_schema"]):
        schema = {}
        if t.parameters_schema:
            try:
                schema = json.loads(t.parameters_schema)
            except Exception:
                schema = {}
        tools.append({"name": t.tool_name, "description": t.description, "parameters": schema})
    return tools
