<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title gradient-text">肌肉健康可视化</h2>
        <p class="page-subtitle">用户列表来自后端数据库，会和小程序登录用户、健康报告数据保持同步。</p>
      </div>
      <div class="header-actions">
        <el-select
          v-model="selectedUser"
          placeholder="选择小程序用户"
          style="width: 240px"
          :loading="loadingUsers"
          filterable
          @change="loadData"
        >
          <el-option
            v-for="u in users"
            :key="u.id"
            :label="userLabel(u)"
            :value="u.id"
          />
        </el-select>
        <el-radio-group v-model="timeRange" size="default">
          <el-radio-button value="24h">24小时</el-radio-button>
          <el-radio-button value="7d">近7天</el-radio-button>
          <el-radio-button value="30d">近30天</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <div class="risk-row">
      <div class="glass-card risk-card">
        <div class="risk-indicator" :class="riskLevel">
          <el-icon :size="28"><Warning /></el-icon>
        </div>
        <div>
          <span class="risk-title">肌肉萎缩风险等级</span>
          <span class="risk-value">{{ riskText }}</span>
        </div>
      </div>
      <div class="glass-card risk-card">
        <div class="risk-indicator info">
          <el-icon :size="28"><TrendCharts /></el-icon>
        </div>
        <div>
          <span class="risk-title">RMS均值</span>
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
      <div class="glass-card risk-card">
        <div class="risk-indicator low">
          <el-icon :size="28"><CircleCheck /></el-icon>
        </div>
        <div>
          <span class="risk-title">最新肌肉状态</span>
          <span class="risk-value">{{ muscleStatus }}</span>
        </div>
      </div>
    </div>

    <div class="glass-card" style="margin-top: 20px">
      <h3 style="margin-bottom: 8px">RMS 肌电强度 & 侧边压力趋势</h3>
      <p style="color: var(--color-text-muted); font-size: 13px; margin-bottom: 16px">
        当前展示的是所选小程序用户在后端数据库中的健康记录。
      </p>
      <div style="position: relative">
        <div ref="healthChartRef" class="chart-area"></div>
        <div v-if="loading" class="chart-loading">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        </div>
        <el-empty v-if="!loading && healthData.length === 0" class="chart-empty" description="暂无健康数据" />
      </div>
    </div>

    <div class="glass-card" style="margin-top: 20px">
      <div class="diag-header">
        <h3>AI 诊断评估</h3>
        <el-tag type="success" size="small">真实肌电 · AI 建议</el-tag>
      </div>
      <div class="diag-content">
        {{ diagnosticText }}
      </div>
    </div>

    <div class="glass-card report-table-card">
      <div class="diag-header">
        <div>
          <h3>健康报告明细</h3>
          <p class="table-caption">当前用户的每一份健康报告、评分和 AI 建议都来自后端数据库。</p>
        </div>
        <el-tag type="info" size="small">{{ rawHealthData.length }} 份报告</el-tag>
      </div>
      <div class="report-table-wrap">
        <el-table
          :data="rawHealthData"
          stripe
          border
          height="360"
          empty-text="该用户暂无健康报告"
        >
          <el-table-column prop="time" label="时间" width="176" />
          <el-table-column prop="score" label="健康评分" width="110">
            <template #default="scope">
              <el-tag :type="scoreTagType(scope.row.score)" size="small">
                {{ scope.row.score > 0 ? scope.row.score.toFixed(1) : '--' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="等级/状态" width="120" />
          <el-table-column label="建议来源" width="170">
            <template #default="scope">
              <el-tag :type="scope.row.aiSource === 'deepseek' ? 'success' : 'info'" size="small">
                {{ sourceLabel(scope.row.aiSource) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="rms" label="RMS" width="100" />
          <el-table-column prop="fatigue" label="疲劳指数" width="110" />
          <el-table-column label="AI 建议" min-width="280">
            <template #default="scope">
              <span class="report-advice">{{ scope.row.aiAdvice || '暂无 AI 建议' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { graphic } from 'echarts/core'
import { CircleCheck, Histogram, Loading, TrendCharts, Warning } from '@element-plus/icons-vue'
import { fetchHealthLogs, fetchHealthUsers } from '@/api/health'
import type { HealthLog, HealthUser } from '@/api/health'
import { normalizeStrength } from '@/utils/math.js'

echarts.use([LineChart, TooltipComponent, GridComponent, LegendComponent, DataZoomComponent, CanvasRenderer])

type HealthPoint = {
  id: number
  time: string
  rms: number
  pressure: number
  strength: number
  score: number
  status: string
  fatigue: number
  aiAdvice: string
  aiSource: string
  diagnostics: string
}

const healthChartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const users = ref<HealthUser[]>([])
const selectedUser = ref<number | null>(null)
const timeRange = ref<'24h' | '7d' | '30d' | 'all'>('24h')
const loading = ref(false)
const loadingUsers = ref(false)

const healthData = shallowRef<HealthPoint[]>([])
const rawHealthData = shallowRef<HealthPoint[]>([])

const rmsAvg = ref(0)
const pressureAvg = ref(0)
const riskLevel = ref('low')
const riskText = ref('暂无数据')
const muscleStatus = ref('暂无数据')
const diagnosticText = ref('请选择用户查看肌肉健康数据。')

function formatBeijingTime(value: string) {
  if (!value) return '--'
  const raw = value.trim()
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-')
}

function userLabel(user: HealthUser) {
  const name = user.name || user.username || user.phone || `用户#${user.id}`
  const suffix = user.health_log_count ? `${user.health_log_count}条健康记录` : '暂无健康记录'
  return `${name} · ${suffix}`
}

async function loadUsers() {
  loadingUsers.value = true
  try {
    users.value = await fetchHealthUsers()
    if (!selectedUser.value && users.value.length) {
      selectedUser.value = users.value[0].id
    }
  } catch {
    users.value = []
    selectedUser.value = null
  } finally {
    loadingUsers.value = false
  }
}

async function loadData() {
  if (!selectedUser.value) {
    rawHealthData.value = []
    healthData.value = []
    computeMetrics()
    renderChart()
    return
  }

  loading.value = true
  try {
    const logs: HealthLog[] = await fetchHealthLogs(selectedUser.value, { range: timeRange.value })
    const mapped = logs.map((log) => ({
      id: log.id,
      time: formatBeijingTime(log.created_at),
      rms: Number(log.rms_value || 0),
      pressure: Number(log.side_pressure ?? log.side_presure ?? 0),
      strength: normalizeStrength(Number(log.rms_value || 0)),
      score: Number(log.health_score || 0),
      status: log.health_level || log.muscle_status || log.muscle_status_label || '正常',
      fatigue: Number(log.analysis?.fatigue_index || 0),
      aiAdvice: log.ai_advice || '',
      aiSource: log.ai_source || '',
      diagnostics: log.ai_advice || log.diagnostics || '',
    }))
    rawHealthData.value = mapped
    healthData.value = mapped.length > 5000 ? lttbDownsample(mapped, 5000) : mapped
  } catch {
    rawHealthData.value = []
    healthData.value = []
  } finally {
    loading.value = false
    computeMetrics()
    renderChart()
  }
}

function computeMetrics() {
  const d = rawHealthData.value
  if (!d.length) {
    rmsAvg.value = 0
    pressureAvg.value = 0
    riskLevel.value = 'low'
    riskText.value = '暂无数据'
    muscleStatus.value = '暂无数据'
    diagnosticText.value = selectedUser.value
      ? '该用户暂无健康记录。请先在小程序端完成健康报告生成或肌电数据采集。'
      : '暂无可查看用户。请先使用小程序登录，或由管理员创建用户。'
    return
  }

  rmsAvg.value = d.reduce((sum, item) => sum + item.rms, 0) / d.length
  pressureAvg.value = d.reduce((sum, item) => sum + item.pressure, 0) / d.length
  const strengthAvg = d.reduce((sum, item) => sum + item.strength, 0) / d.length
  const latest = d[d.length - 1]
  muscleStatus.value = latest.status || '正常'

  if (latest.score > 0 && latest.score < 55) {
    riskLevel.value = 'high'
    riskText.value = '高风险'
    diagnosticText.value = latest.diagnostics || `当前健康评分为 ${latest.score.toFixed(1)}，建议暂停高强度训练并咨询专业医生。`
  } else if (latest.score > 0 && latest.score < 70) {
    riskLevel.value = 'medium'
    riskText.value = '中等风险'
    diagnosticText.value = latest.diagnostics || `当前健康评分为 ${latest.score.toFixed(1)}，建议降低训练强度并持续观察。`
  } else if (muscleStatus.value === '正常' || latest.score >= 70) {
    riskLevel.value = 'low'
    riskText.value = '低风险'
    diagnosticText.value = latest.diagnostics || `该用户 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，侧边压力均值为 ${pressureAvg.value.toFixed(1)}，最新肌肉状态正常。`
  } else if (rmsAvg.value < 80) {
    riskLevel.value = 'high'
    riskText.value = '高风险'
    diagnosticText.value = `该用户 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，归一化强度均值为 ${strengthAvg.toFixed(1)}。结合侧边压力均值 ${pressureAvg.value.toFixed(1)}，存在较高肌肉萎缩风险，建议增加康复训练频率并咨询专业医生。`
  } else if (rmsAvg.value < 150) {
    riskLevel.value = 'medium'
    riskText.value = '中等风险'
    diagnosticText.value = `该用户 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，归一化强度均值为 ${strengthAvg.toFixed(1)}。侧边压力均值 ${pressureAvg.value.toFixed(1)} 相对平稳，建议持续观察并保持规律训练。`
  } else {
    riskLevel.value = 'low'
    riskText.value = '低风险'
    diagnosticText.value = `该用户 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，归一化强度均值为 ${strengthAvg.toFixed(1)}。侧边压力均值 ${pressureAvg.value.toFixed(1)} 表现稳定，当前肌肉状态较好，建议维持训练方案。`
  }
}

function scoreTagType(score: number) {
  if (score <= 0) return 'info'
  if (score < 55) return 'danger'
  if (score < 70) return 'warning'
  return 'success'
}

function sourceLabel(source: string) {
  if (source === 'deepseek') return 'DeepSeek'
  if (source === 'deepseek_unavailable') return 'DeepSeek 不可用'
  if (source === 'local_fallback') return '本地规则'
  return '未请求 AI'
}

function renderChart() {
  if (!healthChartRef.value) return
  if (!chart) chart = echarts.init(healthChartRef.value)

  const d = healthData.value
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['RMS 肌电', '侧边压力'], textStyle: { color: '#94a3b8' } },
    grid: { left: 60, right: 60, top: 50, bottom: 60 },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      {
        type: 'slider',
        xAxisIndex: 0,
        height: 20,
        bottom: 8,
        borderColor: 'transparent',
        backgroundColor: 'rgba(30,41,59,0.5)',
        fillerColor: 'rgba(99,102,241,0.2)',
        handleStyle: { color: '#6366f1' },
      },
    ],
    xAxis: {
      type: 'category',
      data: d.map((v) => v.time),
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        name: 'RMS',
        nameTextStyle: { color: '#94a3b8' },
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(99,102,241,0.06)' } },
      },
      {
        type: 'value',
        name: '压力',
        nameTextStyle: { color: '#94a3b8' },
        axisLabel: { color: '#94a3b8' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'RMS 肌电',
        type: 'line',
        data: d.map((v) => v.rms),
        yAxisIndex: 0,
        showSymbol: false,
        smooth: true,
        lineStyle: { color: '#6366f1', width: 2 },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99,102,241,0.25)' },
            { offset: 1, color: 'rgba(99,102,241,0)' },
          ]),
        },
      },
      {
        name: '侧边压力',
        type: 'line',
        data: d.map((v) => v.pressure),
        yAxisIndex: 1,
        showSymbol: false,
        smooth: true,
        lineStyle: { color: '#06b6d4', width: 2 },
      },
    ],
  }, true)
}

function lttbDownsample(data: HealthPoint[], threshold: number): HealthPoint[] {
  if (threshold >= data.length || threshold <= 0) return data
  const sampled: HealthPoint[] = [data[0]]
  const bucketSize = (data.length - 2) / (threshold - 2)
  let a = 0

  for (let i = 0; i < threshold - 2; i++) {
    const bucketStart = Math.floor((i + 1) * bucketSize) + 1
    const bucketEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, data.length)
    const nextStart = bucketEnd
    const nextEnd = Math.min(Math.floor((i + 3) * bucketSize) + 1, data.length)
    let avgRms = 0
    let avgX = 0
    let avgCount = 0
    for (let j = nextStart; j < nextEnd; j++) {
      avgRms += data[j].rms
      avgX += j
      avgCount += 1
    }
    if (avgCount) {
      avgRms /= avgCount
      avgX /= avgCount
    }

    let maxArea = -1
    let maxIdx = bucketStart
    for (let j = bucketStart; j < bucketEnd; j++) {
      const area = Math.abs((a - avgX) * (data[j].rms - data[a].rms) - (a - j) * (avgRms - data[a].rms))
      if (area > maxArea) {
        maxArea = area
        maxIdx = j
      }
    }
    sampled.push(data[maxIdx])
    a = maxIdx
  }
  sampled.push(data[data.length - 1])
  return sampled
}

function handleResize() {
  chart?.resize()
}

watch(timeRange, loadData)

onMounted(async () => {
  await loadUsers()
  await loadData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header > div:first-child {
  flex: 1 1 420px;
  min-width: 0;
}
.page-title { font-size: 28px; font-weight: 700; margin: 0; }
.page-subtitle {
  max-width: 760px;
  margin: 8px 0 0;
  color: var(--color-text-muted);
  font-size: 14px;
  line-height: 1.6;
  word-break: normal;
  overflow-wrap: anywhere;
}
.header-actions {
  display: flex;
  flex: 0 1 auto;
  min-width: 0;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.risk-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; }
.risk-card { display: flex; align-items: center; gap: 16px; padding: 20px; }
.risk-indicator {
  width: 56px; height: 56px; border-radius: 14px; display: flex; align-items: center; justify-content: center; color: #fff; flex-shrink: 0;
}
.risk-indicator.low { background: linear-gradient(135deg, #22c55e, #4ade80); }
.risk-indicator.medium { background: linear-gradient(135deg, #f59e0b, #fbbf24); }
.risk-indicator.high { background: linear-gradient(135deg, #ef4444, #f87171); }
.risk-indicator.info { background: linear-gradient(135deg, #6366f1, #818cf8); }
.risk-title { display: block; font-size: 13px; color: var(--color-text-muted); }
.risk-value { display: block; font-size: 24px; font-weight: 700; margin-top: 4px; }

.chart-area { width: 100%; height: 380px; }
.chart-loading {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(15,23,42,0.6); border-radius: 10px; color: var(--color-primary);
}
.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.diag-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.diag-header > div:first-child { flex: 1 1 auto; min-width: 0; }
.diag-content { color: var(--color-text-muted); line-height: 1.8; font-size: 14px; padding: 16px; background: rgba(15,23,42,0.5); border-radius: 10px; border: 1px solid rgba(99,102,241,0.1); }
.report-table-card { margin-top: 20px; min-width: 0; overflow: hidden; }
.report-table-wrap { width: 100%; min-width: 0; overflow-x: auto; }
.report-table-wrap :deep(.el-table) { min-width: 1066px; }
.table-caption { margin: 6px 0 0; color: var(--color-text-muted); font-size: 13px; }
.report-advice { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.55; color: var(--color-text-muted); white-space: normal; }

@media (max-width: 900px) {
  .risk-row { grid-template-columns: 1fr; }
}

@media (max-width: 1100px) {
  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
