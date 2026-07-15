const ble = require('../../utils/ble_manager');
const { request } = require('../../utils/request');
const esp32Link = require('../../utils/esp32_link');

function buildStoredDevice(device, extras = {}) {
  const name = device.device_name || device.name || device.hardware_id || extras.hardware_id || '';
  return {
    name,
    deviceName: name,
    hardware_id: device.hardware_id || extras.hardware_id || '',
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
    transportMode: 'ble',
    step: 'scan',
    targetDevice: '',
    failMsg: '',
    wifiForm: {
      hardwareId: '',
      boardToken: '',
      deviceName: '',
    },
    esp32Form: {
      ip: '',
      deviceId: '',
      token: '',
      vendor: '',
      name: '',
      httpPort: '80',
      wsPort: '81',
    },
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
        wx.showToast({ title: '扫码已取消', icon: 'none' });
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
          wx.showToast({ title: '二维码中没有设备信息', icon: 'none' });
          return;
        }
        this.setData({
          wifiForm: {
            hardwareId: payload.hardware_id || '',
            boardToken: payload.board_token || '',
            deviceName: payload.device_name || payload.name || '',
          },
        });
      },
      fail: () => {
        wx.showToast({ title: '扫码已取消', icon: 'none' });
      },
    });
  },

  scanEsp32QrCode() {
    wx.scanCode({
      scanType: ['qrCode'],
      success: (res) => {
        const payload = parseWifiPayload(res.result);
        if (!payload || !payload.ip) {
          wx.showToast({ title: '二维码中没有 ESP32 IP', icon: 'none' });
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
        wx.showToast({ title: '扫码已取消', icon: 'none' });
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
      wx.showToast({ title: '请输入板端密钥', icon: 'none' });
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
        },
      });

      const storedDevice = buildStoredDevice(res.device || {}, {
        hardware_id: hardwareId,
        transport: 'wifi',
      });
      wx.setStorageSync('boundDevice', storedDevice);
      this.setData({ step: 'success' });
    } catch (err) {
      this.setData({
        step: 'fail',
        failMsg: (err && err.detail) || 'ESP32 设备绑定失败，请检查后端连接和设备编号',
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
        failMsg: err.message || 'ESP32 直连校验失败，请检查 IP、设备接口和身份信息',
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
        this.setData({ step: 'success' });
      })
      .catch((err) => {
        this.setData({
          step: 'fail',
          failMsg: err.message || '蓝牙连接失败，请检查设备是否已经开机',
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
