<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { configApi } from '@/api'
const groups=ref<any[]>([]);const loading=ref(false);const dialog=ref(false);const current=ref<any>(null);const form=reactive({config_value:'',remark:''})
const labels:Record<string,string>={home:'首页',rag:'RAG检索',chat:'对话记忆',auth:'认证安全',upload:'文件上传',download:'下载',service:'服务渠道',security:'安全策略',web:'联网检索'}
async function load(){loading.value=true;try{const r=await configApi.list();groups.value=r.data.data.configs}catch(e){ElMessage.error((e as Error).message)}finally{loading.value=false}}
function edit(item:any){current.value=item;form.config_value=item.config_value;form.remark=item.remark;dialog.value=true}
async function save(){try{await configApi.update(current.value.config_key,{...form});ElMessage.success('配置已保存');dialog.value=false;await load()}catch(e){ElMessage.error((e as Error).message)}}
onMounted(load)
</script>
<template><div v-loading="loading" class="page-stack"><div class="config-intro"><span class="eyebrow">运行参数</span><h2>系统配置</h2><p>配置项受白名单与类型校验保护，修改后立即生效。</p></div><div v-for="item in groups" :key="item.config_key" class="panel config-row"><div><div class="config-title"><strong>{{item.config_key}}</strong><el-tag size="small" type="info">{{item.config_group}}</el-tag></div><p>{{item.remark}}</p></div><code>{{item.config_value}}</code><el-button link type="primary" @click="edit(item)">编辑</el-button></div><el-dialog v-model="dialog" title="修改配置" width="520px"><el-form label-position="top"><el-form-item label="配置键"><el-input :model-value="current?.config_key" disabled/></el-form-item><el-form-item label="配置值"><el-input v-model="form.config_value" type="textarea" :rows="3"/></el-form-item><el-form-item label="说明"><el-input v-model="form.remark"/></el-form-item></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog></div></template>
