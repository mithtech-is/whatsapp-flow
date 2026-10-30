<script setup>
import { ref, computed, onMounted } from 'vue'
import { call } from 'frappe-ui'

const loading = ref(true)
const templates = ref([])
const q = ref('')
const statusFilter = ref('All')

const showModal = ref(false)
const saving = ref(false)
const err = ref('')
const opts = ref({ accounts: [], categories: [], header_types: [] })
const form = ref(null)

const STATUSES = ['All', 'APPROVED', 'PENDING', 'REJECTED', 'DRAFT']

const filtered = computed(() => templates.value.filter((t) => {
  if (statusFilter.value !== 'All' && (t.status || '').toUpperCase() !== statusFilter.value) return false
  const s = q.value.trim().toLowerCase()
  return !s || (t.template_name || '').toLowerCase().includes(s)
}))

function statusClass(s) {
  s = (s || '').toUpperCase()
  if (s === 'APPROVED') return 'ok'
  if (s === 'REJECTED') return 'bad'
  if (s === 'PENDING') return 'wait'
  return 'gray'
}

async function load() {
  loading.value = true
  try { templates.value = await call('whatsapp_flow.api.v1.templates.list_templates') }
  finally { loading.value = false }
}

async function openNew() {
  err.value = ''
  if (!opts.value.accounts.length) opts.value = await call('whatsapp_flow.api.v1.templates.accounts')
  form.value = {
    template_name: '', category: 'MARKETING', language_code: 'en',
    header_type: '', header: '', template: '', footer: '', sample_values: '',
    whatsapp_account: opts.value.accounts[0]?.name || '',
  }
  showModal.value = true
}

async function saveTemplate() {
  if (!form.value.template_name || !form.value.template) {
    err.value = 'Template name and body are required.'; return
  }
  saving.value = true; err.value = ''
  try {
    await call('whatsapp_flow.api.v1.templates.save_template', { payload: JSON.stringify(form.value) })
    showModal.value = false
    await load()
  } catch (e) { err.value = e.messages?.join(', ') || e.message || 'Failed to save.' }
  finally { saving.value = false }
}

async function removeTemplate(t) {
  if (!window.confirm(`Delete template "${t.template_name}"?`)) return
  await call('whatsapp_flow.api.v1.templates.delete_template', { name: t.name })
  await load()
}
onMounted(load)
</script>

<template>
  <div class="tp">
    <header class="tp__head">
      <div>
        <h1>Message Templates</h1>
        <p>Pre-approved WhatsApp templates for broadcasts and automated replies.</p>
      </div>
      <button class="btn btn--green" @click="openNew">＋ New Template</button>
    </header>

    <div class="tp__toolbar">
      <input v-model="q" class="tp__search" placeholder="Search templates…" />
      <div class="tp__chips">
        <button v-for="s in STATUSES" :key="s" class="chip" :class="{ on: statusFilter === s }" @click="statusFilter = s">{{ s }}</button>
      </div>
    </div>

    <div v-if="loading" class="tp__empty">Loading…</div>
    <div v-else-if="!filtered.length" class="tp__empty">
      <div class="tp__art">📄</div>
      <p>No templates{{ q || statusFilter !== 'All' ? ' match your filter' : ' yet' }}.</p>
      <button v-if="!q && statusFilter === 'All'" class="btn btn--green" @click="openNew">＋ New Template</button>
    </div>

    <table v-else class="tbl">
      <thead><tr><th>Name</th><th>Category</th><th>Lang</th><th>Header</th><th>Status</th><th></th></tr></thead>
      <tbody>
        <tr v-for="t in filtered" :key="t.name">
          <td class="tbl__name">{{ t.template_name }}<span class="tbl__sub">{{ t.actual_name }}</span></td>
          <td>{{ t.category || '—' }}</td>
          <td>{{ t.language_code || '—' }}</td>
          <td>{{ t.header_type || '—' }}</td>
          <td><span class="st" :data-s="statusClass(t.status)">{{ t.status || 'Draft' }}</span></td>
          <td class="tbl__act"><button class="x" title="Delete" @click="removeTemplate(t)">🗑</button></td>
        </tr>
      </tbody>
    </table>

    <!-- Create modal -->
    <div v-if="showModal" class="modal">
      <div class="modal__backdrop" @click="showModal = false" />
      <div class="modal__box">
        <header class="modal__head">
          <h2>New Template</h2>
          <button class="modal__close" @click="showModal = false">×</button>
        </header>
        <div class="modal__body">
          <p class="modal__hint">Submitting creates the template on Meta for review. Approval status syncs back via the webhook.</p>
          <div class="grid2">
            <label>Template name<input v-model="form.template_name" placeholder="order_confirmation" /></label>
            <label>WhatsApp Account
              <select v-model="form.whatsapp_account">
                <option v-for="a in opts.accounts" :key="a.name" :value="a.name">{{ a.account_name || a.name }}</option>
              </select>
            </label>
            <label>Category
              <select v-model="form.category"><option v-for="c in opts.categories" :key="c">{{ c }}</option></select>
            </label>
            <label>Language code<input v-model="form.language_code" placeholder="en" /></label>
            <label>Header type
              <select v-model="form.header_type"><option v-for="h in opts.header_types" :key="h" :value="h">{{ h || 'None' }}</option></select>
            </label>
            <label v-if="form.header_type === 'TEXT'">Header text<input v-model="form.header" placeholder="Header" /></label>
          </div>
          <label>Body<textarea v-model="form.template" rows="4" placeholder="Hi {{1}}, your order {{2}} has shipped." /></label>
          <div class="grid2">
            <label>Footer<input v-model="form.footer" placeholder="Reply STOP to opt out" /></label>
            <label>Sample values<input v-model="form.sample_values" placeholder="Jane, #1234" /></label>
          </div>
          <p v-if="err" class="modal__err">{{ err }}</p>
        </div>
        <footer class="modal__foot">
          <button class="btn" @click="showModal = false">Cancel</button>
          <button class="btn btn--green" :disabled="saving" @click="saveTemplate">{{ saving ? 'Submitting…' : 'Submit to Meta' }}</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tp { height: 100vh; overflow-y: auto; background: #f8fafc; color: #0f172a; padding: 28px 32px; }
.tp__head { display: flex; align-items: center; margin-bottom: 18px; }
.tp__head h1 { font-size: 24px; font-weight: 700; }
.tp__head p { color: #64748b; font-size: 14px; margin-top: 2px; }
.tp__head .btn { margin-left: auto; }
.btn { font-size: 13px; font-weight: 600; padding: 9px 15px; border-radius: 10px; border: 1px solid #e5e7eb; background: #fff; color: #334155; }
.btn:hover { background: #f1f5f9; }
.btn--green { background: #10b981; border-color: #10b981; color: #fff; }
.btn--green:hover { background: #059669; }

.tp__toolbar { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.tp__search { flex: 1; min-width: 200px; max-width: 320px; border: 1px solid #e5e7eb; border-radius: 10px; padding: 9px 13px; font-size: 13px; outline: none; background: #fff; }
.tp__search:focus { border-color: #10b981; }
.tp__chips { display: flex; gap: 6px; }
.chip { font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 999px; color: #64748b; background: #fff; border: 1px solid #e5e7eb; }
.chip.on { background: #10b981; border-color: #10b981; color: #fff; }

.tp__empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 70px 0; color: #94a3b8; }
.tp__art { font-size: 44px; opacity: 0.6; }

.tbl { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; overflow: hidden; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: #94a3b8; padding: 11px 14px; border-bottom: 1px solid #e5e7eb; background: #fbfcfe; }
.tbl td { padding: 12px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
.tbl tr:last-child td { border-bottom: none; }
.tbl__name { font-weight: 600; display: flex; flex-direction: column; }
.tbl__sub { font-size: 11px; color: #94a3b8; font-weight: 400; }
.tbl__act { text-align: right; }
.x { opacity: .5; } .x:hover { opacity: 1; }
.st { font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 999px; background: #f1f5f9; color: #64748b; }
.st[data-s="ok"] { background: #dcfce7; color: #15803d; }
.st[data-s="bad"] { background: #fee2e2; color: #b91c1c; }
.st[data-s="wait"] { background: #fef3c7; color: #b45309; }

.modal { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; }
.modal__backdrop { position: absolute; inset: 0; background: rgba(2,6,23,0.4); }
.modal__box { position: relative; width: 640px; max-width: 94vw; max-height: 90vh; overflow-y: auto; background: #fff; border-radius: 18px; box-shadow: 0 24px 60px rgba(2,6,23,0.25); }
.modal__head { display: flex; align-items: center; padding: 18px 22px; border-bottom: 1px solid #f1f5f9; }
.modal__head h2 { font-size: 17px; font-weight: 700; }
.modal__close { margin-left: auto; font-size: 24px; color: #94a3b8; line-height: 1; }
.modal__body { padding: 20px 22px; display: flex; flex-direction: column; gap: 14px; }
.modal__hint { font-size: 12px; color: #64748b; background: #f0fdf4; border: 1px solid #dcfce7; border-radius: 10px; padding: 9px 12px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.modal__body label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 600; color: #475569; }
.modal__body input, .modal__body select, .modal__body textarea { border: 1px solid #e5e7eb; border-radius: 9px; padding: 8px 11px; font-size: 13px; font-weight: 400; color: #0f172a; outline: none; }
.modal__body input:focus, .modal__body select:focus, .modal__body textarea:focus { border-color: #10b981; }
.modal__err { color: #b91c1c; font-size: 13px; }
.modal__foot { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 22px; border-top: 1px solid #f1f5f9; }
</style>
