#include "ble_byte_queue.h"

void stage6_ble_byte_queue_init(Stage6BleByteQueue *queue, uint8_t *storage, size_t capacity) {
    if (queue == 0) {
        return;
    }
    queue->storage = storage;
    queue->capacity = capacity;
    stage6_ble_byte_queue_reset(queue);
}

void stage6_ble_byte_queue_reset(Stage6BleByteQueue *queue) {
    if (queue == 0) {
        return;
    }
    queue->head = 0u;
    queue->tail = 0u;
    queue->count = 0u;
    queue->overflow_count = 0u;
    queue->dropped_byte_count = 0u;
}

size_t stage6_ble_byte_queue_size(const Stage6BleByteQueue *queue) {
    return queue == 0 ? 0u : queue->count;
}

uint32_t stage6_ble_byte_queue_overflows(const Stage6BleByteQueue *queue) {
    return queue == 0 ? 0u : queue->overflow_count;
}

uint32_t stage6_ble_byte_queue_dropped_bytes(const Stage6BleByteQueue *queue) {
    return queue == 0 ? 0u : queue->dropped_byte_count;
}

size_t stage6_ble_byte_queue_push_isr(Stage6BleByteQueue *queue, const uint8_t *data, size_t length) {
    size_t pushed = 0u;
    if (queue == 0 || queue->storage == 0 || data == 0 || queue->capacity == 0u) {
        return 0u;
    }
    for (size_t index = 0u; index < length; ++index) {
        if (queue->count >= queue->capacity) {
            queue->overflow_count += 1u;
            queue->dropped_byte_count += (uint32_t)(length - index);
            break;
        }
        queue->storage[queue->head] = data[index];
        queue->head = (queue->head + 1u) % queue->capacity;
        queue->count += 1u;
        pushed += 1u;
    }
    return pushed;
}

int stage6_ble_byte_queue_pop(Stage6BleByteQueue *queue, uint8_t *byte_out) {
    if (queue == 0 || byte_out == 0 || queue->storage == 0 || queue->count == 0u) {
        return 0;
    }
    *byte_out = queue->storage[queue->tail];
    queue->tail = (queue->tail + 1u) % queue->capacity;
    queue->count -= 1u;
    return 1;
}
