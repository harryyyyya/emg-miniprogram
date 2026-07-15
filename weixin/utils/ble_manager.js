/**
 * ble_manager.js - 高频 BLE 通讯管理器
 * 适配 ESP32-S3 (8通道, 500Hz)
 * 特性: 环形缓冲区 + 200ms 窗口处理 + Mock 数据流
 */
const protocol = require('./protocol');

// ========== BLE 服务/特征 UUID (与 ESP32 固件对齐) ==========
const SERVICE_UUID = '0000FFE0-0000-1000-8000-00805F9B34FB';
const NOTIFY_CHAR_UUID = '0000FF02-0000-1000-8000-00805F9B34FB'; // 数据上行 Notify
const WRITE_CHAR_UUID = '0000FF01-0000-1000-8000-00805F9B34FB';  // 指令下发 Write

// ========== 环形缓冲区 ==========
const RING_BUFFER_SIZE = 4096; // 字节
let ringBuffer = new Uint8Array(RING_BUFFER_SIZE);
let writePos = 0;
let readPos = 0;

function ringBufferWrite(data) {
  const u8 = new Uint8Array(data);
  for (let i = 0; i < u8.length; i++) {
    ringBuffer[writePos % RING_BUFFER_SIZE] = u8[i];
    writePos++;
  }
}

function ringBufferRead(length) {
  const available = writePos - readPos;
  const toRead = Math.min(length, available);
  const out = new Uint8Array(toRead);
  for (let i = 0; i < toRead; i++) {
    out[i] = ringBuffer[(readPos + i) % RING_BUFFER_SIZE];
  }
  readPos += toRead;
  return out;
}

function ringBufferAvailable() {
  return writePos - readPos;
}

function ringBufferReset() {
  writePos = 0;
  readPos = 0;
}

// ========== 状态 ==========
let _deviceId = null;
let _connected = false;
let _notifyTimer = null;
let _mockTimer = null;
let _onDataCallback = null;    // 外部回调：接收解析后的 EMG 样本
let _onStatusCallback = null;  // 连接状态回调
let _useMock = false;

// ========== 公共 API ==========

/**
 * 扫描并连接指定设备
 * @param {string} targetName 设备广播名 / MAC
 */
function connectDevice(targetName) {
  return new Promise((resolve, reject) => {
    wx.openBluetoothAdapter({
      success() {
        wx.startBluetoothDevicesDiscovery({
          allowDuplicatesKey: false,
          success() {
            wx.onBluetoothDeviceFound((res) => {
              const device = res.devices.find(
                (d) => d.name === targetName || d.localName === targetName || d.deviceId === targetName
              );
              if (device) {
                wx.stopBluetoothDevicesDiscovery();
                _createConnection(device.deviceId).then(resolve).catch(reject);
              }
            });
            // 10s 超时
            setTimeout(() => {
              wx.stopBluetoothDevicesDiscovery();
              reject(new Error('扫描超时，未找到设备'));
            }, 10000);
          },
          fail: reject,
        });
      },
      fail: reject,
    });
  });
}

function _createConnection(deviceId) {
  return new Promise((resolve, reject) => {
    wx.createBLEConnection({
      deviceId,
      success() {
        _deviceId = deviceId;
        // 请求 MTU 247
        wx.setBLEMTU({
          deviceId,
          mtu: 247,
          success() { console.log('[BLE] MTU set to 247'); },
          fail(e) { console.warn('[BLE] MTU negotiation failed', e); },
        });

        // 延迟后开启 Notify
        setTimeout(() => {
          _enableNotify(deviceId).then(() => {
            _connected = true;
            _fireStatus('connected');
            _startProcessLoop();
            resolve({ deviceId });
          }).catch(reject);
        }, 500);
      },
      fail: reject,
    });
  });
}

function _enableNotify(deviceId) {
  return new Promise((resolve, reject) => {
    wx.getBLEDeviceServices({
      deviceId,
      success(sRes) {
        const svc = sRes.services.find((s) => s.uuid.toUpperCase().includes('FFE0'));
        if (!svc) return reject(new Error('未找到目标服务'));
        wx.getBLEDeviceCharacteristics({
          deviceId,
          serviceId: svc.uuid,
          success(cRes) {
            const notifyChar = cRes.characteristics.find(
              (c) => c.uuid.toUpperCase().includes('FF02') && c.properties.notify
            );
            if (!notifyChar) return reject(new Error('未找到 Notify 特征'));
            wx.notifyBLECharacteristicValueChange({
              deviceId,
              serviceId: svc.uuid,
              characteristicId: notifyChar.uuid,
              state: true,
              success() {
                // 监听数据
                wx.onBLECharacteristicValueChange((charRes) => {
                  ringBufferWrite(charRes.value);
                });
                resolve();
              },
              fail: reject,
            });
          },
          fail: reject,
        });
      },
      fail: reject,
    });
  });
}

/**
 * 每 200ms 处理一次环形缓冲区中的数据 (窗口处理)
 */
function _startProcessLoop() {
  _notifyTimer = setInterval(() => {
    if (ringBufferAvailable() < 6) return; // 最小帧长度
    const raw = ringBufferRead(ringBufferAvailable());
    // 尝试在 raw 中找到完整帧
    _extractFrames(raw);
  }, 200);
}

function _extractFrames(data) {
  let i = 0;
  while (i < data.length) {
    if (data[i] !== protocol.HEADER) { i++; continue; }
    // 找到 TAIL
    let tailIdx = -1;
    for (let j = i + 6; j < data.length; j++) {
      if (data[j] === protocol.TAIL) { tailIdx = j; break; }
    }
    if (tailIdx === -1) break; // 不完整帧，等待下次

    const frameSlice = data.slice(i, tailIdx + 1);
    const result = protocol.unpackFrame(frameSlice.buffer);
    if (result.valid && _onDataCallback) {
      const samples = protocol.parseEMGPayload(result.payload);
      _onDataCallback(samples);
    }
    i = tailIdx + 1;
  }
}

/**
 * 向设备发送指令 (如 0x0A 开始采集)
 * @param {number} cmdByte
 */
function sendCommand(cmdByte) {
  if (!_connected || !_deviceId) {
    console.warn('[BLE] 未连接，无法发送指令');
    return Promise.reject(new Error('设备未连接'));
  }
  const cmdBuffer = protocol.buildCommand(cmdByte);
  return new Promise((resolve, reject) => {
    wx.getBLEDeviceServices({
      deviceId: _deviceId,
      success(sRes) {
        const svc = sRes.services.find((s) => s.uuid.toUpperCase().includes('FFE0'));
        if (!svc) return reject(new Error('服务未找到'));
        wx.getBLEDeviceCharacteristics({
          deviceId: _deviceId,
          serviceId: svc.uuid,
          success(cRes) {
            const writeChar = cRes.characteristics.find(
              (c) => c.uuid.toUpperCase().includes('FF01') && (c.properties.write || c.properties.writeNoResponse)
            );
            if (!writeChar) return reject(new Error('Write 特征未找到'));
            wx.writeBLECharacteristicValue({
              deviceId: _deviceId,
              serviceId: svc.uuid,
              characteristicId: writeChar.uuid,
              value: cmdBuffer,
              success: resolve,
              fail: reject,
            });
          },
          fail: reject,
        });
      },
      fail: reject,
    });
  });
}

/**
 * 断开连接
 */
function disconnect() {
  if (_notifyTimer) { clearInterval(_notifyTimer); _notifyTimer = null; }
  stopMock();
  ringBufferReset();
  if (_deviceId) {
    wx.closeBLEConnection({ deviceId: _deviceId });
  }
  _connected = false;
  _deviceId = null;
  _fireStatus('disconnected');
}

// ========== Mock 数据流 (无硬件调试用) ==========
function startMock() {
  _useMock = true;
  _connected = true;
  _fireStatus('connected');
  _mockTimer = setInterval(() => {
    // 模拟 8 通道，每 200ms 产生 100 个采样点 (500Hz * 0.2s)
    const CHANNELS = 8;
    const SAMPLES = 100;
    const samples = [];
    for (let s = 0; s < SAMPLES; s++) {
      const row = [];
      for (let ch = 0; ch < CHANNELS; ch++) {
        row.push(Math.round((Math.random() - 0.5) * 2000)); // ±1000 模拟肌电信号
      }
      samples.push(row);
    }
    if (_onDataCallback) _onDataCallback(samples);
  }, 200);
}

function stopMock() {
  if (_mockTimer) { clearInterval(_mockTimer); _mockTimer = null; }
  _useMock = false;
}

// ========== 回调注册 ==========
function onData(cb) { _onDataCallback = cb; }
function onStatus(cb) { _onStatusCallback = cb; }
function _fireStatus(status) {
  if (_onStatusCallback) _onStatusCallback(status);
}
function isConnected() { return _connected; }
function getDeviceId() { return _deviceId; }

module.exports = {
  connectDevice,
  sendCommand,
  disconnect,
  startMock,
  stopMock,
  onData,
  onStatus,
  isConnected,
  getDeviceId,
};
