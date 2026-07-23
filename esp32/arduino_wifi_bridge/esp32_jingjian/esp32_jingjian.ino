#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "BLEDevice.h"

// =========================
// Wi-Fi / backend config
// =========================
static const char* WIFI_SSID = "weixin";
static const char* WIFI_PASSWORD = "88888888a";
// Must match the cloud backend address used by the mini-program request helper.
static const char* BACKEND_HOST = "api.handemglsh.cloud";
static const uint16_t BACKEND_PORT = 443;
static const bool BACKEND_USE_HTTPS = true;

static const char* HARDWARE_ID = "ESP32-HAND-001";
static const char* BOARD_TOKEN = "esp32-secret";
static const char* FIRMWARE_VERSION = "1.0.0";

static const uint32_t HEARTBEAT_INTERVAL_MS = 1000;
static const uint32_t EMG_UPLOAD_INTERVAL_MS = 200;

// =========================
// BLE armband config
// =========================
const BLEUUID serviceUUID((uint16_t)0xFFE0);
const BLEUUID charUUID((uint16_t)0xFFE2);
const char targetName[] = "BT-11(BLE)";

// Original BLE globals
BLEClient* pClient = nullptr;
BLEAdvertisedDevice* targetDev = nullptr;
bool triggerConnect = false;
const char hexTable[] = "0123456789ABCDEF";

// =========================
// EMG packet assumptions
// 98 bytes total:
// - 2 bytes header: AA AA
// - 96 bytes payload = 6 samples * 8 channels * int16
// =========================
static const uint8_t EMG_CHANNEL_COUNT = 8;
static const uint8_t EMG_SAMPLES_PER_PACKET = 6;
static const uint8_t EMG_PACKET_BYTES = 98;
static const uint16_t EMG_UPLOAD_BATCH_LIMIT = 80;
static const uint16_t EMG_SAMPLE_RATE_HZ = 500;

struct PendingCommand {
  String commandId;
  String action;
  String sessionId;
  String gestureName;
  String emgUploadPath;
  bool valid = false;
};

struct CollectState {
  bool active = false;
  bool shouldStop = false;
  String sessionId;
  String gestureName;
  String emgUploadPath = "/devices/wifi/emg";
  uint32_t totalSamples = 0;
  uint32_t batchCount = 0;
  uint32_t lastUploadMs = 0;
};

static uint32_t lastHeartbeatMs = 0;
static uint32_t lastBleScanMs = 0;
static String lastHandledCommandId;
static CollectState collectState;

static int16_t latestSamples[EMG_UPLOAD_BATCH_LIMIT][EMG_CHANNEL_COUNT];
static uint8_t latestSampleCount = 0;
static float latestRmsValue = 0.0f;

static int16_t uploadBuffer[EMG_UPLOAD_BATCH_LIMIT][EMG_CHANNEL_COUNT];
static uint8_t uploadBufferCount = 0;
static bool uploadBufferReady = false;

static const uint32_t BLE_RESCAN_INTERVAL_MS = 5000;
static const uint32_t BLE_SCAN_WINDOW_SECONDS = 3;

String buildBaseUrl() {
  return String(BACKEND_USE_HTTPS ? "https://" : "http://") + BACKEND_HOST + ":" + String(BACKEND_PORT);
}

String buildUrl(const String& path) {
  if (path.length() == 0) return buildBaseUrl();
  if (path[0] == '/') return buildBaseUrl() + path;
  return buildBaseUrl() + "/" + path;
}

bool postJson(const String& url, const String& body, String& responseBody, int& statusCode) {
  HTTPClient http;
  WiFiClientSecure secureClient;
  if (BACKEND_USE_HTTPS) {
    secureClient.setInsecure();
    http.begin(secureClient, url);
  } else {
    http.begin(url);
  }
  http.addHeader("Content-Type", "application/json");
  statusCode = http.POST(body);
  responseBody = http.getString();
  http.end();
  return statusCode >= 200 && statusCode < 300;
}

bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting WiFi");
  uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - startMs > 30000) {
      Serial.println("\nWiFi connect timeout");
      return false;
    }
  }

  Serial.println();
  Serial.print("WiFi connected, IP=");
  Serial.println(WiFi.localIP());
  return true;
}

bool registerBoard() {
  StaticJsonDocument<256> doc;
  doc["hardware_id"] = HARDWARE_ID;
  doc["board_token"] = BOARD_TOKEN;
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["wifi_host"] = WiFi.localIP().toString();
  doc["wifi_port"] = 80;

  String body;
  serializeJson(doc, body);

  String responseBody;
  int statusCode = 0;
  bool ok = postJson(buildUrl("/devices/wifi/register"), body, responseBody, statusCode);
  Serial.printf("registerBoard status=%d body=%s\n", statusCode, responseBody.c_str());
  return ok;
}

float calculateRms(const int16_t samples[][EMG_CHANNEL_COUNT], uint8_t sampleCount) {
  if (sampleCount == 0) return 0.0f;
  double totalSq = 0.0;
  uint32_t count = 0;
  for (uint8_t i = 0; i < sampleCount; i++) {
    for (uint8_t ch = 0; ch < EMG_CHANNEL_COUNT; ch++) {
      const double value = samples[i][ch];
      totalSq += value * value;
      count += 1;
    }
  }
  return count ? sqrt(totalSq / count) : 0.0f;
}

void copySamples(
  int16_t dest[][EMG_CHANNEL_COUNT],
  uint8_t& destCount,
  const int16_t src[][EMG_CHANNEL_COUNT],
  uint8_t srcCount
) {
  destCount = srcCount > EMG_UPLOAD_BATCH_LIMIT ? EMG_UPLOAD_BATCH_LIMIT : srcCount;
  for (uint8_t i = 0; i < destCount; i++) {
    for (uint8_t ch = 0; ch < EMG_CHANNEL_COUNT; ch++) {
      dest[i][ch] = src[i][ch];
    }
  }
}

void appendUploadSamples(const int16_t samples[][EMG_CHANNEL_COUNT], uint8_t sampleCount) {
  for (uint8_t i = 0; i < sampleCount; i++) {
    if (uploadBufferCount >= EMG_UPLOAD_BATCH_LIMIT) {
      uploadBufferReady = true;
      break;
    }
    for (uint8_t ch = 0; ch < EMG_CHANNEL_COUNT; ch++) {
      uploadBuffer[uploadBufferCount][ch] = samples[i][ch];
    }
    uploadBufferCount += 1;
  }
  if (uploadBufferCount >= EMG_UPLOAD_BATCH_LIMIT) {
    uploadBufferReady = true;
  }
}

int readBatteryLevel() {
  return 80;
}

String readPredictionResult() {
  if (collectState.active && collectState.gestureName.length()) return collectState.gestureName;
  return pClient && pClient->isConnected() ? "connected" : "idle";
}

float readPredictionConfidence() {
  return collectState.active ? 0.92f : 0.50f;
}

float readSidePressure() {
  return collectState.active ? 18.2f : 6.5f;
}

String readMuscleStatus() {
  return collectState.active ? "training" : "normal";
}

void fillModuleStatuses(JsonObject moduleStatuses) {
  moduleStatuses["storage"] = "ok";
  moduleStatuses["model"] = "loaded";
  moduleStatuses["bluetooth"] = (pClient && pClient->isConnected()) ? "connected" : "disconnected";
  moduleStatuses["cpu"] = collectState.active ? "running" : "idle";
}

void addPreviewSamples(JsonObject telemetry) {
  JsonArray preview = telemetry.createNestedArray("emg_preview");
  for (uint8_t i = 0; i < latestSampleCount; i++) {
    JsonArray row = preview.createNestedArray();
    for (uint8_t ch = 0; ch < EMG_CHANNEL_COUNT; ch++) {
      row.add(latestSamples[i][ch]);
    }
  }
}

void buildHeartbeatPayload(StaticJsonDocument<4096>& doc) {
  doc["hardware_id"] = HARDWARE_ID;
  doc["board_token"] = BOARD_TOKEN;
  doc["ip_address"] = WiFi.localIP().toString();
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["battery_level"] = readBatteryLevel();
  doc["signal_strength"] = WiFi.RSSI();

  JsonObject telemetry = doc.createNestedObject("telemetry");
  telemetry["rms_value"] = latestRmsValue;
  telemetry["side_pressure"] = readSidePressure();
  telemetry["muscle_status"] = readMuscleStatus();
  telemetry["prediction_result"] = readPredictionResult();
  telemetry["prediction_confidence"] = readPredictionConfidence();
  telemetry["emg_preview_updated_at"] = millis();
  addPreviewSamples(telemetry);

  JsonObject moduleStatuses = telemetry.createNestedObject("module_statuses");
  fillModuleStatuses(moduleStatuses);
}

PendingCommand parsePendingCommand(const String& responseBody) {
  PendingCommand cmd;
  StaticJsonDocument<2048> doc;
  DeserializationError err = deserializeJson(doc, responseBody);
  if (err) {
    Serial.printf("deserialize heartbeat failed: %s\n", err.c_str());
    return cmd;
  }

  JsonVariant pending = doc["pending_command"];
  if (pending.isNull()) return cmd;

  cmd.commandId = String((const char*)(pending["command_id"] | ""));
  cmd.action = String((const char*)(pending["action"] | ""));
  cmd.sessionId = String((const char*)(pending["payload"]["session_id"] | ""));
  cmd.gestureName = String((const char*)(pending["payload"]["gesture_name"] | ""));
  cmd.emgUploadPath = String((const char*)(pending["payload"]["emg_upload_path"] | "/devices/wifi/emg"));
  cmd.valid = cmd.commandId.length() > 0 && cmd.action.length() > 0;
  return cmd;
}

bool sendCommandAck(const PendingCommand& cmd, bool success, const String& message) {
  StaticJsonDocument<512> doc;
  doc["hardware_id"] = HARDWARE_ID;
  doc["board_token"] = BOARD_TOKEN;
  doc["command_id"] = cmd.commandId;
  doc["success"] = success;
  doc["message"] = message;

  JsonObject result = doc.createNestedObject("result");
  result["collecting"] = collectState.active;
  result["session_id"] = collectState.sessionId;
  result["sample_count"] = collectState.totalSamples;

  String body;
  serializeJson(doc, body);

  String responseBody;
  int statusCode = 0;
  bool ok = postJson(buildUrl("/devices/wifi/command/ack"), body, responseBody, statusCode);
  Serial.printf("ack status=%d body=%s\n", statusCode, responseBody.c_str());
  return ok;
}

void handleCommand(const PendingCommand& cmd) {
  if (!cmd.valid) return;
  if (cmd.commandId == lastHandledCommandId) return;

  Serial.printf("handleCommand action=%s commandId=%s\n", cmd.action.c_str(), cmd.commandId.c_str());

  if (cmd.action == "start_collect") {
    collectState.active = true;
    collectState.shouldStop = false;
    collectState.sessionId = cmd.sessionId.length() ? cmd.sessionId : String("esp32_") + String(millis());
    collectState.gestureName = cmd.gestureName;
    collectState.emgUploadPath = cmd.emgUploadPath.length() ? cmd.emgUploadPath : "/devices/wifi/emg";
    collectState.totalSamples = 0;
    collectState.batchCount = 0;
    collectState.lastUploadMs = 0;
    uploadBufferCount = 0;
    uploadBufferReady = false;
    sendCommandAck(cmd, true, "collect started");
  } else if (cmd.action == "stop_collect") {
    collectState.shouldStop = true;
    sendCommandAck(cmd, true, "collect stop requested");
  } else {
    sendCommandAck(cmd, false, "unsupported action");
  }

  lastHandledCommandId = cmd.commandId;
}

bool sendHeartbeat() {
  StaticJsonDocument<4096> doc;
  buildHeartbeatPayload(doc);

  String body;
  serializeJson(doc, body);

  String responseBody;
  int statusCode = 0;
  bool ok = postJson(buildUrl("/devices/wifi/heartbeat"), body, responseBody, statusCode);
  Serial.printf("heartbeat status=%d body=%s\n", statusCode, responseBody.c_str());

  if (ok) {
    PendingCommand cmd = parsePendingCommand(responseBody);
    handleCommand(cmd);
  }
  return ok;
}

bool uploadEmgBatch(bool isFinal) {
  if (collectState.sessionId.length() == 0) return false;
  if (!isFinal && uploadBufferCount == 0) return false;

  StaticJsonDocument<16384> doc;
  doc["hardware_id"] = HARDWARE_ID;
  doc["board_token"] = BOARD_TOKEN;
  doc["session_id"] = collectState.sessionId;
  doc["gesture_name"] = collectState.gestureName;
  doc["sample_rate_hz"] = EMG_SAMPLE_RATE_HZ;
  doc["sequence_no"] = collectState.batchCount;
  doc["is_final"] = isFinal;

  JsonArray samples = doc.createNestedArray("samples");
  for (uint8_t i = 0; i < uploadBufferCount; i++) {
    JsonArray row = samples.createNestedArray();
    for (uint8_t ch = 0; ch < EMG_CHANNEL_COUNT; ch++) {
      row.add(uploadBuffer[i][ch]);
    }
  }

  String body;
  serializeJson(doc, body);

  String responseBody;
  int statusCode = 0;
  bool ok = postJson(buildUrl(collectState.emgUploadPath), body, responseBody, statusCode);
  Serial.printf("uploadEmgBatch status=%d body=%s\n", statusCode, responseBody.c_str());

  if (ok) {
    collectState.batchCount += 1;
    collectState.totalSamples += uploadBufferCount;
    collectState.lastUploadMs = millis();
    uploadBufferCount = 0;
    uploadBufferReady = false;
  }

  if (isFinal) {
    collectState.active = false;
    collectState.shouldStop = false;
    collectState.sessionId = "";
    collectState.gestureName = "";
  }

  return ok;
}

void ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("WiFi lost, reconnecting...");
  WiFi.disconnect();
  if (connectWifi()) {
    registerBoard();
  }
}

void parseNotifySamples(uint8_t* pData, int16_t outSamples[][EMG_CHANNEL_COUNT], uint8_t& outCount) {
  outCount = 0;
  if (!pData) return;

  for (uint8_t sampleIndex = 0; sampleIndex < EMG_SAMPLES_PER_PACKET; sampleIndex++) {
    const uint16_t sampleOffset = 2 + sampleIndex * EMG_CHANNEL_COUNT * 2;
    for (uint8_t ch = 0; ch < EMG_CHANNEL_COUNT; ch++) {
      const uint16_t offset = sampleOffset + ch * 2;
      const int16_t value = (int16_t)(pData[offset] | (pData[offset + 1] << 8));
      outSamples[sampleIndex][ch] = value;
    }
    outCount += 1;
  }
}

void handleParsedSamples(const int16_t samples[][EMG_CHANNEL_COUNT], uint8_t sampleCount) {
  copySamples(latestSamples, latestSampleCount, samples, sampleCount);
  latestRmsValue = calculateRms(samples, sampleCount);

  if (!collectState.active) return;

  appendUploadSamples(samples, sampleCount);
}

// --- Data notify callback ---
void onNotify(BLERemoteCharacteristic* pChar, uint8_t* pData, size_t len, bool isNotify) {
  if (len < EMG_PACKET_BYTES || pData[0] != 0xAA || pData[1] != 0xAA) return;

  char output[EMG_PACKET_BYTES * 2 + 4];
  for (size_t i = 0; i < EMG_PACKET_BYTES; i++) {
    output[i * 2] = hexTable[(pData[i] >> 4) & 0x0F];
    output[i * 2 + 1] = hexTable[pData[i] & 0x0F];
  }
  output[EMG_PACKET_BYTES * 2] = '\0';
  Serial.println(output);

  int16_t packetSamples[EMG_SAMPLES_PER_PACKET][EMG_CHANNEL_COUNT];
  uint8_t packetSampleCount = 0;
  parseNotifySamples(pData, packetSamples, packetSampleCount);
  handleParsedSamples(packetSamples, packetSampleCount);
}

// --- Scan callback ---
class ScanCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice dev) override {
    if (dev.getName() == targetName) {
      Serial.println(">>> Found BT-11(BLE)");
      BLEDevice::getScan()->stop();
      targetDev = new BLEAdvertisedDevice(dev);
      triggerConnect = true;
    }
  }
};

// --- Connect logic ---
bool connectToServer() {
  pClient = BLEDevice::createClient();
  pClient->setMTU(128);

  if (!pClient->connect(targetDev)) return false;

  BLERemoteService* pSvc = pClient->getService(serviceUUID);
  if (!pSvc) return false;

  BLERemoteCharacteristic* pDataChar = pSvc->getCharacteristic(charUUID);
  if (!pDataChar || !pDataChar->canNotify()) return false;

  pDataChar->registerForNotify(onNotify);
  Serial.println(">>> Connected & Receiving Data...");
  return true;
}

void startBleScanWindow() {
  BLEScan* pBLEScan = BLEDevice::getScan();
  Serial.println(">>> Starting BLE scan window...");
  pBLEScan->start(BLE_SCAN_WINDOW_SECONDS, false);
  pBLEScan->clearResults();
  lastBleScanMs = millis();
}

void setup() {
  Serial.begin(115200);
  unsigned long start = millis();
  while (!Serial && (millis() - start < 5000)) {}

  Serial.println("\n--- ESP32-S3 BLE + WiFi BRIDGE ---");

  connectWifi();
  registerBoard();

  BLEDevice::init("ESP32_S3_HEX_COLLECTOR");
  BLEScan* pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new ScanCallbacks());
  pBLEScan->setActiveScan(true);
  startBleScanWindow();
}

void loop() {
  ensureWifiConnected();

  if (triggerConnect) {
    if (connectToServer()) {
      Serial.println(">>> Stream Started.");
    } else {
      Serial.println(">>> Connection Failed.");
    }
    triggerConnect = false;
    delete targetDev;
    targetDev = nullptr;
  }

  if (pClient != nullptr && !pClient->isConnected()) {
    Serial.println(">>> Disconnected. Re-scanning...");
    delete pClient;
    pClient = nullptr;
    startBleScanWindow();
  }

  const uint32_t nowMs = millis();

  if (nowMs - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs = nowMs;
    sendHeartbeat();
  }

  if (pClient == nullptr && !triggerConnect && nowMs - lastBleScanMs >= BLE_RESCAN_INTERVAL_MS) {
    startBleScanWindow();
  }

  if (collectState.active && uploadBufferCount > 0 && (uploadBufferReady || nowMs - collectState.lastUploadMs >= EMG_UPLOAD_INTERVAL_MS)) {
    uploadEmgBatch(false);
  }

  if (collectState.shouldStop) {
    uploadEmgBatch(true);
  }

  delay(10);
}
