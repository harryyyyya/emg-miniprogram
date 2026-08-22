#include "stage6_uart_link.h"

#include <Arduino.h>

#include "full_chain_config.h"
#include "runtime_snapshot.h"
#include "uart_protocol.h"

static uint8_t g_uart_sequence = 0u;

static void stage6_uart_print_frame(const uint8_t frame[STAGE6_UART_FRAME_SIZE]) {
    for (uint32_t i = 0; i < STAGE6_UART_FRAME_SIZE; ++i) {
        if (frame[i] < 0x10u) {
            Serial.print("0");
        }
        Serial.print(frame[i], HEX);
    }
}

void stage6_uart_link_begin(void) {
    Serial1.begin(STAGE6_STM32_UART_BAUD, SERIAL_8N1, STAGE6_STM32_UART_RX_PIN, STAGE6_STM32_UART_TX_PIN);
    runtime_snapshot_set_uart_initialized(true);
    Serial.print("STM32_UART begin baud=");
    Serial.print(STAGE6_STM32_UART_BAUD);
    Serial.print(" tx_pin=");
    Serial.print(STAGE6_STM32_UART_TX_PIN);
    Serial.print(" rx_pin=");
    Serial.println(STAGE6_STM32_UART_RX_PIN);
}

void stage6_uart_link_send_valid(uint8_t mode, const char *reason) {
    uint8_t frame[STAGE6_UART_FRAME_SIZE];
    if (!uart_protocol_is_valid_mode(mode)) {
        Serial.print("UART_TX blocked_invalid_mode mode=");
        Serial.print(mode);
        Serial.print(" reason=");
        Serial.println(reason == 0 ? "unknown" : reason);
        stage6_uart_link_send_no_stable("invalid_mode_blocked");
        return;
    }
    uart_protocol_build_valid(mode, g_uart_sequence, frame);
    Serial1.write(frame, STAGE6_UART_FRAME_SIZE);
    Serial.print("UART_TX seq=");
    Serial.print(g_uart_sequence);
    Serial.print(" mode=");
    Serial.print(mode);
    Serial.print(" status=valid bytes=");
    stage6_uart_print_frame(frame);
    Serial.print(" reason=");
    Serial.println(reason == 0 ? "unknown" : reason);
    g_uart_sequence = (uint8_t)(g_uart_sequence + 1u);
}

void stage6_uart_link_send_no_stable(const char *reason) {
    uint8_t frame[STAGE6_UART_FRAME_SIZE];
    uart_protocol_build_no_stable(g_uart_sequence, frame);
    Serial1.write(frame, STAGE6_UART_FRAME_SIZE);
    Serial.print("UART_TX seq=");
    Serial.print(g_uart_sequence);
    Serial.print(" mode=no_stable status=not_valid bytes=");
    stage6_uart_print_frame(frame);
    Serial.print(" reason=");
    Serial.println(reason == 0 ? "unknown" : reason);
    g_uart_sequence = (uint8_t)(g_uart_sequence + 1u);
}

void stage6_uart_link_force_no_stable(const char *reason) {
    stage6_uart_link_send_no_stable(reason == 0 ? "forced_no_stable" : reason);
}

uint8_t stage6_uart_link_next_sequence_preview(void) {
    return g_uart_sequence;
}
