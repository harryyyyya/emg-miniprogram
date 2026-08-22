const ble = require('../../utils/ble_manager');
const esp32Link = require('../../utils/esp32_link');
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
    healthSignalStatus: '等待肌电数据',
    healthWindowSamples: 0,
    healthLiveRms: '--',
    healthLiveMav: '--',
    healthLivePeak: '--',
    healthScore: '--',
    healthLevel: '等待分析',
    healthMuscleStatus: '--',
    healthFatigueIndex: '--',
    healthQualityScore: '--',
    healthAdvice: '绑定设备后，首页会根据最近一段真实肌电信号进行分析。',
    healthAiSource: '',
    healthUpdatedAt: '',
    healthAnalyzing: false,
  },

  _healthTimer: null,
  _healthWindow: [],
  _healthLastPreviewMarker: '',
  _healthLastAnalysisAt: 0,
  _healthAnalysisInFlight: false,
  _healthDataListener: null,
  _healthDevice: null,

  onShow() {
    this.loadDeviceStatus();
    this.loadKnowledgeArticles();
    this.startHealthMonitor();
  },

  onHide() {
    this.stopHealthMonitor();
  },

  onUnload() {
    this.stopHealthMonitor();
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
          deviceStatusText: status ? 'Wi-Fi 在线 · 后端已收到心跳' : 'Wi-Fi 离线 · 等待回连',
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

  startHealthMonitor() {
    this.stopHealthMonitor();
    this._healthDevice = wx.getStorageSync('boundDevice') || null;
    this._healthWindow = [];
    this._healthLastPreviewMarker = '';
    this.setData({
      healthSignalStatus: this._healthDevice ? '正在连接肌电数据流' : '未绑定设备',
      healthWindowSamples: 0,
      healthScore: '--',
      healthLevel: '等待分析',
      healthAdvice: this._healthDevice
        ? '正在等待真实肌电数据...'
        : '请先绑定设备，首页才能进行实时肌电分析。',
      healthAiSource: '',
      healthUpdatedAt: '',
    });
    this.drawHealthChart([]);
    if (!this._healthDevice || !this._healthDevice.hardware_id) return;

    const transport = this._healthDevice.transport || 'ble';
    if (transport === 'ble') {
      this._healthDataListener = (samples) => this.consumeHealthSamples(samples, '蓝牙');
      if (ble.addDataListener) ble.addDataListener(this._healthDataListener);
      this.setData({
        healthSignalStatus: ble.isConnected() ? '蓝牙实时采集中' : '等待蓝牙连接',
        deviceOnline: ble.isConnected(),
      });
      return;
    }

    this.pollHealthDevice();
    this._healthTimer = setInterval(() => this.pollHealthDevice(), 1000);
  },

  stopHealthMonitor() {
    if (this._healthTimer) {
      clearInterval(this._healthTimer);
      this._healthTimer = null;
    }
    if (this._healthDataListener && ble.removeDataListener) {
      ble.removeDataListener(this._healthDataListener);
    }
    this._healthDataListener = null;
  },

  async pollHealthDevice() {
    const device = this._healthDevice;
    if (!device || !device.hardware_id) return;
    try {
      let statusDevice = null;
      let telemetry = {};
      if ((device.transport || 'ble') === 'esp32_direct') {
        esp32Link.setCurrentConfig(device);
        const info = await esp32Link.fetchInfo(device);
        statusDevice = info;
        telemetry = info.telemetry || info;
      } else {
        const res = await request({
          url: `/devices/${encodeURIComponent(device.hardware_id)}/status`,
          method: 'GET',
          silent: true,
          timeout: 5000,
        });
        statusDevice = res.device || {};
        telemetry = statusDevice.telemetry || {};
      }
      const preview = Array.isArray(telemetry.emg_preview) ? telemetry.emg_preview : [];
      const marker = telemetry.emg_preview_updated_at
        || `${telemetry.emg_preview_sequence_no || 0}:${JSON.stringify(preview[preview.length - 1] || [])}`;
      this.setData({
        deviceOnline: (statusDevice.status || 'offline') === 'online' || (device.transport || '') === 'esp32_direct',
        deviceStatusText: (statusDevice.status || 'offline') === 'online' ? '设备在线 · 肌电数据同步中' : '设备离线 · 等待回连',
      });
      if (preview.length && marker !== this._healthLastPreviewMarker) {
        this._healthLastPreviewMarker = marker;
        this.consumeHealthSamples(preview, device.transport === 'esp32_direct' ? 'ESP32' : 'Wi-Fi');
      }
    } catch (e) {
      this.setData({ healthSignalStatus: '肌电数据流暂时中断' });
    }
  },

  consumeHealthSamples(samples, source = '设备') {
    const rows = (samples || []).filter((row) => Array.isArray(row) && row.length === 8)
      .map((row) => row.map((value) => Number(value) || 0));
    if (!rows.length) return;
    this._healthWindow = [...this._healthWindow, ...rows].slice(-1000);
    const stats = this.computeHealthLiveStats(this._healthWindow);
    this.setData({
      healthSignalStatus: `${source}实时采集中`,
      healthWindowSamples: this._healthWindow.length,
      healthLiveRms: stats.rms.toFixed(2),
      healthLiveMav: stats.mav.toFixed(2),
      healthLivePeak: String(Math.round(stats.peak)),
      healthUpdatedAt: new Date().toLocaleTimeString(),
    });
    this.drawHealthChart(this._healthWindow);

    const now = Date.now();
    if (this._healthWindow.length >= 100 && now - this._healthLastAnalysisAt >= 3000 && !this._healthAnalysisInFlight) {
      this.requestHealthAnalysis(false, false);
    }
  },

  computeHealthLiveStats(samples) {
    const centered = [];
    let peak = 0;
    (samples || []).forEach((row) => row.forEach((value) => {
      const n = Number(value) || 0;
      const centeredValue = n - 127;
      centered.push(centeredValue);
      peak = Math.max(peak, Math.abs(centeredValue));
    }));
    if (!centered.length) return { rms: 0, mav: 0, peak: 0 };
    const sum = centered.reduce((acc, value) => acc + value * value, 0);
    return {
      rms: Math.sqrt(sum / centered.length),
      mav: centered.reduce((acc, value) => acc + Math.abs(value), 0) / centered.length,
      peak,
    };
  },

  async requestHealthAnalysis(includeAi = false, persist = false) {
    if (this._healthAnalysisInFlight || this._healthWindow.length < 32 || !this._healthDevice) return;
    this._healthAnalysisInFlight = true;
    this.setData({ healthAnalyzing: true });
    try {
      const res = await request({
        url: '/health/report/analyze',
        method: 'POST',
        data: {
          samples: this._healthWindow.slice(-1000),
          sample_rate_hz: 500,
          hardware_id: this._healthDevice.hardware_id || '',
          include_ai: includeAi,
          persist,
        },
        timeout: includeAi ? 40000 : 10000,
      });
      const metrics = res.metrics || {};
      this.setData({
        healthScore: metrics.health_score !== undefined ? String(metrics.health_score) : this.data.healthScore,
        healthLevel: res.health_level || metrics.health_level || this.data.healthLevel,
        healthMuscleStatus: res.muscle_status || metrics.muscle_status || this.data.healthMuscleStatus,
        healthFatigueIndex: metrics.fatigue_index !== undefined ? String(metrics.fatigue_index) : this.data.healthFatigueIndex,
        healthQualityScore: metrics.quality_score !== undefined ? String(metrics.quality_score) : this.data.healthQualityScore,
        healthAdvice: res.ai_advice || res.diagnostics || this.data.healthAdvice,
        healthAiSource: res.ai_source === 'deepseek' ? 'DeepSeek 建议' : '本地规则建议',
      });
      this._healthLastAnalysisAt = Date.now();
      if (includeAi) wx.showToast({ title: persist ? '健康报告已保存' : 'AI建议已更新', icon: 'success' });
    } catch (err) {
      if (includeAi) wx.showToast({ title: '健康分析失败，请稍后重试', icon: 'none' });
    } finally {
      this._healthAnalysisInFlight = false;
      this.setData({ healthAnalyzing: false });
    }
  },

  requestHealthAi() {
    if (this._healthWindow.length < 32) {
      wx.showToast({ title: '至少采集一段肌电数据后再分析', icon: 'none' });
      return;
    }
    this.requestHealthAnalysis(true, true);
  },

  drawHealthChart(samples) {
    const ctx = wx.createCanvasContext('healthCanvas', this);
    const width = 330;
    const height = 150;
    const series = (samples || []).slice(-160).map((row) => (Number(row[0]) || 0) - 127);
    ctx.setFillStyle('#071b2b');
    ctx.fillRect(0, 0, width, height);
    if (!series.length) {
      ctx.setFillStyle('rgba(255,255,255,0.62)');
      ctx.setFontSize(13);
      ctx.fillText('等待实时肌电信号...', 98, 78);
      ctx.draw();
      return;
    }
    const min = Math.min(...series);
    const max = Math.max(...series);
    const range = Math.max(1, max - min);
    ctx.beginPath();
    series.forEach((value, index) => {
      const x = 12 + (index / Math.max(1, series.length - 1)) * 306;
      const y = 12 + ((max - value) / range) * 116;
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.setStrokeStyle('#24f2a6');
    ctx.setLineWidth(2);
    ctx.stroke();
    ctx.draw();
  },

  openHealthReport() {
    if (this._healthWindow.length >= 32) {
      this.requestHealthAi();
      return;
    }
    wx.showModal({
      title: '实时健康报告',
      content: '请先绑定设备并采集至少一段真实肌电信号。',
      showCancel: false,
    });
  },
});
