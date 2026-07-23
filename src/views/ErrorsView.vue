<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">错误分析系统</h2>
      <div class="header-actions">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          style="width: 280px;"
        />
        <el-button :loading="loadingAll" @click="toggleViewMode">
          {{ allMode ? '分页模式' : '全量模式 (虚拟滚动)' }}
        </el-button>
        <el-button type="primary" :loading="analyzing" @click="runAiAnalysis">
          <el-icon><MagicStick /></el-icon>
          AI 一键分析
        </el-button>
      </div>
    </div>

    <!-- 分页模式：普通 el-table，后端分页，适合日常浏览 -->
    <div class="glass-card" v-if="!allMode">
      <el-table v-loading="tableLoading" :data="errorLogs" style="width: 100%" :header-cell-style="tableHeaderStyle" max-height="440">
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="hardware_id" label="设备 ID" width="140" />
        <el-table-column prop="error_code" label="错误码" width="120">
          <template #default="{ row }">
            <el-tag type="danger" size="small">{{ row.error_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误描述" show-overflow-tooltip />
      </el-table>

      <div class="table-footer">
        <el-pagination
          :total="totalLogs"
          :page-size="10"
          :current-page="currentPage"
          layout="total, prev, pager, next"
          small
          @current-change="onPageChange"
        />
      </div>
    </div>

    <!-- 全量模式：el-table-v2 虚拟滚动，承载 1000+ 行不卡顿 -->
    <div class="glass-card" v-else>
      <div style="margin-bottom: 12px; color: var(--color-text-muted); font-size: 13px;">
        已加载 {{ allLogs.length }} 条记录，使用虚拟滚动渲染
      </div>
      <el-table-v2
        :columns="v2Columns"
        :data="allLogs"
        :width="tableWidth"
        :height="440"
        :header-height="48"
        :row-height="48"
        v-loading="loadingAll"
        fixed
      />
    </div>

    <!-- AI 分析侧边抽屉 -->
    <el-drawer v-model="drawerVisible" title="AI Agent 技术分析报告" size="480px" direction="rtl">
      <div class="ai-report">
        <div class="report-section">
          <h4>📊 错误聚类分析</h4>
          <div class="cluster-list">
            <div v-for="c in clusters" :key="c.name" class="cluster-item">
              <div class="cluster-info">
                <span class="cluster-name">{{ c.name }}</span>
                <span class="cluster-pct">{{ c.pct }}%</span>
              </div>
              <div class="cluster-bar-bg">
                <div class="cluster-bar-fill" :style="{ width: c.pct + '%', background: c.color }"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="report-section">
          <h4>🔍 智能排查建议</h4>
          <div class="ai-text">
            {{ aiReport }}
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { ElMessage, ElTag } from 'element-plus'
import type { Column } from 'element-plus'
import { fetchErrorLogs, analyzeErrors } from '@/api/errors'
import type { ErrorLog, ErrorCluster } from '@/api/errors'

const dateRange = ref<[Date, Date] | null>(null)
const analyzing = ref(false)
const drawerVisible = ref(false)

const tableHeaderStyle = {
  background: 'rgba(30, 41, 59, 0.8)',
  color: '#94a3b8',
  borderBottom: '1px solid rgba(99,102,241,0.1)',
}

// ── 分页模式 ──
const errorLogs = ref<ErrorLog[]>([])
const totalLogs = ref(0)
const currentPage = ref(1)
const pageSize = 10
const tableLoading = ref(false)

async function loadLogs() {
  tableLoading.value = true
  try {
    const [start, end] = dateRange.value ?? [undefined, undefined]
    const res = await fetchErrorLogs({
      page: currentPage.value,
      pageSize,
      startDate: start ? (start as Date).toISOString().slice(0, 10) : undefined,
      endDate: end ? (end as Date).toISOString().slice(0, 10) : undefined,
    })
    errorLogs.value = res.items
    totalLogs.value = res.total
  } catch {
    // 全局拦截器已弹出错误
  } finally {
    tableLoading.value = false
  }
}

function onPageChange(page: number) {
  currentPage.value = page
  loadLogs()
}

onMounted(loadLogs)

// ── 全量虚拟滚动模式 (el-table-v2，承载 1000+ 行不卡顿) ──
const allMode = ref(false)
const allLogs = ref<ErrorLog[]>([])
const loadingAll = ref(false)
const tableWidth = ref(900)

// el-table-v2 列定义（使用渲染函数，支持自定义 cell）
const v2Columns: Column<ErrorLog>[] = [
  { key: 'created_at', dataKey: 'created_at', title: '时间', width: 180 },
  { key: 'hardware_id', dataKey: 'hardware_id', title: '设备 ID', width: 140 },
  {
    key: 'error_code',
    dataKey: 'error_code',
    title: '错误码',
    width: 120,
    cellRenderer: ({ rowData }: { rowData: ErrorLog }) =>
      h(ElTag, { type: 'danger', size: 'small' }, () => rowData.error_code),
  },
  { key: 'error_msg', dataKey: 'error_msg', title: '错误描述', width: 460, flexGrow: 1 },
]

async function loadAllLogs() {
  loadingAll.value = true
  try {
    // 一次请求拉取大页：pageSize=2000 涵盖 1000+ 场景
    const [start, end] = dateRange.value ?? [undefined, undefined]
    const res = await fetchErrorLogs({
      page: 1,
      pageSize: 2000,
      startDate: start ? (start as Date).toISOString().slice(0, 10) : undefined,
      endDate: end ? (end as Date).toISOString().slice(0, 10) : undefined,
    })
    allLogs.value = res.items
  } catch {
    // 全局拦截器已弹出错误
  } finally {
    loadingAll.value = false
  }
}

function toggleViewMode() {
  allMode.value = !allMode.value
  if (allMode.value && allLogs.value.length === 0) {
    loadAllLogs()
  }
}

// ── AI 聚类分析 ──
const clusters = ref<ErrorCluster[]>([])
const aiReport = ref('')

async function runAiAnalysis() {
  analyzing.value = true

  const tip = ElMessage({
    message: 'AI Agent 正在对错误日志进行聚类分析，预计需要 20-60 秒，请耐心等待...',
    type: 'info',
    duration: 0,
  })

  try {
    const [start, end] = dateRange.value ?? [undefined, undefined]
    const result = await analyzeErrors({
      startDate: start ? (start as Date).toISOString().slice(0, 10) : undefined,
      endDate: end ? (end as Date).toISOString().slice(0, 10) : undefined,
    })

    clusters.value = result.clusters
    aiReport.value = result.report
    drawerVisible.value = true
  } catch {
    // 全局拦截器已弹出错误
  } finally {
    tip.close()
    analyzing.value = false
  }
}
</script>

<style scoped>
.page-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 12px;
}
.page-title { font-size: 28px; font-weight: 700; }
.header-actions { display: flex; gap: 12px; align-items: center; }
.table-footer { display: flex; justify-content: flex-end; padding-top: 16px; }

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-text-color: #cbd5e1;
  --el-table-border-color: rgba(99,102,241,0.08);
  --el-table-row-hover-bg-color: rgba(99,102,241,0.06);
}

.ai-report { padding: 8px; }
.report-section { margin-bottom: 24px; }
.report-section h4 { font-size: 16px; margin-bottom: 12px; }

.cluster-list { display: flex; flex-direction: column; gap: 10px; }
.cluster-item {}
.cluster-info { display: flex; justify-content: space-between; margin-bottom: 4px; }
.cluster-name { font-size: 14px; }
.cluster-pct { font-size: 14px; font-weight: 600; }
.cluster-bar-bg { height: 8px; background: rgba(51,65,85,0.4); border-radius: 4px; overflow: hidden; }
.cluster-bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease; }

.ai-text {
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.8;
  color: #cbd5e1;
  padding: 16px;
  background: rgba(15,23,42,0.5);
  border-radius: 10px;
  border: 1px solid rgba(99,102,241,0.1);
}
</style>
