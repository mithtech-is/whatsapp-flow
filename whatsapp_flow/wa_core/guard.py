"""Outbound send guard (§5.2).

Run from WhatsApp Message.before_insert (the override) for every Outgoing message, whatever
created it — agent, bot, Bulk, Notification or API. Three checks, then it stamps the
conversation/sender fields. Raising here (before the upstream before_insert that calls Meta)
blocks the send cleanly.

Checks:
  1. 24h window   — non-template free-form messages require an open customer-service window.
  2. opt-out      — marketing messages are blocked for opted-out contacts.
  3. rate limit   — token bucket per WhatsApp Account.

Phase 0 implements window + opt-out + rate. Pricing-category / template-category detection
is refined in Phase 2 (campaigns); for now "Template" messages are treated as able to open a
window, everything else as free-form.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from whatsapp_flow.wa_core import rate_limiter


class WindowClosedError(frappe.ValidationError):
    pass


class OptedOutError(frappe.ValidationError):
    pass


class RateLimitedError(frappe.ValidationError):
    pass


def _contact(mobile_no: str | None):
    if not mobile_no:
        return None
    name = frappe.db.get_value("WhatsApp Contact", {"mobile_no": mobile_no})
    return frappe.get_doc("WhatsApp Contact", name) if name else None


def run(doc) -> None:
    """Entry point from the WhatsApp Message override. `doc` is the WhatsApp Message."""
    if getattr(doc, "type", None) != "Outgoing":
        return

    # Bulk/notification senders may set a flag to bypass window logic for templates only;
    # we still enforce opt-out and rate limiting unconditionally.
    is_template = getattr(doc, "message_type", None) == "Template" or bool(getattr(doc, "template", None))
    contact = _contact(getattr(doc, "to", None))

    # 2. opt-out (marketing). Template category detection is refined in Phase 2; until then,
    # honour the opt-out flag for any template send (marketing templates are the risk).
    if contact and contact.get("wd_marketing_opt_out") and is_template:
        raise OptedOutError(
            _("Contact {0} has opted out of marketing messages.").format(doc.to)
        )

    # 1. 24h window — free-form (non-template) messages need an open window.
    if not is_template:
        expires = contact.get("wd_window_expires_at") if contact else None
        if not expires or expires < now_datetime():
            raise WindowClosedError(
                _("The 24-hour customer service window is closed for {0}. Send a template instead.").format(
                    doc.to
                )
            )

    # 3. rate limit per account.
    account = getattr(doc, "whatsapp_account", None)
    if not rate_limiter.take(account):
        raise RateLimitedError(_("Outbound rate limit reached for account {0}.").format(account))

    _stamp(doc, contact)


def _stamp(doc, contact) -> None:
    """Link the conversation and record who sent it."""
    user = frappe.session.user if frappe.session else None
    if user and user not in ("Guest", "Administrator") and not getattr(doc, "wd_sent_by", None):
        doc.wd_sent_by = user
        doc.wd_agent = user
    if contact and contact.get("wd_open_issue") and not getattr(doc, "wd_issue", None):
        doc.wd_issue = contact.wd_open_issue
