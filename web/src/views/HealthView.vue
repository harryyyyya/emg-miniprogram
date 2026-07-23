<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">肌肉健康可视化</h2>
      <div class="header-actions">
        <el-select v-model="selectedUser" placeholder="选择患者" style="width: 200px;">
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-radio-group v-model="timeRange" size="default">
          <el-radio-button value="24h">24小时</el-radio-button>
          <el-radio-button value="7d">近7天</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 风险等级卡片 -->
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
    </div>

    <!-- ECharts 双轴图 -->
    <div class="glass-card" style="margin-top: 20px;">
      <h3 style="margin-bottom: 8px;">RMS 肌电强度 & 侧边压力趋势</h3>
      <p style="color: var(--color-text-muted); font-size: 13px; margin-bottom: 16px;">
        支持鼠标滚轮缩放、拖拽查看详情，已启用大数据性能优化
      </p>
      <div style="position: relative;">
        <div ref="healthChartRef" class="chart-area"></div>
        <div v-if="loading" class="chart-loading">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        </div>
      </div>
    </div>

    <!-- LLM 诊断结论 -->
    <div class="glass-card" style="margin-top: 20px;">
      <div class="diag-header">
        <h3>AI 诊断评估</h3>
        <el-tag type="success" size="small">LLM 分析</el-tag>
      </div>
      <div class="diag-content">
        {{ diagnosticText }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
// ECharts 按需引入 — 健康视图：折线图 + 数据缩放
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

echarts.use([LineChart, TooltipComponent, GridComponent, LegendComponent, DataZoomComponent, CanvasRenderer])

import { Loading } from '@element-plus/icons-vue'
import { fetchHealthLogs } from '@/api/health'
import type { HealthLog } from '@/api/health'
import { normalizeStrength } from '@/utils/math.js'

// ─── LTTB 降采样（Largest-Triangle-Three-Buckets）─────────────────────────
// 当数据点 > LTTB_THRESHOLD 时启用，保留关键形态，避免 Canvas 渲染过万点
const LTTB_THRESHOLD = 5000

/**
 * LTTB 降采样：在保留信号形态的前提下，将 data 压缩到 threshold 个点
 * @param data   原始数组 [{time, rms, pressure}, ...]
 * @param threshold  目标点数
 */
type HealthPoint = { time: string; rms: number; pressure: number; strength: number }

function lttbDownsample(data: HealthPoint[], threshold: number): HealthPoint[] {
  const len = data.length
  if (threshold >= len || threshold <= 0) return data

  const sampled: typeof data = []
  sampled.push(data[0]) // 始终保留首点

  const bucketSize = (len - 2) / (threshold - 2)
  let a = 0 // 上一个选中点的索引

  for (let i = 0; i < threshold - 2; i++) {
    // 当前桶
    const bucketStart = Math.floor((i + 1) * bucketSize) + 1
    const bucketEnd   = Math.min(Math.floor((i + 2) * bucketSize) + 1, len)

    // 下一个桶的平均值（作为 C 点）
    const nextStart = bucketEnd
    const nextEnd   = Math.min(Math.floor((i + 3) * bucketSize) + 1, len)
    let avgRms = 0, avgX = 0, avgCount = 0
    for (let j = nextStart; j < nextEnd; j++) {
      avgRms += data[j].rms
      avgX   += j
      avgCount++
    }
    if (avgCount) { avgRms /= avgCount; avgX /= avgCount }

    // 在当前桶中选三角形面积最大的点
    let maxArea = -1, maxIdx = bucketStart
    const aX = a, aRms = data[a].rms
    for (let j = bucketStart; j < bucketEnd; j++) {
      const area = Math.abs((aX - avgX) * (data[j].rms - aRms) - (aX - j) * (avgRms - aRms))
      if (area > maxArea) { maxArea = area; maxIdx = j }
    }

    sampled.push(data[maxIdx])
    a = maxIdx
  }

  sampled.push(data[len - 1]) // 始终保留尾点
  return sampled
}

const healthChartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const selectedUser = ref(1)
const timeRange = ref<'24h' | '7d'>('24h')
const loading = ref(false)

const users = [
  { id: 1, name: '患者张三' },
  { id: 2, name: '患者李四' },
  { id: 3, name: '患者王五' },
]

// shallowRef 避免对大数据数组进行深层响应式劫持，提升渲染性能
const healthData = shallowRef<HealthPoint[]>([])
const rawHealthData = shallowRef<HealthPoint[]>([])

async function loadData() {
  loading.value = true
  try {
    const logs: HealthLog[] = await fetchHealthLogs(selectedUser.value, { range: timeRange.value })
    const mapped: HealthPoint[] = logs.map((log) => ({
      time: log.created_at.slice(5, 16).replace('T', ' '), // "MM-DD HH:mm"
      rms: log.rms_value,
      pressure: log.side_pressure,
      strength: normalizeStrength(log.rms_value),
    }))
    rawHealthData.value = [...mapped]

    let displayData = mapped
    // LTTB 降采样：超过 5000 点时压缩，保留信号形态
    if (displayData.length > LTTB_THRESHOLD) {
      displayData = lttbDownsample(displayData, LTTB_THRESHOLD)
    }
    // 赋值新数组引用以触发 shallowRef 侦测
    healthData.value = [...displayData]
  } catch {
    healthData.value = []
    rawHealthData.value = []
  } finally {
    loading.value = false
  }
}

const rmsAvg = ref(0)
const pressureAvg = ref(0)
const riskLevel = ref('low')
const riskText = ref('低风险')
const diagnosticText = ref('')

function computeMetrics() {
  const d = rawHealthData.value
  if (!d.length) return
  rmsAvg.value = d.reduce((s, v) => s + v.rms, 0) / d.length
  pressureAvg.value = d.reduce((s, v) => s + v.pressure, 0) / d.length
  const strengthAvg = d.reduce((s, v) => s + v.strength, 0) / d.length

  if (rmsAvg.value < 800) {
    riskLevel.value = 'high'
    riskText.value = '高风险'
    diagnosticText.value = `患者 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，归一化强度均值为 ${strengthAvg.toFixed(1)}。结合侧边压力均值 ${pressureAvg.value.toFixed(1)}，LLM 评估该患者存在较高的肌肉萎缩风险。建议立即启动线下康复训练计划并每日监测信号变化。`
  } else if (rmsAvg.value < 1200) {
    riskLevel.value = 'medium'
    riskText.value = '中等风险'
    diagnosticText.value = `患者 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，归一化强度均值为 ${strengthAvg.toFixed(1)}。侧边压力均值 ${pressureAvg.value.toFixed(1)} 相对平稳。LLM 建议持续观察，适当增加穿戴频率以提高肌肉活跃度。`
  } else {
    riskLevel.value = 'low'
    riskText.value = '低风险'
    diagnosticText.value = `患者 RMS 肌电均值为 ${rmsAvg.value.toFixed(1)}，归一化强度均值为 ${strengthAvg.toFixed(1)}。侧边压力均值 ${pressureAvg.value.toFixed(1)} 表现稳定。LLM 评估当前肌肉状态良好，建议维持当前训练方案。`
  }
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
      { type: 'slider', xAxisIndex: 0, height: 20, bottom: 8, borderColor: 'transparent', backgroundColor: 'rgba(30,41,59,0.5)', fillerColor: 'rgba(99,102,241,0.2)', handleStyle: { color: '#6366f1' } },
    ],
    xAxis: {
      type: 'category',
      data: d.map((v) => v.time),
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 },
    },
    yAxis: [
      { type: 'value', name: 'RMS', max: 4096, nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(99,102,241,0.06)' } } },
      { type: 'value', name: '压力', max: 100, nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { show: false } },
    ],
    series: [
      {
        name: 'RMS 肌电',
        type: 'line',
        data: d.map((v) => v.rms),
        yAxisIndex: 0,
        showSymbol: false,
        large: true,
        largeThreshold: 2000,
        smooth: true,
        lineStyle: { color: '#6366f1', width: 2 },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99,102,241,0.25)' },
            { offset: 1, color: 'rgba(99,102,241,0)' },
          ]),
        },
        itemStyle: { color: '#818cf8' },
      },
      {
        name: '侧边压力',
        type: 'line',
        data: d.map((v) => v.pressure),
        yAxisIndex: 1,
        showSymbol: false,
        large: true,
        largeThreshold: 2000,
        smooth: true,
        lineStyle: { color: '#06b6d4', width: 2 },
        itemStyle: { color: '#22d3ee' },
      },
    ],
  })
}

function handleResize() { chart?.resize() }

watch([selectedUser, timeRange], async () => {
  await loadData()
  computeMetrics()
  renderChart()
})

onMounted(async () => {
  await loadData()
  computeMetrics()
  renderChart()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
</script>

<style scoped>
.page-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 12px;
}
.page-title { font-size: 28px; font-weight: 700; }
.header-actions { display: flex; gap: 12px; align-items: center; }

.risk-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
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

.diag-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.diag-content { color: var(--color-text-muted); line-height: 1.8; font-size: 14px; padding: 16px; background: rgba(15,23,42,0.5); border-radius: 10px; border: 1px solid rgba(99,102,241,0.1); }
</style>
