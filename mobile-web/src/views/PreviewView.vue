<script setup lang="ts">
import { useRouter } from 'vue-router'
const router=useRouter()
const categories=[{name:'使用指南',icon:'卡',desc:'基础使用与安全提醒'},{name:'充值补办',icon:'充',desc:'挂失、补办流程指引'},{name:'消费管理',icon:'消',desc:'消费范围与交易核对'},{name:'优惠政策',icon:'惠',desc:'优惠资格与查询渠道'}]
</script>
<template><div class="preview-page"><header class="home-head"><div><span class="eyebrow light">GUEST PREVIEW</span><h1>校园卡智能咨询<br/>游客预览</h1><p class="preview-note">当前为只读界面预览，不查询知识库，也不能查看文档或使用问答功能。账号由学校统一开通。</p></div><div class="head-badge">访</div></header><section class="preview-banner">登录后可查看真实文档、查询本人余额、进行AI问答并保存历史会话</section><section class="preview-grid"><article v-for="item in categories" :key="item.name"><div class="doc-cover">{{item.icon}}</div><h3>{{item.name}}</h3><p>{{item.desc}}</p><span>登录后查看</span></article></section><div class="preview-actions"><van-button type="primary" block round @click="router.push('/login')">登录并体验</van-button></div></div></template>
