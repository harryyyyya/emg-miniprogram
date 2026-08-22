const ble = require('../../utils/ble_manager');
const esp32Link = require('../../utils/esp32_link');
const { request } = require('../../utils/request');

function formatBeijingTime(value = new Date()) {
  const source = value instanceof Date
    ? value
    : new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(String(value)) ? value : `${value}Z`);
  if (Number.isNaN(source.getTime())) return '';
  // Format from the epoch with UTC getters so the phone's local timezone cannot
  // change the displayed collection/report time.
  const bj = new Date(source.getTime() + 8 * 60 * 60 * 1000);
  const pad = (number) => String(number).padStart(2, '0');
  return `${bj.getUTCFullYear()}-${pad(bj.getUTCMonth() + 1)}-${pad(bj.getUTCDate())} ${pad(bj.getUTCHours())}:${pad(bj.getUTCMinutes())}:${pad(bj.getUTCSeconds())}`;
}

Page({
  data: {
    deviceName: '未绑定设备',
    deviceOnline: false,
    deviceStatusText: '请先绑定设备',
    healthSignalStatus: '等待肌电数据',
    healthWindowSamples: 0,
    healthLiveRms: '--',
    healthLiveMav: '--',
    healthLivePeak: '--',
    healthSidePressure: '--',
    healthScore: '--',
    healthLevel: '等待分析',
    healthMuscleStatus: '--',
    healthFatigueIndex: '--',
    healthQualityScore: '--',
    healthBaselineRms: '--',
    healthRmsCv: '--',
    healthMf: '--',
    healthMnf: '--',
    healthPower: '--',
    healthBaselineScore: '--',
    healthStabilityScore: '--',
    healthFrequencyScore: '--',
    healthAdvice: '绑定设备后，这里会根据真实肌电信号生成报告。',
    healthAiSource: '等待 DeepSeek 分析',
    healthUpdatedAt: '',
    healthReportAt: '',
    healthAnalyzing: false,
    healthHasReport: false,
  },

  _healthTimer: null,
  _healthWindow: [],
  _healthLastPreviewMarker: '',
  _healthLastAnalysisAt: 0,
  _healthAnalysisInFlight: false,
  _healthAiAutoRequested: false,
  _healthDataListener: null,
  _healthDevice: null,
  _sidePressure: null,

  onShow() {
    this.loadDeviceStatus();
    this.startHealthMonitor();
    this.loadLatestReport();
  },

  onReady() {
    this.drawHealthChart([]);
  },

  onHide() {
    this.stopHealthMonitor();
  },

  onUnload() {
    this.stopHealthMonitor();
  },

  goToBind() {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  goToControl() {
    wx.navigateTo({ url: '/pages/control/control' });
  },

  async loadDeviceStatus() {
    const device = wx.getStorageSync('boundDevice');
    this._healthDevice = device || null;
    if (!device || !device.hardware_id) {
      this.setData({
        deviceName: '未绑定设备',
        deviceOnline: false,
        deviceStatusText: '请先绑定设备',
      });
      return;
    }

    const name = device.name || device.deviceName || device.hardware_id;
    this.setData({ deviceName: name });
    if ((device.transport || 'ble') === 'ble') {
      const online = ble.isConnected();
      this.setData({
        deviceOnline: online,
        deviceStatusText: online ? '蓝牙在线 · 实时采集中' : '蓝牙离线 · 请到绑定页连接',
      });
      ble.onStatus((status) => {
        const connected = status === 'connected';
        this.setData({
          deviceOnline: connected,
          deviceStatusText: connected ? '蓝牙在线 · 实时采集中' : '蓝牙离线 · 请到绑定页连接',
        });
      });
      return;
    }

    this.pollHealthDevice();
  },

  startHealthMonitor() {
    this.stopHealthMonitor();
    this._healthDevice = wx.getStorageSync('boundDevice') || null;
    this._healthWindow = [];
    this._healthLastPreviewMarker = '';
    this._healthLastAnalysisAt = 0;
    this._healthAiAutoRequested = false;
    this._sidePressure = null;
    const device = this._healthDevice;
    this.setData({
      healthSignalStatus: device ? '正在连接肌电数据流' : '未绑定设备',
      healthWindowSamples: 0,
      healthLiveRms: '--',
      healthLiveMav: '--',
      healthLivePeak: '--',
      healthScore: '--',
      healthLevel: '等待分析',
      healthMuscleStatus: '--',
      healthFatigueIndex: '--',
      healthQualityScore: '--',
      healthAdvice: device ? '正在等待真实肌电数据...' : '请先绑定设备，才能进行实时肌电分析。',
      healthAiSource: '等待 DeepSeek 分析',
      healthUpdatedAt: '',
      healthHasReport: false,
    });
    this.drawHealthChart([]);
    if (!device || !device.hardware_id) return;

    const transport = device.transport || 'ble';
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
      let statusDevice = {};
      let telemetry = {};
      if ((device.transport || 'ble') === 'esp32_direct') {
        esp32Link.setCurrentConfig(device);
        const info = await esp32Link.fetchInfo(device);
        statusDevice = info || {};
        telemetry = info.telemetry || info || {};
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
      const online = (statusDevice.status || 'offline') === 'online' || (device.transport || '') === 'esp32_direct';
      this._sidePressure = telemetry.side_pressure !== undefined
        ? Number(telemetry.side_pressure)
        : (telemetry.side_presure !== undefined ? Number(telemetry.side_presure) : null);
      this.setData({
        deviceOnline: online,
        deviceStatusText: online ? '设备在线 · 肌电数据同步中' : '设备离线 · 等待回连',
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
    const rows = (samples || [])
      .filter((row) => Array.isArray(row) && row.length === 8)
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
      healthUpdatedAt: formatBeijingTime(),
    });
    this.drawHealthChart(this._healthWindow);

    const now = Date.now();
    if (this._healthWindow.length >= 100 && now - this._healthLastAnalysisAt >= 3000 && !this._healthAnalysisInFlight) {
      const requestAi = !this._healthAiAutoRequested;
      if (requestAi) this._healthAiAutoRequested = true;
      this.requestHealthAnalysis(requestAi, requestAi);
    }
  },

  computeHealthLiveStats(samples) {
    const centered = [];
    let peak = 0;
    (samples || []).forEach((row) => row.forEach((value) => {
      const centeredValue = (Number(value) || 0) - 127;
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

  applyReport(res, fromHistory = false) {
    const metrics = res.metrics || res.analysis || {};
    const reportAt = res.generated_at || (fromHistory ? res.recorded_at || '' : '');
    const aiSource = res.ai_source === 'deepseek'
      ? 'DeepSeek 建议'
      : (res.ai_source === 'deepseek_unavailable'
        ? 'DeepSeek 暂不可用 · 本地规则建议'
        : (res.ai_source === 'local_fallback'
          ? '本地规则建议'
          : (res.ai_advice ? '已保存建议（来源未记录）' : this.data.healthAiSource)));
    this.setData({
      healthLiveRms: metrics.rms !== undefined ? String(metrics.rms) : (res.rms_value !== undefined ? String(res.rms_value) : this.data.healthLiveRms),
      healthLiveMav: metrics.mav !== undefined ? String(metrics.mav) : this.data.healthLiveMav,
      healthSidePressure: res.side_pressure !== undefined
        ? String(res.side_pressure)
        : (res.side_presure !== undefined ? String(res.side_presure) : this.data.healthSidePressure),
      healthScore: metrics.health_score !== undefined ? String(metrics.health_score) : (res.health_score !== undefined ? String(res.health_score) : this.data.healthScore),
      healthLevel: res.health_level || metrics.health_level || this.data.healthLevel,
      healthMuscleStatus: res.muscle_status || metrics.muscle_status || this.data.healthMuscleStatus,
      healthFatigueIndex: metrics.fatigue_index !== undefined ? String(metrics.fatigue_index) : this.data.healthFatigueIndex,
      healthQualityScore: metrics.quality_score !== undefined ? String(metrics.quality_score) : this.data.healthQualityScore,
      healthBaselineRms: metrics.baseline_rms !== undefined ? String(metrics.baseline_rms) : this.data.healthBaselineRms,
      healthRmsCv: metrics.rms_cv !== undefined ? String(metrics.rms_cv) : this.data.healthRmsCv,
      healthMf: metrics.mf !== undefined ? String(metrics.mf) : this.data.healthMf,
      healthMnf: metrics.mnf !== undefined ? String(metrics.mnf) : this.data.healthMnf,
      healthPower: metrics.total_power !== undefined ? String(metrics.total_power) : this.data.healthPower,
      healthBaselineScore: metrics.baseline_score !== undefined ? String(metrics.baseline_score) : this.data.healthBaselineScore,
      healthStabilityScore: metrics.stability_score !== undefined ? String(metrics.stability_score) : this.data.healthStabilityScore,
      healthFrequencyScore: metrics.frequency_score !== undefined ? String(metrics.frequency_score) : this.data.healthFrequencyScore,
      healthAdvice: res.ai_advice || res.diagnostics || this.data.healthAdvice,
      healthAiSource: aiSource,
      healthReportAt: reportAt ? formatBeijingTime(reportAt) : this.data.healthReportAt,
      healthHasReport: true,
    });
  },

  async loadLatestReport() {
    try {
      const res = await request({ url: '/health/records?limit=1', method: 'GET', silent: true, timeout: 8000 });
      const records = Array.isArray(res) ? res : (res.records || []);
      if (records.length) this.applyReport(records[0], true);
    } catch (e) {
      // No saved report is a normal first-use state.
    }
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
          side_pressure: this._sidePressure,
          include_ai: includeAi,
          persist,
        },
        timeout: includeAi ? 40000 : 10000,
      });
      this.applyReport(res);
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
    const screenWidth = (wx.getSystemInfoSync && wx.getSystemInfoSync().windowWidth) || 375;
    const scale = screenWidth / 750;
    const width = Math.max(240, Math.floor((750 - 60 - 56) * scale));
    const height = Math.max(100, Math.floor(230 * scale));
    const series = (samples || []).slice(-180).map((row) => (Number(row[0]) || 0) - 127);
    ctx.setFillStyle('#071b2b');
    ctx.fillRect(0, 0, width, height);
    ctx.setStrokeStyle('rgba(148, 163, 184, 0.16)');
    ctx.setLineWidth(1);
    for (let grid = 1; grid < 4; grid += 1) {
      const y = (height / 4) * grid;
      ctx.beginPath();
      ctx.moveTo(10, y);
      ctx.lineTo(width - 10, y);
      ctx.stroke();
    }
    if (!series.length) {
      ctx.setFillStyle('rgba(255,255,255,0.62)');
      ctx.setFontSize(13);
      ctx.fillText('等待实时肌电信号...', Math.max(18, width / 2 - 58), height / 2 + 4);
      ctx.draw();
      return;
    }
    const min = Math.min(...series);
    const max = Math.max(...series);
    const range = Math.max(1, max - min);
    ctx.beginPath();
    series.forEach((value, index) => {
      const x = 12 + (index / Math.max(1, series.length - 1)) * (width - 24);
      const y = 12 + ((max - value) / range) * (height - 24);
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.setStrokeStyle('#24f2a6');
    ctx.setLineWidth(2);
    ctx.stroke();
    ctx.draw();
  },
});
