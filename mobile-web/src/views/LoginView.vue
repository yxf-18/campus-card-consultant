<script setup lang="ts">
import { computed,reactive,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
const router=useRouter();const route=useRoute();const store=useAuthStore();const loading=ref(false)
const method=ref<'USERNAME'|'PHONE'|'STUDENT_NO'>('USERNAME')
const savedAccount=localStorage.getItem('mobile_saved_account')||''
const form=reactive({account:savedAccount||'student',password:'Student123'})
const remember=ref(Boolean(savedAccount))
const showPassword=ref(false)
const helpVisible=ref(false)
const errorText=ref('')
const placeholder=computed(()=>method.value==='PHONE'?'请输入绑定手机号':method.value==='STUDENT_NO'?'请输入学号':'请输入用户名')
const methods=[{value:'USERNAME',label:'用户名'},{value:'PHONE',label:'手机号'},{value:'STUDENT_NO',label:'学号'}] as const
function friendly(message:string){
  if(!message)return '登录失败，请稍后重试'
  if(/Network Error/i.test(message))return '网络连接失败，请检查网络后重试'
  if(/timeout/i.test(message))return '请求超时，请稍后重试'
  if(/Failed to fetch/i.test(message))return '无法连接服务，请稍后重试'
  return message
}
function switchMethod(value:'USERNAME'|'PHONE'|'STUDENT_NO'){method.value=value;errorText.value=''}
async function submit(){
  errorText.value=''
  if(!form.account.trim()){errorText.value=`请输入${placeholder.value.replace('请输入','')}`;return}
  if(!form.password){errorText.value='请输入登录密码';return}
  loading.value=true
  try{
    const user=await store.login(form.account.trim(),form.password,method.value)
    if(remember.value)localStorage.setItem('mobile_saved_account',form.account.trim())
    else localStorage.removeItem('mobile_saved_account')
    const candidate=route.query.redirect as string|undefined
    const redirect=candidate&&candidate.startsWith('/app')?candidate:'/app/home'
    if(user?.role==='USER'&&!user.profile_complete){await router.replace({path:'/bind-account',query:{redirect}})}
    else{await router.replace(redirect)}
  }catch(e){errorText.value=friendly((e as Error).message)}finally{loading.value=false}
}
</script>
<template>
  <div class="auth-page">
    <div class="auth-hero"><span class="pill">SMART CAMPUS · 24H</span><h1>校园卡问题<br/>随时问，放心查</h1><p>账号由学校统一开通，登录后可查询本人余额、查看办事指南并保存咨询记录。</p></div>
    <div class="auth-card">
      <h2>欢迎回来</h2>
      <div class="login-methods"><button v-for="item in methods" :key="item.value" :class="{active:method===item.value}" @click="switchMethod(item.value)">{{item.label}}</button></div>
      <van-field v-model="form.account" label="账号" :placeholder="placeholder" clearable autocomplete="username" @update:model-value="errorText=''"/>
      <van-field v-model="form.password" :type="showPassword?'text':'password'" label="密码" placeholder="请输入登录密码" autocomplete="current-password" @update:model-value="errorText=''" @keyup.enter="submit">
        <template #right-icon>
          <button type="button" class="field-icon" :aria-label="showPassword?'隐藏密码':'显示密码'" @click="showPassword=!showPassword">{{showPassword?'隐藏':'显示'}}</button>
        </template>
      </van-field>
      <div class="login-extra">
        <label class="remember"><input v-model="remember" type="checkbox"/>记住账号</label>
        <button type="button" class="link-btn" @click="helpVisible=true">登录遇到问题？</button>
      </div>
      <p v-if="errorText" class="form-error"><span aria-hidden="true">!</span>{{errorText}}</p>
      <van-button type="primary" block round :loading="loading" :disabled="!form.account.trim()||!form.password" @click="submit">登录</van-button>
      <van-button plain block round @click="router.push('/preview')">游客预览</van-button>
      <p class="login-help">没有账号或忘记账号？请联系学校卡务中心开通或找回。</p>
      <p class="demo-tip">演示用户：student / Student123<br/>也可使用手机号 13800000000 或学号 20230001 登录</p>
    </div>
    <van-dialog v-model:show="helpVisible" title="登录帮助" confirm-button-text="知道了">
      <div class="help-body">
        <p>账号由学校统一开通，系统不提供自助注册，数据库里没有账号无法登录。</p>
        <p>账号或密码输入错误时可以直接重试；忘记密码请携带本人证件联系学校卡务中心重置。</p>
        <p>手机号、邮箱修改需要管理员审核通过后才会生效，审核期间原信息继续有效。</p>
      </div>
    </van-dialog>
  </div>
</template>
<style scoped>
.form-error{display:flex;gap:7px;align-items:flex-start;margin:2px 0 6px;padding:9px 12px;border-radius:10px;background:#fff1f0;color:#c0392b;font-size:13px;line-height:1.5}
.form-error span{flex:0 0 auto;width:16px;height:16px;margin-top:1px;border-radius:50%;background:#c0392b;color:#fff;font-size:11px;font-weight:700;display:grid;place-items:center}
.login-extra{display:flex;align-items:center;justify-content:space-between;margin:2px 0 10px;font-size:12px;color:#7c8f9b}
.remember{display:inline-flex;align-items:center;gap:6px}
.remember input{width:14px;height:14px;accent-color:#0f7c73}
.link-btn{border:0;background:none;color:#0f7c73;font-size:12px;padding:0}
.field-icon{border:0;background:none;color:#0f7c73;font-size:12px;padding:0 2px}
.help-body{padding:4px 18px 8px;font-size:13px;line-height:1.7;color:#43606e}
.help-body p{margin:0 0 8px}
.login-help{margin:6px 0 0;text-align:center;color:#7c8f9b;font-size:12px;line-height:1.6}
</style>
