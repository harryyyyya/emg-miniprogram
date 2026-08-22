#include "network_worker.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "full_chain_config.h"
#include "runtime_snapshot.h"
#include "../generated/mlp_model.h"

struct PendingCommand {
    String command_id;
    String action;
    String session_id;
    String gesture_name;
    String emg_upload_path;
    bool valid;
};

struct CollectState {
    bool active;
    bool should_stop;
    String session_id;
    String gesture_name;
    String emg_upload_path;
    uint32_t total_samples;
    uint32_t batch_count;
    uint32_t last_upload_attempt_ms;
};

static bool g_enable_emg_upload = false;
static bool g_registered = false;
static uint32_t g_last_wifi_attempt_ms = 0u;
static uint32_t g_last_heartbeat_ms = 0u;
static uint32_t g_http_ok_count = 0u;
static uint32_t g_http_fail_count = 0u;
static uint32_t g_emg_upload_count = 0u;
static uint32_t g_emg_upload_drop_count = 0u;
static String g_last_command_id;
static bool g_last_command_success = false;
static String g_last_command_message;
static CollectState g_collect;
static uint8_t g_upload_batch[RUNTIME_EMG_UPLOAD_BATCH_SAMPLES][RUNTIME_SNAPSHOT_CHANNELS];

static String build_base_url(void) {
#if BACKEND_USE_HTTPS
    const char *scheme = "https://";
#else
    const char *scheme = "http://";
#endif
    if ((BACKEND_USE_HTTPS && BACKEND_PORT == 443) ||
        (!BACKEND_USE_HTTPS && BACKEND_PORT == 80)) {
        return String(scheme) + BACKEND_HOST;
    }
    return String(scheme) + BACKEND_HOST + ":" + String(BACKEND_PORT);
}

static String build_url(const String &path) {
    if (path.length() == 0) {
        return build_base_url();
    }
    if (path[0] == '/') {
        return build_base_url() + path;
    }
    return build_base_url() + "/" + path;
}

static bool post_json(const String &url, const String &body, String &response_body, int &status_code) {
    HTTPClient http;
    http.setTimeout(FULL_CHAIN_HTTP_TIMEOUT_MS);
#if BACKEND_USE_HTTPS
    WiFiClientSecure client;
    client.setInsecure();
#else
    WiFiClient client;
#endif
    const bool begin_ok = http.begin(client, url);
    if (!begin_ok) {
        status_code = -1;
        response_body = "";
        g_http_fail_count += 1u;
        return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Accept", "application/json");
    status_code = http.POST(body);
    response_body = http.getString();
    http.end();
    const bool ok = status_code >= 200 && status_code < 300;
    if (ok) {
        g_http_ok_count += 1u;
    } else {
        g_http_fail_count += 1u;
    }
    return ok;
}

static bool ensure_wifi_connected(void) {
    if (WiFi.status() == WL_CONNECTED) {
        return true;
    }

    const uint32_t now_ms = millis();
    if ((now_ms - g_last_wifi_attempt_ms) < FULL_CHAIN_WIFI_RECONNECT_INTERVAL_MS) {
        return false;
    }
    g_last_wifi_attempt_ms = now_ms;
    g_registered = false;

    Serial.println("WIFI_ERROR status=disconnected action=reconnect");
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    return false;
}

static bool register_board(void) {
    StaticJsonDocument<256> doc;
    doc["hardware_id"] = HARDWARE_ID;
    doc["board_token"] = BOARD_TOKEN;
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["wifi_host"] = WiFi.localIP().toString();
    doc["wifi_port"] = 80;

    String body;
    serializeJson(doc, body);

    String response;
    int status_code = 0;
    const bool ok = post_json(build_url("/devices/wifi/register"), body, response, status_code);
    Serial.printf("registerBoard status=%d ok=%d\n", status_code, ok ? 1 : 0);
    g_registered = ok;
    return ok;
}

static const char *validity_name(uint8_t validity) {
    if (validity == 0u) {
        return "VALID";
    }
    if (validity == 1u) {
        return "LOW_CONFIDENCE";
    }
    return "SIGNAL_INVALID";
}

static String build_heartbeat_payload(const RuntimeSnapshot &snapshot) {
    StaticJsonDocument<4096> doc;
    doc["hardware_id"] = HARDWARE_ID;
    doc["board_token"] = BOARD_TOKEN;
    doc["ip_address"] = WiFi.localIP().toString();
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["battery_level"] = snapshot.battery_percent;
    doc["signal_strength"] = WiFi.RSSI();

    JsonObject telemetry = doc.createNestedObject("telemetry");
    telemetry["rms_value"] = 0.0f;
    telemetry["side_pressure"] = 0.0f;
    telemetry["muscle_status"] = snapshot.validity == 0u ? "normal" : "signal_invalid";
    telemetry["prediction_result"] = String("gesture_") + String(snapshot.stable_gesture_id);
    telemetry["prediction_confidence"] = snapshot.raw_margin;
    telemetry["prediction_margin"] = snapshot.raw_margin;
    telemetry["gesture_id"] = snapshot.stable_gesture_id;
    telemetry["raw_top1"] = snapshot.raw_top1;
    telemetry["validity"] = validity_name(snapshot.validity);
    telemetry["sample_timestamp_ms"] = snapshot.sample_timestamp_ms;
    telemetry["model_version"] = MODEL_VERSION;
    telemetry["pipeline_sha256"] = PIPELINE_SHA256;
    telemetry["emg_preview_updated_at"] = snapshot.updated_ms;

    JsonArray preview = telemetry.createNestedArray("emg_preview");
    for (uint8_t row_index = 0; row_index < snapshot.emg_preview_count; ++row_index) {
        JsonArray row = preview.createNestedArray();
        for (uint8_t ch = 0; ch < RUNTIME_SNAPSHOT_CHANNELS; ++ch) {
            row.add(snapshot.emg_preview[row_index][ch]);
        }
    }

    JsonObject module_statuses = telemetry.createNestedObject("module_statuses");
    module_statuses["storage"] = "ok";
    module_statuses["model"] = "loaded";
    module_statuses["bluetooth"] = snapshot.ble_connected ? "connected" : "disconnected";
    module_statuses["cpu"] = "running";
    module_statuses["uart"] = snapshot.uart_initialized ? "initialized" : "not_initialized";
    module_statuses["wifi"] = WiFi.status() == WL_CONNECTED ? "connected" : "disconnected";
    module_statuses["backend"] = snapshot.backend_available ? "available" : "unavailable";
    module_statuses["signal"] = snapshot.signal_timeout ? "timeout" : validity_name(snapshot.validity);

    String body;
    serializeJson(doc, body);
    return body;
}

static PendingCommand parse_pending_command(const String &response_body) {
    PendingCommand cmd;
    cmd.valid = false;

    StaticJsonDocument<2048> doc;
    DeserializationError err = deserializeJson(doc, response_body);
    if (err) {
        Serial.printf("HTTP_ERROR deserialize_pending_command=%s\n", err.c_str());
        return cmd;
    }

    JsonVariant pending = doc["pending_command"];
    if (pending.isNull()) {
        return cmd;
    }

    JsonVariant payload = pending["payload"];
    cmd.command_id = String((const char *)(pending["command_id"] | ""));
    cmd.action = String((const char *)(pending["action"] | ""));
    cmd.session_id = String((const char *)(pending["session_id"] | payload["session_id"] | ""));
    cmd.gesture_name = String((const char *)(pending["gesture_name"] | payload["gesture_name"] | ""));
    cmd.emg_upload_path = String((const char *)(pending["emg_upload_path"] | payload["emg_upload_path"] | ""));
    if (cmd.emg_upload_path.length() == 0) {
        cmd.emg_upload_path = "/devices/wifi/emg";
    }
    cmd.valid = cmd.command_id.length() > 0 && cmd.action.length() > 0;
    return cmd;
}

static bool send_command_ack(const PendingCommand &cmd, bool success, const String &message) {
    StaticJsonDocument<512> doc;
    doc["hardware_id"] = HARDWARE_ID;
    doc["board_token"] = BOARD_TOKEN;
    doc["command_id"] = cmd.command_id;
    doc["success"] = success;
    doc["message"] = message;

    JsonObject result = doc.createNestedObject("result");
    result["collecting"] = g_collect.active;
    result["session_id"] = g_collect.session_id;
    result["sample_count"] = g_collect.total_samples;

    String body;
    serializeJson(doc, body);
    String response;
    int status_code = 0;
    const bool ok = post_json(build_url("/devices/wifi/command/ack"), body, response, status_code);
    Serial.printf("commandAck status=%d ok=%d\n", status_code, ok ? 1 : 0);
    return ok;
}

static void handle_command(const PendingCommand &cmd) {
    if (!cmd.valid) {
        return;
    }
    if (cmd.command_id == g_last_command_id) {
        send_command_ack(cmd, g_last_command_success, g_last_command_message);
        return;
    }

    bool success = false;
    String message;

    if (cmd.action == "start_collect") {
        if (!g_enable_emg_upload) {
            runtime_emg_collection_finish();
            message = "emg upload disabled in this mode";
        } else if (g_collect.active) {
            message = "collection already active";
        } else {
            g_collect.active = true;
            g_collect.should_stop = false;
            g_collect.session_id = cmd.session_id.length() ? cmd.session_id : String("esp32_") + String(millis());
            g_collect.gesture_name = cmd.gesture_name;
            g_collect.emg_upload_path = cmd.emg_upload_path.length() ? cmd.emg_upload_path : "/devices/wifi/emg";
            g_collect.total_samples = 0u;
            g_collect.batch_count = 0u;
            g_collect.last_upload_attempt_ms = millis();
            runtime_emg_collection_begin();
            success = true;
            message = "collect started";
        }
    } else if (cmd.action == "stop_collect") {
        if (!g_collect.active) {
            message = "no active collection";
        } else {
            g_collect.should_stop = true;
            runtime_emg_collection_request_stop();
            success = true;
            message = "collect stop requested";
        }
    } else {
        message = "unsupported action";
    }

    g_last_command_id = cmd.command_id;
    g_last_command_success = success;
    g_last_command_message = message;
    send_command_ack(cmd, success, message);
}

static bool send_heartbeat(void) {
    RuntimeSnapshot snapshot;
    runtime_snapshot_get(&snapshot);

    String body = build_heartbeat_payload(snapshot);

    String response;
    int status_code = 0;
    const bool ok = post_json(build_url("/devices/wifi/heartbeat"), body, response, status_code);
    Serial.printf("heartbeat status=%d ok=%d\n", status_code, ok ? 1 : 0);

    if (ok) {
        handle_command(parse_pending_command(response));
    }
    runtime_snapshot_update_network(WiFi.status() == WL_CONNECTED, ok, g_http_ok_count, g_http_fail_count,
                                    g_emg_upload_count, g_emg_upload_drop_count);
    return ok;
}

static bool upload_emg_batch(bool is_final) {
    if (!g_enable_emg_upload || !g_collect.active || g_collect.session_id.length() == 0) {
        return false;
    }

    const uint16_t sample_count = runtime_emg_collection_copy_batch(
        g_upload_batch,
        RUNTIME_EMG_UPLOAD_BATCH_SAMPLES
    );
    if (!is_final && sample_count == 0u) {
        return false;
    }
    if (is_final && sample_count != 0u) {
        return false;
    }

    DynamicJsonDocument doc(49152);
    doc["hardware_id"] = HARDWARE_ID;
    doc["board_token"] = BOARD_TOKEN;
    doc["session_id"] = g_collect.session_id;
    doc["gesture_name"] = g_collect.gesture_name;
    doc["sample_rate_hz"] = 500;
    doc["sequence_no"] = g_collect.batch_count;
    doc["is_final"] = is_final;

    JsonArray samples = doc.createNestedArray("samples");
    for (uint16_t row_index = 0; row_index < sample_count; ++row_index) {
        JsonArray row = samples.createNestedArray();
        for (uint8_t ch = 0; ch < RUNTIME_SNAPSHOT_CHANNELS; ++ch) {
            row.add(g_upload_batch[row_index][ch]);
        }
    }

    String body;
    serializeJson(doc, body);

    String response;
    int status_code = 0;
    g_collect.last_upload_attempt_ms = millis();
    const bool ok = post_json(build_url(g_collect.emg_upload_path), body, response, status_code);
    Serial.printf("emgUpload path=%s status=%d ok=%d\n", g_collect.emg_upload_path.c_str(), status_code, ok ? 1 : 0);

    if (ok) {
        runtime_emg_collection_discard(sample_count);
        g_collect.batch_count += 1u;
        g_collect.total_samples += sample_count;
        g_emg_upload_count += 1u;
    }
    g_emg_upload_drop_count = runtime_emg_collection_dropped();
    if (is_final && ok) {
        runtime_emg_collection_finish();
        g_collect.active = false;
        g_collect.should_stop = false;
        g_collect.session_id = "";
        g_collect.gesture_name = "";
    }
    runtime_snapshot_update_network(WiFi.status() == WL_CONNECTED, ok, g_http_ok_count, g_http_fail_count,
                                    g_emg_upload_count, g_emg_upload_drop_count);
    return ok;
}

static void network_worker_tick(void) {
    const bool wifi_connected = ensure_wifi_connected();
    if (!wifi_connected) {
        runtime_snapshot_update_network(false, false, g_http_ok_count, g_http_fail_count,
                                        g_emg_upload_count, g_emg_upload_drop_count);
        return;
    }

    if (!g_registered) {
        register_board();
    }

    const uint32_t now_ms = millis();
    if ((now_ms - g_last_heartbeat_ms) >= FULL_CHAIN_HEARTBEAT_INTERVAL_MS) {
        g_last_heartbeat_ms = now_ms;
        send_heartbeat();
    }

    const uint16_t pending_samples = runtime_emg_collection_pending();
    if (g_collect.active && pending_samples > 0u &&
        (now_ms - g_collect.last_upload_attempt_ms) >= FULL_CHAIN_EMG_UPLOAD_INTERVAL_MS) {
        upload_emg_batch(false);
    }
    if (g_collect.should_stop && runtime_emg_collection_pending() == 0u &&
        (millis() - g_collect.last_upload_attempt_ms) >= FULL_CHAIN_EMG_UPLOAD_INTERVAL_MS) {
        upload_emg_batch(true);
    }
}

static void network_worker_task(void *) {
    WiFi.mode(WIFI_STA);
    for (;;) {
        network_worker_tick();
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void network_worker_begin(bool enable_emg_upload) {
    g_enable_emg_upload = enable_emg_upload;
    g_collect.active = false;
    g_collect.should_stop = false;
    g_collect.session_id = "";
    g_collect.gesture_name = "";
    g_collect.emg_upload_path = "/devices/wifi/emg";
    g_collect.total_samples = 0u;
    g_collect.batch_count = 0u;
    g_collect.last_upload_attempt_ms = 0u;
    xTaskCreatePinnedToCore(network_worker_task, "stage6_net", 12288, 0, 1, 0, 0);
}

void network_worker_poll_once_for_wifi_only(void) {
    network_worker_tick();
}
