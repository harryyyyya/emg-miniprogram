import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'user'

export interface AuthUser {
  id: number
  name: string
  role: UserRole
  user_id?: number
  username?: string
  nickname?: string
  avatar_url?: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const user = ref<AuthUser | null>(null)

  const rawUser = localStorage.getItem('auth_user')
  if (rawUser && !user.value) {
    try {
      user.value = JSON.parse(rawUser) as AuthUser
    } catch {
      localStorage.removeItem('auth_user')
    }
  }

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function setAuth(t: string, u: AuthUser) {
    token.value = t
    user.value = u
    localStorage.setItem('token', t)
    localStorage.setItem('auth_user', JSON.stringify(u))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('auth_user')
  }

  return { token, user, isLoggedIn, isAdmin, setAuth, logout }
})
