<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { showFailToast,showSuccessToast } from 'vant'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { docApi } from '@/api'
import type { DocumentDetail } from '@/types'
const route=useRoute();const router=useRouter();const doc=ref<DocumentDetail|null>(null);const loading=ref(true)
const html=computed(()=>DOMPurify.sanitize(marked.parse(doc.value?.content||'') as string))
async function load(){loading.value=true;try{doc.value=(await docApi.detail(Number(route.params.id))).data.data.document}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
async function download(){if(!doc.value)return;try{const r=await docApi.download(doc.value.document_id);window.location.href=r.data.data.file_url;showSuccessToast('下载地址已生成')}catch(e){showFailToast((e as Error).message)}}
onMounted(load)
</script><template><div class="page detail-page"><van-nav-bar title="文档详情" left-arrow fixed placeholder @click-left="router.back()"/><van-loading v-if="loading" class="center-loading"/><template v-else-if="doc"><header class="detail-head"><span class="eyebrow">{{doc.category_name||'知识文档'}}</span><h1>{{doc.title}}</h1><p>{{doc.summary}}</p><div class="meta-row"><span>{{doc.source_department||'资料来源'}}</span><span>{{doc.view_count}} 次浏览</span></div></header><article class="markdown-body" v-html="html"></article><div class="detail-actions"><van-button block round type="primary" :disabled="!doc.allow_download" @click="download">{{doc.allow_download?'下载原文件':'该文档未开放下载'}}</van-button><van-button block round plain icon="chat-o" @click="router.push({path:'/app/chat',query:{document_id:doc.document_id}})">就本文提问</van-button></div></template><van-empty v-else description="文档不存在"/></div></template>
