<script setup>
import { ref, onMounted } from 'vue'
import { call } from 'frappe-ui'

const loading = ref(true)
const forbidden = ref(false)
const settings = ref({})
const teams = ref([])
const agents = ref([])

const active = ref('team')
const msg = ref('')

const ops = ref(null)            // editable copy of the WhatsApp Settings single
const savingOps = ref(false)
const opsMsg = ref('')

async function load() {
  loading.value = true; forbidden.value = false
  try {
    const r = await call('whatsapp_flow.api.v1.settings.get_settings')
    settings.value = r.settings
    ops.value = {
      wd_phone_masking: r.settings.wd_phone_masking ? 1 : 0,
      wd_retention_days: r.settings.wd_retention_days,
      wd_auto_close_days: r.settings.wd_auto_close_days,
      wd_voice_enabled: r.settings.wd_voice_enabled ? 1 : 0,
      has_flows_key: r.settings.has_flows_key,
      wd_flows_private_key: '',
    }
    const ta = await call('whatsapp_flow.api.v1.settings.teams_and_agents')
    teams.value = ta.teams; agents.value = ta.agents
  } catch (e) {
    if (e.exc_type === 'PermissionError' || /Managers/.test(e.message || '')) forbidden.value = true
    else msg.value = e.message || 'Failed to load.'
  } finally { loading.value = false }
}

async function saveOps() {
  savingOps.value = true; opsMsg.value = ''
  try {
    const r = await call('whatsapp_flow.api.v1.settings.save_settings', { payload: JSON.stringify(ops.value) })
    ops.value.wd_flows_private_key = ''
    ops.value.has_flows_key = r.has_flows_key
    opsMsg.value = 'Saved.'
    setTimeout(() => (opsMsg.value = ''), 2000)
  } catch (e) { opsMsg.value = e.message || 'Save failed.' }
  finally { savingOps.value = false }
}
onMounted(load)
</script>

<template>
  <div class="se">
    <header class="se__head">
      <div>
        <h1>Settings</h1>
        <p>Manage teams &amp; agents, retention and the chatbot flow engine. WhatsApp account
          connection lives in the WhatsApp apps (Desk).</p>
      </div>
    </header>

    <div v-if="loading" class="se__empty">Loading…</div>
    <div v-else-if="forbidden" class="se__empty">
      <div class="se__art">🔒</div>
      <p>Settings are available to managers only.</p>
    </div>

    <template v-else>
      <div class="se__tabs">
        <button :class="{ on: active === 'team' }" @click="active = 'team'">👥 Teams &amp; Agents</button>
        <button :class="{ on: active === 'ops' }" @click="active = 'ops'">⚙️ Retention &amp; Ops</button>
      </div>

      <!-- TEAMS -->
      <section v-if="active === 'team'">
        <div class="cols">
          <div class="panel">
            <h2>Teams</h2>
            <div v-for="t in teams" :key="t.team" class="line">
              <span class="line__name">👥 {{ t.team }}</span>
              <span class="line__meta">{{ t.online }}/{{ t.members }} online</span>
            </div>
            <p v-if="!teams.length" class="muted">No teams. Create User Groups in Desk.</p>
            <a class="btn btn--ghost" href="/app/user-group/new" target="_blank">＋ New Team (Desk)</a>
          </div>
          <div class="panel">
            <h2>Agents</h2>
            <div v-for="ag in agents" :key="ag.name" class="line">
              <span class="line__name">{{ ag.full_name || ag.name }}</span>
              <span class="dotstate" :data-s="(ag.wd_wa_availability || 'offline').toLowerCase()">{{ ag.wd_wa_availability || 'Offline' }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- OPS -->
      <section v-else-if="ops" class="panel panel--narrow">
        <h2>Retention &amp; Operations</h2>

        <label class="frm"><span>Log retention (days)</span>
          <input type="number" v-model.number="ops.wd_retention_days" min="0" /></label>
        <label class="frm"><span>Auto-close resolved after (days)</span>
          <input type="number" v-model.number="ops.wd_auto_close_days" min="0" /></label>
        <label class="frm frm--row"><input type="checkbox" v-model="ops.wd_phone_masking" :true-value="1" :false-value="0" /> Mask phone numbers</label>
        <label class="frm frm--row"><input type="checkbox" v-model="ops.wd_voice_enabled" :true-value="1" :false-value="0" /> Enable Voice (calling)</label>

        <div class="frm">
          <span>WhatsApp Flows private key (PEM)
            <em v-if="ops.has_flows_key" class="setoken">● set — leave blank to keep</em>
            <em v-else class="unset">not set</em>
          </span>
          <textarea v-model="ops.wd_flows_private_key" rows="4" placeholder="-----BEGIN PRIVATE KEY-----&#10;…&#10;-----END PRIVATE KEY-----" />
          <small class="hintline">Used to decrypt Meta WhatsApp Flows requests. Upload the matching public key in Meta.</small>
        </div>

        <div class="opsfoot">
          <button class="btn btn--green" :disabled="savingOps" @click="saveOps">{{ savingOps ? 'Saving…' : 'Save' }}</button>
          <span v-if="opsMsg" class="opsmsg">{{ opsMsg }}</span>
        </div>

        <div class="health" v-if="settings.wd_patch_health">
          <div class="health__label">Patch &amp; override health</div>
          <pre>{{ settings.wd_patch_health }}</pre>
        </div>
      </section>

      <p v-if="msg" class="se__msg">{{ msg }}</p>
    </template>
  </div>
</template>

<style scoped>
.se { height: 100vh; overflow-y: auto; background: #f8fafc; color: #0f172a; padding: 28px 32px; }
.se__head { margin-bottom: 20px; }
.se__head h1 { font-size: 24px; font-weight: 700; }
.se__head p { color: #64748b; font-size: 14px; margin-top: 2px; max-width: 640px; }
.se__empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 70px 0; color: #94a3b8; }
.se__art { font-size: 44px; opacity: 0.6; }
.btn { font-size: 13px; font-weight: 600; padding: 9px 15px; border-radius: 10px; border: 1px solid #e5e7eb; background: #fff; color: #334155; cursor: pointer; display: inline-block; text-decoration: none; }
.btn:hover { background: #f1f5f9; }
.btn--green { background: #10b981; border-color: #10b981; color: #fff; }
.btn--green:hover { background: #059669; }
.btn--ghost { margin-top: 12px; color: #16a34a; border-color: #bbf7d0; }

.se__tabs { display: flex; gap: 8px; margin-bottom: 20px; }
.se__tabs button { font-size: 13px; font-weight: 600; padding: 8px 15px; border-radius: 999px; color: #64748b; background: #fff; border: 1px solid #e5e7eb; }
.se__tabs button.on { background: #0b3d2e; color: #fff; border-color: #0b3d2e; }

.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 20px; }
.panel--narrow { max-width: 560px; }
.panel h2 { font-size: 14px; font-weight: 700; margin-bottom: 14px; }
.line { display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
.line:last-child { border-bottom: none; }
.line__name { font-weight: 600; }
.line__meta { font-size: 12px; color: #94a3b8; }
.dotstate { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: #f1f5f9; color: #94a3b8; }
.dotstate[data-s="online"] { background: #dcfce7; color: #15803d; }
.dotstate[data-s="away"] { background: #fef3c7; color: #b45309; }
.muted { color: #94a3b8; font-size: 13px; }

.frm { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; font-size: 12px; font-weight: 600; color: #475569; }
.frm > span { display: flex; align-items: center; gap: 8px; }
.frm input[type="number"], .frm textarea { border: 1px solid #e5e7eb; border-radius: 9px; padding: 8px 11px; font-size: 13px; font-weight: 400; color: #0f172a; outline: none; }
.frm input:focus, .frm textarea:focus { border-color: #10b981; }
.frm textarea { font-family: ui-monospace, monospace; resize: vertical; }
.frm--row { flex-direction: row; align-items: center; gap: 8px; }
.frm--row input[type="checkbox"] { width: 17px; height: 17px; flex: none; accent-color: #10b981; cursor: pointer; }
.setoken { font-weight: 600; color: #15803d; font-style: normal; }
.unset { font-weight: 600; color: #94a3b8; font-style: normal; }
.hintline { font-weight: 400; color: #94a3b8; font-size: 11px; }
.opsfoot { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
.opsmsg { font-size: 13px; color: #15803d; font-weight: 600; }

.health { margin-top: 14px; }
.health__label { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 6px; }
.health pre { font-size: 11px; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px; overflow-x: auto; white-space: pre-wrap; color: #334155; }
.se__msg { margin-top: 14px; font-size: 13px; color: #15803d; }
@media (max-width: 820px) { .cols { grid-template-columns: 1fr; } }
</style>
