<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog,showFailToast,showSuccessToast } from 'vant'
import { sessionApi } from '@/api'
import type { Session } from '@/types'
const router=useRouter();const rows=ref<Session[]>([]);const loading=ref(false)
async function load(){loading.value=true;try{rows.value=(await sessionApi.list({page:1,page_size:100})).data.data.list}catch(e){showFailToast((e as Error).message)}finally{loading.value=false}}
async function rename(item:Session){try{const result=await showConfirmDialog({title:'重命名会话',message:'请输入新标题',showCancelButton:true,confirmButtonText:'保存'}).catch(()=>null);if(!result)return;const title=window.prompt('会话标题',item.title)?.trim();if(title){await sessionApi.rename(item.session_id,title);showSuccessToast('已重命名');await load()}}catch(e){showFailToast((e as Error).message)}}
async function remove(item:Session){try{await showConfirmDialog({title:'删除会话',message:`确定删除“${item.title}”吗？`});await sessionApi.remove(item.session_id);showSuccessToast('已删除');await load()}catch(e:any){if(e!=='cancel'&&e!=='close')showFailToast(e.message||'操作失败')}}
onMounted(load)
</script><template><div class="page sessions-page"><div class="page-head row-head"><div><span class="eyebrow">CONVERSATIONS</span><h1>历史会话</h1></div><van-button size="small" round type="primary" icon="plus" @click="router.push('/app/chat')">新问题</van-button></div><van-loading v-if="loading" class="center-loading"/><template v-else-if="rows.length"><article v-for="item in rows" :key="item.session_id" class="session-card"><div @click="router.push(`/app/chat/${item.session_id}`)"><h3>{{item.title}}</h3><p>{{item.last_message_at||'尚无消息'}} · {{item.message_count||0}} 条消息</p></div><van-button size="mini" plain @click="rename(item)">重命名</van-button><van-button size="mini" plain type="danger" @click="remove(item)">删除</van-button></article></template><van-empty v-else description="还没有历史会话"/></div></template>
