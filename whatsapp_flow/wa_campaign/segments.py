"""WA Segment resolution → native WhatsApp Recipient List (#46)."""

from __future__ import annotations

import json

import frappe


def resolve(segment_name: str, respect_opt_out: bool = True, limit: int = 0) -> list[dict]:
    seg = frappe.get_doc("WA Segment", segment_name)
    filters = {}
    if seg.filters:
        try:
            filters = json.loads(seg.filters)
        except Exception:
            filters = {}
    mobile_field = seg.mobile_field or "mobile_no"
    fields = [mobile_field]
    if seg.name_field:
        fields.append(seg.name_field)

    rows = frappe.get_all(seg.source_doctype, filters=filters, fields=fields,
                          limit_page_length=limit or 0)
    out = []
    seen = set()
    for r in rows:
        num = r.get(mobile_field)
        if not num or num in seen:
            continue
        if respect_opt_out and frappe.db.get_value(
            "WhatsApp Contact", {"mobile_no": num}, "wd_marketing_opt_out"
        ):
            continue
        seen.add(num)
        out.append({"mobile_number": num,
                    "recipient_name": r.get(seg.name_field) if seg.name_field else None})
    return out


def build_recipient_list(segment_name: str, list_name: str | None = None) -> dict:
    seg = frappe.get_doc("WA Segment", segment_name)
    recips = resolve(segment_name)
    name = list_name or f"Segment: {seg.title}"

    existing = frappe.db.get_value("WhatsApp Recipient List", {"list_name": name})
    if existing:
        rl = frappe.get_doc("WhatsApp Recipient List", existing)
        rl.set("recipients", [])
    else:
        rl = frappe.new_doc("WhatsApp Recipient List")
        rl.list_name = name
    for r in recips:
        rl.append("recipients", {"mobile_number": r["mobile_number"],
                                 "recipient_name": r.get("recipient_name")})
    rl.flags.ignore_permissions = True
    rl.save()
    return {"recipient_list": rl.name, "count": len(recips)}
