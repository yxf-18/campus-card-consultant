<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { showFailToast } from 'vant'
import { docApi } from '@/api'
import type { Category,DocCard } from '@/types'
const route=useRoute();const router=useRouter();const keyword=ref(String(route.query.keyword||''));const categoryId=ref<number|undefined>(route.query.category_id?Number(route.query.category_id):undefined);const categories=ref<Category[]>([]);const rows=ref<DocCard[]>([]);const loading=ref(false);const page=ref(1);const finished=ref(false)
async function load(reset=false){if(reset){page.value=1;finished.value=false;rows.value=[]}loading.value=true;try{const r=await docApi.search({keyword:keyword.value,category_id:categoryId.value,page:page.value,page_size:12});rows.value=[...rows.value,...r.data.data.list];finished.value=!(r.data.pagination?.has_more)}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
async function loadMore(){if(finished.value||loading.value)return;page.value++;await load()}
onMounted(async()=>{try{categories.value=(await docApi.home(20)).data.data.categories}catch{};await load(true)})
</script>
<template><div class="page search-page"><div class="page-head"><span class="eyebrow">KNOWLEDGE LIBRARY</span><h1>资料检索</h1></div><van-search v-model="keyword" shape="round" placeholder="输入关键词" @search="load(true)"/><div class="chip-row"><button :class="{active:!categoryId}" @click="categoryId=undefined;load(true)">全部</button><button v-for="item in categories" :key="item.category_id" :class="{active:categoryId===item.category_id}" @click="categoryId=item.category_id;load(true)">{{item.name}}</button></div><van-list v-model:loading="loading" :finished="finished" finished-text="没有更多了" @load="loadMore"><article v-for="doc in rows" :key="doc.document_id" class="list-doc" @click="router.push(`/app/documents/${doc.document_id}`)"><div class="doc-cover">{{doc.title.slice(0,1)}}</div><div><h3>{{doc.title}}</h3><p>{{doc.summary||'暂无摘要'}}</p><span>{{doc.category_name||'知识文档'}} · {{doc.view_count}}次浏览</span></div></article></van-list><van-empty v-if="!loading&&!rows.length" description="没有匹配的资料"/></div></template>
