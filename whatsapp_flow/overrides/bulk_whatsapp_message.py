"""Bulk WhatsApp Message class override — campaign controls (#46-#49).

Adds, without forking upstream:
  * pause / resume / cancel (checked before each per-recipient send)
  * opt-out skipping (respect WhatsApp Contact.wd_marketing_opt_out)
  * throttle (messages/min) — spaces the per-recipient jobs via the scheduler
The send guard on WhatsApp Message is still the backstop for window/opt-out/rate.
"""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import cint

from frappe_whatsapp.frappe_whatsapp.doctype.bulk_whatsapp_message.bulk_whatsapp_message import (
    BulkWhatsAppMessage,
)


class BulkWhatsAppMessageWD(BulkWhatsAppMessage):
    def queue_messages(self):
        throttle = cint(self.get("wd_throttle_per_min"))
        if throttle <= 0:
            return super().queue_messages()
        # Throttled: schedule each recipient with an increasing delay.
        recipients = self._wd_recipients()
        delay = 60.0 / throttle
        from frappe.utils.background_jobs import get_queue

        q = get_queue("long")
        for i, recipient in enumerate(recipients):
            q.enqueue_in(
                timedelta(seconds=i * delay),
                "whatsapp_flow.wa_campaign.bulk.send_recipient",
                bulk_name=self.name,
                recipient=recipient,
            )

    def _wd_recipients(self) -> list[dict]:
        if self.recipient_type == "Recipient List" and self.recipient_list:
            return frappe.get_all(
                "WhatsApp Recipient",
                filters={"parent": self.recipient_list},
                fields=["mobile_number", "recipient_name", "recipient_data"],
            )
        return [
            {"mobile_number": r.mobile_number, "recipient_name": r.recipient_name,
             "recipient_data": r.recipient_data}
            for r in (self.recipients or [])
        ]

    def create_single_message(self, recipient):
        # Honour pause/cancel set after the job was enqueued.
        status = frappe.db.get_value("Bulk WhatsApp Message", self.name, "status")
        if status in ("Paused", "Cancelled"):
            return
        # Skip opted-out recipients up front (quieter than letting the guard raise).
        if self.get("wd_respect_opt_out"):
            num = recipient.get("mobile_number")
            if num and frappe.db.get_value("WhatsApp Contact", {"mobile_no": num}, "wd_marketing_opt_out"):
                self.db_set("wd_skipped_count", cint(self.get("wd_skipped_count")) + 1,
                            update_modified=False)
                return
        return super().create_single_message(recipient)

    @frappe.whitelist()
    def wd_pause(self):
        self.db_set("status", "Paused")

    @frappe.whitelist()
    def wd_resume(self):
        self.db_set("status", "Queued")

    @frappe.whitelist()
    def wd_cancel(self):
        self.db_set("status", "Cancelled")
