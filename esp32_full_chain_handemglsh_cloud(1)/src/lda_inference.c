#include "lda_inference.h"
#include "emg_features.h"

int emg_standardize_features(const EmgLdaModel *model, const float *features, float *standardized) {
    size_t index;
    if (model == 0 || features == 0 || standardized == 0) {
        return -1;
    }
    for (index = 0u; index < model->feature_count; ++index) {
        float scale = model->feature_scale[index] == 0.0f ? 1.0f : model->feature_scale[index];
        standardized[index] = (features[index] - model->feature_mean[index]) / scale;
    }
    return 0;
}

int emg_lda_compute_scores(const EmgLdaModel *model, const float *standardized, float *scores) {
    size_t klass;
    if (model == 0 || standardized == 0 || scores == 0) {
        return -1;
    }
    for (klass = 0u; klass < model->class_count; ++klass) {
        size_t feature;
        float score = model->intercept[klass];
        for (feature = 0u; feature < model->feature_count; ++feature) {
            score += model->coefficients[klass * model->feature_count + feature] * standardized[feature];
        }
        scores[klass] = score;
    }
    return 0;
}

int emg_lda_argmax(const float *scores, size_t class_count, uint32_t *predicted_index) {
    size_t index;
    size_t best = 0u;
    if (scores == 0 || predicted_index == 0 || class_count == 0u) {
        return -1;
    }
    for (index = 1u; index < class_count; ++index) {
        if (scores[index] > scores[best]) {
            best = index;
        }
    }
    *predicted_index = (uint32_t)best;
    return 0;
}

int emg_lda_argmax_margin(const float *scores, size_t class_count, uint32_t *predicted_index, float *margin) {
    size_t index;
    size_t best = 0u;
    size_t second = 0u;
    if (scores == 0 || predicted_index == 0 || margin == 0 || class_count < 2u) {
        return -1;
    }
    if (scores[1] > scores[0]) {
        best = 1u;
        second = 0u;
    } else {
        best = 0u;
        second = 1u;
    }
    for (index = 2u; index < class_count; ++index) {
        if (scores[index] > scores[best]) {
            second = best;
            best = index;
        } else if (scores[index] > scores[second]) {
            second = index;
        }
    }
    *predicted_index = (uint32_t)best;
    *margin = scores[best] - scores[second];
    return 0;
}

int emg_lda_predict(const EmgLdaModel *model, const float *features, float *standardized, float *scores, uint32_t *predicted_index) {
    if (emg_standardize_features(model, features, standardized) != 0) {
        return -1;
    }
    if (emg_lda_compute_scores(model, standardized, scores) != 0) {
        return -2;
    }
    if (emg_lda_argmax(scores, model->class_count, predicted_index) != 0) {
        return -3;
    }
    return 0;
}

int emg_lda_predict_window(const EmgLdaModel *model, const float *window, float *features, float *standardized, float *scores, uint32_t *predicted_index) {
    if (model == 0) {
        return -1;
    }
    if (model->feature_count == model->channel_count * 6u) {
        return emg_lda_predict_stage2_window(model, window, features, standardized, scores, predicted_index);
    }
    if (model->feature_count != model->channel_count * 7u) {
        return -4;
    }
    if (emg_compute_features(window, model->sample_count, model->channel_count, features, model->zc_threshold, model->ssc_threshold) != 0) {
        return -2;
    }
    return emg_lda_predict(model, features, standardized, scores, predicted_index);
}

int emg_lda_predict_stage2_window(const EmgLdaModel *model, const float *window, float *features, float *standardized, float *scores, uint32_t *predicted_index) {
    if (model == 0) {
        return -1;
    }
    if (model->feature_count != model->channel_count * 6u) {
        return -4;
    }
    if (emg_compute_stage2_selected_features(window, model->sample_count, model->channel_count, features, model->zc_threshold, model->ssc_threshold) != 0) {
        return -2;
    }
    return emg_lda_predict(model, features, standardized, scores, predicted_index);
}
