"""Manual end-to-end smoke tests (run on a bench, not part of the unit suite).

    bench --site <site> execute whatsapp_flow.tests.e2e_manual.run
    bench --site <site> execute whatsapp_flow.tests.e2e_manual.run_inbox
    bench --site <site> execute whatsapp_flow.tests.e2e_manual.run_assignment
    bench --site <site> execute whatsapp_flow.tests.e2e_manual.run_diag

Each exercises real behaviour against the live DB, then rolls back so no test data persists.
"""

import frappe

from whatsapp_flow.wa_core import guard

NUM = "99999000001"
NUM2 = "99999000002"


def _out(m):
    print("R::", m, flush=True)


def _ensure_account():
    if not frappe.db.exists("WhatsApp Account", "WD E2E"):
        acc = frappe.new_doc("WhatsApp Account")
        acc.update({"account_name": "WD E2E", "token": "x", "url": "https://graph.facebook.com",
                    "version": "v21.0", "phone_id": "PID", "business_id": "BID", "app_id": "AID",
                    "webhook_verify_token": "vt", "is_default_incoming": 1, "is_default_outgoing": 1})
        acc.wd_app_secret = "sekret"
        acc.flags.ignore_mandatory = True
        acc.insert(ignore_permissions=True)
    return "WD E2E"


def _ensure_contact():
    if not frappe.db.exists("WhatsApp Contact", {"mobile_no": NUM}):
        c = frappe.new_doc("WhatsApp Contact")
        c.update({"contact_name": "E2E Tester", "mobile_no": NUM})
        c.flags.ignore_mandatory = True
        c.insert(ignore_permissions=True)
    return frappe.db.get_value("WhatsApp Contact", {"mobile_no": NUM})


def _inbound(acc, msgid, text="hello"):
    m = frappe.new_doc("WhatsApp Message")
    m.update({"type": "Incoming", "from": NUM, "message": text, "content_type": "text",
              "message_id": msgid, "whatsapp_account": acc})
    m.flags.ignore_permissions = True
    m.insert(ignore_permissions=True)
    return m


def run():
    """Core: inbound->Issue, STOP opt-out, send-guard window + opt-out blocks."""
    try:
        acc = _ensure_account()
        contact_name = _ensure_contact()

        m = _inbound(acc, "wamid.E2E.A", "hello there")
        c = frappe.get_doc("WhatsApp Contact", contact_name)
        issue = c.get("wd_open_issue")
        m2 = frappe.get_doc("WhatsApp Message", m.name)
        _out(f"A inbound: issue_opened={bool(issue)} msg_linked={m2.get('wd_issue') == issue} "
             f"window_set={bool(c.get('wd_window_expires_at'))} unread={c.get('wd_unread_count')}")
        if issue:
            idoc = frappe.get_doc("Issue", issue)
            _out(f"A issue: contact_set={idoc.get('wd_whatsapp_contact') == contact_name} "
                 f"source={idoc.get('wd_source')} status={idoc.status}")

        _inbound(acc, "wamid.E2E.B", "STOP")
        c = frappe.get_doc("WhatsApp Contact", contact_name)
        _out(f"B stop-optout: opt_out={c.get('wd_marketing_opt_out')} source={c.get('wd_opt_out_source')}")

        try:
            og = frappe.new_doc("WhatsApp Message")
            og.update({"type": "Outgoing", "to": NUM2, "message": "blocked?", "content_type": "text",
                       "whatsapp_account": acc})
            og.flags.ignore_permissions = True
            og.insert(ignore_permissions=True)
            res = "NOT BLOCKED (would have sent!)"
        except guard.WindowClosedError:
            res = "WindowClosedError (correct)"
        except Exception as e:  # noqa: BLE001
            res = f"other:{type(e).__name__}:{e}"
        _out(f"C closed-window-send: {res}")

        try:
            od = frappe.new_doc("WhatsApp Message")
            od.update({"type": "Outgoing", "to": NUM, "message_type": "Template", "message": "promo",
                       "content_type": "text", "whatsapp_account": acc})
            od.flags.ignore_permissions = True
            od.insert(ignore_permissions=True)
            res = "NOT BLOCKED (would have sent!)"
        except guard.OptedOutError:
            res = "OptedOutError (correct)"
        except Exception as e:  # noqa: BLE001
            res = f"other:{type(e).__name__}:{e}"
        _out(f"D optout-template-send: {res}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_assignment():
    """Teams (User Group) + presence + bot->human handoff + manual assignment."""
    from whatsapp_flow.api.v1 import agents
    from whatsapp_flow.wa_desk import assignment, teams

    TEAM = "WD Team E2E"
    AGENT = "Administrator"
    try:
        acc = _ensure_account()
        if not frappe.db.exists("User Group", TEAM):
            g = frappe.new_doc("User Group")
            g.name = TEAM
            g.append("user_group_members", {"user": AGENT})
            g.flags.ignore_permissions = True
            g.insert(ignore_permissions=True)
        frappe.db.set_value("User", AGENT, "wd_wa_availability", "Online", update_modified=False)
        _out(f"teams: online_agents={teams.online_agents(TEAM)} pick={teams.pick_agent(TEAM)}")

        contact_name = _ensure_contact()
        frappe.db.set_value("WhatsApp Contact", contact_name, "wd_team", TEAM, update_modified=False)
        _inbound(acc, "wamid.ASSIGN.A", "need a human")
        issue = frappe.db.get_value("WhatsApp Contact", contact_name, "wd_open_issue")

        frappe.flags.wd_debug_handoff = True
        t = frappe.new_doc("WhatsApp Agent Transfer")
        t.update({"phone_number": NUM, "wd_issue": issue, "wd_team": TEAM})
        t.flags.ignore_mandatory = True
        t.flags.ignore_permissions = True
        t.insert(ignore_permissions=True)
        t.reload()
        c = frappe.get_doc("WhatsApp Contact", contact_name)
        todo = frappe.get_all("ToDo", filters={"reference_type": "Issue", "reference_name": issue,
                                               "allocated_to": AGENT, "status": "Open"})
        _out(f"handoff: bot_active={c.get('wd_bot_active')} assignee={c.get('email')} "
             f"queue_status={t.get('wd_queue_status')} picked_up_by={t.get('wd_picked_up_by')} "
             f"todo_created={bool(todo)}")

        agents.set_availability("Away")
        _out(f"after set_availability(Away): online={teams.online_agents(TEAM)}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_inbox():
    """Inbox API smoke test."""
    from whatsapp_flow.api.v1 import inbox

    try:
        acc = _ensure_account()
        contact_name = _ensure_contact()
        _inbound(acc, "wamid.INBOX.A", "inbox hi")

        convs = inbox.list_conversations(status="Open")
        mine = [r for r in convs if r["contact"] == contact_name]
        _out(f"inbox list_conversations: total={len(convs)} has_test_contact={bool(mine)}")
        if mine:
            r = mine[0]
            _out(f"inbox row: name={r['contact_name']} number={r['number']} status={r['status']} "
                 f"unread={r['unread']} window_open={r['window_open']} issue={bool(r['issue'])}")
        msgs = inbox.get_messages(contact_name)
        _out(f"inbox get_messages: count={len(msgs)}")
        det = inbox.get_contact(contact_name)
        _out(f"inbox get_contact: name={det['contact_name']} issue_status={(det.get('issue') or {}).get('status')}")
        _out(f"inbox counts: {inbox.counts()}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_tools():
    """Notes (Comment) + canned responses + tags."""
    from whatsapp_flow.api.v1 import tools

    try:
        acc = _ensure_account()
        contact_name = _ensure_contact()
        _inbound(acc, "wamid.TOOLS.A", "hi tools")

        note = tools.add_note(contact_name, "Called customer, will follow up.")
        notes = tools.list_notes(contact_name)
        _out(f"notes: added={bool(note)} count={len(notes)} first={notes[0]['content'][:20] if notes else None!r}")

        if not frappe.db.exists("WA Canned Response", {"shortcut": "/hi"}):
            cr = frappe.new_doc("WA Canned Response")
            cr.update({"title": "Greeting", "shortcut": "/hi", "message": "Hello {{ contact_name }}!"})
            cr.flags.ignore_permissions = True
            cr.insert(ignore_permissions=True)
        canned = tools.list_canned()
        rendered = tools.render_canned(contact_name, "/hi")
        _out(f"canned: list={len(canned)} rendered={rendered['message']!r}")

        tools.add_tag(contact_name, "vip")
        tags1 = tools.list_tags(contact_name)
        tools.remove_tag(contact_name, "vip")
        tags2 = tools.list_tags(contact_name)
        _out(f"tags: after_add={tags1} after_remove={tags2}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_phase1_extra():
    """Templates list + custom actions (URL + SSRF-blocked webhook) + realtime publish."""
    from whatsapp_flow.api.v1 import actions, inbox

    try:
        acc = _ensure_account()
        contact_name = _ensure_contact()

        # realtime: capture publish_realtime while an inbound arrives
        captured = []
        orig = frappe.publish_realtime
        frappe.publish_realtime = lambda *a, **k: captured.append((a[0] if a else k.get("event")))
        try:
            _inbound(acc, "wamid.RT.A", "ping")
        finally:
            frappe.publish_realtime = orig
        _out(f"realtime: published={'whatsapp_flow:update' in captured} events={captured}")

        _out(f"templates: list={len(inbox.list_templates())}")

        # custom action: URL type
        if not frappe.db.exists("WA Custom Action", {"title": "Open CRM"}):
            a = frappe.new_doc("WA Custom Action")
            a.update({"title": "Open CRM", "action_type": "URL",
                      "url": "https://example.com/c/{{ number }}", "open_in_new_tab": 1})
            a.flags.ignore_permissions = True
            a.insert(ignore_permissions=True)
        acts = actions.list_actions()
        url_action = next(a for a in acts if a["title"] == "Open CRM")
        res = actions.execute_action(url_action["name"], contact_name)
        _out(f"custom-action URL: list={len(acts)} resolved={res.get('url')}")

        # custom action: Webhook to a private addr must be SSRF-blocked
        if not frappe.db.exists("WA Custom Action", {"title": "Bad Hook"}):
            b = frappe.new_doc("WA Custom Action")
            b.update({"title": "Bad Hook", "action_type": "Webhook",
                      "url": "http://127.0.0.1:99/x", "http_method": "POST"})
            b.flags.ignore_permissions = True
            b.insert(ignore_permissions=True)
        bad = frappe.db.get_value("WA Custom Action", {"title": "Bad Hook"})
        try:
            actions.execute_action(bad, contact_name)
            ssrf_res = "NOT BLOCKED"
        except frappe.ValidationError:
            ssrf_res = "blocked (correct)"
        except Exception as e:  # noqa: BLE001
            ssrf_res = f"other:{type(e).__name__}"
        _out(f"custom-action SSRF: {ssrf_res}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_sla():
    """SLA applied to WhatsApp Issue (native) + escalation ladder tick."""
    from whatsapp_flow.setup import sla as sla_setup
    from whatsapp_flow.wa_desk import sla as sla_engine
    from frappe.utils import add_to_date, now_datetime

    AGENT = "Administrator"
    try:
        sla_setup.ensure_default_sla()
        sla_name = frappe.db.get_value("Service Level Agreement", {"service_level": sla_setup.SLA_NAME})
        # add one escalation level (Reassign to Administrator, fires 0 min after response due)
        s = frappe.get_doc("Service Level Agreement", sla_name)
        s.append("wd_escalation_levels", {"level": 1, "basis": "Response",
                                          "minutes_after_due": 0, "action": "Reassign",
                                          "escalate_to": AGENT})
        s.flags.ignore_permissions = True
        s.save(ignore_permissions=True)
        _out(f"sla: created={sla_setup.SLA_NAME} escalation_levels={len(s.wd_escalation_levels)}")

        acc = _ensure_account()
        contact_name = _ensure_contact()
        _inbound(acc, "wamid.SLA.A", "sla please")
        issue = frappe.db.get_value("WhatsApp Contact", contact_name, "wd_open_issue")
        idoc = frappe.db.get_value("Issue", issue,
                                   ["agreement_status", "response_by", "service_level_agreement"],
                                   as_dict=True)
        _out(f"sla applied: agreement_status={idoc.agreement_status} "
             f"has_response_by={bool(idoc.response_by)} sla={idoc.service_level_agreement}")

        # force the response due time into the past, then tick
        frappe.db.set_value("Issue", issue,
                            {"response_by": add_to_date(now_datetime(), minutes=-5),
                             "first_responded_on": None, "wd_escalation_level": 0},
                            update_modified=False)
        sla_engine.tick()
        lvl = frappe.db.get_value("Issue", issue, "wd_escalation_level")
        todo = frappe.get_all("ToDo", filters={"reference_type": "Issue", "reference_name": issue,
                                               "allocated_to": AGENT, "status": "Open"})
        _out(f"escalation tick: level_now={lvl} reassigned_todo={bool(todo)}")

        sla_engine.auto_close()  # just ensure no error
        _out("auto_close: ran ok")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_campaigns():
    """WA Segment resolve/build + Bulk pause/opt-out skip."""
    from whatsapp_flow.wa_campaign import segments

    try:
        _ensure_account()
        contact_name = _ensure_contact()  # E2E Tester / NUM, not opted out

        # segment over WhatsApp Contact
        if not frappe.db.exists("WA Segment", "E2E Segment"):
            seg = frappe.new_doc("WA Segment")
            seg.update({"title": "E2E Segment", "source_doctype": "WhatsApp Contact",
                        "mobile_field": "mobile_no", "name_field": "contact_name",
                        "filters": '{"contact_name": "E2E Tester"}'})
            seg.flags.ignore_permissions = True
            seg.insert(ignore_permissions=True)
        resolved = segments.resolve("E2E Segment")
        built = segments.build_recipient_list("E2E Segment")
        _out(f"segment: resolved={len(resolved)} first={resolved[0]['mobile_number'] if resolved else None} "
             f"recipient_list_count={built['count']}")

        # bulk controls
        b = frappe.new_doc("Bulk WhatsApp Message")
        b.update({"title": "E2E Campaign", "recipient_type": "Individual",
                  "message_content": "hi", "wd_respect_opt_out": 1})
        b.append("recipients", {"mobile_number": NUM})
        b.flags.ignore_permissions = True
        b.insert(ignore_permissions=True)

        # opt-out skip: mark contact opted out, then create_single_message should skip
        frappe.db.set_value("WhatsApp Contact", contact_name, "wd_marketing_opt_out", 1, update_modified=False)
        b.create_single_message({"mobile_number": NUM, "recipient_data": "{}"})
        msg_for_num = frappe.db.exists("WhatsApp Message", {"to": NUM, "bulk_message_reference": b.name})
        _out(f"bulk opt-out skip: skipped_count={b.get('wd_skipped_count')} message_created={bool(msg_for_num)}")

        # pause: create_single_message should no-op
        b.wd_pause()
        before = frappe.db.count("WhatsApp Message", {"bulk_message_reference": b.name})
        b.create_single_message({"mobile_number": "88888000000", "recipient_data": "{}"})
        after = frappe.db.count("WhatsApp Message", {"bulk_message_reference": b.name})
        _out(f"bulk pause: status={frappe.db.get_value('Bulk WhatsApp Message', b.name, 'status')} "
             f"created_while_paused={after - before}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def _build_graph():
    def node(nid, ntype, **data):
        return {"id": nid, "type": ntype, "position": {"x": 0, "y": 0}, "data": data}

    def edge(s, t, handle=None):
        return {"id": f"{s}-{t}-{handle or ''}", "source": s, "target": t, "sourceHandle": handle}

    nodes = [
        node("start", "start", initial_message="Hi!"),
        node("q_name", "input", input_type="Text", store_as="name", message="What's your name?"),
        node("thanks", "text", message="Thanks {{ name }}"),
        node("pick", "buttons", message="Pick", buttons=[{"id": "a", "title": "Sales"},
                                                         {"id": "b", "title": "Support"}]),
        node("sales", "text", message="Sales it is"),
        node("xfer", "transfer"),
        node("fb", "text", message="Didn't get that"),
        node("e1", "end", completion_message="Bye"),
        node("fbend", "end"),
    ]
    edges = [
        edge("start", "q_name"),
        edge("q_name", "thanks"),
        edge("thanks", "pick"),
        edge("pick", "sales", "a"),
        edge("pick", "xfer", "b"),
        edge("pick", "fb", "fallback"),
        edge("sales", "e1"),
        edge("fb", "fbend"),
    ]
    return {"version": 1, "nodes": nodes, "edges": edges}


def run_graph():
    """Graph builder: validate + publish + multi-step simulate."""
    from whatsapp_flow.api.v1 import flows
    import json as _json

    FLOW = "E2E Graph Flow"
    try:
        if not frappe.db.exists("WhatsApp Chatbot Flow", FLOW):
            f = frappe.new_doc("WhatsApp Chatbot Flow")
            f.flow_name = FLOW
            f.enabled = 1
            f.wd_mode = "Graph"
            f.flags.ignore_mandatory = True
            f.insert(ignore_permissions=True)

        flows.save_graph(FLOW, _build_graph())
        res = flows.publish(FLOW)
        _out(f"publish: ok={res.get('ok')} version={res.get('version')} errors={res.get('errors')}")

        # bad graph (no start) rejected
        bad = flows.validate_graph({"nodes": [{"id": "x", "type": "text", "data": {}}], "edges": []})
        _out(f"validate bad graph errors={len(bad)} sample={bad[0] if bad else None!r}")

        # multi-step simulate (session passed back between turns)
        r1 = flows.simulate(FLOW, "hi")
        _out(f"turn1 trace={r1['trace']} out={[o['text'] or 'buttons' for o in r1['outbound']]} "
             f"parked={r1['session']['wd_current_node']}")
        r2 = flows.simulate(FLOW, "Alice", session_state=r1["session"])
        _out(f"turn2 out={[o['text'] or '[buttons]' for o in r2['outbound']]} "
             f"vars={r2['vars']} parked={r2['session']['wd_current_node']}")
        r3 = flows.simulate(FLOW, "a", session_state=r2["session"])
        _out(f"turn3 trace={r3['trace']} out={[o['text'] for o in r3['outbound']]} "
             f"status={r3['session']['status']}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_voice():
    """Phase 6: calls webhook -> Call Log + ring routing, consent, bridge no-op, IVR simulate."""
    from whatsapp_flow.wa_voice import calls, bridge
    from whatsapp_flow.api.v1 import voice, flows
    import json as _json

    TEAM = "WD Team E2E"
    try:
        _ensure_account()  # phone_id PID
        if not frappe.db.exists("User Group", TEAM):
            g = frappe.new_doc("User Group"); g.name = TEAM
            g.append("user_group_members", {"user": "Administrator"})
            g.flags.ignore_permissions = True; g.insert(ignore_permissions=True)
        frappe.db.set_value("User", "Administrator", "wd_wa_availability", "Online", update_modified=False)
        contact = _ensure_contact()
        frappe.db.set_value("WhatsApp Contact", contact, "wd_team", TEAM, update_modified=False)

        # inbound calls webhook -> Call Log + ring rotation
        value = {"metadata": {"phone_number_id": "PID"},
                 "calls": [{"id": "CALL-E2E-1", "from": NUM, "direction": "inbound", "status": "ringing"}]}
        calls.on_calls_webhook(value)
        cl = frappe.db.get_value("Call Log", {"wd_meta_call_id": "CALL-E2E-1"},
                                 ["name", "type", "status", "medium", "call_received_by", "wd_contact"], as_dict=True)
        _out(f"calls webhook: type={cl.type} status={cl.status} medium={cl.medium} "
             f"routed_to={cl.call_received_by} contact_linked={bool(cl.wd_contact)}")

        # consent gate
        before = calls.can_call(NUM)
        voice.set_consent(contact, 1)
        after = calls.can_call(NUM)
        _out(f"consent: before={before} after={after}")

        # media bridge no-op (no URL configured)
        _out(f"bridge say (no url): {bridge.say('CALL-E2E-1', 'hi')}")

        # IVR flow via the graph runner (greeting/menu/say/hangup aliases)
        FLOW = "E2E IVR"
        if not frappe.db.exists("WhatsApp Chatbot Flow", FLOW):
            f = frappe.new_doc("WhatsApp Chatbot Flow"); f.flow_name = FLOW; f.enabled = 1
            f.wd_mode = "Graph"; f.flags.ignore_mandatory = True; f.insert(ignore_permissions=True)
        graph = {"version": 1, "nodes": [
            {"id": "start", "type": "start", "position": {}, "data": {"initial_message": "Welcome to support"}},
            {"id": "menu", "type": "menu", "position": {}, "data": {"message": "Press 1 Sales, 2 Support",
             "buttons": [{"id": "1", "title": "Sales"}, {"id": "2", "title": "Support"}]}},
            {"id": "s1", "type": "say", "position": {}, "data": {"message": "Connecting you to sales"}},
            {"id": "hang", "type": "hangup", "position": {}, "data": {"completion_message": "Goodbye"}},
            {"id": "xfer", "type": "transfer", "position": {}, "data": {}},
        ], "edges": [
            {"id": "e0", "source": "start", "target": "menu", "sourceHandle": None},
            {"id": "e1", "source": "menu", "target": "s1", "sourceHandle": "1"},
            {"id": "e2", "source": "menu", "target": "xfer", "sourceHandle": "2"},
            {"id": "e3", "source": "s1", "target": "hang", "sourceHandle": None},
        ]}
        flows.save_graph(FLOW, graph)
        pub = flows.publish(FLOW)
        r1 = flows.simulate(FLOW, "call")
        r2 = flows.simulate(FLOW, "1", session_state=r1["session"])
        _out(f"ivr publish={pub.get('ok')} turn1={[o['text'] or '[menu]' for o in r1['outbound']]} "
             f"turn2={[o['text'] for o in r2['outbound']]} status={r2['session']['status']}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_platform():
    """Phase 5: webhook SSRF scoping + Item catalog feed + guarded sync + audit report."""
    from whatsapp_flow.wa_platform import webhooks, catalog
    from whatsapp_flow.wa_platform import profile  # noqa: F401 (import-ability)

    try:
        _ensure_account()  # default outgoing account so catalog.sync() reaches the guard
        # webhook SSRF hook is scoped to WA doctypes only
        wa_blocked = other_ok = None
        try:
            webhooks.validate_webhook(frappe._dict(webhook_doctype="Issue", request_url="http://127.0.0.1/x"))
            wa_blocked = "NOT blocked"
        except frappe.ValidationError:
            wa_blocked = "blocked (correct)"
        try:
            webhooks.validate_webhook(frappe._dict(webhook_doctype="ToDo", request_url="http://127.0.0.1/x"))
            other_ok = "allowed (correct, scoped out)"
        except frappe.ValidationError:
            other_ok = "WRONGLY blocked"
        _out(f"webhook ssrf: WA={wa_blocked} nonWA={other_ok}")

        # Item -> catalog feed
        group = frappe.db.get_value("Item Group", {"is_group": 0}) or frappe.db.get_value("Item Group", {})
        uom = frappe.db.get_value("UOM", {"name": "Nos"}) or frappe.db.get_value("UOM", {})
        code = "WD-E2E-ITEM"
        if not frappe.db.exists("Item", code):
            it = frappe.new_doc("Item")
            it.update({"item_code": code, "item_name": "E2E Widget", "item_group": group,
                       "stock_uom": uom, "standard_rate": 125, "is_stock_item": 0,
                       "description": "A test widget"})
            it.flags.ignore_mandatory = True
            it.insert(ignore_permissions=True)
        feed = catalog.build_item_feed({"item_code": code})
        _out(f"catalog feed: n={len(feed)} first={feed[0]['retailer_id'] if feed else None} "
             f"price={feed[0]['price'] if feed else None}")
        res = catalog.sync()  # no catalog_id on account -> guarded, no Meta call
        _out(f"catalog sync (guarded): {res}")

        _out(f"audit report exists={bool(frappe.db.exists('Report', 'WA Audit Trail'))} "
             f"catalog_field={bool(frappe.get_meta('WhatsApp Account').get_field('wd_catalog_id'))}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_analytics():
    """Phase 4: number cards + charts + agent report + workspace created."""
    from whatsapp_flow.setup import analytics

    try:
        analytics.ensure_analytics()
        cards = [c for c in ("WA Open Conversations", "WA Resolved Issues", "WA Unread", "WA Contacts")
                 if frappe.db.exists("Number Card", c)]
        charts = [c for c in ("WA Conversations Over Time", "WA Conversations by Status")
                  if frappe.db.exists("Dashboard Chart", c)]
        _out(f"number_cards={len(cards)}/4 charts={len(charts)}/2 "
             f"report={bool(frappe.db.exists('Report', 'WA Agent Performance'))} "
             f"workspace={bool(frappe.db.exists('Workspace', 'WhatsApp Flow'))}")
        # exercise one card's live value + the report query
        from frappe.desk.doctype.number_card.number_card import get_result
        nc = frappe.get_doc("Number Card", "WA Contacts")
        try:
            val = get_result(nc, {})
            _out(f"WA Contacts card value={val}")
        except Exception as e:  # noqa: BLE001
            _out(f"card value ERR {type(e).__name__}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def run_flows():
    """Encrypted Flows endpoint: RSA/AES round-trip + WA Flow Response + build_context patch."""
    from base64 import b64encode, b64decode
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import os as _os
    from whatsapp_flow.wa_flows import crypto, endpoint as flow_ep
    from whatsapp_flow.compat import patches

    try:
        # keypair
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.TraditionalOpenSSL,
                                     serialization.NoEncryption()).decode()
        pub = key.public_key()

        # simulate Meta's encrypted request
        aes_key = _os.urandom(16)
        iv = _os.urandom(16)
        plaintext = _json_dumps({"action": "data_exchange", "flow_token": "T1",
                                 "screen": "S1", "data": {"number": NUM, "answer": "yes"}})
        enc_flow = AESGCM(aes_key).encrypt(iv, plaintext.encode(), None)
        enc_key = pub.encrypt(aes_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                                    algorithm=hashes.SHA256(), label=None))
        body = {"encrypted_flow_data": b64encode(enc_flow).decode(),
                "encrypted_aes_key": b64encode(enc_key).decode(),
                "initial_vector": b64encode(iv).decode()}

        data, k2, iv2 = crypto.decrypt_request(body, priv_pem)
        _out(f"flows decrypt: action={data.get('action')} token={data.get('flow_token')} "
             f"key_match={k2 == aes_key}")

        # process -> creates WA Flow Response
        resp = flow_ep._process(data)
        saved = frappe.db.exists("WA Flow Response", {"flow_token": "T1"})
        _out(f"flows process: resp_screen={resp.get('screen')} wa_flow_response_created={bool(saved)}")

        # encrypt response, decrypt back (flipped IV) to confirm round-trip
        enc_resp = crypto.encrypt_response(resp, aes_key, iv)
        flipped = bytes(b ^ 0xFF for b in iv)
        back = AESGCM(aes_key).decrypt(flipped, b64decode(enc_resp), None)
        _out(f"flows response round-trip ok={_json_loads(back.decode()) == resp}")

        patches.apply()
        _out(f"build_context patch: {patches.get_status().get('build_context', {}).get('status')}")
    finally:
        frappe.db.rollback()
        _out("rolled back - no test data persisted")


def _json_dumps(o):
    import json
    return json.dumps(o)


def _json_loads(s):
    import json
    return json.loads(s)


def seed_demo():
    """Seed a demo conversation + a published graph flow (COMMITS — for a live walkthrough)."""
    from whatsapp_flow.api.v1 import flows

    acc = "Demo WhatsApp"
    if not frappe.db.exists("WhatsApp Account", acc):
        a = frappe.new_doc("WhatsApp Account")
        a.update({"account_name": acc, "token": "x", "url": "https://graph.facebook.com",
                  "version": "v21.0", "phone_id": "DEMOPID", "business_id": "DEMOBID",
                  "app_id": "DEMOAID", "webhook_verify_token": "vt",
                  "is_default_incoming": 1, "is_default_outgoing": 1})
        a.flags.ignore_mandatory = True
        a.insert(ignore_permissions=True)

    for num, name, msgs in [
        ("15551234567", "Alex Rivera", ["Hi, I need help with my order #4471", "It hasn't shipped yet"]),
        ("15559876543", "Priya Nair", ["Do you have the blue model in stock?"]),
        ("15552223333", "Sam Okoro", ["Thanks, that worked!"]),
    ]:
        if not frappe.db.exists("WhatsApp Contact", {"mobile_no": num}):
            c = frappe.new_doc("WhatsApp Contact")
            c.update({"contact_name": name, "mobile_no": num})
            c.flags.ignore_mandatory = True
            c.insert(ignore_permissions=True)
        for i, m in enumerate(msgs):
            msg = frappe.new_doc("WhatsApp Message")
            msg.update({"type": "Incoming", "from": num, "message": m, "content_type": "text",
                        "message_id": f"wamid.DEMO.{num}.{i}", "whatsapp_account": acc})
            msg.flags.ignore_permissions = True
            msg.insert(ignore_permissions=True)

    FLOW = "Demo Support Flow"
    if not frappe.db.exists("WhatsApp Chatbot Flow", FLOW):
        f = frappe.new_doc("WhatsApp Chatbot Flow")
        f.flow_name = FLOW
        f.enabled = 1
        f.wd_mode = "Graph"
        f.trigger_keywords = "hi,hello,help"
        f.flags.ignore_mandatory = True
        f.insert(ignore_permissions=True)
    graph = {"version": 1, "nodes": [
        {"id": "start", "type": "start", "position": {"x": 60, "y": 180},
         "data": {"label": "Start", "initial_message": "Hi! Welcome to Acme support."}},
        {"id": "name", "type": "input", "position": {"x": 300, "y": 180},
         "data": {"label": "Ask name", "store_as": "name", "message": "What's your name?"}},
        {"id": "menu", "type": "buttons", "position": {"x": 560, "y": 180},
         "data": {"label": "Menu", "message": "Thanks {{ name }}! How can we help?",
                  "buttons": [{"id": "order", "title": "Order status"}, {"id": "agent", "title": "Talk to agent"}]}},
        {"id": "order", "type": "text", "position": {"x": 820, "y": 90},
         "data": {"label": "Order", "message": "Please share your order number."}},
        {"id": "agent", "type": "transfer", "position": {"x": 820, "y": 300},
         "data": {"label": "Handoff"}},
        {"id": "ordend", "type": "end", "position": {"x": 1080, "y": 90},
         "data": {"label": "End", "completion_message": "An agent will follow up shortly."}},
    ], "edges": [
        {"id": "e0", "source": "start", "target": "name", "sourceHandle": None},
        {"id": "e1", "source": "name", "target": "menu", "sourceHandle": None},
        {"id": "e2", "source": "menu", "target": "order", "sourceHandle": "order"},
        {"id": "e3", "source": "menu", "target": "agent", "sourceHandle": "agent"},
        {"id": "e4", "source": "order", "target": "ordend", "sourceHandle": None},
    ]}
    flows.save_graph(FLOW, graph)
    flows.publish(FLOW)
    frappe.db.commit()
    _out(f"seeded demo: 3 conversations + flow '{FLOW}' published")


def cleanup_residue(do_delete=0):
    """Find (and optionally delete) any committed E2E test artifacts on this site."""
    found = {}
    found["WhatsApp Message"] = frappe.get_all("WhatsApp Message",
        filters={"message_id": ["like", "wamid.%E2E%"]}, pluck="name") + \
        frappe.get_all("WhatsApp Message", or_filters=[{"from": NUM}, {"to": NUM}], pluck="name")
    found["Issue"] = frappe.get_all("Issue", filters={"wd_whatsapp_contact": ["is", "set"],
        "subject": ["like", "%E2E Tester%"]}, pluck="name")
    found["WhatsApp Contact"] = frappe.get_all("WhatsApp Contact", filters={"mobile_no": NUM}, pluck="name")
    found["WhatsApp Profiles"] = frappe.get_all("WhatsApp Profiles", filters={"number": NUM}, pluck="name") \
        if frappe.db.exists("DocType", "WhatsApp Profiles") else []
    found["WhatsApp Account"] = frappe.get_all("WhatsApp Account", filters={"account_name": "WD E2E"}, pluck="name")
    found["User Group"] = frappe.get_all("User Group", filters={"name": "WD Team E2E"}, pluck="name")
    found["WA Segment"] = frappe.get_all("WA Segment", filters={"title": "E2E Segment"}, pluck="name") \
        if frappe.db.exists("DocType", "WA Segment") else []
    found["WA Canned Response"] = frappe.get_all("WA Canned Response", filters={"shortcut": "/hi"}, pluck="name") \
        if frappe.db.exists("DocType", "WA Canned Response") else []
    found["WA Custom Action"] = frappe.get_all("WA Custom Action", filters={"title": ["in", ["Open CRM", "Bad Hook"]]}, pluck="name") \
        if frappe.db.exists("DocType", "WA Custom Action") else []
    found["Bulk WhatsApp Message"] = frappe.get_all("Bulk WhatsApp Message", filters={"title": "E2E Campaign"}, pluck="name")
    found["WhatsApp Recipient List"] = frappe.get_all("WhatsApp Recipient List", filters={"list_name": "Segment: E2E Segment"}, pluck="name")
    found["ToDo"] = frappe.get_all("ToDo", filters={"reference_type": "Issue", "reference_name": ["in", found["Issue"] or ["__none__"]]}, pluck="name")

    for dt, names in found.items():
        if names:
            _out(f"{dt}: {names}")
    if not any(found.values()):
        _out("no residue found")

    if int(do_delete):
        order = ["ToDo", "WhatsApp Message", "Bulk WhatsApp Message", "WhatsApp Recipient List",
                 "WA Segment", "WA Canned Response", "WA Custom Action", "Issue",
                 "WhatsApp Profiles", "WhatsApp Contact", "User Group", "WhatsApp Account"]
        for dt in order:
            for name in found.get(dt, []):
                try:
                    frappe.delete_doc(dt, name, force=1, ignore_permissions=True, delete_permanently=True)
                except Exception as e:  # noqa: BLE001
                    _out(f"del {dt} {name} ERR {type(e).__name__}")
        # strip any test-added escalation levels from the (install-created) SLA
        sla = frappe.db.get_value("Service Level Agreement", {"service_level": "WhatsApp SLA"})
        if sla:
            s = frappe.get_doc("Service Level Agreement", sla)
            if s.get("wd_escalation_levels"):
                s.set("wd_escalation_levels", [])
                s.flags.ignore_permissions = True
                s.save(ignore_permissions=True)
                _out("cleared test escalation levels on WhatsApp SLA")
        frappe.db.commit()
        _out("DELETED residue + committed")


def sla_try():
    from whatsapp_flow.setup.sla import TARGETS, SLA_NAME
    try:
        frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
        doc = frappe.new_doc("Service Level Agreement")
        doc.service_level = SLA_NAME
        doc.document_type = "Issue"
        doc.enabled = 1
        doc.default_priority = "Medium"
        doc.apply_sla_for_resolution = 1
        doc.condition = "doc.get('wd_source')"
        for prio, (resp, reso) in TARGETS.items():
            doc.append("priorities", {"priority": prio, "response_time": resp,
                                      "resolution_time": reso, "default_priority": 1 if prio == "Medium" else 0})
        for st in ("Resolved", "Closed"):
            doc.append("sla_fulfilled_on", {"status": st})
        for st in ("Replied", "On Hold"):
            doc.append("pause_sla_on", {"status": st})
        from whatsapp_flow.setup.sla import _default_holiday_list, WEEKDAYS
        doc.holiday_list = _default_holiday_list()
        for day in WEEKDAYS:
            doc.append("support_and_resolution",
                       {"workday": day, "start_time": "00:00:00", "end_time": "23:59:59"})
        doc.flags.ignore_permissions = True
        doc.insert()
        _out(f"created OK: {doc.name}")
    except Exception as e:  # noqa: BLE001
        _out(f"ERR {type(e).__name__}: {str(e)[:400]}")
    finally:
        frappe.db.rollback()


def sla_diag():
    m = frappe.get_meta("Service Level Agreement")
    fields = {f.fieldname: f.fieldtype for f in m.fields}
    interesting = {k: v for k, v in fields.items() if k in (
        "document_type", "enabled", "default_service_level_agreement", "default_priority",
        "condition", "holiday_list", "service_level", "priorities", "sla_fulfilled_on",
        "pause_sla_on", "apply_sla_for_resolution", "entity", "entity_type")}
    _out(f"SLA fields: {interesting}")
    _out(f"SLAs existing: {frappe.get_all('Service Level Agreement', fields=['name','document_type','enabled'])}")
    _out(f"Issue Priorities: {frappe.get_all('Issue Priority', pluck='name')}")
    for fld in ("priorities", "sla_fulfilled_on", "pause_sla_on"):
        opt = m.get_field(fld).options
        cm = frappe.get_meta(opt)
        _out(f"child {fld} ({opt}): {[(f.fieldname, f.fieldtype) for f in cm.fields]}")


def run_diag():
    """Diagnose the WhatsApp Agent Transfer doc_event + the wd_queue_status default."""
    hooks = frappe.get_hooks("doc_events") or {}
    _out(f"doc_events[WhatsApp Agent Transfer] = {hooks.get('WhatsApp Agent Transfer')}")
    f = frappe.get_meta("WhatsApp Agent Transfer").get_field("wd_queue_status")
    _out(f"wd_queue_status default = {f.default!r} options = {f.options!r}")
    _out(f"wd_issue exists = {bool(frappe.get_meta('WhatsApp Agent Transfer').get_field('wd_issue'))}")
