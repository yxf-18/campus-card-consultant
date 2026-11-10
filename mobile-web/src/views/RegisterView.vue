<script setup lang="ts">
import { reactive,ref } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast,showSuccessToast } from 'vant'
import { authApi } from '@/api'
const router=useRouter();const loading=ref(false);const form=reactive({username:'',password:'',nickname:'',privacy_agreed:false})
async function submit(){if(!form.privacy_agreed)return showFailToast('请先同意隐私协议');loading.value=true;try{await authApi.register({...form});showSuccessToast('注册成功，请登录并绑定手机号和学号');await router.replace('/login')}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
</script>
<template><div class="auth-page register"><div class="auth-hero"><span class="pill">CREATE ACCOUNT</span><h1>加入校园卡<br/>智能咨询服务</h1><p>首次登录后绑定手机号和学号，之后可选择手机号或学号登录。</p></div><div class="auth-card"><h2>创建账号</h2><van-field v-model="form.username" label="用户名" placeholder="4-32位字母、数字或下划线"/><van-field v-model="form.nickname" label="昵称" placeholder="可选"/><van-field v-model="form.password" type="password" label="密码" placeholder="至少8位，包含字母和数字"/><van-checkbox v-model="form.privacy_agreed" shape="square">我已阅读并同意隐私说明</van-checkbox><van-button type="primary" block round :loading="loading" @click="submit">注册</van-button><van-button plain block round @click="router.push('/preview')">游客预览</van-button><p class="auth-link" @click="router.back()">返回登录</p></div></div></template>
