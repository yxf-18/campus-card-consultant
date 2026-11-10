<script setup lang="ts">
import { onMounted,reactive,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { showFailToast,showSuccessToast } from 'vant'
import { useAuthStore } from '@/stores/auth'
const route=useRoute();const router=useRouter();const store=useAuthStore();const loading=ref(false)
const form=reactive({phone:'',student_no:'',nickname:'',email:''})
onMounted(async()=>{const user=await store.ensureUser();if(user){form.phone=user.phone||'';form.student_no=user.student_no||'';form.nickname=user.nickname||'';form.email=user.email||''}})
async function submit(){if(!/^1\d{10}$/.test(form.phone))return showFailToast('请输入正确的11位手机号');if(!form.student_no.trim())return showFailToast('请输入学号');loading.value=true;try{await store.updateProfile({...form});showSuccessToast('绑定成功');await router.replace((route.query.redirect as string)||'/app/home')}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
</script>
<template><div class="bind-page"><header><span class="eyebrow">ACCOUNT BINDING</span><h1>完善账号信息</h1><p>绑定手机号和学号后，可以使用用户名、手机号或学号登录。</p></header><section class="bind-card"><van-field v-model="form.phone" type="tel" label="手机号" maxlength="11" placeholder="请输入11位手机号"/><van-field v-model="form.student_no" label="学号" maxlength="32" placeholder="请输入学号"/><van-field v-model="form.nickname" label="昵称" maxlength="32" placeholder="选填"/><van-field v-model="form.email" label="邮箱" maxlength="64" placeholder="选填"/><van-button type="primary" block round :loading="loading" @click="submit">完成绑定</van-button><van-button plain block round @click="store.logout();router.replace('/login')">退出登录</van-button></section></div></template>
