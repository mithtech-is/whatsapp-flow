# whatsapp_flow: Architecture & Phased Roadmap (v3.1: native-first)

*Plan only, no code yet. Revised 2026-10-14.*

> **What changed in v3.1 (folded in):**
> - **Native-first DocTypes.** The 15 proposed new DocTypes reduce to ~5. Conversation/episode → ERPNext **Issue** (which also removes the SLA-genericization risk, since Issue is SLA's native host); teams → Frappe **User Group**; agent presence → **User** fields; settings → existing **WhatsApp Settings**; call consent → **WhatsApp Contact** fields; IVR → **Chatbot Flow** Graph mode; calls → **Call Log**. See §3.5.
> - **Verified upstream facts (source-read):** send-to-Meta is in `WhatsAppMessage.before_insert` (the override chokepoint is correct and catches every sender); webhook has no HMAC + is synchronous; chatbot uses raw `exec()`; the processor runs synchronously inline.
> - **§2.2 refinements:** enqueue the existing `run_processor` (it logs) rather than a silent wrapper; rely on `ignore_chatbot` + `type != Incoming` as loop guards after the async move; verify the `set_typing` cmd-remap against the pinned Frappe version.
> - The visual **flow builder** is specified separately in `flow-builder-spec.md`.
*Feature numbers (#1–#69) refer to the gap list in [whatsapp-frappe-apps-analysis.md §9](whatsapp-frappe-apps-analysis.md).*

> **Decision (v3):** `whatsapp_flow` is an **add-on** that **requires all three existing apps**:
> - `frappe_whatsapp`
> - `whatsapp_chat`
> - `frappe_whatsapp_chatbot`
>
> It also reuses Frappe and ERPNext core DocTypes. **Whatomate is only a feature reference**; no Whatomate code or dependency is used.
>
> `whatsapp_flow` **extends** the three apps and adds only what none of them (or Frappe/ERPNext) provides. Nothing is replaced or migrated.

---

## 1. Dependencies

```python
# whatsapp_flow/hooks.py
required_apps = [
    "frappe",
    "erpnext",
    "shridarpatil/frappe_whatsapp",
    "shridarpatil/whatsapp_chat",
    "shridarpatil/frappe_whatsapp_chatbot",
]
```

**Install order on a site:**
1. `frappe_whatsapp`
2. `whatsapp_chat`
3. `frappe_whatsapp_chatbot`
4. `whatsapp_flow`

Our `doc_events` run after theirs on WhatsApp Message.

**Version pinning:**
- Record a tested commit for each of the three apps in `whatsapp_flow/compat.py` and in the README.
- CI runs against the pinned commits **and** nightly against each app's `develop` branch, so upstream breakage is caught early.

### 1.1 ⚠️ License check: required before any commercial use
| App | License | Impact |
|---|---|---|
| frappe_whatsapp | MIT | No restriction |
| whatsapp_chat | MIT ("unlicense" in hooks) | No restriction |
| **frappe_whatsapp_chatbot** | **MIT + Commons Clause** | Commons Clause forbids "selling" the software. That explicitly includes **charging for hosting, consulting or support services whose value derives substantially from it**. A paid implementation or SaaS that relies on the chatbot app may fall inside this. |

**Action:** before selling `whatsapp_flow`, or charging clients for chatbot-based work, get **written permission or a commercial license from the chatbot app's author** (Shridhar Patil), or take legal advice.

`whatsapp_flow` itself must not copy chatbot code. It only calls and extends it.

---

## 2. How we extend without forking

| Mechanism | Used for |
|---|---|
| **Custom Field / Property Setter** (fixtures, module `WhatsApp Flow`) | New fields and Select options on the three apps' DocTypes and on core DocTypes; `track_changes`; indexes |
| **`override_doctype_class`** (or `extend_doctype_class` where supported) | WhatsApp Message (send guard), WhatsApp Templates (VIDEO / named params / draft), Bulk WhatsApp Message (pause, opt-out, throttle) |
| **`override_whitelisted_methods`** | Replace **insecure or missing endpoints** in the three apps with secured versions (§2.1). This works even for methods that don't exist, such as `set_typing`. |
| **`doc_events`** | Conversation linking, routing, SLA, assignment sync |
| **Runtime patch layer** (`whatsapp_flow/compat/patches.py`, imported from `hooks.py`) | A few targeted monkeypatches on the **chatbot engine**, which is plain Python classes, not DocTypes (§2.2). Each one is version-checked and tested. |
| **`permission_query_conditions` / `has_permission`** | Scoped inbox on WhatsApp Contact, **Issue** and WhatsApp Message |
| **Roles + Custom DocPerm** (fixtures) | WA Admin / WA Manager / WA Agent across all three apps' DocTypes |
| **Patches** | Indexes on their tables, back-fill of **Issue** (conversations) |
| **Upstream PRs** | Every fix below is also offered upstream. When merged, the matching override or patch is deleted. |

### 2.1 Endpoint overrides (security and bug fixes)
| Original endpoint | Problem found | Our replacement |
|---|---|---|
| `frappe_whatsapp.utils.webhook.webhook` | No signature check; synchronous processing | HMAC verify (fail closed) → log → enqueue → reuse their parser in the background; tolerant status handling |
| `frappe_whatsapp...flow_endpoint.handle_flow_request` | Stub: no decryption, no signature, missing DocType | Real encrypted data-exchange endpoint → **WA Flow Response** |
| `whatsapp_chat.api.message.get_all` | Raw SQL, **no permission check**, hides template messages | Permission-checked; includes templates, interactive messages and status |
| `whatsapp_chat.api.message.send` | Text/media only; no window or permission check | Permission-checked; text/media/**template/interactive/reaction**; goes through the send guard |
| `whatsapp_chat.api.message.mark_as_read` | No permission check | Permission-checked |
| `whatsapp_chat.api.contacts.get` / `create` | Returns contacts for any email passed in | Scoped to the caller's assignments/teams |
| `whatsapp_chat.api.message.set_typing` | **Doesn't exist** (the client calls it and it fails silently) | Implemented; broadcasts typing to the room. *Verified:* `override_whitelisted_methods` remaps the `cmd` string before it is resolved, so overriding a non-existent method works — confirm once against the pinned Frappe version with a one-line test |
| `whatsapp_chat.api.config.settings` | Guest path calls an undefined `validate_token` | Guest path closed; admin path unchanged |

### 2.2 Chatbot runtime patches (fragile, so kept minimal)
| Target | Change | Why |
|---|---|---|
| `chatbot.processor.process_incoming_message` | Enqueue their existing **`run_processor`** on queue `wa_bot` instead of running inline | **Verified:** `process_incoming_message` currently runs `processor.process()` synchronously (its own comment says so) inside Meta's webhook request. Enqueue the existing `run_processor` (which logs its own errors) — **not** a new silent wrapper, since `process_incoming_message` swallows all exceptions and never re-raises. ⚠️ Moving to a worker loses the in-process `_processing_messages` re-entrancy set (it lives per-process); the real loop guards survive the enqueue boundary — `doc.flags.ignore_chatbot` and `type != "Incoming"` — so rely on those explicitly |
| `chatbot.flow_engine.FlowEngine.run_script` / `run_response_script` | Use `frappe.utils.safe_exec` instead of `exec()` | Removes arbitrary code execution |
| `chatbot.processor.ChatbotProcessor.process` | Skip when the **Issue** is with a human (`WhatsApp Contact.wd_bot_active = 0`); dispatch to our **graph runner** when the flow is in Graph mode | Graph builder and handoff integration |
| `chatbot.ai_responder.AIResponder.build_context` | Add the **External API** context type; supply tools | #14, #16 |

**Guard:** `patches.py` checks each target's signature and the installed app commit at import.
- On a mismatch it logs an Error Log entry and **skips that patch**, falling back to the original behaviour.
- A health page in **WhatsApp Settings** shows patch status.

---

## 3. DocType inventory

### 3.1 frappe_whatsapp (core transport): reused + extended
| DocType | Role | Extension |
|---|---|---|
| **WhatsApp Account** | Number credentials | `wd_app_secret` (Password, required by the signed webhook), `wd_throughput_tier`, `wd_calling_enabled`, `wd_coexistence`, `wd_quality_rating`, `wd_webhook_last_seen` |
| **WhatsApp Message** | The single message table | `wd_issue` (→ **Issue**, indexed), `wd_sent_by`, `wd_agent`, `wd_pricing_category`, `wd_error_code`. **Class override:** send guard (§5.2) → `super()` |
| **WhatsApp Templates** + **WhatsApp Button** | Templates + Meta sync | Property Setter `header_type` += VIDEO. Fields: `wd_parameter_format`, `wd_local_state`, `wd_quality_score`. Class override for VIDEO, named params and draft → publish |
| **WhatsApp Flow** (+ Screen, Field) | Native Flows | `wd_endpoint_mode`, `wd_private_key`, `wd_public_key` |
| **WhatsApp Notification** + Log | ERP-triggered messages, **as-is** | Log retention job |
| **Bulk WhatsApp Message** + Recipient + Recipient List | Campaigns | Status += Paused/Cancelled; `wd_segment`, `wd_respect_opt_out`, CSV source. Class override: pause/cancel/opt-out/throttle per recipient job |
| **WhatsApp Profiles** | Number ↔ ERPNext Contact link | `wd_customer`, `wd_lead` |
| **WhatsApp Settings** | Default accounts | **Extended (replaces the planned new "WA Settings" Single):** `wd_phone_masking`, `wd_retention_days`, `wd_queues`, `wd_rate_limits`, `wd_patch_health`, `wd_media_bridge_url` |

### 3.2 whatsapp_chat (inbox): reused + extended
| DocType | Role | Extension |
|---|---|---|
| **WhatsApp Contact** | **The customer record and inbox row** (one per number). Its existing `email` field = current assignee, which keeps their chat-bubble realtime working. | `wd_whatsapp_account`, `wd_profile` (→ WhatsApp Profiles), `wd_open_issue` (→ **Issue** — the conversation/episode), `wd_team` (→ **User Group**), `wd_window_expires_at`, `wd_unread_count`, `wd_bot_active`, **`wd_marketing_opt_out`**, `wd_opt_out_on/source`, `wd_call_consent`, `wd_call_consent_on/source` (replaces the planned new "WA Call Permission"), `wd_custom_data` (JSON), `wd_language`; tags via Frappe **Tag** |
| Chat bubble UI (Desk) | **Kept** for quick replies inside Desk | Its calls now hit our secured endpoints (§2.1). Light JS additions through our own bundle: template picker, window badge, "Open in Desk" link to the full SPA |

### 3.3 frappe_whatsapp_chatbot (automation): reused + extended
| DocType | Role | Extension |
|---|---|---|
| **WhatsApp Chatbot** (Single) | Bot settings, AI provider, business hours, excluded numbers | `wd_greeting`, `wd_fallback_buttons` (JSON), `wd_holiday_list` (→ Holiday List), `wd_ai_tools_enabled`, `wd_handoff_team` |
| **WhatsApp Keyword Reply** | Keyword rules, **as-is** | Optional `wd_team` scope |
| **WhatsApp Chatbot Flow** + **WhatsApp Flow Step** | Flows | `wd_mode` (Steps / **Graph**), `wd_graph_json`, `wd_published_json` (immutable live snapshot the runner executes), `wd_version`, `wd_published`. Step mode = their engine; Graph mode = our runner. **IVR flows (voice phase) reuse this DocType in Graph mode** (replaces the planned new "WA IVR Flow"). Full builder/runner spec: `flow-builder-spec.md` |
| **WhatsApp Chatbot Session** + Session Message | Session state | `wd_current_node`, `wd_graph_vars` (JSON), `wd_issue` (→ **Issue**) |
| **WhatsApp AI Context** | AI knowledge | Property Setter `context_type` += **External API**; fields `wd_api_url`, `wd_api_method`, `wd_api_headers` (Password/JSON), `wd_response_path` |
| **WhatsApp Agent Transfer** | **Bot → human handoff record**, reused | `wd_team` (→ **User Group**), `wd_issue` (→ **Issue**), `wd_picked_up_by`, `wd_queue_status` (Queued/Assigned/Resolved/Expired). `doc_events` sync it with the **Issue** and assignment |
| **WhatsApp Business Hours** / **Excluded Number** | Bot hours, exclusions, **as-is** | Bot timing node reads WhatsApp Business Hours + Holiday List |

### 3.4 Frappe / ERPNext core: reused
| Core DocType | Covers |
|---|---|
| **Issue** (ERPNext Support) | **The conversation / support episode** (replaces the planned new "WA Conversation"). Already ships the full native SLA machinery — `service_level_agreement`, `response_by`, `agreement_status`, `first_responded_on`, `sla_resolution_by`, `on_hold_since`, `total_hold_time`, `status` (Open/Replied/On Hold/Resolved/Closed), `priority`, and native `customer`/`lead`/`contact` links. Add `wd_whatsapp_contact`, `wd_account`, `wd_source` (bot/inbound/outbound). **This removes the SLA-genericization risk** — SLA runs on the DocType it was built for. ⚠️ Depends on Issue staying in ERPNext core for the targeted version (see §10). |
| **User Group** + **User Group Member** (Frappe) | **Teams** (replaces the planned new "WA Team"/"WA Team Member"). Native grouping of users. Per-member role/capacity can't live on the Table-MultiSelect member rows, so carry those as custom fields on User (below) or a small custom child table field (`wd_members`) on User Group. Strategy / default SLA / linked Assignment Rule = custom fields on User Group. |
| **User** (Frappe) | **Agent presence/capacity** (replaces the planned new "WA Agent"): `wd_wa_availability` (Online/Away/Offline), `wd_wa_capacity`, plus User Group membership for teams. Drives the Assignment Rule user sync. |
| **Call Log** (Frappe/CRM) | #1–#12 **call records** (replaces the planned new "WA Call") + custom fields. ⚠️ Verify this DocType is present on the target bench (base frappe vs CRM/telephony integration) before the voice phase. |
| **Assignment Rule** + **ToDo** | #30 round-robin / load-balanced / manual. One rule per team (**User Group**) on **Issue**; users synced to online agents (a background job rewrites the rule's user list from `User.wd_wa_availability` — treat as live config mutation under concurrency). On assignment, `WhatsApp Contact.email` is updated too. |
| **Service Level Agreement** (+ Priority, Service Day) + **Issue Priority** + **Holiday List** (ERPNext) | #33 SLA on **Issue** (native host), plus custom child table **WA Escalation Level** for the escalation ladder |
| **Tag** | #36, #48 tags and segments |
| **Comment** | #34 private notes on **Issue** |
| **Contact / Customer / Lead** | CRM links (via WhatsApp Profiles) |
| **Item** (ERPNext) | #69 catalog sync to Meta |
| **Webhook** + Request Log | #66 outbound webhooks (we add an SSRF `validate` hook) |
| **Dashboard Chart / Number Card / Workspace / Script Report** | #54–#57 analytics |
| **Role / Custom DocPerm / User Permission** | #59 RBAC; #58 multi-tenant = Frappe multi-site |
| **Social Login Key / LDAP** | #60 SSO |
| **Version / Activity Log** | #61 audit (`track_changes` via Property Setter) |
| **Server Script** (API type) | Bot script node: sandboxed, System Manager only |
| **User API key** | #67 integrations |
| **File** (private, S3 optional) | Media, call recordings |
| **Translation** | #68 i18n |
| **Notification Log** | Agent alerts (assignment, SLA risk, escalation) |
| **Data Import / Export** | #43 contact CSV, #47 campaign CSV |

### 3.5 New DocTypes in whatsapp_flow

**Native-first directive:** use native Frappe/ERPNext DocTypes and modules wherever possible. The original 15 proposed new DocTypes reduce to a small genuinely-new set below; the rest map onto native or existing-app DocTypes.

**Folded into native / existing (no longer new DocTypes):**
| Was (planned new) | Now (native / existing) |
|---|---|
| WA Conversation | **ERPNext `Issue`** (+ custom fields) — also removes the SLA-genericization risk (§3.4) |
| WA Team + WA Team Member | **Frappe `User Group` + `User Group Member`** (+ custom fields for per-member role/capacity) |
| WA Agent | Custom fields on **`User`** + User Group membership |
| WA Settings (Single) | Custom fields on the existing **`WhatsApp Settings`** Single (§3.1) |
| WA Call Permission | Custom fields on **`WhatsApp Contact`** (§3.2) |
| WA IVR Flow | **Graph mode on the existing `WhatsApp Chatbot Flow`** (§3.3) |
| WA Call | Frappe/CRM **`Call Log`** (+ custom fields) — verify on bench |
| WA Segment | Prefer a saved filter JSON → native **Recipient List** population job; keep a thin DocType only if that proves insufficient |
| WA Insight Cache | Prefer Frappe document cache / Dashboard sources; keep a thin DocType only if a queryable store is needed |

**Genuinely new (no native fit):**
| DocType | Why none of the above covers it |
|---|---|
| **WA Escalation Level** (child of Service Level Agreement) | Escalation ladder — native SLA has no escalation-ladder child |
| **WA Canned Response** | `/shortcut` replies with placeholders and buttons (native `Email Template` is email-shaped and lacks shortcut/buttons) |
| **WA Custom Action** | Inbox action buttons (Webhook / URL / JS) |
| **WA AI Tool** | ERP functions the LLM may call (optional) |
| **WA Flow Response** | Data from the encrypted Flows endpoint |

---

## 4. Gap → implementation map (all 69)

| Gaps | Built on |
|---|---|
| #1–#12 Voice / IVR | **Native/existing:** **Call Log** (call records), **WhatsApp Chatbot Flow** Graph mode (IVR graphs), **WhatsApp Contact** fields (call consent). **Reused:** **User Group** + Assignment Rule (ring rotation), File, Holiday List, WhatsApp Account. `calls` webhook via our override. |
| #13 AI node, #15–#24 graph builder & nodes | **Extended** WhatsApp Chatbot Flow (Graph mode) + Session; our runner; Server Script node; Jinja for #23 |
| #14 AI context from API | **Extended** WhatsApp AI Context (External API) + `build_context` patch |
| #25 Greeting / fallback buttons | **Extended** WhatsApp Chatbot |
| #26 Contact info panel, #27 bot stats | SPA panel over Chatbot Session data; Number Cards on Chatbot Session |
| #28 Safe scripts | `safe_exec` patch + Server Script node |
| #29–#31 Teams, assignment, queues | **User Group** (teams) + **User** fields (agent presence) + **Assignment Rule / ToDo** + **Issue** |
| #32 Handoff | **Reused** WhatsApp Agent Transfer (+ team/queue fields) |
| #33 SLA | **ERPNext SLA** on **Issue** (native host) + WA Escalation Level |
| #34 Notes | **Comment** |
| #35 Canned responses | **New** WA Canned Response |
| #36 Tags | **Tag** on WhatsApp Contact / **Issue** |
| #37 24h window | `WhatsApp Contact.wd_window_expires_at` + send guard |
| #38 Templates/interactive from inbox | Secured `whatsapp_chat.api.message.send` override + SPA composer |
| #39, #44 Unread, team realtime | WhatsApp Contact counters + team rooms |
| #40 Scoped inbox | Permission hooks + secured whatsapp_chat endpoints |
| #41 Masking | WhatsApp Settings + serializer |
| #42 Custom actions | **New** WA Custom Action |
| #43 Contact CSV | **Data Import/Export** on WhatsApp Contact |
| #45 Opt-out | `WhatsApp Contact.wd_marketing_opt_out` + send guard + STOP keyword |
| #46–#49 Campaign controls | **Extended** Bulk WhatsApp Message / Recipient List + WA Segment |
| #50–#53 Templates | **Extended** WhatsApp Templates |
| #54–#57 Analytics | **Dashboard Chart / Number Card / Workspace / Script Report** (+ a thin insight cache only if a queryable Meta-analytics store is needed; prefer Frappe cache) |
| #58–#61 Tenancy, RBAC, SSO, audit | **Frappe multi-site, Role/DocPerm, Social Login Key, Version** |
| #62 Embedded Signup + Coexistence | SPA + API that creates a **WhatsApp Account** |
| #63 Business profile | SPA page → Meta API |
| #64 Webhook signature | Endpoint override (§2.1) |
| #65 Secrets | Password fields |
| #66 Outbound webhooks | **Webhook** + SSRF hook |
| #67 API | Frappe REST + `whatsapp_flow.api.v1` + User API keys |
| #68 i18n | **Translation** |
| #69 Catalog | **ERPNext Item** sync |

---

## 5. Key flows

### 5.1 Inbound message
```
Meta → (same URL) → our webhook override: verify HMAC (fail closed) → enqueue → 200
worker → frappe_whatsapp parser creates WhatsApp Message
  after_insert hooks (in app install order):
   1. whatsapp_chat.last_message        → creates/updates WhatsApp Contact (their code)
   2. frappe_whatsapp_chatbot processor → (patched) enqueued to wa_bot queue
   3. whatsapp_flow.on_message          → find/open Issue, set WhatsApp Contact.wd_open_issue,
                                          update window/unread/opt-out (STOP),
                                          if bot inactive → assignment, publish to team rooms
wa_bot worker → their processor (patched):
   - skips if a human has the conversation
   - Graph flows → our runner
   - Step flows / keywords / AI → their engine
```

### 5.2 Outbound send guard (WhatsApp Message override)
- **Verified against source:** frappe_whatsapp sends to Meta in `WhatsAppMessage.before_insert` → `send_outgoing()` → `notify()`. So a class override of `before_insert` that runs the checks and only then calls `super().before_insert()` is the correct single chokepoint — raising before `super()` prevents the send. Because the send lives in the Message doctype itself, **every** creator funnels through it automatically.
- Every outgoing message passes through the guard, whatever created it: agent (chat bubble or SPA), bot, Bulk, Notification or API.
- The guard runs three checks: **window**, **opt-out** (Marketing), and the **rate-limit token**.
- It then links the conversation, sets `wd_sent_by` / `wd_agent`, and calls `super().before_insert()`.

### 5.3 Handoff, assignment and SLA
1. The bot's transfer (their `WhatsAppAgentTransfer.transfer_to_agent`, or our graph transfer node) creates a **WhatsApp Agent Transfer** with `wd_team`.
2. Our hook sets the **Issue** team (→ User Group) and `WhatsApp Contact.wd_bot_active = 0`.
3. The team's **Assignment Rule** (on Issue) creates the ToDo.
4. We copy the assignee to **`WhatsApp Contact.email`**, so the chat bubble notifies them.
5. The ERPNext **SLA** tracks response and resolution natively on the **Issue**. Our `sla.tick` handles the **escalation ladder** (WA Escalation Level) and auto-close.
6. On resolve: the transfer becomes `Resumed` (their resume logic) and the bot is active again.

---

## 6. Voice
Same approach as before:
- **6a. Browser-direct WebRTC:** the SDP is relayed through Frappe; ring rotation goes through the **User Group** Assignment Rule.
- **6b. SIP → FreeSWITCH bridge** for IVR, Piper TTS, hold, and recording to private File/S3.
- Verify the Meta Calling API specifics in a spike first.
- 6b needs a VPS, not Frappe Cloud, and stays behind a feature flag.

---

## 7. App structure
```
whatsapp_flow/
├── whatsapp_flow/
│   ├── hooks.py              # required_apps (all 3), overrides, doc_events, permissions, scheduler, fixtures
│   ├── compat/               # pinned commits, patches.py (chatbot runtime patches + guards), health checks
│   ├── overrides/            # doctype classes: whatsapp_message, whatsapp_templates, bulk_whatsapp_message
│   ├── endpoints/            # secured replacements: webhook, flow_endpoint, chat_message, chat_contacts, chat_config
│   ├── fixtures/             # custom fields & property setters on all 3 apps + core; roles; docperms; workspace; charts
│   ├── wa_core/              # guard (window/opt-out/rate), rate_limiter, signature, meta_client (calls/insights/catalog/profile/signup)
│   ├── wa_desk/              # Issue integration (SLA + WA Escalation Level child), Canned Response, Custom Action; assignment (User Group teams, User presence); sla
│   ├── wa_bot/               # graph runner + node handlers, AI tools, WA AI Tool
│   ├── wa_flows/             # WA Flow Response, encryption
│   ├── wa_campaign/          # WA Segment, CSV, pause/resume
│   ├── wa_analytics/         # WA Insight Cache, reports
│   ├── wa_voice/             # Call Log integration, IVR (Chatbot Flow Graph mode), call consent (Contact fields), bridge client
│   ├── wa_platform/          # WhatsApp Settings extension, embedded signup, SSRF hook, audit report
│   ├── api/v1/               # SPA endpoints
│   └── patches/              # indexes, Issue (conversation) back-fill
├── frontend/                 # Vue 3 + frappe-ui SPA at /whatsapp
└── media-bridge/             # Phase 6b
```

---

## 8. Phased roadmap

Estimates assume **1 experienced Frappe + Vue developer**.

| Phase | Scope | Est. |
|---|---|---|
| **0. Foundation on the three apps** | Fixtures (custom fields / property setters on all 3), roles + permissions, **endpoint overrides** (webhook, chat API, set_typing, config), WhatsApp Message send guard + rate limiter, **chatbot runtime patches** (async, safe_exec, human-skip) with guards + health page, Issue-as-conversation wiring + back-fill, indexes, opt-out + STOP, template VIDEO/named/draft, retention jobs, CI matrix against pinned + develop | **2–2.5 wks** |
| **1. Agent desk** | SPA `/whatsapp` (inbox, conversation, composer incl. templates/interactive, contact panel), User Group teams + User presence + Assignment Rule sync to `WhatsApp Contact.email`, queues on Agent Transfer, notes (Comment), canned responses, tags, scoped inbox, masking, custom actions, team realtime, chat-bubble enhancements | **3.5–4.5 wks** |
| **2. SLA + campaigns** | ERPNext SLA on **Issue** + escalation ladder + auto-close; Bulk pause/cancel/opt-out/throttle, CSV, WA Segment | **1.5–2 wks** |
| **3. Bot v2 + AI + Flows endpoint** | Graph mode on WhatsApp Chatbot Flow + Vue builder + runner (incl. ai_response, api_call, condition, set_variable, timing, goto, transfer, whatsapp_flow, ERP nodes, server_script), External API context, AI tools, greeting/fallback buttons, contact info panel, bot stats; encrypted Flows endpoint | **3.5–4.5 wks** |
| **4. Analytics** | Workspace, charts, number cards, agent report, Meta Insights | **1–1.5 wks** |
| **5. Platform** | Embedded Signup + Coexistence, business profile, Item catalog sync, outbound webhooks + SSRF, audit report, i18n, SSO guide | **1.5–2 wks** |
| **6. Voice** | 6a browser calling; 6b media bridge, IVR, TTS, hold, recording | **6–8 wks** |
| **Total** | **69/69 gaps, ~5 new DocTypes (native-first), no data migration** | **≈ 19–25 wks** |

**Release cuts:**
- **v0.1** = Phases 0–1 (secured + agent desk)
- **v0.2** = + 2
- **v0.5** = + 3–4
- **v1.0** = + 5
- **v1.1** = voice

---

## 9. Risks of requiring all three apps (and mitigations)
| Risk | Mitigation |
|---|---|
| **Commons Clause** on the chatbot app limits commercial use | Get permission or a commercial license from the author before selling or charging (§1.1) |
| Upstream changes break overrides or runtime patches | Pinned commits, nightly CI against `develop`, guarded patches that fall back safely, health page |
| Chatbot engine patches rely on internal class/method names | Keep them to 4 small patches; send upstream PRs (async processing, safe_exec, hook points) so they can be deleted |
| Three apps' hooks fire on every message (ordering, double replies) | Fixed install order; bot runs in one place only (their processor, patched); our hook never sends bot replies |
| Their insecure endpoints come back if an override fails | Override tests in CI; the WhatsApp Settings health page shows a red status if any override isn't active |
| `doc_events "*"` in frappe_whatsapp adds overhead to every save | Accept (it's cached), or propose an upstream PR to scope it to configured DocTypes |
| One maintainer for all three apps | Upstream contributions + pinned versions; keep the option to fork if the project stalls |

---

## 10. Decisions needed before Phase 0
1. **Bench path** and **Frappe/ERPNext versions** (v15, v16 or both). **Note:** the conversation/episode now maps to ERPNext **Issue** — confirm Issue (ERPNext Support) stays in core for the targeted version. If a version drops it in favour of the separate Helpdesk app (HD Ticket), fall back to HD Ticket or a custom DocType (which re-incurs the SLA-genericization work).
2. **Commons Clause:** will you sell `whatsapp_flow` or charge for chatbot-based services? If yes, contact the author first.
3. **License** for `whatsapp_flow` (MIT recommended).
4. **Meta:**
   - Is the app secret available? (Required because the webhook fails closed.)
   - Is the Meta app a Tech Provider (for Embedded Signup)?
   - Is Business Calling enabled on the number?
5. **Upstream PRs:** OK to contribute our fixes to the three repos?
6. **Data volume:** messages per day and largest campaign size.
7. **Call Log (voice phase):** confirm the native `Call Log` DocType is present on the target bench (base frappe vs a CRM/telephony integration) before relying on it for call records.
