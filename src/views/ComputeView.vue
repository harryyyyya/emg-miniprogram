<template>
  <div>
    <h2 class="page-title gradient-text">算力管理</h2>

    <!-- 算力总览 -->
    <div class="compute-grid">
      <div class="glass-card compute-stat">
        <div class="cs-icon" style="background: linear-gradient(135deg, #6366f1, #818cf8);">
          <el-icon :size="24"><Monitor /></el-icon>
        </div>
        <div class="cs-info">
          <span class="cs-value">{{ trainingCount }} / {{ sessions.length }}</span>
          <span class="cs-label">GPU 使用量 (训练中/总任务)</span>
        </div>
        <el-progress :percentage="gpuPct" :stroke-width="8" color="#6366f1" style="width: 100%;" />
      </div>
      <div class="glass-card compute-stat">
        <div class="cs-icon" style="background: linear-gradient(135deg, #06b6d4, #22d3ee);">
          <el-icon :size="24"><Timer /></el-icon>
        </div>
        <div class="cs-info">
          <span class="cs-value">{{ queuedCount }}</span>
          <span class="cs-label">排队中任务</span>
        </div>
      </div>
      <div class="glass-card compute-stat">
        <div class="cs-icon" style="background: linear-gradient(135deg, #22c55e, #4ade80);">
          <el-icon :size="24"><CircleCheck /></el-icon>
        </div>
        <div class="cs-info">
          <span class="cs-value">{{ completedCount }}</span>
          <span class="cs-label">已完成训练</span>
        </div>
      </div>
    </div>

    <!-- 训练任务列表 -->
    <div class="glass-card" style="margin-top: 20px;">
      <h3 style="margin-bottom: 16px;">训练会话列表 (TrainingSession)</h3>
      <el-table v-loading="loading" :data="sessions" style="width: 100%" :header-cell-style="tableHeaderStyle">
        <el-table-column prop="session_id" label="会话 ID" width="200" />
        <el-table-column label="用户" width="120">
          <template #default="{ row }">
            {{ row.user_name || `#${row.user_id}` }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag
              :type="row.status === 'completed' ? 'success' : row.status === 'training' ? 'warning' : 'info'"
              size="small"
            >
              {{ statusMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="statusProgress(row.status)"
              :stroke-width="6"
              :color="row.status === 'completed' ? '#22c55e' : '#6366f1'"
            />
          </template>
        </el-table-column>
        <el-table-column label="提交时间">
          <template #default="{ row }">
            {{ row.created_at?.slice(0, 16).replace('T', ' ') }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchTrainingSessions } from '@/api/compute'
import type { TrainingSession } from '@/api/compute'

const tableHeaderStyle = {
  background: 'rgba(30, 41, 59, 0.8)',
  color: '#94a3b8',
  borderBottom: '1px solid rgba(99,102,241,0.1)',
}

const statusMap: Record<string, string> = {
  training: '训练中',
  completed: '已完成',
  queued: '排队中',
  collecting: '采集中',
}

// status → 进度百分比映射（后端无 progress 字段，按状态推断）
function statusProgress(status: string): number {
  if (status === 'completed') return 100
  if (status === 'training') return 50
  if (status === 'collecting') return 20
  return 0 // queued
}

const loading = ref(false)
const sessions = ref<TrainingSession[]>([])

async function loadSessions() {
  loading.value = true
  try {
    sessions.value = await fetchTrainingSessions()
  } catch {
    // 全局拦截器已弹出错误
  } finally {
    loading.value = false
  }
}

onMounted(loadSessions)

// 统计卡片从真实数据计算
const trainingCount = computed(() => sessions.value.filter((s) => s.status === 'training').length)
const queuedCount = computed(() => sessions.value.filter((s) => s.status === 'queued' || s.status === 'collecting').length)
const completedCount = computed(() => sessions.value.filter((s) => s.status === 'completed').length)
const gpuPct = computed(() => Math.min(100, Math.round((trainingCount.value / Math.max(sessions.value.length, 1)) * 100)))
</script>

<style scoped>
.page-title { font-size: 28px; font-weight: 700; margin-bottom: 24px; }
.compute-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.compute-stat { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; padding: 20px; }
.cs-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #fff; }
.cs-info { display: flex; flex-direction: column; }
.cs-value { font-size: 28px; font-weight: 700; }
.cs-label { font-size: 13px; color: var(--color-text-muted); }

:deep(.el-table) {
  --el-table-bg-color: transparent; --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent; --el-table-text-color: #cbd5e1;
  --el-table-border-color: rgba(99,102,241,0.08); --el-table-row-hover-bg-color: rgba(99,102,241,0.06);
}
</style>
