#include "live_ble_inference.h"

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <esp_arduino_version.h>
#include <string.h>

#include "ble_byte_queue.h"
#include "frame_stream_parser.h"
#include "sample_ring_buffer.h"
#include "full_chain_modes.h"
#include "runtime_snapshot.h"
#include "stage6_uart_link.h"
extern "C" {
#include "emg_features.h"
#include "mlp_inference.h"
#include "emg_controller.h"
}
#include "stage6_1c_integration_config.h"
#include "../generated/mlp_model.h"

/* STAGE6_1C_CONTRACT_ASSERTS_BEGIN */
static_assert(STAGE6_1C_WINDOW_SAMPLES == STAGE5_RING_WINDOW_SAMPLES, "window/ring mismatch");
static_assert(STAGE6_1C_WINDOW_SAMPLES == LSH_MLP_WINDOW_SAMPLES, "window/model mismatch");
static_assert(STAGE6_1C_CHANNEL_COUNT == STAGE5_RING_CHANNELS, "channel/ring mismatch");
static_assert(STAGE6_1C_CHANNEL_COUNT == STAGE5_CHANNELS, "channel/parser mismatch");
static_assert(STAGE6_1C_CHANNEL_COUNT == LSH_MLP_CHANNEL_COUNT, "channel/model mismatch");
static_assert(STAGE6_1C_FEATURE_COUNT == LSH_MLP_INPUT_COUNT, "feature/model mismatch");
static_assert(STAGE6_1C_CLASS_COUNT == LSH_MLP_CLASS_COUNT, "class/model mismatch");
static_assert(STAGE6_1C_STEP_SAMPLES == STAGE4_STEP_SAMPLES, "step/config mismatch");
/* STAGE6_1C_CONTRACT_ASSERTS_END */

#define STAGE6_TARGET_NAME "BT-11(BLE)"
#define STAGE6_SERVICE_UUID "0000ffe0-0000-1000-8000-00805f9b34fb"
#define STAGE6_NOTIFY_UUID "0000ffe2-0000-1000-8000-00805f9b34fb"
#define STAGE6_REQUESTED_MTU 28u
#define STAGE6_QUEUE_CAPACITY 4096u
#define STAGE6_SCAN_WINDOW_SECONDS 5u
#define STAGE6_STATUS_INTERVAL_MS 1000u
#define STAGE6_NO_VALID_FRAME_TIMEOUT_MS 250u
#define STAGE6_SAMPLE_INTERVAL_MS 2u
#define STAGE6_PACKET_INTERVAL_MS 20u
#define STAGE6_STEP_SAMPLES STAGE6_1C_STEP_SAMPLES
#define STAGE6_TIMING_CAP 128u

#ifndef ARDUINO_BOARD
#define ARDUINO_BOARD "unknown"
#endif

typedef struct Stage6TimingStats {
    uint32_t values[STAGE6_TIMING_CAP];
    uint32_t count;
    uint32_t write_index;
    uint32_t max_us;
} Stage6TimingStats;

typedef struct Stage6LiveSession {
    Stage5FrameStreamParser parser;
    Stage5SampleRingBuffer ring_buffer;
    EmgController controller;
    EmgControllerOutput last_output;
    Stage6TimingStats model_timing;
    Stage6TimingStats end_to_end_timing;
    uint32_t notify_count;
    uint32_t notify_bytes;
    uint32_t notify_len_hist[201];
    uint32_t notify_len_other;
    uint32_t parsed_frame_count;
    uint32_t total_sample_count;
    uint32_t inference_count;
    uint32_t inference_failure_count;
    uint32_t continuity_reset_count;
    uint32_t dropped_packet_count;
    uint32_t timestamp_gap_count;
    uint32_t estimated_missing_packets;
    uint32_t largest_gap_ms;
    uint32_t signal_timeout_count;
    uint32_t samples_since_last_inference;
    uint32_t last_packet_timestamp_ms;
    uint32_t last_valid_frame_host_ms;
    uint32_t last_status_ms;
    uint8_t has_last_packet_timestamp;
    uint8_t connected;
    uint8_t signal_timeout_active;
} Stage6LiveSession;

static BLEUUID g_service_uuid(STAGE6_SERVICE_UUID);
static BLEUUID g_notify_uuid(STAGE6_NOTIFY_UUID);
static BLEAdvertisedDevice *g_target_device = 0;
static BLEClient *g_client = 0;
static BLERemoteCharacteristic *g_notify_characteristic = 0;
static uint8_t g_queue_storage[STAGE6_QUEUE_CAPACITY];
static Stage6BleByteQueue g_rx_queue;
static Stage6LiveSession g_live;
static portMUX_TYPE g_queue_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint8_t g_connect_requested = 0u;
static uint8_t g_scan_running = 0u;
static float g_window[STAGE4_WINDOW_SAMPLES * STAGE4_CHANNEL_COUNT];
static float g_features[STAGE4_FEATURE_COUNT];
static float g_standardized[STAGE4_FEATURE_COUNT];
static float g_hidden1[LSH_MLP_HIDDEN1_COUNT];
static float g_hidden2[LSH_MLP_HIDDEN2_COUNT];
static float g_scores[STAGE4_CLASS_COUNT];
static uint32_t g_timing_scratch[STAGE6_TIMING_CAP];
static uint32_t g_last_uart_tx_ms = 0u;
static uint8_t g_last_uart_mode = 0xFFu;
static uint8_t g_last_uart_was_valid = 0u;
static uint32_t g_uart_tx_count = 0u;
static uint32_t g_uart_no_stable_count = 0u;
static uint32_t g_min_free_heap = 0u;

static void stage6_force_uart_no_stable(const char *reason);
static void stage6_publish_signal_snapshot(const EmgControllerOutput *output, uint32_t raw_top1, float margin);

static EmgControllerConfig stage6_controller_config(void) {
    EmgControllerConfig cfg;
    cfg.margin_threshold = STAGE4_MARGIN_THRESHOLD;
    cfg.vote_horizon_ms = STAGE4_VOTE_HORIZON_MS;
    cfg.vote_required_fraction = STAGE4_VOTE_REQUIRED_FRACTION;
    cfg.nominal_step_ms = STAGE4_STEP_MS;
    cfg.low_confidence_hold_ms = STAGE4_LOW_CONFIDENCE_HOLD_MS;
    cfg.rest_label = STAGE4_REST_LABEL;
    return cfg;
}

static void stage6_timing_reset(Stage6TimingStats *stats) {
    memset(stats, 0, sizeof(*stats));
}

static void stage6_timing_record(Stage6TimingStats *stats, uint32_t value_us) {
    stats->values[stats->write_index] = value_us;
    stats->write_index = (stats->write_index + 1u) % STAGE6_TIMING_CAP;
    if (stats->count < STAGE6_TIMING_CAP) {
        stats->count += 1u;
    }
    if (value_us > stats->max_us) {
        stats->max_us = value_us;
    }
}

static void stage6_sort_u32(uint32_t *values, uint32_t count) {
    for (uint32_t i = 1u; i < count; ++i) {
        uint32_t key = values[i];
        int32_t cursor = (int32_t)i - 1;
        while (cursor >= 0 && values[cursor] > key) {
            values[cursor + 1] = values[cursor];
            cursor -= 1;
        }
        values[cursor + 1] = key;
    }
}

static uint32_t stage6_timing_percentile(const Stage6TimingStats *stats, uint32_t pct) {
    if (stats->count == 0u) {
        return 0u;
    }
    for (uint32_t index = 0u; index < stats->count; ++index) {
        g_timing_scratch[index] = stats->values[index];
    }
    stage6_sort_u32(g_timing_scratch, stats->count);
    return g_timing_scratch[(stats->count - 1u) * pct / 100u];
}

static void stage6_print_core_version(void) {
    Serial.print(ESP_ARDUINO_VERSION_MAJOR);
    Serial.print(".");
    Serial.print(ESP_ARDUINO_VERSION_MINOR);
    Serial.print(".");
    Serial.print(ESP_ARDUINO_VERSION_PATCH);
}

static void stage6_note_notification_length(size_t length) {
    if (length < 201u) {
        g_live.notify_len_hist[length] += 1u;
    } else {
        g_live.notify_len_other += 1u;
    }
}

static void stage6_print_len_hist(void) {
    uint8_t printed = 0u;
    for (uint32_t index = 0u; index < 201u; ++index) {
        if (g_live.notify_len_hist[index] == 0u) {
            continue;
        }
        if (printed > 0u) {
            Serial.print(",");
        }
        Serial.print(index);
        Serial.print(":");
        Serial.print(g_live.notify_len_hist[index]);
        printed = 1u;
    }
    if (g_live.notify_len_other > 0u) {
        if (printed > 0u) {
            Serial.print(",");
        }
        Serial.print("other:");
        Serial.print(g_live.notify_len_other);
    }
    if (printed == 0u) {
        Serial.print("none");
    }
}

static void stage6_reset_signal_path(const char *reason) {
    portENTER_CRITICAL(&g_queue_mux);
    stage6_ble_byte_queue_reset(&g_rx_queue);
    portEXIT_CRITICAL(&g_queue_mux);
    stage5_frame_stream_parser_reset(&g_live.parser);
    stage5_sample_ring_buffer_reset(&g_live.ring_buffer);
    emg_controller_reset_for_continuity_block(&g_live.controller);
    g_live.samples_since_last_inference = 0u;
    g_live.has_last_packet_timestamp = 0u;
    g_live.signal_timeout_active = 1u;
    g_live.last_valid_frame_host_ms = 0u;
    memset(&g_live.last_output, 0, sizeof(g_live.last_output));
    runtime_snapshot_set_ble(g_live.connected != 0u, true);
    stage6_force_uart_no_stable(reason);
    Serial.print("BLE_STATE connected=");
    Serial.print(g_live.connected);
    Serial.print(" reason=");
    Serial.print(reason);
    Serial.println(" gesture=0 validity=2");
}

static void stage6_reset_runtime(void) {
    stage5_frame_stream_parser_init(&g_live.parser);
    stage5_sample_ring_buffer_init(&g_live.ring_buffer);
    emg_controller_init(&g_live.controller, stage6_controller_config());
    stage6_timing_reset(&g_live.model_timing);
    stage6_timing_reset(&g_live.end_to_end_timing);
    memset(&g_live.last_output, 0, sizeof(g_live.last_output));
    g_live.parsed_frame_count = 0u;
    g_live.total_sample_count = 0u;
    g_live.inference_count = 0u;
    g_live.inference_failure_count = 0u;
    g_live.continuity_reset_count = 0u;
    g_live.dropped_packet_count = 0u;
    g_live.timestamp_gap_count = 0u;
    g_live.estimated_missing_packets = 0u;
    g_live.largest_gap_ms = 0u;
    g_live.signal_timeout_count = 0u;
    g_live.samples_since_last_inference = 0u;
    g_live.last_packet_timestamp_ms = 0u;
    g_live.last_valid_frame_host_ms = 0u;
    g_live.has_last_packet_timestamp = 0u;
    g_live.signal_timeout_active = 0u;
}

static void stage6_print_infer(uint32_t timestamp_ms, uint32_t raw_top1, float margin, int valid_signal, uint32_t model_us, uint32_t end_to_end_us) {
    Serial.print("INFER timestamp_ms="); Serial.print(timestamp_ms);
    Serial.print(" top1="); Serial.print(raw_top1);
    Serial.print(" raw_top1="); Serial.print(raw_top1);
    Serial.print(" margin="); Serial.print(margin, 6);
    Serial.print(" validity="); Serial.print(valid_signal);
    Serial.print(" model_pipeline_us="); Serial.print(model_us);
    Serial.print(" end_to_end_processing_us="); Serial.print(end_to_end_us);
    Serial.println();
}

static void stage6_print_state(const EmgControllerOutput *output, uint32_t model_us) {
    Serial.print("STATE timestamp_ms="); Serial.print(output->timestamp_ms);
    Serial.print(" gesture="); Serial.print(output->gesture_id);
    Serial.print(" validity="); Serial.print((uint32_t)output->validity);
    Serial.print(" state_seq="); Serial.print(output->state_seq);
    Serial.print(" raw_top1="); Serial.print(output->candidate_label);
    Serial.print(" raw_margin="); Serial.print(output->margin, 6);
    Serial.print(" model_pipeline_us="); Serial.print(model_us);
    Serial.print(" model_p95_us="); Serial.print(stage6_timing_percentile(&g_live.model_timing, 95u));
    Serial.print(" free_heap="); Serial.println(ESP.getFreeHeap());
}

static void stage6_publish_signal_snapshot(const EmgControllerOutput *output, uint32_t raw_top1, float margin) {
    uint32_t free_heap = ESP.getFreeHeap();
    if (g_min_free_heap == 0u || free_heap < g_min_free_heap) {
        g_min_free_heap = free_heap;
    }
    runtime_snapshot_update_signal(
        output == 0 ? 0u : output->timestamp_ms,
        output == 0 ? 0u : (uint8_t)output->gesture_id,
        (uint8_t)raw_top1,
        output == 0 ? 2u : (uint8_t)output->validity,
        margin,
        g_live.connected != 0u,
        g_live.signal_timeout_active != 0u,
        g_live.notify_count,
        g_live.parsed_frame_count,
        g_live.parser.parse_error_count,
        g_live.timestamp_gap_count,
        g_live.estimated_missing_packets,
        stage6_ble_byte_queue_overflows(&g_rx_queue),
        g_live.inference_count,
        g_live.inference_failure_count,
        g_uart_tx_count,
        g_uart_no_stable_count,
        stage6_timing_percentile(&g_live.model_timing, 50u),
        stage6_timing_percentile(&g_live.model_timing, 95u),
        g_live.model_timing.max_us,
        free_heap,
        g_min_free_heap,
        output == 0 ? 0u : output->state_seq
    );
}

static void stage6_force_uart_no_stable(const char *reason) {
#if FULL_CHAIN_ENABLE_UART
    stage6_uart_link_force_no_stable(reason);
    g_last_uart_tx_ms = millis();
    g_last_uart_mode = 0xFFu;
    g_last_uart_was_valid = 0u;
    g_uart_tx_count += 1u;
    g_uart_no_stable_count += 1u;
#else
    (void)reason;
#endif
}

static void stage6_maybe_send_uart_from_output(const EmgControllerOutput *output) {
#if FULL_CHAIN_ENABLE_UART
    if (output == 0) {
        return;
    }
    const uint32_t now_ms = millis();
    if (output->validity == EMG_VALIDITY_VALID && output->gesture_id <= 8u) {
        if (g_last_uart_was_valid == 0u || g_last_uart_mode != output->gesture_id || (now_ms - g_last_uart_tx_ms) >= 500u) {
            stage6_uart_link_send_valid((uint8_t)output->gesture_id, "ble_infer_uart");
            g_last_uart_tx_ms = now_ms;
            g_last_uart_mode = (uint8_t)output->gesture_id;
            g_last_uart_was_valid = 1u;
            g_uart_tx_count += 1u;
        }
    } else {
        if (g_last_uart_was_valid != 0u || (now_ms - g_last_uart_tx_ms) >= 500u) {
            stage6_uart_link_send_no_stable("ble_infer_no_stable");
            g_last_uart_tx_ms = now_ms;
            g_last_uart_mode = 0xFFu;
            g_last_uart_was_valid = 0u;
            g_uart_tx_count += 1u;
            g_uart_no_stable_count += 1u;
        }
    }
#else
    (void)output;
#endif
}

static void stage6_run_inference(uint32_t sample_timestamp_ms, uint32_t frame_start_us) {
    uint32_t predicted_label = STAGE4_REST_LABEL;
    float margin = 0.0f;
    EmgControllerOutput output;
    uint32_t model_start_us;
    uint32_t model_us;
    uint32_t end_to_end_us;
    int predict_status;

    stage5_sample_ring_buffer_copy_window(&g_live.ring_buffer, g_window);
    model_start_us = micros();
    predict_status = emg_mlp_predict_stage2_window(
        &LSH_MLP_MODEL,
        g_window,
        g_features,
        g_standardized,
        g_hidden1,
        g_hidden2,
        g_scores,
        &predicted_label,
        &margin
    );
    model_us = micros() - model_start_us;
    end_to_end_us = micros() - frame_start_us;
    stage6_timing_record(&g_live.model_timing, model_us);
    stage6_timing_record(&g_live.end_to_end_timing, end_to_end_us);
    g_live.inference_count += 1u;

    if (predict_status != 0) {
        g_live.inference_failure_count += 1u;
        predicted_label = STAGE4_REST_LABEL;
        margin = 0.0f;
        stage6_force_uart_no_stable("fatal_inference_failure");
    }

    emg_controller_update(
        &g_live.controller,
        sample_timestamp_ms,
        predicted_label,
        margin,
        predict_status == 0 ? 1 : 0,
        &output
    );
    stage6_print_infer(sample_timestamp_ms, predicted_label, margin, predict_status == 0 ? 1 : 0, model_us, end_to_end_us);
    if (output.state_seq != g_live.last_output.state_seq || output.gesture_id != g_live.last_output.gesture_id || output.validity != g_live.last_output.validity) {
        stage6_print_state(&output, model_us);
    }
    stage6_maybe_send_uart_from_output(&output);
    stage6_publish_signal_snapshot(&output, predicted_label, margin);
    g_live.last_output = output;
}

static void stage6_reset_continuity(const char *reason) {
    g_live.continuity_reset_count += 1u;
    stage5_sample_ring_buffer_reset(&g_live.ring_buffer);
    emg_controller_reset_for_continuity_block(&g_live.controller);
    g_live.samples_since_last_inference = 0u;
    runtime_snapshot_set_ble(g_live.connected != 0u, true);
    stage6_force_uart_no_stable(reason);
    Serial.print("BLE_STATE connected=");
    Serial.print(g_live.connected);
    Serial.print(" reason=");
    Serial.print(reason);
    Serial.println(" gesture=0 validity=2");
}

static void stage6_handle_timestamp(uint32_t timestamp_ms) {
    if (g_live.has_last_packet_timestamp != 0u) {
        uint32_t delta_ms = timestamp_ms - g_live.last_packet_timestamp_ms;
        if (delta_ms != STAGE6_PACKET_INTERVAL_MS) {
            g_live.timestamp_gap_count += 1u;
            if (delta_ms > g_live.largest_gap_ms) {
                g_live.largest_gap_ms = delta_ms;
            }
            if (delta_ms > STAGE6_PACKET_INTERVAL_MS && (delta_ms % STAGE6_PACKET_INTERVAL_MS) == 0u) {
                g_live.estimated_missing_packets += (delta_ms / STAGE6_PACKET_INTERVAL_MS) - 1u;
                stage6_reset_continuity("packet_gap");
            } else {
                stage6_reset_continuity("packet_interval_error");
            }
        }
    }
    g_live.last_packet_timestamp_ms = timestamp_ms;
    g_live.has_last_packet_timestamp = 1u;
}

static void stage6_handle_frame(const Stage5Frame *frame, uint32_t frame_start_us) {
    stage6_handle_timestamp(frame->timestamp_ms);
    g_live.parsed_frame_count += 1u;
    g_live.last_valid_frame_host_ms = millis();
    g_live.signal_timeout_active = 0u;
    runtime_snapshot_set_ble(g_live.connected != 0u, false);
    runtime_snapshot_update_emg_preview(frame->timestamp_ms, frame->battery_percent, frame->emg, STAGE5_SAMPLES_PER_FRAME);
    runtime_emg_collection_push(frame->emg, STAGE5_SAMPLES_PER_FRAME);

    for (uint32_t sample = 0u; sample < STAGE5_SAMPLES_PER_FRAME; ++sample) {
        uint32_t sample_timestamp_ms = frame->timestamp_ms + sample * STAGE6_SAMPLE_INTERVAL_MS;
        stage5_sample_ring_buffer_push(&g_live.ring_buffer, frame->emg[sample], STAGE4_FIXED_BASELINE);
        g_live.total_sample_count += 1u;
        g_live.samples_since_last_inference += 1u;
        if (stage5_sample_ring_buffer_ready(&g_live.ring_buffer) && g_live.samples_since_last_inference >= STAGE6_STEP_SAMPLES) {
            g_live.samples_since_last_inference = 0u;
            stage6_run_inference(sample_timestamp_ms, frame_start_us);
        }
    }
}

static void stage6_live_drain_queue(void) {
    uint8_t byte = 0u;
    for (;;) {
        int have_byte;
        portENTER_CRITICAL(&g_queue_mux);
        have_byte = stage6_ble_byte_queue_pop(&g_rx_queue, &byte);
        portEXIT_CRITICAL(&g_queue_mux);
        if (!have_byte) {
            break;
        }
        Stage5Frame frame;
        uint32_t frame_start_us = micros();
        uint32_t before_errors = g_live.parser.parse_error_count;
        int ready = stage5_frame_stream_parser_feed_byte(&g_live.parser, byte, &frame);
        if (g_live.parser.parse_error_count != before_errors) {
            Serial.print("FRAME_INVALID reason=resync discarded_bytes=");
            Serial.println(g_live.parser.discarded_byte_count);
        }
        if (ready > 0) {
            stage6_handle_frame(&frame, frame_start_us);
        }
    }
}

static void stage6_notify_callback(BLERemoteCharacteristic *, uint8_t *data, size_t length, bool) {
    portENTER_CRITICAL(&g_queue_mux);
    stage6_ble_byte_queue_push_isr(&g_rx_queue, data, length);
    portEXIT_CRITICAL(&g_queue_mux);
    g_live.notify_count += 1u;
    g_live.notify_bytes += (uint32_t)length;
    stage6_note_notification_length(length);
}

class Stage6LiveClientCallbacks : public BLEClientCallbacks {
    void onConnect(BLEClient *) override {
        g_live.connected = 1u;
    }

    void onDisconnect(BLEClient *) override {
        g_live.connected = 0u;
        Serial.print("BLE_DISCONNECT reason=client_disconnect uptime_ms=");
        Serial.println(millis());
        stage6_reset_signal_path("disconnect");
    }
};

class Stage6LiveScanCallbacks : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertised_device) override {
        bool name_match = advertised_device.haveName() && advertised_device.getName() == STAGE6_TARGET_NAME;
        bool service_match = advertised_device.haveServiceUUID() && advertised_device.isAdvertisingService(g_service_uuid);
        if (!name_match && !service_match) {
            return;
        }
        Serial.print("BLE_SCAN name=");
        Serial.print(advertised_device.haveName() ? advertised_device.getName().c_str() : "<none>");
        Serial.print(" address=");
        Serial.print(advertised_device.getAddress().toString().c_str());
        Serial.print(" address_type=unknown");
        Serial.print(" rssi=");
        Serial.print(advertised_device.getRSSI());
        Serial.print(" services=");
        Serial.println(advertised_device.haveServiceUUID() ? advertised_device.getServiceUUID().toString().c_str() : "<none>");

        if (g_target_device != 0) {
            return;
        }
        g_target_device = new BLEAdvertisedDevice(advertised_device);
        g_connect_requested = 1u;
        BLEDevice::getScan()->stop();
        g_scan_running = 0u;
    }
};

static void stage6_start_scan(void) {
    BLEScan *scan = BLEDevice::getScan();
    Serial.print("BLE_SCAN_START target_name=");
    Serial.print(STAGE6_TARGET_NAME);
    Serial.print(" service_uuid=");
    Serial.println(STAGE6_SERVICE_UUID);
    scan->setAdvertisedDeviceCallbacks(new Stage6LiveScanCallbacks(), false);
    scan->setActiveScan(true);
    scan->setInterval(1349);
    scan->setWindow(449);
    g_scan_running = 1u;
    scan->start(STAGE6_SCAN_WINDOW_SECONDS, false);
    g_scan_running = 0u;
}

static bool stage6_connect(void) {
    if (g_target_device == 0) {
        return false;
    }
    if (g_client != 0) {
        delete g_client;
        g_client = 0;
    }
    g_client = BLEDevice::createClient();
    g_client->setClientCallbacks(new Stage6LiveClientCallbacks());
    g_client->setMTU(STAGE6_REQUESTED_MTU);
    Serial.print("BLE_CONNECT address=");
    Serial.print(g_target_device->getAddress().toString().c_str());
    Serial.print(" requested_mtu=");
    Serial.print(STAGE6_REQUESTED_MTU);
    if (!g_client->connect(g_target_device)) {
        Serial.println(" negotiated_mtu=unknown result=FAIL");
        return false;
    }
    Serial.print(" negotiated_mtu=");
    Serial.print(g_client->getMTU());
    Serial.println(" result=OK");
    Serial.println("BLE_STATE connected=1 reason=connect gesture=0 validity=2");

    BLERemoteService *service = g_client->getService(g_service_uuid);
    if (service == 0) {
        Serial.println("BLE_GATT service=" STAGE6_SERVICE_UUID " result=MISSING");
        return false;
    }
    g_notify_characteristic = service->getCharacteristic(g_notify_uuid);
    if (g_notify_characteristic == 0) {
        Serial.println("BLE_GATT service=" STAGE6_SERVICE_UUID " characteristic=" STAGE6_NOTIFY_UUID " result=MISSING");
        return false;
    }
    Serial.print("BLE_GATT service=");
    Serial.print(STAGE6_SERVICE_UUID);
    Serial.print(" characteristic=");
    Serial.print(STAGE6_NOTIFY_UUID);
    Serial.print(" properties=");
    Serial.print(g_notify_characteristic->canRead() ? "read," : "");
    Serial.print(g_notify_characteristic->canWrite() ? "write," : "");
    Serial.print(g_notify_characteristic->canNotify() ? "notify," : "");
    Serial.print(g_notify_characteristic->canIndicate() ? "indicate," : "");
    Serial.println("end");
    if (g_notify_characteristic->canNotify()) {
        g_notify_characteristic->registerForNotify(stage6_notify_callback, false);
        Serial.println("BLE_SUBSCRIBE result=registered mode=notify");
    } else if (g_notify_characteristic->canIndicate()) {
        g_notify_characteristic->registerForNotify(stage6_notify_callback, true);
        Serial.println("BLE_SUBSCRIBE result=registered mode=indicate");
    } else {
        Serial.println("BLE_SUBSCRIBE result=FAIL reason=no_notify_or_indicate");
        return false;
    }
    return true;
}

static void stage6_print_live_stats(void) {
    Serial.print("FULL_STATS uptime_ms="); Serial.print(millis());
    Serial.print(" model="); Serial.print(MODEL_VERSION);
    Serial.print(" connected="); Serial.print(g_live.connected);
    Serial.print(" ble="); Serial.print(g_live.connected);
    Serial.print(" notify_count="); Serial.print(g_live.notify_count);
    Serial.print(" notify_bytes="); Serial.print(g_live.notify_bytes);
    Serial.print(" len_hist="); stage6_print_len_hist();
    Serial.print(" valid_frames="); Serial.print(g_live.parsed_frame_count);
    Serial.print(" invalid_frames="); Serial.print(g_live.parser.parse_error_count);
    Serial.print(" discarded_bytes="); Serial.print(g_live.parser.discarded_byte_count);
    Serial.print(" timestamp_gap_count="); Serial.print(g_live.timestamp_gap_count);
    Serial.print(" estimated_missing_packets="); Serial.print(g_live.estimated_missing_packets);
    Serial.print(" queue_overflow_count="); Serial.print(stage6_ble_byte_queue_overflows(&g_rx_queue));
    Serial.print(" inference_count="); Serial.print(g_live.inference_count);
    Serial.print(" inference_failure_count="); Serial.print(g_live.inference_failure_count);
    Serial.print(" uart_tx="); Serial.print(g_uart_tx_count);
    Serial.print(" uart_no_stable="); Serial.print(g_uart_no_stable_count);
    Serial.print(" model_p50_us="); Serial.print(stage6_timing_percentile(&g_live.model_timing, 50u));
    Serial.print(" model_p95_us="); Serial.print(stage6_timing_percentile(&g_live.model_timing, 95u));
    Serial.print(" model_max_us="); Serial.print(g_live.model_timing.max_us);
    Serial.print(" end_to_end_p95_us="); Serial.print(stage6_timing_percentile(&g_live.end_to_end_timing, 95u));
    Serial.print(" signal_timeout_count="); Serial.print(g_live.signal_timeout_count);
    Serial.print(" free_heap="); Serial.print(ESP.getFreeHeap());
    Serial.print(" min_free_heap="); Serial.println(g_min_free_heap);
}

void stage6_live_ble_setup(void) {
    memset(&g_live, 0, sizeof(g_live));
    runtime_snapshot_init();
    g_min_free_heap = ESP.getFreeHeap();
    stage6_ble_byte_queue_init(&g_rx_queue, g_queue_storage, sizeof(g_queue_storage));
    stage6_reset_runtime();
    Serial.print("LIVE_BOOT board=");
    Serial.print(ARDUINO_BOARD);
    Serial.print(" core=");
    stage6_print_core_version();
    Serial.print(" mode=");
    Serial.print(FULL_CHAIN_MODE);
    Serial.print(" baud=921600 window_samples=");
    Serial.print(STAGE4_WINDOW_SAMPLES);
    /* STAGE6_1C_BOOT_IDENTITY_BEGIN */
    Serial.print(" MODEL_VERSION=");
    Serial.print(MODEL_VERSION);
    Serial.print(" PIPELINE_HASH=");
    Serial.print(PIPELINE_SHA256);
    Serial.print(" WINDOW_SIZE=");
    Serial.print(STAGE6_1C_WINDOW_SAMPLES);
    Serial.print(" STEP_SIZE=");
    Serial.print(STAGE6_1C_STEP_SAMPLES);
    Serial.print(" FEATURE_COUNT=");
    Serial.print(STAGE6_1C_FEATURE_COUNT);
    Serial.print(" CLASS_COUNT=");
    Serial.print(STAGE6_1C_CLASS_COUNT);
    /* STAGE6_1C_BOOT_IDENTITY_END */
    Serial.print(" step_samples=");
    Serial.print(STAGE6_STEP_SAMPLES);
    Serial.print(" margin_threshold=");
    Serial.print(STAGE4_MARGIN_THRESHOLD, 6);
    Serial.print(" vote_horizon_ms=");
    Serial.print(STAGE4_VOTE_HORIZON_MS);
    Serial.print(" free_heap=");
    Serial.println(ESP.getFreeHeap());
#if FULL_CHAIN_ENABLE_UART
    stage6_uart_link_begin();
#endif
    BLEDevice::init("ESP32_S3_STAGE6_LIVE_BLE");
    stage6_start_scan();
    g_live.last_status_ms = millis();
}

void stage6_live_ble_loop(void) {
    if (g_connect_requested != 0u) {
        g_connect_requested = 0u;
        stage6_connect();
        delete g_target_device;
        g_target_device = 0;
    }

    if (g_client != 0 && !g_client->isConnected()) {
        if (g_live.connected != 0u) {
            Serial.print("BLE_DISCONNECT reason=poll_disconnect uptime_ms=");
            Serial.println(millis());
        }
        g_live.connected = 0u;
        stage6_reset_signal_path("disconnect_poll");
        delete g_client;
        g_client = 0;
        g_notify_characteristic = 0;
        delay(500);
        stage6_start_scan();
    } else if (g_client == 0 && g_scan_running == 0u && g_target_device == 0) {
        stage6_start_scan();
    }

    stage6_live_drain_queue();

    if (g_live.connected != 0u && g_live.last_valid_frame_host_ms != 0u) {
        uint32_t silence_ms = millis() - g_live.last_valid_frame_host_ms;
        if (silence_ms >= STAGE6_NO_VALID_FRAME_TIMEOUT_MS && g_live.signal_timeout_active == 0u) {
            g_live.signal_timeout_active = 1u;
            g_live.signal_timeout_count += 1u;
            Serial.print("SIGNAL_TIMEOUT no_valid_frame_ms=");
            Serial.print(silence_ms);
            Serial.println(" gesture=0 validity=2");
            stage6_reset_signal_path("signal_timeout");
        }
    }

    if ((millis() - g_live.last_status_ms) >= STAGE6_STATUS_INTERVAL_MS) {
        g_live.last_status_ms = millis();
        stage6_print_live_stats();
    }
}
