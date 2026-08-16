import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器 —— 注入 Token
request.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器 —— 全局错误处理
request.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    let detail = error.response?.data?.detail
    if (!detail && error.response?.data instanceof Blob) {
      try {
        const payload = JSON.parse(await error.response.data.text())
        detail = payload?.detail
      } catch {
        // Non-JSON download errors fall back to the HTTP error message.
      }
    }
    const msg = detail || error.message || '网络异常'
    ElMessage.error(msg)
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default request
