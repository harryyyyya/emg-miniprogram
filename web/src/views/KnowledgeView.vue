<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title gradient-text">官方知识库</h2>
        <p class="page-subtitle">这里发布的文章会同步显示到小程序首页“康复与训练”。新发布文章默认排在最前面。</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadArticles">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          发布文章
        </el-button>
      </div>
    </div>

    <div class="kb-grid" v-loading="loading">
      <div v-for="article in articles" :key="article.id" class="glass-card kb-card">
        <div class="kb-cover" v-if="webCover(article.cover_url)">
          <img :src="webCover(article.cover_url)" alt="" />
        </div>
        <div class="kb-tag-row">
          <el-tag :type="tagType(article.type)" size="small">{{ typeLabel(article.type) }}</el-tag>
          <span class="kb-date">{{ article.date }}</span>
        </div>
        <h3 class="kb-title">{{ article.title }}</h3>
        <p class="kb-excerpt">{{ article.summary || article.content || '暂无摘要' }}</p>
        <div class="kb-footer">
          <el-switch
            v-model="article.is_published"
            inline-prompt
            active-text="已发布"
            inactive-text="草稿"
            @change="togglePublish(article)"
          />
          <div class="kb-actions">
            <el-button type="primary" text size="small" @click="openEdit(article)">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <el-button type="danger" text size="small" @click="deleteArticle(article)">
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </div>
        </div>
      </div>

      <el-empty v-if="!loading && articles.length === 0" description="暂无文章，点击右上角发布第一篇" />
    </div>

    <el-dialog v-model="showEditor" :title="editingId ? '编辑知识库文章' : '发布知识库文章'" width="860">
      <el-form label-position="top">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="例如：动作录入怎么练更稳定" />
        </el-form-item>

        <div class="form-row">
          <el-form-item label="分类">
            <el-select v-model="form.type" style="width: 220px">
              <el-option label="使用指南" value="guide" />
              <el-option label="设备连接" value="connection" />
              <el-option label="训练建议" value="training" />
              <el-option label="心理支持" value="mental" />
              <el-option label="版本更新" value="update" />
            </el-select>
          </el-form-item>
          <el-form-item label="显示风格">
            <el-select v-model="form.theme" style="width: 180px">
              <el-option label="默认" value="" />
              <el-option label="暖色心理支持" value="warm" />
            </el-select>
          </el-form-item>
          <el-form-item label="排序">
            <el-input-number v-model="form.sort_order" :min="0" :max="999" />
          </el-form-item>
          <el-form-item label="发布状态">
            <el-switch v-model="form.is_published" active-text="发布" inactive-text="草稿" />
          </el-form-item>
        </div>

        <el-form-item label="封面图片">
          <div class="cover-editor">
            <el-upload
              action="#"
              :show-file-list="false"
              :auto-upload="false"
              accept="image/*"
              :on-change="uploadCover"
            >
              <el-button :loading="uploadingCover">上传本地图片</el-button>
            </el-upload>
            <el-input v-model="form.cover_url" placeholder="也可以粘贴 https://... 或 /static/images/... 图片地址" />
          </div>
          <div class="cover-preview" v-if="webCover(form.cover_url)">
            <img :src="webCover(form.cover_url)" alt="" />
          </div>
        </el-form-item>

        <el-form-item label="首页摘要">
          <el-input v-model="form.summary" type="textarea" :rows="3" placeholder="这段会显示在小程序首页文章卡片上" />
        </el-form-item>

        <el-form-item label="正文内容">
          <el-input v-model="form.content" type="textarea" :rows="7" placeholder="网页端正文。支持换行，小程序如果没有填写下面的分段，会按换行自动展示。" />
        </el-form-item>

        <div class="format-editor">
          <div class="format-head">
            <div>
              <h3>小程序详情格式</h3>
              <p>每个分段会显示为一个标题和多个要点，更适合手机阅读。</p>
            </div>
            <el-button @click="addSection">
              <el-icon><Plus /></el-icon>
              添加分段
            </el-button>
          </div>

          <div v-for="(section, sectionIndex) in form.sections" :key="sectionIndex" class="section-editor">
            <div class="section-editor-head">
              <el-input v-model="section.heading" placeholder="分段标题，例如：1. 录入前准备" />
              <el-button type="danger" text @click="removeSection(sectionIndex)">删除分段</el-button>
            </div>
            <div v-for="(item, itemIndex) in section.items" :key="`${sectionIndex}-${itemIndex}-${item}`" class="point-row">
              <el-input v-model="section.items[itemIndex]" placeholder="输入一个要点" />
              <el-button text type="danger" @click="removeSectionItem(sectionIndex, itemIndex)">删除</el-button>
            </div>
            <el-button text type="primary" @click="addSectionItem(sectionIndex)">添加要点</el-button>
          </div>
        </div>

        <div class="format-editor">
          <div class="format-head">
            <div>
              <h3>实用提醒</h3>
              <p>这些内容会显示在小程序文章底部。</p>
            </div>
            <el-button @click="addTip">
              <el-icon><Plus /></el-icon>
              添加提醒
            </el-button>
          </div>
          <div v-for="(tip, index) in form.tips" :key="`${index}-${tip}`" class="point-row">
            <el-input v-model="form.tips[index]" placeholder="输入一条提醒" />
            <el-button text type="danger" @click="removeTip(index)">删除</el-button>
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveArticle">
          {{ editingId ? '保存修改' : '发布' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Delete, Edit, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import request from '@/utils/request'

interface ArticleSection {
  heading: string
  items: string[]
}

interface Article {
  id: number
  type: string
  title: string
  summary: string
  content: string
  cover_url: string
  theme: string
  is_published: boolean
  sort_order: number
  date: string
  sections?: ArticleSection[]
  tips?: string[]
}

const loading = ref(false)
const saving = ref(false)
const uploadingCover = ref(false)
const showEditor = ref(false)
const editingId = ref<number | null>(null)
const articles = ref<Article[]>([])

const form = reactive({
  title: '',
  type: 'guide',
  summary: '',
  content: '',
  cover_url: '',
  theme: '',
  is_published: true,
  sort_order: 0,
  sections: [] as ArticleSection[],
  tips: [] as string[],
})

function resetForm() {
  editingId.value = null
  form.title = ''
  form.type = 'guide'
  form.summary = ''
  form.content = ''
  form.cover_url = ''
  form.theme = ''
  form.is_published = true
  form.sort_order = 0
  form.sections = [{ heading: '正文', items: [''] }]
  form.tips = []
}

async function loadArticles() {
  loading.value = true
  try {
    articles.value = await request.get('/knowledge/articles?published=all&limit=200') as Article[]
  } finally {
    loading.value = false
  }
}

function openCreate() {
  resetForm()
  showEditor.value = true
}

function openEdit(article: Article) {
  editingId.value = article.id
  form.title = article.title
  form.type = article.type || 'guide'
  form.summary = article.summary || ''
  form.content = article.content || ''
  form.cover_url = article.cover_url || ''
  form.theme = article.theme || ''
  form.is_published = article.is_published
  form.sort_order = article.sort_order || 0
  form.sections = normalizeSections(article.sections, article.content)
  form.tips = Array.isArray(article.tips) ? [...article.tips] : []
  showEditor.value = true
}

async function uploadCover(file: UploadFile) {
  if (!file.raw) return
  uploadingCover.value = true
  try {
    const data = new FormData()
    data.append('file', file.raw)
    const res = await request.post('/upload/image', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }) as { url?: string; image_url?: string }
    form.cover_url = res.url || res.image_url || ''
    ElMessage.success('封面上传成功')
  } finally {
    uploadingCover.value = false
  }
}

async function saveArticle() {
  if (!form.title.trim()) return ElMessage.warning('请填写文章标题')
  if (!form.summary.trim()) return ElMessage.warning('请填写首页摘要')
  if (!form.content.trim() && !cleanSections(form.sections).length) {
    return ElMessage.warning('请填写正文内容或小程序详情格式')
  }

  saving.value = true
  try {
    const payload = {
      title: form.title,
      type: form.type,
      summary: form.summary,
      content: form.content,
      cover_url: form.cover_url,
      theme: form.theme,
      is_published: form.is_published,
      sort_order: form.sort_order,
      sections: cleanSections(form.sections),
      tips: form.tips.map(item => item.trim()).filter(Boolean),
    }
    if (editingId.value) {
      await request.put(`/knowledge/articles/${editingId.value}`, payload)
      ElMessage.success('文章已更新，小程序会同步显示')
    } else {
      await request.post('/knowledge/articles', payload)
      ElMessage.success('发布成功，小程序会同步显示在首页靠前位置')
    }
    showEditor.value = false
    await loadArticles()
  } finally {
    saving.value = false
  }
}

async function togglePublish(article: Article) {
  await request.put(`/knowledge/articles/${article.id}`, {
    title: article.title,
    type: article.type,
    summary: article.summary,
    content: article.content,
    cover_url: article.cover_url,
    theme: article.theme,
    is_published: article.is_published,
    sort_order: article.sort_order,
    sections: article.sections || [],
    tips: article.tips || [],
  })
  ElMessage.success(article.is_published ? '文章已发布' : '文章已下架')
}

async function deleteArticle(article: Article) {
  await ElMessageBox.confirm(`确定删除《${article.title}》吗？删除后小程序也不会再显示。`, '删除文章', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await request.delete(`/knowledge/articles/${article.id}`)
  ElMessage.success('文章已删除')
  await loadArticles()
}

function addSection() {
  form.sections.push({ heading: '', items: [''] })
}

function removeSection(index: number) {
  form.sections.splice(index, 1)
}

function addSectionItem(sectionIndex: number) {
  form.sections[sectionIndex].items.push('')
}

function removeSectionItem(sectionIndex: number, itemIndex: number) {
  form.sections[sectionIndex].items.splice(itemIndex, 1)
}

function addTip() {
  form.tips.push('')
}

function removeTip(index: number) {
  form.tips.splice(index, 1)
}

function normalizeSections(sections: ArticleSection[] | undefined, content = '') {
  if (Array.isArray(sections) && sections.length) {
    return sections.map(section => ({
      heading: section.heading || '',
      items: Array.isArray(section.items) && section.items.length ? [...section.items] : [''],
    }))
  }
  const items = content.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  return [{ heading: '正文', items: items.length ? items : [''] }]
}

function cleanSections(sections: ArticleSection[]) {
  return sections
    .map(section => ({
      heading: section.heading.trim() || '正文',
      items: section.items.map(item => item.trim()).filter(Boolean),
    }))
    .filter(section => section.items.length)
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    guide: '使用指南',
    connection: '设备连接',
    training: '训练建议',
    mental: '心理支持',
    update: '版本更新',
  }
  return labels[type] || '使用指南'
}

function tagType(type: string) {
  if (type === 'update') return 'primary'
  if (type === 'mental') return 'warning'
  if (type === 'connection') return 'info'
  return 'success'
}

function webCover(url: string) {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/static/')) return url
  return ''
}

onMounted(loadArticles)
</script>

<style scoped>
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.page-title { font-size: 28px; font-weight: 700; margin: 0; }
.page-subtitle { margin: 8px 0 0; color: var(--color-text-muted); font-size: 14px; }
.header-actions { display: flex; gap: 10px; }

.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; min-height: 180px; }
.kb-card { display: flex; flex-direction: column; overflow: hidden; }
.kb-cover { height: 128px; margin: -4px -4px 16px; border-radius: 16px; overflow: hidden; background: rgba(148, 163, 184, 0.12); }
.kb-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.kb-tag-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.kb-date { font-size: 12px; color: var(--color-text-muted); }
.kb-title { font-size: 18px; font-weight: 600; margin: 0 0 8px; }
.kb-excerpt { font-size: 14px; color: var(--color-text-muted); line-height: 1.7; flex: 1; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.kb-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(148, 163, 184, 0.16); }
.kb-actions { display: flex; align-items: center; gap: 4px; }
.form-row { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }

.cover-editor { display: grid; grid-template-columns: auto 1fr; gap: 12px; width: 100%; align-items: center; }
.cover-preview { margin-top: 12px; width: 240px; height: 120px; border-radius: 16px; overflow: hidden; background: rgba(148, 163, 184, 0.12); }
.cover-preview img { width: 100%; height: 100%; object-fit: cover; display: block; }

.format-editor { margin: 18px 0; padding: 16px; border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 18px; background: rgba(15, 23, 42, 0.28); }
.format-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 14px; }
.format-head h3 { margin: 0 0 6px; font-size: 16px; }
.format-head p { margin: 0; color: var(--color-text-muted); font-size: 13px; }
.section-editor { padding: 14px; border-radius: 14px; background: rgba(255, 255, 255, 0.04); margin-bottom: 12px; }
.section-editor-head { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-bottom: 10px; }
.point-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-bottom: 10px; }
</style>
