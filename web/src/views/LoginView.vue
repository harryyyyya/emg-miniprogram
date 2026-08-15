<template>
  <div class="login-wrapper">
    <div class="login-card glass-card">
      <div class="login-header">
        <el-icon class="login-logo" :size="40"><Cpu /></el-icon>
        <h1 class="gradient-text">掌控未来</h1>
        <p>肌电假手智能管理系统</p>
      </div>

      <el-tabs v-model="loginMode" stretch class="login-tabs">
        <el-tab-pane label="管理员登录" name="admin" />
        <el-tab-pane label="用户登录" name="user" />
      </el-tabs>

      <el-form v-if="loginMode === 'admin'" ref="adminFormRef" :model="adminForm" :rules="loginRules" label-position="top" @keyup.enter="handleAdminLogin">
        <el-form-item label="账号" prop="username"><el-input v-model="adminForm.username" prefix-icon="User" placeholder="请输入管理员账号" size="large" /></el-form-item>
        <el-form-item label="密码" prop="password"><el-input v-model="adminForm.password" prefix-icon="Lock" type="password" show-password placeholder="请输入密码" size="large" /></el-form-item>
        <el-button class="submit-btn" type="primary" :loading="loading" @click="handleAdminLogin">登录管理后台</el-button>
      </el-form>

      <template v-else>
        <el-segmented v-model="userMode" :options="userModeOptions" block class="user-mode" />
        <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-position="top" @keyup.enter="handleUserSubmit">
          <el-form-item label="账号" prop="username"><el-input v-model="userForm.username" prefix-icon="User" placeholder="请输入用户账号" size="large" /></el-form-item>
          <el-form-item label="密码" prop="password"><el-input v-model="userForm.password" prefix-icon="Lock" type="password" show-password placeholder="请输入密码" size="large" /></el-form-item>
          <template v-if="userMode === 'register'">
            <el-form-item label="确认密码" prop="confirmPassword"><el-input v-model="userForm.confirmPassword" prefix-icon="Lock" type="password" show-password placeholder="请再次输入密码" size="large" /></el-form-item>
            <el-form-item label="姓名" prop="name"><el-input v-model="userForm.name" placeholder="请输入患者姓名" size="large" /></el-form-item>
            <el-form-item label="截肢部位" prop="amputationPart"><el-input v-model="userForm.amputationPart" placeholder="请输入截肢部位" size="large" /></el-form-item>
            <el-form-item label="病程（月）"><el-input-number v-model="userForm.illnessDurationMonths" :min="0" :max="1200" controls-position="right" /></el-form-item>
          </template>
          <el-button class="submit-btn" type="primary" :loading="loading" @click="handleUserSubmit">{{ userMode === 'login' ? '登录用户端' : '注册并登录' }}</el-button>
        </el-form>
      </template>

      <div class="login-footer">© 2026 掌控未来</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { login, register, type LoginResponse } from '@/api/auth'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const loginMode = ref<'admin' | 'user'>('admin')
const userMode = ref<'login' | 'register'>('login')
const userModeOptions = [{ label: '账号登录', value: 'login' }, { label: '注册账号', value: 'register' }]
const adminFormRef = ref<FormInstance>()
const userFormRef = ref<FormInstance>()
const adminForm = reactive({ username: '', password: '' })
const userForm = reactive({ username: '', password: '', confirmPassword: '', name: '', amputationPart: '', illnessDurationMonths: 0 })
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const userRules: FormRules = {
  username: [{ required: true, min: 3, message: '账号至少需要 3 个字符', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少需要 6 个字符', trigger: 'blur' }],
  confirmPassword: [{ validator: (_rule, value, callback) => userMode.value !== 'register' || value === userForm.password ? callback() : callback(new Error('两次输入的密码不一致')), trigger: 'blur' }],
  name: [{ validator: (_rule, value, callback) => userMode.value !== 'register' || value?.trim() ? callback() : callback(new Error('请输入姓名')), trigger: 'blur' }],
  amputationPart: [{ validator: (_rule, value, callback) => userMode.value !== 'register' || value?.trim() ? callback() : callback(new Error('请输入截肢部位')), trigger: 'blur' }],
}

function finishLogin(res: LoginResponse) {
  const user: any = res.user || res
  authStore.setAuth(res.token, { id: user.id || res.user_id, name: user.name || res.name, role: user.role || res.role, user_id: res.user_id, username: user.username || res.username, avatar_url: user.avatar_url })
  ElMessage.success('登录成功')
  router.push((user.role || res.role) === 'admin' ? '/admin/dashboard' : '/user/device')
}
async function handleAdminLogin() {
  if (!await adminFormRef.value?.validate().catch(() => false)) return
  loading.value = true
  try { const res = await login(adminForm.username, adminForm.password); if ((res.user?.role || res.role) !== 'admin') throw new Error('该账号不是管理员账号'); finishLogin(res) }
  catch (error: any) { if (!error?.response) ElMessage.error(error.message) }
  finally { loading.value = false }
}
async function handleUserSubmit() {
  if (!await userFormRef.value?.validate().catch(() => false)) return
  loading.value = true
  try {
    const res = userMode.value === 'login'
      ? await login(userForm.username, userForm.password)
      : await register({ username: userForm.username, password: userForm.password, name: userForm.name.trim(), amputation_part: userForm.amputationPart.trim(), illness_duration_months: userForm.illnessDurationMonths })
    if ((res.user?.role || res.role) === 'admin') throw new Error('管理员账号请使用管理员登录')
    finishLogin(res)
  } catch (error: any) { if (!error?.response) ElMessage.error(error.message) }
  finally { loading.value = false }
}
</script>

<style scoped>
.login-wrapper{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#060918;padding:24px}.login-card{width:420px;padding:36px}.login-header{text-align:center;margin-bottom:20px}.login-logo{color:var(--color-primary-light)}.login-header h1{font-size:32px;margin:8px 0}.login-header p,.login-footer{color:var(--color-text-muted);font-size:14px}.login-tabs,.user-mode{margin-bottom:20px}.submit-btn{width:100%;height:44px;margin-top:8px}.login-footer{text-align:center;margin-top:24px;font-size:12px}:deep(.el-input-number){width:100%}@media(max-width:480px){.login-card{width:100%;padding:28px 20px}}
</style>
