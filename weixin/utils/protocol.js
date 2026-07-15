/**
 * protocol.js - 与后端 utils.py ProtocolUtils 100% 对齐的 CRC32 / 帧协议模块
 * 帧格式: [0xAA] [payload bytes] [CRC32 4字节 little-endian] [0x55]
 */

const HEADER = 0xAA;
const TAIL = 0x55;

// ========== 标准 CRC32 查找表 (与 Python zlib.crc32 一致) ==========
const CRC32_TABLE = new Uint32Array(256);
(function buildTable() {
  for (let i = 0; i < 256; i++) {
    let crc = i;
    for (let j = 0; j < 8; j++) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xEDB88320 : crc >>> 1;
    }
    CRC32_TABLE[i] = crc >>> 0;
  }
})();

/**
 * 计算 CRC32，结果与 Python 的 zlib.crc32(data) & 0xFFFFFFFF 完全一致
 * @param {Uint8Array} uint8arr
 * @returns {number} 32bit unsigned CRC
 */
function calculateCRC32(uint8arr) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < uint8arr.length; i++) {
    crc = (crc >>> 8) ^ CRC32_TABLE[(crc ^ uint8arr[i]) & 0xFF];
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

/**
 * 校验 CRC32
 */
function verifyCRC32(uint8arr, receivedCRC) {
  return calculateCRC32(uint8arr) === receivedCRC;
}

/**
 * 封包: 将 payload 打包成 [0xAA][payload][CRC32_LE][0x55]
 * @param {Uint8Array} payload
 * @returns {ArrayBuffer}
 */
function packFrame(payload) {
  const crc = calculateCRC32(payload);
  const frame = new Uint8Array(1 + payload.length + 4 + 1);
  let offset = 0;
  frame[offset++] = HEADER;
  frame.set(payload, offset);
  offset += payload.length;
  // CRC32 little-endian
  frame[offset++] = crc & 0xFF;
  frame[offset++] = (crc >>> 8) & 0xFF;
  frame[offset++] = (crc >>> 16) & 0xFF;
  frame[offset++] = (crc >>> 24) & 0xFF;
  frame[offset++] = TAIL;
  return frame.buffer;
}

/**
 * 解包: 校验并提取 payload
 * @param {ArrayBuffer} buffer
 * @returns {{ valid: boolean, payload: Uint8Array|null }}
 */
function unpackFrame(buffer) {
  const view = new Uint8Array(buffer);
  if (view.length < 6) return { valid: false, payload: null };
  if (view[0] !== HEADER || view[view.length - 1] !== TAIL) return { valid: false, payload: null };

  const payload = view.slice(1, view.length - 5);
  const crcBytes = view.slice(view.length - 5, view.length - 1);
  const receivedCRC = crcBytes[0] | (crcBytes[1] << 8) | (crcBytes[2] << 16) | ((crcBytes[3] << 24) >>> 0);
  receivedCRC >>> 0; // ensure unsigned

  if (!verifyCRC32(payload, receivedCRC >>> 0)) return { valid: false, payload: null };
  return { valid: true, payload };
}

/**
 * 解析 8 通道 500Hz EMG 数据帧
 * payload 格式: 每个采样点 = 8 * int16 = 16 bytes
 * @param {Uint8Array} payload
 * @returns {Array<Array<number>>} 二维数组 [sample][channel]
 */
function parseEMGPayload(payload) {
  const CHANNELS = 8;
  const BYTES_PER_SAMPLE = CHANNELS * 2; // int16 per channel
  const sampleCount = Math.floor(payload.length / BYTES_PER_SAMPLE);
  const dataView = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const samples = [];
  for (let i = 0; i < sampleCount; i++) {
    const row = [];
    for (let ch = 0; ch < CHANNELS; ch++) {
      row.push(dataView.getInt16(i * BYTES_PER_SAMPLE + ch * 2, true)); // little-endian
    }
    samples.push(row);
  }
  return samples;
}

/**
 * 构造指令帧，如发送 0x0A 开始采集
 * @param {number} cmdByte 单字节指令
 * @returns {ArrayBuffer}
 */
function buildCommand(cmdByte) {
  return packFrame(new Uint8Array([cmdByte]));
}

module.exports = {
  HEADER,
  TAIL,
  calculateCRC32,
  verifyCRC32,
  packFrame,
  unpackFrame,
  parseEMGPayload,
  buildCommand,
};
