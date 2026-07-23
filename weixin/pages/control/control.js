const ble = require('../../utils/ble_manager');
const { request, uploadChunk } = require('../../utils/request');
const esp32Link = require('../../utils/esp32_link');

const DEFAULT_GESTURES = [
  { emoji: '🖐️', name: '目标动作', duration: 3 },
];

const EMG_STORAGE_PREFIX = 'realtime_emg_';
const EMG_CACHE_LIMIT = 240;
const RELAX_SECONDS = 3;
const ACTION_SECONDS = 3;
const MAX_COLLECT_SECONDS = 60;
const fs = wx.getFileSystemManager();
const TEMP_DIR = `${wx.env.USER_DATA_PATH}/emg_collect`;

function statusText(value) {
  if (value === undefined || value === null || value === '') return '未上报';
  return String(value);
}

Page({
  data: {
    mode: 'public',
    deviceTransport: 'ble',
    deviceName: '',
    deviceStatus: 'offline',
    deviceStatusLabel: '离线',
    deviceStatusHint: '等待设备连接',
    deviceIp: '',
    firmwareVersion: '',
    battery: 0,
    strength: 0,
    rmsValue: '',
    sidePresure: '',
    muscleStatus: '正常',
    healthAlert: '',
    lastCommandMessage: '',

    predictionResult: '',
    predictionConfidence: '',
    storageStatus: '未上报',
    modelStatus: '未上报',
    bluetoothStatus: '未上报',
    cpuStatus: '未上报',
    armbandStatusLabel: '未知',
    armbandStatusHint: '等待臂环状态上报',

    recordingSessionId: '',
    recordingSamples: 0,
    recordingBatches: 0,
    recordingRms: '',
    recordingActive: false,
    emgPreviewUpdatedAt: '',
    emgLiveSamples: 0,
    emgLiveRms: '--',
    emgLivePeak: '--',
    emgLiveMin: '--',
    emgLiveMax: '--',

    isCollecting: false,
    gestureEmoji: '🌿',
    gestureName: '等待开始',
    collectGuide: '点击开始后，按 3 秒放松、3 秒目标动作循环采集。',
    collectElapsedText: '最长 1 分钟，可随时停止',
    collectPhase: 'idle',
    countdown: 0,
    hasCollectedData: false,
    canUpload: false,

    customGestures: [],
    selectedGestureIndex: -1,
    storedSessions: [],
    storedSessionsLoading: false,
    storedSessionsError: '',
    selectedStoredSessionId: '',
    selectedStoredSession: null,

    isUploading: false,
    uploadProgress: 0,
    uploadedChunks: 0,
    totalChunks: 0,
  },

  _boundDevice: null,
  _collectTimer: null,
  _statusTimer: null,
  _gestureIndex: 0,
  _activeGestures: DEFAULT_GESTURES,
  _collectStartedAt: 0,
  _sessionId: '',
  _collectBuffer: [],
  _tempFilePath: '',
  _emgSamples: [],

  onLoad(options) {
    if (options && options.tab === 'health') {
      this.generateReport();
    }

    try {
      fs.mkdirSync(TEMP_DIR, true);
    } catch (e) {}

    const savedGestures = wx.getStorageSync('customGestures');
    if (savedGestures && savedGestures.length) {
      this.setData({ customGestures: savedGestures, selectedGestureIndex: 0 });
    }

    this.loadBoundDevice();
    this.loadStoredSessions(true);
  },

  onReady() {
    this.drawRing('batteryCanvas', this.data.battery / 100, '#0B59D6');
    this.drawRing('strengthCanvas', this.data.strength / 100, '#1F9D55');
    this.drawEmgChart(this._emgSamples);

    if (this.data.deviceTransport === 'wifi' && this._boundDevice && this._boundDevice.hardware_id) {
      this.refreshWifiStatus(true);
      this.startWifiStatusPolling();
    } else if (this.data.deviceTransport === 'esp32_direct') {
      this.initEsp32DirectMode();
    } else {
      this.initBleMode();
    }

    this.drawStoredSessionPreview();
  },

  onShow() {
    if (this.data.deviceTransport === 'wifi' && this._boundDevice && this._boundDevice.hardware_id) {
      this.refreshWifiStatus(true);
    }
    if (this.data.deviceTransport === 'esp32_direct') {
      this.refreshEsp32Info(true);
    }
    this.loadStoredSessions(true);
  },

  onUnload() {
    if (this._collectTimer) clearInterval(this._collectTimer);
    if (this._statusTimer) clearInterval(this._statusTimer);
    if (this.data.deviceTransport === 'esp32_direct') {
      esp32Link.disconnect();
    }
  },

  loadBoundDevice() {
    this._boundDevice = wx.getStorageSync('boundDevice') || null;
    const transport = (this._boundDevice && this._boundDevice.transport) || 'ble';
    const deviceName = (this._boundDevice && (this._boundDevice.name || this._boundDevice.deviceName || this._boundDevice.hardware_id)) || '未绑定设备';
    const cacheKey = this._boundDevice && this._boundDevice.hardware_id
      ? `${EMG_STORAGE_PREFIX}${this._boundDevice.hardware_id}`
      : '';
    const cache = cacheKey ? (wx.getStorageSync(cacheKey) || {}) : {};

    this._emgSamples = cache.samples || [];

    this.setData({
      deviceTransport: transport,
      deviceName,
      deviceIp: (this._boundDevice && this._boundDevice.ip) || '',
      canUpload: transport === 'ble',
      deviceStatus: transport === 'wifi' || transport === 'esp32_direct'
        ? 'offline'
        : (ble.isConnected() ? 'online' : 'offline'),
      emgPreviewUpdatedAt: cache.updatedAt || '',
    });
    this.updateConnectionState(this.data.deviceStatus);
  },

  updateConnectionState(status = this.data.deviceStatus, hint = '') {
    const online = status === 'online';
    const transport = this.data.deviceTransport;
    let autoHint = '等待设备连接';

    if (transport === 'wifi') {
      autoHint = online ? 'ESP32 已在线，后端心跳正常' : '等待 ESP32 通过 Wi-Fi 上报心跳和肌电数据';
    } else if (transport === 'esp32_direct') {
      autoHint = online ? 'ESP32 直连已建立，波形实时刷新' : '等待 ESP32 直连 WebSocket 恢复';
    } else {
      autoHint = online ? '蓝牙已连接，可直接采集' : '蓝牙未连接，请先绑定设备';
    }

    this.setData({
      deviceStatusLabel: online ? '在线' : '离线',
      deviceStatusHint: hint || autoHint,
    });
  },

  updateArmbandState(bluetoothStatus) {
    const value = String(bluetoothStatus || '').toLowerCase();
    const online = /online|connected|connected\+|ok|true|已连接|在线|正常/.test(value);
    const offline = /offline|disconnected|close|false|断开|离线/.test(value);
    let label = '未知';
    let hint = '等待臂环状态上报';

    if (online) {
      label = '在线';
      hint = '已连接臂环，正在接收肌电信号';
    } else if (offline) {
      label = '离线';
      hint = '臂环未连接或信号中断';
    }

    this.setData({
      armbandStatusLabel: label,
      armbandStatusHint: hint,
    });
  },

  async loadStoredSessions(silent = false) {
    this.setData({ storedSessionsLoading: true, storedSessionsError: '' });
    try {
      const res = await request({
        url: '/devices/emg/sessions?limit=12',
        method: 'GET',
      });
      const sessions = res.sessions || [];
      this.setData({
        storedSessions: sessions,
        storedSessionsError: '',
      });
      if (sessions.length) {
        const keepSelected = this.data.selectedStoredSessionId
          ? sessions.find((item) => item.session_id === this.data.selectedStoredSessionId)
          : null;
        if (keepSelected) {
          this.setData({
            selectedStoredSessionId: keepSelected.session_id,
            selectedStoredSession: keepSelected,
          });
          this.drawStoredSessionPreview();
        } else {
          this.selectStoredSessionByIndex(0);
        }
      } else {
        this.setData({
          selectedStoredSessionId: '',
          selectedStoredSession: null,
        });
        this.drawStoredSessionPreview();
      }
    } catch (err) {
      this.setData({ storedSessionsError: '读取采集记录失败' });
      if (!silent) {
        wx.showToast({ title: '读取采集记录失败', icon: 'none' });
      }
    } finally {
      this.setData({ storedSessionsLoading: false });
    }
  },

  selectStoredSession(e) {
    const index = Number(e.currentTarget.dataset.index);
    this.selectStoredSessionByIndex(index);
  },

  selectStoredSessionByIndex(index) {
    const session = this.data.storedSessions[index];
    if (!session) return;
    this.setData({
      selectedStoredSessionId: session.session_id,
      selectedStoredSession: session,
    });
    this.drawStoredSessionPreview();
  },

  deleteStoredSession(e) {
    const sessionId = e.currentTarget.dataset.id;
    if (!sessionId) return;

    wx.showModal({
      title: '删除采集记录',
      content: '删除后会同时删除数据库里的动作录入记录和对应肌电数据文件，确认继续吗？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request({
            url: `/devices/emg/sessions/${encodeURIComponent(sessionId)}`,
            method: 'DELETE',
          });
          const nextSessions = this.data.storedSessions.filter((item) => item.session_id !== sessionId);
          const selectedRemoved = this.data.selectedStoredSessionId === sessionId;
          this.setData({
            storedSessions: nextSessions,
            selectedStoredSessionId: selectedRemoved ? '' : this.data.selectedStoredSessionId,
            selectedStoredSession: selectedRemoved ? null : this.data.selectedStoredSession,
          });
          if (nextSessions.length && selectedRemoved) {
            this.selectStoredSessionByIndex(0);
          } else {
            this.drawStoredSessionPreview();
          }
          wx.showToast({ title: '删除成功', icon: 'success' });
        } catch (err) {
          wx.showToast({ title: '删除失败，请重试', icon: 'none' });
        }
      },
    });
  },

  drawStoredSessionPreview() {
    const session = this.data.selectedStoredSession;
    const preview = session && Array.isArray(session.preview) ? session.preview : [];
    this.drawEmgChart(preview, 'historyCanvas');
  },

  initBleMode() {
    ble.onStatus((status) => {
      const nextStatus = status === 'connected' ? 'online' : 'offline';
      this.setData({ deviceStatus: nextStatus });
      this.updateConnectionState(nextStatus);
      this.updateArmbandState(nextStatus === 'online' ? 'connected' : 'disconnected');
    });

    ble.onData((samples) => {
      const stats = this.computeSampleStats(samples);
      this.setData({
        strength: stats.strength,
        rmsValue: stats.rms.toFixed(1),
      });
      this.drawRing('strengthCanvas', stats.strength / 100, '#1F9D55');
      this.pushRealtimeSamples(samples);

      if (this.data.isCollecting) {
        this._collectBuffer.push(...samples);
      }
    });
  },

  initEsp32DirectMode() {
    esp32Link.setCurrentConfig(this._boundDevice);
    esp32Link.onStatus(({ status }) => {
      const nextStatus = status === 'online' ? 'online' : 'offline';
      this.setData({ deviceStatus: nextStatus });
      this.updateConnectionState(nextStatus);
    });
    esp32Link.onMessage((msg) => {
      this.applyEsp32Message(msg);
    });
    this.refreshEsp32Info(true);
    esp32Link.connect(this._boundDevice).catch(() => {
      this.setData({ deviceStatus: 'offline', lastCommandMessage: 'ESP32 WebSocket 未连接' });
      this.updateConnectionState('offline');
    });
  },

  applyEsp32Message(msg) {
    const type = msg.type || '';
    const data = msg.data || {};

    if (type === 'telemetry') {
      this.applyDirectTelemetry(data);
      return;
    }

    if (type === 'ack') {
      this.setData({
        lastCommandMessage: data.message || msg.msg || 'ESP32 已确认命令',
      });
      return;
    }

    if (type === 'collect_state') {
      this.setData({
        recordingSessionId: data.session_id || this.data.recordingSessionId,
        recordingSamples: Number(data.sample_count || this.data.recordingSamples || 0),
        recordingBatches: Number(data.batch_count || this.data.recordingBatches || 0),
        recordingRms: data.last_batch_rms !== undefined ? String(data.last_batch_rms) : this.data.recordingRms,
        recordingActive: !!data.recording,
      });
    }
  },

  applyDirectTelemetry(data) {
    const moduleStatuses = data.module_statuses || {};
    const rmsValue = data.rms_value;
    const strength = data.strength !== undefined
      ? Number(data.strength)
      : (rmsValue !== undefined ? Math.min(100, Math.round(Number(rmsValue) / 10)) : this.data.strength);

    this.setData({
      deviceStatus: 'online',
      battery: data.battery_level !== undefined ? Number(data.battery_level) : this.data.battery,
      strength,
      rmsValue: rmsValue !== undefined ? String(rmsValue) : this.data.rmsValue,
      sidePresure: data.side_pressure !== undefined ? String(data.side_pressure) : this.data.sidePresure,
      muscleStatus: data.muscle_status || this.data.muscleStatus,
      predictionResult: data.prediction_result || data.gesture_result || this.data.predictionResult,
      predictionConfidence: data.prediction_confidence !== undefined ? String(data.prediction_confidence) : this.data.predictionConfidence,
      storageStatus: statusText(moduleStatuses.storage || data.storage_status),
      modelStatus: statusText(moduleStatuses.model || data.model_status),
      bluetoothStatus: statusText(moduleStatuses.bluetooth || data.bluetooth_status || data.ble_status),
      cpuStatus: statusText(moduleStatuses.cpu || data.cpu_status),
      lastCommandMessage: data.message || this.data.lastCommandMessage,
      emgPreviewUpdatedAt: data.emg_preview_updated_at || this.data.emgPreviewUpdatedAt,
    });
    this.updateConnectionState('online');
    this.updateArmbandState(moduleStatuses.bluetooth || data.bluetooth_status || data.ble_status);
    this.drawRing('batteryCanvas', (this.data.battery || 0) / 100, '#0B59D6');
    this.drawRing('strengthCanvas', strength / 100, '#1F9D55');

    if (data.emg_preview && data.emg_preview.length) {
      this.applyRealtimeEmgPreview(data.emg_preview, data.emg_preview_updated_at || '');
    }
  },

  async refreshEsp32Info(silent = false) {
    if (!this._boundDevice || !this._boundDevice.ip) return;
    try {
      const info = await esp32Link.fetchInfo(this._boundDevice);
      this.applyDirectTelemetry(info);
      this.setData({
        deviceName: info.name || info.device || this.data.deviceName,
        firmwareVersion: info.firmware || info.firmwareVersion || this.data.firmwareVersion,
        deviceIp: this._boundDevice.ip,
      });
      this.updateConnectionState('online');
      this.updateArmbandState(info.bluetooth_status || info.ble_status || info.module_statuses && info.module_statuses.bluetooth);
    } catch (err) {
      if (!silent) {
        wx.showToast({ title: 'ESP32 信息查询失败', icon: 'none' });
      }
      this.setData({ deviceStatus: 'offline' });
      this.updateConnectionState('offline', 'ESP32 信息请求失败');
    }
  },

  startWifiStatusPolling() {
    if (this._statusTimer) clearInterval(this._statusTimer);
    this._statusTimer = setInterval(() => {
      this.refreshWifiStatus(true);
    }, 1000);
  },

  async refreshWifiStatus(silent = false) {
    if (!this._boundDevice || !this._boundDevice.hardware_id) return;

    try {
      const res = await request({
        url: `/devices/${encodeURIComponent(this._boundDevice.hardware_id)}/status`,
        method: 'GET',
      });

      const device = res.device || {};
      const telemetry = device.telemetry || {};
      const telemetryStrength = telemetry.strength;
      const rmsValue = telemetry.rms_value;
      const sidePressure = telemetry.side_pressure !== undefined ? telemetry.side_pressure : telemetry.side_presure;
      const moduleStatuses = telemetry.module_statuses || {};
      const predictionResult = telemetry.prediction_result || '';
      const predictionConfidence = telemetry.prediction_confidence;
      const collectState = telemetry.collect_state || telemetry.last_collection || {};
      const lastAck = device.last_command_ack || {};
      const emgPreview = telemetry.emg_preview || [];
      const emgPreviewUpdatedAt = telemetry.emg_preview_updated_at || '';

      const strength = telemetryStrength !== undefined
        ? Number(telemetryStrength)
        : (rmsValue !== undefined ? Math.min(100, Math.round(Number(rmsValue) / 10)) : this.data.strength);

      this.setData({
        deviceName: device.device_name || this.data.deviceName,
        deviceStatus: device.status || 'offline',
        deviceIp: device.last_ip || this.data.deviceIp,
        firmwareVersion: device.firmware_version || '',
        battery: device.battery_level !== null && device.battery_level !== undefined ? device.battery_level : this.data.battery,
        strength,
        rmsValue: rmsValue !== undefined && rmsValue !== null ? Number(rmsValue).toFixed(1) : this.data.rmsValue,
        sidePresure: sidePressure !== undefined && sidePressure !== null ? String(sidePressure) : this.data.sidePresure,
        muscleStatus: telemetry.muscle_status || this.data.muscleStatus,
        healthAlert: telemetry.health_alert || telemetry.diagnostics || '',
        lastCommandMessage: lastAck.message || this.data.lastCommandMessage,

        predictionResult,
        predictionConfidence: predictionConfidence !== undefined && predictionConfidence !== null
          ? String(predictionConfidence)
          : '',
        storageStatus: statusText(moduleStatuses.storage),
        modelStatus: statusText(moduleStatuses.model),
        bluetoothStatus: statusText(moduleStatuses.bluetooth),
        cpuStatus: statusText(moduleStatuses.cpu),

        recordingSessionId: collectState.session_id || '',
        recordingSamples: Number(collectState.sample_count || 0),
        recordingBatches: Number(collectState.batch_count || 0),
        recordingRms: collectState.last_batch_rms !== undefined && collectState.last_batch_rms !== null
          ? String(collectState.last_batch_rms)
          : '',
        recordingActive: !!collectState.recording,
        emgPreviewUpdatedAt,
      });
      this.updateConnectionState(device.status || 'offline');
      this.updateArmbandState(moduleStatuses.bluetooth);

      this.drawRing('batteryCanvas', (this.data.battery || 0) / 100, '#0B59D6');
      this.drawRing('strengthCanvas', strength / 100, '#1F9D55');

      if (emgPreview.length) {
        this.applyRealtimeEmgPreview(emgPreview, emgPreviewUpdatedAt);
      }
    } catch (err) {
      if (!silent) {
        wx.showToast({ title: '获取设备状态失败', icon: 'none' });
      }
      this.setData({ deviceStatus: 'offline' });
      this.updateConnectionState('offline', '后端状态请求失败');
      this.updateArmbandState('离线');
    }
  },

  async refreshDeviceStatus() {
    if (this.data.deviceTransport === 'wifi') {
      await this.refreshWifiStatus(false);
      return;
    }

    if (this.data.deviceTransport === 'esp32_direct') {
      await this.refreshEsp32Info(false);
      return;
    }

    this.setData({
      deviceStatus: ble.isConnected() ? 'online' : 'offline',
      lastCommandMessage: ble.isConnected()
        ? '蓝牙已连接，可以直接采集'
        : '蓝牙未连接，请返回绑定页重新连接',
    });
    this.updateConnectionState(ble.isConnected() ? 'online' : 'offline');
    this.updateArmbandState(ble.isConnected() ? 'connected' : 'disconnected');
  },

  switchMode(e) {
    this.setData({ mode: e.currentTarget.dataset.mode });
  },

  addGesture() {
    const emojiOptions = ['🖐️', '🤏', '🤝', '👍', '👌', '☝️'];
    wx.showModal({
      title: '录入动作',
      editable: true,
      placeholderText: '例如：张开、抬腕、夹取',
      success: (res) => {
        if (!res.confirm || !res.content || !res.content.trim()) return;
        const name = res.content.trim();
        const emoji = emojiOptions[this.data.customGestures.length % emojiOptions.length];
        const list = [...this.data.customGestures, { name, emoji }];
        this.setData({
          customGestures: list,
          selectedGestureIndex: list.length - 1,
        });
        wx.setStorageSync('customGestures', list);
      },
    });
  },

  selectGesture(e) {
    this.setData({ selectedGestureIndex: e.currentTarget.dataset.index });
  },

  deleteGesture(e) {
    const index = Number(e.currentTarget.dataset.index);
    wx.showModal({
      title: '删除动作',
      content: '确认从动作管理里删除这个动作吗？已保存的历史采集记录不会自动删除。',
      success: (res) => {
        if (!res.confirm) return;
        const list = this.data.customGestures.filter((_, i) => i !== index);
        this.setData({
          customGestures: list,
          selectedGestureIndex: list.length > 0 ? Math.min(index, list.length - 1) : -1,
        });
        wx.setStorageSync('customGestures', list);
      },
    });
  },

  computeSampleStats(samples) {
    if (!samples || !samples.length) {
      return { rms: 0, strength: 0 };
    }

    let sum = 0;
    let count = 0;
    samples.forEach((row) => row.forEach((value) => {
      const n = Number(value) || 0;
      sum += n * n;
      count += 1;
    }));

    const rms = count ? Math.sqrt(sum / count) : 0;
    return {
      rms,
      strength: Math.min(100, Math.round(rms / 10)),
    };
  },

  drawRing(canvasId, percent, color) {
    const ctx = wx.createCanvasContext(canvasId, this);
    const width = 100;
    const height = 100;
    const radius = 38;
    const lineWidth = 10;
    const cx = width / 2;
    const cy = height / 2;

    ctx.setLineWidth(lineWidth);
    ctx.setStrokeStyle('#E8EEF6');
    ctx.setLineCap('round');
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.stroke();

    ctx.setStrokeStyle(color);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.max(0, Math.min(1, percent)));
    ctx.stroke();
    ctx.draw();
  },

  pushRealtimeSamples(samples) {
    if (!samples || !samples.length) return;
    this._emgSamples = [...this._emgSamples, ...samples].slice(-EMG_CACHE_LIMIT);
    const stats = this.computeSampleStats(samples);
    const rawStats = this.computeRawStats(samples);
    this.setData({
      emgLiveSamples: samples.length,
      emgLiveRms: stats.rms.toFixed(1),
      emgLivePeak: String(this.computePeakAbs(samples).toFixed(0)),
      emgLiveMin: String(rawStats.min),
      emgLiveMax: String(rawStats.max),
    });
    this.drawEmgChart(this._emgSamples);
    this.persistRealtimeEmg();
  },

  applyRealtimeEmgPreview(samples, updatedAt = '') {
    if (!samples || !samples.length) return;
    this._emgSamples = samples.slice(-EMG_CACHE_LIMIT);
    const stats = this.computeSampleStats(samples);
    const rawStats = this.computeRawStats(samples);
    this.setData({
      emgPreviewUpdatedAt: updatedAt || this.data.emgPreviewUpdatedAt,
      emgLiveSamples: samples.length,
      emgLiveRms: stats.rms.toFixed(1),
      emgLivePeak: String(this.computePeakAbs(samples).toFixed(0)),
      emgLiveMin: String(rawStats.min),
      emgLiveMax: String(rawStats.max),
    });
    this.drawEmgChart(this._emgSamples);
    this.persistRealtimeEmg();
  },

  computePeakAbs(samples) {
    let peak = 0;
    (samples || []).forEach((row) => {
      row.forEach((value) => {
        peak = Math.max(peak, Math.abs(Number(value) || 0));
      });
    });
    return peak;
  },

  computeRawStats(samples) {
    const series = this.buildWaveSeries(samples);
    if (!series.length) return { min: '--', max: '--' };
    return {
      min: Math.min(...series).toFixed(0),
      max: Math.max(...series).toFixed(0),
    };
  },

  computeVisualSignal(row) {
    const values = row || [];
    return Number(values[0]) || 0;
  },

  buildWaveSeries(samples) {
    return (samples || []).map((row) => this.computeVisualSignal(row));
  },

  persistRealtimeEmg() {
    if (!this._boundDevice || !this._boundDevice.hardware_id) return;
    wx.setStorageSync(`${EMG_STORAGE_PREFIX}${this._boundDevice.hardware_id}`, {
      samples: this._emgSamples,
      updatedAt: this.data.emgPreviewUpdatedAt || '',
    });
  },

  drawEmgChart(samples, canvasId = 'emgCanvas') {
    const ctx = wx.createCanvasContext(canvasId, this);
    const isHistory = canvasId === 'historyCanvas';
    const width = isHistory ? 320 : 330;
    const height = isHistory ? 130 : 180;
    const paddingLeft = 18;
    const paddingRight = 12;
    const paddingTop = 14;
    const paddingBottom = 20;
    const visible = (samples || []).slice(-EMG_CACHE_LIMIT);
    const plotWidth = width - paddingLeft - paddingRight;
    const plotHeight = height - paddingTop - paddingBottom;
    const series = this.buildWaveSeries(visible);

    ctx.setFillStyle('#061826');
    ctx.fillRect(0, 0, width, height);

    ctx.setStrokeStyle('rgba(255,255,255,0.08)');
    ctx.setLineWidth(1);
    for (let i = 0; i <= 4; i += 1) {
      const y = paddingTop + (plotHeight / 4) * i;
      ctx.beginPath();
      ctx.moveTo(paddingLeft, y);
      ctx.lineTo(width - paddingRight, y);
      ctx.stroke();
    }

    for (let i = 0; i <= 6; i += 1) {
      const x = paddingLeft + (plotWidth / 6) * i;
      ctx.beginPath();
      ctx.moveTo(x, paddingTop);
      ctx.lineTo(x, height - paddingBottom);
      ctx.stroke();
    }

    if (!series.length) {
      ctx.setFillStyle('rgba(255,255,255,0.58)');
      ctx.setFontSize(13);
      ctx.fillText('Waiting for EMG data...', paddingLeft + 70, height / 2 + 4);
      ctx.draw();
      return;
    }

    const min = Math.min(...series);
    const max = Math.max(...series);
    const mean = series.reduce((sum, value) => sum + value, 0) / series.length;
    const maxDeviation = Math.max(...series.map((value) => Math.abs(value - mean)));
    const halfRange = Math.max(12, maxDeviation * 1.25, (max - min) * 0.62);
    const topValue = mean + halfRange;
    const bottomValue = mean - halfRange;
    const valueRange = Math.max(1, topValue - bottomValue);
    const centerY = paddingTop + ((topValue - mean) / valueRange) * plotHeight;

    ctx.setStrokeStyle('rgba(255,255,255,0.2)');
    ctx.beginPath();
    ctx.moveTo(paddingLeft, centerY);
    ctx.lineTo(width - paddingRight, centerY);
    ctx.stroke();

    const strokeColor = this.data.deviceStatus === 'online' ? '#24F2A6' : '#FF6B6B';
    const glowColor = this.data.deviceStatus === 'online'
      ? 'rgba(36, 242, 166, 0.18)'
      : 'rgba(255, 107, 107, 0.15)';

    ctx.beginPath();
    series.forEach((value, index) => {
      const x = paddingLeft + (series.length > 1 ? (index / (series.length - 1)) * plotWidth : 0);
      const y = paddingTop + ((topValue - value) / valueRange) * plotHeight;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.setStrokeStyle(glowColor);
    ctx.setLineWidth(isHistory ? 5 : 7);
    ctx.setLineJoin('round');
    ctx.setLineCap('round');
    ctx.stroke();

    ctx.beginPath();
    series.forEach((value, index) => {
      const x = paddingLeft + (series.length > 1 ? (index / (series.length - 1)) * plotWidth : 0);
      const y = paddingTop + ((topValue - value) / valueRange) * plotHeight;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.setStrokeStyle(strokeColor);
    ctx.setLineWidth(isHistory ? 2 : 2.5);
    ctx.setLineJoin('round');
    ctx.setLineCap('round');
    ctx.stroke();

    ctx.setFillStyle('rgba(255,255,255,0.55)');
    ctx.setFontSize(10);
    ctx.fillText(`max ${Math.round(max)}`, paddingLeft, paddingTop + 9);
    ctx.fillText(`min ${Math.round(min)}`, paddingLeft, height - 8);

    ctx.draw();
  },

  async toggleCollect() {
    if (this.data.isCollecting) {
      await this.stopCollect();
    } else {
      await this.startCollect();
    }
  },

  buildGestureSequence() {
    const actionName = this.data.mode === 'personal' && this.data.selectedGestureIndex >= 0
      ? this.data.customGestures[this.data.selectedGestureIndex].name
      : '目标动作';

    if (this.data.mode === 'personal' && this.data.selectedGestureIndex >= 0) {
      const gesture = this.data.customGestures[this.data.selectedGestureIndex];
      return [
        { emoji: '🌿', name: '放松准备', duration: RELAX_SECONDS },
        { emoji: gesture.emoji || '🖐️', name: actionName, duration: ACTION_SECONDS },
      ];
    }

    return [
      { emoji: '🌿', name: '放松准备', duration: RELAX_SECONDS },
      { emoji: DEFAULT_GESTURES[0].emoji, name: actionName, duration: ACTION_SECONDS },
    ];
  },

  async ensureDeviceOnlineForCollect() {
    const transport = this.data.deviceTransport;
    if (transport !== 'wifi' && transport !== 'esp32_direct') return true;

    if (transport === 'wifi') {
      await this.refreshWifiStatus(true);
    } else {
      await this.refreshEsp32Info(true);
    }

    if (this.data.deviceStatus === 'online') return true;

    wx.showModal({
      title: transport === 'wifi' ? 'ESP32 未在线' : 'ESP32 直连失败',
      content: transport === 'wifi'
        ? '绑定成功只代表后端保存了设备。请确认 ESP32 串口打印 registerBoard status=200 和 heartbeat status=200，并检查 BACKEND_HOST、HARDWARE_ID、BOARD_TOKEN 与小程序绑定值一致。'
        : '请确认手机和 ESP32 在同一 Wi-Fi，且 ESP32 的 /esp32/info 和 WebSocket 服务已开启。',
      showCancel: false,
    });
    return false;
  },

  async startCollect() {
    const online = await this.ensureDeviceOnlineForCollect();
    if (!online) {
      return;
    }

    this._sessionId = `session_${Date.now()}`;
    this._gestureIndex = 0;
    this._collectBuffer = [];
    this._activeGestures = this.buildGestureSequence();
    this._collectStartedAt = Date.now();

    this.setData({
      isCollecting: true,
      hasCollectedData: false,
      lastCommandMessage: '',
      recordingSessionId: this._sessionId,
      recordingSamples: 0,
      recordingBatches: 0,
      recordingRms: '',
      recordingActive: this.data.deviceTransport !== 'ble',
      gestureEmoji: '🌿',
      gestureName: '放松准备',
      collectGuide: '先放松 3 秒，听从提示切换到目标动作。',
      collectElapsedText: `00:00 / 01:00`,
      collectPhase: 'relax',
      countdown: RELAX_SECONDS,
    });

    try {
      if (this.data.deviceTransport === 'wifi') {
        await this.sendWifiCommand('start_collect', {
          mode: this.data.mode,
          session_id: this._sessionId,
          gesture_name: this.data.selectedGestureIndex >= 0
            ? this.data.customGestures[this.data.selectedGestureIndex].name
            : '',
          gestures: this._activeGestures.map((gesture) => ({
            name: gesture.name,
            duration: gesture.duration,
          })),
          phase_rule: '3秒放松 + 3秒目标动作循环',
          max_duration: MAX_COLLECT_SECONDS,
          manual_stop: true,
          emg_upload_path: '/devices/wifi/emg',
        });
        this.setData({ lastCommandMessage: '已通过后端向 ESP32 下发开始采集命令' });
      } else if (this.data.deviceTransport === 'esp32_direct') {
        await esp32Link.sendControl({
          action: 'start_collect',
          mode: this.data.mode,
          session_id: this._sessionId,
          gesture_name: this.data.selectedGestureIndex >= 0
            ? this.data.customGestures[this.data.selectedGestureIndex].name
            : '',
          gestures: this._activeGestures.map((gesture) => ({
            name: gesture.name,
            duration: gesture.duration,
          })),
          phase_rule: '3秒放松 + 3秒目标动作循环',
          max_duration: MAX_COLLECT_SECONDS,
          manual_stop: true,
        });
        this.setData({ lastCommandMessage: '已通过 WebSocket 向 ESP32 下发开始采集命令' });
      } else if (ble.isConnected()) {
        await ble.sendCommand(0x0A);
      }
    } catch (err) {
      this.setData({ isCollecting: false, recordingActive: false });
      wx.showToast({ title: '开始采集失败', icon: 'none' });
      return;
    }

    this.playGestureGuide();
  },

  playGestureGuide() {
    if (this._collectTimer) {
      clearInterval(this._collectTimer);
      this._collectTimer = null;
    }

    this.updateCollectGuide();
    this._collectTimer = setInterval(() => {
      this.updateCollectGuide();
    }, 1000);
  },

  updateCollectGuide() {
    if (!this.data.isCollecting || !this._collectStartedAt) return;

    const elapsed = Math.floor((Date.now() - this._collectStartedAt) / 1000);
    if (elapsed >= MAX_COLLECT_SECONDS) {
      wx.showToast({ title: '已达到 1 分钟，自动停止采集', icon: 'none' });
      this.stopCollect();
      return;
    }

    const cycle = RELAX_SECONDS + ACTION_SECONDS;
    const cycleOffset = elapsed % cycle;
    const isRelaxPhase = cycleOffset < RELAX_SECONDS;
    const secondsLeft = isRelaxPhase
      ? RELAX_SECONDS - cycleOffset
      : cycle - cycleOffset;
    const actionGesture = this._activeGestures[1] || DEFAULT_GESTURES[0];
    const elapsedText = `00:${String(Math.min(elapsed, MAX_COLLECT_SECONDS)).padStart(2, '0')} / 01:00`;

    this.setData({
      gestureEmoji: isRelaxPhase ? '🌿' : '🖐️',
      gestureName: isRelaxPhase ? '放松 3 秒' : `执行动作：${actionGesture.name}`,
      collectGuide: isRelaxPhase
        ? '手臂自然放松，不要主动用力。'
        : '保持目标动作，力度尽量稳定。',
      collectElapsedText: elapsedText,
      collectPhase: isRelaxPhase ? 'relax' : 'action',
      countdown: secondsLeft,
    });
  },

  async stopCollect() {
    if (this._collectTimer) {
      clearInterval(this._collectTimer);
      this._collectTimer = null;
    }
    this._collectStartedAt = 0;

    if (this.data.deviceTransport === 'wifi') {
      try {
        await this.sendWifiCommand('stop_collect', { session_id: this._sessionId });
        this.setData({ lastCommandMessage: '已通过后端向 ESP32 下发停止采集命令' });
      } catch (e) {}
    } else if (this.data.deviceTransport === 'esp32_direct') {
      try {
        await esp32Link.sendControl({
          action: 'stop_collect',
          session_id: this._sessionId,
        });
        this.setData({ lastCommandMessage: '已通过 WebSocket 向 ESP32 下发停止采集命令' });
      } catch (e) {}
    } else if (ble.isConnected()) {
      ble.sendCommand(0x0B).catch(() => {});
    }

    const hasLocalData = this.data.deviceTransport === 'ble' && this._collectBuffer.length > 0;
    this.setData({
      isCollecting: false,
      gestureEmoji: '🌿',
      gestureName: this.data.deviceTransport === 'ble' ? '采集完成' : '等待设备返回结果',
      collectGuide: '一次采集已结束，可以查看波形和存储记录。',
      collectElapsedText: '最长 1 分钟，可随时停止',
      collectPhase: 'idle',
      countdown: 0,
      hasCollectedData: hasLocalData,
      recordingActive: false,
    });

    if (hasLocalData) {
      this.saveToTempFile();
    }
  },

  saveToTempFile() {
    const flat = [];
    this._collectBuffer.forEach((row) => row.forEach((value) => flat.push(value)));
    const int16 = new Int16Array(flat);
    const filePath = `${TEMP_DIR}/${this._sessionId}.dat`;
    fs.writeFileSync(filePath, int16.buffer, 'binary');
    this._tempFilePath = filePath;
  },

  async sendWifiCommand(action, payload) {
    if (!this._boundDevice || !this._boundDevice.hardware_id) {
      throw new Error('未绑定 Wi-Fi 设备');
    }

    return request({
      url: `/devices/${encodeURIComponent(this._boundDevice.hardware_id)}/command`,
      method: 'POST',
      data: { action, payload },
    });
  },

  async startUpload() {
    if (!this.data.canUpload) {
      wx.showToast({ title: '当前模式不需要本地上传', icon: 'none' });
      return;
    }
    if (!this._tempFilePath) return;

    const fileInfo = fs.statSync(this._tempFilePath);
    const chunkSize = 256 * 1024;
    const totalChunks = Math.ceil(fileInfo.size / chunkSize);

    this.setData({
      isUploading: true,
      uploadProgress: 0,
      uploadedChunks: 0,
      totalChunks,
    });

    try {
      for (let i = 0; i < totalChunks; i += 1) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, fileInfo.size);
        const chunkData = fs.readFileSync(this._tempFilePath, 'binary', start, end);
        const chunkPath = `${TEMP_DIR}/${this._sessionId}_chunk_${i}.dat`;
        fs.writeFileSync(chunkPath, chunkData, 'binary');

        await uploadChunk('/upload/chunk', chunkPath, {
          session_id: this._sessionId,
          chunk_index: String(i),
        });

        try {
          fs.unlinkSync(chunkPath);
        } catch (e) {}

        const uploaded = i + 1;
        this.setData({
          uploadedChunks: uploaded,
          uploadProgress: Math.round((uploaded / totalChunks) * 100),
        });
      }

      await request({
        url: '/upload/merge',
        method: 'POST',
        data: {
          session_id: this._sessionId,
          total_chunks: totalChunks,
          gesture_name: this.data.gestureName,
        },
      });

      wx.showToast({ title: '上传成功', icon: 'success' });
      this.setData({ hasCollectedData: false });
      this.loadStoredSessions(true);
    } catch (err) {
      wx.showToast({ title: '上传失败，请重试', icon: 'none' });
    } finally {
      this.setData({ isUploading: false });
    }
  },

  generateReport() {
    wx.showLoading({ title: '生成报告中...' });
    request({
      url: '/health/report/generate',
      method: 'POST',
      data: {},
    })
      .then((res) => {
        wx.hideLoading();
        this.setData({
          rmsValue: res.rms_value !== undefined ? String(res.rms_value) : this.data.rmsValue,
          sidePresure: res.side_presure !== undefined ? String(res.side_presure) : this.data.sidePresure,
          muscleStatus: res.muscle_status || this.data.muscleStatus,
          healthAlert: res.diagnostics || '',
        });
      })
      .catch(() => {
        wx.hideLoading();
        wx.showToast({ title: '报告生成失败', icon: 'none' });
      });
  },

  dismissAlert() {
    this.setData({ healthAlert: '' });
  },
});

