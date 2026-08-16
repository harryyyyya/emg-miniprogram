#include "runtime_snapshot.h"

#include <Arduino.h>
#include <string.h>

static RuntimeSnapshot g_snapshot;
static portMUX_TYPE g_snapshot_mux = portMUX_INITIALIZER_UNLOCKED;
static uint8_t g_upload_queue[RUNTIME_EMG_UPLOAD_QUEUE_SAMPLES][RUNTIME_SNAPSHOT_CHANNELS];
static uint16_t g_upload_head = 0u;
static uint16_t g_upload_tail = 0u;
static uint16_t g_upload_count = 0u;
static uint32_t g_upload_dropped = 0u;
static bool g_upload_accepting = false;

void runtime_snapshot_init(void) {
    portENTER_CRITICAL(&g_snapshot_mux);
    memset(&g_snapshot, 0, sizeof(g_snapshot));
    g_snapshot.minimum_free_heap = ESP.getFreeHeap();
    g_snapshot.free_heap = g_snapshot.minimum_free_heap;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_snapshot_set_ble(bool connected, bool signal_timeout) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_snapshot.updated_ms = millis();
    g_snapshot.ble_connected = connected;
    g_snapshot.signal_timeout = signal_timeout;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_snapshot_set_uart_initialized(bool initialized) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_snapshot.updated_ms = millis();
    g_snapshot.uart_initialized = initialized;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_snapshot_update_network(bool wifi_connected, bool backend_available,
                                     uint32_t http_ok_count, uint32_t http_fail_count,
                                     uint32_t emg_upload_count, uint32_t emg_upload_drop_count) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_snapshot.updated_ms = millis();
    g_snapshot.wifi_connected = wifi_connected;
    g_snapshot.backend_available = backend_available;
    g_snapshot.http_ok_count = http_ok_count;
    g_snapshot.http_fail_count = http_fail_count;
    g_snapshot.emg_upload_count = emg_upload_count;
    g_snapshot.emg_upload_drop_count = emg_upload_drop_count;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_snapshot_update_emg_preview(uint32_t sample_timestamp_ms, uint8_t battery_percent,
                                         const uint8_t emg[RUNTIME_SNAPSHOT_PREVIEW_SAMPLES][RUNTIME_SNAPSHOT_CHANNELS],
                                         uint8_t sample_count) {
    if (sample_count > RUNTIME_SNAPSHOT_PREVIEW_SAMPLES) {
        sample_count = RUNTIME_SNAPSHOT_PREVIEW_SAMPLES;
    }
    portENTER_CRITICAL(&g_snapshot_mux);
    g_snapshot.updated_ms = millis();
    g_snapshot.sample_timestamp_ms = sample_timestamp_ms;
    g_snapshot.battery_percent = battery_percent;
    g_snapshot.emg_preview_count = sample_count;
    for (uint8_t row = 0; row < sample_count; ++row) {
        for (uint8_t ch = 0; ch < RUNTIME_SNAPSHOT_CHANNELS; ++ch) {
            g_snapshot.emg_preview[row][ch] = emg[row][ch];
        }
    }
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_snapshot_update_signal(uint32_t sample_timestamp_ms, uint8_t stable_gesture_id,
                                    uint8_t raw_top1, uint8_t validity, float raw_margin,
                                    bool ble_connected, bool signal_timeout,
                                    uint32_t notify_count, uint32_t valid_frame_count,
                                    uint32_t invalid_frame_count, uint32_t timestamp_gap_count,
                                    uint32_t estimated_missing_packets, uint32_t ble_queue_overflow_count,
                                    uint32_t inference_count, uint32_t inference_failure_count,
                                    uint32_t uart_tx_count, uint32_t uart_no_stable_count,
                                    uint32_t model_p50_us, uint32_t model_p95_us,
                                    uint32_t model_max_us, uint32_t free_heap,
                                    uint32_t minimum_free_heap, uint32_t state_seq) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_snapshot.updated_ms = millis();
    g_snapshot.sample_timestamp_ms = sample_timestamp_ms;
    g_snapshot.state_seq = state_seq;
    g_snapshot.stable_gesture_id = stable_gesture_id;
    g_snapshot.raw_top1 = raw_top1;
    g_snapshot.validity = validity;
    g_snapshot.raw_margin = raw_margin;
    g_snapshot.ble_connected = ble_connected;
    g_snapshot.signal_timeout = signal_timeout;
    g_snapshot.notify_count = notify_count;
    g_snapshot.valid_frame_count = valid_frame_count;
    g_snapshot.invalid_frame_count = invalid_frame_count;
    g_snapshot.timestamp_gap_count = timestamp_gap_count;
    g_snapshot.estimated_missing_packets = estimated_missing_packets;
    g_snapshot.ble_queue_overflow_count = ble_queue_overflow_count;
    g_snapshot.inference_count = inference_count;
    g_snapshot.inference_failure_count = inference_failure_count;
    g_snapshot.uart_tx_count = uart_tx_count;
    g_snapshot.uart_no_stable_count = uart_no_stable_count;
    g_snapshot.model_p50_us = model_p50_us;
    g_snapshot.model_p95_us = model_p95_us;
    g_snapshot.model_max_us = model_max_us;
    g_snapshot.free_heap = free_heap;
    if (g_snapshot.minimum_free_heap == 0u || minimum_free_heap < g_snapshot.minimum_free_heap) {
        g_snapshot.minimum_free_heap = minimum_free_heap;
    }
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_snapshot_get(RuntimeSnapshot *out) {
    if (out == 0) {
        return;
    }
    portENTER_CRITICAL(&g_snapshot_mux);
    *out = g_snapshot;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_emg_collection_begin(void) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_upload_head = 0u;
    g_upload_tail = 0u;
    g_upload_count = 0u;
    g_upload_dropped = 0u;
    g_upload_accepting = true;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_emg_collection_request_stop(void) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_upload_accepting = false;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_emg_collection_finish(void) {
    portENTER_CRITICAL(&g_snapshot_mux);
    g_upload_accepting = false;
    g_upload_head = 0u;
    g_upload_tail = 0u;
    g_upload_count = 0u;
    portEXIT_CRITICAL(&g_snapshot_mux);
}

void runtime_emg_collection_push(
    const uint8_t samples[][RUNTIME_SNAPSHOT_CHANNELS],
    uint8_t sample_count
) {
    portENTER_CRITICAL(&g_snapshot_mux);
    if (g_upload_accepting) {
        for (uint8_t row = 0u; row < sample_count; ++row) {
            if (g_upload_count >= RUNTIME_EMG_UPLOAD_QUEUE_SAMPLES) {
                g_upload_dropped += 1u;
                continue;
            }
            memcpy(g_upload_queue[g_upload_tail], samples[row], RUNTIME_SNAPSHOT_CHANNELS);
            g_upload_tail = (uint16_t)((g_upload_tail + 1u) % RUNTIME_EMG_UPLOAD_QUEUE_SAMPLES);
            g_upload_count += 1u;
        }
    }
    portEXIT_CRITICAL(&g_snapshot_mux);
}

uint16_t runtime_emg_collection_copy_batch(
    uint8_t out[][RUNTIME_SNAPSHOT_CHANNELS],
    uint16_t max_samples
) {
    portENTER_CRITICAL(&g_snapshot_mux);
    uint16_t count = g_upload_count < max_samples ? g_upload_count : max_samples;
    uint16_t index = g_upload_head;
    for (uint16_t row = 0u; row < count; ++row) {
        memcpy(out[row], g_upload_queue[index], RUNTIME_SNAPSHOT_CHANNELS);
        index = (uint16_t)((index + 1u) % RUNTIME_EMG_UPLOAD_QUEUE_SAMPLES);
    }
    portEXIT_CRITICAL(&g_snapshot_mux);
    return count;
}

void runtime_emg_collection_discard(uint16_t sample_count) {
    portENTER_CRITICAL(&g_snapshot_mux);
    uint16_t count = sample_count < g_upload_count ? sample_count : g_upload_count;
    g_upload_head = (uint16_t)((g_upload_head + count) % RUNTIME_EMG_UPLOAD_QUEUE_SAMPLES);
    g_upload_count = (uint16_t)(g_upload_count - count);
    portEXIT_CRITICAL(&g_snapshot_mux);
}

uint16_t runtime_emg_collection_pending(void) {
    portENTER_CRITICAL(&g_snapshot_mux);
    uint16_t count = g_upload_count;
    portEXIT_CRITICAL(&g_snapshot_mux);
    return count;
}

uint32_t runtime_emg_collection_dropped(void) {
    portENTER_CRITICAL(&g_snapshot_mux);
    uint32_t count = g_upload_dropped;
    portEXIT_CRITICAL(&g_snapshot_mux);
    return count;
}
