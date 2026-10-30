<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { call } from 'frappe-ui'

const router = useRouter()
const loading = ref(true)
const voiceEnabled = ref(false)
const cards = ref([])
const calls = ref([])
const ivrFlows = ref([])

function hashColor(s) {
  let h = 0
  for (let i = 0; i < (s || '').length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
  return `hsl(${h}, 55%, 55%)`
}
function initials(s) {
  return (s || '?').split(/[ @.]/).filter(Boolean).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
}
function timeOf(dt) {
  if (!dt) return ''
  const d = new Date(dt.replace(' ', 'T'))
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function statusClass(s) {
  s = (s || '').toLowerCase()
  if (s === 'completed') return 'ok'
  if (s === 'in progress' || s === 'ringing') return 'live'
  if (['no answer', 'busy', 'failed'].includes(s)) return 'bad'
  return 'gray'
}

async function load() {
  loading.value = true
  try {
    const r = await call('whatsapp_flow.api.v1.voice.calls_overview', { limit: 100 })
    voiceEnabled.value = r.voice_enabled
    cards.value = r.cards
    calls.value = r.calls
    ivrFlows.value = r.ivr_flows
  } finally { loading.value = false }
}
function openFlow(f) { router.push(`/flows/${encodeURIComponent(f.name)}`) }
onMounted(load)
</script>

<template>
  <div class="cl">
    <header class="cl__head">
      <div>
        <h1>Calls</h1>
        <p>WhatsApp voice call logs, IVR flows and consent — powered by native Call Log.</p>
      </div>
      <span class="vbadge" :class="voiceEnabled ? 'on' : 'off'">
        {{ voiceEnabled ? '● Voice enabled' : '○ Voice off' }}
      </span>
    </header>

    <div v-if="!loading && !voiceEnabled" class="banner">
      <b>Live calling is not enabled.</b> Call logs and IVR flows still work. To place/receive real
      WhatsApp calls you need to turn on <i>Settings → Enable Voice</i>, add Meta Calling API access,
      and connect a media bridge (VPS). IVR flows are built in the Flow Builder (Graph mode).
    </div>

    <div v-if="loading" class="cl__empty">Loading…</div>

    <template v-else>
      <div class="cl__cards">
        <div v-for="c in cards" :key="c.key" class="kpi" :style="{ '--accent': c.accent }">
          <div class="kpi__val">{{ c.value }}</div>
          <div class="kpi__label">{{ c.label }}</div>
        </div>
      </div>

      <div class="cl__body">
        <!-- Call log -->
        <section class="panel">
          <h2>Recent calls</h2>
          <div v-if="!calls.length" class="muted">No calls logged yet.</div>
          <div v-for="c in calls" :key="c.name" class="row">
            <div class="row__dir" :class="c.type === 'Incoming' ? 'in' : 'out'">
              {{ c.type === 'Incoming' ? '↙' : '↗' }}
            </div>
            <div class="row__who">
              <span class="ava" :style="{ background: hashColor(c.contact_name || c.number) }">{{ initials(c.contact_name || c.number) }}</span>
              <div class="row__name">
                <b>{{ c.contact_name || c.number || '—' }}</b>
                <span class="row__sub">{{ c.number }}<template v-if="c.ivr_flow"> · IVR: {{ c.ivr_flow }}</template></span>
              </div>
            </div>
            <span class="st" :data-s="statusClass(c.status)">{{ c.status }}</span>
            <span class="row__dur">{{ c.duration ? c.duration_fmt : '—' }}</span>
            <span class="row__agent">{{ c.agent || '—' }}</span>
            <span class="row__time">{{ timeOf(c.creation) }}</span>
            <a v-if="c.recording_url" class="row__rec" :href="c.recording_url" target="_blank" title="Recording">▶</a>
            <span v-else class="row__rec row__rec--off">–</span>
          </div>
        </section>

        <!-- IVR flows -->
        <aside class="panel">
          <div class="panel__head">
            <h2>IVR flows</h2>
            <button class="mini" @click="router.push('/flows')">＋ Build</button>
          </div>
          <p class="hint">Voice menus run on the same graph engine — <code>greeting / gather / menu / hangup</code> nodes.</p>
          <div v-if="!ivrFlows.length" class="muted">No graph flows yet.</div>
          <button v-for="f in ivrFlows" :key="f.name" class="ivr" @click="openFlow(f)">
            <span class="ivr__icon">☎️</span>
            <span class="ivr__body">
              <span class="ivr__name">{{ f.flow_name || f.name }}</span>
              <span class="ivr__tags">
                <span class="tag" :class="f.wd_published ? 'tag--green' : 'tag--gray'">{{ f.wd_published ? 'published' : 'draft' }}</span>
                <span class="tag" :class="f.enabled ? 'tag--blue' : 'tag--gray'">{{ f.enabled ? 'on' : 'off' }}</span>
              </span>
            </span>
          </button>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cl { height: 100vh; overflow-y: auto; background: #f8fafc; color: #0f172a; padding: 28px 32px; }
.cl__head { display: flex; align-items: center; margin-bottom: 18px; }
.cl__head h1 { font-size: 24px; font-weight: 700; }
.cl__head p { color: #64748b; font-size: 14px; margin-top: 2px; }
.vbadge { margin-left: auto; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 999px; }
.vbadge.on { background: #dcfce7; color: #15803d; }
.vbadge.off { background: #f1f5f9; color: #64748b; }
.banner { background: #fffbeb; border: 1px solid #fef3c7; color: #92400e; font-size: 13px; border-radius: 12px; padding: 12px 15px; margin-bottom: 18px; line-height: 1.5; }
.cl__empty { padding: 60px; text-align: center; color: #94a3b8; }

.cl__cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px; margin-bottom: 18px; }
.kpi { background: #fff; border: 1px solid #e5e7eb; border-left: 4px solid var(--accent); border-radius: 14px; padding: 15px 16px; }
.kpi__val { font-size: 26px; font-weight: 800; color: var(--accent); line-height: 1; }
.kpi__label { font-size: 12px; color: #475569; margin-top: 6px; font-weight: 600; }

.cl__body { display: grid; grid-template-columns: 1fr 320px; gap: 16px; align-items: start; }
.panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 18px 20px; }
.panel h2 { font-size: 14px; font-weight: 700; margin-bottom: 12px; }
.panel__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.panel__head h2 { margin-bottom: 0; }
.muted { color: #94a3b8; font-size: 13px; padding: 16px 0; }

.row { display: grid; grid-template-columns: 24px 1fr auto 56px 90px 110px 20px; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
.row:last-child { border-bottom: none; }
.row__dir { font-size: 16px; font-weight: 700; text-align: center; }
.row__dir.in { color: #16a34a; }
.row__dir.out { color: #7c3aed; }
.row__who { display: flex; align-items: center; gap: 9px; min-width: 0; }
.ava { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-weight: 700; font-size: 12px; flex-shrink: 0; }
.row__name { display: flex; flex-direction: column; min-width: 0; }
.row__name b { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row__sub { font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row__dur, .row__agent, .row__time { font-size: 12px; color: #64748b; }
.row__time { text-align: right; }
.row__rec { text-align: center; color: #16a34a; }
.row__rec--off { color: #cbd5e1; }
.st { font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; background: #f1f5f9; color: #64748b; white-space: nowrap; }
.st[data-s="ok"] { background: #dcfce7; color: #15803d; }
.st[data-s="live"] { background: #dbeafe; color: #1d4ed8; }
.st[data-s="bad"] { background: #fee2e2; color: #b91c1c; }

.hint { font-size: 12px; color: #64748b; margin-bottom: 12px; line-height: 1.5; }
.hint code { background: #f1f5f9; border-radius: 5px; padding: 1px 5px; font-size: 11px; }
.ivr { display: flex; align-items: center; gap: 11px; width: 100%; text-align: left; padding: 10px; border-radius: 11px; }
.ivr:hover { background: #f8fafc; }
.ivr__icon { width: 36px; height: 36px; border-radius: 10px; background: #ecfdf5; display: grid; place-items: center; font-size: 17px; flex-shrink: 0; }
.ivr__body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.ivr__name { font-weight: 650; font-size: 13px; }
.ivr__tags { display: flex; gap: 5px; }
.tag { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; }
.tag--green { background: #dcfce7; color: #15803d; }
.tag--blue { background: #dbeafe; color: #1d4ed8; }
.tag--gray { background: #f1f5f9; color: #64748b; }
.mini { font-size: 12px; font-weight: 600; color: #16a34a; }

@media (max-width: 900px) { .cl__body { grid-template-columns: 1fr; } }
</style>
