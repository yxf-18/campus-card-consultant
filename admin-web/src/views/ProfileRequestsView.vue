<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { profileRequestApi } from '@/api'
import type { ProfileChangeRequest } from '@/types'
const rows = ref<ProfileChangeRequest[]>([]); const loading = ref(false); const page = ref(1); const total = ref(0)
const filters = reactive({ status: 'PENDING', keyword: '' })
const statusText: Record<string, string> = { PENDING: '待审核', APPROVED: '已通过', REJECTED: '已驳回' }
const statusType: Record<string, 'warning' | 'success' | 'danger'> = { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger' }
async function load() {
  loading.value = true
  try {
    const r = await profileRequestApi.list({ ...filters, page: page.value, page_size: 20 })
    rows.value = r.data.data.list
    total.value = r.data.pagination?.total || 0
  } catch (e) { ElMessage.error((e as Error).message) } finally { loading.value = false }
}
async function approve(row: ProfileChangeRequest) {
  try {
    await ElMessageBox.confirm(`确认把用户“${row.nickname || row.username}”的${row.field_label}由 ${row.old_value || '未填写'} 改为 ${row.new_value} 吗？`, '审核通过', { type: 'warning' })
    await profileRequestApi.review(row.request_id, { status: 'APPROVED', remark: '管理员审核通过' })
    ElMessage.success('已通过，用户资料已更新')
    await load()
  } catch (e: any) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '操作失败') }
}
async function reject(row: ProfileChangeRequest) {
  try {
    const result = await ElMessageBox.prompt('请填写驳回原因，用户可在个人中心看到', '驳回申请', {
      inputPlaceholder: '例如：手机号信息与学校登记不一致', confirmButtonText: '确认驳回', cancelButtonText: '取消'
    })
    await profileRequestApi.review(row.request_id, { status: 'REJECTED', remark: result.value || '管理员驳回' })
    ElMessage.success('已驳回')
    await load()
  } catch (e: any) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '操作失败') }
}
onMounted(load)
</script>
<template>
  <div class="panel page-stack">
    <div class="panel-head"><div><h3>资料变更审核</h3><p>用户修改手机号或邮箱后，需要管理员审核通过才会写入账号资料</p></div>
      <div class="filter-bar">
        <el-input v-model="filters.keyword" placeholder="用户名/昵称/学号/手机号" clearable style="width:220px" @keyup.enter="page=1;load()" />
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width:140px">
          <el-option label="待审核" value="PENDING" /><el-option label="已通过" value="APPROVED" /><el-option label="已驳回" value="REJECTED" />
        </el-select>
        <el-button type="primary" @click="page=1;load()">筛选</el-button><el-button @click="load">刷新</el-button>
      </div>
    </div>
    <el-table v-loading="loading" :data="rows" stripe>
      <el-table-column label="用户" min-width="170"><template #default="{row}"><div class="doc-title"><strong>{{row.nickname || row.username}}</strong><small>@{{row.username}} · 学号 {{row.student_no || '未填写'}}</small></div></template></el-table-column>
      <el-table-column prop="field_label" label="变更项" width="100" />
      <el-table-column label="原信息" min-width="170"><template #default="{row}"><span class="muted">{{row.old_value || '未填写'}}</span></template></el-table-column>
      <el-table-column label="新信息" min-width="180"><template #default="{row}"><strong>{{row.new_value}}</strong></template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="statusType[row.status]">{{statusText[row.status] || row.status}}</el-tag></template></el-table-column>
      <el-table-column prop="created_at" label="提交时间" width="180" />
      <el-table-column prop="remark" label="审核备注" min-width="150" show-overflow-tooltip />
      <el-table-column label="操作" width="150" fixed="right"><template #default="{row}"><template v-if="row.status === 'PENDING'"><el-button link type="success" @click="approve(row)">通过</el-button><el-button link type="danger" @click="reject(row)">驳回</el-button></template><span v-else class="muted">已处理</span></template></el-table-column>
    </el-table>
    <div class="pager"><el-pagination v-model:current-page="page" layout="prev, pager, next" :page-size="20" :total="total" @current-change="load" /></div>
  </div>
</template>
