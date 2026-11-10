<script setup lang="ts">
import { computed } from 'vue'
import { useRoute,useRouter } from 'vue-router'
const route=useRoute();const router=useRouter()
const active=computed(()=>{if(route.path==='/app/home')return 'home';if(route.path.startsWith('/app/chat'))return 'chat';if(route.path.startsWith('/app/sessions'))return 'sessions';if(route.path.startsWith('/app/profile'))return 'profile';return 'documents'})
function change(name:string){router.push(name==='home'?'/app/home':name==='chat'?'/app/chat':name==='sessions'?'/app/sessions':'/app/profile')}
</script>
<template><div class="mobile-shell"><main class="mobile-content"><router-view/></main><van-tabbar :model-value="active" active-color="#0f7c73" inactive-color="#8497a5" @change="change"><van-tabbar-item name="home" icon="home-o" @click="router.push('/app/home')">首页</van-tabbar-item><van-tabbar-item name="chat" icon="chat-o" @click="router.push('/app/chat')">问答</van-tabbar-item><van-tabbar-item name="sessions" icon="records-o" @click="router.push('/app/sessions')">会话</van-tabbar-item><van-tabbar-item name="profile" icon="user-o" @click="router.push('/app/profile')">我的</van-tabbar-item></van-tabbar></div></template>
