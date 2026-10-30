"""WA Admin / WA Manager / WA Agent roles.

Roles are created here (idempotent) and also exported as fixtures (hooks.fixtures) so they
travel with the app. DocPerms across the three apps' DocTypes + Issue are layered on in
Phase 0/1 via Custom DocPerm fixtures.
"""

from __future__ import annotations

import frappe

ROLES = [
    {"role_name": "WA Admin", "desk_access": 1},
    {"role_name": "WA Manager", "desk_access": 1},
    {"role_name": "WA Agent", "desk_access": 1},
]


def create() -> None:
    for r in ROLES:
        if not frappe.db.exists("Role", r["role_name"]):
            doc = frappe.new_doc("Role")
            doc.update(r)
            doc.flags.ignore_permissions = True
            doc.insert()
