#ifndef DUO_S_FULL_CHAIN_EMG_FEATURES_H
#define DUO_S_FULL_CHAIN_EMG_FEATURES_H

#include <stdint.h>

#if defined(_WIN32)
#define DUO_EXPORT __declspec(dllexport)
#else
#define DUO_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

DUO_EXPORT int duo_emg_features(
    const uint8_t window[125][8],
    float features[48],
    float zc_threshold,
    float ssc_threshold
);

#ifdef __cplusplus
}
#endif

#endif
