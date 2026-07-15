const DEFAULT_PROTOCOL = 'http';
const DEFAULT_HOST = '192.168.43.9';
const DEFAULT_PORT = 8000;
const CANDIDATE_PORTS = [8000, 8001, 8080];

const BASE_URL_KEY = 'baseUrl';
const RESOLVED_BASE_URL_KEY = 'resolvedBaseUrl';

let baseUrlProbePromise = null;

const normalizeBaseUrl = (url) => String(url || '').trim().replace(/\/+$/, '');

const buildBaseUrl = (host, port, protocol = DEFAULT_PROTOCOL) => {
  return `${protocol}://${host}:${port}`;
};

const DEFAULT_BASE_URL = buildBaseUrl(DEFAULT_HOST, DEFAULT_PORT);

const isLegacyLocalBaseUrl = (url) => {
  return url.includes('127.0.0.1') || url.includes('localhost');
};

const parseBaseUrl = (url) => {
  const match = normalizeBaseUrl(url).match(/^(https?):\/\/([^:/]+)(?::(\d+))?$/i);
  if (!match) {
    return {
      protocol: DEFAULT_PROTOCOL,
      host: DEFAULT_HOST,
      port: DEFAULT_PORT,
    };
  }

  return {
    protocol: match[1].toLowerCase(),
    host: match[2],
    port: Number(match[3] || DEFAULT_PORT),
  };
};

const clearInvalidBaseUrlCache = () => {
  const cachedBaseUrl = normalizeBaseUrl(wx.getStorageSync(BASE_URL_KEY));
  const resolvedBaseUrl = normalizeBaseUrl(wx.getStorageSync(RESOLVED_BASE_URL_KEY));

  if (cachedBaseUrl && isLegacyLocalBaseUrl(cachedBaseUrl)) {
    wx.removeStorageSync(BASE_URL_KEY);
    console.warn('[request] removed invalid cached baseUrl:', cachedBaseUrl);
  }

  if (resolvedBaseUrl && isLegacyLocalBaseUrl(resolvedBaseUrl)) {
    wx.removeStorageSync(RESOLVED_BASE_URL_KEY);
    console.warn('[request] removed invalid cached resolvedBaseUrl:', resolvedBaseUrl);
  }
};

const getConfiguredBaseUrl = () => {
  clearInvalidBaseUrlCache();
  const cachedBaseUrl = normalizeBaseUrl(wx.getStorageSync(BASE_URL_KEY));
  return cachedBaseUrl || DEFAULT_BASE_URL;
};

const getBaseUrl = () => {
  clearInvalidBaseUrlCache();
  const resolvedBaseUrl = normalizeBaseUrl(wx.getStorageSync(RESOLVED_BASE_URL_KEY));
  if (resolvedBaseUrl) return resolvedBaseUrl;
  return getConfiguredBaseUrl();
};

const BASE_URL = getBaseUrl();

const isLocalAsset = (url) => {
  return url.startsWith('/assets/') || url.startsWith('../../assets/');
};

const normalizeMediaUrl = (url) => {
  if (!url) return '';
  if (isLocalAsset(url)) return url;
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  return `${getBaseUrl()}${url.startsWith('/') ? '' : '/'}${url}`;
};

const buildCandidateBaseUrls = () => {
  const configuredBaseUrl = getConfiguredBaseUrl();
  const resolvedBaseUrl = normalizeBaseUrl(wx.getStorageSync(RESOLVED_BASE_URL_KEY));
  const configured = parseBaseUrl(configuredBaseUrl);
  const urls = [];
  const seen = new Set();

  const pushUrl = (url) => {
    const normalized = normalizeBaseUrl(url);
    if (!normalized || seen.has(normalized) || isLegacyLocalBaseUrl(normalized)) return;
    seen.add(normalized);
    urls.push(normalized);
  };

  if (resolvedBaseUrl) pushUrl(resolvedBaseUrl);
  pushUrl(configuredBaseUrl);

  const portCandidates = [configured.port, ...CANDIDATE_PORTS];
  portCandidates.forEach((port) => {
    pushUrl(buildBaseUrl(configured.host, port, configured.protocol));
  });

  if (configured.host !== DEFAULT_HOST) {
    [DEFAULT_PORT, ...CANDIDATE_PORTS].forEach((port) => {
      pushUrl(buildBaseUrl(DEFAULT_HOST, port, DEFAULT_PROTOCOL));
    });
  }

  return urls;
};

const probeBaseUrl = (baseUrl) => {
  return new Promise((resolve) => {
    wx.request({
      url: `${baseUrl}/ping`,
      method: 'GET',
      timeout: 1500,
      success: (res) => {
        resolve(res.statusCode >= 200 && res.statusCode < 300);
      },
      fail: () => resolve(false),
    });
  });
};

const ensureBaseUrl = async () => {
  if (baseUrlProbePromise) {
    return baseUrlProbePromise;
  }

  baseUrlProbePromise = (async () => {
    clearInvalidBaseUrlCache();
    const candidates = buildCandidateBaseUrls();

    for (const candidate of candidates) {
      const ok = await probeBaseUrl(candidate);
      if (ok) {
        wx.setStorageSync(RESOLVED_BASE_URL_KEY, candidate);
        console.log('[request] resolved backend baseUrl:', candidate);
        return candidate;
      }
    }

    const fallback = getConfiguredBaseUrl();
    wx.removeStorageSync(RESOLVED_BASE_URL_KEY);
    console.warn('[request] no reachable backend found, fallback to configured baseUrl:', fallback);
    return fallback;
  })();

  try {
    return await baseUrlProbePromise;
  } finally {
    baseUrlProbePromise = null;
  }
};

const request = (options) => {
  return new Promise(async (resolve, reject) => {
    const token = wx.getStorageSync('token') || '';
    const baseUrl = options.url.startsWith('http') ? '' : await ensureBaseUrl();
    const resolvedUrl = options.url.startsWith('http') ? options.url : baseUrl + options.url;

    console.log('[request]', {
      baseUrl: baseUrl || '(absolute url)',
      method: options.method || 'GET',
      url: resolvedUrl,
    });

    wx.request({
      url: resolvedUrl,
      method: options.method || 'GET',
      data: options.data || {},
      timeout: options.timeout || 10000,
      header: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
        ...options.header,
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }

        if (res.statusCode === 401) {
          wx.removeStorageSync('token');
          wx.reLaunch({ url: '/pages/login/login' });
          reject(new Error('授权已失效，请重新登录'));
          return;
        }

        wx.showToast({
          title: res.data.detail || res.data.message || '请求异常',
          icon: 'none',
        });
        reject(res.data);
      },
      fail: (err) => {
        if (baseUrl) {
          wx.removeStorageSync(RESOLVED_BASE_URL_KEY);
        }
        console.error('[request] failed:', resolvedUrl, err);
        wx.showToast({
          title: '网络连接失败，请检查后端地址',
          icon: 'none',
        });
        reject(err);
      },
    });
  });
};

const uploadChunk = async (url, filePath, formData, onProgress) => {
  const token = wx.getStorageSync('token') || '';
  const baseUrl = url.startsWith('http') ? '' : await ensureBaseUrl();
  const resolvedUrl = url.startsWith('http') ? url : baseUrl + url;

  console.log('[uploadChunk]', {
    baseUrl: baseUrl || '(absolute url)',
    url: resolvedUrl,
    sessionId: formData && formData.session_id,
  });

  return new Promise((resolve, reject) => {
    const uploadTask = wx.uploadFile({
      url: resolvedUrl,
      filePath,
      name: 'file',
      formData,
      header: {
        Authorization: token ? `Bearer ${token}` : '',
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          const data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
          resolve(data);
          return;
        }
        reject(res);
      },
      fail: (err) => {
        if (baseUrl) {
          wx.removeStorageSync(RESOLVED_BASE_URL_KEY);
        }
        reject(err);
      },
    });

    if (onProgress) {
      uploadTask.onProgressUpdate((res) => {
        onProgress(res.progress, res.totalBytesSent, res.totalBytesExpectedToSend);
      });
    }
  });
};

const uploadImage = async (filePath, url = '/forum/upload/image') => {
  const token = wx.getStorageSync('token') || '';
  const baseUrl = await ensureBaseUrl();
  const resolvedUrl = `${baseUrl}${url.startsWith('/') ? '' : '/'}${url}`;

  console.log('[uploadImage]', {
    baseUrl,
    url: resolvedUrl,
    filePath,
  });

  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: resolvedUrl,
      filePath,
      name: 'file',
      header: { Authorization: token ? `Bearer ${token}` : '' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          const data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
          resolve(normalizeMediaUrl(data.url || data.image_url || ''));
          return;
        }
        reject(res);
      },
      fail: (err) => {
        wx.removeStorageSync(RESOLVED_BASE_URL_KEY);
        reject(err);
      },
    });
  });
};

const Forum = {
  async getPosts(page, size) {
    const res = await request({ url: `/forum/posts?page=${page}&size=${size}`, method: 'GET' });
    const posts = (res.posts || []).map((post) => ({
      ...post,
      author_avatar: normalizeMediaUrl(post.author_avatar),
      image_urls: (post.image_urls || []).map(normalizeMediaUrl),
    }));
    return { ...res, posts };
  },

  createPost(content, imageUrls) {
    return request({
      url: '/forum/posts',
      method: 'POST',
      data: { content, image_urls: imageUrls },
    });
  },

  deletePost(postId) {
    return request({
      url: `/forum/posts/${postId}`,
      method: 'DELETE',
    });
  },

  like(postId) {
    return request({ url: `/forum/posts/${postId}/like`, method: 'POST' });
  },

  async getComments(postId, page, size) {
    const res = await request({
      url: `/forum/posts/${postId}/comments?page=${page}&size=${size}`,
      method: 'GET',
    });
    const comments = (res.comments || []).map((comment) => ({
      ...comment,
      author_avatar: normalizeMediaUrl(comment.author_avatar),
      replies: (comment.replies || []).map((reply) => ({
        ...reply,
        author_avatar: normalizeMediaUrl(reply.author_avatar),
      })),
    }));
    return { ...res, comments };
  },

  addComment(postId, content, parentId = null) {
    return request({
      url: `/forum/posts/${postId}/comments`,
      method: 'POST',
      data: { content, parent_id: parentId },
    });
  },

  deleteComment(postId, commentId) {
    return request({
      url: `/forum/posts/${postId}/comments/${commentId}`,
      method: 'DELETE',
    });
  },

  uploadImage(filePath) {
    return uploadImage(filePath, '/forum/upload/image');
  },
};

module.exports = {
  request,
  uploadChunk,
  uploadImage,
  BASE_URL,
  getBaseUrl,
  normalizeMediaUrl,
  Forum,
};
