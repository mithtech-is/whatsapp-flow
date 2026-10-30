"""ERPNext Item -> Meta product catalog sync (#69).

Builds a Meta product feed from ERPNext Items and pushes it to the account's catalog via the
Items Batch API. The push is guarded — it no-ops unless a catalog id and token are configured.
"""

from __future__ import annotations

import frappe
from frappe import _

from whatsapp_flow.wa_core import meta_client


def build_item_feed(filters: dict | None = None, limit: int = 0) -> list[dict]:
    """Map Items to Meta product dicts. Only items with a price are included."""
    items = frappe.get_all(
        "Item",
        filters=filters or {"disabled": 0},
        fields=["name", "item_code", "item_name", "description", "standard_rate", "image"],
        limit_page_length=limit or 0,
    )
    feed = []
    for it in items:
        price = it.standard_rate or 0
        if not price:
            continue
        feed.append({
            "retailer_id": it.item_code or it.name,
            "name": it.item_name or it.item_code,
            "description": frappe.utils.strip_html(it.description or it.item_name or "")[:9000],
            "price": int(round(price * 100)),  # minor units
            "currency": frappe.defaults.get_global_default("currency") or "USD",
            "availability": "in stock",
            "image_url": (frappe.utils.get_url() + it.image) if it.image else None,
        })
    return feed


@frappe.whitelist()
def sync(account: str | None = None, filters: dict | None = None):
    from whatsapp_flow.endpoints.chat import _is_manager

    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))

    acc = meta_client.get_account(account)
    if not acc:
        frappe.throw(_("No WhatsApp Account."))
    catalog_id = acc.get("wd_catalog_id")
    feed = build_item_feed(filters)
    if not catalog_id:
        return {"synced": 0, "built": len(feed), "note": "No wd_catalog_id configured on the account."}

    requests = [{"method": "UPDATE", "retailer_id": p["retailer_id"], "data": p} for p in feed]
    # Meta Items Batch API: POST /{catalog_id}/items_batch
    meta_client.post(f"{catalog_id}/items_batch", {"item_type": "PRODUCT_ITEM", "requests": requests},
                     account=acc.name)
    return {"synced": len(requests), "built": len(feed)}
