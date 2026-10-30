"""Meta webhook signature verification (X-Hub-Signature-256).

Meta signs the raw request body with HMAC-SHA256 keyed by the app secret. We verify against
the WhatsApp Account's `wd_app_secret`. Fail closed: no secret / no signature / mismatch => reject.
"""

from __future__ import annotations

import hashlib
import hmac

import frappe


def _secrets() -> list[str]:
    """All configured app secrets (one per WhatsApp Account). We accept a signature that
    matches any configured account, since the webhook URL is shared across numbers."""
    secrets: list[str] = []
    for name in frappe.get_all("WhatsApp Account", pluck="name"):
        try:
            s = frappe.get_doc("WhatsApp Account", name).get_password(
                "wd_app_secret", raise_exception=False
            )
            if s:
                secrets.append(s)
        except Exception:
            continue
    return secrets


def verify(raw_body: bytes, header: str | None) -> bool:
    """Return True iff `header` is a valid signature of `raw_body` for some account secret."""
    if not header or not header.startswith("sha256="):
        return False
    provided = header.split("=", 1)[1].strip()
    for secret in _secrets():
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, provided):
            return True
    return False
