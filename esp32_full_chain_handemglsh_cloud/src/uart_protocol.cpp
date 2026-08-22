#include "uart_protocol.h"

uint8_t uart_protocol_checksum(const uint8_t frame[STAGE6_UART_FRAME_SIZE]) {
    return (uint8_t)(frame[0] ^ frame[1] ^ frame[2] ^ frame[3] ^ frame[4]);
}

int uart_protocol_is_valid_mode(uint8_t mode) {
    return mode <= 8u;
}

void uart_protocol_build_no_stable(uint8_t sequence, uint8_t frame[STAGE6_UART_FRAME_SIZE]) {
    frame[0] = STAGE6_UART_HEAD0;
    frame[1] = STAGE6_UART_HEAD1;
    frame[2] = STAGE6_UART_MODE_NO_STABLE;
    frame[3] = sequence;
    frame[4] = STAGE6_UART_STATUS_NO_STABLE;
    frame[5] = uart_protocol_checksum(frame);
}

void uart_protocol_build_valid(uint8_t mode, uint8_t sequence, uint8_t frame[STAGE6_UART_FRAME_SIZE]) {
    if (!uart_protocol_is_valid_mode(mode)) {
        uart_protocol_build_no_stable(sequence, frame);
        return;
    }
    frame[0] = STAGE6_UART_HEAD0;
    frame[1] = STAGE6_UART_HEAD1;
    frame[2] = mode;
    frame[3] = sequence;
    frame[4] = STAGE6_UART_STATUS_VALID;
    frame[5] = uart_protocol_checksum(frame);
}
