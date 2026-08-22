<template>
  <div>
    <div class="page-header">
      <div><h2 class="page-title gradient-text">采集数据</h2><p>查看小程序用户上传的肌电数据，并下载带动作标签的标准 CSV 文件用于后续训练。</p></div>
      <el-button :loading="loading" @click="loadData"><el-icon><Refresh /></el-icon>刷新</el-button>
    </div>
    <div class="filters">
      <el-input v-model="keyword" clearable placeholder="搜索用户、动作、设备或会话 ID" prefix-icon="Search" />
      <el-select v-model="status" clearable placeholder="全部状态"><el-option label="已完成" value="completed" /><el-option label="采集中" value="collecting" /><el-option label="无有效数据" value="empty" /></el-select>
    </div>
    <div class="glass-card table-wrap">
      <el-table :data="filteredRows" v-loading="loading" style="width:100%">
        <el-table-column label="采集用户" min-width="180"><template #default="{ row }"><div class="user-cell"><strong>{{ row.user_name || '未知用户' }}</strong><span>ID {{ row.user_id }}<template v-if="row.user_username"> · {{ row.user_username }}</template></span></div></template></el-table-column>
        <el-table-column prop="gesture_name" label="动作" min-width="120"><template #default="{ row }">{{ row.gesture_name || '-' }}</template></el-table-column>
        <el-table-column prop="hardware_id" label="设备" min-width="150"><template #default="{ row }">{{ row.hardware_id || 'BLE' }}</template></el-table-column>
        <el-table-column prop="total_samples" label="样本数" width="100" />
        <el-table-column prop="rms_value" label="RMS" width="100"><template #default="{ row }">{{ Number(row.rms_value || 0).toFixed(2) }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="110"><template #default="{ row }"><el-tag :type="statusTagType(row)">{{ statusLabel(row) }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="采集时间" min-width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column prop="session_id" label="会话 ID" min-width="190" show-overflow-tooltip />
        <el-table-column label="操作" width="190" fixed="right"><template #default="{ row }"><el-button type="primary" size="small" :disabled="row.downloadable === false" :loading="downloading === row.session_id" @click="download(row)"><el-icon><Download /></el-icon>下载 CSV</el-button><el-button type="danger" size="small" :loading="deleting === row.session_id" @click="remove(row)"><el-icon><Delete /></el-icon>删除</el-button></template></el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredRows.length" description="暂无采集数据" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, Refresh } from '@element-plus/icons-vue'
import { deleteTrainingSession, downloadTrainingSession, fetchTrainingSessions, type TrainingSession } from '@/api/training'

const rows = ref<TrainingSession[]>([])
const loading = ref(false)
const downloading = ref('')
const deleting = ref('')
const keyword = ref('')
const status = ref('')
const filteredRows = computed(() => rows.value.filter((row) => {
  const text = `${row.user_name || ''} ${row.user_username || ''} ${row.user_id} ${row.gesture_name || ''} ${row.hardware_id || ''} ${row.session_id}`.toLowerCase()
  return (!keyword.value || text.includes(keyword.value.toLowerCase())) && (!status.value || row.status === status.value)
}))
function formatTime(value: string) { return value ? new Date(value).toLocaleString('zh-CN') : '-' }
function statusLabel(row: TrainingSession) {
  if (row.status === 'empty') return '无有效数据'
  if (row.status === 'completed') return '已完成'
  if (row.status === 'collecting') return '采集中'
  return row.status === 'training' ? '训练中' : '等待处理'
}
function statusTagType(row: TrainingSession) {
  if (row.status === 'empty') return 'danger'
  if (row.status === 'completed') return 'success'
  return 'warning'
}
async function loadData() { loading.value = true; try { rows.value = await fetchTrainingSessions() } finally { loading.value = false } }
async function download(row: TrainingSession) {
  downloading.value = row.session_id
  try {
    const blob = await downloadTrainingSession(row.session_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const userLabel = (row.user_username || row.user_name || `user-${row.user_id}`).replace(/[^\w\u4e00-\u9fa5.-]+/g, '_')
    const gesture = (row.gesture_name || 'unlabeled').replace(/[^\w\u4e00-\u9fa5.-]+/g, '_')
    link.href = url; link.download = `user-${row.user_id}_${userLabel}_${gesture}_${row.session_id}.csv`; link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } finally { downloading.value = '' }
}
async function remove(row: TrainingSession) {
  await ElMessageBox.confirm(`确定删除用户“${row.user_name || row.user_id}”的采集数据吗？原始文件也会一并删除。`, '删除采集数据', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  deleting.value = row.session_id
  try { await deleteTrainingSession(row.session_id); ElMessage.success('采集数据已删除'); await loadData() }
  finally { deleting.value = '' }
}
onMounted(loadData)
</script>

<style scoped>
.page-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px}.page-header p{color:var(--color-text-muted);margin-top:6px}.filters{display:grid;grid-template-columns:minmax(260px,420px) 180px;gap:12px;margin-bottom:16px}.table-wrap{padding:16px}.user-cell{display:flex;flex-direction:column;gap:3px}.user-cell span{color:var(--color-text-muted);font-size:12px}@media(max-width:700px){.filters{grid-template-columns:1fr}.page-header{gap:16px}}
</style>
