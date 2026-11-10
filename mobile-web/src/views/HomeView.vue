<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast } from 'vant'
import { docApi } from '@/api'
import type { Category } from '@/types'
const router=useRouter();const categories=ref<Category[]>([]);const keyword=ref('');const loading=ref(true)
async function load(){loading.value=true;try{categories.value=(await docApi.home(8)).data.data.categories}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
function search(){router.push({path:'/app/documents',query:{keyword:keyword.value}})}
onMounted(load)
</script>
<template><div class="page home-page"><header class="home-head"><div><span class="eyebrow light">CAMPUS CARD GUIDE</span><h1>今天想了解<br/>校园卡的什么？</h1></div><div class="head-badge">AI</div></header><van-search v-model="keyword" shape="round" placeholder="搜索使用指南、充值、补办、优惠" @search="search" @click-input="undefined"/><section class="quick-grid"><button @click="router.push('/app/chat')"><span>问</span><strong>智能咨询</strong><small>带引用回答</small></button><button @click="router.push({path:'/app/documents',query:{keyword:'补办'}})"><span>办</span><strong>充值补办</strong><small>办理流程指引</small></button><button @click="router.push({path:'/app/documents',query:{keyword:'优惠'}})"><span>惠</span><strong>优惠政策</strong><small>官方信息查询</small></button></section><van-loading v-if="loading" class="center-loading"/><template v-else><section v-for="category in categories" :key="category.category_id" class="category-section"><div class="section-title"><div><span>{{category.name}}</span><small>{{category.documents.length}} 篇资料</small></div><button @click="router.push({path:'/app/documents',query:{category_id:category.category_id}})">查看全部</button></div><div class="doc-grid"><article v-for="doc in category.documents" :key="doc.document_id" @click="router.push(`/app/documents/${doc.document_id}`)"><div class="doc-cover">{{doc.title.slice(0,1)}}</div><h3>{{doc.title}}</h3><p>{{doc.summary}}</p><span>{{doc.view_count}} 次浏览</span></article></div></section></template><van-empty v-if="!loading&&!categories.length" description="暂无知识内容"/></div></template>
