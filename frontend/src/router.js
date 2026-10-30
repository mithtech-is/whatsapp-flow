import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory('/whatsapp'),
  routes: [
    { path: '/', name: 'Inbox', component: () => import('./pages/Inbox.vue') },
    { path: '/flows', name: 'Flows', component: () => import('./pages/Flows.vue') },
    { path: '/flows/:flow', name: 'FlowBuilder', component: () => import('./pages/FlowBuilder.vue') },
    { path: '/settings', name: 'Settings', component: () => import('./pages/Settings.vue') },
    { path: '/:path(.*)*', component: () => import('./pages/NotFound.vue') },
  ],
})
