<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: isCollapsed }">
      <div class="sidebar-header">
        <div class="logo-area">
          <div class="logo-icon">
            <el-icon :size="28"><Cpu /></el-icon>
          </div>
          <transition name="fade-slide">
            <span v-if="!isCollapsed" class="logo-text gradient-text">NeuroHand</span>
          </transition>
        </div>
      </div>

      <el-menu
        :default-active="$route.path"
        :collapse="isCollapsed"
        background-color="transparent"
        text-color="#94a3b8"
        active-text-color="#818cf8"
        router
        class="sidebar-menu"
      >
        <template v-for="item in menuItems" :key="item.path">
          <el-menu-item :index="'/user/' + item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>

      <div class="sidebar-footer">
        <el-button text @click="isCollapsed = !isCollapsed" class="collapse-btn">
          <el-icon :size="18">
            <component :is="isCollapsed ? 'Expand' : 'Fold'" />
          </el-icon>
        </el-button>
      </div>
    </aside>

    <!-- 主体区域 -->
    <div class="main-area" :class="{ expanded: isCollapsed }">
      <!-- 顶部栏 -->
      <header class="top-header glass-card" style="border-radius: 0; padding: 0 24px;">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentRoute?.meta?.title || '' }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click" @command="handleCommand">
            <div class="user-avatar-area">
              <el-avatar :size="32" class="avatar-glow">
                {{ authStore.user?.name?.[0] || 'U' }}
              </el-avatar>
              <span class="user-name">{{ authStore.user?.name || '用户' }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- 内容区域 -->
      <main class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isCollapsed = ref(false)

const currentRoute = computed(() => route)

const menuItems = [
  { path: 'device', title: '设备状态', icon: 'Cpu' },
  { path: 'community', title: '社区交流', icon: 'ChatDotRound' },
  { path: 'ai', title: '智能问答', icon: 'ChatLineSquare' },
  { path: 'knowledge', title: '知识库', icon: 'Reading' },
]

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.admin-layout {
  display: flex;
  min-height: 100vh;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: var(--sidebar-width);
  background: linear-gradient(180deg, #0f172a 0%, #1a1040 100%);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
  border-right: 1px solid rgba(99, 102, 241, 0.1);
}
.sidebar.collapsed {
  width: 64px;
}

.sidebar-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
}
.logo-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-icon {
  color: var(--color-primary-light);
}
.logo-text {
  font-size: 20px;
  font-weight: 700;
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
}
.sidebar-menu .el-menu-item {
  border-radius: 10px;
  margin-bottom: 4px;
  height: 44px;
  line-height: 44px;
}
.sidebar-menu .el-menu-item.is-active {
  background: rgba(99, 102, 241, 0.15) !important;
  color: var(--color-primary-light) !important;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid rgba(99, 102, 241, 0.1);
}
.collapse-btn {
  color: var(--color-text-muted) !important;
  width: 100%;
}

/* ===== 主体 ===== */
.main-area {
  margin-left: var(--sidebar-width);
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.main-area.expanded {
  margin-left: 64px;
}

.top-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(15, 23, 42, 0.85) !important;
  backdrop-filter: blur(12px);
}
.header-left {
  display: flex;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.user-avatar-area {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.avatar-glow {
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  font-weight: 600;
}
.user-name {
  color: var(--color-text);
  font-size: 14px;
}

.content-area {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>
