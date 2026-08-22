# ESP32-S3 LSH MLP Live BLE Candidate

This is an independent, compile-only candidate derived from
`artifacts/lsh_multisession_esp32_lda_v4_trim30_70`. It replaces only the
LDA inference path with the LSH second-batch MLP. BLE transport, 98-byte
parser, channel order, queue, MTU, 20-sample inference cadence, disconnect
safety, UART, network, and inherited controller behavior are preserved.

Frozen identity:

- model version: `lsh_mlp_e68ac986c09f`
- model SHA256: `e68ac986c09f921532434363d54fb5b94854dcff601f099df93caf3dca825a72`
- pipeline SHA256: `d9183f43ef5a67e761e5ac298fa34a3016f5a051c7137ac32fa8cfb702c6cffd`
- input: 125 samples x 8 channels, fixed baseline 127
- features: 48 in MAV/RMS/WL/VAR/ZC/SSC feature-major order
- classes: 0 through 8
- inference step: 20 samples (40 ms at 500 Hz)
- model: `48 -> 64 -> 32 -> 9`, ReLU after the first two layers
- preprocessing: fixed subtract 127, standardize with generated mean/std
- digital filter: none, matching the training contract

`generated/mlp_model.h` contains the exported float32 weights and
preprocessing parameters. `src/mlp_inference.c/.h` implements the MLP forward
pass and argmax/margin. The existing `emg_features.c`, BLE, UART, network and
controller behavior is preserved; only model identity, model include/call
wiring, and the MLP-specific controller margin setting are changed.

The training contract has `filter_mode: none`. The ESP32 path therefore does
not add a digital filter: it subtracts the fixed baseline 127, computes the
same six feature families, standardizes with the exported train-plus-validation
statistics, and runs the MLP. Adding a filter only on the ESP32 would create a
train/inference mismatch. A filtered variant must first retrain with the exact
same filter and then replace the generated model and contract together.
The 3.0 LDA margin threshold is not reused: MLP logits use
`STAGE4_MARGIN_THRESHOLD=0.0`; the inherited 300 ms/70% voting and low
confidence hold remain active.

At startup, `LIVE_BOOT` prints `MODEL_VERSION`, `PIPELINE_HASH`,
`WINDOW_SIZE`, `STEP_SIZE`, `FEATURE_COUNT`, and `CLASS_COUNT`.

## Real EMG upload and administrator download

The default mode is `FULL_CHAIN_WITH_EMG_UPLOAD`. Each decoded BLE frame is copied into a 3000-sample queue. The network worker sends up to 250 samples per request to `POST /devices/wifi/emg` and keeps samples queued when a request fails. After `stop_collect`, the queue is drained and an empty `is_final=true` request marks the session complete.

The backend stores the raw bytes under `uploads/esp32_emg/<session_id>.dat`, exposes the record from `GET /training/sessions`, and lets an administrator download the exact binary file from `GET /admin/training/sessions/{session_id}/download`. The web admin page calls that download endpoint and saves a `.dat` file.

Before flashing, make sure `WIFI_SSID`, `WIFI_PASSWORD`, `HARDWARE_ID`, and `BOARD_TOKEN` match the bound Wi-Fi device. Successful serial logs should include `registerBoard status=200` and `emgUpload path=/devices/wifi/emg status=200 ok=1`.
Status: `LSH_MLP_FIRMWARE_READY_NOT_HARDWARE_VERIFIED`.

This candidate has not been uploaded, burned, or tested on hardware. Historical
hardware logs from earlier firmware are not evidence for this candidate.

The sibling `verification/` directory contains a host-side C forward smoke
test. It checks the raw 125x8 window through features, standardization, and all
three MLP layers; it is not a substitute for ESP32 BLE/UART hardware testing.
