<template>
  <div>
    <h2 class="page-title gradient-text">数据初始化管理</h2>
    <p class="page-desc">快速初始化系统所需的种子数据，方便演示与测试。</p>

    <div class="seed-grid">
      <div v-for="entity in entities" :key="entity.key" class="glass-card seed-card">
        <div class="seed-header">
          <div class="seed-icon" :style="{ background: entity.gradient }">
            <el-icon :size="24"><component :is="entity.icon" /></el-icon>
          </div>
          <div>
            <h3 class="seed-title">{{ entity.title }}</h3>
            <p class="seed-desc">{{ entity.description }}</p>
          </div>
        </div>

        <div class="seed-status">
          <div class="status-row">
            <span class="status-label">当前记录数</span>
            <el-tag :type="entity.count > 0 ? 'success' : 'info'" size="small">
              {{ entity.count }} 条
            </el-tag>
          </div>
          <div class="status-row">
            <span class="status-label">状态</span>
            <span class="status-val" :class="entity.count > 0 ? 'initialized' : 'empty'">
              {{ entity.count > 0 ? '已初始化' : '未初始化' }}
            </span>
          </div>
        </div>

        <div class="seed-actions">
          <el-button type="primary" :loading="entity.loading" @click="seedEntity(entity)" :disabled="entity.count > 0">
            <el-icon><Upload /></el-icon> 初始化
          </el-button>
          <el-button type="danger" plain :loading="entity.resetting" @click="resetEntity(entity)" :disabled="entity.count === 0">
            <el-icon><RefreshRight /></el-icon> 重置
          </el-button>
        </div>
      </div>
    </div>

    <!-- 一键全部初始化 -->
    <div class="glass-card batch-card">
      <div style="display: flex; align-items: center; gap: 16px">
        <el-icon :size="24" style="color: var(--color-primary-light)"><SetUp /></el-icon>
        <div>
          <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 4px">批量操作</h3>
          <p style="color: var(--color-text-muted); font-size: 13px">一键初始化所有种子数据，或清空所有数据</p>
        </div>
      </div>
      <div style="display: flex; gap: 12px">
        <el-button type="primary" size="large" :loading="batchSeeding" @click="seedAll">
          一键初始化全部
        </el-button>
        <el-button type="danger" plain size="large" :loading="batchResetting" @click="resetAll">
          清空全部数据
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/utils/request'

interface SeedEntity {
  key: string; title: string; description: string; icon: string; gradient: string;
  count: number; loading: boolean; resetting: boolean;
}

const entities = reactive<SeedEntity[]>([
  {
    key: 'users', title: '用户数据', description: '创建示例患者账户（姓名、截肢部位、患病时长）',
    icon: 'User', gradient: 'linear-gradient(135deg, #6366f1, #818cf8)',
    count: 0, loading: false, resetting: false,
  },
  {
    key: 'devices', title: '设备数据', description: '创建示例 ESP32 设备（hardware_id、固件版本、电量）',
    icon: 'Cpu', gradient: 'linear-gradient(135deg, #06b6d4, #22d3ee)',
    count: 0, loading: false, resetting: false,
  },
  {
    key: 'health_logs', title: '健康日志', description: '生成近7天的模拟 RMS/侧压力数据',
    icon: 'TrendCharts', gradient: 'linear-gradient(135deg, #22c55e, #4ade80)',
    count: 0, loading: false, resetting: false,
  },
  {
    key: 'forum_posts', title: '论坛帖子', description: '创建示例帖子和评论内容',
    icon: 'ChatDotRound', gradient: 'linear-gradient(135deg, #f59e0b, #fbbf24)',
    count: 0, loading: false, resetting: false,
  },
  {
    key: 'training_sessions', title: '训练会话', description: '创建已完成的训练会话记录',
    icon: 'VideoCamera', gradient: 'linear-gradient(135deg, #ef4444, #f87171)',
    count: 0, loading: false, resetting: false,
  },
])

const batchSeeding = ref(false)
const batchResetting = ref(false)

// ── 种子数据定义 ──
const seedData: Record<string, any> = {
  users: [
    { name: '患者张三', amputation_part: '右手', illness_duration_months: 18 },
    { name: '患者李四', amputation_part: '左手', illness_duration_months: 24 },
    { name: '患者王五', amputation_part: '右前臂', illness_duration_months: 6 },
  ],
  devices: [
    { user_id: 1, hardware_id: 'ESP32-A7F3', battery_level: 78, firmware_version: 'v2.1.0' },
    { user_id: 2, hardware_id: 'ESP32-B1D9', battery_level: 45, firmware_version: 'v2.0.3' },
    { user_id: 3, hardware_id: 'ESP32-C4E2', battery_level: 92, firmware_version: 'v2.1.0' },
  ],
  health_logs: (() => {
    const logs: any[] = []
    const now = Date.now()
    for (let u = 1; u <= 3; u++) {
      for (let i = 0; i < 30; i++) {
        logs.push({
          user_id: u,
          rms_value: +(80 + Math.random() * 100).toFixed(2),
          side_pressure: +(25 + Math.random() * 50).toFixed(2),
          muscle_status_label: Math.random() > 0.7 ? '轻度萎缩' : '正常',
          created_at: new Date(now - (30 - i) * 3600000 * 6).toISOString(),
        })
      }
    }
    return logs
  })(),
  forum_posts: [
    { user_id: 1, title: '使用三个月心得分享', content: '用了假手三个月，现在可以独立打鸡蛋了！感谢团队的支持，康复训练真的很有效。坚持每天训练15分钟，进步真的很明显。', pinned: 0, hidden: 0 },
    { user_id: 2, title: '训练准确率提升经验', content: '今天进行了第15次个性化模式训练，识别准确率已经从最初的60%提升到了88%，非常激动！分享几个提高准确率的小技巧。', pinned: 1, hidden: 0 },
    { user_id: 3, title: '数据采集小技巧', content: '分享一个小技巧：在采集训练数据时，放松肌肉后再做动作，准确率会更高。另外，确保电极贴合皮肤非常重要。', pinned: 0, hidden: 0 },
    { user_id: 1, title: '假手充电注意事项', content: '提醒大家注意充电习惯：建议电量低于20%时充电，不要等完全没电。快充模式大约40分钟可以充满。', pinned: 0, hidden: 0 },
  ],
  training_sessions: [
    { session_id: 'sess_20260320_001', user_id: 1, raw_data_path: '/uploads/sess_20260320_001.dat', status: 'completed' },
    { session_id: 'sess_20260322_002', user_id: 1, raw_data_path: '/uploads/sess_20260322_002.dat', status: 'completed' },
    { session_id: 'sess_20260324_003', user_id: 2, raw_data_path: '/uploads/sess_20260324_003.dat', status: 'completed' },
    { session_id: 'sess_20260326_004', user_id: 2, raw_data_path: null, status: 'training' },
    { session_id: 'sess_20260327_005', user_id: 3, raw_data_path: '/uploads/sess_20260327_005.dat', status: 'completed' },
  ],
}

async function loadCounts() {
  try {
    const res: any = await request.get('/admin/seed/status')
    for (const e of entities) {
      if (res[e.key] !== undefined) e.count = res[e.key]
    }
  } catch {
    // 后端未提供此接口时，从 localStorage 读取
    for (const e of entities) {
      e.count = parseInt(localStorage.getItem(`seed_count_${e.key}`) || '0')
    }
  }
}

async function seedEntity(entity: SeedEntity) {
  entity.loading = true
  try {
    await request.post(`/admin/seed/${entity.key}`, seedData[entity.key])
    entity.count = seedData[entity.key].length
    localStorage.setItem(`seed_count_${entity.key}`, String(entity.count))
    ElMessage.success(`${entity.title} 初始化成功`)
  } catch {
    // 后端未提供接口，用 localStorage 模拟
    entity.count = seedData[entity.key].length
    localStorage.setItem(`seed_count_${entity.key}`, String(entity.count))
    ElMessage.success(`${entity.title} 初始化成功（本地模拟）`)
  } finally {
    entity.loading = false
  }
}

async function resetEntity(entity: SeedEntity) {
  try {
    await ElMessageBox.confirm(`确定要清空所有${entity.title}吗？此操作不可恢复。`, '确认重置', { type: 'warning' })
  } catch { return }

  entity.resetting = true
  try {
    await request.delete(`/admin/seed/${entity.key}`)
  } catch { /* 忽略后端错误 */ }
  entity.count = 0
  localStorage.setItem(`seed_count_${entity.key}`, '0')
  ElMessage.success(`${entity.title} 已清空`)
  entity.resetting = false
}

async function seedAll() {
  batchSeeding.value = true
  for (const entity of entities) {
    if (entity.count === 0) await seedEntity(entity)
  }
  batchSeeding.value = false
  ElMessage.success('全部初始化完成')
}

async function resetAll() {
  try {
    await ElMessageBox.confirm('确定要清空所有种子数据吗？此操作不可恢复。', '确认重置', { type: 'warning' })
  } catch { return }

  batchResetting.value = true
  for (const entity of entities) {
    if (entity.count > 0) {
      entity.resetting = true
      try { await request.delete(`/admin/seed/${entity.key}`) } catch { /* ignore */ }
      entity.count = 0
      localStorage.setItem(`seed_count_${entity.key}`, '0')
      entity.resetting = false
    }
  }
  batchResetting.value = false
  ElMessage.success('全部数据已清空')
}

onMounted(loadCounts)
</script>

<style scoped>
.page-title { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.page-desc { color: var(--color-text-muted); font-size: 14px; margin-bottom: 24px; }

.seed-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px; margin-bottom: 24px; }

.seed-card { display: flex; flex-direction: column; gap: 16px; }
.seed-header { display: flex; gap: 14px; align-items: flex-start; }
.seed-icon {
  width: 48px; height: 48px; border-radius: 12px; display: flex;
  align-items: center; justify-content: center; color: #fff; flex-shrink: 0;
}
.seed-title { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.seed-desc { font-size: 13px; color: var(--color-text-muted); line-height: 1.5; }

.seed-status { display: flex; flex-direction: column; gap: 8px; padding: 12px 0; border-top: 1px solid rgba(99,102,241,0.08); }
.status-row { display: flex; justify-content: space-between; align-items: center; }
.status-label { font-size: 13px; color: var(--color-text-muted); }
.status-val { font-size: 13px; font-weight: 600; }
.status-val.initialized { color: #22c55e; }
.status-val.empty { color: #64748b; }

.seed-actions { display: flex; gap: 8px; }

.batch-card {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;
}
</style>
