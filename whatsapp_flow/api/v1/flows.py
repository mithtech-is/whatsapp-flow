"""Flow builder API (flow-builder-spec §6): save draft, validate, publish, simulate."""

from __future__ import annotations

import json

import frappe
from frappe import _

from whatsapp_flow.endpoints.chat import _is_manager
from whatsapp_flow.wa_bot import graph_runner

TERMINAL = {"end", "goto", "transfer", "hangup", "goto_flow"}
BRANCHING = {
    "condition": ["true", "false"],
    "api_call": ["success", "error"],
    "http_callback": ["success", "error"],
    "make_request": ["success", "error"],
    "ai_response": ["continue", "handoff"],
}
# Interactive nodes whose outputs depend on the user-defined options table — validated
# dynamically from node.data rather than a static list.
INTERACTIVE_OPTIONED = {"buttons", "menu", "list", "poll"}


def _guard():
    if not _is_manager():
        raise frappe.PermissionError(_("Managers only."))


@frappe.whitelist()
def list_flows():
    return frappe.get_all(
        "WhatsApp Chatbot Flow",
        fields=["name", "flow_name", "wd_mode", "wd_published", "wd_version", "enabled"],
        order_by="modified desc",
    )


@frappe.whitelist()
def create_flow(flow_name: str):
    _guard()
    doc = frappe.new_doc("WhatsApp Chatbot Flow")
    doc.flow_name = flow_name
    doc.enabled = 1
    doc.wd_mode = "Graph"
    doc.wd_graph_json = json.dumps({"version": 1, "nodes": [
        {"id": "start", "type": "start", "position": {"x": 80, "y": 80}, "data": {"label": "Start"}}
    ], "edges": []})
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return {"flow": doc.name}


@frappe.whitelist()
def get_graph(flow: str):
    doc = frappe.get_doc("WhatsApp Chatbot Flow", flow)
    return {
        "flow": doc.name,
        "mode": doc.get("wd_mode"),
        "graph": json.loads(doc.get("wd_graph_json") or "{}"),
        "published": doc.get("wd_published"),
        "version": doc.get("wd_version"),
    }


@frappe.whitelist()
def save_graph(flow: str, graph):
    _guard()
    if isinstance(graph, str):
        graph = json.loads(graph)
    doc = frappe.get_doc("WhatsApp Chatbot Flow", flow)
    doc.wd_mode = "Graph"
    doc.wd_graph_json = json.dumps(graph)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    return {"ok": True}


def validate_graph(graph: dict) -> list[str]:
    errors = []
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    starts = [n for n in nodes.values() if n.get("type") == "start"]
    if len(starts) != 1:
        errors.append(f"Graph must have exactly one start node (found {len(starts)}).")

    # edges reference existing nodes
    for e in edges:
        if e.get("source") not in nodes:
            errors.append(f"Edge from unknown node {e.get('source')}.")
        if e.get("target") not in nodes:
            errors.append(f"Edge to unknown node {e.get('target')}.")

    out_by = {}
    for e in edges:
        out_by.setdefault(e.get("source"), set()).add(e.get("sourceHandle") or None)

    for nid, n in nodes.items():
        ntype = n.get("type")
        if ntype in TERMINAL:
            continue
        if nid not in out_by:
            errors.append(f"Node '{_label(n)}' has no outgoing connection.")
            continue
        for handle in BRANCHING.get(ntype, []):
            if handle not in out_by.get(nid, set()):
                errors.append(f"Node '{_label(n)}' is missing its '{handle}' branch.")
        if ntype == "condition_router":
            # the `default` handle is always expected; each condition row must be connected.
            if "default" not in out_by.get(nid, set()):
                errors.append(f"Node '{_label(n)}' is missing its 'default' branch.")
            for row in (n.get("data") or {}).get("conditions") or []:
                rid = row.get("id")
                if rid and rid not in out_by.get(nid, set()):
                    errors.append(f"Node '{_label(n)}' condition '{rid}' is not connected.")
        if ntype in INTERACTIVE_OPTIONED:
            data = n.get("data") or {}
            if ntype == "list":
                rows = [r for s in (data.get("sections") or []) for r in s.get("rows", [])]
            elif ntype == "poll":
                rows = data.get("options") or []
            else:
                rows = data.get("buttons") or []
            seen = set()
            for r in rows:
                rid = r.get("id")
                if not rid:
                    errors.append(f"Node '{_label(n)}' has an option without an id.")
                elif rid in seen:
                    errors.append(f"Node '{_label(n)}' has duplicate option id '{rid}'.")
                seen.add(rid)
            if not rows:
                errors.append(f"Node '{_label(n)}' needs at least one option.")

    # reachability from start
    if starts:
        reachable, stack = set(), [starts[0]["id"]]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for e in edges:
                if e.get("source") == cur and e.get("target") in nodes:
                    stack.append(e["target"])
        for nid, n in nodes.items():
            if nid not in reachable:
                errors.append(f"Node '{_label(n)}' is unreachable from start.")
    return errors


def _label(n: dict) -> str:
    return n.get("data", {}).get("label") or n.get("type") or n.get("id")


@frappe.whitelist()
def publish(flow: str):
    _guard()
    doc = frappe.get_doc("WhatsApp Chatbot Flow", flow)
    graph = json.loads(doc.get("wd_graph_json") or "{}")
    errors = validate_graph(graph)
    if errors:
        return {"ok": False, "errors": errors}
    doc.wd_mode = "Graph"
    doc.wd_published_json = json.dumps(graph)
    doc.wd_version = (doc.get("wd_version") or 0) + 1
    doc.wd_published = 1
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    return {"ok": True, "version": doc.wd_version}


@frappe.whitelist()
def simulate(flow: str, inbound: str, session_state=None):
    """Dry-run the DRAFT graph. Pass back the returned session to continue the conversation."""
    _guard()
    if isinstance(session_state, str):
        session_state = json.loads(session_state) if session_state else None
    graph = json.loads(frappe.get_doc("WhatsApp Chatbot Flow", flow).get("wd_graph_json") or "{}")
    out = []

    def send(text=None, buttons=None, template=None, template_components=None,
             template_language="en", list=None, poll=None, media=None, wa_form=None):
        out.append({"text": text, "buttons": buttons, "template": template,
                    "template_components": template_components,
                    "template_language": template_language,
                    "list": list, "poll": poll, "media": media, "wa_form": wa_form})

    sess = session_state or {"wd_current_node": None, "wd_graph_vars": "{}", "status": "Active"}
    trace = graph_runner.run(flow, "SIMULATE", None, inbound, send=send, session=sess, graph=graph)
    return {
        "trace": trace,
        "outbound": out,
        "session": {"wd_current_node": sess.get("wd_current_node"),
                    "wd_graph_vars": sess.get("wd_graph_vars"), "status": sess.get("status")},
        "vars": json.loads(sess.get("wd_graph_vars") or "{}"),
    }
