"""Health checks surfaced on the WhatsApp Settings health page (§2.2 guard).

Reports (a) runtime patch status and (b) whether our endpoint overrides are active, so an
operator can see at a glance if any security override silently fell back to upstream.
"""

from __future__ import annotations

import frappe

from whatsapp_flow.compat import patches

# Endpoint overrides we expect to be active (plan §2.1).
EXPECTED_OVERRIDES = {
    "frappe_whatsapp.utils.webhook.webhook": "whatsapp_flow.endpoints.webhook.webhook",
    "frappe_whatsapp.frappe_whatsapp.api.flow_endpoint.handle_flow_request": "whatsapp_flow.wa_flows.endpoint.handle_flow_request",
    "whatsapp_chat.api.message.get_all": "whatsapp_flow.endpoints.chat.get_all",
    "whatsapp_chat.api.message.send": "whatsapp_flow.endpoints.chat.send",
    "whatsapp_chat.api.message.mark_as_read": "whatsapp_flow.endpoints.chat.mark_as_read",
    "whatsapp_chat.api.message.set_typing": "whatsapp_flow.endpoints.chat.set_typing",
    "whatsapp_chat.api.contacts.get": "whatsapp_flow.endpoints.chat.contacts_get",
    "whatsapp_chat.api.contacts.create": "whatsapp_flow.endpoints.chat.contacts_create",
    "whatsapp_chat.api.config.settings": "whatsapp_flow.endpoints.chat.config_settings",
}


def patch_status() -> dict[str, dict]:
    return patches.get_status()


def override_status() -> dict[str, dict]:
    active = frappe.get_hooks("override_whitelisted_methods") or {}
    out: dict[str, dict] = {}
    for original, expected in EXPECTED_OVERRIDES.items():
        got = active.get(original)
        got = got[-1] if isinstance(got, list) and got else got
        out[original] = {"ok": got == expected, "resolved_to": got}
    return out


def _summary() -> dict:
    patches_ = patch_status()
    overrides_ = override_status()
    healthy = all(p.get("status") == "applied" for p in patches_.values()) and all(
        o.get("ok") for o in overrides_.values()
    )
    return {"healthy": healthy, "patches": patches_, "overrides": overrides_}


@frappe.whitelist()
def summary() -> dict:
    """Consumed by the SPA / health page. System Manager only (whitelist + perms)."""
    frappe.only_for("System Manager")
    return _summary()


def refresh_settings_field() -> None:
    """Write a human-readable health snapshot into WhatsApp Settings.wd_patch_health."""
    try:
        s = _summary()
        lines = ["HEALTHY" if s["healthy"] else "DEGRADED", ""]
        for name, info in s["patches"].items():
            lines.append(f"patch {name}: {info.get('status')} {info.get('detail', '')}".strip())
        for original, info in s["overrides"].items():
            lines.append(f"override {original}: {'ok' if info.get('ok') else 'MISSING'}")
        frappe.db.set_single_value("WhatsApp Settings", "wd_patch_health", "\n".join(lines))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: health refresh failed")
