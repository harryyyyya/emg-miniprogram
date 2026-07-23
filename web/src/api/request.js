import request from '@/utils/request'

async function getPosts(params = {}) {
  try {
    return await request.get('/forum/posts', { params })
  } catch (error) {
    console.error('[Forum] getPosts failed:', error)
    throw error
  }
}

async function createPost(data) {
  try {
    return await request.post('/forum/posts', data)
  } catch (error) {
    console.error('[Forum] createPost failed:', error)
    throw error
  }
}

async function like(postId) {
  try {
    return await request.post('/forum/like', { post_id: postId })
  } catch (error) {
    console.error('[Forum] like failed:', error)
    throw error
  }
}

async function comment(postId, content, parentId = null) {
  try {
    return await request.post('/forum/comments', {
      post_id: postId,
      content,
      parent_id: parentId,
    })
  } catch (error) {
    console.error('[Forum] comment failed:', error)
    throw error
  }
}

async function getComments(postId, page = 1, pageSize = 20) {
  try {
    return await request.get('/forum/comments', {
      params: {
        post_id: postId,
        page,
        pageSize,
      },
    })
  } catch (error) {
    console.error('[Forum] getComments failed:', error)
    throw error
  }
}

async function updatePost(postId, data) {
  try {
    return await request.put(`/forum/posts/${postId}`, data)
  } catch (error) {
    console.error('[Forum] updatePost failed:', error)
    throw error
  }
}

async function deletePost(postId) {
  try {
    return await request.delete(`/forum/posts/${postId}`)
  } catch (error) {
    console.error('[Forum] deletePost failed:', error)
    throw error
  }
}

export const Forum = {
  getPosts,
  createPost,
  like,
  comment,
  getComments,
  updatePost,
  deletePost,
}

export default {
  Forum,
}
