#include "emg_controller.h"

static void emg_controller_clear_votes(EmgController *controller) {
    controller->vote_count = 0u;
    controller->has_election_start = 0u;
}

static void emg_controller_reset_to_rest(EmgController *controller) {
    emg_controller_clear_votes(controller);
    controller->stable_label = controller->config.rest_label;
    controller->has_last_confident_timestamp = 0u;
}

static void emg_controller_emit(EmgController *controller, uint32_t timestamp_ms, uint32_t gesture_id, EmgValidity validity, float margin, uint32_t candidate_label, EmgControllerOutput *output) {
    if (gesture_id != controller->last_output.gesture_id || validity != controller->last_output.validity) {
        controller->state_seq += 1u;
    }
    output->frame_seq = controller->frame_seq;
    output->state_seq = controller->state_seq;
    output->gesture_id = gesture_id;
    output->validity = validity;
    output->margin = margin;
    output->timestamp_ms = timestamp_ms;
    output->candidate_label = candidate_label;
    controller->last_output = *output;
}

void emg_controller_init(EmgController *controller, EmgControllerConfig config) {
    controller->config = config;
    controller->frame_seq = 0u;
    controller->state_seq = 0u;
    controller->stable_label = config.rest_label;
    controller->last_timestamp_ms = 0u;
    controller->has_last_timestamp = 0u;
    controller->last_confident_timestamp_ms = 0u;
    controller->has_last_confident_timestamp = 0u;
    controller->election_start_timestamp_ms = 0u;
    controller->has_election_start = 0u;
    controller->vote_count = 0u;
    controller->last_output.frame_seq = 0u;
    controller->last_output.state_seq = 0u;
    controller->last_output.gesture_id = config.rest_label;
    controller->last_output.validity = EMG_VALIDITY_VALID;
    controller->last_output.margin = 0.0f;
    controller->last_output.timestamp_ms = 0u;
    controller->last_output.candidate_label = config.rest_label;
}

void emg_controller_reset_for_continuity_block(EmgController *controller) {
    emg_controller_reset_to_rest(controller);
    controller->has_last_timestamp = 0u;
    controller->last_output.gesture_id = controller->config.rest_label;
    controller->last_output.validity = EMG_VALIDITY_VALID;
}

static void emg_controller_add_vote(EmgController *controller, uint32_t timestamp_ms, uint32_t candidate_label) {
    size_t write_index;
    size_t read_index;
    size_t new_count = 0u;
    for (read_index = 0u; read_index < controller->vote_count; ++read_index) {
        if (timestamp_ms - controller->vote_timestamps[read_index] <= controller->config.vote_horizon_ms) {
            controller->vote_timestamps[new_count] = controller->vote_timestamps[read_index];
            controller->vote_labels[new_count] = controller->vote_labels[read_index];
            new_count += 1u;
        }
    }
    controller->vote_count = new_count;
    write_index = controller->vote_count;
    if (write_index < 16u) {
        controller->vote_timestamps[write_index] = timestamp_ms;
        controller->vote_labels[write_index] = candidate_label;
        controller->vote_count += 1u;
    }
}

static int emg_controller_election_mature(const EmgController *controller, uint32_t timestamp_ms) {
    uint32_t min_count = controller->config.vote_horizon_ms / controller->config.nominal_step_ms + 1u;
    if (!controller->has_election_start) {
        return 0;
    }
    if (controller->vote_count < (size_t)min_count) {
        return 0;
    }
    return (timestamp_ms - controller->election_start_timestamp_ms) >= controller->config.vote_horizon_ms;
}

static int emg_controller_majority_label(const EmgController *controller, uint32_t *label_out) {
    size_t i;
    size_t j;
    for (i = 0u; i < controller->vote_count; ++i) {
        uint32_t label = controller->vote_labels[i];
        size_t count = 0u;
        for (j = 0u; j < controller->vote_count; ++j) {
            if (controller->vote_labels[j] == label) {
                count += 1u;
            }
        }
        if (((float)count / (float)controller->vote_count) >= controller->config.vote_required_fraction) {
            *label_out = label;
            return 1;
        }
    }
    return 0;
}

int emg_controller_update(EmgController *controller, uint32_t timestamp_ms, uint32_t candidate_label, float margin, int valid_signal, EmgControllerOutput *output) {
    controller->frame_seq += 1u;
    if (controller->has_last_timestamp && timestamp_ms < controller->last_timestamp_ms) {
        emg_controller_reset_to_rest(controller);
        controller->has_last_timestamp = 0u;
        emg_controller_emit(controller, timestamp_ms, controller->config.rest_label, EMG_VALIDITY_SIGNAL_INVALID, margin, candidate_label, output);
        return 0;
    }
    controller->last_timestamp_ms = timestamp_ms;
    controller->has_last_timestamp = 1u;
    if (!valid_signal) {
        emg_controller_reset_to_rest(controller);
        emg_controller_emit(controller, timestamp_ms, controller->config.rest_label, EMG_VALIDITY_SIGNAL_INVALID, margin, candidate_label, output);
        return 0;
    }
    if (margin < controller->config.margin_threshold) {
        int hold_active = controller->has_last_confident_timestamp && (timestamp_ms - controller->last_confident_timestamp_ms <= controller->config.low_confidence_hold_ms);
        if (!hold_active) {
            emg_controller_reset_to_rest(controller);
        }
        emg_controller_emit(controller, timestamp_ms, hold_active ? controller->stable_label : controller->config.rest_label, EMG_VALIDITY_LOW_CONFIDENCE_SAFE, margin, candidate_label, output);
        return 0;
    }
    controller->last_confident_timestamp_ms = timestamp_ms;
    controller->has_last_confident_timestamp = 1u;
    if (!controller->has_election_start) {
        controller->election_start_timestamp_ms = timestamp_ms;
        controller->has_election_start = 1u;
    }
    emg_controller_add_vote(controller, timestamp_ms, candidate_label);
    if (emg_controller_election_mature(controller, timestamp_ms)) {
        uint32_t voted_label = controller->stable_label;
        if (emg_controller_majority_label(controller, &voted_label)) {
            controller->stable_label = voted_label;
        }
    }
    emg_controller_emit(controller, timestamp_ms, controller->stable_label, EMG_VALIDITY_VALID, margin, candidate_label, output);
    return 0;
}
