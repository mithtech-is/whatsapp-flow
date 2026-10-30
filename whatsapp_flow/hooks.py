app_name = "whatsapp_flow"
app_title = "WhatsApp Flow"
app_publisher = "MithTech"
app_description = (
    "Native-first agent desk, visual chatbot flow builder, SLA and campaigns for the "
    "Frappe WhatsApp apps."
)
app_email = "manoj@polemarch.in"
app_license = "mit"

# ---------------------------------------------------------------------------
# Dependencies — whatsapp_flow is an ADD-ON. It requires all three upstream apps.
# Install order: frappe_whatsapp -> whatsapp_chat -> frappe_whatsapp_chatbot -> whatsapp_flow
# so that our doc_events run AFTER theirs on WhatsApp Message.
# ---------------------------------------------------------------------------
required_apps = [
    "frappe",
    "erpnext",
    "frappe_whatsapp",
    "whatsapp_chat",
    "frappe_whatsapp_chatbot",
]

# ---------------------------------------------------------------------------
# DocType class overrides
# ---------------------------------------------------------------------------
# WhatsApp Message: wrap before_insert with the outbound send guard (window / opt-out /
# rate limit), then call super(). Verified: frappe_whatsapp sends to Meta inside
# before_insert, so this is the single chokepoint every sender funnels through.
override_doctype_class = {
    "WhatsApp Message": "whatsapp_flow.overrides.whatsapp_message.WhatsAppMessageWD",
    "WhatsApp Templates": "whatsapp_flow.overrides.whatsapp_templates.WhatsAppTemplatesWD",
    "Bulk WhatsApp Message": "whatsapp_flow.overrides.bulk_whatsapp_message.BulkWhatsAppMessageWD",
    "WhatsApp Chatbot Flow": "whatsapp_flow.overrides.whatsapp_chatbot_flow.WhatsAppChatbotFlowWD",
}

# ---------------------------------------------------------------------------
# Secured / missing endpoint replacements (§2.1 of the plan).
# NOTE: override_whitelisted_methods remaps the `cmd` string before it is resolved,
# so it also works for methods that don't exist upstream (e.g. set_typing).
# Additional chat-API overrides are added in Phase 0/1 as each is hardened.
# ---------------------------------------------------------------------------
override_whitelisted_methods = {
    # Webhook: HMAC verify + async (§2.1)
    "frappe_whatsapp.utils.webhook.webhook": "whatsapp_flow.endpoints.webhook.webhook",
    # Encrypted Flows data-exchange endpoint (§2.1, #64) — real decryption, upstream was a stub
    "frappe_whatsapp.frappe_whatsapp.api.flow_endpoint.handle_flow_request": "whatsapp_flow.wa_flows.endpoint.handle_flow_request",
    # whatsapp_chat API: permission checks, no contact leak, templates/interactive/status,
    # closed guest path, and the missing set_typing (§2.1)
    "whatsapp_chat.api.message.get_all": "whatsapp_flow.endpoints.chat.get_all",
    "whatsapp_chat.api.message.send": "whatsapp_flow.endpoints.chat.send",
    "whatsapp_chat.api.message.mark_as_read": "whatsapp_flow.endpoints.chat.mark_as_read",
    "whatsapp_chat.api.message.set_typing": "whatsapp_flow.endpoints.chat.set_typing",
    "whatsapp_chat.api.contacts.get": "whatsapp_flow.endpoints.chat.contacts_get",
    "whatsapp_chat.api.contacts.create": "whatsapp_flow.endpoints.chat.contacts_create",
    "whatsapp_chat.api.config.settings": "whatsapp_flow.endpoints.chat.config_settings",
}

# ---------------------------------------------------------------------------
# Document events — our handlers run last (install order).
# ---------------------------------------------------------------------------
doc_events = {
    "WhatsApp Message": {
        "after_insert": "whatsapp_flow.wa_desk.conversation.on_message",
    },
    "WhatsApp Agent Transfer": {
        "after_insert": "whatsapp_flow.wa_desk.assignment.on_agent_transfer",
    },
    # SSRF-harden outbound webhooks targeting WhatsApp Flow doctypes (#66).
    "Webhook": {
        "validate": "whatsapp_flow.wa_platform.webhooks.validate_webhook",
    },
}

# ---------------------------------------------------------------------------
# Fixtures (the documented way to ship customizations with an app — see Frappe
# "How To Create Custom Fields During App Installation"). Custom Fields are
# filtered by module == "WhatsApp Flow" (the module is stamped in
# setup/custom_fields.py) so the set captures exactly this app's fields.
# Regenerate with:  bench --site <site> export-fixtures --app whatsapp_flow
#
# Property Setters are deliberately NOT shipped as fixtures: our select-option
# setters (header_type, context_type, Bulk status) re-read the LIVE options and
# APPEND ours at install time (setup/property_setters.py). A frozen fixture would
# snapshot those options and could clobber a future upstream option, so these
# stay programmatic (idempotent, re-applied on every migrate).
# ---------------------------------------------------------------------------
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "WhatsApp Flow"]]},
    {"dt": "Role", "filters": [["name", "in", ["WA Admin", "WA Manager", "WA Agent"]]]},
]

# ---------------------------------------------------------------------------
# SPA at /whatsapp (Phase 1). Vue 3 + frappe-ui, built to public/frontend;
# www/whatsapp.html is the entry (replaced by `yarn copy-html-entry` after build).
# Deep links fall back to the same page for client-side routing.
# ---------------------------------------------------------------------------
website_route_rules = [
    {"from_route": "/whatsapp/<path:app_path>", "to_route": "whatsapp"},
]

# ---------------------------------------------------------------------------
# Install / migrate lifecycle
# ---------------------------------------------------------------------------
after_install = "whatsapp_flow.setup.install.after_install"
after_migrate = "whatsapp_flow.setup.install.after_migrate"

# ---------------------------------------------------------------------------
# Scheduler — retention / log cleanup (stubs wired in Phase 0).
# ---------------------------------------------------------------------------
scheduler_events = {
    "hourly": [
        "whatsapp_flow.wa_desk.sla.tick",
    ],
    "daily": [
        "whatsapp_flow.wa_platform.retention.run_retention",
        "whatsapp_flow.wa_desk.sla.auto_close",
    ],
}

# ---------------------------------------------------------------------------
# Runtime patch layer (§2.2). Guarded monkeypatches on the chatbot engine
# (plain Python classes, not DocTypes). Applied at app import in every process.
# Each patch checks the target signature + installed commit and falls back
# safely on mismatch; status is surfaced on the WhatsApp Settings health page.
# Wrapped so a failure here can never break app load.
# ---------------------------------------------------------------------------
try:
    from whatsapp_flow.compat import patches as _wd_patches

    _wd_patches.apply()
except Exception:  # pragma: no cover - never break app load
    import frappe

    frappe.log_error(frappe.get_traceback(), "whatsapp_flow: patch apply failed at import")
