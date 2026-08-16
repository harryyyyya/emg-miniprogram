#include "stage6_uart_only_test.h"

#include <Arduino.h>

#include "stage6_uart_link.h"

static uint32_t g_last_send_ms = 0u;
static uint8_t g_step = 0u;

void stage6_uart_only_test_setup(void) {
    stage6_uart_link_begin();
    Serial.println("LINK_TEST mode=UART_ONLY_TEST pattern=0,2,8,no_stable interval_ms=500");
}

void stage6_uart_only_test_loop(void) {
    if ((millis() - g_last_send_ms) < 500u) {
        return;
    }
    g_last_send_ms = millis();
    if (g_step == 0u) {
        stage6_uart_link_send_valid(0u, "uart_only_pattern");
    } else if (g_step == 1u) {
        stage6_uart_link_send_valid(2u, "uart_only_pattern");
    } else if (g_step == 2u) {
        stage6_uart_link_send_valid(8u, "uart_only_pattern");
    } else {
        stage6_uart_link_send_no_stable("uart_only_pattern");
    }
    g_step = (uint8_t)((g_step + 1u) & 0x03u);
}
