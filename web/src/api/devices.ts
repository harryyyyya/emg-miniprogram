import request from '@/utils/request'

export interface Device {
  id: number
  user_id: number
  user_name?: string
  hardware_id: string
  device_name?: string
  board_type?: string
  board_label?: string
  transport?: string
  status?: string
  last_seen_at?: string
  battery_level: number
  firmware_version: string
  is_online?: boolean
  last_ip?: string
  rms_value?: number
  prediction_result?: string
}

export function fetchDevices() {
  return request.get<any, Device[]>('/devices')
}
