<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title gradient-text">报表管控</h2>
        <p class="page-subtitle">这里的患者资料来自后端真实用户数据，会和小程序登录页录入的信息同步。</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadPatients">刷新</el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新增患者
        </el-button>
      </div>
    </div>

    <div class="glass-card">
      <h3 style="margin-bottom: 16px">患者列表 · 点击生成诊断报告</h3>
      <el-table :data="patients" style="width: 100%" :header-cell-style="tableHeaderStyle" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="姓名" min-width="140" />
        <el-table-column prop="phone" label="手机号" min-width="140">
          <template #default="{ row }">{{ row.phone || '-' }}</template>
        </el-table-column>
        <el-table-column prop="amputation_part" label="截肢部位" min-width="150">
          <template #default="{ row }">{{ row.amputation_part || '-' }}</template>
        </el-table-column>
        <el-table-column prop="illness_duration_months" label="患病时长" width="130">
          <template #default="{ row }">{{ formatDuration(row.illness_duration_months) }}</template>
        </el-table-column>
        <el-table-column prop="last_report" label="上次报告" width="150">
          <template #default="{ row }">{{ row.last_report || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" :loading="row.generating" @click="generateReport(row)">
              <el-icon><Document /></el-icon>
              生成报告
            </el-button>
            <el-button size="small" @click="openEdit(row)">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <el-button type="danger" size="small" @click="removePatient(row)">
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="诊断结论" width="620">
      <div class="diag-dialog-content">
        <div class="diag-meta">
          <el-tag type="success" size="small">健康报告结果</el-tag>
          <span style="color: var(--color-text-muted); font-size: 13px">患者：{{ currentPatient?.name }}</span>
        </div>
        <div class="diag-text">{{ currentDiagnostics }}</div>
      </div>
    </el-dialog>

    <el-dialog v-model="editorVisible" :title="editingId ? '编辑患者资料' : '新增患者资料'" width="560">
      <el-form label-position="top">
        <el-form-item label="姓名">
          <el-input v-model="form.name" placeholder="请输入患者姓名" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="可选，用于和手机号登录用户关联" maxlength="20" />
        </el-form-item>
        <el-form-item label="截肢部位">
          <el-input v-model="form.amputation_part" placeholder="例如：左前臂、右手掌、左小腿" />
        </el-form-item>
        <el-form-item label="患病时长（月）">
          <el-input-number v-model="form.illness_duration_months" :min="0" :max="1200" style="width: 180px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePatient">
          {{ editingId ? '保存修改' : '新增' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Delete, Document, Edit, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createHealthUser,
  deleteHealthUser,
  fetchHealthUsers,
  generateReport as apiGenerateReport,
  updateHealthUser,
} from '@/api/health'
import type { HealthUser } from '@/api/health'

interface PatientRow extends HealthUser {
  generating?: boolean
}

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editorVisible = ref(false)
const editingId = ref<number | null>(null)
const currentPatient = ref<PatientRow | null>(null)
const currentDiagnostics = ref('')
const patients = ref<PatientRow[]>([])

const form = reactive({
  name: '',
  phone: '',
  amputation_part: '',
  illness_duration_months: 0,
})

const tableHeaderStyle = {
  background: 'rgba(30, 41, 59, 0.8)',
  color: '#94a3b8',
  borderBottom: '1px solid rgba(99,102,241,0.1)',
}

async function loadPatients() {
  loading.value = true
  try {
    patients.value = (await fetchHealthUsers()).map((item) => ({ ...item, generating: false }))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.phone = ''
  form.amputation_part = ''
  form.illness_duration_months = 0
  editorVisible.value = true
}

function openEdit(row: PatientRow) {
  editingId.value = row.id
  form.name = row.name || ''
  form.phone = row.phone || ''
  form.amputation_part = row.amputation_part || ''
  form.illness_duration_months = row.illness_duration_months || 0
  editorVisible.value = true
}

async function savePatient() {
  if (!form.name.trim()) return ElMessage.warning('请填写患者姓名')
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      phone: form.phone.trim(),
      amputation_part: form.amputation_part.trim(),
      illness_duration_months: form.illness_duration_months || 0,
    }
    if (editingId.value) {
      await updateHealthUser(editingId.value, payload)
      ElMessage.success('患者资料已更新')
    } else {
      await createHealthUser(payload)
      ElMessage.success('患者已新增')
    }
    editorVisible.value = false
    await loadPatients()
  } finally {
    saving.value = false
  }
}

async function removePatient(row: PatientRow) {
  await ElMessageBox.confirm(
    `确定删除患者「${row.name}」吗？相关设备、健康记录、训练记录、帖子和评论也会被删除。`,
    '删除患者',
    {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    },
  )
  await deleteHealthUser(row.id)
  ElMessage.success('患者已删除')
  await loadPatients()
}

async function generateReport(patient: PatientRow) {
  if (patient.generating) return
  patient.generating = true
  const loadingMsg = ElMessage({
    message: `正在为 ${patient.name} 生成诊断报告，请稍候...`,
    type: 'info',
    duration: 0,
  })

  try {
    const response = await apiGenerateReport(patient.id)
    currentPatient.value = patient
    currentDiagnostics.value = response.diagnostics || '报告已生成，但暂无诊断建议。'
    dialogVisible.value = true
    ElMessage.success('报告生成完毕')
    await loadPatients()
  } finally {
    loadingMsg.close()
    patient.generating = false
  }
}

function formatDuration(months: number) {
  const value = Number(months || 0)
  if (value <= 0) return '-'
  if (value < 12) return `${value}个月`
  const years = Math.floor(value / 12)
  const rest = value % 12
  return rest ? `${years}年${rest}个月` : `${years}年`
}

onMounted(loadPatients)
</script>

<style scoped>
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.page-title { font-size: 28px; font-weight: 700; margin: 0; }
.page-subtitle { margin: 8px 0 0; color: var(--color-text-muted); font-size: 14px; }
.header-actions { display: flex; gap: 10px; }

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-text-color: #cbd5e1;
  --el-table-border-color: rgba(99,102,241,0.08);
  --el-table-row-hover-bg-color: rgba(99,102,241,0.06);
}

.diag-meta { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.diag-text {
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
