"""Custom fields added by whatsapp_flow (native-first).

Created programmatically (idempotent) on install and migrate. All field names are prefixed
`wd_` so they never collide with upstream or core fields. Nothing here changes an existing
field — only additions and (separately) Property Setters.

Targets:
  * Upstream apps:  WhatsApp Account, WhatsApp Message, WhatsApp Contact,
                    WhatsApp Chatbot Flow, WhatsApp Chatbot Session, WhatsApp Agent Transfer,
                    WhatsApp Settings
  * Core / ERPNext: Issue (conversation/episode), User (agent presence)
"""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
    # ----- frappe_whatsapp: transport -------------------------------------
    "WhatsApp Account": [
        {
            "fieldname": "wd_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow",
            "insert_after": "allow_auto_read_receipt",
        },
        {
            "fieldname": "wd_app_secret",
            "label": "Meta App Secret",
            "fieldtype": "Password",
            "description": "Required — the signed webhook fails closed without it.",
            "insert_after": "wd_section",
        },
        {
            "fieldname": "wd_throughput_tier",
            "label": "Throughput Tier",
            "fieldtype": "Data",
            "insert_after": "wd_app_secret",
        },
        {
            "fieldname": "wd_calling_enabled",
            "label": "Calling Enabled",
            "fieldtype": "Check",
            "insert_after": "wd_throughput_tier",
        },
        {
            "fieldname": "wd_coexistence",
            "label": "Coexistence",
            "fieldtype": "Check",
            "insert_after": "wd_calling_enabled",
        },
        {
            "fieldname": "wd_quality_rating",
            "label": "Quality Rating",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "wd_coexistence",
        },
        {
            "fieldname": "wd_webhook_last_seen",
            "label": "Webhook Last Seen",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "wd_quality_rating",
        },
        {
            "fieldname": "wd_catalog_id",
            "label": "Meta Catalog ID",
            "fieldtype": "Data",
            "insert_after": "wd_webhook_last_seen",
        },
    ],
    # ----- frappe_whatsapp: the single message table ----------------------
    "WhatsApp Message": [
        {
            "fieldname": "wd_issue",
            "label": "Conversation (Issue)",
            "fieldtype": "Link",
            "options": "Issue",
            "search_index": 1,
            "insert_after": "whatsapp_account",
        },
        {
            "fieldname": "wd_sent_by",
            "label": "Sent By",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "wd_issue",
        },
        {
            "fieldname": "wd_agent",
            "label": "Agent",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "wd_sent_by",
        },
        {
            "fieldname": "wd_pricing_category",
            "label": "Pricing Category",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "wd_agent",
        },
        {
            "fieldname": "wd_error_code",
            "label": "Error Code",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "wd_pricing_category",
        },
        {
            # Meta Cloud API payload (interactive/list/poll/media/template components)
            # emitted by the graph runner for sends the upstream `content_type` can't express.
            # Upstream frappe_whatsapp honours its own fields first; this is read by the
            # send hook when present and used as the raw body sent to Meta.
            "fieldname": "wd_meta_payload",
            "label": "Meta Payload (JSON)",
            "fieldtype": "Long Text",
            "read_only": 1,
            "insert_after": "wd_error_code",
        },
    ],
    # ----- whatsapp_chat: the customer record / inbox row -----------------
    "WhatsApp Contact": [
        {
            "fieldname": "wd_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow",
            "insert_after": "email",
        },
        {
            "fieldname": "wd_whatsapp_account",
            "label": "WhatsApp Account",
            "fieldtype": "Link",
            "options": "WhatsApp Account",
            "insert_after": "wd_section",
        },
        {
            "fieldname": "wd_profile",
            "label": "Profile",
            "fieldtype": "Link",
            "options": "WhatsApp Profiles",
            "insert_after": "wd_whatsapp_account",
        },
        {
            "fieldname": "wd_open_issue",
            "label": "Open Conversation (Issue)",
            "fieldtype": "Link",
            "options": "Issue",
            "insert_after": "wd_profile",
        },
        {
            "fieldname": "wd_team",
            "label": "Team",
            "fieldtype": "Link",
            "options": "User Group",
            "insert_after": "wd_open_issue",
        },
        {
            "fieldname": "wd_window_expires_at",
            "label": "24h Window Expires At",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "wd_team",
        },
        {
            "fieldname": "wd_col_break",
            "fieldtype": "Column Break",
            "insert_after": "wd_window_expires_at",
        },
        {
            "fieldname": "wd_unread_count",
            "label": "Unread Count",
            "fieldtype": "Int",
            "insert_after": "wd_col_break",
        },
        {
            "fieldname": "wd_bot_active",
            "label": "Bot Active",
            "fieldtype": "Check",
            "default": "1",
            "insert_after": "wd_unread_count",
        },
        {
            "fieldname": "wd_marketing_opt_out",
            "label": "Marketing Opt-out",
            "fieldtype": "Check",
            "insert_after": "wd_bot_active",
        },
        {
            "fieldname": "wd_opt_out_on",
            "label": "Opted Out On",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "wd_marketing_opt_out",
        },
        {
            "fieldname": "wd_opt_out_source",
            "label": "Opt-out Source",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "wd_opt_out_on",
        },
        {
            "fieldname": "wd_call_consent",
            "label": "Outbound Call Consent",
            "fieldtype": "Check",
            "insert_after": "wd_opt_out_source",
        },
        {
            "fieldname": "wd_call_consent_on",
            "label": "Call Consent On",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "wd_call_consent",
        },
        {
            "fieldname": "wd_call_consent_source",
            "label": "Call Consent Source",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "wd_call_consent_on",
        },
        {
            "fieldname": "wd_custom_data",
            "label": "Custom Data",
            "fieldtype": "JSON",
            "insert_after": "wd_call_consent_source",
        },
        {
            "fieldname": "wd_language",
            "label": "Language",
            "fieldtype": "Data",
            "insert_after": "wd_custom_data",
        },
    ],
    # ----- frappe_whatsapp_chatbot: AI Context External API (#14) ---------
    "WhatsApp AI Context": [
        {
            "fieldname": "wd_api_section",
            "fieldtype": "Section Break",
            "label": "External API (WhatsApp Flow)",
            "insert_after": "phone_field",
            "depends_on": "eval:doc.context_type=='External API'",
            "collapsible": 1,
        },
        {"fieldname": "wd_api_url", "label": "API URL", "fieldtype": "Data", "insert_after": "wd_api_section"},
        {"fieldname": "wd_api_method", "label": "Method", "fieldtype": "Select",
         "options": "GET\nPOST", "default": "GET", "insert_after": "wd_api_url"},
        {"fieldname": "wd_api_headers", "label": "Headers (JSON)", "fieldtype": "JSON", "insert_after": "wd_api_method"},
        {"fieldname": "wd_response_path", "label": "Response Path", "fieldtype": "Data",
         "description": "Dotted path into the JSON response, e.g. data.summary", "insert_after": "wd_api_headers"},
    ],
    # ----- frappe_whatsapp_chatbot: greeting / fallback / handoff (#25) ----
    "WhatsApp Chatbot": [
        {
            "fieldname": "wd_desk_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow",
            "insert_after": "default_response",
            "collapsible": 1,
        },
        {"fieldname": "wd_greeting", "label": "Greeting Message", "fieldtype": "Small Text", "insert_after": "wd_desk_section"},
        {"fieldname": "wd_fallback_buttons", "label": "Fallback Buttons (JSON)", "fieldtype": "JSON", "insert_after": "wd_greeting"},
        {"fieldname": "wd_handoff_team", "label": "Default Handoff Team", "fieldtype": "Link",
         "options": "User Group", "insert_after": "wd_fallback_buttons"},
        {"fieldname": "wd_ai_tools_enabled", "label": "Enable AI Tools", "fieldtype": "Check", "insert_after": "wd_handoff_team"},
        {"fieldname": "wd_holiday_list", "label": "Holiday List", "fieldtype": "Link",
         "options": "Holiday List", "insert_after": "wd_ai_tools_enabled"},
    ],
    # ----- frappe_whatsapp_chatbot: flows & sessions ----------------------
    "WhatsApp Chatbot Flow": [
        {
            "fieldname": "wd_mode",
            "label": "Builder Mode",
            "fieldtype": "Select",
            "options": "Steps\nGraph",
            "default": "Steps",
            "insert_after": "enabled",
        },
        {
            "fieldname": "wd_graph_json",
            "label": "Graph (draft)",
            "fieldtype": "Long Text",
            "depends_on": "eval:doc.wd_mode=='Graph'",
            "insert_after": "wd_mode",
        },
        {
            "fieldname": "wd_published_json",
            "label": "Graph (published snapshot)",
            "fieldtype": "Long Text",
            "read_only": 1,
            "insert_after": "wd_graph_json",
        },
        {
            "fieldname": "wd_version",
            "label": "Version",
            "fieldtype": "Int",
            "read_only": 1,
            "insert_after": "wd_published_json",
        },
        {
            "fieldname": "wd_published",
            "label": "Published",
            "fieldtype": "Check",
            "read_only": 1,
            "insert_after": "wd_version",
        },
    ],
    "WhatsApp Chatbot Session": [
        {
            "fieldname": "wd_current_node",
            "label": "Current Node",
            "fieldtype": "Data",
            "insert_after": "name",
        },
        {
            "fieldname": "wd_graph_vars",
            "label": "Graph Variables",
            "fieldtype": "JSON",
            "insert_after": "wd_current_node",
        },
        {
            "fieldname": "wd_issue",
            "label": "Conversation (Issue)",
            "fieldtype": "Link",
            "options": "Issue",
            "insert_after": "wd_graph_vars",
        },
    ],
    "WhatsApp Agent Transfer": [
        {
            "fieldname": "wd_team",
            "label": "Team",
            "fieldtype": "Link",
            "options": "User Group",
            "insert_after": "name",
        },
        {
            "fieldname": "wd_issue",
            "label": "Conversation (Issue)",
            "fieldtype": "Link",
            "options": "Issue",
            "insert_after": "wd_team",
        },
        {
            "fieldname": "wd_picked_up_by",
            "label": "Picked Up By",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "wd_issue",
        },
        {
            "fieldname": "wd_queue_status",
            "label": "Queue Status",
            "fieldtype": "Select",
            "options": "Queued\nAssigned\nResolved\nExpired",
            "insert_after": "wd_picked_up_by",
        },
    ],
    # ----- frappe_whatsapp: WhatsApp Settings (Single) --------------------
    "WhatsApp Settings": [
        {
            "fieldname": "wd_desk_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow",
            "insert_after": "",
        },
        {
            "fieldname": "wd_phone_masking",
            "label": "Mask Phone Numbers",
            "fieldtype": "Check",
            "insert_after": "wd_desk_section",
        },
        {
            "fieldname": "wd_retention_days",
            "label": "Log Retention (days)",
            "fieldtype": "Int",
            "insert_after": "wd_phone_masking",
        },
        {
            "fieldname": "wd_auto_close_days",
            "label": "Auto-close Resolved After (days)",
            "fieldtype": "Int",
            "insert_after": "wd_retention_days",
        },
        {
            "fieldname": "wd_media_bridge_url",
            "label": "Media Bridge URL",
            "fieldtype": "Data",
            "insert_after": "wd_retention_days",
        },
        {
            "fieldname": "wd_rate_limits",
            "label": "Rate Limits (JSON)",
            "fieldtype": "JSON",
            "insert_after": "wd_media_bridge_url",
        },
        {
            "fieldname": "wd_patch_health",
            "label": "Patch & Override Health",
            "fieldtype": "Small Text",
            "read_only": 1,
            "insert_after": "wd_rate_limits",
        },
        {
            "fieldname": "wd_flows_private_key",
            "label": "WhatsApp Flows Private Key (PEM)",
            "fieldtype": "Password",
            "description": "RSA private key for the encrypted Flows data-exchange endpoint.",
            "insert_after": "wd_patch_health",
        },
        {"fieldname": "wd_voice_enabled", "label": "Enable Voice (Calling)", "fieldtype": "Check",
         "insert_after": "wd_flows_private_key"},
    ],
    # ----- ERPNext Issue: the conversation / support episode --------------
    "Issue": [
        {
            "fieldname": "wd_whatsapp_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp",
            "insert_after": "content_type",
            "collapsible": 1,
        },
        {
            "fieldname": "wd_whatsapp_contact",
            "label": "WhatsApp Contact",
            "fieldtype": "Link",
            "options": "WhatsApp Contact",
            "insert_after": "wd_whatsapp_section",
        },
        {
            "fieldname": "wd_account",
            "label": "WhatsApp Account",
            "fieldtype": "Link",
            "options": "WhatsApp Account",
            "insert_after": "wd_whatsapp_contact",
        },
        {
            "fieldname": "wd_source",
            "label": "Source",
            "fieldtype": "Select",
            "options": "\nbot\ninbound\noutbound",
            "insert_after": "wd_account",
        },
        {
            "fieldname": "wd_escalation_level",
            "label": "WA Escalation Level",
            "fieldtype": "Int",
            "hidden": 1,
            "read_only": 1,
            "insert_after": "wd_source",
        },
    ],
    # ----- frappe_whatsapp Bulk WhatsApp Message: campaign controls (#46-49) --
    "Bulk WhatsApp Message": [
        {
            "fieldname": "wd_campaign_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow",
            "insert_after": "status",
            "collapsible": 1,
        },
        {
            "fieldname": "wd_respect_opt_out",
            "label": "Respect Marketing Opt-out",
            "fieldtype": "Check",
            "default": "1",
            "insert_after": "wd_campaign_section",
        },
        {
            "fieldname": "wd_throttle_per_min",
            "label": "Throttle (messages/min, 0 = unlimited)",
            "fieldtype": "Int",
            "insert_after": "wd_respect_opt_out",
        },
        {
            "fieldname": "wd_segment",
            "label": "Segment",
            "fieldtype": "Link",
            "options": "WA Segment",
            "insert_after": "wd_throttle_per_min",
        },
        {
            "fieldname": "wd_skipped_count",
            "label": "Skipped (opt-out)",
            "fieldtype": "Int",
            "read_only": 1,
            "insert_after": "wd_segment",
        },
    ],
    # ----- ERPNext Service Level Agreement: escalation ladder (#33) --------
    "Service Level Agreement": [
        {
            "fieldname": "wd_escalation_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow Escalation",
            "insert_after": "pause_sla_on",
            "collapsible": 1,
        },
        {
            "fieldname": "wd_escalation_levels",
            "label": "Escalation Levels",
            "fieldtype": "Table",
            "options": "WA Escalation Level",
            "insert_after": "wd_escalation_section",
        },
    ],
    # ----- Frappe Call Log: WhatsApp voice calls (#1-#12) -----------------
    "Call Log": [
        {"fieldname": "wd_section", "fieldtype": "Section Break", "label": "WhatsApp Flow",
         "insert_after": "recording_url", "collapsible": 1},
        {"fieldname": "wd_whatsapp_account", "label": "WhatsApp Account", "fieldtype": "Link",
         "options": "WhatsApp Account", "insert_after": "wd_section"},
        {"fieldname": "wd_contact", "label": "WhatsApp Contact", "fieldtype": "Link",
         "options": "WhatsApp Contact", "insert_after": "wd_whatsapp_account"},
        {"fieldname": "wd_issue", "label": "Conversation (Issue)", "fieldtype": "Link",
         "options": "Issue", "insert_after": "wd_contact"},
        {"fieldname": "wd_meta_call_id", "label": "Meta Call ID", "fieldtype": "Data",
         "read_only": 1, "insert_after": "wd_issue"},
        {"fieldname": "wd_ivr_flow", "label": "IVR Flow", "fieldtype": "Link",
         "options": "WhatsApp Chatbot Flow", "insert_after": "wd_meta_call_id"},
    ],
    # ----- Frappe User: agent presence / capacity -------------------------
    "User": [
        {
            "fieldname": "wd_wa_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Flow Agent",
            "insert_after": "",
            "collapsible": 1,
        },
        {
            "fieldname": "wd_wa_availability",
            "label": "WhatsApp Availability",
            "fieldtype": "Select",
            "options": "Offline\nOnline\nAway",
            "default": "Offline",
            "insert_after": "wd_wa_section",
        },
        {
            "fieldname": "wd_wa_capacity",
            "label": "Concurrent Conversation Capacity",
            "fieldtype": "Int",
            "insert_after": "wd_wa_availability",
        },
    ],
}


# This app's module — stamped on every Custom Field so the fields are OWNED by
# whatsapp_flow (they belong to this app's module, are exported with it, and are
# removed cleanly on uninstall) rather than being orphaned onto the upstream
# apps' doctypes. See Frappe docs: a Custom Field's `module` decides which app
# owns it. https://docs.frappe.io/framework/user/en/guides/app-development/exporting-customizations
APP_MODULE = "WhatsApp Flow"


def create() -> None:
    """Idempotent: create_custom_fields updates existing fields in place.

    Each field is stamped with this app's module (APP_MODULE) so it is housed
    under whatsapp_flow. On migrate this also re-homes any field that predates
    the stamping.
    """
    for fields in CUSTOM_FIELDS.values():
        for df in fields:
            df.setdefault("module", APP_MODULE)
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
