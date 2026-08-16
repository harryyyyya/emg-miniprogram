#include "emg_features.h"

static float emg_absf(float value) {
    return value < 0.0f ? -value : value;
}

static float emg_sqrtf(float value) {
    float guess;
    int index;
    if (value <= 0.0f) {
        return 0.0f;
    }
    guess = value > 1.0f ? value : 1.0f;
    for (index = 0; index < 16; ++index) {
        guess = 0.5f * (guess + value / guess);
    }
    return guess;
}

int emg_compute_features(
    const float *window,
    size_t sample_count,
    size_t channel_count,
    float *features,
    float zc_threshold,
    float ssc_threshold
) {
    size_t channel;
    if (window == 0 || features == 0 || sample_count == 0u || channel_count == 0u) {
        return -1;
    }

    for (channel = 0u; channel < channel_count; ++channel) {
        float sum = 0.0f;
        float sum_abs = 0.0f;
        float sum_sq = 0.0f;
        float wl = 0.0f;
        float zc = 0.0f;
        float ssc = 0.0f;
        size_t sample;
        size_t base = channel * 7u;

        for (sample = 0u; sample < sample_count; ++sample) {
            float value = window[sample * channel_count + channel];
            sum += value;
            sum_abs += emg_absf(value);
            sum_sq += value * value;
            if (sample > 0u) {
                float previous = window[(sample - 1u) * channel_count + channel];
                wl += emg_absf(value - previous);
                if (((previous > 0.0f && value < 0.0f) || (previous < 0.0f && value > 0.0f)) &&
                    emg_absf(value - previous) > zc_threshold) {
                    zc += 1.0f;
                }
            }
        }

        for (sample = 1u; sample + 1u < sample_count; ++sample) {
            float left = window[sample * channel_count + channel] - window[(sample - 1u) * channel_count + channel];
            float right = window[(sample + 1u) * channel_count + channel] - window[sample * channel_count + channel];
            float largest = emg_absf(left) > emg_absf(right) ? emg_absf(left) : emg_absf(right);
            if (((left > 0.0f && right < 0.0f) || (left < 0.0f && right > 0.0f)) && largest > ssc_threshold) {
                ssc += 1.0f;
            }
        }

        {
            float mean = sum / (float)sample_count;
            float variance = (sum_sq / (float)sample_count) - (mean * mean);
            if (variance < 0.0f) {
                variance = 0.0f;
            }
            features[base + 0u] = sum_abs / (float)sample_count;
            features[base + 1u] = emg_sqrtf(sum_sq / (float)sample_count);
            features[base + 2u] = wl;
            features[base + 3u] = variance;
            features[base + 4u] = zc;
            features[base + 5u] = ssc;
            features[base + 6u] = sum_abs;
        }
    }
    return 0;
}

int emg_compute_stage2_selected_features(
    const float *window,
    size_t sample_count,
    size_t channel_count,
    float *features,
    float zc_threshold,
    float ssc_threshold
) {
    size_t channel;
    if (window == 0 || features == 0 || sample_count == 0u || channel_count == 0u) {
        return -1;
    }

    for (channel = 0u; channel < channel_count; ++channel) {
        float sum = 0.0f;
        float sum_abs = 0.0f;
        float sum_sq = 0.0f;
        float wl = 0.0f;
        float zc = 0.0f;
        float ssc = 0.0f;
        size_t sample;

        for (sample = 0u; sample < sample_count; ++sample) {
            float value = window[sample * channel_count + channel];
            sum += value;
            sum_abs += emg_absf(value);
            sum_sq += value * value;
            if (sample > 0u) {
                float previous = window[(sample - 1u) * channel_count + channel];
                float delta = value - previous;
                wl += emg_absf(delta);
                if (((previous > 0.0f && value < 0.0f) || (previous < 0.0f && value > 0.0f)) &&
                    emg_absf(delta) >= zc_threshold) {
                    zc += 1.0f;
                }
            }
        }

        for (sample = 1u; sample + 1u < sample_count; ++sample) {
            float d1 = window[sample * channel_count + channel] - window[(sample - 1u) * channel_count + channel];
            float d2 = window[sample * channel_count + channel] - window[(sample + 1u) * channel_count + channel];
            if ((d1 * d2) > 0.0f && (emg_absf(d1) >= ssc_threshold || emg_absf(d2) >= ssc_threshold)) {
                ssc += 1.0f;
            }
        }

        {
            float mean = sum / (float)sample_count;
            float variance = (sum_sq / (float)sample_count) - (mean * mean);
            if (variance < 0.0f) {
                variance = 0.0f;
            }
            features[channel] = sum_abs / (float)sample_count;
            features[channel_count + channel] = emg_sqrtf(sum_sq / (float)sample_count);
            features[(2u * channel_count) + channel] = wl;
            features[(3u * channel_count) + channel] = variance;
            features[(4u * channel_count) + channel] = zc;
            features[(5u * channel_count) + channel] = ssc;
        }
    }
    return 0;
}
