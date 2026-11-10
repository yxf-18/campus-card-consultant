import api from './client'
import type { ApiEnvelope,CardAccount,Category,ChatMessage,DocCard,DocumentDetail,ProfileChangeRequest,Session,User } from '@/types'
export const authApi={
  login:(body:Record<string,unknown>)=>api.post<ApiEnvelope<any>>('/auth/login',body),
  me:()=>api.get<ApiEnvelope<{user:User}>>('/auth/me'),
  updateProfile:(body:Record<string,unknown>)=>api.put<ApiEnvelope<{user:User;pending_changes:Record<string,string>;message:string}>>('/auth/profile',body),
  changeRequests:()=>api.get<ApiEnvelope<{list:ProfileChangeRequest[]}>>('/auth/profile/change-requests'),
  logout:()=>api.post('/auth/logout')
}
export const cardApi={balance:()=>api.get<ApiEnvelope<{account:CardAccount|null;message?:string}>>('/card/balance')}
export const docApi={home:(limit=5)=>api.get<ApiEnvelope<{categories:Category[]}>>('/home/categories',{params:{limit}}),search:(params:Record<string,unknown>)=>api.get<ApiEnvelope<{list:DocCard[]}>>('/documents',{params}),detail:(id:number)=>api.get<ApiEnvelope<{document:DocumentDetail}>>(`/documents/${id}`),download:(id:number)=>api.get<ApiEnvelope<{file_url:string;file_name:string;expires_in:number}>>(`/documents/${id}/download`)}
export const sessionApi={list:(params:Record<string,unknown>={})=>api.get<ApiEnvelope<{list:Session[]}>>('/chat/sessions',{params}),create:(title?:string)=>api.post('/chat/sessions',{title}),rename:(id:number,title:string)=>api.patch(`/chat/sessions/${id}`,{title}),remove:(id:number)=>api.delete(`/chat/sessions/${id}`),messages:(id:number)=>api.get<ApiEnvelope<{session:Session;messages:ChatMessage[]}>>(`/chat/sessions/${id}/messages`)}
export const chatApi={feedback:(id:number,body:Record<string,unknown>)=>api.post(`/chat/messages/${id}/feedback`,body)}
