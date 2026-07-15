let socketTask = null;
let currentConfig = null;
let socketOpen = false;
let messageHandler = null;
let statusHandler = null;

function normalizePort(value, fallback) {
  const port = Number(value);
  return Number.isFinite(port) && port > 0 ? port : fallback;
}

function parseJsonSafe(text) {
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

function setStatus(status, extra = {}) {
  if (typeof statusHandler === 'function') {
    statusHandler({ status, ...extra });
  }
}

function normalizeDeviceInfo(data, ip, defaults = {}) {
  return {
    transport: 'esp32_direct',
    name: data.name || data.device || defaults.name || data.deviceId || defaults.deviceId || ip,
    deviceName: data.name || data.device || defaults.name || data.deviceId || defaults.deviceId || ip,
    hardware_id: data.deviceId || defaults.deviceId || ip,
    deviceId: data.deviceId || defaults.deviceId || ip,
    ip,
    httpPort: normalizePort(data.httpPort || defaults.httpPort, 80),
    wsPort: normalizePort(data.wsPort || defaults.wsPort, 81),
    wsPath: data.wsPath || defaults.wsPath || '/esp32',
    infoPath: data.infoPath || defaults.infoPath || '/esp32/info',
    cmdPath: data.cmdPath || defaults.cmdPath || '/esp32/cmd',
    token: data.token || defaults.token || '',
    vendor: data.vendor || defaults.vendor || '',
    bindTime: Date.now(),
    status: 'online',
  };
}

function buildHttpUrl(config, path) {
  return `http://${config.ip}:${normalizePort(config.httpPort, 80)}${path}`;
}

function buildWsUrl(config) {
  return `ws://${config.ip}:${normalizePort(config.wsPort, 81)}${config.wsPath || '/esp32'}`;
}

function getSavedConfig() {
  if (currentConfig) return currentConfig;
  const device = wx.getStorageSync('boundDevice');
  if (device && device.transport === 'esp32_direct') {
    currentConfig = device;
    return currentConfig;
  }
  return null;
}

function setCurrentConfig(config) {
  currentConfig = config;
}

function onMessage(handler) {
  messageHandler = handler;
}

function onStatus(handler) {
  statusHandler = handler;
}

function fetchInfo(config) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: buildHttpUrl(config, config.infoPath || '/esp32/info'),
      method: 'GET',
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data || {});
        } else {
          reject(new Error((res.data && (res.data.message || res.data.detail)) || '设备信息查询失败'));
        }
      },
      fail: reject,
    });
  });
}

function validateDeviceInfo(info, config) {
  const expectedId = config.deviceId || config.hardware_id || '';
  if (expectedId && info.deviceId && info.deviceId !== expectedId) {
    throw new Error('deviceId 不匹配');
  }
  if (config.vendor && info.vendor && info.vendor !== config.vendor) {
    throw new Error('vendor 不匹配');
  }
  return true;
}

function connect(config) {
  setCurrentConfig(config);
  return new Promise((resolve, reject) => {
    if (socketTask) {
      try {
        socketTask.close({});
      } catch (e) {}
      socketTask = null;
    }

    socketOpen = false;
    setStatus('connecting', { ip: config.ip });
    const url = buildWsUrl(config);
    const task = wx.connectSocket({ url });
    socketTask = task;

    task.onOpen(() => {
      socketOpen = true;
      setStatus('online', { ip: config.ip });
      resolve(true);
    });

    task.onMessage((res) => {
      const msg = typeof res.data === 'string' ? parseJsonSafe(res.data) : res.data;
      if (!msg) return;
      if (msg.deviceId && currentConfig && currentConfig.deviceId && msg.deviceId !== currentConfig.deviceId) {
        return;
      }
      if (currentConfig && currentConfig.token && msg.token && msg.token !== currentConfig.token) {
        return;
      }
      if (typeof messageHandler === 'function') {
        messageHandler(msg);
      }
    });

    task.onClose(() => {
      socketOpen = false;
      setStatus('offline');
    });

    task.onError((err) => {
      socketOpen = false;
      setStatus('error', { error: err });
      reject(err);
    });
  });
}

function disconnect() {
  if (socketTask) {
    try {
      socketTask.close({});
    } catch (e) {}
  }
  socketTask = null;
  socketOpen = false;
  setStatus('offline');
}

function ensureConnected() {
  if (socketOpen) return Promise.resolve(true);
  const config = getSavedConfig();
  if (!config) return Promise.reject(new Error('未找到已保存的 ESP32 直连配置'));
  return connect(config);
}

function send(data) {
  return ensureConnected().then(() => new Promise((resolve, reject) => {
    socketTask.send({
      data: JSON.stringify(data),
      success: resolve,
      fail: reject,
    });
  }));
}

function sendControl(data, seq = Date.now()) {
  const config = getSavedConfig();
  return send({
    type: 'control',
    seq,
    deviceId: config ? config.deviceId : '',
    token: config ? config.token || '' : '',
    data,
  });
}

module.exports = {
  normalizeDeviceInfo,
  fetchInfo,
  validateDeviceInfo,
  connect,
  disconnect,
  send,
  sendControl,
  onMessage,
  onStatus,
  getSavedConfig,
  setCurrentConfig,
};
