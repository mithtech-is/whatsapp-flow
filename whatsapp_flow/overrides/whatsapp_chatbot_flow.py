"""WhatsApp Chatbot Flow override — allow Graph-mode flows to skip the Steps requirement.

Upstream validate() requires a non-empty `steps` table (Steps mode). Graph-mode flows store
their logic in wd_graph_json instead, so we skip the steps check for them while keeping the
completion-action validation.
"""

from __future__ import annotations

from frappe_whatsapp_chatbot.frappe_whatsapp_chatbot.doctype.whatsapp_chatbot_flow.whatsapp_chatbot_flow import (
    WhatsAppChatbotFlow,
)


class WhatsAppChatbotFlowWD(WhatsAppChatbotFlow):
    def validate(self):
        if self.get("wd_mode") == "Graph":
            self.validate_completion_action()
            return
        super().validate()
