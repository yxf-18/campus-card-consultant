<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
const savedAccount = localStorage.getItem('admin_saved_account') || ''
const form = reactive({ account: savedAccount || 'admin', password: 'Admin12345' })
const remember = ref(Boolean(savedAccount))
const loading = ref(false)
const errorText = ref('')
const router = useRouter(); const route = useRoute(); const store = useAuthStore()
function friendly(message: string) {
  if (/Network Error/i.test(message)) return '网络连接失败，请检查网络后重试'
  if (/timeout/i.test(message)) return '请求超时，请稍后重试'
  if (!message) return '登录失败，请稍后重试'
  return message
}
async function submit() {
  errorText.value = ''
  if (!form.account.trim()) { errorText.value = '请输入管理员账号'; return }
  if (!form.password) { errorText.value = '请输入登录密码'; return }
  loading.value = true
  try {
    await store.login(form.account.trim(), form.password)
    if (remember.value) localStorage.setItem('admin_saved_account', form.account.trim())
    else localStorage.removeItem('admin_saved_account')
    const candidate = route.query.redirect as string | undefined
    await router.push(candidate && candidate.startsWith('/console') ? candidate : '/console/dashboard')
  } catch (error) {
    errorText.value = friendly((error as Error).message)
  } finally { loading.value = false }
}
</script>
<template>
  <div class="login-page">
    <section class="login-visual">
      <div class="login-badge">CAMPUS CARD · AI CONSULTANT</div>
      <h1>让校园卡咨询<br />更及时、更可信</h1>
      <p>统一管理知识内容、用户资料审核、反馈与运营数据。</p>
      <div class="visual-orbit"><span>智能问答</span><span>隐私保护</span><span>资料可追溯</span></div>
    </section>
    <section class="login-panel">
      <div class="login-card">
        <p class="eyebrow">管理后台</p>
        <h2>管理员登录</h2>
        <p class="muted">使用管理员账号进入知识运营中心</p>
        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="管理员账号">
            <el-input v-model="form.account" size="large" placeholder="请输入管理员账号" clearable autocomplete="username" @input="errorText = ''" />
          </el-form-item>
          <el-form-item label="登录密码">
            <el-input v-model="form.password" type="password" show-password size="large" placeholder="请输入登录密码" autocomplete="current-password" @input="errorText = ''" @keyup.enter="submit" />
          </el-form-item>
          <div class="login-extra">
            <el-checkbox v-model="remember">记住账号</el-checkbox>
            <span class="muted">仅管理员可登录本后台</span>
          </div>
          <p v-if="errorText" class="form-error"><span aria-hidden="true">!</span>{{ errorText }}</p>
          <el-button type="primary" size="large" class="full" :loading="loading" @click="submit">进入后台</el-button>
        </el-form>
        <p class="login-tip">演示账号：admin / Admin12345</p>
      </div>
    </section>
  </div>
</template>
<style scoped>
.login-extra{display:flex;align-items:center;justify-content:space-between;margin:-4px 0 12px;font-size:12px}
.login-extra .muted{font-size:12px}
.form-error{display:flex;gap:8px;align-items:flex-start;margin:-2px 0 10px;padding:9px 12px;border-radius:9px;background:#fff1f0;color:#c0392b;font-size:13px;line-height:1.5}
.form-error span{flex:0 0 auto;width:16px;height:16px;margin-top:1px;border-radius:50%;background:#c0392b;color:#fff;font-size:11px;font-weight:700;display:grid;place-items:center}
</style>
