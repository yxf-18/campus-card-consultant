import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/console', component: () => import('@/layouts/AdminLayout.vue'), meta: { auth: true }, children: [
      { path: '', redirect: '/console/dashboard' },
      { path: 'dashboard', component: () => import('@/views/DashboardView.vue') },
      { path: 'categories', component: () => import('@/views/CategoriesView.vue') },
      { path: 'documents', component: () => import('@/views/DocumentsView.vue') },
      { path: 'users', component: () => import('@/views/UsersView.vue') },
      { path: 'profile-requests', component: () => import('@/views/ProfileRequestsView.vue') },
      { path: 'feedbacks', component: () => import('@/views/FeedbacksView.vue') },
      { path: 'configs', component: () => import('@/views/ConfigsView.vue') }
    ]},
    { path: '/:pathMatch(.*)*', redirect: '/login' }
  ]
})
router.beforeEach(async (to) => {
  const store = useAuthStore()
  if (to.meta.public) return true
  if (!store.token) return { path: '/login', query: { redirect: to.fullPath } }
  try {
    const user = await store.ensureUser()
    if (user?.role !== 'ADMIN') return { path: '/login', query: { redirect: to.fullPath } }
    return true
  } catch {
    await store.logout()
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})
export default router
