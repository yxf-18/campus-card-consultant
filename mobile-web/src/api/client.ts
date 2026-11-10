import axios from 'axios'
import type { ApiEnvelope } from '@/types'
const api=axios.create({baseURL:'/api/v1',timeout:30000})
api.interceptors.request.use(c=>{const token=localStorage.getItem('mobile_token');if(token)c.headers.Authorization=`Bearer ${token}`;return c})
api.interceptors.response.use(r=>{const body=r.data as ApiEnvelope<unknown>;if(body&&typeof body.code==='number'&&body.code!==0)return Promise.reject(new Error(body.message||'请求失败'));return r},e=>{if(e.response?.status===401){localStorage.removeItem('mobile_token');localStorage.removeItem('mobile_user');if(!location.pathname.startsWith('/login'))location.href=`/login?redirect=${encodeURIComponent(location.pathname+location.search)}`}return Promise.reject(new Error(e.response?.data?.message||e.message||'网络请求失败'))})
export default api
