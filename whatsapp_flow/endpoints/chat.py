"""Secured replacements for the whatsapp_chat API (§2.1).

These override the upstream whitelisted methods via override_whitelisted_methods. They add the
permission checks the originals lack, stop leaking other users' contacts, include template /
interactive / status rows that the raw-SQL original hid, close the broken guest config path,
and implement the missing set_typing. Outbound sends still pass through the WhatsApp Message
send guard automatically (the send happens in the doctype's before_insert).
"""

from __future__ import annotations

import frappe
from frappe import _

MANAGER_ROLES = {"System Manager", "WA Admin", "WA Manager"}


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
def _is_manager() -> bool:
    return bool(MANAGER_ROLES.intersection(frappe.get_roles()))


def _can_access_contact(room: str) -> bool:
    """A manager sees everything; an agent sees contacts assigned to them.

    whatsapp_chat stores the current assignee in WhatsApp Contact.email; we also honour a
    standard Frappe ToDo assignment on the contact or its open Issue.
    """
    if not room:
        return False
    if _is_manager():
        return True
    user = frappe.session.user
    contact = frappe.db.get_value(
        "WhatsApp Contact", room, ["email", "wd_open_issue"], as_dict=True
    )
    if not contact:
        return False
    if contact.email == user:
        return True
    # assigned via ToDo on the contact or the Issue
    for dt, dn in (("WhatsApp Contact", room), ("Issue", contact.wd_open_issue)):
        if dn and frappe.db.exists(
            "ToDo", {"reference_type": dt, "reference_name": dn, "allocated_to": user, "status": "Open"}
        ):
            return True
    return False


def _guard_contact(room: str) -> None:
    if not _can_access_contact(room):
        raise frappe.PermissionError(_("You are not allowed to access this conversation."))


# ---------------------------------------------------------------------------
# message.get_all  — permission-checked; includes templates / interactive / status
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_all(room: str, user_no: str):
    _guard_contact(room)
    return frappe.get_all(
        "WhatsApp Message",
        or_filters=[{"from": user_no}, {"to": user_no}],
        fields=[
            "name",
            "creation",
            "type",
            "`from`",
            "`to`",
            "message",
            "attach",
            "content_type",
            "message_type",
            "template",
            "buttons",
            "status",
            "message_id",
            "reply_to_message_id",
            "is_reply",
        ],
        order_by="creation asc",
        limit_page_length=0,
    )


# ---------------------------------------------------------------------------
# message.send — permission-checked; text / media / template / interactive / reaction
# ---------------------------------------------------------------------------
@frappe.whitelist()
def send(content, user, room, user_no, attachment=None, message_type=None, template=None,
         buttons=None, reaction_to=None, body_param=None):
    _guard_contact(room)

    doc = {
        "doctype": "WhatsApp Message",
        "to": user_no,
        "type": "Outgoing",
    }

    if template:
        doc.update({"message_type": "Template", "template": template, "content_type": "text"})
        if body_param:
            doc["body_param"] = body_param if isinstance(body_param, str) else frappe.as_json(body_param)
    elif reaction_to:
        doc.update({"content_type": "reaction", "message": content, "reply_to_message_id": reaction_to})
    elif buttons:
        doc.update({"content_type": "interactive", "message": content, "buttons": buttons})
    elif attachment:
        doc.update({"attach": attachment, "content_type": _content_type_for(attachment)})
    else:
        doc.update({"message": content, "content_type": "text"})

    # The WhatsApp Message before_insert send guard (window / opt-out / rate) runs here.
    frappe.get_doc(doc).insert(ignore_permissions=True)
    return "ok"


def _content_type_for(path: str) -> str:
    import mimetypes

    ft = (mimetypes.guess_type(path)[0] or "")
    if ft.startswith("image/"):
        return "image"
    if ft.startswith("video/"):
        return "video"
    if ft.startswith("audio/"):
        return "audio"
    return "document"


# ---------------------------------------------------------------------------
# message.mark_as_read — permission-checked
# ---------------------------------------------------------------------------
@frappe.whitelist()
def mark_as_read(room):
    _guard_contact(room)
    frappe.db.set_value("WhatsApp Contact", room, {"is_read": 1, "wd_unread_count": 0}, update_modified=False)
    frappe.db.commit()
    try:
        from whatsapp_chat.api.message import send_whatsapp_read_receipts

        send_whatsapp_read_receipts(room)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: read receipt failed")
    return "ok"


# ---------------------------------------------------------------------------
# message.set_typing — implemented (upstream is missing; client calls it)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def set_typing(room, state: str = "on"):
    _guard_contact(room)
    assignee = frappe.db.get_value("WhatsApp Contact", room, "email")
    payload = {"room": room, "state": state, "user": frappe.session.user}
    # Match upstream realtime convention: event name = room, targeted at the assignee.
    frappe.publish_realtime(f"{room}:typing", payload, user=assignee or None)
    return "ok"


# ---------------------------------------------------------------------------
# contacts.get / create — scoped to the caller
# ---------------------------------------------------------------------------
@frappe.whitelist()
def contacts_get(email=None):
    """Ignore any email passed in (the upstream leak); scope to the caller unless manager."""
    if _is_manager():
        return frappe.get_all("WhatsApp Contact", fields=["*"])
    user = frappe.session.user
    return frappe.get_all("WhatsApp Contact", filters={"email": user}, fields=["*"])


@frappe.whitelist()
def contacts_create(contact_name, mobile_no, email=None):
    if not _is_manager() and "WA Agent" not in frappe.get_roles():
        raise frappe.PermissionError(_("Not allowed to create contacts."))
    doc = frappe.get_doc(
        {
            "doctype": "WhatsApp Contact",
            "contact_name": contact_name,
            "mobile_no": mobile_no,
            "email": email or frappe.session.user,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


# ---------------------------------------------------------------------------
# config.settings — close the broken guest path (undefined validate_token)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def config_settings(token=None):
    from whatsapp_chat.api.config import get_admin_name, get_chat_settings, get_user_settings

    is_admin = "user_type" in (frappe.session.data or {})
    config = {
        "socketio_port": frappe.conf.socketio_port,
        "user_email": frappe.session.user,
        "is_admin": bool(is_admin),
        "guest_title": "".join(frappe.get_hooks("guest_title")),
    }
    config.update(get_chat_settings())
    if is_admin:
        config["user"] = get_admin_name(config["user_email"])
        config["user_settings"] = get_user_settings()
    else:
        # Guest chat is not supported in whatsapp_flow; the upstream guest branch called an
        # undefined validate_token. Close it cleanly instead of erroring.
        config["user"] = "Guest"
        config["is_verified"] = False
    return config
