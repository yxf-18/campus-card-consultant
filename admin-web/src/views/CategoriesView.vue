<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { categoryApi } from '@/api'
import type { Category } from '@/types'
const rows = ref<Category[]>([]); const loading = ref(false); const dialog = ref(false); const editingId = ref<number | null>(null)
const form = reactive({ name: '', icon: '', sort_order: 0, status: 'ENABLED' })
async function load() { loading.value = true; try { rows.value = (await categoryApi.list()).data.data.list } catch (e) { ElMessage.error((e as Error).message) } finally { loading.value = false } }
function openCreate() { editingId.value = null; Object.assign(form, { name: '', icon: '', sort_order: 0, status: 'ENABLED' }); dialog.value = true }
function openEdit(row: Category) { editingId.value = row.category_id; Object.assign(form, { name: row.name, icon: row.icon, sort_order: row.sort_order, status: row.status }); dialog.value = true }
async function save() {
  if (!form.name.trim()) return ElMessage.warning('请输入分类名称')
  try {
    if (editingId.value) await categoryApi.update(editingId.value, form); else await categoryApi.create(form)
    ElMessage.success('分类已保存'); dialog.value = false; await load()
  } catch (e) { ElMessage.error((e as Error).message) }
}
async function remove(row: Category) {
  try { await ElMessageBox.confirm(`确定删除分类“${row.name}”吗？`, '删除确认', { type: 'warning' }); await categoryApi.remove(row.category_id); ElMessage.success('分类已删除'); await load() } catch (e: any) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '操作失败') }
}
onMounted(load)
</script>
<template>
  <div class="panel page-stack">
    <div class="panel-head"><div><h3>知识分类</h3><p>控制移动端首页分类、排序与可用状态</p></div><el-button type="primary" @click="openCreate">新增分类</el-button></div>
    <el-table v-loading="loading" :data="rows" stripe>
      <el-table-column prop="name" label="分类名称" min-width="160" /><el-table-column prop="sort_order" label="排序" width="90" /><el-table-column prop="document_count" label="文档数" width="100" /><el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'">{{ row.status === 'ENABLED' ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column prop="updated_at" label="更新时间" width="180" /><el-table-column label="操作" width="160" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openEdit(row)">编辑</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="dialog" :title="editingId ? '编辑分类' : '新增分类'" width="480px"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="form.name" maxlength="50" /></el-form-item><el-form-item label="图标/封面地址"><el-input v-model="form.icon" placeholder="可填写图片 URL" /></el-form-item><el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" /></el-form-item><el-form-item label="状态"><el-radio-group v-model="form.status"><el-radio value="ENABLED">启用</el-radio><el-radio value="DISABLED">停用</el-radio></el-radio-group></el-form-item></el-form><template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  </div>
</template>
