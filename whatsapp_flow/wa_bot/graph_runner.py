"""Graph-mode chatbot runner (flow-builder-spec §7).

Executes a published graph (WhatsApp Chatbot Flow.wd_published_json) against a
WhatsApp Chatbot Session. Node-agnostic walk: each handler returns a directive —
("next",) | ("branch", handle) | ("goto", node_id) | ("wait", node_id) | ("end",).

`send` is injectable so the dry-run simulator and tests can capture outbound messages
instead of creating real WhatsApp Message docs. The default send creates an Outgoing
WhatsApp Message flagged ignore_chatbot (so it never re-triggers the bot) — it passes
through the send guard like any other sender.
"""

from __future__ import annotations

import json
import re

import frappe

MAX_STEPS = 50


class Ctx:
    def __init__(self, flow, graph, session, inbound, send, issue=None, contact=None):
        self.flow = flow
        self.nodes = {n["id"]: n for n in graph.get("nodes", [])}
        self.edges = graph.get("edges", [])
        self.session = session
        self.inbound = (inbound or "").strip()
        self.send = send
        self.issue = issue
        self.contact = contact or {}
        self.vars = json.loads(session.get("wd_graph_vars") or "{}") if session else {}
        # Built-in variables Polyg-style, available to {{ }} rendering and the condition
        # router without polluting the persisted user-vars.
        self.builtins = {
            "senderName": self.contact.get("first_name") or self.contact.get("name") or "",
            "senderMessage": self.inbound,
            "CustomInput": self.inbound,
        }
        self.consume = False  # True only on the parked node we resume into


# --------------------------------------------------------------------------- helpers
def _start_node(ctx: Ctx):
    for nid, n in ctx.nodes.items():
        if n.get("type") == "start":
            return nid
    return None


def _follow(ctx: Ctx, source: str, handle):
    for e in ctx.edges:
        if e.get("source") == source and (e.get("sourceHandle") or None) == (handle or None):
            return e.get("target")
    # fall back to any edge from source if the exact handle wasn't found
    if handle:
        for e in ctx.edges:
            if e.get("source") == source:
                return e.get("target")
    return None


def _d(node: str, key: str, default=None):
    return (node or {}).get("data", {}).get(key, default) if isinstance(node, dict) else default


# --------------------------------------------------------------------------- node handlers
def h_start(node, ctx: Ctx):
    msg = _d(node, "initial_message")
    if msg and not ctx.consume:
        ctx.send(text=_render(msg, ctx))
    return ("next",)


def h_text(node, ctx: Ctx):
    tmpl = _d(node, "template")
    if _d(node, "message_type") == "Template" and tmpl:
        params = _d(node, "template_components") or _d(node, "template_params")
        ctx.send(template=tmpl, template_components=_render_components(params, ctx),
                 template_language=_d(node, "template_language", "en"))
    else:
        ctx.send(text=_render(_d(node, "message", ""), ctx))
    return ("next",)


def h_media(node, ctx: Ctx):
    kind = (_d(node, "media_type") or "image").lower()  # image|video|document|audio
    link = _render(_d(node, "media_url", ""), ctx)
    caption = _render(_d(node, "caption", ""), ctx)
    filename = _d(node, "filename")
    ctx.send(media={"type": kind, "link": link, "caption": caption, "filename": filename})
    return ("next",)


def h_buttons(node, ctx: Ctx):
    """≤3 options → Meta interactive buttons; 4–10 → fallthrough to list via h_list.

    Reply handles are the stable button `id`s plus a `fallback`.
    """
    buttons = _d(node, "buttons", []) or []
    if ctx.consume:
        picked = _match_button(ctx.inbound, buttons)
        if picked is not None:
            return ("branch", picked)
        return ("branch", "fallback")
    if len(buttons) > 3:
        # auto-route to list payload for correct Meta shape
        sections = [{"title": _d(node, "list_section_title", "Options"),
                     "rows": [{"id": b.get("id"), "title": b.get("title", "")[:24],
                               "description": b.get("description", "")[:72]}
                              for b in buttons]}]
        ctx.send(list={"body": _render(_d(node, "message", ""), ctx),
                       "button": _d(node, "list_button", "Choose"),
                       "sections": sections})
    else:
        ctx.send(buttons={"body": _render(_d(node, "message", ""), ctx),
                          "buttons": [{"id": b.get("id"), "title": b.get("title", "")[:20]}
                                      for b in buttons]})
    return ("wait", node["id"])


def h_list(node, ctx: Ctx):
    """Explicit native list — one `sections[]` of rows[]; same reply matching as buttons."""
    sections = _d(node, "sections") or []
    # flatten rows for match (same `id` scheme as buttons)
    rows = [r for s in sections for r in s.get("rows", [])]
    if ctx.consume:
        picked = _match_button(ctx.inbound, rows)
        return ("branch", picked if picked is not None else "fallback")
    out_sections = [{"title": s.get("title", "")[:24],
                     "rows": [{"id": r.get("id"), "title": r.get("title", "")[:24],
                               "description": r.get("description", "")[:72]}
                              for r in s.get("rows", [])]}
                    for s in sections]
    ctx.send(list={"body": _render(_d(node, "message", ""), ctx),
                   "button": _d(node, "list_button", "Choose"),
                   "sections": out_sections})
    return ("wait", node["id"])


def h_poll(node, ctx: Ctx):
    """Native WhatsApp poll (interactive type=poll). Options branch like buttons on reply id."""
    options = _d(node, "options") or []
    if ctx.consume:
        picked = _match_button(ctx.inbound, options)
        return ("branch", picked if picked is not None else "fallback")
    ctx.send(poll={"body": _render(_d(node, "message", ""), ctx),
                   "options": [{"id": o.get("id"), "title": o.get("title", "")[:60]}
                               for o in options],
                   "multiple": bool(_d(node, "multiple"))})
    return ("wait", node["id"])


def h_input(node, ctx: Ctx):
    store = _d(node, "store_as")
    if ctx.consume:
        if _valid(ctx.inbound, node):
            if store:
                ctx.vars[store] = ctx.inbound
            return ("next",)
        err = _d(node, "validation_error") or "Sorry, that doesn't look right. Please try again."
        ctx.send(text=err)
        return ("wait", node["id"])
    ctx.send(text=_render(_d(node, "message", "Please reply."), ctx))
    return ("wait", node["id"])


def h_condition(node, ctx: Ctx):
    """Legacy single-expression condition. Still supported; prefer `condition_router`."""
    expr = _d(node, "expression", "")
    locals_ = {"vars": ctx.vars, "message": ctx.inbound, "contact": ctx.contact,
               **ctx.builtins, **ctx.vars}
    try:
        result = bool(frappe.safe_eval(expr, eval_locals=locals_))
    except Exception:
        result = False
    return ("branch", "true" if result else "false")


def h_condition_router(node, ctx: Ctx):
    """Polyg-style multi-condition router.

    `conditions` is an ordered list of rows: {id, variable, match, value, case_sensitive}.
    `match` ∈ Exact Match | Contains | Regex. The first matching row's `id` becomes the
    branch handle; nothing matched → `default`.
    """
    scope = {"message": ctx.inbound, "contact": ctx.contact,
             **ctx.builtins, **ctx.vars}
    for row in _d(node, "conditions", []) or []:
        var_expr = row.get("variable") or "senderMessage"
        # resolve the variable: a bare name is looked up in scope; otherwise rendered as a token
        value = scope.get(var_expr)
        if value is None:
            value = _render("{{ %s }}" % var_expr, ctx)
        target = str(_render(str(row.get("value", "")), ctx))
        actual = str(value or "")
        if not row.get("case_sensitive"):
            actual_cmp, target_cmp = actual.lower(), target.lower()
        else:
            actual_cmp, target_cmp = actual, target
        match = (row.get("match") or "Exact Match")
        hit = False
        if match == "Exact Match":
            hit = actual_cmp == target_cmp
        elif match == "Contains":
            hit = target_cmp in actual_cmp
        elif match == "Regex":
            try:
                hit = bool(re.search(target, actual, 0 if row.get("case_sensitive") else re.I))
            except re.error:
                hit = False
        if hit:
            return ("branch", row.get("id") or "match")
    return ("branch", "default")


def h_set_variable(node, ctx: Ctx):
    for a in _d(node, "assignments", []) or []:
        name = a.get("name")
        if name:
            ctx.vars[name] = _render(str(a.get("value", "")), ctx)
    return ("next",)


def h_api_call(node, ctx: Ctx):
    from whatsapp_flow.wa_core import ssrf
    from frappe.integrations.utils import make_get_request, make_post_request

    url = _render(_d(node, "url", ""), ctx)
    try:
        ssrf.validate(url)
        method = (_d(node, "method") or "GET").upper()
        if method == "POST":
            body = _d(node, "body") or {}
            resp = make_post_request(url, data=json.dumps(body),
                                     headers={"Content-Type": "application/json"})
        else:
            resp = make_get_request(url)
        path = _d(node, "response_path")
        val = resp
        if path:
            for key in path.split("."):
                val = val.get(key) if isinstance(val, dict) else None
        store = _d(node, "store_as")
        if store:
            ctx.vars[store] = val
        return ("branch", "success")
    except Exception:
        return ("branch", "error")


def h_transfer(node, ctx: Ctx):
    """Hand the conversation to a human — team (User Group) or specific agent (User)."""
    try:
        t = frappe.new_doc("WhatsApp Agent Transfer")
        t.phone_number = ctx.session.get("phone_number")
        t.wd_issue = ctx.issue
        t.wd_team = _d(node, "wd_team")
        agent = _d(node, "wd_agent")
        if agent:
            t.wd_agent = agent
        t.flags.ignore_mandatory = True
        t.flags.ignore_permissions = True
        t.insert(ignore_permissions=True)
        # Pin bot off on the Issue so the human can take over.
        if ctx.issue:
            frappe.db.set_value("Issue", ctx.issue, "wd_bot_active", 0, update_modified=False)
        qm = _d(node, "queue_message")
        if qm:
            ctx.send(text=_render(qm, ctx))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph transfer failed")
    return ("end",)


def h_assign(node, ctx: Ctx):
    """Assign the conversation (Issue) to an agent (ToDo), without ending the flow."""
    try:
        if ctx.issue and _d(node, "wd_agent"):
            from frappe.desk.form.assign_to import add as assign_to
            assign_to({"assign_to": [_d(node, "wd_agent")],
                       "doctype": "Issue", "name": ctx.issue,
                       "description": _d(node, "description") or "Assigned by flow"})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph assign failed")
    return ("next",)


def h_tag(node, ctx: Ctx):
    """Legacy add-single-tag. Prefer `set_labels` for Polyg-style add+remove in one node."""
    tag = _render(_d(node, "tag", ""), ctx)
    if ctx.issue and tag:
        try:
            from frappe.desk.doctype.tag.tag import add_tag
            add_tag(tag, "Issue", ctx.issue)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph tag failed")
    return ("next",)


def h_set_labels(node, ctx: Ctx):
    """Add and/or remove labels (tags) on the Issue in one step."""
    if not ctx.issue:
        return ("next",)
    try:
        from frappe.desk.doctype.tag.tag import add_tag
        for name in _d(node, "add", []) or []:
            rendered = _render(str(name), ctx)
            if rendered:
                add_tag(rendered, "Issue", ctx.issue)
        for name in _d(node, "remove", []) or []:
            rendered = _render(str(name), ctx)
            if rendered:
                frappe.db.delete("Tag Link", {"document_type": "Issue",
                                               "document_name": ctx.issue, "tag": rendered})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph set_labels failed")
    return ("next",)


def h_note(node, ctx: Ctx):
    """Attach a Communication (type Comment) to the Issue — internal note."""
    content = _render(_d(node, "content", ""), ctx)
    if ctx.issue and content:
        try:
            c = frappe.new_doc("Comment")
            c.comment_type = "Comment"
            c.reference_doctype = "Issue"
            c.reference_name = ctx.issue
            c.content = content
            c.flags.ignore_permissions = True
            c.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph note failed")
    return ("next",)


def h_webhook(node, ctx: Ctx):
    """Fire-and-forget outbound HTTP POST — doesn't block the flow on the response."""
    from whatsapp_flow.wa_core import ssrf
    from frappe.integrations.utils import make_post_request

    url = _render(_d(node, "url", ""), ctx)
    body = _d(node, "body") or {"message": ctx.inbound, "vars": ctx.vars,
                                 "contact": ctx.contact, "issue": ctx.issue}
    try:
        ssrf.validate(url)
        make_post_request(url, data=json.dumps(body),
                          headers={"Content-Type": "application/json"})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph webhook failed")
    return ("next",)


def h_make_request(node, ctx: Ctx):
    """Polyg-style Make Request: full HTTP call with method/headers/body and optional store_as.

    Branches: `success` / `error`. Unlike api_call this exposes headers and keeps the raw
    body (not a path extraction) in `store_as`.
    """
    from whatsapp_flow.wa_core import ssrf
    from frappe.integrations.utils import make_get_request, make_post_request

    url = _render(_d(node, "url", ""), ctx)
    try:
        ssrf.validate(url)
        method = (_d(node, "method") or "GET").upper()
        headers = _d(node, "headers") or {}
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except Exception:
                headers = {}
        headers = {k: _render(str(v), ctx) for k, v in headers.items()}
        headers.setdefault("Content-Type", "application/json")
        body = _render_components(_d(node, "body") or {}, ctx)
        if method == "POST":
            resp = make_post_request(url, data=json.dumps(body), headers=headers)
        elif method == "GET":
            resp = make_get_request(url, headers=headers)
        else:
            # frappe helpers don't cover PUT/DELETE/PATCH; fall back to requests
            import requests
            resp = requests.request(method, url, headers=headers,
                                     data=json.dumps(body)).json()
        store = _d(node, "store_as")
        if store:
            ctx.vars[store] = resp
        return ("branch", "success")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph make_request failed")
        return ("branch", "error")


def h_response_saver(node, ctx: Ctx):
    """Prompt the user, wait for their reply, store it in a variable (Polyg's node)."""
    store = _d(node, "store_as") or _d(node, "variable")
    if ctx.consume:
        if store:
            ctx.vars[store] = ctx.inbound
        return ("next",)
    prompt = _render(_d(node, "message", ""), ctx)
    if prompt:
        ctx.send(text=prompt)
    return ("wait", node["id"])


def h_delay(node, ctx: Ctx):
    """Delay node — units `seconds` or `minutes`. Async enqueue in production; sync no-op here."""
    # The dispatch layer enqueues the next step after `_seconds(node)`; the sync runner
    # treats delays as pass-through so simulate/tests don't actually sleep.
    return ("next",)


def h_disable_auto_reply(node, ctx: Ctx):
    """Flip the Issue's `wd_bot_active` off (temporarily, until a human toggles it back)."""
    if ctx.issue:
        try:
            frappe.db.set_value("Issue", ctx.issue, "wd_bot_active", 0, update_modified=False)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph disable_auto_reply failed")
    return ("next",)


def h_phonebook(node, ctx: Ctx):
    """Add or remove the contact from a Phonebook (Polyg: audience list for broadcasts).

    `op` ∈ `add` | `remove`. `phonebook` is the Phonebook doc name.
    """
    if not ctx.contact.get("name"):
        return ("next",)
    pb = _render(_d(node, "phonebook", ""), ctx)
    op = (_d(node, "op") or "add").lower()
    if not pb:
        return ("next",)
    try:
        if op == "remove":
            frappe.db.delete("Phonebook Member",
                             {"phonebook": pb, "contact": ctx.contact["name"]})
        else:
            if not frappe.db.exists("Phonebook Member",
                                     {"phonebook": pb, "contact": ctx.contact["name"]}):
                m = frappe.new_doc("Phonebook Member")
                m.phonebook = pb
                m.contact = ctx.contact["name"]
                m.flags.ignore_permissions = True
                m.flags.ignore_mandatory = True
                m.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: graph phonebook failed")
    return ("next",)


def h_wa_form(node, ctx: Ctx):
    """Send a native WhatsApp Flow (form) to collect responses.

    `flow_id` is the Meta Flow id. `prefill` is a dict of {{var}}-renderable values
    passed as `flow_action_payload.data`.
    """
    prefill = _render_components(_d(node, "prefill") or {}, ctx)
    ctx.send(wa_form={
        "flow_id": _d(node, "flow_id"),
        "flow_cta": _d(node, "flow_cta", "Open form"),
        "flow_screen": _d(node, "flow_screen"),
        "body": _render(_d(node, "message", ""), ctx),
        "prefill": prefill,
    })
    return ("wait", node["id"])


def h_google(node, ctx: Ctx):
    """Google Services (Sheets/Calendar/Drive/Docs) — stub, coming soon.

    Logs the intent so the audit trail shows this ran, then no-ops forward.
    """
    frappe.log_error(f"whatsapp_flow google stub: {_d(node, 'service')} / {_d(node, 'action')}",
                     "whatsapp_flow: google stub")
    return ("next",)


def h_goto(node, ctx: Ctx):
    target_flow = _d(node, "target_flow")
    if target_flow:
        ctx.session["wd_next_flow"] = target_flow  # handled by caller
    return ("end",)


def h_timing(node, ctx: Ctx):
    # Synchronous runner: delays are a no-op here (handled by enqueue in production).
    return ("next",)


def h_stub(node, ctx: Ctx):
    # ai_response / server_script / erp — implemented in Phase 3b; pass through.
    return ("next",)


def h_end(node, ctx: Ctx):
    msg = _d(node, "completion_message")
    if msg:
        ctx.send(text=_render(msg, ctx))
    return ("end",)


HANDLERS = {
    "start": h_start, "text": h_text, "media": h_media, "buttons": h_buttons,
    "list": h_list, "poll": h_poll, "input": h_input, "condition": h_condition,
    "condition_router": h_condition_router,
    "set_variable": h_set_variable, "response_saver": h_response_saver,
    "api_call": h_api_call, "webhook": h_webhook, "make_request": h_make_request,
    "transfer": h_transfer, "assign": h_assign, "tag": h_tag, "set_labels": h_set_labels,
    "note": h_note, "disable_auto_reply": h_disable_auto_reply,
    "phonebook": h_phonebook, "wa_form": h_wa_form, "google": h_google,
    "goto": h_goto, "timing": h_timing, "delay": h_delay, "end": h_end,
    "ai_response": h_stub, "server_script": h_stub, "erp": h_stub, "whatsapp_flow": h_wa_form,
    # IVR (voice) node aliases — same engine, voice `send` maps text->TTS, buttons->DTMF menu.
    "greeting": h_text, "say": h_text, "gather": h_input, "menu": h_buttons,
    "hangup": h_end, "http_callback": h_api_call, "goto_flow": h_goto,
}


# --------------------------------------------------------------------------- utilities
def _render(text: str, ctx: Ctx) -> str:
    out = text or ""
    # Polyg's built-ins first so a user variable of the same name wins (least surprise).
    scope = {**ctx.builtins, **ctx.vars, "message": ctx.inbound}
    for k, v in scope.items():
        out = out.replace("{{ %s }}" % k, str(v)).replace("{{%s}}" % k, str(v))
    for k, v in (ctx.contact or {}).items():
        out = out.replace("{{ contact.%s }}" % k, str(v)).replace("{{contact.%s}}" % k, str(v))
    return out


def _render_components(components, ctx: Ctx):
    """Render Jinja-ish `{{ var }}` tokens inside Meta template components recursively."""
    if components is None:
        return None
    if isinstance(components, str):
        return _render(components, ctx)
    if isinstance(components, list):
        return [_render_components(c, ctx) for c in components]
    if isinstance(components, dict):
        return {k: _render_components(v, ctx) for k, v in components.items()}
    return components


def _match_button(inbound: str, buttons: list) -> str | None:
    low = (inbound or "").strip().lower()
    for b in buttons:
        if low == str(b.get("id", "")).lower() or low == str(b.get("title", "")).lower():
            return b.get("id")
    # numeric pick (1-based)
    if low.isdigit():
        i = int(low) - 1
        if 0 <= i < len(buttons):
            return buttons[i].get("id")
    return None


def _valid(value: str, node) -> bool:
    if not value:
        return False
    itype = _d(node, "input_type", "Text")
    rx = _d(node, "validation_regex")
    if rx:
        try:
            if not re.match(rx, value):
                return False
        except re.error:
            pass
    if itype == "Number":
        return value.replace(".", "", 1).isdigit()
    if itype == "Email":
        return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))
    return True


# --------------------------------------------------------------------------- run
def run(flow_name, phone, account, inbound, issue=None, send=None, session=None, graph=None,
        contact=None):
    """Advance the graph for one inbound. Returns the node path walked (trace).

    `graph` overrides the published graph (used by the dry-run simulator on the draft).
    """
    flow = frappe.get_doc("WhatsApp Chatbot Flow", flow_name)
    if graph is None:
        graph = json.loads(flow.get("wd_published_json") or "{}")
    if not graph.get("nodes"):
        return []

    sess = session if session is not None else _get_session(phone, account, flow_name)
    ctx = Ctx(flow, graph, sess, inbound, send or _make_default_send(phone, account), issue,
              contact or {})

    node_id = sess.get("wd_current_node") or _start_node(ctx)
    ctx.consume = bool(sess.get("wd_current_node"))  # resuming into a parked node
    trace, steps = [], 0
    while node_id and steps < MAX_STEPS:
        steps += 1
        node = ctx.nodes.get(node_id)
        if not node:
            break
        trace.append(node_id)
        directive = HANDLERS.get(node["type"], h_stub)(node, ctx)
        ctx.consume = False  # only the first (parked) node consumes the inbound
        kind = directive[0]
        if kind == "wait":
            sess["wd_current_node"] = directive[1]
            node_id = None
        elif kind == "branch":
            node_id = _follow(ctx, node["id"], directive[1])
        elif kind == "goto":
            node_id = directive[1]
        elif kind == "end":
            sess["wd_current_node"] = None
            sess["status"] = "Completed"
            node_id = None
        else:  # next
            node_id = _follow(ctx, node["id"], None)

    sess["wd_graph_vars"] = json.dumps(ctx.vars)
    _persist(sess)
    return trace


def _get_session(phone, account, flow_name) -> dict:
    name = frappe.db.get_value(
        "WhatsApp Chatbot Session",
        {"phone_number": phone, "current_flow": flow_name, "status": "Active"},
    )
    if name:
        doc = frappe.get_doc("WhatsApp Chatbot Session", name)
    else:
        doc = frappe.new_doc("WhatsApp Chatbot Session")
        doc.phone_number = phone
        doc.whatsapp_account = account
        doc.current_flow = flow_name
        doc.status = "Active"
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
    return doc.as_dict()


def _persist(sess: dict) -> None:
    name = sess.get("name")
    if not name:
        return
    frappe.db.set_value(
        "WhatsApp Chatbot Session", name,
        {"wd_current_node": sess.get("wd_current_node"),
         "wd_graph_vars": sess.get("wd_graph_vars"),
         "status": sess.get("status") or "Active"},
        update_modified=False,
    )


def _make_default_send(phone, account):
    def send(text=None, buttons=None, template=None, template_components=None,
             template_language="en", list=None, poll=None, media=None, wa_form=None):
        """Build a WhatsApp Message doc, attaching a Meta Cloud API payload on `wd_meta_payload`
        for shapes `content_type` alone can't express (interactive list/poll, media caption,
        template components). Simple text/buttons use upstream fields directly.
        """
        doc = {"doctype": "WhatsApp Message", "type": "Outgoing", "to": phone,
               "whatsapp_account": account}
        meta = None
        if template:
            doc.update({"message_type": "Template", "template": template,
                        "content_type": "text"})
            if template_components:
                meta = _meta_template(template, template_language, template_components)
        elif list:
            doc.update({"content_type": "interactive", "message": list.get("body", "")})
            meta = _meta_list(phone, list)
        elif poll:
            doc.update({"content_type": "interactive", "message": poll.get("body", "")})
            meta = _meta_poll(phone, poll)
        elif media:
            doc.update({"content_type": media.get("type", "image"),
                        "message": media.get("caption", ""),
                        "media_url": media.get("link")})
            meta = _meta_media(phone, media)
        elif wa_form:
            doc.update({"content_type": "interactive", "message": wa_form.get("body", "")})
            meta = _meta_wa_form(phone, wa_form)
        elif buttons:
            body = buttons.get("body", "")
            doc.update({"content_type": "interactive", "message": body,
                        "buttons": json.dumps(buttons.get("buttons", []))})
            meta = _meta_buttons(phone, body, buttons.get("buttons", []))
        else:
            doc.update({"content_type": "text", "message": text or ""})
        if meta is not None:
            doc["wd_meta_payload"] = json.dumps(meta)
        d = frappe.get_doc(doc)
        d.flags.ignore_chatbot = True
        d.insert(ignore_permissions=True)
    return send


# --------------------------------------------------------------------------- Meta payload builders
def _meta_buttons(to, body, buttons):
    return {"messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {"type": "button", "body": {"text": body},
                             "action": {"buttons": [{"type": "reply",
                                                      "reply": {"id": b.get("id"),
                                                                "title": b.get("title", "")[:20]}}
                                                     for b in buttons]}}}


def _meta_list(to, lst):
    return {"messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {"type": "list", "body": {"text": lst.get("body", "")},
                             "action": {"button": lst.get("button", "Choose")[:20],
                                         "sections": lst.get("sections", [])}}}


def _meta_poll(to, poll):
    # Meta's native poll shape (available on interactive type=poll on supported tiers).
    return {"messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {"type": "poll",
                             "body": {"text": poll.get("body", "")},
                             "action": {"name": "poll",
                                         "allow_multiple_answers": bool(poll.get("multiple")),
                                         "options": [{"name": o.get("title", "")}
                                                     for o in poll.get("options", [])]}}}


def _meta_media(to, m):
    kind = (m.get("type") or "image").lower()
    body = {"link": m.get("link")}
    if m.get("caption") and kind in ("image", "video", "document"):
        body["caption"] = m["caption"]
    if m.get("filename") and kind == "document":
        body["filename"] = m["filename"]
    return {"messaging_product": "whatsapp", "to": to, "type": kind, kind: body}


def _meta_template(name, language, components):
    return {"messaging_product": "whatsapp", "type": "template",
            "template": {"name": name, "language": {"code": language or "en"},
                          "components": components or []}}


def _meta_wa_form(to, form):
    """Interactive type=flow — the Meta WhatsApp Flows (form) shape."""
    action = {"name": "flow",
              "parameters": {"flow_id": form.get("flow_id"),
                              "flow_cta": (form.get("flow_cta") or "Open form")[:20],
                              "flow_action": "navigate",
                              "flow_message_version": "3",
                              "mode": "published"}}
    if form.get("flow_screen"):
        action["parameters"]["flow_action_payload"] = {
            "screen": form["flow_screen"],
            "data": form.get("prefill") or {},
        }
    return {"messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {"type": "flow",
                             "body": {"text": form.get("body", "")},
                             "action": action}}


# --------------------------------------------------------------------------- dispatch
def maybe_run_graph(message_data: dict) -> bool:
    """Entry from the patched ChatbotProcessor.process. Returns True if a Graph flow handled it."""
    try:
        phone = message_data.get("from")
        account = message_data.get("whatsapp_account")
        text = (message_data.get("message") or "").strip()
        if not phone:
            return False

        # Resume an active graph session?
        sess = frappe.db.get_value(
            "WhatsApp Chatbot Session",
            {"phone_number": phone, "status": "Active", "wd_current_node": ["is", "set"]},
            ["name", "current_flow"], as_dict=True,
        )
        if sess and frappe.db.get_value("WhatsApp Chatbot Flow", sess.current_flow, "wd_mode") == "Graph":
            _run_dispatch(sess.current_flow, phone, account, text)
            return True

        # Otherwise start a Graph flow whose trigger keyword matches.
        flows = frappe.get_all(
            "WhatsApp Chatbot Flow",
            filters={"wd_mode": "Graph", "wd_published": 1, "enabled": 1},
            fields=["name", "trigger_keywords"],
        )
        low = text.lower()
        for f in flows:
            kws = [k.strip().lower() for k in (f.trigger_keywords or "").split(",") if k.strip()]
            if not kws or low in kws:
                _run_dispatch(f.name, phone, account, text)
                return True
        return False
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: maybe_run_graph failed")
        return False


def _run_dispatch(flow_name, phone, account, text):
    contact_doc = frappe.db.get_value(
        "WhatsApp Contact", {"mobile_no": phone},
        ["name", "wd_open_issue", "wd_team", "first_name", "last_name", "email", "mobile_no"],
        as_dict=True,
    ) or {}
    issue = contact_doc.get("wd_open_issue")
    run(flow_name, phone, account, text, issue=issue, contact=dict(contact_doc))
