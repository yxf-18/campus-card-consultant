<script setup lang="ts">
import { computed,reactive,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { showFailToast } from 'vant'
import { useAuthStore } from '@/stores/auth'
const router=useRouter();const route=useRoute();const store=useAuthStore();const loading=ref(false)
const method=ref<'USERNAME'|'PHONE'|'STUDENT_NO'>('USERNAME')
const form=reactive({account:'student',password:'Student123'})
const placeholder=computed(()=>method.value==='PHONE'?'请输入绑定手机号':method.value==='STUDENT_NO'?'请输入学号':'用户名或邮箱')
const methods=[{value:'USERNAME',label:'用户名'},{value:'PHONE',label:'手机号'},{value:'STUDENT_NO',label:'学号'}] as const
async function submit(){loading.value=true;try{const user=await store.login(form.account,form.password,method.value);const candidate=route.query.redirect as string|undefined;const redirect=candidate&&candidate.startsWith('/app')?candidate:'/app/home';if(user?.role==='USER'&&!user.profile_complete){await router.replace({path:'/bind-account',query:{redirect}})}else{await router.replace(redirect)}}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
</script>
<template><div class="auth-page"><div class="auth-hero"><span class="pill">SMART CAMPUS · 24H</span><h1>校园卡问题<br/>随时问，放心查</h1><p>知识库优先、引用可追溯，不能让AI替你猜政策。</p></div><div class="auth-card"><h2>欢迎回来</h2><div class="login-methods"><button v-for="item in methods" :key="item.value" :class="{active:method===item.value}" @click="method=item.value">{{item.label}}</button></div><van-field v-model="form.account" label="账号" :placeholder="placeholder" clearable/><van-field v-model="form.password" type="password" label="密码" placeholder="请输入密码" @keyup.enter="submit"/><van-button type="primary" block round :loading="loading" @click="submit">登录</van-button><van-button plain block round @click="router.push('/preview')">游客预览</van-button><p class="auth-link" @click="router.push('/register')">没有账号？立即注册</p><p class="demo-tip">演示用户：student / Student123<br/>绑定后可用手机号或学号登录</p></div></div></template>
