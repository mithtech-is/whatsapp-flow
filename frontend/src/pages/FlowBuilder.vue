<script setup>
import { ref, onMounted, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { call, Button } from 'frappe-ui'
import FlowNode from '../components/FlowNode.vue'
import NodeMenu from '../components/NodeMenu.vue'

const nodeMenuOpen = ref(false)

const route = useRoute()
const router = useRouter()
const flow = route.params.flow

const TYPES = ['start', 'text', 'say', 'greeting', 'media', 'input', 'gather', 'buttons', 'menu',
  'list', 'poll', 'condition', 'condition_router', 'set_variable', 'response_saver',
  'api_call', 'http_callback', 'webhook', 'make_request', 'timing', 'delay',
  'transfer', 'assign', 'tag', 'set_labels', 'note', 'disable_auto_reply',
  'phonebook', 'wa_form', 'google',
  'goto', 'goto_flow', 'end', 'hangup', 'ai_response']
const nodeTypes = Object.fromEntries(TYPES.map((t) => [t, markRaw(FlowNode)]))

const nodes = ref([])
const edges = ref([])
const selected = ref(null)
const errors = ref([])
const saving = ref(false)

const simOpen = ref(false)
const simInput = ref('')
const simSession = ref(null)
const simLog = ref([])

const { onConnect, addEdges, onNodeClick, onNodeDragStop, onPaneClick } = useVueFlow()

function toVueFlow(graph) {
  nodes.value = (graph.nodes || []).map((n) => ({
    id: n.id, type: n.type, position: n.position || { x: 0, y: 0 }, data: { ...(n.data || {}) },
  }))
  edges.value = (graph.edges || []).map((e) => ({
    id: e.id || `${e.source}-${e.target}-${e.sourceHandle || ''}`,
    source: e.source, target: e.target, sourceHandle: e.sourceHandle || null,
    label: e.sourceHandle || '', animated: true,
  }))
}
function toGraph() {
  return {
    version: 1,
    nodes: nodes.value.map((n) => ({ id: n.id, type: n.type, position: n.position, data: { ...n.data } })),
    edges: edges.value.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle || null })),
  }
}
async function load() {
  const r = await call('whatsapp_flow.api.v1.flows.get_graph', { flow })
  toVueFlow(r.graph || { nodes: [], edges: [] })
}

onConnect((params) => {
  const handle = params.sourceHandle || null
  addEdges([{ ...params, id: `${params.source}-${params.target}-${handle || ''}`, sourceHandle: handle, label: handle || '', animated: true }])
})
onNodeClick(({ node }) => { selected.value = node })
onPaneClick(() => { selected.value = null })
onNodeDragStop(({ node }) => {
  const n = nodes.value.find((x) => x.id === node.id)
  if (n) n.position = node.position
})

function addNode(payload) {
  // Accept either a bare type string (legacy) or {type, variant, title} from NodeMenu.
  const { type, variant, title } = typeof payload === 'string' ? { type: payload } : payload
  const id = 'n_' + Math.random().toString(36).slice(2, 8)
  const data = { label: title || '' }
  if (variant === 'template') data.message_type = 'Template'
  const n = { id, type, position: { x: 160 + Math.random() * 120, y: 120 + Math.random() * 120 }, data }
  nodes.value.push(n)
  selected.value = n
  nodeMenuOpen.value = false
}
async function save() {
  saving.value = true
  try { await call('whatsapp_flow.api.v1.flows.save_graph', { flow, graph: toGraph() }) }
  finally { saving.value = false }
}
async function publish() {
  await save()
  const r = await call('whatsapp_flow.api.v1.flows.publish', { flow })
  errors.value = r.errors || []
  if (r.ok) window.alert('Published v' + r.version)
}

async function runSim() {
  if (!simInput.value.trim()) return
  const r = await call('whatsapp_flow.api.v1.flows.simulate', { flow, inbound: simInput.value, session_state: simSession.value })
  simLog.value.push({ me: simInput.value, bot: r.outbound })
  simSession.value = r.session
  simInput.value = ''
}
function resetSim() { simSession.value = null; simLog.value = [] }

onMounted(load)
</script>

<template>
  <div class="wd-builder">
    <header class="wd-topbar">
      <button class="wd-back" @click="router.push('/flows')">← Flows</button>
      <span class="wd-flowname">{{ flow }}</span>
      <div class="ml-auto flex items-center gap-2">
        <button class="wd-btn wd-btn--primary" @click="nodeMenuOpen = true">＋ Add node</button>
        <button class="wd-btn" @click="simOpen = !simOpen">Simulate</button>
        <button class="wd-btn" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
        <button class="wd-btn wd-btn--primary" @click="publish">Publish</button>
      </div>
    </header>

    <div v-if="errors.length" class="wd-errors">
      <div v-for="(e, i) in errors" :key="i">• {{ e }}</div>
    </div>

    <div class="wd-main">
      <!-- canvas -->
      <div class="wd-canvas">
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" :node-types="nodeTypes" :fit-view-on-init="true"
                 :default-edge-options="{ animated: true, type: 'smoothstep', style: { stroke: '#94a3b8' } }">
          <Background :gap="18" pattern-color="#e2e8f0" />
          <Controls />
        </VueFlow>
        <div v-if="!nodes.length" class="wd-hint">Click <b>＋ Add node</b> to start building your flow.</div>
        <NodeMenu :open="nodeMenuOpen" @add="addNode" @close="nodeMenuOpen = false" />
      </div>

      <!-- simulator -->
      <aside v-if="simOpen" class="wd-panel">
        <div class="wd-sim">
          <div class="wd-sim__head">
            <span>Simulator <span class="wd-sim__tag">draft</span></span>
            <button class="wd-chip" @click="resetSim">Reset</button>
          </div>
          <div class="wd-sim__log">
            <div v-for="(t, i) in simLog" :key="i">
              <div class="wd-sim__me">{{ t.me }}</div>
              <div v-for="(o, j) in t.bot" :key="j" class="wd-sim__bot">
                {{ o.text || (o.buttons ? '[buttons: ' + o.buttons.map(b => b.title).join(', ') + ']' : o.template) }}
              </div>
            </div>
            <p v-if="!simLog.length" class="wd-sim__hint">Type a customer message below to test the flow.</p>
          </div>
          <div class="wd-sim__input">
            <input v-model="simInput" placeholder="Customer message…" @keyup.enter="runSim" />
            <button class="wd-btn wd-btn--primary" @click="runSim">Send</button>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.wd-builder { display: flex; flex-direction: column; height: 100%; background: #f1f5f9; color: #0f172a; }
.wd-topbar { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #fff; border-bottom: 1px solid #e5e7eb; }
.wd-back { font-size: 13px; color: #16a34a; font-weight: 600; }
.wd-flowname { font-weight: 700; font-size: 15px; }
.wd-btn { font-size: 13px; font-weight: 600; padding: 6px 14px; border-radius: 8px; border: 1px solid #e5e7eb; background: #fff; color: #334155; }
.wd-btn:hover { background: #f8fafc; }
.wd-btn--primary { background: #16a34a; border-color: #16a34a; color: #fff; }
.wd-btn--primary:hover { background: #15803d; }
.wd-errors { background: #fef2f2; color: #b91c1c; padding: 8px 14px; font-size: 13px; border-bottom: 1px solid #fecaca; }
.wd-main { display: flex; min-height: 0; flex: 1; }

.wd-palette { width: 180px; flex-shrink: 0; overflow-y: auto; background: #fff; border-right: 1px solid #e5e7eb; padding: 10px; }
.wd-palette__group { margin-bottom: 14px; }
.wd-palette__title { font-size: 10px; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 6px; padding-left: 4px; }
.wd-palette__item { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; font-size: 13px; color: #334155; padding: 7px 8px; border-radius: 8px; }
.wd-palette__item:hover { background: #f1f5f9; }
.wd-palette__icon { width: 20px; text-align: center; }

.wd-canvas { position: relative; flex: 1; min-width: 0; background: #f8fafc; }
.wd-hint { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #94a3b8; font-size: 14px; pointer-events: none; }
.wd-canvas :deep(.vue-flow__edge-path) { stroke-width: 2; }

.wd-panel { width: 300px; flex-shrink: 0; overflow-y: auto; background: #fff; border-left: 1px solid #e5e7eb; padding: 14px; }
.wd-panel__head { display: flex; align-items: center; margin-bottom: 12px; }
.wd-panel__type { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #16a34a; background: #dcfce7; padding: 3px 8px; border-radius: 6px; }
.wd-del { margin-left: auto; font-size: 12px; color: #ef4444; font-weight: 600; }
.wd-panel__empty { color: #94a3b8; font-size: 13px; text-align: center; padding: 40px 0; }

.wd-sim { margin-top: 16px; border-top: 1px solid #e5e7eb; padding-top: 12px; }
.wd-sim__head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.wd-sim__tag { font-size: 10px; color: #94a3b8; font-weight: 500; }
.wd-chip { font-size: 12px; color: #16a34a; font-weight: 600; }
.wd-sim__log { max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
.wd-sim__me { align-self: flex-end; background: #dcfce7; color: #166534; border-radius: 10px 10px 2px 10px; padding: 5px 9px; font-size: 13px; max-width: 85%; }
.wd-sim__bot { align-self: flex-start; background: #f1f5f9; color: #334155; border-radius: 10px 10px 10px 2px; padding: 5px 9px; font-size: 13px; max-width: 85%; margin-top: 2px; }
.wd-sim__input { display: flex; gap: 6px; margin-top: 10px; }
.wd-sim__input input { flex: 1; border: 1px solid #e5e7eb; border-radius: 8px; padding: 7px 10px; font-size: 13px; outline: none; }
.wd-sim__input input:focus { border-color: #16a34a; }
.wd-sim__hint { color: #94a3b8; font-size: 13px; text-align: center; padding: 20px 8px; }
</style>
