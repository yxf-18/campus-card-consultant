<script setup lang="ts">
import { onMounted,reactive,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { showFailToast,showSuccessToast } from 'vant'
import { useAuthStore } from '@/stores/auth'
const route=useRoute();const router=useRouter();const store=useAuthStore();const loading=ref(false)
const form=reactive({phone:'',student_no:'',nickname:'',email:''})
onMounted(async()=>{const user=await store.refreshUser();if(user){form.phone=user.phone||'';form.student_no=user.student_no||'';form.nickname=user.nickname||'';form.email=user.email||''}})
async function submit(){
  if(!/^1\d{10}$/.test(form.phone))return showFailToast('请输入正确的11位手机号')
  if(!form.student_no.trim())return showFailToast('请输入学号')
  if(form.email&&!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email))return showFailToast('请输入正确的邮箱地址')
  loading.value=true
  try{
    const result=await store.updateProfile({...form})
    const pending=Object.keys(result.pending_changes||{})
    if(pending.length){showSuccessToast('修改申请已提交，请等待管理员审核');await router.replace('/app/profile')}
    else{showSuccessToast(result.message||'资料已更新');await router.replace((route.query.redirect as string)||'/app/profile')}
  }catch(e){showFailToast((e as Error).message)}finally{loading.value=false}
}
</script>
<template><div class="bind-page"><header><span class="eyebrow">ACCOUNT PROFILE</span><h1>修改账号资料</h1><p>学号和昵称可以直接修改；手机号、邮箱修改需要管理员审核，审核通过前原信息继续有效。</p></header><section class="bind-card"><van-field v-model="form.phone" type="tel" label="手机号" maxlength="11" placeholder="请输入11位手机号"/><van-field v-model="form.student_no" label="学号" maxlength="32" placeholder="请输入学号"/><van-field v-model="form.nickname" label="昵称" maxlength="32" placeholder="选填"/><van-field v-model="form.email" label="邮箱" maxlength="64" placeholder="选填"/><p class="bind-note">手机号修改后需管理员审核，审核结果可在“我的”页面查看。</p><van-button type="primary" block round :loading="loading" @click="submit">保存资料</van-button><van-button plain block round @click="store.logout();router.replace('/login')">退出登录</van-button></section></div></template>
<style scoped>
.bind-note{margin:2px 4px 4px;padding:10px 12px;border-radius:11px;background:#eef7f5;color:#48706f;font-size:11px;line-height:1.6}
</style>
