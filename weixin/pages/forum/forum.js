const { Forum } = require('../../utils/request');

Page({
  data: {
    posts: [],
    page: 1,
    loading: false,
    noMore: false,
    userAvatar: '',
    currentUserId: null,

    showPublish: false,
    postContent: '',
    selectedImages: [],
    publishing: false,

    showComment: false,
    currentPostId: null,
    comments: [],
    commentPage: 1,
    commentTotal: 0,
    commentLoading: false,
    commentNoMore: false,
    commentText: '',
    commentSubmitting: false,
    commentInputFocus: false,
    replyParentId: null,
    replyTargetName: '',
    commentPlaceholder: '友善评论，一起交流康复经验',
  },

  onShow() {
    const app = getApp();
    const userInfo = wx.getStorageSync('userInfo') || app.globalData.userInfo || {};
    app.globalData.userInfo = userInfo;
    this.setData({
      userAvatar: userInfo.avatar_url || '/assets/icons/default_avatar.png',
      currentUserId: userInfo.id || null,
    });
    this._loadPosts(true);
    if (this.data.showComment && this.data.currentPostId) {
      this._loadComments(this.data.currentPostId, 1);
    }
  },

  onPullDownRefresh() {
    this._loadPosts(true).finally(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (this.data.showComment) return;
    if (!this.data.noMore && !this.data.loading) {
      this._loadPosts(false);
    }
  },

  stopTouchMove() {},

  onCommentScrollToLower() {
    this.loadMoreComments();
  },

  async _loadPosts(reset) {
    if (this.data.loading) return;
    const page = reset ? 1 : this.data.page;
    this.setData({ loading: true });
    try {
      const pageSize = 50;
      const res = await Forum.getPosts(page, pageSize);
      const newPosts = res.posts || [];
      this.setData({
        posts: reset ? newPosts : [...this.data.posts, ...newPosts],
        page: page + 1,
        noMore: newPosts.length < pageSize,
      });
    } catch {
      if (reset) {
        this.setData({ posts: this._mockPosts(), page: 2, noMore: true });
      }
    } finally {
      this.setData({ loading: false });
    }
  },

  _mockPosts() {
    return [
      {
        id: 1,
        author_name: '康复用户A',
        author_avatar: '/assets/icons/default_avatar.png',
        created_at: '2小时前',
        content: '最近训练效果不错，已经能更自然地完成一些简单抓握动作。',
        image_urls: [],
        like_count: 24,
        comment_count: 8,
        liked: false,
      },
      {
        id: 2,
        author_name: '康复用户B',
        author_avatar: '/assets/icons/default_avatar.png',
        created_at: '昨天',
        content: '今天做了新的模式训练，识别率比上周又高了一些。',
        image_urls: [],
        like_count: 47,
        comment_count: 12,
        liked: false,
      },
    ];
  },

  showPublish() {
    this.setData({ showPublish: true });
  },

  hidePublish() {
    this.setData({ showPublish: false, postContent: '', selectedImages: [] });
  },

  onContentInput(e) {
    this.setData({ postContent: e.detail.value });
  },

  removeImage(e) {
    const idx = e.currentTarget.dataset.idx;
    const images = [...this.data.selectedImages];
    images.splice(idx, 1);
    this.setData({ selectedImages: images });
  },

  pickImages() {
    const remain = 9 - this.data.selectedImages.length;
    wx.chooseMedia({
      count: remain,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const paths = res.tempFiles.map((file) => file.tempFilePath);
        this.setData({ selectedImages: [...this.data.selectedImages, ...paths] });
      },
    });
  },

  async submitPost() {
    const { postContent, selectedImages } = this.data;
    const content = postContent.trim();
    if (!content) return;

    this.setData({ publishing: true });
    try {
      const imageUrls = [];
      for (const path of selectedImages) {
        const url = await Forum.uploadImage(path);
        imageUrls.push(url);
      }
      await Forum.createPost(content, imageUrls);
      wx.showToast({ title: '发布成功', icon: 'success' });
      this.hidePublish();
      this._loadPosts(true);
    } catch {
      wx.showToast({ title: '发布失败，请重试', icon: 'none' });
    } finally {
      this.setData({ publishing: false });
    }
  },

  likePost(e) {
    const postId = e.currentTarget.dataset.id;
    if (!postId) return;

    const posts = [...this.data.posts];
    const post = posts.find((item) => item.id == postId);
    if (!post) return;

    post.liked = !post.liked;
    post.like_count = post.liked ? post.like_count + 1 : Math.max(0, post.like_count - 1);
    this.setData({ posts });

    Forum.like(postId).catch(() => {
      wx.showToast({ title: '网络异常', icon: 'none' });
    });
  },

  deletePost(e) {
    const postId = e.currentTarget.dataset.id;
    if (!postId) return;

    wx.showModal({
      title: '删除帖子',
      content: '删除后帖子、评论和点赞都会一起删除，确认继续吗？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await Forum.deletePost(postId);
          wx.showToast({ title: '删除成功', icon: 'success' });
          this.setData({
            posts: this.data.posts.filter((item) => item.id != postId),
          });
        } catch {
          wx.showToast({ title: '删除失败，请重试', icon: 'none' });
        }
      },
    });
  },

  async openComment(e) {
    const postId = e.currentTarget.dataset.id;
    this.setData({
      showComment: true,
      currentPostId: postId,
      comments: [],
      commentPage: 1,
      commentNoMore: false,
      commentText: '',
      commentTotal: 0,
      commentInputFocus: false,
      replyParentId: null,
      replyTargetName: '',
      commentPlaceholder: '友善评论，一起交流康复经验',
    });
    await this._loadComments(postId, 1);
    setTimeout(() => this.setData({ commentInputFocus: true }), 250);
  },

  closeComment() {
    this.setData({
      showComment: false,
      currentPostId: null,
      commentInputFocus: false,
      commentText: '',
      replyParentId: null,
      replyTargetName: '',
      commentPlaceholder: '友善评论，一起交流康复经验',
    });
  },

  onCommentInput(e) {
    this.setData({ commentText: e.detail.value });
  },

  replyComment(e) {
    const parentId = e.currentTarget.dataset.id;
    const authorName = e.currentTarget.dataset.author;
    this.setData({
      replyParentId: parentId,
      replyTargetName: authorName || '',
      commentPlaceholder: authorName ? `回复 ${authorName}` : '回复评论',
      commentInputFocus: true,
    });
  },

  cancelReply() {
    this.setData({
      replyParentId: null,
      replyTargetName: '',
      commentPlaceholder: '友善评论，一起交流康复经验',
      commentInputFocus: true,
    });
  },

  async _loadComments(postId, page) {
    this.setData({ commentLoading: true });
    try {
      const res = await Forum.getComments(postId, page, 20);
      const newComments = (res.comments || []).map((item) => ({
        ...item,
        replies: item.replies || [],
      }));
      const total = res.total != null ? res.total : newComments.length;
      const posts = this.data.posts.map((post) =>
        post.id == postId ? { ...post, comment_count: total } : post
      );

      this.setData({
        comments: page === 1 ? newComments : [...this.data.comments, ...newComments],
        commentTotal: total,
        commentPage: page + 1,
        commentNoMore: newComments.length < 20,
        posts,
      });
    } catch {
      if (page === 1) {
        this.setData({
          comments: this._mockComments(),
          commentTotal: 2,
          commentNoMore: true,
        });
      }
    } finally {
      this.setData({ commentLoading: false });
    }
  },

  _mockComments() {
    return [
      {
        id: 101,
        author_id: this.data.currentUserId,
        author_name: '康复指导员',
        author_avatar: '/assets/icons/default_avatar.png',
        created_at: '10分钟前',
        content: '恢复得不错，继续保持训练频率。',
        replies: [
          {
            id: 201,
            author_id: null,
            author_name: '志愿者',
            author_avatar: '/assets/icons/default_avatar.png',
            created_at: '刚刚',
            content: '坚持训练确实很关键。',
            reply_to_user_name: '康复指导员',
            can_delete: false,
          },
        ],
        reply_count: 1,
        can_delete: true,
      },
    ];
  },

  loadMoreComments() {
    if (this.data.commentLoading || this.data.commentNoMore || !this.data.currentPostId) return;
    this._loadComments(this.data.currentPostId, this.data.commentPage);
  },

  async submitComment() {
    const { commentText, currentPostId, replyParentId } = this.data;
    const content = commentText.trim();
    if (!content || !currentPostId) return;

    this.setData({ commentSubmitting: true });
    try {
      await Forum.addComment(currentPostId, content, replyParentId);
      wx.showToast({ title: replyParentId ? '回复成功' : '评论成功', icon: 'success' });
      this.setData({
        commentText: '',
        replyParentId: null,
        replyTargetName: '',
        commentPlaceholder: '友善评论，一起交流康复经验',
        commentInputFocus: false,
      });
      await this._loadComments(currentPostId, 1);
    } catch {
      wx.showToast({ title: replyParentId ? '回复失败，请重试' : '评论失败，请重试', icon: 'none' });
    } finally {
      this.setData({ commentSubmitting: false });
    }
  },

  deleteComment(e) {
    const postId = this.data.currentPostId;
    const commentId = e.currentTarget.dataset.id;
    if (!postId || !commentId) return;

    wx.showModal({
      title: '删除评论',
      content: '删除后无法恢复，确认删除这条评论吗？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await Forum.deleteComment(postId, commentId);
          wx.showToast({ title: '删除成功', icon: 'success' });
          await this._loadComments(postId, 1);
        } catch {
          wx.showToast({ title: '删除失败，请重试', icon: 'none' });
        }
      },
    });
  },

  previewImage(e) {
    wx.previewImage({
      current: e.currentTarget.dataset.src,
      urls: e.currentTarget.dataset.urls,
    });
  },

  goDetail(e) {
    wx.navigateTo({ url: `/pages/forum/detail?id=${e.currentTarget.dataset.id}` });
  },

  onShareAppMessage() {
    return { title: '肌电假手康复社区', path: '/pages/forum/forum' };
  },
});
