"""Media-bridge client (Phase 6b) — feature-flagged.

Talks to an external FreeSWITCH/SIP media bridge (WA Settings.wd_media_bridge_url) for TTS
(Piper), hold, and recording. The bridge runs on a VPS, not Frappe Cloud. Every call no-ops
cleanly when no bridge URL is configured, so the rest of voice works without 6b.
"""

from __future__ import annotations

import json

import frappe
from frappe.integrations.utils import make_post_request

from whatsapp_flow.wa_core import ssrf


def _url() -> str | None:
    try:
        return frappe.db.get_single_value("WhatsApp Settings", "wd_media_bridge_url")
    except Exception:
        return None


def _post(action: str, payload: dict) -> dict:
    url = _url()
    if not url:
        return {"skipped": "no media bridge configured"}
    endpoint = url.rstrip("/") + "/" + action
    ssrf.validate(endpoint)
    return make_post_request(endpoint, data=json.dumps(payload),
                             headers={"Content-Type": "application/json"})


def say(call_id: str, text: str) -> dict:
    return _post("say", {"call_id": call_id, "text": text})


def gather(call_id: str, prompt: str, num_digits: int = 1) -> dict:
    return _post("gather", {"call_id": call_id, "prompt": prompt, "num_digits": num_digits})


def hold(call_id: str, on: bool = True) -> dict:
    return _post("hold", {"call_id": call_id, "on": on})


def record(call_id: str, on: bool = True) -> dict:
    return _post("record", {"call_id": call_id, "on": on})


def hangup(call_id: str) -> dict:
    return _post("hangup", {"call_id": call_id})
