<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { syncApi } from '@/api'
import type { SyncTask } from '@/types'
const rows=ref<SyncTask[]>([]); const loading=ref(false); const page=ref(1); const total=ref(0); const filters=reactive({status:''})
function type(s:string){return s==='SUCCESS'?'success':s==='FAILED'?'danger':s==='RUNNING'?'warning':'info'}
async function load(){loading.value=true;try{const r=await syncApi.list({...filters,page:page.value,page_size:20});rows.value=r.data.data.list;total.value=r.data.pagination?.total||0}catch(e){ElMessage.error((e as Error).message)}finally{loading.value=false}}
async function retry(row:SyncTask){try{await syncApi.retry(row.task_id);ElMessage.success('任务已重新排队');await load()}catch(e){ElMessage.error((e as Error).message)}}
onMounted(load)
</script>
<template><div class="panel page-stack"><div class="panel-head"><div><h3>RAG 同步任务</h3><p>跟踪索引生成结果并重试失败任务</p></div><div class="filter-bar"><el-select v-model="filters.status" placeholder="全部状态" clearable><el-option label="等待" value="PENDING"/><el-option label="运行中" value="RUNNING"/><el-option label="成功" value="SUCCESS"/><el-option label="失败" value="FAILED"/></el-select><el-button type="primary" @click="page=1;load()">筛选</el-button><el-button @click="load">刷新</el-button></div></div><el-table v-loading="loading" :data="rows" stripe><el-table-column prop="task_id" label="任务" width="80"/><el-table-column prop="document_title" label="文档" min-width="220"/><el-table-column prop="task_type" label="类型" width="100"/><el-table-column prop="target_version" label="版本" width="80"/><el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="type(row.status)">{{row.status}}</el-tag></template></el-table-column><el-table-column prop="chunk_count" label="切片" width="80"/><el-table-column prop="error_message" label="失败原因" min-width="220" show-overflow-tooltip/><el-table-column prop="created_at" label="创建时间" width="180"/><el-table-column label="操作" width="90"><template #default="{row}"><el-button v-if="row.status==='FAILED'" link type="primary" @click="retry(row)">重试</el-button></template></el-table-column></el-table><div class="pager"><el-pagination v-model:current-page="page" layout="prev, pager, next" :page-size="20" :total="total" @current-change="load"/></div></div></template>
