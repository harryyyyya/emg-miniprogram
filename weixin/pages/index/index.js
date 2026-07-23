const ble = require('../../utils/ble_manager');
const { request, normalizeMediaUrl } = require('../../utils/request');

const FALLBACK_KNOWLEDGE_LIST = [
  {
    id: 1,
    cover: '/assets/images/article1.jpg',
    title: '新手第一次连接：先确认这 3 件事',
    tag: '设备连接',
    desc: '确认 ESP32 已连上 Wi-Fi、串口出现 heartbeat status=200，再在小程序里一键绑定默认设备。',
  },
  {
    id: 2,
    cover: '/assets/images/article2.jpg',
    title: '动作录入怎么练：每次 5 秒更稳定',
    tag: '训练建议',
    desc: '录入动作时保持姿势稳定，观察原始肌电波形和 RMS，逐步提高识别准确度。',
  },
  {
    id: 3,
    cover: '/assets/images/article3.jpg',
    title: '假手适应期心理疏导：慢慢来，也是一种进步',
    tag: '心理支持',
    desc: '学习呼吸放松、建立支持网络，并在需要时寻求专业帮助。',
    tone: 'warm',
  },
];

const normalizeKnowledgeArticle = (article) => ({
  id: article.id,
  cover: normalizeMediaUrl(article.cover || article.cover_url || ''),
  title: article.title || '未命名文章',
  tag: article.tag || article.type || '康复建议',
  desc: article.desc || article.summary || article.excerpt || '',
  tone: article.theme || '',
});

Page({
  data: {
    banners: [
      { id: 1, image: '/assets/images/banner1.png', title: '智能肌电假手，重塑日常能力' },
      { id: 2, image: '/assets/images/banner2.png', title: '个性化动作录入，让控制更贴合你' },
      { id: 3, image: '/assets/images/banner3.png', title: '持续监测设备与肌电状态' },
    ],
    knowledgeList: FALLBACK_KNOWLEDGE_LIST,
    deviceName: '',
    deviceOnline: false,
    deviceStatusText: '离线 · 点击绑定',
  },

  onShow() {
    this.loadDeviceStatus();
    this.loadKnowledgeArticles();
  },

  onPullDownRefresh() {
    Promise.all([
      this.loadDeviceStatus(),
      this.loadKnowledgeArticles(),
    ]).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadKnowledgeArticles() {
    try {
      const articles = await request({
        url: '/knowledge/articles?published=true&limit=100',
        method: 'GET',
        timeout: 5000,
        silent: true,
      });
      const list = (articles || []).map(normalizeKnowledgeArticle).filter((item) => item.id);
      if (list.length) {
        this.setData({ knowledgeList: list });
      }
    } catch (e) {
      this.setData({ knowledgeList: FALLBACK_KNOWLEDGE_LIST });
    }
  },

  async loadDeviceStatus() {
    const device = wx.getStorageSync('boundDevice');
    if (!device || !device.hardware_id) {
      this.setData({
        deviceName: '',
        deviceOnline: false,
        deviceStatusText: '离线 · 点击绑定',
      });
      return;
    }

    const name = device.name || device.deviceName || device.hardware_id;
    if ((device.transport || 'ble') === 'wifi') {
      this.setData({
        deviceName: name,
        deviceOnline: false,
        deviceStatusText: 'Wi-Fi 设备 · 正在检查',
      });

      try {
        const res = await request({
          url: `/devices/${encodeURIComponent(device.hardware_id)}/status`,
          method: 'GET',
          timeout: 3000,
          silent: true,
        });
        const status = ((res.device || {}).status || 'offline') === 'online';
        this.setData({
          deviceName: name,
          deviceOnline: status,
          deviceStatusText: status ? 'Wi-Fi 在线 · 后端已收到心跳' : 'Wi-Fi 离线 · 等待 ESP32 回连',
        });
      } catch (e) {
        this.setData({
          deviceName: name,
          deviceOnline: false,
          deviceStatusText: 'Wi-Fi 离线 · 无法获取设备状态',
        });
      }
      return;
    }

    this.setData({
      deviceName: name,
      deviceOnline: ble.isConnected(),
      deviceStatusText: ble.isConnected() ? '蓝牙在线 · 已连接' : '蓝牙离线 · 点击重新绑定',
    });

    ble.onStatus((status) => {
      const online = status === 'connected';
      this.setData({
        deviceOnline: online,
        deviceStatusText: online ? '蓝牙在线 · 已连接' : '蓝牙离线 · 点击重新绑定',
      });
    });
  },

  openArticle(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/article/article?id=${id}` });
  },

  goToBind() {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  goTo(e) {
    const url = e.currentTarget.dataset.url;
    if (url.startsWith('/pages/ai/')) {
      wx.switchTab({ url: '/pages/ai/ai' });
    } else {
      wx.navigateTo({ url });
    }
  },
});
