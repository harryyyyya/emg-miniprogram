#ifndef STAGE6_UART_LINK_H
#define STAGE6_UART_LINK_H

#include <stdint.h>

void stage6_uart_link_begin(void);
void stage6_uart_link_send_valid(uint8_t mode, const char *reason);
void stage6_uart_link_send_no_stable(const char *reason);
void stage6_uart_link_force_no_stable(const char *reason);
uint8_t stage6_uart_link_next_sequence_preview(void);

#endif
