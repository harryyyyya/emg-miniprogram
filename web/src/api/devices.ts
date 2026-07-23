import request from '@/utils/request'

export interface Device {
  id: number
  user_id: number
  user_name?: string
  hardware_id: string
  battery_level: number
  firmware_version: string
  is_online?: boolean
}

export function fetchDevices() {
  return request.get<any, Device[]>('/devices')
}
