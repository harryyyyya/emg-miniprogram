declare module '@/api/request.js' {
  export interface ForumRequestApi {
    getPosts(params?: { page?: number; search?: string }): Promise<any>
    createPost(data: { title?: string; content: string; image_urls?: string[] }): Promise<any>
    like(postId: number): Promise<any>
    comment(postId: number, content: string, parentId?: number | null): Promise<any>
    getComments(postId: number, page?: number, pageSize?: number): Promise<any>
    updatePost(postId: number, data: { pinned?: boolean; hidden?: boolean }): Promise<any>
    deletePost(postId: number): Promise<any>
  }

  export const Forum: ForumRequestApi
  const _default: { Forum: ForumRequestApi }
  export default _default
}
