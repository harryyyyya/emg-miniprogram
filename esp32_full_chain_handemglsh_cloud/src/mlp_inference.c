#include "mlp_inference.h"

#include "emg_features.h"

static float mlp_relu(float value) {
    return value > 0.0f ? value : 0.0f;
}

static int mlp_argmax_margin(const float *scores, size_t class_count, uint32_t *predicted_index, float *margin) {
    size_t index;
    size_t best;
    size_t second;
    if (scores == 0 || predicted_index == 0 || margin == 0 || class_count < 2u) {
        return -1;
    }
    best = scores[1u] > scores[0u] ? 1u : 0u;
    second = best == 0u ? 1u : 0u;
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
) {
    size_t input;
    size_t hidden;
    size_t klass;
    if (model == 0 || window == 0 || features == 0 || standardized == 0 || hidden1 == 0 || hidden2 == 0 || scores == 0) {
        return -1;
    }
    if (model->input_count != 48u || model->hidden1_count != 64u || model->hidden2_count != 32u || model->class_count != 9u || model->channel_count != 8u || model->window_samples != 125u) {
        return -2;
    }
    if (emg_compute_stage2_selected_features(window, model->window_samples, model->channel_count, features, model->zc_threshold, model->ssc_threshold) != 0) {
        return -3;
    }
    for (input = 0u; input < model->input_count; ++input) {
        float scale = model->feature_scale[input] == 0.0f ? 1.0f : model->feature_scale[input];
        standardized[input] = (features[input] - model->feature_mean[input]) / scale;
    }
    for (hidden = 0u; hidden < model->hidden1_count; ++hidden) {
        float value = model->layer1_bias[hidden];
        for (input = 0u; input < model->input_count; ++input) {
            value += model->layer1_weights[hidden * model->input_count + input] * standardized[input];
        }
        hidden1[hidden] = mlp_relu(value);
    }
    for (hidden = 0u; hidden < model->hidden2_count; ++hidden) {
        float value = model->layer2_bias[hidden];
        for (input = 0u; input < model->hidden1_count; ++input) {
            value += model->layer2_weights[hidden * model->hidden1_count + input] * hidden1[input];
        }
        hidden2[hidden] = mlp_relu(value);
    }
    for (klass = 0u; klass < model->class_count; ++klass) {
        float value = model->layer3_bias[klass];
        for (input = 0u; input < model->hidden2_count; ++input) {
            value += model->layer3_weights[klass * model->hidden2_count + input] * hidden2[input];
        }
        scores[klass] = value;
    }
    return mlp_argmax_margin(scores, model->class_count, predicted_index, margin);
}
