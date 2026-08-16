#ifndef STAGE6_UART_PROTOCOL_H
#define STAGE6_UART_PROTOCOL_H

#include <stdint.h>

#define STAGE6_UART_FRAME_SIZE 6u
#define STAGE6_UART_HEAD0 0xAAu
#define STAGE6_UART_HEAD1 0x55u
#define STAGE6_UART_MODE_NO_STABLE 0xFEu
#define STAGE6_UART_STATUS_VALID 0x01u
#define STAGE6_UART_STATUS_NO_STABLE 0x00u

uint8_t uart_protocol_checksum(const uint8_t frame[STAGE6_UART_FRAME_SIZE]);
int uart_protocol_is_valid_mode(uint8_t mode);
void uart_protocol_build_valid(uint8_t mode, uint8_t sequence, uint8_t frame[STAGE6_UART_FRAME_SIZE]);
void uart_protocol_build_no_stable(uint8_t sequence, uint8_t frame[STAGE6_UART_FRAME_SIZE]);

#endif
