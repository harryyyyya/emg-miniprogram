<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">设备资产监控</h2>
      <div class="header-actions">
        <el-input
          v-model="searchText"
          placeholder="搜索设备 ID..."
          prefix-icon="Search"
          clearable
          class="search-input"
        />
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 140px;">
          <el-option label="在线" value="online" />
          <el-option label="离线" value="offline" />
        </el-select>
      </div>
    </div>

    <div class="device-grid" v-loading="loading">
      <div v-for="device in filteredDevices" :key="device.hardware_id" class="glass-card device-card">
        <div class="device-header">
          <div class="device-id">
            <el-icon><Cpu /></el-icon>
            <span>{{ device.hardware_id }}</span>
          </div>
          <span class="pulse-dot" :class="device.is_online ? 'online' : 'offline'"></span>
        </div>
        <div class="device-body">
          <div class="device-metric">
            <span class="metric-label">绑定用户</span>
            <span class="metric-value">{{ device.user_name || `#${device.user_id}` }}</span>
          </div>
          <div class="device-metric">
            <span class="metric-label">固件版本</span>
            <el-tag size="small" type="info">{{ device.firmware_version }}</el-tag>
          </div>
          <div class="device-metric">
            <span class="metric-label">电量</span>
            <div class="battery-bar-wrap">
              <div
                class="battery-bar"
                :style="{ width: device.battery_level + '%', background: batteryColor(device.battery_level) }"
              ></div>
            </div>
            <span class="battery-text" :style="{ color: batteryColor(device.battery_level) }">
              {{ device.battery_level }}%
            </span>
          </div>
        </div>
      </div>

      <div v-if="!loading && filteredDevices.length === 0" style="grid-column: 1/-1;">
        <el-empty description="暂无设备数据" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchDevices } from '@/api/devices'
import type { Device } from '@/api/devices'

const searchText = ref('')
const statusFilter = ref('')
const loading = ref(false)
const devices = ref<Device[]>([])

async function loadDevices() {
  loading.value = true
  try {
    devices.value = await fetchDevices()
  } catch {
    // 全局拦截器已弹出错误
  } finally {
    loading.value = false
  }
}

onMounted(loadDevices)

const filteredDevices = computed(() => {
  return devices.value.filter((d) => {
    const matchSearch = !searchText.value || d.hardware_id.toLowerCase().includes(searchText.value.toLowerCase())
    const matchStatus =
      !statusFilter.value ||
      (statusFilter.value === 'online' ? d.is_online : !d.is_online)
    return matchSearch && matchStatus
  })
})

function batteryColor(level: number) {
  if (level <= 15) return '#ef4444'
  if (level <= 40) return '#f59e0b'
  return '#22c55e'
}
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-title {
  font-size: 28px;
  font-weight: 700;
}
.header-actions {
  display: flex;
  gap: 12px;
}
.search-input {
  width: 260px;
}
.search-input :deep(.el-input__wrapper) {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  box-shadow: none !important;
}

.device-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}
.device-card {
  padding: 20px;
}
.device-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.device-id {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-primary-light);
}
.device-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.device-metric {
  display: flex;
  align-items: center;
  gap: 8px;
}
.metric-label {
  color: var(--color-text-muted);
  font-size: 13px;
  width: 70px;
  flex-shrink: 0;
}
.metric-value {
  font-weight: 500;
}

.battery-bar-wrap {
  flex: 1;
  height: 8px;
  background: rgba(51, 65, 85, 0.6);
  border-radius: 4px;
  overflow: hidden;
}
.battery-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}
.battery-text {
  font-size: 13px;
  font-weight: 600;
  width: 40px;
  text-align: right;
}
</style>
