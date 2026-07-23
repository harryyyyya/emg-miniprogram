import { Forum } from '@/api/request.js'

export interface ForumPost {
  id: number
  user_id: number
  title?: string
  content: string
  parent_id: number | null
  created_at: string
  // 后端 JOIN 返回的扩展字段
  author_name?: string
  pinned?: boolean
  hidden?: boolean
}

export interface TreePost extends ForumPost {
  replies: TreePost[]
}

// 获取帖子列表 (含分页和搜索)
export async function fetchPosts(params?: { page?: number; search?: string }) {
  const res = await Forum.getPosts(params) as any
  return (Array.isArray(res) ? res : (res.posts || [])) as ForumPost[]
}

// 更新帖子状态 (置顶/隐藏)
export async function updatePost(postId: number, data: { pinned?: boolean; hidden?: boolean }) {
  return await Forum.updatePost(postId, data) as ForumPost
}

// 删除帖子
export async function deletePost(postId: number) {
  return await Forum.deletePost(postId) as { msg: string }
}

// 工具函数：将平面帖子数组转为树状结构
export function buildPostTree(flatPosts: ForumPost[]): TreePost[] {
  const map = new Map<number, TreePost>()
  const roots: TreePost[] = []

  for (const post of flatPosts) {
    map.set(post.id, { ...post, replies: [] })
  }

  for (const post of flatPosts) {
    const node = map.get(post.id)!
    if (post.parent_id === null) {
      roots.push(node)
    } else {
      const parent = map.get(post.parent_id)
      if (parent) parent.replies.push(node)
    }
  }

  return roots
}
