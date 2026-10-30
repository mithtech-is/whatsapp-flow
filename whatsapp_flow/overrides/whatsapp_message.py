"""WhatsApp Message class override — the single outbound chokepoint.

Verified against source: frappe_whatsapp sends to Meta inside `before_insert`
(-> send_outgoing -> notify). So running the send guard first and only then calling
`super().before_insert()` means a blocked message is never sent (the guard raises before
super()). Because the send lives in the Message doctype itself, every creator — agent chat
bubble, SPA composer, bot, Bulk, Notification, REST API — funnels through here.
"""

from __future__ import annotations

from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message import (
    WhatsAppMessage,
)

from whatsapp_flow.wa_core import guard


class WhatsAppMessageWD(WhatsAppMessage):
    def before_insert(self):
        # Guard only outbound sends; raising aborts the insert (and the Meta call).
        guard.run(self)
        super().before_insert()
