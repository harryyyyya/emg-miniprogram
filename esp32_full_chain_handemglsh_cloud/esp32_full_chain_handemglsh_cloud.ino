#include <Arduino.h>
#include "src/full_chain_modes.h"
#include "src/stage6_ble_mode_config.h"
#include "src/ble_transport_probe.h"
#include "src/live_ble_inference.h"
#include "src/stage5_replay_runner.h"
#include "src/stage6_uart_only_test.h"
#include "src/network_worker.h"
#include "src/runtime_snapshot.h"

void setup() {
    Serial.begin(921600);
    uint32_t start_ms = millis();
    while (!Serial && millis() - start_ms < 3000u) { delay(10); }
#if FULL_CHAIN_MODE == UART_ONLY_TEST
    runtime_snapshot_init();
    stage6_uart_only_test_setup();
#elif FULL_CHAIN_MODE == WIFI_ONLY_TEST
    runtime_snapshot_init();
    network_worker_begin(false);
#elif FULL_CHAIN_MODE == BLE_INFER_UART_TEST
    stage6_live_ble_setup();
#elif FULL_CHAIN_MODE == FULL_CHAIN_SAFE_DEMO
    stage6_live_ble_setup();
    network_worker_begin(false);
#elif FULL_CHAIN_MODE == FULL_CHAIN_WITH_EMG_UPLOAD
    stage6_live_ble_setup();
    network_worker_begin(true);
#elif STAGE6_BLE_MODE == BLE_TRANSPORT_PROBE
    stage6_ble_probe_setup();
#elif STAGE6_BLE_MODE == LIVE_BLE_INFERENCE
    stage6_live_ble_setup();
#else
    stage5_replay_setup();
#endif
}

void loop() {
#if FULL_CHAIN_MODE == UART_ONLY_TEST
    stage6_uart_only_test_loop();
#elif FULL_CHAIN_MODE == WIFI_ONLY_TEST
    delay(100);
#elif FULL_CHAIN_MODE == BLE_INFER_UART_TEST || FULL_CHAIN_MODE == FULL_CHAIN_SAFE_DEMO || FULL_CHAIN_MODE == FULL_CHAIN_WITH_EMG_UPLOAD
    stage6_live_ble_loop();
#elif STAGE6_BLE_MODE == BLE_TRANSPORT_PROBE
    stage6_ble_probe_loop();
#elif STAGE6_BLE_MODE == LIVE_BLE_INFERENCE
    stage6_live_ble_loop();
#else
    stage5_replay_loop();
#endif
    delay(1);
}
