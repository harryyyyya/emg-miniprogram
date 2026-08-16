# ESP32-S3 Stage 6.1C Live BLE Candidate

This is an independent, compile-only candidate derived from
`firmware/esp32_s3_live_ble_demo`. It integrates the frozen Stage 6.1C LDA
model without changing the BLE transport, 98-byte parser, channel order,
queue, MTU, 20-sample inference cadence, disconnect safety, or inherited
controller behavior.

Frozen identity:

- model version: `stage6_1c-aa84efaaea80`
- pipeline SHA256: `aa84efaaea80af2e0272d728435d91134bb81761512ed075e176026a16d51abc`
- input: 125 samples x 8 channels, fixed baseline 127
- features: 48 in MAV/RMS/WL/VAR/ZC/SSC feature-major order
- classes: 0 through 8
- inference step: 20 samples (40 ms at 500 Hz)

The generated headers and manifest under `generated/` are copied from
`generated/stage6_1c`. `src/stage6_1c_integration_config.h` provides only
compatibility aliases plus the unchanged existing controller safety values;
the Stage 6.1C training runner explicitly did not select controller values.
`generated/lda_inference.h` is an Arduino include-path forwarding shim; it
contains no model parameters and leaves both exported files byte-identical.

At startup, `LIVE_BOOT` prints `MODEL_VERSION`, `PIPELINE_HASH`,
`WINDOW_SIZE`, `STEP_SIZE`, `FEATURE_COUNT`, and `CLASS_COUNT`.

Status: `STAGE6_1C_FIRMWARE_READY_NOT_HARDWARE_VERIFIED`.

This candidate has not been uploaded, burned, or tested on hardware. Historical
hardware logs from earlier firmware are not evidence for this candidate.

## Real EMG collection upload

The default `FULL_CHAIN_MODE` is `FULL_CHAIN_WITH_EMG_UPLOAD`. After the user
binds `HARDWARE_ID` and `BOARD_TOKEN` to an account, the board receives
`start_collect` and `stop_collect` commands through the Wi-Fi heartbeat.

While collection is active, every decoded 10 x 8 BLE frame is copied into a
thread-safe queue. The network worker uploads continuous 250-sample batches to
`POST /devices/wifi/emg`; it removes a batch from the queue only after a 2xx
response. On stop, pending samples are drained before an empty final marker is
sent. The backend uses `session_id` plus `sequence_no` for retry idempotency,
and assigns the session to the user who owns the bound board.

The queue retains up to 3000 samples (about six seconds at 500 Hz). Queue
overflow is exposed through the `emg_upload_drop_count` heartbeat field. The
firmware has not been flashed by this repository change; use the board and FQBN
documented in `BUILD_SETTINGS.md` for a compile check and manual upload.
