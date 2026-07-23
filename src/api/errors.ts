import request from '@/utils/request'

export interface ErrorLog {
  id: number
  hardware_id: string
  error_code: string
  error_msg: string
  created_at: string
}

export interface ErrorLogPage {
  total: number
  items: ErrorLog[]
}

export interface ErrorCluster {
  name: string
  pct: number
  color?: string
}

export interface AnalyzeResult {
  clusters: ErrorCluster[]
  report: string
}

// 分页查询错误日志 (GET，与小程序上传的 POST /logs/error 是同路由不同方法)
export function fetchErrorLogs(params: {
  page: number
  pageSize: number
  startDate?: string
  endDate?: string
}) {
  return request.get<any, ErrorLogPage>('/logs/error', { params })
}

// AI Agent 聚类分析 (耗时 20-60s，单独设 120s 超时)
export function analyzeErrors(params?: { startDate?: string; endDate?: string }) {
  return request.post<any, AnalyzeResult>('/logs/error/analyze', params, {
    timeout: 120000,
  })
}
