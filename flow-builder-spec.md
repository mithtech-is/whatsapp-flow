# whatsapp_flow — Visual Flow Builder Spec

*Addendum to the whatsapp_flow plan (expands the one-line "Graph mode + Vue builder + runner" of Phase 3).*
*Native-first: no new DocTypes for the builder. The graph is stored on the **existing** `WhatsApp Chatbot Flow` DocType; execution reuses the **existing** `WhatsApp Chatbot Session`.*

---

## 0. References (studied, not copied)

- **Vue Flow** `@vue-flow/core@1.48.2` (+ `@vue-flow/background`, `@vue-flow/controls`, `@vue-flow/minimap`). Requires Vue 3.3+, Node 20+.
- **Whatomate** (`shridarpatil/whatomate`, **AGPL-3.0**, standalone Go + Vue 3) — the visual-builder *feature reference*. Its chatbot builder is built on the same Vue Flow stack. **Reference only; do not copy its `.vue` source** (AGPL network-copyleft would attach to whatsapp_flow). We reimplement in our own frappe-ui SPA.
- **Frappe CRM** (`frappe/crm`) — first-party proof that `frappe-ui@1.0.0-rc.2` + `@vue-flow/core@1.48.2` build and run together inside a Frappe app. Used as the integration pattern.

---

## 1. Where it lives

- A route in the single `/whatsapp` SPA: `/whatsapp/flows` (list) and `/whatsapp/flows/:flow_name` (builder).
- Served by Frappe: `vite build --base=/assets/whatsapp_flow/frontend/` → `copy-html-entry` → `whatsapp_flow/www/whatsapp.html`; `website_route_rules` in `hooks.py` maps `/whatsapp/<path>` to it for client-side routing.
- Loads/saves via frappe-ui `createDocumentResource('WhatsApp Chatbot Flow', name)` reading/writing `wd_graph_json`; publish/validate via `createResource({ url: 'whatsapp_flow.api.v1.flows.*' })`.

---

## 2. Storage (native-first — fields on the existing DocType)

Custom fields added by fixtures to **`WhatsApp Chatbot Flow`**:

| Field | Type | Purpose |
|---|---|---|
| `wd_mode` | Select (`Steps`\|`Graph`) | `Steps` = upstream engine (unchanged). `Graph` = our runner. Default `Steps`. |
| `wd_graph_json` | JSON (Long Text) | The canvas graph (see §4). Only meaningful when `wd_mode = Graph`. |
| `wd_version` | Int | Incremented on each publish. |
| `wd_published` | Check | Whether a validated graph is live. |
| `wd_published_json` | JSON (Long Text) | Immutable snapshot of the graph at last publish (the runner executes **this**, never the editable draft). |

On **`WhatsApp Chatbot Session`** (also existing):

| Field | Type | Purpose |
|---|---|---|
| `wd_current_node` | Data | Id of the node the session is paused on. |
| `wd_graph_vars` | JSON | Collected variables / `store_as` values for this session. |
| `wd_conversation` | Link → Issue | The episode this session belongs to (per the native-first model: WA Conversation = ERPNext **Issue**). |

No new DocType is introduced for the builder. IVR (voice phase) reuses the same `wd_mode = Graph` + `wd_graph_json` pattern with the IVR node set (§5.3).

---

## 3. Canvas UX

- **Layout:** left node palette · center Vue Flow canvas · right property panel (`ChatNodeProperties`-style, one editor per node type).
- **Vue Flow setup:** `@vue-flow/core` with `<Background>`, `<Controls>`, `<MiniMap>`. Canvas container has an explicit height (required or it won't render). Custom node components registered via `nodeTypes` with `markRaw(...)`.
- **Node interaction:** every form input inside a node carries `nodrag`; scrollable node bodies carry `nowheel` (so editing doesn't drag/zoom the canvas).
- **Connections:** each node renders `<Handle type="target" :position="Position.Top">` and one or more `<Handle type="source" ...>`. Branching nodes (condition, buttons) expose one source handle **per branch**, each with a stable `id` used as the edge `sourceHandle`.
- **Events:** `useVueFlow()` → `onConnect` (add edge, enforce single-outgoing where required), `onNodeClick` (open property panel), `updateNodeData(id, patch)` (write from the panel). Drag/drop from palette creates a node at drop position.
- **Autosave:** draft `wd_graph_json` autosaves (debounced) via the document resource; publish is explicit (§6).

---

## 4. Graph JSON schema (`wd_graph_json`)

```json
{
  "version": 1,
  "viewport": { "x": 0, "y": 0, "zoom": 1 },
  "nodes": [
    {
      "id": "n_start",
      "type": "start",
      "position": { "x": 80, "y": 120 },
      "data": { /* per-node, see §5 */ }
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "n_start",
      "target": "n_text1",
      "sourceHandle": null,
      "label": null
    }
  ]
}
```

- `id` stable across edits (generated `n_<rand>`), never reused.
- Edge `sourceHandle` names the branch for multi-output nodes (`"true"`/`"false"`, or a button id); `null` = the node's single default output.
- Node `data` reuses the **existing** `WhatsApp Flow Step` vocabulary wherever possible (`message_type`, `template`, `input_type`, `buttons`, `store_as`, `whatsapp_flow`/`flow_cta`/`flow_screen`, `validation_regex`), so Graph mode and Steps mode share one capability model.

---

## 5. Node catalog

### 5.1 Chatbot nodes (parity with Whatomate + whatsapp_flow additions)

| `type` | Node | `data` (key fields) | Handles (source) | Notes |
|---|---|---|---|---|
| `start` | Start | `trigger_keywords`, `trigger_on_button`, `initial_message` | 1 default | Exactly one per graph. |
| `text` | Send Message | `message_type` (Text/Template), `message`, `template` | 1 default | Reuses step fields. |
| `buttons` | Buttons / List | `message`, `buttons[]` (`{id,title,description?}`) | 1 per button + 1 `fallback` | ≤3 → buttons, 4–10 → list (mirrors frappe_whatsapp send logic). |
| `input` | Collect Input | `input_type` (Text/Number/Email/Phone/Date/Select), `store_as`, `validation_regex`, `validation_error`, `max_retries` | 1 default (+ `invalid` optional) | |
| `condition` | Condition | `expression` (evaluated with `frappe.safe_eval` against `wd_graph_vars`) | `true`, `false` | No raw `eval`. |
| `set_variable` | Set Variable | `assignments[]` (`{name, value|jinja}`) | 1 default | Jinja rendered server-side. **Addition.** |
| `api_call` | API Call | `url`, `method`, `headers` (Password/JSON), `body`, `response_path`, `store_as` | `success`, `error` | SSRF-validated (platform hook). |
| `timing` | Wait / Hours | `delay`, or `business_hours` (→ WhatsApp Business Hours + Holiday List) | `open`, `closed` (for hours) / 1 default (for delay) | |
| `whatsapp_flow` | WhatsApp Flow | `whatsapp_flow`, `flow_cta`, `flow_screen`, `flow_field_mapping` | 1 default | Native Meta Flow; response → WA Flow Response. |
| `goto` | Go To Flow | `target_flow` (→ WhatsApp Chatbot Flow) | — (terminal jump) | |
| `transfer` | Handoff | `wd_team` (→ User Group), `queue_message` | 1 `resumed` (optional) | Creates WhatsApp Agent Transfer; sets Issue team + `bot_active=0`. |
| `ai_response` | AI Response | `ai_context`, `tools[]` (→ WA AI Tool), `fallback` | `handoff`, `continue` | **Addition** (#13/#14/#16). Uses patched `build_context` + External API context. |
| `server_script` | Server Script | `server_script` (→ Server Script, API type) | `success`, `error` | Sandboxed, System-Manager-authored. **Addition.** |
| `erp` | ERP Action | `action` (Create/Update Doc), `doctype`, `field_mapping` | `success`, `error` | **Addition** (#69/CRM links). |
| `end` | End | `completion_message`, `on_complete_action` | — | Terminal. |

### 5.2 Node→backend mapping (how the runner handles each)

Each `type` maps to a handler in `whatsapp_flow/wa_bot/nodes/<type>.py` exposing `run(node, session, ctx) -> NextDirective`. `NextDirective` is one of: `goto(node_id)`, `branch(handle)`, `wait_for_input(node_id)`, `end`. This keeps the graph walk (§7) node-agnostic.

### 5.3 IVR nodes (voice phase — same graph machinery, `wd_mode=Graph` on an IVR flow)

Parity set from Whatomate's `calling/nodes/`: `greeting`, `gather`, `menu`, `timing`, `transfer`, `hangup`, `goto_flow`, `http_callback`. Same JSON schema, same runner contract, different handlers. Deferred to the voice phase; listed here so the schema is designed once.

---

## 6. Validation & publish

On **Publish**, `whatsapp_flow.api.v1.flows.publish(name)` validates the draft `wd_graph_json`:

1. Exactly one `start` node.
2. Every node (except `end`, `goto`) has at least one outgoing edge; every declared source handle (each button, `true`/`false`, `success`/`error`) is connected or explicitly defaulted.
3. No edge references a missing node; no orphan nodes (all reachable from `start`).
4. `condition`/`set_variable` expressions parse under `frappe.safe_eval`; `server_script` references an existing API-type Server Script.
5. Referenced entities exist (templates, flows, teams, AI contexts, target flows).

On success: copy draft → `wd_published_json`, bump `wd_version`, set `wd_published = 1`. The runner only ever executes `wd_published_json`, so editing a draft never affects live conversations.

---

## 7. Runner execution model (server-side)

Lives in `whatsapp_flow/wa_bot/graph_runner.py`. Entry via the chatbot processor patch (`§2.2` of the plan): the dispatch to the graph runner happens when `wd_mode = Graph`.

```
on inbound message routed to a Graph flow:
  session = get/create WhatsApp Chatbot Session (wd_current_node, wd_graph_vars)
  if Issue.bot_active == 0:  return          # human owns the conversation — skip bot
  graph = json.loads(flow.wd_published_json)
  node  = graph node at (session.wd_current_node or the start node)
  loop:
     directive = handlers[node.type].run(node, session, ctx)
     persist session (wd_current_node, wd_graph_vars) on every step
     match directive:
        wait_for_input(id) -> set wd_current_node=id; break   # park until next message
        branch(handle)     -> node = follow edge (source=node.id, sourceHandle=handle)
        goto(id)           -> node = graph[id]
        end                -> run on_complete_action; clear session; break
```

Execution-safety rules:
- Runs on the **`wa_bot` queue** (async), never inside Meta's webhook request.
- All script/expression nodes use `frappe.safe_exec` / `frappe.safe_eval` — **never** raw `exec`/`eval`.
- Loop guard: a max-steps-per-message cap (e.g. 50) prevents runaway cycles; every bot-sent message carries `flags.ignore_chatbot` and is typed `Outgoing`, so it cannot re-trigger the processor.
- All outbound sends go through the WhatsApp Message send guard (window / opt-out / rate limit) like any other sender.

---

## 8. Live preview / simulator (adopt from Whatomate)

Whatomate ships a `flow-preview/` simulator the plan didn't call out — worth matching, because it is the single biggest authoring-productivity feature:

- **InteractivePreview** — a WhatsApp-style chat pane that dry-runs the *published or draft* graph.
- **ExecutionTimeline / DebugPanel** — shows the node path taken, variables set, and branch chosen at each step.
- **ApiMockDialog** — mock `api_call`/`erp` responses so flows can be tested without live side effects.

Implementation: a `whatsapp_flow.api.v1.flows.simulate(name, draft, inbound, session_state)` endpoint that runs the **same handlers** as §7 in a dry-run mode (no real sends, side effects mocked), returning the step trace. Reuses the runner — no second engine.

---

## 9. Graph vs Steps coexistence & migration

- `wd_mode` gates everything: `Steps` flows run on the upstream engine untouched; `Graph` flows run on our runner. Both can exist on the same site.
- One-way **import**: a helper converts an existing Steps flow (`WhatsApp Flow Step` rows wired by `next_step`/`conditional_next`) into an equivalent graph (`text`/`input`/`condition`/`buttons` nodes + edges), so users can migrate without rebuilding.
- No downgrade path is needed (Graph is a superset); Steps mode stays for users who never open the builder.

---

## 10. Build/serve checklist (from the Frappe CRM pattern)

- `frappe-ui/vite` plugin in `vite.config.js`; `base=/assets/whatsapp_flow/frontend/`.
- `setConfig('resourceFetcher', frappeRequest)` in `main.js`; `resourcesPlugin` if any Options-API components.
- Dev: `bench set-config ignore_csrf 1`; Vite proxy auto-detects the bench port.
- `markRaw` every custom node in `nodeTypes`; import `@vue-flow/core/dist/style.css`.
- Node 20.19+ / 22.12+ for the frappe-ui toolchain.
