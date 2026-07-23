<template>
  <div :style="`padding-left: ${indent}px; margin-top: 8px;`">
    <div v-if="post._orphan" class="orphan-notice">
      <el-icon :size="14"><Warning /></el-icon>
      <span>原帖已被管理员删除/隐藏，以下为该帖回复内容</span>
    </div>

    <div class="reply-item" :class="{ 'reply-hidden': post.hidden }">
      <el-avatar :size="24" style="flex-shrink: 0;">{{ displayName[0] }}</el-avatar>
      <div class="reply-body">
        <span class="reply-author">{{ displayName }}</span>
        <span v-if="post.hidden" class="reply-text muted-italic">（该回复已被管理员隐藏）</span>
        <span v-else class="reply-text">{{ post.content }}</span>
        <span class="reply-time">{{ timeStr }}</span>
      </div>
      <div class="reply-actions">
        <el-button text size="small" @click="$emit('toggle-hide', post)">
          <el-icon><Hide /></el-icon>
        </el-button>
        <el-button text size="small" style="color: #ef4444;" @click="$emit('confirm-delete', post)">
          删
        </el-button>
      </div>
    </div>

    <!-- 递归子回复 -->
    <ReplyNode
      v-for="child in post.replies"
      :key="child.id"
      :post="child"
      :depth="depth + 1"
      @toggle-hide="(p) => $emit('toggle-hide', p)"
      @confirm-delete="(p) => $emit('confirm-delete', p)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Warning, Hide } from '@element-plus/icons-vue'
import type { TreePostEx } from './ForumView.vue'

// Recursive self-reference: Vue SFC supports naming via 'name' option
defineOptions({ name: 'ReplyNode' })

const props = defineProps<{
  post: TreePostEx
  depth: number
}>()

defineEmits<{
  'toggle-hide': [post: TreePostEx]
  'confirm-delete': [post: TreePostEx]
}>()

const indent = computed(() => Math.min(props.depth, 3) * 20)
const displayName = computed(() => props.post.author_name || `用户 #${props.post.user_id}`)
const timeStr = computed(() => props.post.created_at?.slice(0, 16).replace('T', ' ') ?? '')
</script>
