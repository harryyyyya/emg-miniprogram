#include "emg_features.h"

#include <math.h>
#include <stddef.h>

static float absolute(float value) {
    return value < 0.0f ? -value : value;
}

int duo_emg_features(
    const uint8_t window[125][8],
    float features[48],
    float zc_threshold,
    float ssc_threshold
) {
    size_t channel;
    if (window == NULL || features == NULL) {
        return -1;
    }
    for (channel = 0; channel < 8; ++channel) {
        float sum = 0.0f;
        float sum_abs = 0.0f;
        float sum_sq = 0.0f;
        float wl = 0.0f;
        float zc = 0.0f;
        float ssc = 0.0f;
        size_t sample;
        for (sample = 0; sample < 125; ++sample) {
            float value = (float)window[sample][channel] - 127.0f;
            sum += value;
            sum_abs += absolute(value);
            sum_sq += value * value;
            if (sample > 0) {
                float previous = (float)window[sample - 1][channel] - 127.0f;
                float delta = value - previous;
                wl += absolute(delta);
                if (previous * value < 0.0f && absolute(delta) >= zc_threshold) {
                    zc += 1.0f;
                }
            }
        }
        for (sample = 1; sample + 1 < 125; ++sample) {
            float previous = (float)window[sample - 1][channel] - 127.0f;
            float current = (float)window[sample][channel] - 127.0f;
            float following = (float)window[sample + 1][channel] - 127.0f;
            float d1 = current - previous;
            float d2 = current - following;
            float largest = absolute(d1) > absolute(d2) ? absolute(d1) : absolute(d2);
            if (d1 * d2 > 0.0f && largest >= ssc_threshold) {
                ssc += 1.0f;
            }
        }
        {
            float mean = sum / 125.0f;
            float variance = sum_sq / 125.0f - mean * mean;
            features[channel] = sum_abs / 125.0f;
            features[8 + channel] = sqrtf(sum_sq / 125.0f);
            features[16 + channel] = wl;
            features[24 + channel] = variance < 0.0f ? 0.0f : variance;
            features[32 + channel] = zc;
            features[40 + channel] = ssc;
        }
    }
    return 0;
}
