"""Thin Meta Graph API client, keyed on a WhatsApp Account's credentials.

Used by catalog sync, business profile and (later) calling/insights. All calls
go through frappe's integration request helpers so they're logged and testable.
"""

from __future__ import annotations

import json

import frappe
from frappe.integrations.utils import make_get_request, make_post_request

from whatsapp_flow.wa_core import ssrf


def get_account(account: str | None = None):
    if account:
        return frappe.get_doc("WhatsApp Account", account)
    from frappe_whatsapp.utils import get_whatsapp_account

    acc = get_whatsapp_account(account_type="outgoing")
    return frappe.get_doc("WhatsApp Account", acc.name) if acc else None


def _base(acc) -> str:
    return f"{acc.url}/{acc.version}"


def _headers(acc) -> dict:
    return {"Authorization": f"Bearer {acc.get_password('token')}", "Content-Type": "application/json"}


def get(path: str, account: str | None = None, params: dict | None = None):
    acc = get_account(account)
    url = f"{_base(acc)}/{path.lstrip('/')}"
    ssrf.validate(url)
    return make_get_request(url, headers=_headers(acc), params=params or {})


def post(path: str, data: dict, account: str | None = None):
    acc = get_account(account)
    url = f"{_base(acc)}/{path.lstrip('/')}"
    ssrf.validate(url)
    return make_post_request(url, headers=_headers(acc), data=json.dumps(data))
