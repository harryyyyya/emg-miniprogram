#ifndef LDA_INFERENCE_H
#define LDA_INFERENCE_H

#include <stddef.h>
#include <stdint.h>

typedef struct EmgLdaModel {
    size_t channel_count;
    size_t sample_count;
    size_t feature_count;
    size_t class_count;
    float zc_threshold;
    float ssc_threshold;
    const float *feature_mean;
    const float *feature_scale;
    const float *coefficients;
    const float *intercept;
} EmgLdaModel;

int emg_standardize_features(const EmgLdaModel *model, const float *features, float *standardized);
int emg_lda_compute_scores(const EmgLdaModel *model, const float *standardized, float *scores);
int emg_lda_argmax(const float *scores, size_t class_count, uint32_t *predicted_index);
int emg_lda_argmax_margin(const float *scores, size_t class_count, uint32_t *predicted_index, float *margin);
int emg_lda_predict(const EmgLdaModel *model, const float *features, float *standardized, float *scores, uint32_t *predicted_index);
int emg_lda_predict_window(const EmgLdaModel *model, const float *window, float *features, float *standardized, float *scores, uint32_t *predicted_index);
int emg_lda_predict_stage2_window(const EmgLdaModel *model, const float *window, float *features, float *standardized, float *scores, uint32_t *predicted_index);

#endif
