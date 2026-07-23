<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">官方知识库</h2>
      <el-button type="primary" @click="showEditor = true">
        <el-icon><Plus /></el-icon>
        发布文章
      </el-button>
    </div>

    <div class="kb-grid">
      <div v-for="article in articles" :key="article.id" class="glass-card kb-card">
        <div class="kb-tag-row">
          <el-tag :type="article.type === 'update' ? 'primary' : 'success'" size="small">
            {{ article.type === 'update' ? '版本更新' : '使用指南' }}
          </el-tag>
          <span class="kb-date">{{ article.date }}</span>
        </div>
        <h3 class="kb-title">{{ article.title }}</h3>
        <p class="kb-excerpt">{{ article.excerpt }}</p>
        <el-button type="primary" text size="small" class="kb-read-more">
          阅读全文 →
        </el-button>
      </div>
    </div>

    <!-- 发布文章弹窗 -->
    <el-dialog v-model="showEditor" title="发布知识库文章" width="640">
      <el-form label-position="top">
        <el-form-item label="标题">
          <el-input v-model="newArticle.title" placeholder="输入文章标题" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="newArticle.type">
            <el-radio value="update">版本更新</el-radio>
            <el-radio value="guide">使用指南</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="newArticle.content" type="textarea" :rows="8" placeholder="输入文章正文..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" @click="publishArticle">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'

const showEditor = ref(false)
const newArticle = reactive({ title: '', type: 'update', content: '' })

const articles = ref([
  {
    id: 1,
    type: 'update',
    title: '固件 v2.1.0 发布说明',
    excerpt: '本次更新优化了 BLE 连接的稳定性，新增自适应重连延迟策略 (Exponential Backoff)。同时修复了高负载场景下电机驱动 PID 控制器偶发过流保护误触的问题...',
    date: '2026-03-22',
  },
  {
    id: 2,
    type: 'guide',
    title: '新用户穿戴入门指南',
    excerpt: '欢迎使用 NeuroHand 肌电假手系统！本指南将帮助您了解设备的基本穿戴步骤、传感器安放位置以及初次校准流程...',
    date: '2026-03-20',
  },
  {
    id: 3,
    type: 'guide',
    title: '肌电信号训练最佳实践',
    excerpt: '为获得最佳的控制精度，建议新用户每日进行 3 次、每次 15 分钟的标准化握力训练。训练过程中注意保持前臂放松...',
    date: '2026-03-18',
  },
  {
    id: 4,
    type: 'update',
    title: '小程序 v1.5.0 更新日志',
    excerpt: '新增 AI 助手对话功能，优化了数据采集时的实时波形展示性能，修复了论坛页面在低版本微信基础库中的兼容性问题...',
    date: '2026-03-15',
  },
])

function publishArticle() {
  if (!newArticle.title || !newArticle.content) {
    return ElMessage.warning('请填写完整信息')
  }
  articles.value.unshift({
    id: Date.now(),
    type: newArticle.type,
    title: newArticle.title,
    excerpt: newArticle.content.slice(0, 120) + '...',
    date: new Date().toISOString().slice(0, 10),
  })
  showEditor.value = false
  newArticle.title = ''
  newArticle.content = ''
  ElMessage.success('发布成功')
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.page-title { font-size: 28px; font-weight: 700; }

.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }
.kb-card { display: flex; flex-direction: column; }
.kb-tag-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.kb-date { font-size: 12px; color: var(--color-text-muted); }
.kb-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.kb-excerpt { font-size: 14px; color: var(--color-text-muted); line-height: 1.7; flex: 1; }
.kb-read-more { margin-top: 12px; padding: 0; }
</style>
