import axios from 'axios'
import type { ApiEnvelope } from '@/types'

function friendly(message: string) {
  if (/Network Error/i.test(message)) return '网络连接失败，请检查网络后重试'
  if (/timeout/i.test(message)) return '请求超时，请稍后重试'
  if (/Request failed with status code 5\d\d/.test(message)) return '系统繁忙，请稍后重试'
  return message || '网络请求失败'
}
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
  return Promise.reject(new Error(friendly(error.response?.data?.message || error.message)))
})
export default api
