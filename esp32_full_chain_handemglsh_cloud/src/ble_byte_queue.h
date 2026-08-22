#ifndef STAGE6_BLE_BYTE_QUEUE_H
#define STAGE6_BLE_BYTE_QUEUE_H

#include <stddef.h>
#include <stdint.h>

typedef struct Stage6BleByteQueue {
    uint8_t *storage;
    size_t capacity;
    volatile size_t head;
    volatile size_t tail;
    volatile size_t count;
    volatile uint32_t overflow_count;
    volatile uint32_t dropped_byte_count;
} Stage6BleByteQueue;

void stage6_ble_byte_queue_init(Stage6BleByteQueue *queue, uint8_t *storage, size_t capacity);
void stage6_ble_byte_queue_reset(Stage6BleByteQueue *queue);
size_t stage6_ble_byte_queue_size(const Stage6BleByteQueue *queue);
uint32_t stage6_ble_byte_queue_overflows(const Stage6BleByteQueue *queue);
uint32_t stage6_ble_byte_queue_dropped_bytes(const Stage6BleByteQueue *queue);
size_t stage6_ble_byte_queue_push_isr(Stage6BleByteQueue *queue, const uint8_t *data, size_t length);
int stage6_ble_byte_queue_pop(Stage6BleByteQueue *queue, uint8_t *byte_out);

#endif
