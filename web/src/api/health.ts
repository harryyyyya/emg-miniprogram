import request from '@/utils/request'

export interface HealthLog {
  id: number
  user_id: number
  rms_value: number
  side_pressure: number
  side_presure?: number
  muscle_status_label: string
  muscle_status?: string
  diagnostics?: string
  created_at: string
}

export interface HealthUser {
  id: number
  user_id: number
  name: string
  username: string
  phone: string
  role: string
  avatar_url: string
  device_count: number
  health_log_count: number
  latest_health_at: string
}

export interface ReportResponse {
  msg?: string
  report_url?: string
  diagnostics: string
  rms_value?: number
  side_presure?: number
  muscle_status?: string
}

export function fetchHealthUsers() {
  return request.get<any, HealthUser[]>('/users')
}

export function fetchHealthLogs(userId: number, params?: { range?: '24h' | '7d' }) {
  return request.get<any, HealthLog[]>(`/health/logs/${userId}`, { params })
}

export function generateReport(userId: number) {
  return request.post<any, ReportResponse>('/health/report/generate', null, {
    params: { user_id: userId },
  })
}
