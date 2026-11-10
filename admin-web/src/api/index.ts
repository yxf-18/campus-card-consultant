import api from './client'
import type { ApiEnvelope, Category, DocumentItem, SyncTask, User } from '@/types'

export const authApi = {
  login: (body: { account: string; password: string; redirect_url?: string; client_type?: 'ADMIN' | 'MOBILE' }) => api.post<ApiEnvelope<any>>('/auth/login', body),
  me: () => api.get<ApiEnvelope<{ user: User }>>('/auth/me'),
  logout: () => api.post('/auth/logout')
}
export const categoryApi = {
  list: () => api.get<ApiEnvelope<{ list: Category[] }>>('/admin/categories'),
  create: (body: Record<string, unknown>) => api.post('/admin/categories', body),
  update: (id: number, body: Record<string, unknown>) => api.put(`/admin/categories/${id}`, body),
  remove: (id: number) => api.delete(`/admin/categories/${id}`)
}
export const documentApi = {
  list: (params: Record<string, unknown>) => api.get<ApiEnvelope<{ list: DocumentItem[] }>>('/admin/documents', { params }),
  detail: (id: number) => api.get<ApiEnvelope<{ document: DocumentItem }>>(`/admin/documents/${id}`),
  create: (form: FormData) => api.post('/admin/documents', form),
  update: (id: number, form: FormData) => api.put(`/admin/documents/${id}`, form),
  setStatus: (id: number, status: string) => api.patch(`/admin/documents/${id}/status`, { status }),
  remove: (id: number) => api.delete(`/admin/documents/${id}`)
}
export const userApi = {
  list: (params: Record<string, unknown>) => api.get<ApiEnvelope<{ list: User[] }>>('/admin/users', { params }),
  setStatus: (id: number, status: string) => api.patch(`/admin/users/${id}/status`, { status })
}
export const syncApi = {
  list: (params: Record<string, unknown>) => api.get<ApiEnvelope<{ list: SyncTask[] }>>('/admin/sync/tasks', { params }),
  retry: (id: number) => api.post(`/admin/sync/tasks/${id}/retry`)
}
export const feedbackApi = {
  list: (params: Record<string, unknown>) => api.get('/admin/feedbacks', { params }),
  handle: (id: number, body: Record<string, unknown>) => api.patch(`/admin/feedbacks/${id}`, body)
}
export const statsApi = {
  overview: (params: Record<string, unknown>) => api.get('/admin/statistics/overview', { params }),
  export: (body: Record<string, unknown>) => api.post('/admin/statistics/export', body)
}
export const configApi = {
  list: (group?: string) => api.get('/admin/configs', { params: group ? { config_group: group } : {} }),
  update: (key: string, body: Record<string, unknown>) => api.put(`/admin/configs/${encodeURIComponent(key)}`, body)
}
