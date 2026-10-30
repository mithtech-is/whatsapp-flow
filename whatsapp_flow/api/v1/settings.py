"""Settings API for the SPA: whatsapp_flow operations (retention, voice, Flows key) + teams/agents.

WhatsApp *account* connection (phone id, token, webhook) is handled by the upstream WhatsApp
apps in the Frappe Desk — this app does not duplicate it.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from whatsapp_flow.endpoints.chat import _is_manager


def _guard_manager():
    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))


@frappe.whitelist()
def get_settings():
    _guard_manager()
    s = frappe.get_single("WhatsApp Settings")
    settings = {
        "wd_phone_masking": s.wd_phone_masking,
        "wd_retention_days": s.wd_retention_days,
        "wd_auto_close_days": s.wd_auto_close_days,
        "wd_voice_enabled": s.wd_voice_enabled,
        "wd_patch_health": s.wd_patch_health,
        "has_flows_key": bool(s.get("wd_flows_private_key")),
    }
    return {"settings": settings}


@frappe.whitelist()
def save_settings(payload):
    _guard_manager()
    if isinstance(payload, str):
        payload = json.loads(payload)
    s = frappe.get_single("WhatsApp Settings")
    for f in ("wd_phone_masking", "wd_retention_days", "wd_auto_close_days", "wd_voice_enabled"):
        if payload.get(f) is not None:
            s.set(f, payload[f])
    # Flows private key (Password): only overwrite when a non-empty value is supplied.
    if payload.get("wd_flows_private_key"):
        s.wd_flows_private_key = payload["wd_flows_private_key"]
    s.save()
    frappe.db.commit()
    return {"ok": True, "has_flows_key": bool(s.get("wd_flows_private_key"))}


@frappe.whitelist()
def teams_and_agents():
    """User Groups (teams) with their members + a flat agent roster."""
    from whatsapp_flow.wa_desk import teams as teams_mod

    team_rows = []
    for g in frappe.get_all("User Group", pluck="name"):
        mem = teams_mod.members(g)
        team_rows.append({"team": g, "members": len(mem), "online": len(teams_mod.online_agents(g))})

    agent_rows = frappe.get_all(
        "User",
        filters={"enabled": 1, "user_type": "System User"},
        fields=["name", "full_name", "wd_wa_availability"],
        order_by="full_name",
        limit=200,
    )
    return {"teams": team_rows, "agents": agent_rows}
