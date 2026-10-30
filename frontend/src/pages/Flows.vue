<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { call } from 'frappe-ui'

const router = useRouter()
const flows = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try { flows.value = await call('whatsapp_flow.api.v1.flows.list_flows') }
  finally { loading.value = false }
}
async function createFlow() {
  const name = window.prompt('New flow name')
  if (!name) return
  const r = await call('whatsapp_flow.api.v1.flows.create_flow', { flow_name: name })
  router.push(`/flows/${encodeURIComponent(r.flow)}`)
}
function open(f) { router.push(`/flows/${encodeURIComponent(f.name)}`) }
onMounted(load)
</script>

<template>
  <div class="flows">
    <header class="flows__head">
      <div>
        <h1>Chatbot Flows</h1>
        <p>Visual graph flows that automate WhatsApp conversations.</p>
      </div>
      <button class="btn btn--green" @click="createFlow">＋ New Graph Flow</button>
    </header>

    <div v-if="loading" class="flows__empty">Loading…</div>
    <div v-else-if="!flows.length" class="flows__empty">
      <div class="flows__art">🤖</div>
      <p>No flows yet. Create your first graph flow.</p>
      <button class="btn btn--green" @click="createFlow">＋ New Graph Flow</button>
    </div>

    <div v-else class="flows__grid">
      <button v-for="f in flows" :key="f.name" class="card" @click="open(f)">
        <div class="card__icon">🤖</div>
        <div class="card__body">
          <div class="card__name">{{ f.flow_name || f.name }}</div>
          <div class="card__meta">{{ f.wd_mode || 'Steps' }} mode</div>
        </div>
        <div class="card__tags">
          <span v-if="f.wd_published" class="tag tag--green">published v{{ f.wd_version || 1 }}</span>
          <span v-else class="tag tag--gray">draft</span>
          <span class="tag" :class="f.enabled ? 'tag--blue' : 'tag--gray'">{{ f.enabled ? 'enabled' : 'disabled' }}</span>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.flows { height: 100vh; overflow-y: auto; background: #f8fafc; color: #0f172a; padding: 28px 32px; }
.flows__head { display: flex; align-items: center; margin-bottom: 24px; }
.flows__head h1 { font-size: 24px; font-weight: 700; }
.flows__head p { color: #64748b; font-size: 14px; margin-top: 2px; }
.flows__head .btn { margin-left: auto; }
.btn { font-size: 14px; font-weight: 600; padding: 9px 16px; border-radius: 10px; border: 1px solid #e5e7eb; background: #fff; color: #334155; }
.btn--green { background: #10b981; border-color: #10b981; color: #fff; }
.btn--green:hover { background: #059669; }
.flows__empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 80px 0; color: #94a3b8; }
.flows__art { font-size: 48px; opacity: 0.6; }
.flows__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.card { display: flex; align-items: center; gap: 14px; text-align: left; background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 16px; transition: box-shadow .15s, transform .1s; }
.card:hover { box-shadow: 0 8px 20px rgba(2,6,23,0.08); transform: translateY(-1px); }
.card__icon { width: 44px; height: 44px; border-radius: 12px; background: #ecfdf5; display: grid; place-items: center; font-size: 20px; flex-shrink: 0; }
.card__body { flex: 1; min-width: 0; }
.card__name { font-weight: 700; font-size: 15px; }
.card__meta { font-size: 12px; color: #94a3b8; }
.card__tags { display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
.tag { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.tag--green { background: #dcfce7; color: #15803d; }
.tag--blue { background: #dbeafe; color: #1d4ed8; }
.tag--gray { background: #f1f5f9; color: #64748b; }
</style>
