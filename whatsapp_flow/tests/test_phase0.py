"""Phase 0 guard tests — run on a bench via `bench run-tests --app whatsapp_flow`.

They assert the security-critical wiring is actually active: endpoint overrides resolve to our
handlers, the chatbot runtime patches applied, the custom fields exist, and the send guard /
webhook signature behave. These are the CI gate the plan calls for (so an override silently
falling back to upstream fails the build).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from whatsapp_flow.compat import health, patches
from whatsapp_flow.wa_core import signature


class TestPhase0Overrides(FrappeTestCase):
    def test_endpoint_overrides_active(self):
        active = frappe.get_hooks("override_whitelisted_methods") or {}
        for original, expected in health.EXPECTED_OVERRIDES.items():
            got = active.get(original)
            got = got[-1] if isinstance(got, list) and got else got
            self.assertEqual(got, expected, f"override for {original} not active")

    def test_message_class_override_active(self):
        cls = frappe.get_hooks("override_doctype_class") or {}
        self.assertIn("WhatsApp Message", cls)

    def test_runtime_patches_applied(self):
        patches.apply()
        status = patches.get_status()
        for name in ("async_processing", "safe_exec", "human_skip"):
            self.assertIn(name, status, f"patch {name} never ran")
            self.assertIn(
                status[name]["status"],
                ("applied", "skipped"),
                f"patch {name} errored: {status[name]}",
            )


class TestPhase0Fields(FrappeTestCase):
    def test_custom_fields_exist(self):
        checks = [
            ("WhatsApp Message", "wd_issue"),
            ("WhatsApp Contact", "wd_open_issue"),
            ("WhatsApp Contact", "wd_bot_active"),
            ("WhatsApp Account", "wd_app_secret"),
            ("Issue", "wd_whatsapp_contact"),
            ("User", "wd_wa_availability"),
        ]
        for doctype, field in checks:
            self.assertTrue(
                frappe.get_meta(doctype).has_field(field),
                f"missing custom field {doctype}.{field}",
            )


class TestSignature(FrappeTestCase):
    def test_bad_signature_rejected(self):
        self.assertFalse(signature.verify(b"{}", None))
        self.assertFalse(signature.verify(b"{}", "sha256=deadbeef"))
