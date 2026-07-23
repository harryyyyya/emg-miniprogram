<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">知识库</h2>
      <el-input v-model="searchText" placeholder="搜索文章..." prefix-icon="Search" clearable style="width: 260px" />
    </div>

    <div class="kb-grid" v-loading="loading">
      <div v-for="article in filteredArticles" :key="article.id" class="glass-card kb-card" @click="openArticle(article)">
        <div class="kb-cover" v-if="webCover(article.cover_url)">
          <img :src="webCover(article.cover_url)" alt="" />
        </div>
        <div class="kb-tag-row">
          <el-tag :type="tagType(article.type)" size="small">{{ typeLabel(article.type) }}</el-tag>
          <span class="kb-date">{{ article.date }}</span>
        </div>
        <h3 class="kb-title">{{ article.title }}</h3>
        <p class="kb-excerpt">{{ article.summary || article.content || '暂无摘要' }}</p>
        <span class="kb-read-more">阅读全文 →</span>
      </div>

      <el-empty v-if="!loading && filteredArticles.length === 0" description="暂无相关文章" />
    </div>

    <el-dialog
      v-model="showDetail"
      :title="currentArticle?.title || ''"
      width="740"
      top="5vh"
      class="article-dialog"
      :close-on-click-modal="true"
      destroy-on-close
    >
      <div class="article-detail" v-if="currentArticle">
        <div class="article-meta">
          <el-tag :type="tagType(currentArticle.type)" size="small">{{ typeLabel(currentArticle.type) }}</el-tag>
          <span class="article-date">{{ currentArticle.date }}</span>
        </div>
        <p class="article-summary">{{ currentArticle.summary }}</p>
        <div class="article-body">{{ currentArticle.content }}</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import request from '@/utils/request'

const searchText = ref('')
const showDetail = ref(false)
const loading = ref(false)

interface Article {
  id: number
  type: string
  title: string
  summary: string
  content: string
  cover_url: string
  date: string
}

const currentArticle = ref<Article | null>(null)
const articles = ref<Article[]>([])

const filteredArticles = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return articles.value
  return articles.value.filter((article) => {
    return article.title.toLowerCase().includes(kw)
      || (article.summary || '').toLowerCase().includes(kw)
      || (article.content || '').toLowerCase().includes(kw)
  })
})

async function loadArticles() {
  loading.value = true
  try {
    articles.value = await request.get('/knowledge/articles?published=true&limit=100') as Article[]
  } finally {
    loading.value = false
  }
}

function openArticle(article: Article) {
  currentArticle.value = article
  showDetail.value = true
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
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.page-title { font-size: 28px; font-weight: 700; }

.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; min-height: 180px; }
.kb-card {
  display: flex; flex-direction: column; cursor: pointer; overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}
.kb-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(99, 102, 241, 0.15);
}

.kb-cover { height: 128px; margin: -4px -4px 16px; border-radius: 16px; overflow: hidden; background: rgba(148, 163, 184, 0.12); }
.kb-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.kb-tag-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.kb-date { font-size: 12px; color: var(--color-text-muted); }
.kb-title { font-size: 18px; font-weight: 600; margin: 0 0 8px; }
.kb-excerpt { font-size: 14px; color: var(--color-text-muted); line-height: 1.7; flex: 1; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.kb-read-more { margin-top: 12px; color: var(--color-primary-light); font-size: 13px; font-weight: 500; }

.article-meta { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid rgba(99,102,241,0.1); }
.article-date { font-size: 13px; color: var(--color-text-muted); }
.article-summary { padding: 12px 14px; border-radius: 14px; background: rgba(99, 102, 241, 0.08); color: #cbd5e1; line-height: 1.75; }
.article-body { margin-top: 18px; font-size: 14px; line-height: 1.9; color: #e2e8f0; white-space: pre-wrap; }
</style>
