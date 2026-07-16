# ESP32 Jingjian merged sketch

Use this single sketch:

`D:\weixin\esp32\arduino_wifi_bridge\esp32_jingjian\esp32_jingjian.ino`

It has merged the old Wi-Fi transport code from `connect.ino` and the BLE armband collector code from `esp32_jingjian.ino`.

## What it does

- Connects ESP32 to Wi-Fi
- Registers to the FastAPI backend
- Sends heartbeat every 1 second
- Scans and connects to `BT-11(BLE)`
- Receives 98-byte BLE EMG packets from characteristic `FFE2`
- Parses each packet as 6 samples x 8 channels x int16
- Sends realtime EMG preview in heartbeat
- Uploads EMG batches to `/devices/wifi/emg` during action recording
- Lets the mini-program render realtime waveform on the control page

## Required edits before upload

Edit these values at the top of `esp32_jingjian.ino`:

```cpp
static const char* WIFI_SSID = "weixin";
static const char* WIFI_PASSWORD = "88888888a";
static const char* BACKEND_HOST = "47.239.150.223";
static const uint16_t BACKEND_PORT = 80;

static const char* HARDWARE_ID = "ESP32-HAND-001";
static const char* BOARD_TOKEN = "esp32-secret";
```

`BACKEND_HOST` must be your cloud backend host. During current testing it should be `47.239.150.223`, the same backend address used by the mini-program.

## Mini-program binding values

Use the same values:

```text
hardware_id: ESP32-HAND-001
board_token: esp32-secret
transport: wifi
```

## Expected serial logs

```text
WiFi connected, IP=...
registerBoard status=200
>>> Found BT-11(BLE)
>>> Connected & Receiving Data...
heartbeat status=200
uploadEmgBatch status=200
```

## Packet format assumption

The current parser assumes each BLE Notify packet is:

```text
AA AA + 96 bytes data
```

The 96 data bytes are parsed as:

```text
6 samples * 8 channels * int16 little-endian
```

If your armband packet layout is different, only update `parseNotifySamples()`.
