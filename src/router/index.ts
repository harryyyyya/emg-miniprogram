import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false },
  },

  // ─── 管理员路由 ─────────────────────────────────────
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, role: 'admin' },
    redirect: '/admin/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '仪表盘', icon: 'Odometer' },
      },
      {
        path: 'devices',
        name: 'Devices',
        component: () => import('@/views/DevicesView.vue'),
        meta: { title: '设备管理', icon: 'Cpu' },
      },
      {
        path: 'health',
        name: 'Health',
        component: () => import('@/views/HealthView.vue'),
        meta: { title: '肌肉健康', icon: 'TrendCharts' },
      },
      {
        path: 'errors',
        name: 'Errors',
        component: () => import('@/views/ErrorsView.vue'),
        meta: { title: '错误分析', icon: 'Warning' },
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('@/views/ReportsView.vue'),
        meta: { title: '报表管控', icon: 'Document' },
      },
      {
        path: 'compute',
        name: 'Compute',
        component: () => import('@/views/ComputeView.vue'),
        meta: { title: '算力管理', icon: 'Monitor' },
      },
      {
        path: 'forum',
        name: 'AdminForum',
        component: () => import('@/views/ForumView.vue'),
        meta: { title: '社区管理', icon: 'ChatDotRound' },
      },
      {
        path: 'knowledge',
        name: 'AdminKnowledge',
        component: () => import('@/views/KnowledgeView.vue'),
        meta: { title: '知识库', icon: 'Reading' },
      },
      {
        path: 'seed',
        name: 'SeedData',
        component: () => import('@/views/admin/SeedDataView.vue'),
        meta: { title: '数据初始化', icon: 'SetUp' },
      },
    ],
  },

  // ─── 普通用户路由 ─────────────────────────────────────
  {
    path: '/user',
    component: () => import('@/layouts/UserLayout.vue'),
    meta: { requiresAuth: true, role: 'user' },
    redirect: '/user/device',
    children: [
      {
        path: 'device',
        name: 'UserDevice',
        component: () => import('@/views/user/UserDeviceView.vue'),
        meta: { title: '设备状态', icon: 'Cpu' },
      },
      {
        path: 'community',
        name: 'UserCommunity',
        component: () => import('@/views/user/UserCommunityView.vue'),
        meta: { title: '社区交流', icon: 'ChatDotRound' },
      },
      {
        path: 'ai',
        name: 'UserAI',
        component: () => import('@/views/user/UserAIView.vue'),
        meta: { title: '智能问答', icon: 'ChatLineSquare' },
      },
      {
        path: 'knowledge',
        name: 'UserKnowledge',
        component: () => import('@/views/user/UserKnowledgeView.vue'),
        meta: { title: '知识库', icon: 'Reading' },
      },
    ],
  },

  // ─── 根路径重定向 ─────────────────────────────────────
  {
    path: '/',
    redirect: () => {
      const authStore = useAuthStore()
      if (!authStore.isLoggedIn) return '/login'
      return authStore.isAdmin ? '/admin/dashboard' : '/user/device'
    },
  },

  // ─── 兼容旧路径 ─────────────────────────────────────
  { path: '/dashboard', redirect: '/admin/dashboard' },
  { path: '/devices', redirect: '/admin/devices' },
  { path: '/health', redirect: '/admin/health' },
  { path: '/errors', redirect: '/admin/errors' },
  { path: '/reports', redirect: '/admin/reports' },
  { path: '/compute', redirect: '/admin/compute' },
  { path: '/forum', redirect: '/admin/forum' },
  { path: '/knowledge', redirect: '/admin/knowledge' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  // 未登录 → 去登录页
  if (to.meta.requiresAuth !== false && !authStore.isLoggedIn) {
    return next('/login')
  }

  // 已登录访问登录页 → 重定向到首页
  if (to.path === '/login' && authStore.isLoggedIn) {
    return next(authStore.isAdmin ? '/admin/dashboard' : '/user/device')
  }

  // 角色检查：admin 不能访问 /user，user 不能访问 /admin
  if (to.meta.role === 'admin' && !authStore.isAdmin) {
    return next('/user/device')
  }
  if (to.meta.role === 'user' && authStore.isAdmin) {
    return next('/admin/dashboard')
  }

  next()
})

export default router
