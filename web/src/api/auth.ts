import request from '@/utils/request'

export interface LoginResponse {
  token: string
  role: 'admin' | 'user'
  username: string
  name: string
  user_id: number
  user?: {
    id: number
    user_id?: number
    role: 'admin' | 'user'
    username: string
    name: string
    nickname?: string
    avatar_url?: string
  }
}

export function login(username: string, password: string) {
  return request.post<any, LoginResponse>('/auth/login', { username, password })
}

export interface RegisterPayload {
  username: string
  password: string
  name: string
  amputation_part: string
  illness_duration_months: number
}

export function register(payload: RegisterPayload) {
  return request.post<any, LoginResponse>('/auth/register', payload)
}
