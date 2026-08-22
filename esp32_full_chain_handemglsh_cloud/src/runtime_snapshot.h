#ifndef RUNTIME_SNAPSHOT_H
#define RUNTIME_SNAPSHOT_H

#include <stdint.h>

#define RUNTIME_SNAPSHOT_PREVIEW_SAMPLES 10u
#define RUNTIME_SNAPSHOT_CHANNELS 8u
#define RUNTIME_EMG_UPLOAD_QUEUE_SAMPLES 3000u
#define RUNTIME_EMG_UPLOAD_BATCH_SAMPLES 250u

typedef struct RuntimeSnapshot {
    uint32_t updated_ms;
    uint32_t sample_timestamp_ms;
    uint32_t state_seq;

    uint8_t stable_gesture_id;
    uint8_t raw_top1;
    uint8_t validity;
    uint8_t battery_percent;

    float raw_margin;

    bool ble_connected;
    bool wifi_connected;
    bool backend_available;
    bool uart_initialized;
    bool signal_timeout;

    uint32_t notify_count;
    uint32_t valid_frame_count;
    uint32_t invalid_frame_count;
    uint32_t timestamp_gap_count;
    uint32_t estimated_missing_packets;
    uint32_t ble_queue_overflow_count;
    uint32_t inference_count;
    uint32_t inference_failure_count;
    uint32_t uart_tx_count;
    uint32_t uart_no_stable_count;

    uint32_t model_p50_us;
    uint32_t model_p95_us;
    uint32_t model_max_us;

    uint32_t http_ok_count;
    uint32_t http_fail_count;
    uint32_t emg_upload_count;
    uint32_t emg_upload_drop_count;

    uint32_t free_heap;
    uint32_t minimum_free_heap;

    uint8_t emg_preview_count;
    uint8_t emg_preview[RUNTIME_SNAPSHOT_PREVIEW_SAMPLES][RUNTIME_SNAPSHOT_CHANNELS];
} RuntimeSnapshot;

void runtime_snapshot_init(void);
void runtime_snapshot_set_ble(bool connected, bool signal_timeout);
void runtime_snapshot_set_uart_initialized(bool initialized);
void runtime_snapshot_update_network(bool wifi_connected, bool backend_available,
                                     uint32_t http_ok_count, uint32_t http_fail_count,
                                     uint32_t emg_upload_count, uint32_t emg_upload_drop_count);
void runtime_snapshot_update_emg_preview(uint32_t sample_timestamp_ms, uint8_t battery_percent,
                                         const uint8_t emg[RUNTIME_SNAPSHOT_PREVIEW_SAMPLES][RUNTIME_SNAPSHOT_CHANNELS],
                                         uint8_t sample_count);
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
                                    uint32_t minimum_free_heap, uint32_t state_seq);
void runtime_snapshot_get(RuntimeSnapshot *out);

void runtime_emg_collection_begin(void);
void runtime_emg_collection_request_stop(void);
void runtime_emg_collection_finish(void);
void runtime_emg_collection_push(
    const uint8_t samples[][RUNTIME_SNAPSHOT_CHANNELS],
    uint8_t sample_count
);
uint16_t runtime_emg_collection_copy_batch(
    uint8_t out[][RUNTIME_SNAPSHOT_CHANNELS],
    uint16_t max_samples
);
void runtime_emg_collection_discard(uint16_t sample_count);
uint16_t runtime_emg_collection_pending(void);
uint32_t runtime_emg_collection_dropped(void);

#endif
