import { createRouter,createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
const router=createRouter({history:createWebHistory(),routes:[
  {path:'/',redirect:'/login'},
  {path:'/login',component:()=>import('@/views/LoginView.vue'),meta:{public:true}},
  {path:'/preview',component:()=>import('@/views/PreviewView.vue'),meta:{public:true}},
  {path:'/bind-account',component:()=>import('@/views/BindAccountView.vue'),meta:{auth:true}},
  {path:'/app',component:()=>import('@/layouts/MobileLayout.vue'),meta:{auth:true},children:[
    {path:'',redirect:'/app/home'},
    {path:'home',component:()=>import('@/views/HomeView.vue')},
    {path:'documents',component:()=>import('@/views/DocumentsView.vue')},
    {path:'documents/:id',component:()=>import('@/views/DocumentDetailView.vue')},
    {path:'chat/:sessionId?',component:()=>import('@/views/ChatView.vue')},
    {path:'sessions',component:()=>import('@/views/SessionsView.vue')},
    {path:'profile',component:()=>import('@/views/ProfileView.vue')}
  ]},
  {path:'/:pathMatch(.*)*',redirect:'/login'}
]})
router.beforeEach(async to=>{const store=useAuthStore();if(to.meta.public)return true;if(!to.meta.auth)return true;if(!store.token)return{path:'/login',query:{redirect:to.fullPath}};try{const user=await store.ensureUser();if(user?.role==='USER'&&!user.profile_complete&&to.path!='/bind-account')return{path:'/bind-account',query:{redirect:to.fullPath}};return true}catch{await store.logout();return{path:'/login',query:{redirect:to.fullPath}}}})
export default router
