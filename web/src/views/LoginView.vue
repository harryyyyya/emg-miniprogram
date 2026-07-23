<template>
  <div class="login-wrapper">
    <div class="login-bg">
      <div class="glow glow-1"></div>
      <div class="glow glow-2"></div>
      <div class="glow glow-3"></div>
    </div>

    <div class="login-card glass-card">
      <div class="login-header">
        <div class="login-logo">
          <el-icon :size="40"><Cpu /></el-icon>
        </div>
        <h1 class="gradient-text">NeuroHand</h1>
        <p class="login-subtitle">肌电假手智能管理系统</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item label="账号" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入管理员账号"
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          class="login-btn"
          @click="handleLogin"
        >
          {{ loading ? '登录中...' : '登 录' }}
        </el-button>
      </el-form>

      <div class="login-footer">
        <span>© 2026 NeuroHand · 肌电假手智能管理平台</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, type FormInstance } from 'element-plus'
import { login as apiLogin, type LoginResponse } from '@/api/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    let res: LoginResponse
    try {
      res = await apiLogin(form.username, form.password)
    } catch {
      // 后端未就绪时走本地 Mock：admin/admin → Admin，user/user → User
      const mockMap: Record<string, typeof res> = {
        'admin:admin': { token: 'mock-token-admin', role: 'admin', username: 'admin', name: '管理员', user_id: 1 },
        'user:user':   { token: 'mock-token-user',  role: 'user',  username: 'user',  name: '普通用户', user_id: 2 },
      }
      const key = `${form.username}:${form.password}`
      if (!mockMap[key]) throw new Error('账号或密码错误')
      res = mockMap[key]
    }
    // 将后端返回的 JWT Token 和用户信息存入 Pinia + localStorage
    authStore.setAuth(res.token, {
      id: res.user?.id || res.user_id || 0,
      name: res.user?.name || res.name,
      role: res.user?.role || res.role,
      user_id: res.user_id,
      username: res.username,
      avatar_url: res.user?.avatar_url,
    })
    ElMessage.success('登录成功')
    router.push(res.role === 'admin' ? '/admin/dashboard' : '/user/device')
  } catch {
    // 全局拦截器已弹出 "账号或密码错误" 错误信息
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: #060918;
}

.login-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}
.glow-1 {
  width: 400px;
  height: 400px;
  background: #6366f1;
  top: -10%;
  left: -5%;
  animation: float 8s ease-in-out infinite;
}
.glow-2 {
  width: 300px;
  height: 300px;
  background: #06b6d4;
  bottom: -5%;
  right: -5%;
  animation: float 10s ease-in-out infinite reverse;
}
.glow-3 {
  width: 250px;
  height: 250px;
  background: #8b5cf6;
  top: 40%;
  right: 20%;
  animation: float 12s ease-in-out infinite;
}
@keyframes float {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(30px, -30px); }
}

.login-card {
  width: 420px;
  padding: 40px 36px;
  z-index: 10;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.login-logo {
  color: var(--color-primary-light);
  margin-bottom: 12px;
}
.login-header h1 {
  font-size: 32px;
  font-weight: 800;
  margin-bottom: 8px;
}
.login-subtitle {
  color: var(--color-text-muted);
  font-size: 14px;
}

.login-form :deep(.el-input__wrapper) {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  box-shadow: none !important;
}
.login-form :deep(.el-form-item__label) {
  color: var(--color-text-muted);
}

.login-btn {
  width: 100%;
  height: 44px;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  border: none;
  margin-top: 8px;
  transition: all 0.3s;
}
.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
}

.login-footer {
  text-align: center;
  margin-top: 24px;
  color: var(--color-text-muted);
  font-size: 12px;
}
</style>
