import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('admin_token') || '')
  const user = ref<User | null>(JSON.parse(localStorage.getItem('admin_user') || 'null'))
  async function login(account: string, password: string) {
    const response = await authApi.login({ account, password, client_type: 'ADMIN' })
    const data = response.data.data
    if (data.user.role !== 'ADMIN') throw new Error('该账号不是管理员账号')
    token.value = data.token
    user.value = data.user
    localStorage.setItem('admin_token', data.token)
    localStorage.setItem('admin_user', JSON.stringify(data.user))
  }
  async function ensureUser() {
    if (!token.value) return null
    if (user.value) return user.value
    const response = await authApi.me()
    user.value = response.data.data.user
    localStorage.setItem('admin_user', JSON.stringify(user.value))
    return user.value
  }
  async function logout() {
    try { await authApi.logout() } catch { /* local logout still succeeds */ }
    token.value = ''
    user.value = null
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_user')
  }
  return { token, user, login, ensureUser, logout }
})
