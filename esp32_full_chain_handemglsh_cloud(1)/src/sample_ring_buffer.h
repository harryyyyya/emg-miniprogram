#ifndef STAGE5_SAMPLE_RING_BUFFER_H
#define STAGE5_SAMPLE_RING_BUFFER_H

#include <stdint.h>

#define STAGE5_RING_WINDOW_SAMPLES 125u
#define STAGE5_RING_CHANNELS 8u

typedef struct Stage5SampleRingBuffer {
    float samples[STAGE5_RING_WINDOW_SAMPLES * STAGE5_RING_CHANNELS];
    uint16_t write_index;
    uint16_t count;
} Stage5SampleRingBuffer;

void stage5_sample_ring_buffer_init(Stage5SampleRingBuffer *buffer);
void stage5_sample_ring_buffer_reset(Stage5SampleRingBuffer *buffer);
void stage5_sample_ring_buffer_push(Stage5SampleRingBuffer *buffer, const uint8_t row[STAGE5_RING_CHANNELS], float baseline);
int stage5_sample_ring_buffer_ready(const Stage5SampleRingBuffer *buffer);
void stage5_sample_ring_buffer_copy_window(const Stage5SampleRingBuffer *buffer, float *window_out);

#endif
