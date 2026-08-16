#include "sample_ring_buffer.h"

void stage5_sample_ring_buffer_init(Stage5SampleRingBuffer *buffer) {
    stage5_sample_ring_buffer_reset(buffer);
}

void stage5_sample_ring_buffer_reset(Stage5SampleRingBuffer *buffer) {
    if (buffer == 0) {
        return;
    }
    buffer->write_index = 0u;
    buffer->count = 0u;
}

void stage5_sample_ring_buffer_push(Stage5SampleRingBuffer *buffer, const uint8_t row[STAGE5_RING_CHANNELS], float baseline) {
    uint16_t base;
    if (buffer == 0 || row == 0) {
        return;
    }
    base = (uint16_t)(buffer->write_index * STAGE5_RING_CHANNELS);
    for (uint16_t channel = 0u; channel < STAGE5_RING_CHANNELS; ++channel) {
        buffer->samples[base + channel] = (float)row[channel] - baseline;
    }
    buffer->write_index = (uint16_t)((buffer->write_index + 1u) % STAGE5_RING_WINDOW_SAMPLES);
    if (buffer->count < STAGE5_RING_WINDOW_SAMPLES) {
        buffer->count += 1u;
    }
}

int stage5_sample_ring_buffer_ready(const Stage5SampleRingBuffer *buffer) {
    return buffer != 0 && buffer->count >= STAGE5_RING_WINDOW_SAMPLES;
}

void stage5_sample_ring_buffer_copy_window(const Stage5SampleRingBuffer *buffer, float *window_out) {
    uint16_t start;
    if (buffer == 0 || window_out == 0 || buffer->count < STAGE5_RING_WINDOW_SAMPLES) {
        return;
    }
    start = buffer->write_index;
    for (uint16_t sample = 0u; sample < STAGE5_RING_WINDOW_SAMPLES; ++sample) {
        uint16_t source_index = (uint16_t)(((start + sample) % STAGE5_RING_WINDOW_SAMPLES) * STAGE5_RING_CHANNELS);
        uint16_t target_index = (uint16_t)(sample * STAGE5_RING_CHANNELS);
        for (uint16_t channel = 0u; channel < STAGE5_RING_CHANNELS; ++channel) {
            window_out[target_index + channel] = buffer->samples[source_index + channel];
        }
    }
}
