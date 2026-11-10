import axios from 'axios'
import type { ApiEnvelope } from '@/types'

const api = axios.create({ baseURL: '/api/v1', timeout: 60000 })
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
api.interceptors.response.use((response) => {
  const body = response.data as ApiEnvelope<unknown>
  if (body && typeof body.code === 'number' && body.code !== 0) return Promise.reject(new Error(body.message || '请求失败'))
  return response
}, (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem('admin_token')
    if (!location.pathname.startsWith('/login')) location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`
  }
  const message = error.response?.data?.message || error.message || '网络请求失败'
  return Promise.reject(new Error(message))
})
export default api
