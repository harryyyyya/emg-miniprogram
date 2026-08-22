#include "frame_stream_parser.h"

#include <string.h>

static int stage5_find_header(const uint8_t *buffer, size_t count) {
    for (size_t index = 0u; index + 1u < count; ++index) {
        if (buffer[index] == STAGE5_HEADER_A && buffer[index + 1u] == STAGE5_HEADER_B) {
            return (int)index;
        }
    }
    return -1;
}

static uint32_t stage5_read_be_u32(const uint8_t *bytes) {
    return ((uint32_t)bytes[0] << 24)
        | ((uint32_t)bytes[1] << 16)
        | ((uint32_t)bytes[2] << 8)
        | (uint32_t)bytes[3];
}

static void stage5_decode_frame(const uint8_t *buffer, Stage5Frame *frame_out) {
    frame_out->timestamp_ms = stage5_read_be_u32(buffer + 3u);
    for (size_t row = 0u; row < STAGE5_SAMPLES_PER_FRAME; ++row) {
        for (size_t channel = 0u; channel < STAGE5_CHANNELS; ++channel) {
            frame_out->emg[row][channel] = buffer[16u + row * STAGE5_CHANNELS + channel];
        }
    }
    frame_out->battery_percent = buffer[96u];
}

void stage5_frame_stream_parser_init(Stage5FrameStreamParser *parser) {
    if (parser == 0) {
        return;
    }
    parser->buffered_bytes = 0u;
    parser->parse_error_count = 0u;
    parser->discarded_byte_count = 0u;
}

void stage5_frame_stream_parser_reset(Stage5FrameStreamParser *parser) {
    if (parser == 0) {
        return;
    }
    parser->buffered_bytes = 0u;
}

size_t stage5_frame_stream_parser_pending_bytes(const Stage5FrameStreamParser *parser) {
    return parser == 0 ? 0u : parser->buffered_bytes;
}

int stage5_frame_stream_parser_feed_byte(Stage5FrameStreamParser *parser, uint8_t byte, Stage5Frame *frame_out) {
    if (parser == 0 || frame_out == 0) {
        return -1;
    }

    if (parser->buffered_bytes < sizeof(parser->buffer)) {
        parser->buffer[parser->buffered_bytes] = byte;
        parser->buffered_bytes += 1u;
    } else {
        parser->parse_error_count += 1u;
        parser->discarded_byte_count += 1u;
        memmove(parser->buffer, parser->buffer + 1u, sizeof(parser->buffer) - 1u);
        parser->buffer[sizeof(parser->buffer) - 1u] = byte;
    }

    for (;;) {
        int header_index = stage5_find_header(parser->buffer, parser->buffered_bytes);
        if (header_index < 0) {
            if (parser->buffered_bytes > 0u && parser->buffer[parser->buffered_bytes - 1u] == STAGE5_HEADER_A) {
                parser->discarded_byte_count += (uint32_t)(parser->buffered_bytes - 1u);
                parser->buffer[0] = STAGE5_HEADER_A;
                parser->buffered_bytes = 1u;
            } else {
                parser->discarded_byte_count += (uint32_t)parser->buffered_bytes;
                parser->buffered_bytes = 0u;
            }
            return 0;
        }

        if (header_index > 0) {
            size_t remaining = parser->buffered_bytes - (size_t)header_index;
            parser->discarded_byte_count += (uint32_t)header_index;
            memmove(parser->buffer, parser->buffer + header_index, remaining);
            parser->buffered_bytes = remaining;
        }

        if (parser->buffered_bytes < sizeof(parser->buffer)) {
            return 0;
        }

        if (parser->buffer[2u] != STAGE5_FRAME_TYPE || parser->buffer[STAGE5_FRAME_SIZE - 1u] != STAGE5_TAIL) {
            parser->parse_error_count += 1u;
            parser->discarded_byte_count += 1u;
            memmove(parser->buffer, parser->buffer + 1u, parser->buffered_bytes - 1u);
            parser->buffered_bytes -= 1u;
            continue;
        }

        stage5_decode_frame(parser->buffer, frame_out);
        parser->buffered_bytes = 0u;
        return 1;
    }
}
