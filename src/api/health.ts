import request from '@/utils/request'

export interface HealthLog {
  id: number
  user_id: number
  rms_value: number
  side_pressure: number
  muscle_status_label: string
  created_at: string
}

export interface ReportResponse {
  msg: string
  report_url: string
  diagnostics: string
}

// 获取用户 HealthLog 历史，用于 ECharts 绘图
export function fetchHealthLogs(userId: number, params?: { range?: '24h' | '7d' }) {
  return request.get<any, HealthLog[]>(`/health/logs/${userId}`, { params })
}

// 触发报告生成 (LLM 分析 + PDF)
// ⚠️ user_id 是 Query 参数，不是 Body
// ⚠️ LLM 可能耗时 10-30s，request.ts 默认 30s 超时
export function generateReport(userId: number) {
  return request.post<any, ReportResponse>('/health/report/generate', null, {
    params: { user_id: userId },
  })
}
