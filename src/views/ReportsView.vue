<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">报表管控</h2>
    </div>

    <div class="glass-card">
      <h3 style="margin-bottom: 16px;">患者列表 —— 点击生成诊断报告</h3>
      <el-table :data="patients" style="width: 100%" :header-cell-style="tableHeaderStyle">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="姓名" width="140" />
        <el-table-column prop="amputation_part" label="截肢部位" width="140" />
        <el-table-column prop="illness_duration_months" label="患病时长" width="120">
          <template #default="{ row }">{{ row.illness_duration_months }} 个月</template>
        </el-table-column>
        <el-table-column prop="last_report" label="上次报告" width="180" />
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button type="primary" size="small" :loading="row.generating" @click="generateReport(row)">
              <el-icon><Document /></el-icon>
              生成报告
            </el-button>
            <el-button
              v-if="row.report_url"
              type="success"
              size="small"
              @click="downloadReport(row)"
            >
              <el-icon><Download /></el-icon>
              下载 PDF
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 诊断结论弹窗 -->
    <el-dialog v-model="dialogVisible" title="AI 诊断结论" width="600">
      <div class="diag-dialog-content">
        <div class="diag-meta">
          <el-tag type="success" size="small">LLM 分析结果</el-tag>
          <span style="color: var(--color-text-muted); font-size: 13px;">患者：{{ currentPatient?.name }}</span>
        </div>
        <div class="diag-text">{{ currentDiagnostics }}</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { generateReport as apiGenerateReport } from '@/api/health'
import { useAuthStore } from '@/stores/auth'

const dialogVisible = ref(false)
const currentPatient = ref<any>(null)
const currentDiagnostics = ref('')

const tableHeaderStyle = {
  background: 'rgba(30, 41, 59, 0.8)',
  color: '#94a3b8',
  borderBottom: '1px solid rgba(99,102,241,0.1)',
}

const patients = ref([
  { id: 1, name: '张三', amputation_part: '左前臂', illness_duration_months: 18, last_report: '2026-03-20', generating: false, report_url: '' },
  { id: 2, name: '李四', amputation_part: '右手掌', illness_duration_months: 6, last_report: '2026-03-15', generating: false, report_url: '' },
  { id: 3, name: '王五', amputation_part: '左手掌', illness_duration_months: 24, last_report: '-', generating: false, report_url: '' },
])

async function generateReport(patient: any) {
  if (patient.generating) return // 防重复点击

  patient.generating = true
  // LLM 调用可能耗时 10-30s，提前告知用户
  const loadingMsg = ElMessage({
    message: `正在为 ${patient.name} 调用 AI 生成诊断报告，请稍候（约 10-30 秒）...`,
    type: 'info',
    duration: 0, // 手动关闭，不自动消失
  })

  try {
    // apiGenerateReport 内部已设置 user_id 为 Query 参数
    // health.ts 使用全局 request 实例（timeout: 30000），后端 LLM 可能超 30s
    // 因此此处直接调用，如遇超时用户重试即可（当前后端无 streaming 支持）
    const response = await apiGenerateReport(patient.id)

    patient.report_url = response.report_url
    patient.last_report = new Date().toISOString().slice(0, 10)
    currentPatient.value = patient
    currentDiagnostics.value = response.diagnostics
    dialogVisible.value = true

    ElMessage.success('报告生成完毕')
  } catch {
    // 全局拦截器已弹出错误，此处不重复弹
  } finally {
    loadingMsg.close()
    patient.generating = false
  }
}

// 方案 B: Blob 流下载 —— 带 Authorization Token，绕过 request.ts 响应拦截器
// request.ts 拦截器 return response.data 会破坏 Blob，必须用裸 axios 实例
async function downloadReport(patient: any) {
  const authStore = useAuthStore()
  const reportUrl = patient.report_url // 形如 "/download/report_user_1.pdf"

  const downloading = ElMessage({ message: '正在下载 PDF...', type: 'info', duration: 0 })
  try {
    const resp = await axios.get(`/api${reportUrl}`, {
      responseType: 'blob',
      headers: authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {},
    })

    const blob = new Blob([resp.data], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = reportUrl.split('/').pop() || 'report.pdf'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url) // 必须释放，否则内存泄漏
  } catch {
    ElMessage.error('PDF 下载失败，请检查网络或联系管理员')
  } finally {
    downloading.close()
  }
}
</script>

<style scoped>
.page-header { margin-bottom: 24px; }
.page-title { font-size: 28px; font-weight: 700; }

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-text-color: #cbd5e1;
  --el-table-border-color: rgba(99,102,241,0.08);
  --el-table-row-hover-bg-color: rgba(99,102,241,0.06);
}

.diag-dialog-content {}
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
