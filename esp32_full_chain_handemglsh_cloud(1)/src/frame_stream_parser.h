#ifndef STAGE5_FRAME_STREAM_PARSER_H
#define STAGE5_FRAME_STREAM_PARSER_H

#include <stddef.h>
#include <stdint.h>

#define STAGE5_FRAME_SIZE 98u
#define STAGE5_HEADER_A 0xAAu
#define STAGE5_HEADER_B 0xAAu
#define STAGE5_FRAME_TYPE 0x5Fu
#define STAGE5_TAIL 0x55u
#define STAGE5_SAMPLES_PER_FRAME 10u
#define STAGE5_CHANNELS 8u

typedef struct Stage5Frame {
    uint32_t timestamp_ms;
    uint8_t battery_percent;
    uint8_t emg[STAGE5_SAMPLES_PER_FRAME][STAGE5_CHANNELS];
} Stage5Frame;

typedef struct Stage5FrameStreamParser {
    uint8_t buffer[STAGE5_FRAME_SIZE];
    size_t buffered_bytes;
    uint32_t parse_error_count;
    uint32_t discarded_byte_count;
} Stage5FrameStreamParser;

void stage5_frame_stream_parser_init(Stage5FrameStreamParser *parser);
void stage5_frame_stream_parser_reset(Stage5FrameStreamParser *parser);
size_t stage5_frame_stream_parser_pending_bytes(const Stage5FrameStreamParser *parser);
int stage5_frame_stream_parser_feed_byte(Stage5FrameStreamParser *parser, uint8_t byte, Stage5Frame *frame_out);

#endif
