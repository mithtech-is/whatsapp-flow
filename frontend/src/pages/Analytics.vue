<script setup>
import { ref, computed, onMounted } from 'vue'
import { call } from 'frappe-ui'

const loading = ref(true)
const cards = ref([])
const io = ref({ incoming: 0, outgoing: 0 })
const series = ref([])
const statusRows = ref([])
const campaigns = ref([])

const maxVol = computed(() =>
  Math.max(1, ...series.value.map((b) => b.incoming + b.outgoing)))
const ioTotal = computed(() => Math.max(1, io.value.incoming + io.value.outgoing))

const STATUS_COLOR = {
  Open: '#f59e0b', Replied: '#2563eb', Resolved: '#16a34a', Closed: '#64748b',
}

async function load() {
  loading.value = true
  const [o, v, s, c] = await Promise.allSettled([
    call('whatsapp_flow.api.v1.analytics.overview'),
    call('whatsapp_flow.api.v1.analytics.volume_series', { days: 7 }),
    call('whatsapp_flow.api.v1.analytics.status_breakdown'),
    call('whatsapp_flow.api.v1.analytics.campaign_results', { limit: 6 }),
  ])
  if (o.status === 'fulfilled') { cards.value = o.value.cards; io.value = o.value.io }
  if (v.status === 'fulfilled') series.value = v.value.series
  if (s.status === 'fulfilled') statusRows.value = s.value.rows
  if (c.status === 'fulfilled') campaigns.value = c.value.rows
  loading.value = false
}
const statusTotal = computed(() => Math.max(1, statusRows.value.reduce((a, r) => a + r.count, 0)))
onMounted(load)
</script>

<template>
  <div class="an">
    <header class="an__head">
      <div>
        <h1>Analytics</h1>
        <p>Conversation volume, response health, and campaign performance.</p>
      </div>
      <button class="btn" @click="load">↻ Refresh</button>
    </header>

    <div v-if="loading" class="an__loading">Loading…</div>

    <template v-else>
      <!-- KPI cards -->
      <div class="an__cards">
        <div v-for="c in cards" :key="c.key" class="kpi" :style="{ '--accent': c.accent }">
          <div class="kpi__val">{{ c.value }}</div>
          <div class="kpi__label">{{ c.label }}</div>
          <div v-if="c.sub" class="kpi__sub">{{ c.sub }}</div>
        </div>
      </div>

      <div class="an__row">
        <!-- Volume bars -->
        <section class="panel">
          <h2>Message volume · 7 days</h2>
          <div class="bars">
            <div v-for="b in series" :key="b.date" class="bars__col">
              <div class="bars__stack">
                <div class="bars__out" :style="{ height: (b.outgoing / maxVol * 120) + 'px' }" :title="b.outgoing + ' outgoing'" />
                <div class="bars__in" :style="{ height: (b.incoming / maxVol * 120) + 'px' }" :title="b.incoming + ' incoming'" />
              </div>
              <div class="bars__label">{{ b.label }}</div>
            </div>
          </div>
          <div class="legend">
            <span><i class="dot" style="background:#16a34a" /> Incoming</span>
            <span><i class="dot" style="background:#93c5fd" /> Outgoing</span>
          </div>
        </section>

        <!-- In/out donut -->
        <section class="panel">
          <h2>Direction split</h2>
          <div class="split">
            <div class="split__bar">
              <div class="split__in" :style="{ width: (io.incoming / ioTotal * 100) + '%' }" />
              <div class="split__out" :style="{ width: (io.outgoing / ioTotal * 100) + '%' }" />
            </div>
            <div class="split__nums">
              <div><b>{{ io.incoming }}</b><span>Incoming</span></div>
              <div><b>{{ io.outgoing }}</b><span>Outgoing</span></div>
            </div>
          </div>
          <h2 style="margin-top:20px">Conversations by status</h2>
          <div v-for="r in statusRows" :key="r.status" class="statusrow">
            <span class="statusrow__label">{{ r.status }}</span>
            <div class="statusrow__track">
              <div class="statusrow__fill" :style="{ width: (r.count / statusTotal * 100) + '%', background: STATUS_COLOR[r.status] || '#94a3b8' }" />
            </div>
            <span class="statusrow__n">{{ r.count }}</span>
          </div>
        </section>
      </div>

      <!-- Campaign results -->
      <section class="panel">
        <h2>Recent campaigns</h2>
        <table v-if="campaigns.length" class="tbl">
          <thead><tr><th>Campaign</th><th>Status</th><th>Recipients</th><th>Sent</th><th>Skipped</th></tr></thead>
          <tbody>
            <tr v-for="c in campaigns" :key="c.name">
              <td class="tbl__name">{{ c.title || c.name }}</td>
              <td><span class="pill" :data-s="(c.status || '').toLowerCase()">{{ c.status }}</span></td>
              <td>{{ c.recipient_count || 0 }}</td>
              <td>{{ c.sent_count || 0 }}</td>
              <td>{{ c.wd_skipped_count || 0 }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">No campaigns yet.</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.an { height: 100vh; overflow-y: auto; background: #f8fafc; color: #0f172a; padding: 28px 32px; }
.an__head { display: flex; align-items: center; margin-bottom: 22px; }
.an__head h1 { font-size: 24px; font-weight: 700; }
.an__head p { color: #64748b; font-size: 14px; margin-top: 2px; }
.an__head .btn { margin-left: auto; }
.btn { font-size: 13px; font-weight: 600; padding: 8px 14px; border-radius: 10px; border: 1px solid #e5e7eb; background: #fff; color: #334155; }
.btn:hover { background: #f1f5f9; }
.an__loading { padding: 80px; text-align: center; color: #94a3b8; }

.an__cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 14px; margin-bottom: 18px; }
.kpi { background: #fff; border: 1px solid #e5e7eb; border-left: 4px solid var(--accent); border-radius: 14px; padding: 16px 18px; }
.kpi__val { font-size: 30px; font-weight: 800; color: var(--accent); line-height: 1; }
.kpi__label { font-size: 13px; color: #475569; margin-top: 6px; font-weight: 600; }
.kpi__sub { font-size: 11px; color: #94a3b8; margin-top: 2px; }

.an__row { display: grid; grid-template-columns: 1.3fr 1fr; gap: 16px; margin-bottom: 16px; }
.panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
.panel h2 { font-size: 14px; font-weight: 700; margin-bottom: 14px; }

.bars { display: flex; align-items: flex-end; gap: 14px; height: 140px; padding: 0 4px; }
.bars__col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; justify-content: flex-end; }
.bars__stack { display: flex; flex-direction: column-reverse; width: 60%; min-height: 2px; }
.bars__in { background: #16a34a; border-radius: 4px 4px 0 0; min-height: 0; }
.bars__out { background: #93c5fd; border-radius: 4px 4px 0 0; min-height: 0; }
.bars__label { font-size: 11px; color: #94a3b8; font-weight: 600; }
.legend { display: flex; gap: 16px; margin-top: 12px; font-size: 12px; color: #64748b; }
.legend .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; }

.split__bar { display: flex; height: 16px; border-radius: 8px; overflow: hidden; background: #f1f5f9; }
.split__in { background: #16a34a; }
.split__out { background: #93c5fd; }
.split__nums { display: flex; gap: 24px; margin-top: 12px; }
.split__nums div { display: flex; flex-direction: column; }
.split__nums b { font-size: 20px; font-weight: 800; }
.split__nums span { font-size: 11px; color: #94a3b8; }

.statusrow { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.statusrow__label { width: 70px; font-size: 12px; color: #475569; }
.statusrow__track { flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
.statusrow__fill { height: 100%; border-radius: 4px; }
.statusrow__n { width: 28px; text-align: right; font-size: 12px; font-weight: 700; }

.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: #94a3b8; padding: 8px 10px; border-bottom: 1px solid #e5e7eb; }
.tbl td { padding: 10px; border-bottom: 1px solid #f1f5f9; }
.tbl__name { font-weight: 600; }
.pill { font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; background: #f1f5f9; color: #64748b; }
.pill[data-s="completed"] { background: #dcfce7; color: #15803d; }
.pill[data-s="in progress"], .pill[data-s="queued"] { background: #dbeafe; color: #1d4ed8; }
.pill[data-s="scheduled"] { background: #fef3c7; color: #b45309; }
.pill[data-s="cancelled"] { background: #fee2e2; color: #b91c1c; }
.muted { color: #94a3b8; font-size: 13px; }

@media (max-width: 900px) { .an__row { grid-template-columns: 1fr; } }
</style>
