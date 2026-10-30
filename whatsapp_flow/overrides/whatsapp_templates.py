"""WhatsApp Templates class override (§3.1 / #50–#53).

Adds, without forking upstream:
  * VIDEO header support — upstream validate() only uploads sample media for IMAGE/DOCUMENT;
    get_header() already emits header_handle for any non-TEXT type, so we just extend the
    media-upload gate to include VIDEO (the Select option is added by a Property Setter).

TODO (Phase 2/3), scaffolded here:
  * named parameters (Meta's named vs positional body params)
  * draft -> publish lifecycle (create as draft, publish explicitly)
These are stubbed so the override is in place; they are implemented when the template composer
lands and can be validated on a bench.
"""

from __future__ import annotations

from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import (
    WhatsAppTemplates,
)

MEDIA_HEADER_TYPES = {"IMAGE", "DOCUMENT", "VIDEO"}


class WhatsAppTemplatesWD(WhatsAppTemplates):
    def validate(self):
        # Upload sample media for VIDEO too (upstream handles only IMAGE/DOCUMENT).
        if self.header_type == "VIDEO" and self.sample:
            self.set_whatsapp_account()
            if not self.language_code or self.has_value_changed("language"):
                import frappe

                lang_code = frappe.db.get_value("Language", self.language) or "en"
                self.language_code = lang_code.replace("-", "_")
            self.get_session_id(self.sample)
            self.get_media_id(self.sample)
            if not self.is_new():
                self.update_template()
            return
        super().validate()

    # --- Phase 2/3 scaffolding ------------------------------------------------
    def wd_publish_draft(self):
        """Publish a locally-drafted template to Meta. Implemented in Phase 2."""
        raise NotImplementedError("draft->publish lands in Phase 2")
