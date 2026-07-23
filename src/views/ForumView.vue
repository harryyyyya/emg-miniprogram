<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">社区内容管理</h2>
      <div class="header-actions">
        <el-input
          v-model="searchText"
          placeholder="搜索帖子..."
          prefix-icon="Search"
          clearable
          style="width: 260px;"
          @input="onSearch"
        />
      </div>
    </div>

    <!-- 加载骨架 -->
    <div v-if="loading" class="post-list">
      <div v-for="n in 3" :key="n" class="glass-card" style="padding: 24px;">
        <el-skeleton :rows="3" animated />
      </div>
    </div>

    <!-- 帖子列表 -->
    <div v-else class="post-list">
      <div
        v-for="post in filteredRoots"
        :key="post.id"
        class="glass-card post-card"
        :class="{ 'post-hidden': post.hidden }"
      >
        <!-- 主帖头部 -->
        <div class="post-header">
          <div class="post-author">
            <el-avatar :size="36" class="avatar-glow">
              {{ displayName(post)[0] }}
            </el-avatar>
            <div>
              <span class="author-name">{{ displayName(post) }}</span>
              <span class="post-time">{{ post.created_at?.slice(0, 16).replace('T', ' ') }}</span>
            </div>
          </div>
          <div class="post-actions">
            <el-tag v-if="post.pinned" type="warning" size="small">置顶</el-tag>
            <el-tag v-if="post.hidden" type="info" size="small">已隐藏</el-tag>
            <el-dropdown trigger="click">
              <el-button text size="small">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="togglePin(post)">
                    {{ post.pinned ? '取消置顶' : '置顶' }}
                  </el-dropdown-item>
                  <el-dropdown-item @click="toggleHide(post)">
                    {{ post.hidden ? '恢复显示' : '隐藏' }}
                  </el-dropdown-item>
                  <el-dropdown-item @click="confirmDelete(post)" style="color: #ef4444;">
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <!-- 主帖内容（hidden 时显示占位） -->
        <template v-if="!post.hidden">
          <h3 class="post-title">{{ post.title }}</h3>
          <p class="post-content">{{ post.content }}</p>
        </template>
        <div v-else class="hidden-placeholder">
          <el-icon :size="16"><Warning /></el-icon>
          <span>该内容已被管理员隐藏</span>
        </div>

        <!-- 回复树（递归） -->
        <div v-if="post.replies.length" class="replies-section">
          <div class="reply-divider">
            <span>{{ countReplies(post) }} 条回复</span>
          </div>
          <ReplyNode
            v-for="reply in post.replies"
            :key="reply.id"
            :post="reply"
            :depth="1"
            @toggle-hide="toggleHide"
            @confirm-delete="confirmDelete"
          />
        </div>
      </div>

      <div v-if="filteredRoots.length === 0" class="empty-state">
        <el-empty description="暂无帖子" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Warning, MoreFilled } from '@element-plus/icons-vue'
import ReplyNode from './ReplyNode.vue'
import {
  fetchPosts,
  updatePost,
  deletePost as apiDeletePost,
  buildPostTree,
} from '@/api/forum'
import type { TreePost } from '@/api/forum'

// TreePostEx: 运行时扩展 _orphan 标记，也导出供 ReplyNode.vue 使用
export type TreePostEx = TreePost & { _orphan?: boolean; replies: TreePostEx[] }

// ── 页面状态 ─────────────────────────────────────────────────────
const searchText = ref('')
const loading = ref(false)
const rootPosts = ref<TreePostEx[]>([])

function displayName(post: TreePost) {
  return post.author_name || `用户 #${post.user_id}`
}

function countReplies(post: TreePost): number {
  return post.replies.reduce((sum, r) => sum + 1 + countReplies(r), 0)
}

// ── 数据加载 ─────────────────────────────────────────────────────
async function loadPosts(search?: string) {
  loading.value = true
  try {
    const flat = await fetchPosts(search ? { search } : undefined)

    // 标记孤儿节点（parent_id 非空但父节点不在结果集中）
    const idSet = new Set(flat.map((p) => p.id))
    const markedFlat = flat.map((p) => ({
      ...p,
      _orphan: p.parent_id !== null && !idSet.has(p.parent_id),
    }))

    rootPosts.value = buildPostTree(markedFlat) as TreePostEx[]
  } catch {
    // 全局拦截器已弹出错误
  } finally {
    loading.value = false
  }
}

// 防抖搜索（300ms）
let searchTimer: ReturnType<typeof setTimeout>
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadPosts(searchText.value || undefined), 300)
}

const filteredRoots = computed(() => rootPosts.value)

onMounted(() => loadPosts())

// ── 置顶（乐观更新） ─────────────────────────────────────────────
async function togglePin(post: TreePostEx) {
  const prev = post.pinned
  post.pinned = !post.pinned
  try {
    await updatePost(post.id, { pinned: post.pinned })
    ElMessage.success(post.pinned ? '已置顶' : '已取消置顶')
  } catch {
    post.pinned = prev
  }
}

// ── 隐藏（乐观更新） ─────────────────────────────────────────────
async function toggleHide(post: TreePostEx) {
  const prev = post.hidden
  post.hidden = !post.hidden
  try {
    await updatePost(post.id, { hidden: post.hidden })
    ElMessage.success(post.hidden ? '已隐藏' : '已恢复显示')
  } catch {
    post.hidden = prev
  }
}

// ── 删除（二次确认 + 乐观移除） ──────────────────────────────────
async function confirmDelete(post: TreePostEx) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${post.title || '该回复'}」？此操作不可撤销，其子回复将变为孤儿节点。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return
  }

  const removed = removeNodeFromTree(rootPosts.value, post.id)
  if (!removed) return

  try {
    await apiDeletePost(post.id)
    ElMessage.success('已删除')
  } catch {
    ElMessage.warning('删除失败，正在恢复数据...')
    await loadPosts()
  }
}

function removeNodeFromTree(nodes: TreePostEx[], id: number): TreePostEx | null {
  for (let i = 0; i < nodes.length; i++) {
    if (nodes[i].id === id) return nodes.splice(i, 1)[0]
    const found = removeNodeFromTree(nodes[i].replies, id)
    if (found) return found
  }
  return null
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
.page-title { font-size: 28px; font-weight: 700; }
.header-actions { display: flex; gap: 12px; }

.post-list { display: flex; flex-direction: column; gap: 16px; }
.post-card { position: relative; transition: opacity 0.2s; }
.post-card.post-hidden { opacity: 0.55; }

.post-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.post-author { display: flex; align-items: center; gap: 10px; }
.author-name { font-weight: 600; font-size: 15px; display: block; }
.post-time { font-size: 12px; color: var(--color-text-muted); display: block; }
.post-actions { display: flex; align-items: center; gap: 8px; }
.avatar-glow { background: linear-gradient(135deg, var(--color-primary), var(--color-accent)); font-weight: 600; color: #fff; }

.post-title { font-size: 17px; font-weight: 600; margin-bottom: 8px; }
.post-content { font-size: 14px; color: var(--color-text-muted); line-height: 1.7; }

/* 隐藏帖子的内联占位（不用绝对遮罩，保留操作按钮可见） */
.hidden-placeholder {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--color-text-muted);
  padding: 8px 0; font-style: italic;
}

/* 孤儿节点提示 */
.orphan-notice {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #f59e0b;
  padding: 4px 0; margin-bottom: 4px;
}

/* 回复区 */
.replies-section { margin-top: 16px; }
.reply-divider { padding: 8px 0; border-top: 1px solid rgba(99,102,241,0.1); font-size: 13px; color: var(--color-text-muted); margin-bottom: 4px; }

/* ReplyNode 内部样式（全局，因为是 h() 渲染函数生成） */
</style>

<!-- ReplyNode 使用 h() 渲染函数，样式无法 scoped；用全局补充 -->
<style>
.reply-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 0; border-bottom: 1px solid rgba(99,102,241,0.05);
  transition: opacity 0.2s;
}
.reply-item.reply-hidden { opacity: 0.45; }
.reply-body { flex: 1; min-width: 0; }
.reply-author { font-weight: 600; font-size: 13px; margin-right: 6px; }
.reply-text { font-size: 13px; color: #94a3b8; }
.reply-text.muted-italic { font-style: italic; }
.reply-time { font-size: 11px; color: #475569; margin-left: 8px; }
.reply-actions { display: flex; gap: 2px; flex-shrink: 0; }
</style>
