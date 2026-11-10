<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
const form = reactive({ account: 'admin', password: 'Admin12345' })
const loading = ref(false)
const router = useRouter(); const route = useRoute(); const store = useAuthStore()
async function submit() {
  loading.value = true
  try {
    await store.login(form.account, form.password)
    const candidate=route.query.redirect as string|undefined
    await router.push(candidate&&candidate.startsWith('/console')?candidate:'/console/dashboard')
  } catch (error) { ElMessage.error((error as Error).message) } finally { loading.value = false }
}
</script>
<template>
  <div class="login-page">
    <section class="login-visual"><div class="login-badge">CAMPUS CARD · AI CONSULTANT</div><h1>让校园卡咨询<br />更及时、更可信</h1><p>统一管理知识内容、同步任务、用户反馈与运营数据。</p><div class="visual-orbit"><span>RAG</span><span>安全兜底</span><span>引用可追溯</span></div></section>
    <section class="login-panel"><div class="login-card"><p class="eyebrow">管理后台</p><h2>管理员登录</h2><p class="muted">使用管理员账号进入知识运营中心</p>
      <el-form label-position="top" @submit.prevent="submit"><el-form-item label="账号"><el-input v-model="form.account" size="large" placeholder="用户名、手机号或邮箱" /></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" show-password size="large" @keyup.enter="submit" /></el-form-item><el-button type="primary" size="large" class="full" :loading="loading" @click="submit">进入后台</el-button></el-form>
      <p class="login-tip">演示账号：admin / Admin12345</p></div></section>
  </div>
</template>
