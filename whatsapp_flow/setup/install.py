"""Install / migrate lifecycle for whatsapp_flow."""

from __future__ import annotations

import frappe

from whatsapp_flow.setup import analytics, custom_fields, permissions, property_setters, roles, sla


def after_install() -> None:
    _setup()


def after_migrate() -> None:
    _setup()
    # Refresh the health snapshot shown on WhatsApp Settings.
    try:
        from whatsapp_flow.compat import health

        health.refresh_settings_field()
    except Exception:
        pass


def _setup() -> None:
    roles.create()
    # Custom fields are NOT created here — they ship as fixtures
    # (whatsapp_flow/fixtures/custom_field.json) and are synced automatically on
    # install + every `bench migrate` (frappe.migrate -> sync_fixtures), which is
    # the documented method. `custom_fields.create()` remains in the module as the
    # authoring tool: edit CUSTOM_FIELDS, run it once on a dev site, then
    # `bench --site <site> export-fixtures --app whatsapp_flow` to regenerate.
    property_setters.create()
    permissions.create()
    sla.ensure_default_sla()
    analytics.ensure_analytics()
    frappe.db.commit()
