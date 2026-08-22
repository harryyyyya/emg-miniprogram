#ifndef EMG_CONTROLLER_H
#define EMG_CONTROLLER_H

#include <stddef.h>
#include <stdint.h>

typedef enum EmgValidity {
    EMG_VALIDITY_VALID = 0,
    EMG_VALIDITY_LOW_CONFIDENCE_SAFE = 1,
    EMG_VALIDITY_SIGNAL_INVALID = 2
} EmgValidity;

typedef struct EmgControllerConfig {
    float margin_threshold;
    uint32_t vote_horizon_ms;
    float vote_required_fraction;
    uint32_t nominal_step_ms;
    uint32_t low_confidence_hold_ms;
    uint32_t rest_label;
} EmgControllerConfig;

typedef struct EmgControllerOutput {
    uint32_t frame_seq;
    uint32_t state_seq;
    uint32_t gesture_id;
    EmgValidity validity;
    float margin;
    uint32_t timestamp_ms;
    uint32_t candidate_label;
} EmgControllerOutput;

typedef struct EmgController {
    EmgControllerConfig config;
    uint32_t frame_seq;
    uint32_t state_seq;
    uint32_t stable_label;
    uint32_t last_timestamp_ms;
    uint32_t has_last_timestamp;
    uint32_t last_confident_timestamp_ms;
    uint32_t has_last_confident_timestamp;
    uint32_t election_start_timestamp_ms;
    uint32_t has_election_start;
    uint32_t vote_labels[16];
    uint32_t vote_timestamps[16];
    size_t vote_count;
    EmgControllerOutput last_output;
} EmgController;

void emg_controller_init(EmgController *controller, EmgControllerConfig config);
void emg_controller_reset_for_continuity_block(EmgController *controller);
int emg_controller_update(EmgController *controller, uint32_t timestamp_ms, uint32_t candidate_label, float margin, int valid_signal, EmgControllerOutput *output);

#endif
