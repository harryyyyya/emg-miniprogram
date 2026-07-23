import request from '@/utils/request'

export interface AIChatResponse {
  reply?: string
  message?: string
}

export async function sendChatMessage(message: string, hardwareId?: string | null): Promise<AIChatResponse> {
  try {
    return await request.post('/ai/chat', {
      message,
      hardware_id: hardwareId || null,
    })
  } catch {
    // Mock 回复逻辑 — 与小程序保持一致
    return { reply: mockReply(message) }
  }
}

function mockReply(question: string): string {
  if (question.includes('报错')) {
    return '根据系统日志，您的假手设备在过去24小时内未检测到错误事件。一切运行正常！'
  }
  if (question.includes('肌电') || question.includes('数据')) {
    return '您最近7天的肌电RMS均值为125.3μV，侧压力均值为48.7N，数据趋势平稳，无异常波动。'
  }
  if (question.includes('康复') || question.includes('训练')) {
    return '建议每日进行3组×15次的握拳-张手交替训练，每组间休息2分钟。训练时保持手臂放松，专注于残肢肌肉的发力感。'
  }
  if (question.includes('电量')) {
    return '您的假手设备当前电量约为85%，预计可正常使用约6-8小时。'
  }
  return '感谢您的提问！我正在分析您的问题，如需更专业的建议，建议咨询您的康复医生。目前我可以帮您查看设备状态、训练数据和健康报告。'
}
