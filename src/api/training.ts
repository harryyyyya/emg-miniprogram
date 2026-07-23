import request from '@/utils/request'

export async function fetchTrainingSessions() {
  try {
    return await request.get('/training/sessions')
  } catch (error) {
    console.error('[Training] fetchSessions failed:', error)
    throw error
  }
}
