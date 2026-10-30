<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { call } from 'frappe-ui'
import { io } from 'socket.io-client'

const me = ref(window.user || null)
const isManager = ref(false)

const FILTERS = [
  { key: 'Open', label: 'Open' },
  { key: 'Mine', label: 'Mine' },
  { key: 'Unread', label: 'Unread' },
  { key: 'All', label: 'All' },
]
const filter = ref('Open')
const search = ref('')
const conversations = ref([])
const loadingList = ref(false)

const active = ref(null)
const messages = ref([])
const loadingThread = ref(false)
const contact = ref(null)
const notes = ref([])
const newNote = ref('')
const draft = ref('')
const sending = ref(false)
const threadEl = ref(null)

const canned = ref([])
const cannedOpen = ref(false)
const templates = ref([])
const templatesOpen = ref(false)
const tplParam = ref(null)
const tplParamErr = ref('')
function tag(v) { return `{{${v}}}` }
const actions = ref([])
const teamAgents = ref([])
const reassignOpen = ref(false)
const tagInput = ref('')

let socket = null, listTimer = null, threadTimer = null

const filtered = computed(() => {
  let rows = conversations.value
  if (filter.value === 'Mine') rows = rows.filter((r) => r.assignee === me.value)
  if (filter.value === 'Unread') rows = rows.filter((r) => (r.unread || 0) > 0)
  return rows
})
const assignedToMe = computed(() => active.value && contact.value?.assignee === me.value)

const AVATAR_COLORS = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316']
function avatarColor(s) {
  let h = 0
  for (const c of (s || '')) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}
function initials(name) {
  return (name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()
}
function timeOf(dt) {
  if (!dt) return ''
  return new Date(dt.replace(' ', 'T')).toLocaleString([], { hour: '2-digit', minute: '2-digit' })
}
function dayOf(dt) {
  if (!dt) return ''
  return new Date(dt.replace(' ', 'T')).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

async function loadMyStatus() {
  try { const s = await call('whatsapp_flow.api.v1.agents.my_status'); isManager.value = s.is_manager } catch (e) {}
}
async function loadConversations() {
  loadingList.value = true
  try {
    const listStatus = filter.value === 'Mine' || filter.value === 'Unread' ? 'All' : filter.value
    conversations.value = await call('whatsapp_flow.api.v1.inbox.list_conversations', { status: listStatus, search: search.value || null })
  } finally { loadingList.value = false }
}
async function select(row) {
  active.value = row
  messages.value = []; contact.value = null; notes.value = []; reassignOpen.value = false
  loadingThread.value = true
  try {
    const [msgs, c, ns] = await Promise.all([
      call('whatsapp_flow.api.v1.inbox.get_messages', { contact: row.contact }),
      call('whatsapp_flow.api.v1.inbox.get_contact', { contact: row.contact }),
      call('whatsapp_flow.api.v1.tools.list_notes', { contact: row.contact }),
    ])
    messages.value = msgs; contact.value = c; notes.value = ns
    loadActions()
    if (row.unread) { call('whatsapp_flow.endpoints.chat.mark_as_read', { room: row.contact }).catch(() => {}); row.unread = 0 }
    scrollThread()
  } finally { loadingThread.value = false }
}
function scrollThread() { nextTick(() => { if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight }) }
async function refreshThread() {
  if (!active.value) return
  messages.value = await call('whatsapp_flow.api.v1.inbox.get_messages', { contact: active.value.contact })
  scrollThread()
}
async function send() {
  const content = draft.value.trim()
  if (!content || !active.value || sending.value) return
  sending.value = true
  try { await call('whatsapp_flow.api.v1.inbox.send_message', { contact: active.value.contact, content }); draft.value = ''; await refreshThread() }
  catch (e) { window.alert(e?.messages?.join('\n') || e?.message || 'Failed to send') }
  finally { sending.value = false }
}

async function assignToMe() { await call('whatsapp_flow.api.v1.agents.assign_conversation', { contact: active.value.contact }); await select(active.value); loadConversations() }
async function openReassign() {
  reassignOpen.value = !reassignOpen.value
  if (reassignOpen.value && contact.value?.team) teamAgents.value = await call('whatsapp_flow.api.v1.agents.team_agents', { team: contact.value.team })
}
async function reassign(agent) { await call('whatsapp_flow.api.v1.agents.assign_conversation', { contact: active.value.contact, agent }); reassignOpen.value = false; await select(active.value); loadConversations() }
async function resolve() { await call('whatsapp_flow.api.v1.agents.resolve_conversation', { contact: active.value.contact }); await select(active.value); loadConversations() }

async function toggleCanned() { cannedOpen.value = !cannedOpen.value; templatesOpen.value = false; if (cannedOpen.value && !canned.value.length) canned.value = await call('whatsapp_flow.api.v1.tools.list_canned', { team: contact.value?.team || null }) }
async function applyCanned(sc) { const r = await call('whatsapp_flow.api.v1.tools.render_canned', { contact: active.value.contact, shortcut: sc }); draft.value = draft.value ? draft.value + '\n' + r.message : r.message; cannedOpen.value = false }
async function toggleTemplates() { templatesOpen.value = !templatesOpen.value; cannedOpen.value = false; if (templatesOpen.value && !templates.value.length) templates.value = await call('whatsapp_flow.api.v1.inbox.list_templates') }
async function sendTemplate(tpl) {
  templatesOpen.value = false
  let detail = null
  try { detail = await call('whatsapp_flow.api.v1.templates.template_detail', { name: tpl.name }) } catch (e) { /* fall back to paramless */ }
  if (detail && detail.variables.length) {
    const values = {}; detail.variables.forEach((v) => (values[v] = ''))
    tplParam.value = { tpl, detail, values }
    return
  }
  await doSendTemplate(tpl.name, null)
}
async function doSendTemplate(name, body_param) {
  try { await call('whatsapp_flow.api.v1.inbox.send_message', { contact: active.value.contact, template: name, body_param }); await refreshThread() }
  catch (e) { window.alert(e?.message || 'Failed') }
}
async function confirmTemplate() {
  const { tpl, detail, values } = tplParam.value
  const missing = detail.variables.filter((v) => !String(values[v] || '').trim())
  if (missing.length) { tplParamErr.value = `Fill all variables (${missing.join(', ')}).`; return }
  const obj = {}; detail.variables.forEach((v, i) => { obj[String(i + 1)] = values[v] })
  tplParam.value = null; tplParamErr.value = ''
  await doSendTemplate(tpl.name, JSON.stringify(obj))
}
const tplParamPreview = computed(() => {
  if (!tplParam.value) return ''
  let body = tplParam.value.detail.body || ''
  for (const v of tplParam.value.detail.variables) {
    const val = tplParam.value.values[v] || `{{${v}}}`
    body = body.replaceAll(`{{${v}}}`, val).replaceAll(`{{ ${v} }}`, val)
  }
  return body
})

async function loadActions() { actions.value = await call('whatsapp_flow.api.v1.actions.list_actions', { team: contact.value?.team || null }) }
async function runAction(a) { try { const res = await call('whatsapp_flow.api.v1.actions.execute_action', { action: a.name, contact: active.value.contact }); if (res?.type === 'URL' && res.url) window.open(res.url, res.new_tab ? '_blank' : '_self'); else window.alert('Action sent.') } catch (e) { window.alert(e?.message || 'Action failed') } }

async function addNote() { const content = newNote.value.trim(); if (!content) return; await call('whatsapp_flow.api.v1.tools.add_note', { contact: active.value.contact, content }); newNote.value = ''; notes.value = await call('whatsapp_flow.api.v1.tools.list_notes', { contact: active.value.contact }) }
async function addTag() { const tag = tagInput.value.trim(); if (!tag) return; await call('whatsapp_flow.api.v1.tools.add_tag', { contact: active.value.contact, tag }); tagInput.value = ''; contact.value.tags = await call('whatsapp_flow.api.v1.tools.list_tags', { contact: active.value.contact }) }
async function removeTag(tag) { await call('whatsapp_flow.api.v1.tools.remove_tag', { contact: active.value.contact, tag }); contact.value.tags = await call('whatsapp_flow.api.v1.tools.list_tags', { contact: active.value.contact }) }

function onRealtime(p) { loadConversations(); if (active.value && p?.contact === active.value.contact) refreshThread() }
function startRealtime() {
  try { socket = io({ path: '/socket.io', withCredentials: true }); socket.on('whatsapp_flow:update', onRealtime) } catch (e) { socket = null }
  listTimer = setInterval(loadConversations, 12000)
  threadTimer = setInterval(() => active.value && refreshThread(), 6000)
}
onMounted(() => { loadMyStatus(); loadConversations(); startRealtime() })
onUnmounted(() => { if (socket) socket.disconnect(); if (listTimer) clearInterval(listTimer); if (threadTimer) clearInterval(threadTimer) })
</script>

<template>
  <div class="ibx">
    <!-- LEFT: list -->
    <aside class="ibx__list">
      <div class="ibx__listhead">
        <h1>Inbox</h1>
        <span class="ibx__count">{{ filtered.length }}</span>
      </div>
      <div class="ibx__search">
        <input v-model="search" type="search" placeholder="Search conversations…" @keyup.enter="loadConversations" />
      </div>
      <div class="ibx__chips">
        <button v-for="f in FILTERS" :key="f.key" class="chip" :class="{ on: filter === f.key }" @click="filter = f.key">{{ f.label }}</button>
      </div>
      <div class="ibx__rows">
        <div v-if="loadingList" class="ibx__empty">Loading…</div>
        <p v-else-if="!filtered.length" class="ibx__empty">No conversations.</p>
        <button v-for="row in filtered" :key="row.contact" class="row" :class="{ on: active?.contact === row.contact }" @click="select(row)">
          <span class="ava" :style="{ background: avatarColor(row.contact_name || row.number) }">{{ initials(row.contact_name) }}</span>
          <div class="row__mid">
            <div class="row__top"><span class="row__name">{{ row.contact_name || row.number }}</span><span class="row__time">{{ dayOf(row.modified) }}</span></div>
            <div class="row__bot"><span class="row__last">{{ row.last_message || '—' }}</span><span v-if="row.unread" class="badge">{{ row.unread }}</span></div>
          </div>
          <span v-if="!row.window_open" class="row__win" title="24h window closed">🔒</span>
        </button>
      </div>
    </aside>

    <!-- CENTER: thread -->
    <section class="ibx__thread">
      <template v-if="active">
        <header class="th__head">
          <span class="ava ava--sm" :style="{ background: avatarColor(active.contact_name || active.number) }">{{ initials(active.contact_name) }}</span>
          <div class="th__id"><div class="th__name">{{ active.contact_name || active.number }}</div><div class="th__num">{{ active.number }}</div></div>
          <div class="th__actions">
            <span v-if="contact?.issue" class="pill" :class="'pill--' + (contact.issue.status || '').toLowerCase()">{{ contact.issue.status }}</span>
            <button v-if="!assignedToMe" class="btn" @click="assignToMe">Assign to me</button>
            <div v-if="isManager" class="rel">
              <button class="btn" @click="openReassign">Reassign ▾</button>
              <div v-if="reassignOpen" class="menu">
                <p v-if="!teamAgents.length" class="menu__empty">No team / agents.</p>
                <button v-for="a in teamAgents" :key="a.user" class="menu__item" @click="reassign(a.user)">
                  <span>{{ a.full_name || a.user }}</span><span class="menu__meta">{{ a.availability }} · {{ a.load }}</span>
                </button>
              </div>
            </div>
            <button class="btn btn--green" @click="resolve">Resolve</button>
          </div>
        </header>

        <div ref="threadEl" class="th__msgs">
          <div v-if="loadingThread" class="ibx__empty">Loading…</div>
          <div v-for="m in messages" :key="m.name" class="msg" :class="m.type === 'Outgoing' ? 'msg--out' : 'msg--in'">
            <div class="bubble">
              <div v-if="m.content_type !== 'text'" class="bubble__kind">{{ m.message_type === 'Template' ? '📄 template' : '📎 ' + m.content_type }}</div>
              <p class="bubble__text">{{ m.message || m.attach || '—' }}</p>
              <span class="bubble__time">{{ timeOf(m.creation) }}<template v-if="m.type === 'Outgoing'"> · {{ m.status }}</template></span>
            </div>
          </div>
        </div>

        <footer class="th__composer">
          <p v-if="!active.window_open" class="th__note">⏳ 24-hour window closed — only approved templates can be sent.</p>
          <div class="cmp">
            <div class="cmp__tools">
              <button class="icon" title="Canned responses" @click="toggleCanned">⚡</button>
              <button class="icon" title="Send template" @click="toggleTemplates">📄</button>
            </div>
            <div v-if="cannedOpen" class="pop">
              <p v-if="!canned.length" class="pop__empty">No canned responses.</p>
              <button v-for="cr in canned" :key="cr.name" class="pop__item" @click="applyCanned(cr.shortcut)"><b>{{ cr.shortcut }}</b> {{ cr.title }}</button>
            </div>
            <div v-if="templatesOpen" class="pop">
              <p class="pop__hdr">Approved templates</p>
              <p v-if="!templates.length" class="pop__empty">None available.</p>
              <button v-for="tpl in templates" :key="tpl.name" class="pop__item" @click="sendTemplate(tpl)"><b>{{ tpl.template_name }}</b> <span class="pop__meta">{{ tpl.language_code }}</span></button>
            </div>
            <textarea v-model="draft" rows="1" placeholder="Type a message…  (Enter to send)" @keydown.enter.exact.prevent="send" />
            <button class="btn btn--green cmp__send" :disabled="sending" @click="send">Send</button>
          </div>
        </footer>
      </template>
      <div v-else class="th__blank"><div class="th__blankart">💬</div><p>Select a conversation</p></div>
    </section>

    <!-- RIGHT: contact -->
    <aside v-if="active && contact" class="ibx__panel">
      <div class="pan__top">
        <span class="ava ava--lg" :style="{ background: avatarColor(contact.contact_name || contact.number) }">{{ initials(contact.contact_name) }}</span>
        <div class="pan__name">{{ contact.contact_name || contact.number }}</div>
        <div class="pan__num">{{ contact.number }}</div>
      </div>

      <div class="pan__sec">
        <div class="pan__row"><span>Assignee</span><b>{{ contact.assignee || '—' }}</b></div>
        <div class="pan__row"><span>Team</span><b>{{ contact.team || '—' }}</b></div>
        <div class="pan__row"><span>Bot</span><b>{{ contact.bot_active ? 'Active' : 'Paused' }}</b></div>
        <div class="pan__row"><span>Opted out</span><b>{{ contact.marketing_opt_out ? 'Yes' : 'No' }}</b></div>
      </div>

      <div v-if="contact.issue" class="pan__card">
        <div class="pan__cardhdr">Conversation (Issue)</div>
        <div class="pan__row"><span>Status</span><b>{{ contact.issue.status }}</b></div>
        <div class="pan__row"><span>SLA</span><b>{{ contact.issue.agreement_status || '—' }}</b></div>
      </div>

      <div v-if="actions.length" class="pan__block">
        <div class="pan__h">Actions</div>
        <div class="pan__actions"><button v-for="a in actions" :key="a.name" class="btn btn--sm" @click="runAction(a)">{{ a.title }}</button></div>
      </div>

      <div class="pan__block">
        <div class="pan__h">Tags</div>
        <div class="tags">
          <span v-for="t in contact.tags" :key="t" class="tag">{{ t }}<button @click="removeTag(t)">×</button></span>
        </div>
        <input v-model="tagInput" class="pan__in" placeholder="Add tag…" @keyup.enter="addTag" />
      </div>

      <div class="pan__block">
        <div class="pan__h">Private notes</div>
        <div v-for="n in notes" :key="n.name" class="note"><div v-html="n.content" /><div class="note__by">{{ n.owner }} · {{ dayOf(n.creation) }}</div></div>
        <textarea v-model="newNote" rows="2" class="pan__in" placeholder="Add a private note…" />
        <button class="btn btn--sm" @click="addNote">Add note</button>
      </div>
    </aside>

    <!-- Template parameter fill -->
    <div v-if="tplParam" class="tpm">
      <div class="tpm__backdrop" @click="tplParam = null" />
      <div class="tpm__box">
        <div class="tpm__head">
          <b>{{ tplParam.tpl.template_name }}</b>
          <button class="tpm__x" @click="tplParam = null">×</button>
        </div>
        <div class="tpm__body">
          <div class="tpm__label">Fill template variables</div>
          <div v-for="v in tplParam.detail.variables" :key="v" class="tpm__var">
            <span class="tpm__tag">{{ tag(v) }}</span>
            <input v-model="tplParam.values[v]" :placeholder="`Value for ${v}`" />
          </div>
          <div class="tpm__label" style="margin-top:12px">Preview</div>
          <div class="tpm__bubble">{{ tplParamPreview }}</div>
          <p v-if="tplParamErr" class="tpm__err">{{ tplParamErr }}</p>
        </div>
        <div class="tpm__foot">
          <button class="btn" @click="tplParam = null">Cancel</button>
          <button class="btn btn--green" @click="confirmTemplate">Send</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tpm { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; }
.tpm__backdrop { position: absolute; inset: 0; background: rgba(2,6,23,0.4); }
.tpm__box { position: relative; width: 440px; max-width: 94vw; background: #fff; border-radius: 16px; box-shadow: 0 24px 60px rgba(2,6,23,0.25); }
.tpm__head { display: flex; align-items: center; padding: 15px 18px; border-bottom: 1px solid #f1f5f9; }
.tpm__head b { font-size: 15px; }
.tpm__x { margin-left: auto; font-size: 22px; color: #94a3b8; line-height: 1; }
.tpm__body { padding: 16px 18px; }
.tpm__label { font-size: 10px; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px; }
.tpm__var { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tpm__tag { font-family: ui-monospace, monospace; font-size: 11px; font-weight: 700; color: #0369a1; background: #e0f2fe; border-radius: 6px; padding: 3px 7px; white-space: nowrap; }
.tpm__var input { flex: 1; border: 1px solid #e5e7eb; border-radius: 9px; padding: 7px 11px; font-size: 13px; outline: none; }
.tpm__var input:focus { border-color: #10b981; }
.tpm__bubble { background: #d9fdd3; border-radius: 10px 10px 10px 2px; padding: 10px 12px; font-size: 13px; white-space: pre-wrap; word-break: break-word; }
.tpm__err { color: #b91c1c; font-size: 12px; margin-top: 8px; }
.tpm__foot { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 18px; border-top: 1px solid #f1f5f9; }
.btn--green { background: #10b981; border-color: #10b981; color: #fff; }


.ibx { display: flex; height: 100vh; background: #f8fafc; color: #0f172a; font-size: 14px; }
.ava { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-weight: 700; font-size: 14px; flex-shrink: 0; }
.ava--sm { width: 36px; height: 36px; font-size: 13px; }
.ava--lg { width: 64px; height: 64px; font-size: 22px; }
.btn { font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 8px; border: 1px solid #e5e7eb; background: #fff; color: #334155; white-space: nowrap; }
.btn:hover { background: #f1f5f9; }
.btn--green { background: #10b981; border-color: #10b981; color: #fff; }
.btn--green:hover { background: #059669; }
.btn--sm { padding: 4px 10px; font-size: 12px; }

/* list */
.ibx__list { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; background: #fff; border-right: 1px solid #e5e7eb; }
.ibx__listhead { display: flex; align-items: center; gap: 8px; padding: 16px 16px 8px; }
.ibx__listhead h1 { font-size: 20px; font-weight: 700; }
.ibx__count { font-size: 12px; font-weight: 700; color: #10b981; background: #d1fae5; border-radius: 10px; padding: 1px 8px; }
.ibx__search { padding: 4px 12px 8px; }
.ibx__search input { width: 100%; border: 1px solid #e5e7eb; border-radius: 10px; padding: 8px 12px; font-size: 13px; background: #f8fafc; outline: none; }
.ibx__search input:focus { border-color: #10b981; background: #fff; }
.ibx__chips { display: flex; gap: 6px; padding: 0 12px 8px; }
.chip { font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 999px; color: #64748b; background: #f1f5f9; }
.chip.on { background: #10b981; color: #fff; }
.ibx__rows { flex: 1; overflow-y: auto; }
.ibx__empty { padding: 32px 16px; text-align: center; color: #94a3b8; font-size: 13px; }
.row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 16px; text-align: left; border-bottom: 1px solid #f1f5f9; }
.row:hover { background: #f8fafc; }
.row.on { background: #ecfdf5; }
.row__mid { min-width: 0; flex: 1; }
.row__top { display: flex; align-items: center; gap: 6px; }
.row__name { font-weight: 600; color: #0f172a; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row__time { font-size: 11px; color: #94a3b8; }
.row__bot { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.row__last { font-size: 13px; color: #64748b; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.badge { font-size: 11px; font-weight: 700; color: #fff; background: #10b981; border-radius: 10px; min-width: 18px; height: 18px; display: grid; place-items: center; padding: 0 5px; }
.row__win { font-size: 12px; }

/* thread */
.ibx__thread { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.th__head { display: flex; align-items: center; gap: 12px; padding: 12px 18px; background: #fff; border-bottom: 1px solid #e5e7eb; }
.th__id { flex: 1; min-width: 0; }
.th__name { font-weight: 700; }
.th__num { font-size: 12px; color: #94a3b8; }
.th__actions { display: flex; align-items: center; gap: 8px; }
.pill { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: #e0f2fe; color: #0369a1; }
.pill--resolved, .pill--closed { background: #dcfce7; color: #15803d; }
.rel { position: relative; }
.menu { position: absolute; right: 0; top: 36px; z-index: 20; width: 220px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 8px 24px rgba(2,6,23,0.12); padding: 4px; }
.menu__item { display: flex; width: 100%; padding: 8px 10px; border-radius: 8px; font-size: 13px; }
.menu__item:hover { background: #f1f5f9; }
.menu__meta { margin-left: auto; font-size: 11px; color: #94a3b8; }
.menu__empty { padding: 8px 10px; font-size: 12px; color: #94a3b8; }
.th__msgs { flex: 1; overflow-y: auto; padding: 18px; background: #efeae2; display: flex; flex-direction: column; gap: 4px; }
.msg { display: flex; }
.msg--out { justify-content: flex-end; }
.bubble { max-width: 70%; border-radius: 8px; padding: 6px 9px 4px; box-shadow: 0 1px 1px rgba(0,0,0,0.08); position: relative; }
.msg--in .bubble { background: #fff; }
.msg--out .bubble { background: #d9fdd3; }
.bubble__kind { font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 2px; }
.bubble__text { font-size: 14px; color: #111827; white-space: pre-wrap; word-break: break-word; }
.bubble__time { display: block; text-align: right; font-size: 10px; color: #94a3b8; margin-top: 2px; }
.th__composer { background: #f8fafc; border-top: 1px solid #e5e7eb; padding: 10px 14px; }
.th__note { font-size: 12px; color: #92400e; background: #fef3c7; border-radius: 8px; padding: 6px 10px; margin-bottom: 8px; }
.cmp { position: relative; display: flex; align-items: flex-end; gap: 8px; }
.cmp__tools { display: flex; gap: 2px; }
.icon { width: 36px; height: 36px; border-radius: 8px; font-size: 16px; color: #64748b; }
.icon:hover { background: #e2e8f0; }
.pop { position: absolute; bottom: 48px; left: 0; z-index: 20; width: 300px; max-height: 260px; overflow-y: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 8px 24px rgba(2,6,23,0.12); padding: 4px; }
.pop__hdr { font-size: 10px; text-transform: uppercase; color: #94a3b8; padding: 6px 10px 2px; }
.pop__item { display: block; width: 100%; text-align: left; padding: 8px 10px; border-radius: 8px; font-size: 13px; }
.pop__item:hover { background: #f1f5f9; }
.pop__meta { color: #94a3b8; font-size: 11px; }
.pop__empty { padding: 10px; font-size: 12px; color: #94a3b8; }
.cmp textarea { flex: 1; max-height: 140px; min-height: 40px; resize: none; border: 1px solid #e5e7eb; border-radius: 20px; padding: 9px 16px; font-size: 14px; background: #fff; outline: none; }
.cmp textarea:focus { border-color: #10b981; }
.cmp__send { border-radius: 20px; height: 40px; }
.th__blank { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #94a3b8; gap: 10px; }
.th__blankart { font-size: 48px; opacity: 0.5; }

/* panel */
.ibx__panel { width: 300px; flex-shrink: 0; overflow-y: auto; background: #fff; border-left: 1px solid #e5e7eb; padding: 18px; }
.pan__top { display: flex; flex-direction: column; align-items: center; gap: 6px; padding-bottom: 14px; border-bottom: 1px solid #f1f5f9; }
.pan__name { font-weight: 700; font-size: 16px; }
.pan__num { font-size: 13px; color: #94a3b8; }
.pan__sec { padding: 12px 0; border-bottom: 1px solid #f1f5f9; }
.pan__row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: 13px; }
.pan__row span { color: #94a3b8; }
.pan__row b { color: #0f172a; font-weight: 600; }
.pan__card { margin-top: 12px; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; }
.pan__cardhdr { font-weight: 700; font-size: 13px; margin-bottom: 4px; }
.pan__block { padding: 14px 0; border-top: 1px solid #f1f5f9; }
.pan__h { font-size: 11px; text-transform: uppercase; font-weight: 700; color: #94a3b8; margin-bottom: 8px; }
.pan__actions { display: flex; flex-wrap: wrap; gap: 6px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tag { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; background: #f1f5f9; border-radius: 999px; padding: 2px 8px; }
.tag button { color: #94a3b8; }
.tag button:hover { color: #ef4444; }
.pan__in { width: 100%; border: 1px solid #e5e7eb; border-radius: 8px; padding: 7px 10px; font-size: 13px; outline: none; margin-bottom: 8px; }
.pan__in:focus { border-color: #10b981; }
.note { background: #f8fafc; border-radius: 8px; padding: 8px 10px; font-size: 13px; margin-bottom: 8px; }
.note__by { font-size: 10px; color: #94a3b8; margin-top: 4px; }
</style>
