<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { call } from 'frappe-ui'

const route = useRoute()
const availability = ref('Offline')
const me = ref(window.user || '')

const NAV = [
  { to: '/', icon: '💬', label: 'Inbox', match: (p) => p === '/' || p.startsWith('/?') },
  { to: '/flows', icon: '🤖', label: 'Flows', match: (p) => p.startsWith('/flows') },
  { to: '/settings', icon: '⚙️', label: 'Settings', match: (p) => p.startsWith('/settings') },
]
const AVAIL = ['Online', 'Away', 'Offline']

function initials(s) {
  return (s || '?').split(/[ @.]/).filter(Boolean).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
}
async function loadStatus() {
  try {
    const s = await call('whatsapp_flow.api.v1.agents.my_status')
    availability.value = s.availability
  } catch (e) { /* ignore */ }
}
async function setAvailability(v) {
  availability.value = v
  try { await call('whatsapp_flow.api.v1.agents.set_availability', { availability: v }) } catch (e) {}
}
function isActive(item) {
  return item.match ? item.match(route.path) : false
}
onMounted(loadStatus)
</script>

<template>
  <div class="shell">
    <nav class="rail">
      <div class="rail__logo">WD</div>
      <template v-for="item in NAV" :key="item.label">
        <RouterLink v-if="item.to" :to="item.to" class="rail__item" :class="{ active: isActive(item) }" :title="item.label">
          <span class="rail__icon">{{ item.icon }}</span>
          <span class="rail__label">{{ item.label }}</span>
        </RouterLink>
        <a v-else :href="item.href" class="rail__item" :title="item.label">
          <span class="rail__icon">{{ item.icon }}</span>
          <span class="rail__label">{{ item.label }}</span>
        </a>
      </template>

      <div class="rail__spacer" />
      <div class="rail__avail" :data-state="availability.toLowerCase()">
        <select :value="availability" @change="(e) => setAvailability(e.target.value)">
          <option v-for="a in AVAIL" :key="a" :value="a">{{ a }}</option>
        </select>
      </div>
      <a class="rail__me" href="/app" :title="me">{{ initials(me) }}</a>
    </nav>

    <main class="shell__content">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell { display: flex; height: 100vh; background: #fff; color: #0f172a; }
.rail {
  width: 76px; flex-shrink: 0; display: flex; flex-direction: column; align-items: center;
  gap: 4px; padding: 12px 6px; background: #0b3d2e; color: #d1fae5;
}
.rail__logo {
  width: 40px; height: 40px; border-radius: 12px; background: #10b981; color: #052e1b;
  display: grid; place-items: center; font-weight: 800; font-size: 15px; margin-bottom: 10px;
}
.rail__item {
  width: 100%; display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 8px 2px; border-radius: 10px; color: #a7f3d0; text-decoration: none; transition: background .15s;
}
.rail__item:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
.rail__item.active { background: #10b981; color: #052e1b; }
.rail__icon { font-size: 18px; }
.rail__label { font-size: 10px; font-weight: 600; }
.rail__spacer { flex: 1; }
.rail__avail select {
  width: 60px; border: none; border-radius: 8px; padding: 4px; font-size: 10px; font-weight: 700;
  background: #064e3b; color: #a7f3d0; text-align: center; outline: none;
}
.rail__avail[data-state="online"] select { background: #10b981; color: #052e1b; }
.rail__avail[data-state="away"] select { background: #f59e0b; color: #422006; }
.rail__me {
  margin-top: 8px; width: 36px; height: 36px; border-radius: 50%; background: #10b981; color: #052e1b;
  display: grid; place-items: center; font-weight: 700; font-size: 12px; text-decoration: none;
}
.shell__content { flex: 1; min-width: 0; height: 100vh; overflow: hidden; }
</style>
