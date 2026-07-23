<template>
  <div>
    <h2 class="page-title gradient-text">设备状态查询</h2>

    <!-- 设备概览卡片 -->
    <div class="device-overview glass-card" v-if="device">
      <div class="device-hero">
        <div class="device-visual">
          <div class="device-ring" :class="device.is_online ? 'online' : 'offline'">
            <el-icon :size="48"><Cpu /></el-icon>
          </div>
          <span class="device-status-badge" :class="device.is_online ? 'online' : 'offline'">
            {{ device.is_online ? '在线' : '离线' }}
          </span>
        </div>
        <div class="device-meta">
          <h3 class="device-hw-id">{{ device.hardware_id }}</h3>
          <div class="device-detail-row">
            <span class="detail-label">绑定用户</span>
            <span class="detail-val">{{ device.user_name || '未知' }}</span>
          </div>
          <div class="device-detail-row">
            <span class="detail-label">固件版本</span>
            <el-tag size="small" type="info">{{ device.firmware_version }}</el-tag>
          </div>
          <div class="device-detail-row">
            <span class="detail-label">电量</span>
            <div class="battery-inline">
              <div class="battery-bar-wrap">
                <div class="battery-bar" :style="{ width: device.battery_level + '%', background: batteryColor(device.battery_level) }"></div>
              </div>
              <span :style="{ color: batteryColor(device.battery_level) }">{{ device.battery_level }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="!loadingDevice" class="glass-card empty-device">
      <el-empty description="暂未绑定设备" />
    </div>

    <!-- Tab 区域 -->
    <el-tabs v-model="activeTab" class="device-tabs">
      <!-- Tab 1: 使用情况 -->
      <el-tab-pane label="使用情况" name="usage">
        <div class="tab-content">
          <div class="stat-mini-grid">
            <div class="glass-card stat-mini">
              <span class="stat-mini-val">{{ sessions.length }}</span>
              <span class="stat-mini-label">总训练次数</span>
            </div>
            <div class="glass-card stat-mini">
              <span class="stat-mini-val">{{ completedCount }}</span>
              <span class="stat-mini-label">已完成</span>
            </div>
            <div class="glass-card stat-mini">
              <span class="stat-mini-val">{{ latestSession }}</span>
              <span class="stat-mini-label">最近训练</span>
            </div>
          </div>

          <div class="glass-card" style="margin-top: 16px">
            <h4 style="margin-bottom: 12px">训练会话记录</h4>
            <el-table :data="sessions" style="width: 100%" :header-cell-style="tableHeaderStyle" v-loading="loadingSessions">
              <el-table-column prop="session_id" label="会话 ID" width="220" />
              <el-table-column prop="status" label="状态" width="120">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'training' ? 'warning' : 'info'" size="small">
                    {{ row.status === 'completed' ? '已完成' : row.status === 'training' ? '训练中' : row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="180">
                <template #default="{ row }">
                  {{ row.created_at?.slice(0, 16).replace('T', ' ') || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="raw_data_path" label="数据路径">
                <template #default="{ row }">
                  <span class="path-text">{{ row.raw_data_path || '无' }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 动作查询 -->
      <el-tab-pane label="动作查询" name="actions">
        <div class="tab-content">
          <div class="filter-bar">
            <el-date-picker v-model="actionDateRange" type="daterange" start-placeholder="开始日期" end-placeholder="结束日期" style="width: 300px" />
          </div>
          <div class="action-grid">
            <div v-for="s in filteredActions" :key="s.session_id" class="glass-card action-card">
              <div class="action-header">
                <el-icon :size="20" class="action-icon"><VideoCamera /></el-icon>
                <span class="action-id">{{ s.session_id.slice(0, 12) }}...</span>
              </div>
              <div class="action-body">
                <div class="action-row">
                  <span>状态</span>
                  <el-tag :type="s.status === 'completed' ? 'success' : 'info'" size="small">{{ s.status === 'completed' ? '已完成' : s.status }}</el-tag>
                </div>
                <div class="action-row">
                  <span>时间</span>
                  <span class="action-time">{{ s.created_at?.slice(0, 16).replace('T', ' ') || '-' }}</span>
                </div>
              </div>
            </div>
            <el-empty v-if="filteredActions.length === 0" description="暂无动作记录" style="grid-column: 1/-1" />
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 电极位置 -->
      <el-tab-pane label="电极位置" name="electrodes">
        <div class="tab-content">
          <div class="electrode-layout">
            <!-- 前臂示意图 -->
            <div class="glass-card electrode-map">
              <h4>8 通道电极分布</h4>
              <div class="forearm-diagram">
                <svg viewBox="0 0 300 400" class="forearm-svg">
                  <!-- 前臂轮廓 -->
                  <ellipse cx="150" cy="200" rx="100" ry="180" fill="rgba(99,102,241,0.08)" stroke="rgba(99,102,241,0.3)" stroke-width="2" />
                  <text x="150" y="380" text-anchor="middle" fill="#64748b" font-size="12">前臂横截面</text>
                  <!-- 8个电极点 -->
                  <g v-for="(e, i) in electrodes" :key="i">
                    <circle
                      :cx="e.x" :cy="e.y" r="16"
                      :fill="e.color" :stroke="selectedElectrode === i ? '#fff' : 'transparent'" stroke-width="3"
                      class="electrode-dot" @click="selectedElectrode = i" style="cursor: pointer"
                    />
                    <text :x="e.x" :y="e.y + 5" text-anchor="middle" fill="#fff" font-size="11" font-weight="600" style="pointer-events: none">
                      {{ i + 1 }}
                    </text>
                  </g>
                </svg>
              </div>
            </div>

            <!-- 电极详情 -->
            <div class="glass-card electrode-detail">
              <h4>通道 {{ selectedElectrode + 1 }} 详情</h4>
              <el-form label-position="top">
                <el-form-item label="通道名称">
                  <el-input v-model="electrodes[selectedElectrode].label" @change="saveElectrodes" />
                </el-form-item>
                <el-form-item label="肌肉映射">
                  <el-input v-model="electrodes[selectedElectrode].muscle" @change="saveElectrodes" />
                </el-form-item>
                <el-form-item label="备注">
                  <el-input v-model="electrodes[selectedElectrode].note" type="textarea" :rows="3" @change="saveElectrodes" />
                </el-form-item>
              </el-form>
              <div class="electrode-colors">
                <span v-for="(e, i) in electrodes" :key="i"
                  class="color-swatch" :class="{ active: selectedElectrode === i }"
                  :style="{ background: e.color }" @click="selectedElectrode = i"
                >{{ i + 1 }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 肌肉萎缩状态 -->
      <el-tab-pane label="肌肉萎缩状态" name="muscle">
        <div class="tab-content">
          <div class="risk-row">
            <div class="glass-card risk-card">
              <div class="risk-indicator" :class="riskLevel">
                <el-icon :size="28"><Warning /></el-icon>
              </div>
              <div>
                <span class="risk-title">萎缩风险等级</span>
                <span class="risk-value">{{ riskText }}</span>
              </div>
            </div>
            <div class="glass-card risk-card">
              <div class="risk-indicator info">
                <el-icon :size="28"><TrendCharts /></el-icon>
              </div>
              <div>
                <span class="risk-title">RMS 均值</span>
                <span class="risk-value">{{ rmsAvg.toFixed(1) }}</span>
              </div>
            </div>
            <div class="glass-card risk-card">
              <div class="risk-indicator info">
                <el-icon :size="28"><Histogram /></el-icon>
              </div>
              <div>
                <span class="risk-title">压力均值</span>
                <span class="risk-value">{{ pressureAvg.toFixed(1) }}</span>
              </div>
            </div>
          </div>

          <div class="glass-card" style="margin-top: 16px">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px">
              <h4>RMS 肌电强度 & 侧压力趋势</h4>
              <el-radio-group v-model="muscleRange" size="small" @change="loadHealthLogs">
                <el-radio-button value="24h">24小时</el-radio-button>
                <el-radio-button value="7d">近7天</el-radio-button>
              </el-radio-group>
            </div>
            <div ref="muscleChartRef" class="chart-container"></div>
          </div>

          <div style="margin-top: 16px; text-align: right">
            <el-button type="primary" :loading="generatingReport" @click="generateReport">
              <el-icon><Document /></el-icon> 生成健康报告
            </el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, reactive, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { fetchDevices } from '@/api/devices'
import { fetchTrainingSessions } from '@/api/training'
import { fetchHealthLogs } from '@/api/health'
import type { Device } from '@/api/devices'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { graphic } from 'echarts/core'
import request from '@/utils/request'

echarts.use([LineChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const authStore = useAuthStore()
const userId = computed(() => authStore.user?.id ?? 1)

// ── 设备概览 ──
const device = ref<Device | null>(null)
const loadingDevice = ref(true)

async function loadDevice() {
  loadingDevice.value = true
  try {
    const devices = await fetchDevices()
    device.value = devices.find((d: any) => d.user_id === userId.value) || devices[0] || null
  } catch {
    // mock
    device.value = {
      hardware_id: 'ESP32-A7F3', user_id: 1, user_name: '患者张三',
      battery_level: 78, firmware_version: 'v2.1.0', is_online: true, id: 1,
    } as any
  } finally {
    loadingDevice.value = false
  }
}

function batteryColor(level: number) {
  if (level <= 15) return '#ef4444'
  if (level <= 40) return '#f59e0b'
  return '#22c55e'
}

// ── 训练会话 ──
const sessions = ref<any[]>([])
const loadingSessions = ref(false)
const activeTab = ref('usage')

async function loadSessions() {
  loadingSessions.value = true
  try {
    const all = await fetchTrainingSessions()
    sessions.value = (all as any[]).filter((s: any) => !userId.value || s.user_id === userId.value || s.user_id === null)
  } catch {
    sessions.value = [
      { session_id: 'sess_20260325_001', user_id: 1, status: 'completed', created_at: '2026-03-25T14:30:00', raw_data_path: '/uploads/sess_20260325_001.dat' },
      { session_id: 'sess_20260326_002', user_id: 1, status: 'completed', created_at: '2026-03-26T10:15:00', raw_data_path: '/uploads/sess_20260326_002.dat' },
      { session_id: 'sess_20260327_003', user_id: 1, status: 'training', created_at: '2026-03-27T09:00:00', raw_data_path: null },
    ]
  } finally {
    loadingSessions.value = false
  }
}

const completedCount = computed(() => sessions.value.filter(s => s.status === 'completed').length)
const latestSession = computed(() => {
  if (sessions.value.length === 0) return '-'
  const latest = sessions.value[0]
  return latest.created_at?.slice(0, 10) || '-'
})

const tableHeaderStyle = {
  background: 'rgba(30, 41, 59, 0.8)',
  color: '#94a3b8',
  borderBottom: '1px solid rgba(99,102,241,0.1)',
}

// ── 动作查询 ──
const actionDateRange = ref<[Date, Date] | null>(null)
const filteredActions = computed(() => {
  let list = sessions.value.filter(s => s.status === 'completed')
  if (actionDateRange.value) {
    const [start, end] = actionDateRange.value
    list = list.filter(s => {
      const d = new Date(s.created_at)
      return d >= start && d <= end
    })
  }
  return list
})

// ── 电极位置 ──
const selectedElectrode = ref(0)
const defaultElectrodes = [
  { x: 150, y: 50, color: '#ef4444', label: 'CH1', muscle: '桡侧腕屈肌', note: '' },
  { x: 220, y: 90, color: '#f59e0b', label: 'CH2', muscle: '指伸肌', note: '' },
  { x: 245, y: 170, color: '#22c55e', label: 'CH3', muscle: '尺侧腕伸肌', note: '' },
  { x: 230, y: 260, color: '#06b6d4', label: 'CH4', muscle: '尺侧腕屈肌', note: '' },
  { x: 150, y: 330, color: '#6366f1', label: 'CH5', muscle: '掌长肌', note: '' },
  { x: 70, y: 260, color: '#a78bfa', label: 'CH6', muscle: '旋前圆肌', note: '' },
  { x: 55, y: 170, color: '#f472b6', label: 'CH7', muscle: '肱桡肌', note: '' },
  { x: 80, y: 90, color: '#fb923c', label: 'CH8', muscle: '桡侧腕伸肌', note: '' },
]

function loadElectrodes() {
  const saved = localStorage.getItem('neurohand_electrodes')
  if (saved) {
    try { return JSON.parse(saved) } catch { /* ignore */ }
  }
  return defaultElectrodes.map(e => ({ ...e }))
}
const electrodes = reactive(loadElectrodes())
function saveElectrodes() {
  localStorage.setItem('neurohand_electrodes', JSON.stringify(electrodes))
}

// ── 肌肉萎缩状态 ──
const muscleRange = ref('7d')
const healthLogs = ref<any[]>([])
const muscleChartRef = ref<HTMLElement>()
let muscleChart: echarts.ECharts | null = null
const generatingReport = ref(false)

const rmsAvg = computed(() => {
  if (healthLogs.value.length === 0) return 0
  return healthLogs.value.reduce((s, l) => s + l.rms_value, 0) / healthLogs.value.length
})
const pressureAvg = computed(() => {
  if (healthLogs.value.length === 0) return 0
  return healthLogs.value.reduce((s, l) => s + l.side_pressure, 0) / healthLogs.value.length
})
const riskLevel = computed(() => {
  if (rmsAvg.value > 150) return 'low'
  if (rmsAvg.value > 80) return 'medium'
  return 'high'
})
const riskText = computed(() => {
  if (riskLevel.value === 'low') return '低风险'
  if (riskLevel.value === 'medium') return '中等风险'
  return '高风险'
})

async function loadHealthLogs() {
  try {
    healthLogs.value = await fetchHealthLogs(userId.value, { range: muscleRange.value as '24h' | '7d' }) as any[]
  } catch {
    // mock
    const now = Date.now()
    healthLogs.value = Array.from({ length: 20 }, (_, i) => ({
      id: i + 1, user_id: 1,
      rms_value: 100 + Math.random() * 80,
      side_pressure: 30 + Math.random() * 40,
      muscle_status_label: '正常',
      created_at: new Date(now - (20 - i) * 3600000).toISOString(),
    }))
  }
  await nextTick()
  renderMuscleChart()
}

function renderMuscleChart() {
  if (!muscleChartRef.value) return
  if (!muscleChart) muscleChart = echarts.init(muscleChartRef.value)
  const times = healthLogs.value.map(l => l.created_at?.slice(5, 16).replace('T', ' ') || '')
  muscleChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['RMS 肌电强度', '侧压力'], textStyle: { color: '#94a3b8' } },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: times, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8', fontSize: 10 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(99,102,241,0.08)' } }, axisLabel: { color: '#94a3b8' } },
    series: [
      {
        name: 'RMS 肌电强度', type: 'line', smooth: true,
        data: healthLogs.value.map(l => l.rms_value?.toFixed(1)),
        lineStyle: { color: '#6366f1', width: 2 },
        areaStyle: { color: new graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(99,102,241,0.25)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }]) },
        itemStyle: { color: '#818cf8' },
      },
      {
        name: '侧压力', type: 'line', smooth: true,
        data: healthLogs.value.map(l => l.side_pressure?.toFixed(1)),
        lineStyle: { color: '#06b6d4', width: 2 },
        areaStyle: { color: new graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(6,182,212,0.2)' }, { offset: 1, color: 'rgba(6,182,212,0.02)' }]) },
        itemStyle: { color: '#22d3ee' },
      },
    ],
  })
}

async function generateReport() {
  generatingReport.value = true
  try {
    const res = await request.post('/health/report/generate', null, { params: { user_id: userId.value } })
    ElMessage.success('报告已生成')
    if ((res as any).report_url) {
      window.open((res as any).report_url, '_blank')
    }
  } catch {
    ElMessage.warning('报告生成失败（后端可能未就绪）')
  } finally {
    generatingReport.value = false
  }
}

function handleResize() {
  muscleChart?.resize()
}

onMounted(() => {
  loadDevice()
  loadSessions()
  loadHealthLogs()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  muscleChart?.dispose()
})
</script>

<style scoped>
.page-title { font-size: 28px; font-weight: 700; margin-bottom: 24px; }

/* 设备概览 */
.device-overview { margin-bottom: 24px; }
.device-hero { display: flex; align-items: center; gap: 32px; padding: 8px; }
.device-visual { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.device-ring {
  width: 100px; height: 100px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: rgba(99,102,241,0.1); border: 3px solid rgba(99,102,241,0.3);
  transition: all 0.3s;
}
.device-ring.online { border-color: #22c55e; background: rgba(34,197,94,0.1); color: #22c55e; }
.device-ring.offline { border-color: #64748b; background: rgba(100,116,139,0.1); color: #64748b; }
.device-status-badge {
  font-size: 12px; font-weight: 600; padding: 2px 12px; border-radius: 99px;
}
.device-status-badge.online { background: rgba(34,197,94,0.15); color: #22c55e; }
.device-status-badge.offline { background: rgba(100,116,139,0.15); color: #64748b; }
.device-meta { flex: 1; }
.device-hw-id { font-size: 22px; font-weight: 700; margin-bottom: 12px; color: var(--color-primary-light); }
.device-detail-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.detail-label { font-size: 13px; color: var(--color-text-muted); width: 70px; }
.detail-val { font-weight: 500; }
.battery-inline { display: flex; align-items: center; gap: 8px; flex: 1; }
.battery-bar-wrap { flex: 1; height: 8px; background: rgba(51,65,85,0.6); border-radius: 4px; overflow: hidden; max-width: 200px; }
.battery-bar { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
.empty-device { margin-bottom: 24px; }

/* Tabs */
.device-tabs :deep(.el-tabs__item) { color: #94a3b8; }
.device-tabs :deep(.el-tabs__item.is-active) { color: var(--color-primary-light); }
.device-tabs :deep(.el-tabs__active-bar) { background: var(--color-primary); }
.device-tabs :deep(.el-tabs__nav-wrap::after) { background: rgba(99,102,241,0.1); }
.tab-content { padding-top: 8px; }

/* 统计迷你卡片 */
.stat-mini-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stat-mini { text-align: center; padding: 20px; }
.stat-mini-val { display: block; font-size: 28px; font-weight: 700; color: var(--color-primary-light); }
.stat-mini-label { font-size: 13px; color: var(--color-text-muted); }

.path-text { font-size: 12px; color: var(--color-text-muted); word-break: break-all; }

:deep(.el-table) {
  --el-table-bg-color: transparent; --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent; --el-table-text-color: #cbd5e1;
  --el-table-border-color: rgba(99,102,241,0.08); --el-table-row-hover-bg-color: rgba(99,102,241,0.06);
}

/* 动作查询 */
.filter-bar { margin-bottom: 16px; }
.action-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.action-card { padding: 16px; }
.action-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.action-icon { color: var(--color-primary-light); }
.action-id { font-weight: 600; font-size: 14px; }
.action-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: var(--color-text-muted); margin-bottom: 6px; }
.action-time { font-size: 12px; }

/* 电极位置 */
.electrode-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.electrode-map { padding: 20px; }
.electrode-map h4 { margin-bottom: 12px; }
.forearm-diagram { display: flex; justify-content: center; }
.forearm-svg { width: 100%; max-width: 300px; height: auto; }
.electrode-dot { transition: all 0.2s; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.3)); }
.electrode-dot:hover { r: 20; }
.electrode-detail { padding: 20px; }
.electrode-detail h4 { margin-bottom: 16px; }
.electrode-colors { display: flex; gap: 8px; margin-top: 16px; }
.color-swatch {
  width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; border: 2px solid transparent; transition: all 0.2s;
}
.color-swatch.active { border-color: #fff; transform: scale(1.15); }

/* 肌肉萎缩 */
.risk-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.risk-card { display: flex; align-items: center; gap: 16px; padding: 20px; }
.risk-indicator { width: 56px; height: 56px; border-radius: 14px; display: flex; align-items: center; justify-content: center; }
.risk-indicator.low { background: rgba(34,197,94,0.15); color: #22c55e; }
.risk-indicator.medium { background: rgba(245,158,11,0.15); color: #f59e0b; }
.risk-indicator.high { background: rgba(239,68,68,0.15); color: #ef4444; }
.risk-indicator.info { background: rgba(99,102,241,0.15); color: #818cf8; }
.risk-title { display: block; font-size: 13px; color: var(--color-text-muted); }
.risk-value { display: block; font-size: 22px; font-weight: 700; }
.chart-container { width: 100%; height: 280px; }
</style>
