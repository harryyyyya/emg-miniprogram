#include <Arduino.h>
#include <string.h>

#include "stage5_replay_runner.h"
#include "frame_stream_parser.h"
#include "sample_ring_buffer.h"
extern "C" {
#include "emg_features.h"
#include "lda_inference.h"
#include "emg_controller.h"
}
#include "stage6_1c_integration_config.h"
#include "../generated/lda_model.h"

#define STAGE5_SAMPLE_INTERVAL_MS 2u
#define STAGE5_PACKET_INTERVAL_MS 20u
#define STAGE5_STEP_SAMPLES 20u
#define STAGE5_TIMING_CAP 128u
#define STAGE5_STATUS_INTERVAL_MS 1000u
#define STAGE5_IDLE_TIMEOUT_MS 500u

typedef struct Stage5Session {
    Stage5FrameStreamParser parser;
    Stage5SampleRingBuffer ring_buffer;
    EmgController controller;
    EmgControllerOutput last_output;
    uint32_t timing_history[STAGE5_TIMING_CAP];
    uint32_t timing_count;
    uint32_t timing_write;
    uint32_t parsed_frame_count;
    uint32_t total_sample_count;
    uint32_t inference_count;
    uint32_t inference_failure_count;
    uint32_t dropped_packet_count;
    uint32_t continuity_reset_count;
    uint32_t samples_since_last_inference;
    uint32_t last_packet_timestamp_ms;
    uint32_t last_status_ms;
    uint32_t last_rx_ms;
    uint8_t last_battery_percent;
    uint8_t session_active;
    uint8_t has_last_packet_timestamp;
} Stage5Session;

static Stage5Session g_session;
static float g_window[STAGE4_WINDOW_SAMPLES * STAGE4_CHANNEL_COUNT];
static float g_features[STAGE4_FEATURE_COUNT];
static float g_standardized[STAGE4_FEATURE_COUNT];
static float g_scores[STAGE4_CLASS_COUNT];
static uint32_t g_timing_scratch[STAGE5_TIMING_CAP];

static EmgControllerConfig stage5_controller_config(void) {
    EmgControllerConfig cfg;
    cfg.margin_threshold = STAGE4_MARGIN_THRESHOLD;
    cfg.vote_horizon_ms = STAGE4_VOTE_HORIZON_MS;
    cfg.vote_required_fraction = STAGE4_VOTE_REQUIRED_FRACTION;
    cfg.nominal_step_ms = STAGE4_STEP_MS;
    cfg.low_confidence_hold_ms = STAGE4_LOW_CONFIDENCE_HOLD_MS;
    cfg.rest_label = STAGE4_REST_LABEL;
    return cfg;
}

static void stage5_sort_u32(uint32_t *values, uint32_t count) {
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

static uint32_t stage5_p95_us(void) {
    if (g_session.timing_count == 0u) {
        return 0u;
    }
    for (uint32_t index = 0u; index < g_session.timing_count; ++index) {
        g_timing_scratch[index] = g_session.timing_history[index];
    }
    stage5_sort_u32(g_timing_scratch, g_session.timing_count);
    return g_timing_scratch[(g_session.timing_count - 1u) * 95u / 100u];
}

static void stage5_record_timing(uint32_t inference_us) {
    g_session.timing_history[g_session.timing_write] = inference_us;
    g_session.timing_write = (g_session.timing_write + 1u) % STAGE5_TIMING_CAP;
    if (g_session.timing_count < STAGE5_TIMING_CAP) {
        g_session.timing_count += 1u;
    }
}

static void stage5_reset_runtime(void) {
    stage5_frame_stream_parser_init(&g_session.parser);
    stage5_sample_ring_buffer_init(&g_session.ring_buffer);
    emg_controller_init(&g_session.controller, stage5_controller_config());
    memset(g_session.timing_history, 0, sizeof(g_session.timing_history));
    memset(&g_session.last_output, 0, sizeof(g_session.last_output));
    g_session.timing_count = 0u;
    g_session.timing_write = 0u;
    g_session.parsed_frame_count = 0u;
    g_session.total_sample_count = 0u;
    g_session.inference_count = 0u;
    g_session.inference_failure_count = 0u;
    g_session.dropped_packet_count = 0u;
    g_session.continuity_reset_count = 0u;
    g_session.samples_since_last_inference = 0u;
    g_session.last_packet_timestamp_ms = 0u;
    g_session.last_battery_percent = 0u;
    g_session.has_last_packet_timestamp = 0u;
    g_session.last_status_ms = millis();
}

static void stage5_print_begin(void) {
    Serial.println("STAGE5_REPLAY_BEGIN");
    Serial.print("mode=RECORDED_EMG_REALTIME_REPLAY");
    Serial.print(" frame_size="); Serial.print(STAGE5_FRAME_SIZE);
    Serial.print(" window_samples="); Serial.print(STAGE4_WINDOW_SAMPLES);
    Serial.print(" channel_count="); Serial.print(STAGE4_CHANNEL_COUNT);
    Serial.print(" step_samples="); Serial.print(STAGE5_STEP_SAMPLES);
    Serial.print(" margin_threshold="); Serial.print(STAGE4_MARGIN_THRESHOLD, 6);
    Serial.print(" vote_horizon_ms="); Serial.print(STAGE4_VOTE_HORIZON_MS);
    Serial.print(" vote_required_fraction="); Serial.print(STAGE4_VOTE_REQUIRED_FRACTION, 2);
    Serial.print(" free_heap="); Serial.print(ESP.getFreeHeap());
    Serial.print(" free_psram="); Serial.println(ESP.getFreePsram());
}

static void stage5_print_status(const char *reason) {
    Serial.print("REPLAY_STATUS");
    Serial.print(" reason="); Serial.print(reason);
    Serial.print(" result="); Serial.print(g_session.inference_failure_count == 0u ? "PASS" : "FAIL");
    Serial.print(" parsed_frames="); Serial.print(g_session.parsed_frame_count);
    Serial.print(" parsed_frame_count="); Serial.print(g_session.parsed_frame_count);
    Serial.print(" sample_count="); Serial.print(g_session.total_sample_count);
    Serial.print(" inferred_windows="); Serial.print(g_session.inference_count);
    Serial.print(" inference_count="); Serial.print(g_session.inference_count);
    Serial.print(" dropped_packet_count="); Serial.print(g_session.dropped_packet_count);
    Serial.print(" parse_error_count="); Serial.print(g_session.parser.parse_error_count);
    Serial.print(" discarded_byte_count="); Serial.print(g_session.parser.discarded_byte_count);
    Serial.print(" continuity_reset_count="); Serial.print(g_session.continuity_reset_count);
    Serial.print(" inference_failure_count="); Serial.print(g_session.inference_failure_count);
    Serial.print(" pipeline_p95_us="); Serial.print(stage5_p95_us());
    Serial.print(" inference_p95_us="); Serial.print(stage5_p95_us());
    Serial.print(" pending_bytes="); Serial.print(stage5_frame_stream_parser_pending_bytes(&g_session.parser));
    Serial.print(" battery_percent="); Serial.print(g_session.last_battery_percent);
    Serial.print(" free_heap="); Serial.print(ESP.getFreeHeap());
    Serial.print(" free_psram="); Serial.print(ESP.getFreePsram());
    Serial.print(" uptime_ms="); Serial.println(millis());
}

static void stage5_print_state(const EmgControllerOutput *output, uint32_t inference_us) {
    Serial.print("REPLAY_STATE");
    Serial.print(" timestamp_ms="); Serial.print(output->timestamp_ms);
    Serial.print(" parsed_frame_count="); Serial.print(g_session.parsed_frame_count);
    Serial.print(" frame_seq="); Serial.print(output->frame_seq);
    Serial.print(" state_seq="); Serial.print(output->state_seq);
    Serial.print(" gesture="); Serial.print(output->gesture_id);
    Serial.print(" gesture_id="); Serial.print(output->gesture_id);
    Serial.print(" validity="); Serial.print((uint32_t)output->validity);
    Serial.print(" candidate="); Serial.print(output->candidate_label);
    Serial.print(" candidate_label="); Serial.print(output->candidate_label);
    Serial.print(" margin="); Serial.print(output->margin, 6);
    Serial.print(" inference_us="); Serial.print(inference_us);
    Serial.print(" pipeline_p95_us="); Serial.print(stage5_p95_us());
    Serial.print(" inference_p95_us="); Serial.print(stage5_p95_us());
    Serial.print(" dropped_packet_count="); Serial.print(g_session.dropped_packet_count);
    Serial.print(" parse_error_count="); Serial.print(g_session.parser.parse_error_count);
    Serial.print(" free_heap="); Serial.println(ESP.getFreeHeap());
}

static void stage5_print_end(const char *reason) {
    Serial.print("STAGE5_REPLAY_SUMMARY");
    Serial.print(" reason="); Serial.print(reason);
    Serial.print(" replay_frame_count="); Serial.print(g_session.parsed_frame_count);
    Serial.print(" parsed_frames="); Serial.print(g_session.parsed_frame_count);
    Serial.print(" parsed_frame_count="); Serial.print(g_session.parsed_frame_count);
    Serial.print(" inference_count="); Serial.print(g_session.inference_count);
    Serial.print(" dropped_packet_count="); Serial.print(g_session.dropped_packet_count);
    Serial.print(" parse_error_count="); Serial.print(g_session.parser.parse_error_count);
    Serial.print(" discarded_byte_count="); Serial.print(g_session.parser.discarded_byte_count);
    Serial.print(" pipeline_p95_us="); Serial.print(stage5_p95_us());
    Serial.print(" inference_p95_us="); Serial.print(stage5_p95_us());
    Serial.print(" free_heap="); Serial.print(ESP.getFreeHeap());
    Serial.print(" free_psram="); Serial.println(ESP.getFreePsram());
    Serial.println("STAGE5_REPLAY_END");
}

static void stage5_begin_session(void) {
    stage5_reset_runtime();
    g_session.session_active = 1u;
    g_session.last_rx_ms = millis();
    stage5_print_begin();
}

static void stage5_end_session(const char *reason) {
    size_t pending_bytes = stage5_frame_stream_parser_pending_bytes(&g_session.parser);
    if (pending_bytes > 0u) {
        g_session.parser.parse_error_count += 1u;
        g_session.parser.discarded_byte_count += (uint32_t)pending_bytes;
    }
    stage5_print_status("final");
    stage5_print_end(reason);
    g_session.session_active = 0u;
    stage5_frame_stream_parser_reset(&g_session.parser);
    stage5_sample_ring_buffer_reset(&g_session.ring_buffer);
    g_session.samples_since_last_inference = 0u;
    g_session.has_last_packet_timestamp = 0u;
}

static void stage5_reset_continuity(const char *reason) {
    stage5_sample_ring_buffer_reset(&g_session.ring_buffer);
    emg_controller_reset_for_continuity_block(&g_session.controller);
    g_session.samples_since_last_inference = 0u;
    g_session.continuity_reset_count += 1u;
    stage5_print_status(reason);
}

static void stage5_run_inference(uint32_t sample_timestamp_ms) {
    uint32_t predicted_label = STAGE4_REST_LABEL;
    float margin = 0.0f;
    EmgControllerOutput output;
    int predict_status;
    uint32_t start_us;
    uint32_t inference_us;

    stage5_sample_ring_buffer_copy_window(&g_session.ring_buffer, g_window);
    start_us = micros();
    predict_status = emg_lda_predict_stage2_window(
        &EMG_STAGE2_LDA_MODEL,
        g_window,
        g_features,
        g_standardized,
        g_scores,
        &predicted_label
    );
    if (predict_status == 0) {
        predict_status = emg_lda_argmax_margin(g_scores, STAGE4_CLASS_COUNT, &predicted_label, &margin);
    }
    inference_us = micros() - start_us;
    stage5_record_timing(inference_us);
    g_session.inference_count += 1u;

    if (predict_status != 0) {
        g_session.inference_failure_count += 1u;
        predicted_label = STAGE4_REST_LABEL;
        margin = 0.0f;
    }

    emg_controller_update(
        &g_session.controller,
        sample_timestamp_ms,
        predicted_label,
        margin,
        predict_status == 0 ? 1 : 0,
        &output
    );
    g_session.last_output = output;
    stage5_print_state(&output, inference_us);
}

static void stage5_handle_frame(const Stage5Frame *frame) {
    if (g_session.has_last_packet_timestamp) {
        if (frame->timestamp_ms < g_session.last_packet_timestamp_ms) {
            stage5_reset_continuity("timestamp_retreat");
        } else {
            uint32_t delta_ms = frame->timestamp_ms - g_session.last_packet_timestamp_ms;
            if (delta_ms == 0u) {
                stage5_reset_continuity("duplicate_timestamp");
            } else if (delta_ms != STAGE5_PACKET_INTERVAL_MS) {
                if (delta_ms > STAGE5_PACKET_INTERVAL_MS && (delta_ms % STAGE5_PACKET_INTERVAL_MS) == 0u) {
                    g_session.dropped_packet_count += (delta_ms / STAGE5_PACKET_INTERVAL_MS) - 1u;
                    stage5_reset_continuity("packet_gap");
                } else {
                    stage5_reset_continuity("packet_interval_error");
                }
            }
        }
    }

    g_session.last_packet_timestamp_ms = frame->timestamp_ms;
    g_session.has_last_packet_timestamp = 1u;
    g_session.parsed_frame_count += 1u;
    g_session.last_battery_percent = frame->battery_percent;

    for (uint32_t sample = 0u; sample < STAGE5_SAMPLES_PER_FRAME; ++sample) {
        uint32_t sample_timestamp_ms = frame->timestamp_ms + sample * STAGE5_SAMPLE_INTERVAL_MS;
        stage5_sample_ring_buffer_push(&g_session.ring_buffer, frame->emg[sample], STAGE4_FIXED_BASELINE);
        g_session.total_sample_count += 1u;
        g_session.samples_since_last_inference += 1u;
        if (stage5_sample_ring_buffer_ready(&g_session.ring_buffer) && g_session.samples_since_last_inference >= STAGE5_STEP_SAMPLES) {
            g_session.samples_since_last_inference = 0u;
            stage5_run_inference(sample_timestamp_ms);
        }
    }
}

void stage5_replay_setup(void) {
    memset(&g_session, 0, sizeof(g_session));
    stage5_reset_runtime();
    Serial.println("STAGE5_REPLAY_BOOT");
    Serial.println("STAGE5_READY serial_ready=1 baud=921600");
}

void stage5_replay_loop(void) {
    while (Serial.available() > 0) {
        Stage5Frame frame;
        int read_value = Serial.read();
        int frame_ready;
        if (read_value < 0) {
            break;
        }
        if (!g_session.session_active) {
            stage5_begin_session();
        }
        g_session.last_rx_ms = millis();
        frame_ready = stage5_frame_stream_parser_feed_byte(&g_session.parser, (uint8_t)read_value, &frame);
        if (frame_ready > 0) {
            stage5_handle_frame(&frame);
        }
    }

    if (g_session.session_active && (millis() - g_session.last_rx_ms) >= STAGE5_IDLE_TIMEOUT_MS) {
        stage5_end_session("idle_timeout");
        return;
    }

    if (g_session.session_active && (millis() - g_session.last_status_ms) >= STAGE5_STATUS_INTERVAL_MS) {
        g_session.last_status_ms = millis();
        stage5_print_status("periodic");
    }
}
