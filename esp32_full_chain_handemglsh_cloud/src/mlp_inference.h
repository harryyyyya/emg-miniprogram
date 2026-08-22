#ifndef LSH_MLP_INFERENCE_H
#define LSH_MLP_INFERENCE_H

#include <stddef.h>
#include <stdint.h>

typedef struct LshMlpModel {
    size_t input_count;
    size_t hidden1_count;
    size_t hidden2_count;
    size_t class_count;
    size_t window_samples;
    size_t channel_count;
    float zc_threshold;
    float ssc_threshold;
    const float *feature_mean;
    const float *feature_scale;
    const float *layer1_weights;
    const float *layer1_bias;
    const float *layer2_weights;
    const float *layer2_bias;
    const float *layer3_weights;
    const float *layer3_bias;
} LshMlpModel;

/* The input window is already fixed-baseline centered by sample_ring_buffer. */
int emg_mlp_predict_stage2_window(
    const LshMlpModel *model,
    const float *window,
    float *features,
    float *standardized,
    float *hidden1,
    float *hidden2,
    float *scores,
    uint32_t *predicted_index,
    float *margin
);

#endif
