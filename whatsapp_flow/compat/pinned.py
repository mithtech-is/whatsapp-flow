"""Pinned / tested upstream commits.

CI runs against these pinned commits AND nightly against each app's develop branch so
upstream breakage is caught early. The runtime patch guards (patches.py) compare the
installed commit against these and skip a patch on mismatch rather than crashing.

Fill the hashes in once the apps are vendored on the target bench:
    bench version --format json   # or: git -C apps/<app> rev-parse HEAD
"""

# app -> tested commit (None = "untested / accept any", guards then rely on signature checks only).
# Pinned 2026-10-14 against the commits whatsapp_flow was built + validated on (ERPNext v16.20).
PINNED_COMMITS = {
    "frappe_whatsapp": "08bc1f6af2e36022d7a5f77641c8ba2ef8c16aaa",        # master
    "whatsapp_chat": "4ad3712528e9a56b536bccd190231663f04b8e7b",          # develop
    "frappe_whatsapp_chatbot": "e98a655af42be5c0e8cc3912780418e2206d5bdb",  # master
}


def installed_commit(app: str) -> str | None:
    """Best-effort current commit of an installed app; None if unavailable."""
    try:
        import frappe

        return frappe.get_app_commit(app)  # type: ignore[attr-defined]
    except Exception:
        try:
            import subprocess
            import frappe

            path = frappe.get_app_path(app)
            return (
                subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"])
                .decode()
                .strip()
            )
        except Exception:
            return None


def commit_matches(app: str) -> bool:
    """True if we have no pin (accept) or the installed commit equals the pin."""
    pin = PINNED_COMMITS.get(app)
    if not pin:
        return True
    return installed_commit(app) == pin
