import request from '@/utils/request'

export interface TrainingSession {
  session_id: string
  user_id: number
  user_name?: string
  raw_data_path: string
  status: 'collecting' | 'training' | 'completed' | 'queued'
  created_at: string
}

// 获取训练会话列表
export function fetchTrainingSessions() {
  return request.get<any, TrainingSession[]>('/training/sessions')
}
