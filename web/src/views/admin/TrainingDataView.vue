<template>
  <div>
    <div class="page-header">
      <div><h2 class="page-title gradient-text">采集数据</h2><p>查看小程序用户上传的肌电数据，并下载原始 DAT 文件用于后续训练。</p></div>
      <el-button :loading="loading" @click="loadData"><el-icon><Refresh /></el-icon>刷新</el-button>
    </div>
    <div class="filters">
      <el-input v-model="keyword" clearable placeholder="搜索用户、动作、设备或会话 ID" prefix-icon="Search" />
      <el-select v-model="status" clearable placeholder="全部状态"><el-option label="已完成" value="completed" /><el-option label="采集中" value="collecting" /></el-select>
    </div>
    <div class="glass-card table-wrap">
      <el-table :data="filteredRows" v-loading="loading" style="width:100%">
        <el-table-column prop="user_name" label="用户" min-width="120" />
        <el-table-column prop="gesture_name" label="动作" min-width="120"><template #default="{ row }">{{ row.gesture_name || '-' }}</template></el-table-column>
        <el-table-column prop="hardware_id" label="设备" min-width="150"><template #default="{ row }">{{ row.hardware_id || 'BLE' }}</template></el-table-column>
        <el-table-column prop="total_samples" label="样本数" width="100" />
        <el-table-column prop="rms_value" label="RMS" width="100"><template #default="{ row }">{{ Number(row.rms_value || 0).toFixed(2) }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : 'warning'">{{ row.status === 'completed' ? '已完成' : '采集中' }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="采集时间" min-width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column prop="session_id" label="会话 ID" min-width="190" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right"><template #default="{ row }"><el-button type="primary" size="small" :disabled="!row.raw_data_path" :loading="downloading === row.session_id" @click="download(row)"><el-icon><Download /></el-icon>下载</el-button></template></el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredRows.length" description="暂无采集数据" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Refresh } from '@element-plus/icons-vue'
import { downloadTrainingSession, fetchTrainingSessions, type TrainingSession } from '@/api/training'

const rows = ref<TrainingSession[]>([])
const loading = ref(false)
const downloading = ref('')
const keyword = ref('')
const status = ref('')
const filteredRows = computed(() => rows.value.filter((row) => {
  const text = `${row.user_name || ''} ${row.gesture_name || ''} ${row.hardware_id || ''} ${row.session_id}`.toLowerCase()
  return (!keyword.value || text.includes(keyword.value.toLowerCase())) && (!status.value || row.status === status.value)
}))
function formatTime(value: string) { return value ? new Date(value).toLocaleString('zh-CN') : '-' }
async function loadData() { loading.value = true; try { rows.value = await fetchTrainingSessions() } finally { loading.value = false } }
async function download(row: TrainingSession) {
  downloading.value = row.session_id
  try {
    const blob = await downloadTrainingSession(row.session_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = `${row.session_id}.dat`; link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } finally { downloading.value = '' }
}
onMounted(loadData)
</script>

<style scoped>
.page-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px}.page-header p{color:var(--color-text-muted);margin-top:6px}.filters{display:grid;grid-template-columns:minmax(260px,420px) 180px;gap:12px;margin-bottom:16px}.table-wrap{padding:16px}@media(max-width:700px){.filters{grid-template-columns:1fr}.page-header{gap:16px}}
</style>
