#ifndef EMG_FEATURES_H
#define EMG_FEATURES_H

#include <stddef.h>

int emg_compute_features(
    const float *window,
    size_t sample_count,
    size_t channel_count,
    float *features,
    float zc_threshold,
    float ssc_threshold
);

int emg_compute_stage2_selected_features(
    const float *window,
    size_t sample_count,
    size_t channel_count,
    float *features,
    float zc_threshold,
    float ssc_threshold
);

#endif
