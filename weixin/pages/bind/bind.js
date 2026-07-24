const ble = require('../../utils/ble_manager');
const { request } = require('../../utils/request');
const esp32Link = require('../../utils/esp32_link');

const WIFI_DEVICE_PRESETS = [
  {
    key: 'milk_duo_s',
    label: 'Milk Duo S',
    hardwareId: 'DUOS-WIFI-001',
    boardToken: 'duos-secret',
    deviceName: '我的 Milk Duo S 智能假手',
  },
  {
    key: 'esp32',
    label: 'ESP32',
    hardwareId: 'ESP32-HAND-001',
    boardToken: 'esp32-secret',
    deviceName: '我的 ESP32 智能假手',
  },
];

const DEFAULT_WIFI_DEVICE = WIFI_DEVICE_PRESETS[0];

function getWifiPreset(key) {
  return WIFI_DEVICE_PRESETS.find((item) => item.key === key) || DEFAULT_WIFI_DEVICE;
}

function inferBoardType(device = {}, extras = {}) {
  const text = [
    device.board_type,
    extras.board_type,
    device.hardware_id,
    extras.hardware_id,
    device.device_name,
    device.name,
  ].filter(Boolean).join(' ').toLowerCase();
  if (text.includes('milk') || text.includes('duo') || text.includes('duos')) return 'milk_duo_s';
  if (text.includes('esp32')) return 'esp32';
  return (device.transport || extras.transport) === 'wifi' ? 'wifi_board' : 'ble';
}

function boardLabel(boardType) {
  const labels = {
    milk_duo_s: 'Milk Duo S',
    esp32: 'ESP32',
    wifi_board: 'Wi-Fi 板子',
    ble: '蓝牙设备',
  };
  return labels[boardType] || '智能设备';
}

const DEFAULT_DIRECT_DEVICE = {
  ip: '',
  deviceId: 'ESP32-HAND-001',
  token: 'esp32-secret',
  vendor: '',
  name: '我的智能假手',
  httpPort: '80',
  wsPort: '81',
};

function buildStoredDevice(device, extras = {}) {
  const name = device.device_name || device.name || device.hardware_id || extras.hardware_id || '';
  const board_type = device.board_type || extras.board_type || inferBoardType(device, extras);
  return {
    name,
    deviceName: name,
    hardware_id: device.hardware_id || extras.hardware_id || '',
    board_type,
    board_label: device.board_label || extras.board_label || boardLabel(board_type),
    transport: device.transport || extras.transport || 'ble',
    bindTime: Date.now(),
    status: device.status || extras.status || 'offline',
    deviceId: extras.deviceId || '',
    wifi_host: device.wifi_host || extras.wifi_host || '',
    wifi_port: device.wifi_port || extras.wifi_port || 0,
    ip: extras.ip || device.ip || '',
    httpPort: extras.httpPort || 80,
    wsPort: extras.wsPort || 81,
    wsPath: extras.wsPath || '/esp32',
    infoPath: extras.infoPath || '/esp32/info',
    cmdPath: extras.cmdPath || '/esp32/cmd',
    token: extras.token || '',
    vendor: extras.vendor || '',
  };
}

function parseWifiPayload(rawText) {
  const text = (rawText || '').trim();
  if (!text) return null;

  try {
    const parsed = JSON.parse(text);
    if (parsed) return parsed;
  } catch (e) {}

  const queryIndex = text.indexOf('?');
  const queryText = queryIndex >= 0 ? text.slice(queryIndex + 1) : text;
  const segments = queryText.split('&');
  const kv = {};
  segments.forEach((segment) => {
    const [key, value = ''] = segment.split('=');
    if (key) kv[decodeURIComponent(key)] = decodeURIComponent(value);
  });
  return kv;
}

Page({
  data: {
    transportMode: 'wifi',
    step: 'scan',
    targetDevice: '',
    failMsg: '',
    showWifiAdvanced: false,
    showDirectAdvanced: false,
    wifiPresets: WIFI_DEVICE_PRESETS,
    wifiBoardType: DEFAULT_WIFI_DEVICE.key,
    wifiForm: { ...DEFAULT_WIFI_DEVICE },
    esp32Form: { ...DEFAULT_DIRECT_DEVICE },
  },

  switchTransport(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({
      transportMode: mode,
      step: 'scan',
      targetDevice: '',
      failMsg: '',
    });
  },

  fillDefaultWifiDevice() {
    const preset = getWifiPreset(this.data.wifiBoardType);
    this.setData({
      wifiForm: { ...preset },
      failMsg: '',
    });
  },

  selectWifiPreset(e) {
    const boardType = e.currentTarget.dataset.type || DEFAULT_WIFI_DEVICE.key;
    const preset = getWifiPreset(boardType);
    this.setData({
      wifiBoardType: preset.key,
      wifiForm: { ...preset },
      failMsg: '',
    });
  },

  quickBindWifiDevice() {
    this.fillDefaultWifiDevice();
    this.bindWifiDevice();
  },

  toggleWifiAdvanced() {
    this.setData({ showWifiAdvanced: !this.data.showWifiAdvanced });
  },

  toggleDirectAdvanced() {
    this.setData({ showDirectAdvanced: !this.data.showDirectAdvanced });
  },

  startScan() {
    if (this.data.transportMode === 'wifi') {
      this.scanWifiQrCode();
      return;
    }
    if (this.data.transportMode === 'esp32_direct') {
      this.scanEsp32QrCode();
      return;
    }

    wx.scanCode({
      scanType: ['qrCode'],
      success: (res) => {
        const deviceIdentifier = (res.result || '').trim();
        if (!deviceIdentifier) {
          wx.showToast({ title: '二维码内容为空', icon: 'none' });
          return;
        }
        this.setData({ targetDevice: deviceIdentifier, step: 'searching' });
        this.connectBle(deviceIdentifier);
      },
      fail: () => {
        wx.showToast({ title: '已取消扫码', icon: 'none' });
      },
    });
  },

  manualInput() {
    wx.showModal({
      title: '手动输入',
      editable: true,
      placeholderText: '请输入 BLE 广播名或 MAC 地址',
      success: (res) => {
        if (res.confirm && res.content) {
          const value = res.content.trim();
          this.setData({ targetDevice: value, step: 'searching' });
          this.connectBle(value);
        }
      },
    });
  },

  scanWifiQrCode() {
    wx.scanCode({
      scanType: ['qrCode'],
      success: (res) => {
        const payload = parseWifiPayload(res.result);
        if (!payload || !payload.hardware_id) {
          wx.showToast({ title: '二维码里没有设备信息', icon: 'none' });
          return;
        }
        const boardType = inferBoardType({
          board_type: payload.board_type || payload.platform,
          hardware_id: payload.hardware_id,
          device_name: payload.device_name || payload.name,
        }, {});
        this.setData({
          wifiBoardType: boardType === 'milk_duo_s' ? 'milk_duo_s' : 'esp32',
          wifiForm: {
            hardwareId: payload.hardware_id || '',
            boardToken: payload.board_token || '',
            deviceName: payload.device_name || payload.name || '',
          },
        });
      },
      fail: () => {
        wx.showToast({ title: '已取消扫码', icon: 'none' });
      },
    });
  },

  scanEsp32QrCode() {
    wx.scanCode({
      scanType: ['qrCode'],
      success: (res) => {
        const payload = parseWifiPayload(res.result);
        if (!payload || !payload.ip) {
          wx.showToast({ title: '二维码里没有 ESP32 IP', icon: 'none' });
          return;
        }
        this.setData({
          esp32Form: {
            ip: payload.ip || '',
            deviceId: payload.deviceId || payload.device_id || '',
            token: payload.token || '',
            vendor: payload.vendor || '',
            name: payload.name || '',
            httpPort: String(payload.httpPort || payload.http_port || 80),
            wsPort: String(payload.wsPort || payload.ws_port || 81),
          },
        });
      },
      fail: () => {
        wx.showToast({ title: '已取消扫码', icon: 'none' });
      },
    });
  },

  onWifiInput(e) {
    const field = e.currentTarget.dataset.field;
    const wifiForm = { ...this.data.wifiForm, [field]: e.detail.value };
    this.setData({ wifiForm });
  },

  onEsp32Input(e) {
    const field = e.currentTarget.dataset.field;
    const esp32Form = { ...this.data.esp32Form, [field]: e.detail.value };
    this.setData({ esp32Form });
  },

  async bindWifiDevice() {
    const hardwareId = this.data.wifiForm.hardwareId.trim();
    const boardToken = this.data.wifiForm.boardToken.trim();
    const deviceName = this.data.wifiForm.deviceName.trim();

    if (!hardwareId) {
      wx.showToast({ title: '请输入设备编号', icon: 'none' });
      return;
    }
    if (!boardToken) {
      wx.showToast({ title: '请输入设备密钥', icon: 'none' });
      return;
    }

    this.setData({
      step: 'searching',
      targetDevice: hardwareId,
      failMsg: '',
    });

    try {
      const res = await request({
        url: '/devices/bind',
        method: 'POST',
        data: {
          hardware_id: hardwareId,
          transport: 'wifi',
          board_token: boardToken,
          device_name: deviceName || hardwareId,
          board_type: this.data.wifiBoardType,
        },
      });

      const storedDevice = buildStoredDevice(res.device || {}, {
        hardware_id: hardwareId,
        transport: 'wifi',
        board_type: this.data.wifiBoardType,
      });
      wx.setStorageSync('boundDevice', storedDevice);
      this.setData({ step: 'success', targetDevice: storedDevice.name || hardwareId });
    } catch (err) {
      this.setData({
        step: 'fail',
        failMsg: (err && err.detail) || 'Wi-Fi 设备绑定失败，请检查登录状态、后端连接、设备编号和密钥。',
      });
    }
  },

  async bindEsp32Direct() {
    const form = this.data.esp32Form;
    const ip = form.ip.trim();
    const deviceId = form.deviceId.trim();
    const token = form.token.trim();
    const vendor = form.vendor.trim();
    const name = form.name.trim();
    const httpPort = form.httpPort.trim() || '80';
    const wsPort = form.wsPort.trim() || '81';

    if (!ip) {
      wx.showToast({ title: '请输入 ESP32 的 IP', icon: 'none' });
      return;
    }

    const config = {
      ip,
      deviceId,
      token,
      vendor,
      name,
      httpPort,
      wsPort,
      wsPath: '/esp32',
      infoPath: '/esp32/info',
      cmdPath: '/esp32/cmd',
    };

    this.setData({
      step: 'searching',
      targetDevice: ip,
      failMsg: '',
    });

    try {
      const info = await esp32Link.fetchInfo(config);
      esp32Link.validateDeviceInfo(info, config);
      const normalized = esp32Link.normalizeDeviceInfo(info, ip, config);
      wx.setStorageSync('boundDevice', normalized);
      esp32Link.setCurrentConfig(normalized);
      this.setData({
        step: 'success',
        targetDevice: normalized.name || normalized.deviceId || ip,
      });
    } catch (err) {
      this.setData({
        step: 'fail',
        failMsg: err.message || 'ESP32 直连校验失败，请检查手机和 ESP32 是否在同一 Wi-Fi，以及 IP 和端口是否正确。',
      });
    }
  },

  connectBle(name) {
    ble.connectDevice(name)
      .then(async (result) => {
        const res = await request({
          url: '/devices/bind',
          method: 'POST',
          data: {
            hardware_id: name,
            transport: 'ble',
            device_name: name,
          },
        }).catch(() => null);

        const storedDevice = buildStoredDevice((res && res.device) || {}, {
          hardware_id: name,
          transport: 'ble',
          status: 'online',
          deviceId: result.deviceId,
        });

        wx.setStorageSync('boundDevice', storedDevice);
        this.setData({ step: 'success', targetDevice: storedDevice.name || name });
      })
      .catch((err) => {
        this.setData({
          step: 'fail',
          failMsg: err.message || '蓝牙连接失败，请检查设备是否开机并在蓝牙范围内。',
        });
      });
  },

  retry() {
    this.setData({ step: 'scan', targetDevice: '', failMsg: '' });
  },

  goHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
