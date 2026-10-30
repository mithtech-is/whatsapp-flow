<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { call } from 'frappe-ui'

const loading = ref(true)
const campaigns = ref([])

const showModal = ref(false)
const saving = ref(false)
const err = ref('')
const opts = ref({ templates: [], all_templates: [], segments: [], recipient_lists: [], accounts: [] })
const form = ref(null)
const segPreview = ref(null)

// Template param fill
const tpl = ref(null)          // { body, variables:[...], header, footer }
const tplLoading = ref(false)
const varValues = ref({})

async function loadTemplate(name) {
  tpl.value = null; varValues.value = {}
  if (!name) return
  tplLoading.value = true
  try {
    const d = await call('whatsapp_flow.api.v1.templates.template_detail', { name })
    tpl.value = d
    for (const v of d.variables) varValues.value[v] = ''
  } catch (e) { tpl.value = null }
  finally { tplLoading.value = false }
}

function tag(v) { return `{{${v}}}` }

const preview = computed(() => {
  if (!tpl.value) return ''
  let body = tpl.value.body || ''
  for (const v of tpl.value.variables) {
    const val = varValues.value[v] || `{{${v}}}`
    body = body.replaceAll(`{{${v}}}`, val).replaceAll(`{{ ${v} }}`, val)
  }
  return body
})

async function load() {
  loading.value = true
  try { campaigns.value = await call('whatsapp_flow.api.v1.campaigns.list_campaigns') }
  finally { loading.value = false }
}

async function openNew() {
  err.value = ''; segPreview.value = null
  opts.value = await call('whatsapp_flow.api.v1.campaigns.new_campaign_options')
  form.value = {
    title: '', template: opts.value.templates[0]?.name || '',
    whatsapp_account: opts.value.accounts[0]?.name || '',
    audience: 'segment', wd_segment: opts.value.segments[0]?.name || '', recipient_list: '',
    wd_respect_opt_out: true, wd_throttle_per_min: 0, scheduled_time: '',
  }
  showModal.value = true
  loadTemplate(form.value.template)
}

watch(() => form.value?.template, (name) => { if (showModal.value) loadTemplate(name) })

async function previewSegment() {
  if (!form.value.wd_segment) return
  try {
    const r = await call('whatsapp_flow.api.v1.campaigns.preview_segment', { segment: form.value.wd_segment })
    segPreview.value = r.count
  } catch (e) { segPreview.value = null }
}

async function createCampaign() {
  if (!form.value.title) { err.value = 'Give the campaign a title.'; return }
  // Build template_variables in body-token order (Common: same values for all recipients).
  let template_variables = null
  if (tpl.value && tpl.value.variables.length) {
    const missing = tpl.value.variables.filter((v) => !String(varValues.value[v] || '').trim())
    if (missing.length) { err.value = `Fill all template variables (${missing.join(', ')}).`; return }
    const obj = {}
    tpl.value.variables.forEach((v, i) => { obj[String(i + 1)] = varValues.value[v] })
    template_variables = obj
  }
  saving.value = true; err.value = ''
  const payload = {
    title: form.value.title, template: form.value.template,
    whatsapp_account: form.value.whatsapp_account,
    template_variables,
    wd_segment: form.value.audience === 'segment' ? form.value.wd_segment : '',
    recipient_list: form.value.audience === 'list' ? form.value.recipient_list : '',
    wd_respect_opt_out: form.value.wd_respect_opt_out,
    wd_throttle_per_min: form.value.wd_throttle_per_min,
    scheduled_time: form.value.scheduled_time || '',
  }
  try {
    await call('whatsapp_flow.api.v1.campaigns.create_campaign', { payload: JSON.stringify(payload) })
    showModal.value = false
    await load()
  } catch (e) { err.value = e.messages?.join(', ') || e.message || 'Failed to create.' }
  finally { saving.value = false }
}

async function act(c, action) {
  const fn = { pause: 'pause_campaign', resume: 'resume_campaign', cancel: 'cancel_campaign' }[action]
  if (action === 'cancel' && !window.confirm(`Cancel "${c.title}"?`)) return
  await call(`whatsapp_flow.api.v1.campaigns.${fn}`, { name: c.name })
  await load()
}
function pct(c) {
  if (!c.recipient_count) return 0
  return Math.min(100, Math.round((c.sent_count || 0) / c.recipient_count * 100))
}
function openDesk(c) { window.open(`/app/bulk-whatsapp-message/${encodeURIComponent(c.name)}`, '_blank') }
onMounted(load)
</script>

<template>
  <div class="cp">
    <header class="cp__head">
      <div>
        <h1>Campaigns</h1>
        <p>Broadcast approved templates to a segment or recipient list, with opt-out &amp; throttle.</p>
      </div>
      <button class="btn btn--green" @click="openNew">＋ New Broadcast</button>
    </header>

    <div v-if="loading" class="cp__empty">Loading…</div>
    <div v-else-if="!campaigns.length" class="cp__empty">
      <div class="cp__art">📣</div>
      <p>No campaigns yet.</p>
      <button class="btn btn--green" @click="openNew">＋ New Broadcast</button>
    </div>

    <div v-else class="cp__grid">
      <div v-for="c in campaigns" :key="c.name" class="card">
        <div class="card__top">
          <div class="card__title">{{ c.title || c.name }}</div>
          <span class="pill" :data-s="(c.status || '').toLowerCase()">{{ c.status }}</span>
        </div>
        <div class="card__meta">
          <span>📄 {{ c.template || 'No template' }}</span>
          <span v-if="c.wd_segment">🎯 {{ c.wd_segment }}</span>
          <span v-else-if="c.recipient_list">📋 {{ c.recipient_list }}</span>
          <span v-if="c.scheduled_time">🕑 {{ c.scheduled_time }}</span>
        </div>
        <div class="card__prog">
          <div class="card__track"><div class="card__fill" :style="{ width: pct(c) + '%' }" /></div>
          <span class="card__nums">{{ c.sent_count || 0 }} / {{ c.recipient_count || 0 }}
            <template v-if="c.wd_skipped_count"> · {{ c.wd_skipped_count }} skipped</template>
          </span>
        </div>
        <div class="card__actions">
          <button v-if="['Queued','In Progress','Scheduled'].includes(c.status)" class="mini" @click="act(c, 'pause')">⏸ Pause</button>
          <button v-if="c.status === 'Paused'" class="mini" @click="act(c, 'resume')">▶ Resume</button>
          <button v-if="!['Completed','Cancelled'].includes(c.status)" class="mini mini--red" @click="act(c, 'cancel')">✕ Cancel</button>
          <button class="mini" @click="openDesk(c)">Open ↗</button>
        </div>
      </div>
    </div>

    <!-- Composer -->
    <div v-if="showModal" class="modal">
      <div class="modal__backdrop" @click="showModal = false" />
      <div class="modal__box">
        <header class="modal__head">
          <h2>New Broadcast</h2>
          <button class="modal__close" @click="showModal = false">×</button>
        </header>
        <div class="modal__body">
          <label>Campaign title<input v-model="form.title" placeholder="October promo" /></label>
          <div class="grid2">
            <label>Template
              <select v-model="form.template">
                <option value="">— none —</option>
                <option v-for="t in opts.templates" :key="t.name" :value="t.name">{{ t.template_name }} ({{ t.language_code }})</option>
              </select>
            </label>
            <label>WhatsApp Account
              <select v-model="form.whatsapp_account">
                <option v-for="a in opts.accounts" :key="a.name" :value="a.name">{{ a.account_name || a.name }}</option>
              </select>
            </label>
          </div>
          <p v-if="!opts.templates.length" class="modal__warn">No APPROVED templates yet — create and get one approved first, or the broadcast can't send.</p>

          <!-- Template parameter fill -->
          <div v-if="form.template" class="tpl">
            <div v-if="tplLoading" class="tpl__loading">Loading template…</div>
            <template v-else-if="tpl">
              <div v-if="tpl.variables.length" class="tpl__vars">
                <div class="tpl__label">Template variables</div>
                <div v-for="(v, i) in tpl.variables" :key="v" class="tpl__var">
                  <span class="tpl__tag">{{ tag(v) }}</span>
                  <input v-model="varValues[v]" :placeholder="`Value for ${v}`" />
                </div>
              </div>
              <div class="tpl__preview">
                <div class="tpl__label">Preview</div>
                <div class="tpl__bubble">
                  <div v-if="tpl.header" class="tpl__hdr">{{ tpl.header }}</div>
                  <div class="tpl__body">{{ preview }}</div>
                  <div v-if="tpl.footer" class="tpl__footer">{{ tpl.footer }}</div>
                </div>
              </div>
            </template>
          </div>

          <div class="aud">
            <div class="aud__tabs">
              <button :class="{ on: form.audience === 'segment' }" @click="form.audience = 'segment'">Segment</button>
              <button :class="{ on: form.audience === 'list' }" @click="form.audience = 'list'">Recipient List</button>
            </div>
            <div v-if="form.audience === 'segment'" class="aud__row">
              <select v-model="form.wd_segment" @change="segPreview = null">
                <option v-for="s in opts.segments" :key="s.name" :value="s.name">{{ s.title }}</option>
              </select>
              <button class="btn" @click="previewSegment">Preview</button>
              <span v-if="segPreview !== null" class="aud__count">{{ segPreview }} recipients</span>
            </div>
            <div v-else class="aud__row">
              <select v-model="form.recipient_list">
                <option v-for="l in opts.recipient_lists" :key="l.name" :value="l.name">{{ l.list_name || l.name }}</option>
              </select>
            </div>
          </div>

          <div class="grid2">
            <label class="chk"><input type="checkbox" v-model="form.wd_respect_opt_out" /> Respect marketing opt-out</label>
            <label>Throttle (msgs/min, 0 = unlimited)<input type="number" v-model.number="form.wd_throttle_per_min" min="0" /></label>
          </div>
          <label>Schedule (optional)<input type="datetime-local" v-model="form.scheduled_time" /></label>
          <p v-if="err" class="modal__err">{{ err }}</p>
        </div>
        <footer class="modal__foot">
          <button class="btn" @click="showModal = false">Cancel</button>
          <button class="btn btn--green" :disabled="saving" @click="createCampaign">{{ saving ? 'Creating…' : (form.scheduled_time ? 'Schedule' : 'Create Draft') }}</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp { height: 100vh; overflow-y: auto; background: #f8fafc; color: #0f172a; padding: 28px 32px; }
.cp__head { display: flex; align-items: center; margin-bottom: 22px; }
.cp__head h1 { font-size: 24px; font-weight: 700; }
.cp__head p { color: #64748b; font-size: 14px; margin-top: 2px; }
.cp__head .btn { margin-left: auto; }
.btn { font-size: 13px; font-weight: 600; padding: 9px 15px; border-radius: 10px; border: 1px solid #e5e7eb; background: #fff; color: #334155; }
.btn:hover { background: #f1f5f9; }
.btn--green { background: #10b981; border-color: #10b981; color: #fff; }
.btn--green:hover { background: #059669; }

.cp__empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 70px 0; color: #94a3b8; }
.cp__art { font-size: 44px; opacity: 0.6; }
.cp__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 16px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 18px; }
.card__top { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.card__title { font-weight: 700; font-size: 15px; flex: 1; min-width: 0; }
.card__meta { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: #64748b; margin-bottom: 14px; }
.card__prog { margin-bottom: 14px; }
.card__track { height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; margin-bottom: 5px; }
.card__fill { height: 100%; background: #10b981; border-radius: 4px; transition: width .3s; }
.card__nums { font-size: 11px; color: #94a3b8; }
.card__actions { display: flex; flex-wrap: wrap; gap: 6px; }
.mini { font-size: 12px; font-weight: 600; padding: 5px 10px; border-radius: 8px; border: 1px solid #e5e7eb; background: #fff; color: #475569; }
.mini:hover { background: #f1f5f9; }
.mini--red { color: #dc2626; border-color: #fecaca; }
.pill { font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 999px; background: #f1f5f9; color: #64748b; }
.pill[data-s="completed"] { background: #dcfce7; color: #15803d; }
.pill[data-s="in progress"], .pill[data-s="queued"] { background: #dbeafe; color: #1d4ed8; }
.pill[data-s="scheduled"] { background: #fef3c7; color: #b45309; }
.pill[data-s="paused"] { background: #ffedd5; color: #c2410c; }
.pill[data-s="cancelled"] { background: #fee2e2; color: #b91c1c; }
.pill[data-s="draft"] { background: #f1f5f9; color: #64748b; }

.modal { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; }
.modal__backdrop { position: absolute; inset: 0; background: rgba(2,6,23,0.4); }
.modal__box { position: relative; width: 620px; max-width: 94vw; max-height: 90vh; overflow-y: auto; background: #fff; border-radius: 18px; box-shadow: 0 24px 60px rgba(2,6,23,0.25); }
.modal__head { display: flex; align-items: center; padding: 18px 22px; border-bottom: 1px solid #f1f5f9; }
.modal__head h2 { font-size: 17px; font-weight: 700; }
.modal__close { margin-left: auto; font-size: 24px; color: #94a3b8; line-height: 1; }
.modal__body { padding: 20px 22px; display: flex; flex-direction: column; gap: 14px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.modal__body label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 600; color: #475569; }
.modal__body input, .modal__body select { border: 1px solid #e5e7eb; border-radius: 9px; padding: 8px 11px; font-size: 13px; font-weight: 400; color: #0f172a; outline: none; }
.modal__body input:focus, .modal__body select:focus { border-color: #10b981; }
.chk { flex-direction: row !important; align-items: center; gap: 8px !important; }
.chk input { width: auto; }
.aud { border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px; }
.aud__tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.aud__tabs button { font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 999px; color: #64748b; background: #f1f5f9; }
.aud__tabs button.on { background: #10b981; color: #fff; }
.aud__row { display: flex; align-items: center; gap: 8px; }
.aud__row select { flex: 1; border: 1px solid #e5e7eb; border-radius: 9px; padding: 8px 11px; font-size: 13px; outline: none; }
.aud__count { font-size: 12px; font-weight: 700; color: #15803d; white-space: nowrap; }
.modal__warn { font-size: 12px; color: #b45309; background: #fffbeb; border: 1px solid #fef3c7; border-radius: 10px; padding: 9px 12px; }
.tpl { display: flex; flex-direction: column; gap: 12px; }
.tpl__loading { font-size: 12px; color: #94a3b8; }
.tpl__label { font-size: 10px; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 6px; }
.tpl__vars { display: flex; flex-direction: column; gap: 8px; }
.tpl__var { display: flex; align-items: center; gap: 8px; }
.tpl__tag { font-family: ui-monospace, monospace; font-size: 11px; font-weight: 700; color: #0369a1; background: #e0f2fe; border-radius: 6px; padding: 3px 7px; white-space: nowrap; }
.tpl__var input { flex: 1; border: 1px solid #e5e7eb; border-radius: 9px; padding: 7px 11px; font-size: 13px; outline: none; }
.tpl__var input:focus { border-color: #10b981; }
.tpl__preview .tpl__bubble { background: #d9fdd3; border-radius: 10px 10px 10px 2px; padding: 10px 12px; font-size: 13px; color: #0f172a; white-space: pre-wrap; word-break: break-word; }
.tpl__hdr { font-weight: 700; margin-bottom: 4px; }
.tpl__footer { font-size: 11px; color: #64748b; margin-top: 6px; }
.modal__err { color: #b91c1c; font-size: 13px; }
.modal__foot { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 22px; border-top: 1px solid #f1f5f9; }
</style>
