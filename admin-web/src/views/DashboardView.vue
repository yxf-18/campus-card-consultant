<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { statsApi } from '@/api'
const loading = ref(false); const chartEl = ref<HTMLDivElement>(); let chart: echarts.ECharts | null = null
const metrics = ref<any>({ user: {}, document: {}, qa: {}, feedback: {} })
async function load() {
  loading.value = true
  try {
    const response = await statsApi.overview({})
    metrics.value = response.data.data
    if (chartEl.value) {
      chart ||= echarts.init(chartEl.value)
      chart.setOption({ tooltip: { trigger: 'axis' }, legend: { data: ['提问数', '活跃用户'] }, grid: { left: 36, right: 20, top: 40, bottom: 30 }, xAxis: { type: 'category', data: metrics.value.trend.map((item: any) => item.date) }, yAxis: { type: 'value' }, series: [{ name: '提问数', type: 'line', smooth: true, areaStyle: {}, data: metrics.value.trend.map((item: any) => item.qa_count) }, { name: '活跃用户', type: 'bar', data: metrics.value.trend.map((item: any) => item.user_active) }] })
    }
  } catch (error) { ElMessage.error((error as Error).message) } finally { loading.value = false }
}
async function exportCsv() {
  const end = new Date(); const start = new Date(); start.setDate(end.getDate() - 29)
  const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  try { const r = await statsApi.export({ type: 'qa', start_date: fmt(start), end_date: fmt(end), format: 'CSV', desensitize: true }); window.open(r.data.data.file_url, '_blank') } catch (e) { ElMessage.error((e as Error).message) }
}
function resize() { chart?.resize() }
onMounted(() => { load(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart?.dispose() })
</script>
<template>
  <div v-loading="loading" class="page-stack">
    <div class="hero-card"><div><span class="eyebrow">运营总览</span><h2>知识内容运营状态</h2><p>关注问答效果、知识内容与用户反馈，持续维护可信知识。</p></div><div class="filter-bar"><el-button type="primary" plain @click="load">刷新数据</el-button><el-button @click="exportCsv">导出问答CSV</el-button></div></div>
    <div class="metric-grid"><article class="metric-card"><span>用户总数</span><strong>{{ metrics.user.total || 0 }}</strong><small>近30天新增 {{ metrics.user.new || 0 }}</small></article><article class="metric-card mint"><span>已发布文档</span><strong>{{ metrics.document.published || 0 }}</strong><small>文档总数 {{ metrics.document.total || 0 }}</small></article><article class="metric-card violet"><span>问答量</span><strong>{{ metrics.qa.total || 0 }}</strong><small>有依据 {{ metrics.qa.answered || 0 }}</small></article><article class="metric-card amber"><span>待处理反馈</span><strong>{{ metrics.feedback.pending || 0 }}</strong><small>点赞 {{ metrics.feedback.like || 0 }} · 点踩 {{ metrics.feedback.dislike || 0 }}</small></article></div>
    <div class="panel"><div class="panel-head"><div><h3>近30天趋势</h3><p>用户活跃与提问变化</p></div></div><div ref="chartEl" class="chart"></div></div>
  </div>
</template>
