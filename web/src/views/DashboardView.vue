<template>
  <div>
    <h2 class="page-title gradient-text">仪表盘总览</h2>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <div v-for="stat in stats" :key="stat.label" class="glass-card stat-card">
        <div class="stat-icon" :style="{ background: stat.color }">
          <el-icon :size="24"><component :is="stat.icon" /></el-icon>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stat.value }}</span>
          <span class="stat-label">{{ stat.label }}</span>
        </div>
        <div class="stat-trend" :class="stat.trend > 0 ? 'up' : 'down'">
          {{ stat.trend > 0 ? '+' : '' }}{{ stat.trend }}%
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="chart-row">
      <div class="glass-card chart-card" style="flex: 2">
        <h3>设备活跃趋势 (近 7 天)</h3>
        <div ref="activityChartRef" class="chart-container"></div>
      </div>
      <div class="glass-card chart-card" style="flex: 1">
        <h3>错误类型分布</h3>
        <div ref="errorPieRef" class="chart-container"></div>
      </div>
    </div>

    <!-- 最近告警 -->
    <div class="glass-card" style="margin-top: 20px;">
      <h3 style="margin-bottom: 16px;">最近系统告警</h3>
      <el-table :data="recentAlerts" style="width: 100%" :header-cell-style="tableHeaderStyle">
        <el-table-column prop="time" label="时间" width="180" />
        <el-table-column prop="device" label="设备" width="160" />
        <el-table-column prop="message" label="告警内容" />
        <el-table-column prop="level" label="等级" width="100">
          <template #default="{ row }">
            <el-tag :type="row.level === '严重' ? 'danger' : row.level === '警告' ? 'warning' : 'info'" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
// ECharts 按需引入 —— 彻底树摇，去除未使用的 20+ 图表类型
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import {
  TooltipComponent,
  GridComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { graphic } from 'echarts/core'

echarts.use([LineChart, PieChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const activityChartRef = ref<HTMLElement>()
const errorPieRef = ref<HTMLElement>()
let activityChart: echarts.ECharts | null = null
let errorPie: echarts.ECharts | null = null

const tableHeaderStyle = {
  background: 'rgba(30, 41, 59, 0.8)',
  color: '#94a3b8',
  borderBottom: '1px solid rgba(99,102,241,0.1)',
}

const stats = [
  { label: '在线设备', value: '128', icon: 'Cpu', color: 'linear-gradient(135deg,#6366f1,#818cf8)', trend: 12 },
  { label: '活跃患者', value: '86', icon: 'User', color: 'linear-gradient(135deg,#06b6d4,#22d3ee)', trend: 8 },
  { label: '今日错误', value: '7', icon: 'Warning', color: 'linear-gradient(135deg,#f59e0b,#fbbf24)', trend: -23 },
  { label: '训练任务', value: '15', icon: 'Monitor', color: 'linear-gradient(135deg,#22c55e,#4ade80)', trend: 5 },
]

const recentAlerts = [
  { time: '2026-03-23 22:31', device: 'ESP32-A7F3', message: '传感器 CH2 信号丢失超过30秒', level: '严重' },
  { time: '2026-03-23 21:15', device: 'ESP32-B1D9', message: '电池电量低于 15%', level: '警告' },
  { time: '2026-03-23 20:50', device: 'ESP32-C4E2', message: '固件版本过旧 (v1.0.2)', level: '提示' },
  { time: '2026-03-23 19:22', device: 'ESP32-A7F3', message: 'BLE 连接频繁断开重连', level: '警告' },
]

function initCharts() {
  // 活跃趋势折线图
  if (activityChartRef.value) {
    activityChart = echarts.init(activityChartRef.value)
    activityChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 30, bottom: 30 },
      xAxis: {
        type: 'category',
        data: ['03-17', '03-18', '03-19', '03-20', '03-21', '03-22', '03-23'],
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#94a3b8' },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: 'rgba(99,102,241,0.08)' } },
        axisLabel: { color: '#94a3b8' },
      },
      series: [
        {
          name: '活跃设备数',
          type: 'line',
          smooth: true,
          data: [98, 105, 112, 108, 120, 125, 128],
          lineStyle: { color: '#6366f1', width: 3 },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(99,102,241,0.3)' },
              { offset: 1, color: 'rgba(99,102,241,0.02)' },
            ]),
          },
          itemStyle: { color: '#818cf8' },
        },
      ],
    })
  }

  // 错误分布饼图
  if (errorPieRef.value) {
    errorPie = echarts.init(errorPieRef.value)
    errorPie.setOption({
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['45%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: '#0f172a', borderWidth: 3 },
          label: { show: true, color: '#94a3b8', fontSize: 11 },
          data: [
            { value: 35, name: '通信丢失', itemStyle: { color: '#ef4444' } },
            { value: 25, name: '传感器异常', itemStyle: { color: '#f59e0b' } },
            { value: 20, name: '电量过低', itemStyle: { color: '#6366f1' } },
            { value: 12, name: 'BLE断连', itemStyle: { color: '#06b6d4' } },
            { value: 8, name: '其他', itemStyle: { color: '#334155' } },
          ],
        },
      ],
    })
  }
}

function handleResize() {
  activityChart?.resize()
  errorPie?.resize()
}

onMounted(() => {
  initCharts()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  activityChart?.dispose()
  errorPie?.dispose()
})
</script>

<style scoped>
.page-title {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 24px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.stat-info {
  display: flex;
  flex-direction: column;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}
.stat-label {
  font-size: 13px;
  color: var(--color-text-muted);
}
.stat-trend {
  margin-left: auto;
  font-size: 13px;
  font-weight: 600;
}
.stat-trend.up { color: var(--color-success); }
.stat-trend.down { color: var(--color-danger); }

.chart-row {
  display: flex;
  gap: 20px;
}
.chart-card h3 {
  font-size: 16px;
  margin-bottom: 12px;
  color: var(--color-text);
}
.chart-container {
  width: 100%;
  height: 280px;
}

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-text-color: #cbd5e1;
  --el-table-border-color: rgba(99,102,241,0.08);
  --el-table-row-hover-bg-color: rgba(99,102,241,0.06);
}
</style>
