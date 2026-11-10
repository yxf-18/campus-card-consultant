<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog } from 'vant'
import { authApi,cardApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { CardAccount,ProfileChangeRequest } from '@/types'
const store=useAuthStore();const router=useRouter()
const account=ref<CardAccount|null>(null)
const requests=ref<ProfileChangeRequest[]>([])
const pending=computed(()=>requests.value.filter(item=>item.status==='PENDING'))
const statusText:Record<string,string>={PENDING:'待审核',APPROVED:'已通过',REJECTED:'已驳回'}
async function loadExtra(){
  try{
    await store.refreshUser()
    const [balance,changes]=await Promise.all([cardApi.balance(),authApi.changeRequests()])
    account.value=balance.data.data.account
    requests.value=changes.data.data.list
  }catch{/* 页面主体仍可正常使用 */}
}
async function logout(){try{await showConfirmDialog({title:'退出登录',message:'确定退出当前账号吗？'});await store.logout();router.replace('/login')}catch{}}
onMounted(loadExtra)
</script>
<template><div class="page profile-page"><header class="profile-hero"><div class="avatar">{{store.user?.nickname?.slice(0,1)||'访'}}</div><div><span class="eyebrow light">MY ACCOUNT</span><h1>{{store.user?.nickname||'游客'}}</h1><p>{{store.user?`@${store.user.username}`:'登录后保存问答记录'}}</p></div></header><template v-if="store.user">
  <section class="balance-card"><div class="balance-head"><span>我的校园卡</span><small>仅本人可查询</small></div><strong class="balance-value">¥ {{account?.balance || '—'}}</strong><div class="balance-meta"><span>{{account?.card_no || '未绑定卡片'}}</span><span>{{account ? (account.status==='ACTIVE'?'状态正常':'状态异常') : '未绑定'}}</span></div><p class="balance-tip">为保护隐私，本页面只展示当前登录账号本人的余额，不支持查询他人账户。</p></section>
  <section class="profile-card"><van-cell title="账号" :value="store.user.username"/><van-cell title="角色" :value="store.user.role==='ADMIN'?'管理员':'普通用户'"/><van-cell title="学号" :value="store.user.student_no||'未填写'"/><van-cell title="手机号" :value="store.user.phone||'未填写'"/><van-cell title="邮箱" :value="store.user.email||'未填写'"/><van-cell title="修改资料" is-link value="手机号/邮箱需审核" @click="router.push('/bind-account?redirect=/app/profile')"/></section>
  <section v-if="pending.length" class="profile-card request-card"><div class="request-title">待审核的修改</div><div v-for="item in pending" :key="item.request_id" class="request-row"><span>{{item.field_label}}</span><small>{{item.old_value||'未填写'}} → {{item.new_value}}</small><em>审核中</em></div><p class="request-tip">审核通过前，原手机号/邮箱继续有效。</p></section>
  <section v-else-if="requests.length" class="profile-card request-card"><div class="request-title">最近资料申请</div><div v-for="item in requests.slice(0,3)" :key="item.request_id" class="request-row"><span>{{item.field_label}}</span><small>{{item.new_value}}</small><em :class="item.status">{{statusText[item.status]||item.status}}</em></div><p v-if="requests[0]?.remark" class="request-tip">审核备注：{{requests[0].remark}}</p></section>
  <section class="privacy-card"><h3>隐私与安全</h3><p>系统仅保存完成咨询所需的账号信息、会话内容和反馈。校园卡余额只能查询本人账户；涉及充值、挂失等操作时，本工具只提供办理指引，不直接执行账户操作。</p></section>
  <van-button block round type="danger" plain @click="logout">退出登录</van-button>
</template><van-empty v-else description="请先登录"><van-button type="primary" round @click="router.push('/login')">去登录</van-button></van-empty></div></template>
<style scoped>
.balance-card{margin:-18px 0 14px;padding:18px;border-radius:22px;background:linear-gradient(135deg,#0f756f,#0b4058);color:white;box-shadow:0 18px 36px rgba(12,60,80,.2)}
.balance-head{display:flex;justify-content:space-between;align-items:center;font-size:13px;opacity:.9}.balance-head small{font-size:10px;opacity:.7}
.balance-value{display:block;font-size:38px;line-height:1.2;margin:10px 0 8px;letter-spacing:.5px}
.balance-meta{display:flex;justify-content:space-between;font-size:12px;opacity:.8}
.balance-tip{margin:14px 0 0;font-size:10px;line-height:1.6;opacity:.65}
.request-card{margin-top:12px}.request-title{font-size:14px;font-weight:700;margin-bottom:10px}
.request-row{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid #eef4f6;font-size:12px}
.request-row:last-child{border-bottom:0}.request-row span{font-weight:600;color:#315261}.request-row small{flex:1;color:#7d929e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.request-row em{font-style:normal;font-size:10px;padding:3px 7px;border-radius:999px;background:#fff4e5;color:#a46a16}
.request-row em.APPROVED{background:#e8f6f0;color:#187a5a}.request-row em.REJECTED{background:#fdecea;color:#b23b32}
.request-tip{margin:10px 0 0;font-size:10px;color:#93a4ad;line-height:1.6}
</style>
