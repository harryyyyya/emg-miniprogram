import request from '@/utils/request'

export interface TrainingSession {
  session_id: string
  user_id: number
  user_name?: string
  user_username?: string
  raw_data_path: string
  downloadable?: boolean
  status: 'collecting' | 'training' | 'completed' | 'queued' | 'empty'
  created_at: string
  updated_at?: string
  hardware_id?: string
  gesture_name?: string
  total_samples?: number
  batch_count?: number
  rms_value?: number
}

export async function downloadTrainingSession(sessionId: string, format: 'csv' | 'dat' = 'csv') {
  return await request.get(`/admin/training/sessions/${encodeURIComponent(sessionId)}/download?format=${format}`, {
    responseType: 'blob',
  }) as unknown as Blob
}

const STANDARD_CSV_COLUMNS = [
  'SampleIndex', 'PacketIndex', 'PacketTimestamp',
  'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8',
  'AX', 'AY', 'AZ', 'GX', 'GY', 'GZ', 'P', 'R', 'Y',
  'Label', 'Session', 'ActionBlock', 'Repetition', 'Phase',
  'LabelName', 'GestureName', 'UserId', 'UserName', 'HardwareId',
  'Transport', 'SampleRateHz', 'IMUAvailable',
]

const csvCell = (value: unknown) => {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function actionLabelId(gestureName: string) {
  const normalized = gestureName.trim().toLowerCase()
  const aliases: Record<number, string[]> = {
    1: ['张开手掌', '张开', 'open', 'open_hand'],
    2: ['自然抓握', '抓握', 'natural_grip'],
    3: ['用力抓握', '握拳', 'fist', 'strong_grip'],
    4: ['三指捏', '三指', 'three_finger_pinch'],
    5: ['指尖捏', '指尖', 'pinch', 'tip_pinch'],
    6: ['食指伸展', '食指', 'index_extend', 'index_finger'],
    7: ['钩状抓握', '钩状', '钩握', 'hook_grip'],
    8: ['竖拇指', '拇指', 'thumbs_up', 'thumb_up'],
  }
  for (const [label, values] of Object.entries(aliases)) {
    if (values.some((alias) => normalized === alias.toLowerCase() || normalized.includes(alias.toLowerCase()))) {
      return Number(label)
    }
  }
  return 1
}

/** Converts an old 8-channel little-endian DAT response when the server has not been redeployed yet. */
export async function normalizeTrainingDownload(blob: Blob, session: TrainingSession) {
  const head = new TextDecoder('utf-8').decode(new Uint8Array(await blob.slice(0, 96).arrayBuffer())).replace(/^\uFEFF/, '')
  if (head.startsWith('SampleIndex,PacketIndex,PacketTimestamp,')) return blob

  const bytes = new Uint8Array(await blob.arrayBuffer())
  const bytesPerSample = 8 * 2
  if (!bytes.length || bytes.length % bytesPerSample !== 0) {
    throw new Error('服务器返回的文件不是标准 CSV，也不是可解析的 8 通道 DAT')
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const sampleRate = 500
  const gestureName = session.gesture_name || '未命名动作'
  const actionLabel = actionLabelId(gestureName)
  const cycleSamples = sampleRate * 6
  const actionSamples = sampleRate * 3
  const userName = session.user_username || session.user_name || `用户#${session.user_id}`
  const rows = [STANDARD_CSV_COLUMNS.map(csvCell).join(',')]

  for (let index = 0; index < bytes.length / bytesPerSample; index += 1) {
    const packetIndex = Math.floor(index / 10)
    const offset = index % cycleSamples
    const isAction = offset >= actionSamples
    const actionBlock = Math.floor(index / cycleSamples) + 1
    const values = Array.from({ length: 8 }, (_, channel) => view.getInt16((index * 16) + channel * 2, true))
    rows.push([
      index, packetIndex, Math.round(packetIndex * 1000 * 10 / sampleRate),
      ...values, ...Array(9).fill(0), actionLabel, session.session_id,
      actionBlock, actionBlock, isAction ? 'action' : 'rest',
      isAction ? gestureName : '静息', gestureName, session.user_id, userName,
      session.hardware_id || '', 'ble', sampleRate, 0,
    ].map(csvCell).join(','))
  }

  return new Blob([`\uFEFF${rows.join('\r\n')}\r\n`], { type: 'text/csv;charset=utf-8' })
}

export async function deleteTrainingSession(sessionId: string) {
  return await request.delete(`/admin/training/sessions/${encodeURIComponent(sessionId)}`)
}

export async function fetchTrainingSessions() {
  try {
    return await request.get<any, TrainingSession[]>('/training/sessions')
  } catch (error) {
    console.error('[Training] fetchSessions failed:', error)
    throw error
  }
}
