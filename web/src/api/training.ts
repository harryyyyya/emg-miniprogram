import request from '@/utils/request'

export interface TrainingSession {
  session_id: string
  user_id: number
  user_name?: string
  user_username?: string
  raw_data_path: string
  status: 'collecting' | 'training' | 'completed' | 'queued'
  created_at: string
  updated_at?: string
  hardware_id?: string
  gesture_name?: string
  total_samples?: number
  batch_count?: number
  rms_value?: number
}

export async function downloadTrainingSession(sessionId: string) {
  return await request.get(`/admin/training/sessions/${encodeURIComponent(sessionId)}/download`, {
    responseType: 'blob',
  }) as unknown as Blob
}

export async function fetchTrainingSessions() {
  try {
    return await request.get<any, TrainingSession[]>('/training/sessions')
  } catch (error) {
    console.error('[Training] fetchSessions failed:', error)
    throw error
  }
}
