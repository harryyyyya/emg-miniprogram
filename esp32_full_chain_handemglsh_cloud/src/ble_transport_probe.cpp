#include "ble_transport_probe.h"

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <esp_arduino_version.h>
#include <string.h>

#include "ble_byte_queue.h"
#include "frame_stream_parser.h"

#define STAGE6_TARGET_NAME "BT-11(BLE)"
#define STAGE6_SERVICE_UUID "0000ffe0-0000-1000-8000-00805f9b34fb"
#define STAGE6_NOTIFY_UUID "0000ffe2-0000-1000-8000-00805f9b34fb"
#define STAGE6_REQUESTED_MTU 28u
#define STAGE6_QUEUE_CAPACITY 4096u
#define STAGE6_STATUS_INTERVAL_MS 1000u
#define STAGE6_SCAN_WINDOW_SECONDS 5u
#define STAGE6_NO_VALID_FRAME_TIMEOUT_MS 250u

#ifndef ARDUINO_BOARD
#define ARDUINO_BOARD "unknown"
#endif

typedef struct Stage6BleProbeStats {
    uint32_t notify_count;
    uint32_t notify_bytes;
    uint32_t notify_len_hist[201];
    uint32_t notify_len_other;
    uint32_t valid_frames;
    uint32_t invalid_frames_reported;
    uint32_t timestamp_gap_count;
    uint32_t estimated_missing_packets;
    uint32_t largest_gap_ms;
    uint32_t signal_timeout_count;
    uint32_t last_timestamp_ms;
    uint32_t last_valid_frame_host_ms;
    uint32_t last_status_ms;
    uint8_t has_timestamp;
    uint8_t connected;
    uint8_t signal_timeout_active;
} Stage6BleProbeStats;

static BLEUUID g_service_uuid(STAGE6_SERVICE_UUID);
static BLEUUID g_notify_uuid(STAGE6_NOTIFY_UUID);
static BLEAdvertisedDevice *g_target_device = 0;
static BLEClient *g_client = 0;
static BLERemoteCharacteristic *g_notify_characteristic = 0;
static uint8_t g_queue_storage[STAGE6_QUEUE_CAPACITY];
static Stage6BleByteQueue g_rx_queue;
static Stage5FrameStreamParser g_parser;
static Stage6BleProbeStats g_stats;
static portMUX_TYPE g_queue_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint8_t g_connect_requested = 0u;
static uint8_t g_scan_running = 0u;

static void stage6_ble_print_core_version(void) {
    Serial.print(ESP_ARDUINO_VERSION_MAJOR);
    Serial.print(".");
    Serial.print(ESP_ARDUINO_VERSION_MINOR);
    Serial.print(".");
    Serial.print(ESP_ARDUINO_VERSION_PATCH);
}

static void stage6_ble_print_len_hist(void) {
    uint8_t printed = 0u;
    for (uint32_t index = 0u; index < 201u; ++index) {
        if (g_stats.notify_len_hist[index] == 0u) {
            continue;
        }
        if (printed > 0u) {
            Serial.print(",");
        }
        Serial.print(index);
        Serial.print(":");
        Serial.print(g_stats.notify_len_hist[index]);
        printed = 1u;
    }
    if (g_stats.notify_len_other > 0u) {
        if (printed > 0u) {
            Serial.print(",");
        }
        Serial.print("other:");
        Serial.print(g_stats.notify_len_other);
    }
    if (printed == 0u) {
        Serial.print("none");
    }
}

static void stage6_ble_note_notification_length(size_t length) {
    if (length < 201u) {
        g_stats.notify_len_hist[length] += 1u;
    } else {
        g_stats.notify_len_other += 1u;
    }
}

static void stage6_ble_reset_signal_state(void) {
    stage5_frame_stream_parser_reset(&g_parser);
    g_stats.has_timestamp = 0u;
    g_stats.signal_timeout_active = 0u;
    g_stats.last_valid_frame_host_ms = 0u;
}

static void stage6_ble_print_stats(const char *tag) {
    Serial.print(tag);
    Serial.print(" uptime_ms="); Serial.print(millis());
    Serial.print(" notify_count="); Serial.print(g_stats.notify_count);
    Serial.print(" notify_bytes="); Serial.print(g_stats.notify_bytes);
    Serial.print(" len_hist="); stage6_ble_print_len_hist();
    Serial.print(" valid_frames="); Serial.print(g_stats.valid_frames);
    Serial.print(" invalid_frames="); Serial.print(g_parser.parse_error_count);
    Serial.print(" resync_count="); Serial.print(g_parser.parse_error_count);
    Serial.print(" discarded_bytes="); Serial.print(g_parser.discarded_byte_count);
    Serial.print(" timestamp_gap_count="); Serial.print(g_stats.timestamp_gap_count);
    Serial.print(" estimated_missing_packets="); Serial.print(g_stats.estimated_missing_packets);
    Serial.print(" largest_gap_ms="); Serial.print(g_stats.largest_gap_ms);
    Serial.print(" queue_overflow_count="); Serial.print(stage6_ble_byte_queue_overflows(&g_rx_queue));
    Serial.print(" queue_dropped_bytes="); Serial.print(stage6_ble_byte_queue_dropped_bytes(&g_rx_queue));
    Serial.print(" pending_bytes="); Serial.print(stage5_frame_stream_parser_pending_bytes(&g_parser));
    Serial.print(" queued_bytes="); Serial.print(stage6_ble_byte_queue_size(&g_rx_queue));
    Serial.print(" free_heap="); Serial.println(ESP.getFreeHeap());
}

static void stage6_ble_handle_timestamp(uint32_t timestamp_ms) {
    if (g_stats.has_timestamp != 0u) {
        uint32_t delta_ms = timestamp_ms - g_stats.last_timestamp_ms;
        if (delta_ms != 20u) {
            g_stats.timestamp_gap_count += 1u;
            if (delta_ms > g_stats.largest_gap_ms) {
                g_stats.largest_gap_ms = delta_ms;
            }
            if (delta_ms > 30u) {
                uint32_t estimated_steps = (delta_ms + 10u) / 20u;
                if (estimated_steps > 0u) {
                    g_stats.estimated_missing_packets += estimated_steps - 1u;
                }
            }
        }
    }
    g_stats.last_timestamp_ms = timestamp_ms;
    g_stats.has_timestamp = 1u;
}

static void stage6_ble_handle_frame(const Stage5Frame *frame) {
    g_stats.valid_frames += 1u;
    g_stats.last_valid_frame_host_ms = millis();
    g_stats.signal_timeout_active = 0u;
    stage6_ble_handle_timestamp(frame->timestamp_ms);
    Serial.print("FRAME_OK seq="); Serial.print(g_stats.valid_frames);
    Serial.print(" timestamp_ms="); Serial.print(frame->timestamp_ms);
    Serial.print(" battery="); Serial.println(frame->battery_percent);
}

static void stage6_ble_drain_queue(void) {
    uint8_t byte = 0u;
    for (;;) {
        int have_byte;
        portENTER_CRITICAL(&g_queue_mux);
        have_byte = stage6_ble_byte_queue_pop(&g_rx_queue, &byte);
        portEXIT_CRITICAL(&g_queue_mux);
        if (!have_byte) {
            break;
        }
        Stage5Frame frame;
        uint32_t before_errors = g_parser.parse_error_count;
        int ready = stage5_frame_stream_parser_feed_byte(&g_parser, byte, &frame);
        if (g_parser.parse_error_count != before_errors) {
            Serial.print("FRAME_INVALID reason=resync discarded_bytes=");
            Serial.println(g_parser.discarded_byte_count);
        }
        if (ready > 0) {
            stage6_ble_handle_frame(&frame);
        }
    }
}

static void stage6_ble_notify_callback(BLERemoteCharacteristic *, uint8_t *data, size_t length, bool) {
    portENTER_CRITICAL(&g_queue_mux);
    stage6_ble_byte_queue_push_isr(&g_rx_queue, data, length);
    portEXIT_CRITICAL(&g_queue_mux);
    g_stats.notify_count += 1u;
    g_stats.notify_bytes += (uint32_t)length;
    stage6_ble_note_notification_length(length);
}

class Stage6ClientCallbacks : public BLEClientCallbacks {
    void onConnect(BLEClient *) override {
        g_stats.connected = 1u;
    }

    void onDisconnect(BLEClient *) override {
        g_stats.connected = 0u;
        Serial.print("BLE_DISCONNECT reason=client_disconnect uptime_ms=");
        Serial.println(millis());
        stage6_ble_reset_signal_state();
    }
};

class Stage6ScanCallbacks : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertised_device) override {
        bool name_match = advertised_device.haveName() && advertised_device.getName() == STAGE6_TARGET_NAME;
        bool service_match = advertised_device.haveServiceUUID() && advertised_device.isAdvertisingService(g_service_uuid);
        if (!name_match && !service_match) {
            return;
        }

        Serial.print("BLE_SCAN name=");
        Serial.print(advertised_device.haveName() ? advertised_device.getName().c_str() : "<none>");
        Serial.print(" address=");
        Serial.print(advertised_device.getAddress().toString().c_str());
        Serial.print(" address_type=unknown");
        Serial.print(" rssi=");
        Serial.print(advertised_device.getRSSI());
        Serial.print(" services=");
        if (advertised_device.haveServiceUUID()) {
            Serial.println(advertised_device.getServiceUUID().toString().c_str());
        } else {
            Serial.println("<none>");
        }

        if (g_target_device != 0) {
            return;
        }
        g_target_device = new BLEAdvertisedDevice(advertised_device);
        g_connect_requested = 1u;
        BLEDevice::getScan()->stop();
        g_scan_running = 0u;
    }
};

static void stage6_ble_start_scan(void) {
    BLEScan *scan = BLEDevice::getScan();
    Serial.print("BLE_SCAN_START target_name=");
    Serial.print(STAGE6_TARGET_NAME);
    Serial.print(" service_uuid=");
    Serial.println(STAGE6_SERVICE_UUID);
    scan->setAdvertisedDeviceCallbacks(new Stage6ScanCallbacks(), false);
    scan->setActiveScan(true);
    scan->setInterval(1349);
    scan->setWindow(449);
    g_scan_running = 1u;
    scan->start(STAGE6_SCAN_WINDOW_SECONDS, false);
    g_scan_running = 0u;
}

static void stage6_ble_print_characteristic(BLERemoteCharacteristic *characteristic) {
    Serial.print("BLE_GATT service=");
    Serial.print(STAGE6_SERVICE_UUID);
    Serial.print(" characteristic=");
    Serial.print(STAGE6_NOTIFY_UUID);
    Serial.print(" properties=");
    Serial.print(characteristic->canRead() ? "read," : "");
    Serial.print(characteristic->canWrite() ? "write," : "");
    Serial.print(characteristic->canNotify() ? "notify," : "");
    Serial.print(characteristic->canIndicate() ? "indicate," : "");
    Serial.println("end");
}

static bool stage6_ble_connect(void) {
    if (g_target_device == 0) {
        return false;
    }

    if (g_client != 0) {
        delete g_client;
        g_client = 0;
    }

    g_client = BLEDevice::createClient();
    g_client->setClientCallbacks(new Stage6ClientCallbacks());
    g_client->setMTU(STAGE6_REQUESTED_MTU);
    Serial.print("BLE_CONNECT address=");
    Serial.print(g_target_device->getAddress().toString().c_str());
    Serial.print(" requested_mtu=");
    Serial.print(STAGE6_REQUESTED_MTU);

    if (!g_client->connect(g_target_device)) {
        Serial.println(" negotiated_mtu=unknown result=FAIL");
        return false;
    }

    Serial.print(" negotiated_mtu=");
    Serial.print(g_client->getMTU());
    Serial.println(" result=OK");

    BLERemoteService *service = g_client->getService(g_service_uuid);
    if (service == 0) {
        Serial.print("BLE_GATT service=");
        Serial.print(STAGE6_SERVICE_UUID);
        Serial.println(" result=MISSING");
        return false;
    }

    g_notify_characteristic = service->getCharacteristic(g_notify_uuid);
    if (g_notify_characteristic == 0) {
        Serial.print("BLE_GATT service=");
        Serial.print(STAGE6_SERVICE_UUID);
        Serial.print(" characteristic=");
        Serial.print(STAGE6_NOTIFY_UUID);
        Serial.println(" result=MISSING");
        return false;
    }

    stage6_ble_print_characteristic(g_notify_characteristic);
    if (g_notify_characteristic->canNotify()) {
        g_notify_characteristic->registerForNotify(stage6_ble_notify_callback, false);
        Serial.println("BLE_SUBSCRIBE result=registered mode=notify");
    } else if (g_notify_characteristic->canIndicate()) {
        g_notify_characteristic->registerForNotify(stage6_ble_notify_callback, true);
        Serial.println("BLE_SUBSCRIBE result=registered mode=indicate");
    } else {
        Serial.println("BLE_SUBSCRIBE result=FAIL reason=no_notify_or_indicate");
        return false;
    }
    return true;
}

void stage6_ble_probe_setup(void) {
    memset(&g_stats, 0, sizeof(g_stats));
    stage6_ble_byte_queue_init(&g_rx_queue, g_queue_storage, sizeof(g_queue_storage));
    stage5_frame_stream_parser_init(&g_parser);

    Serial.print("BOOT board=");
    Serial.print(ARDUINO_BOARD);
    Serial.print(" core=");
    stage6_ble_print_core_version();
    Serial.print(" mode=BLE_TRANSPORT_PROBE baud=921600 requested_mtu=");
    Serial.print(STAGE6_REQUESTED_MTU);
    Serial.print(" frame_size=");
    Serial.println(STAGE5_FRAME_SIZE);

    BLEDevice::init("ESP32_S3_STAGE6_BLE_PROBE");
    stage6_ble_start_scan();
    g_stats.last_status_ms = millis();
}

void stage6_ble_probe_loop(void) {
    if (g_connect_requested != 0u) {
        g_connect_requested = 0u;
        stage6_ble_connect();
        delete g_target_device;
        g_target_device = 0;
    }

    if (g_client != 0 && !g_client->isConnected()) {
        if (g_stats.connected != 0u) {
            Serial.print("BLE_DISCONNECT reason=poll_disconnect uptime_ms=");
            Serial.println(millis());
        }
        g_stats.connected = 0u;
        stage6_ble_reset_signal_state();
        delete g_client;
        g_client = 0;
        g_notify_characteristic = 0;
        delay(500);
        stage6_ble_start_scan();
    } else if (g_client == 0 && g_scan_running == 0u && g_target_device == 0) {
        stage6_ble_start_scan();
    }

    stage6_ble_drain_queue();

    if (g_stats.connected != 0u && g_stats.last_valid_frame_host_ms != 0u) {
        uint32_t silence_ms = millis() - g_stats.last_valid_frame_host_ms;
        if (silence_ms >= STAGE6_NO_VALID_FRAME_TIMEOUT_MS && g_stats.signal_timeout_active == 0u) {
            g_stats.signal_timeout_active = 1u;
            g_stats.signal_timeout_count += 1u;
            Serial.print("SIGNAL_TIMEOUT no_valid_frame_ms=");
            Serial.print(silence_ms);
            Serial.println(" gesture=0");
        }
    }

    if ((millis() - g_stats.last_status_ms) >= STAGE6_STATUS_INTERVAL_MS) {
        g_stats.last_status_ms = millis();
        stage6_ble_print_stats("BLE_STATS");
    }
}
