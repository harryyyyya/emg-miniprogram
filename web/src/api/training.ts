import request from '@/utils/request'

export interface TrainingSession {
  session_id: string
  user_id: number
  user_name?: string
  raw_data_path: string
  status: 'collecting' | 'training' | 'completed' | 'queued'
  created_at: string
}

export async function fetchTrainingSessions() {
  try {
    return await request.get<any, TrainingSession[]>('/training/sessions')
  } catch (error) {
    console.error('[Training] fetchSessions failed:', error)
    throw error
  }
}
