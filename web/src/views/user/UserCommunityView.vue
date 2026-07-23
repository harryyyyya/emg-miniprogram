<template>
  <div class="community-page">
    <div class="page-header">
      <h2 class="page-title gradient-text">社区交流</h2>
      <div class="header-actions">
        <el-input v-model="searchText" placeholder="搜索帖子..." prefix-icon="Search" clearable style="width: 260px" @input="onSearch" />
        <el-button type="primary" @click="showPublish = true">
          <el-icon><Plus /></el-icon> 发帖
        </el-button>
      </div>
    </div>

    <!-- 帖子列表 -->
    <div v-if="loading" class="post-list">
      <div v-for="n in 3" :key="n" class="glass-card" style="padding: 24px"><el-skeleton :rows="3" animated /></div>
    </div>

    <div v-else class="post-list">
      <div v-for="post in posts" :key="post.id" class="glass-card post-card">
        <!-- 帖子头部 -->
        <div class="post-top">
          <div class="post-author">
            <el-avatar :size="40" class="avatar-glow">{{ (post.author_name || '匿')[0] }}</el-avatar>
            <div>
              <span class="author-name">{{ post.author_name || '匿名用户' }}</span>
              <span class="post-time">{{ post.created_at || '' }}</span>
            </div>
          </div>
        </div>

        <!-- 帖子内容 -->
        <p class="post-content">{{ post.content }}</p>

        <!-- 图片区域 -->
        <div v-if="post.image_urls && post.image_urls.length" class="post-images">
          <el-image
            v-for="(img, i) in post.image_urls" :key="i"
            :src="img" fit="cover" class="post-img"
            :preview-src-list="post.image_urls" :initial-index="i"
          />
        </div>

        <!-- 操作栏 -->
        <div class="post-actions">
          <button class="action-btn" :class="{ liked: post.liked }" @click="handleLike(post)">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" :fill="post.liked ? '#ef4444' : 'none'" :stroke="post.liked ? '#ef4444' : 'currentColor'" />
            </svg>
            <span>{{ post.like_count || 0 }}</span>
          </button>
          <button class="action-btn" @click="openComments(post)">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span>{{ post.comment_count || 0 }}</span>
          </button>
        </div>
      </div>

      <div v-if="posts.length === 0" class="empty-state">
        <el-empty description="暂无帖子，快来发第一篇吧！" />
      </div>

      <!-- 加载更多 -->
      <div v-if="!noMore && posts.length > 0" class="load-more">
        <el-button text :loading="loadingMore" @click="loadMore">加载更多</el-button>
      </div>
    </div>

    <!-- 发帖弹窗 -->
    <el-dialog v-model="showPublish" title="发布新帖" width="560" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="内容">
          <el-input v-model="newPostContent" type="textarea" :rows="5" placeholder="分享你的康复经验、使用心得..." maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="图片（可选，最多9张）">
          <el-upload
            list-type="picture-card" :auto-upload="false"
            v-model:file-list="newPostImages" :limit="9"
            accept="image/*"
          >
            <el-icon><Plus /></el-icon>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPublish = false">取消</el-button>
        <el-button type="primary" :loading="publishing" @click="submitPost">发布</el-button>
      </template>
    </el-dialog>

    <!-- 评论抽屉 -->
    <el-drawer v-model="showComments" title="评论" size="420px" :with-header="true">
      <div class="comment-list">
        <div v-for="c in comments" :key="c.id" class="comment-item">
          <el-avatar :size="32" class="comment-avatar">{{ (c.author_name || '匿')[0] }}</el-avatar>
          <div class="comment-body">
            <div class="comment-meta">
              <span class="comment-author">{{ c.author_name || '匿名' }}</span>
              <span class="comment-time">{{ c.created_at || '' }}</span>
            </div>
            <p class="comment-text">{{ c.content }}</p>
          </div>
        </div>
        <div v-if="comments.length === 0 && !commentLoading" class="comment-empty">暂无评论</div>
        <div v-if="!commentNoMore && comments.length > 0" class="load-more">
          <el-button text size="small" :loading="commentLoading" @click="loadMoreComments">加载更多</el-button>
        </div>
      </div>
      <div class="comment-input-bar">
        <el-input v-model="commentText" placeholder="写评论..." @keyup.enter="submitComment" />
        <el-button type="primary" :loading="commentSubmitting" @click="submitComment" :disabled="!commentText.trim()">发送</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Forum } from '@/api/request.js'

interface Post {
  id: number; author_name: string; author_avatar?: string; created_at: string;
  content: string; image_urls: string[]; like_count: number; comment_count: number; liked: boolean;
}
interface Comment {
  id: number; author_name: string; author_avatar?: string; created_at: string; content: string;
}

const searchText = ref('')
const loading = ref(false)
const loadingMore = ref(false)
const posts = ref<Post[]>([])
const page = ref(1)
const noMore = ref(false)

// ── 加载帖子 ──
async function loadPosts(reset = false) {
  if (reset) { page.value = 1; noMore.value = false }
  loading.value = reset
  loadingMore.value = !reset
  try {
    const params: any = { page: page.value }
    if (searchText.value) params.search = searchText.value
    const res = await Forum.getPosts(params)
    const list: Post[] = (res.posts || res || []).map((p: any) => ({
      ...p,
      image_urls: p.image_urls || [],
      like_count: p.like_count || 0,
      comment_count: p.comment_count || 0,
      liked: p.liked || false,
    }))
    posts.value = reset ? list : [...posts.value, ...list]
    if (list.length < 15) noMore.value = true
    page.value++
  } catch {
    if (reset) {
      posts.value = mockPosts()
      noMore.value = true
    }
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function loadMore() { loadPosts(false) }

let searchTimer: ReturnType<typeof setTimeout>
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadPosts(true), 300)
}

function mockPosts(): Post[] {
  return [
    { id: 1, author_name: '张先生', created_at: '2小时前', content: '用了假手三个月，现在可以独立打鸡蛋了！感谢团队的支持，康复训练真的很有效。', image_urls: [], like_count: 24, comment_count: 8, liked: false },
    { id: 2, author_name: '李阿姨', created_at: '昨天', content: '今天进行了第15次个性化模式训练，识别准确率已经从最初的60%提升到了88%，非常激动！', image_urls: [], like_count: 47, comment_count: 12, liked: false },
    { id: 3, author_name: '王小明', created_at: '3天前', content: '分享一个小技巧：在采集训练数据时，放松肌肉后再做动作，准确率会更高。', image_urls: [], like_count: 33, comment_count: 5, liked: false },
    { id: 4, author_name: '赵医生', created_at: '5天前', content: '各位患者朋友，建议每天的训练不要超过30分钟，循序渐进效果更好。有任何问题可以在这里交流。', image_urls: [], like_count: 56, comment_count: 18, liked: false },
  ]
}

// ── 点赞 ──
function handleLike(post: Post) {
  post.liked = !post.liked
  post.like_count += post.liked ? 1 : -1
  Forum.like(post.id).catch(() => {
    post.liked = !post.liked
    post.like_count += post.liked ? 1 : -1
  })
}

// ── 发帖 ──
const showPublish = ref(false)
const newPostContent = ref('')
const newPostImages = ref<any[]>([])
const publishing = ref(false)

async function submitPost() {
  if (!newPostContent.value.trim()) return ElMessage.warning('请输入内容')
  publishing.value = true
  try {
    await Forum.createPost({ content: newPostContent.value.trim(), image_urls: [] })
    ElMessage.success('发布成功')
    showPublish.value = false
    newPostContent.value = ''
    newPostImages.value = []
    loadPosts(true)
  } catch {
    ElMessage.error('发布失败，请重试')
  } finally {
    publishing.value = false
  }
}

// ── 评论 ──
const showComments = ref(false)
const currentPostId = ref<number | null>(null)
const comments = ref<Comment[]>([])
const commentPage = ref(1)
const commentNoMore = ref(false)
const commentLoading = ref(false)
const commentText = ref('')
const commentSubmitting = ref(false)

async function openComments(post: Post) {
  currentPostId.value = post.id
  comments.value = []
  commentPage.value = 1
  commentNoMore.value = false
  commentText.value = ''
  showComments.value = true
  await loadComments(post.id, 1)
}

async function loadComments(postId: number, pg: number) {
  commentLoading.value = true
  try {
    const res = await Forum.getComments(postId, pg, 20)
    const list: Comment[] = res.comments || res || []
    comments.value = pg === 1 ? list : [...comments.value, ...list]
    if (list.length < 20) commentNoMore.value = true
    commentPage.value = pg + 1
  } catch {
    if (pg === 1) {
      comments.value = [
        { id: 101, author_name: '赵医生', created_at: '10分钟前', content: '恢复得不错！继续保持训练频率。' },
        { id: 102, author_name: '康复志愿者', created_at: '1小时前', content: '我也有类似经历，坚持就是胜利！' },
      ]
      commentNoMore.value = true
    }
  } finally {
    commentLoading.value = false
  }
}

function loadMoreComments() {
  if (currentPostId.value) loadComments(currentPostId.value, commentPage.value)
}

async function submitComment() {
  if (!commentText.value.trim() || !currentPostId.value) return
  commentSubmitting.value = true
  try {
    await Forum.comment(currentPostId.value, commentText.value.trim())
    comments.value.push({
      id: Date.now(),
      author_name: '我',
      created_at: '刚刚',
      content: commentText.value.trim(),
    })
    // 更新帖子评论数
    const post = posts.value.find(p => p.id === currentPostId.value)
    if (post) post.comment_count++
    commentText.value = ''
  } catch {
    ElMessage.error('评论失败')
  } finally {
    commentSubmitting.value = false
  }
}

onMounted(() => loadPosts(true))
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
.page-title { font-size: 28px; font-weight: 700; }
.header-actions { display: flex; gap: 12px; }

.post-list { display: flex; flex-direction: column; gap: 16px; max-width: 680px; margin: 0 auto; }

.post-card { padding: 20px; transition: transform 0.2s; }
.post-card:hover { transform: translateY(-2px); }

.post-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.post-author { display: flex; align-items: center; gap: 10px; }
.avatar-glow { background: linear-gradient(135deg, var(--color-primary), var(--color-accent)); font-weight: 600; color: #fff; }
.author-name { font-weight: 600; font-size: 15px; display: block; }
.post-time { font-size: 12px; color: var(--color-text-muted); display: block; }

.post-content { font-size: 14px; color: var(--color-text); line-height: 1.75; margin-bottom: 12px; }

.post-images { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
.post-img { width: 100%; aspect-ratio: 1; border-radius: 8px; cursor: pointer; }

.post-actions { display: flex; gap: 24px; padding-top: 8px; border-top: 1px solid rgba(99,102,241,0.08); }
.action-btn {
  display: flex; align-items: center; gap: 6px; background: none; border: none;
  color: var(--color-text-muted); cursor: pointer; font-size: 13px; padding: 6px 0;
  transition: color 0.2s;
}
.action-btn:hover { color: var(--color-primary-light); }
.action-btn.liked { color: #ef4444; }

.load-more { text-align: center; padding: 16px; }

/* 评论抽屉 */
.comment-list { flex: 1; overflow-y: auto; padding-bottom: 80px; }
.comment-item { display: flex; gap: 10px; padding: 12px 0; border-bottom: 1px solid rgba(99,102,241,0.06); }
.comment-avatar { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-weight: 600; flex-shrink: 0; }
.comment-body { flex: 1; min-width: 0; }
.comment-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.comment-author { font-weight: 600; font-size: 13px; }
.comment-time { font-size: 11px; color: var(--color-text-muted); }
.comment-text { font-size: 13px; color: #cbd5e1; line-height: 1.6; }
.comment-empty { text-align: center; padding: 40px; color: var(--color-text-muted); font-size: 14px; }

.comment-input-bar {
  position: absolute; bottom: 0; left: 0; right: 0; display: flex; gap: 8px;
  padding: 12px 20px; background: rgba(15,23,42,0.95); border-top: 1px solid rgba(99,102,241,0.1);
  backdrop-filter: blur(12px);
}
</style>
