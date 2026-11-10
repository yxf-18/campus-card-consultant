<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { DataAnalysis, Document, FolderOpened, User, Warning, Setting, SwitchButton, EditPen } from '@element-plus/icons-vue'
const route = useRoute()
const router = useRouter()
const store = useAuthStore()
async function logout() { await store.logout(); router.push('/login') }
</script>
<template>
  <div class="admin-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">卡</div><div><strong>智慧校园卡</strong><span>智能咨询管理后台</span></div></div>
      <el-menu :default-active="route.path" router class="side-menu">
        <el-menu-item index="/console/dashboard"><el-icon><DataAnalysis /></el-icon>运营概览</el-menu-item>
        <el-menu-item index="/console/categories"><el-icon><FolderOpened /></el-icon>分类管理</el-menu-item>
        <el-menu-item index="/console/documents"><el-icon><Document /></el-icon>文档管理</el-menu-item>
        <el-menu-item index="/console/users"><el-icon><User /></el-icon>用户管理</el-menu-item>
        <el-menu-item index="/console/profile-requests"><el-icon><EditPen /></el-icon>资料审核</el-menu-item>
        <el-menu-item index="/console/feedbacks"><el-icon><Warning /></el-icon>反馈处理</el-menu-item>
        <el-menu-item index="/console/configs"><el-icon><Setting /></el-icon>系统配置</el-menu-item>
      </el-menu>
    </aside>
    <main class="main-area">
      <header class="topbar"><div><span class="eyebrow">校园一卡通使用智能咨询工具</span><h1>{{ route.meta.title || '管理后台' }}</h1></div>
        <div class="user-box"><span>{{ store.user?.nickname || '管理员' }}</span><el-button text :icon="SwitchButton" @click="logout">退出</el-button></div>
      </header>
      <section class="page-body"><router-view /></section>
    </main>
  </div>
</template>
