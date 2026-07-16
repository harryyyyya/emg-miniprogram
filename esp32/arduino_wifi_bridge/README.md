# ESP32 Wi-Fi Demo

This demo matches your current backend routes:

- `POST /devices/bind`
- `POST /devices/wifi/register`
- `POST /devices/wifi/heartbeat`
- `POST /devices/{hardware_id}/command`
- `POST /devices/wifi/command/ack`
- `POST /devices/wifi/emg`
- `GET /devices/{hardware_id}/status`

Arduino sketch:

- [arduino_wifi_bridge.ino](d:/weixin/esp32/arduino_wifi_bridge/arduino_wifi_bridge.ino)

## What this demo does

1. Connects ESP32 to your Wi-Fi
2. Registers the board to your FastAPI backend
3. Sends heartbeat every 3 seconds
4. Receives `start_collect` and `stop_collect` commands from backend
5. Uploads simulated 8-channel EMG data to backend
6. Reports battery, signal, module status, and prediction result

## Before you upload

Open `arduino_wifi_bridge.ino` and change these values:

```cpp
static const char* WIFI_SSID = "YOUR_WIFI_NAME";
static const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
static const char* BACKEND_HOST = "47.239.150.223";
static const uint16_t BACKEND_PORT = 80;
static const char* HARDWARE_ID = "ESP32-HAND-001";
static const char* BOARD_TOKEN = "esp32-secret";
```

Notes:

- `BACKEND_HOST` must be your backend host. For current cloud testing, use `47.239.150.223`.
- `HARDWARE_ID` and `BOARD_TOKEN` must match what you bind in the mini-program

## Arduino IDE setup

1. Install Arduino IDE
2. Install ESP32 board package
3. Install library `ArduinoJson`
4. Select your board, for example `ESP32 Dev Module` or your exact ESP32-S3 board
5. Select the correct COM port
6. Open the `.ino` file and upload

## Start backend first

Run backend on your computer:

```bat
cd /d d:\weixin\backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then test on your computer browser:

```text
http://127.0.0.1:8000/ping
```

If backend is fine, your phone and ESP32 must be on the same Wi-Fi as this computer.

## Mini-program binding

In your mini-program bind page, choose the `ESP32 走后端` mode and fill:

- `hardware_id`: `ESP32-HAND-001`
- `board_token`: `esp32-secret`
- `device_name`: any display name you want

Then tap bind.

## Expected data flow

### ESP32 register

ESP32 sends:

```json
{
  "hardware_id": "ESP32-HAND-001",
  "board_token": "esp32-secret",
  "firmware_version": "1.0.0",
  "wifi_host": "192.168.1.88",
  "wifi_port": 80
}
```

### ESP32 heartbeat

ESP32 sends:

```json
{
  "hardware_id": "ESP32-HAND-001",
  "board_token": "esp32-secret",
  "ip_address": "192.168.1.88",
  "battery_level": 80,
  "signal_strength": -45,
  "telemetry": {
    "rms_value": 126.4,
    "side_pressure": 18.2,
    "muscle_status": "normal",
    "module_statuses": {
      "storage": "ok",
      "model": "loaded",
      "bluetooth": "connected",
      "cpu": "idle"
    },
    "prediction_result": "idle",
    "prediction_confidence": 0.5
  }
}
```

### Backend command

Mini-program asks backend to queue a command:

```json
{
  "action": "start_collect",
  "payload": {
    "session_id": "session_123",
    "gesture_name": "握拳",
    "emg_upload_path": "/devices/wifi/emg"
  }
}
```

ESP32 receives it in heartbeat response, then uploads EMG.

## Replace simulated EMG with your real hardware

You only need to replace these functions in the sketch:

- `readBatteryLevel()`
- `readPredictionResult()`
- `readPredictionConfidence()`
- `readRmsValue()`
- `readSidePressure()`
- `readMuscleStatus()`
- `readEmgValue(uint8_t channelIndex)`

The current version uses fake values so you can test the whole link first.

## How to verify it works

1. Open Arduino serial monitor at `115200`
2. Power ESP32
3. Check serial log:
   - `WiFi connected`
   - `registerBoard status=200`
   - `heartbeat status=200`
4. Open mini-program control page
5. Check whether you can see:
   - online status
   - battery
   - signal strength
   - module statuses
   - prediction result
6. Tap start collect in mini-program
7. Watch serial log for:
   - `handleCommand action=start_collect`
   - `uploadEmgBatch status=200`
8. Tap stop collect
9. Watch final upload succeed

## Common issues

### 0. Mini-program real device still cannot call local IP

ESP32 can talk to your LAN backend with:

- `http://192.168.x.x:8000`

But WeChat mini-program real-device mode may still block local IP requests.

If your phone browser can open backend but mini-program fails, then:

- keep ESP32 -> backend on LAN for debugging
- expose backend with a public HTTPS domain for mini-program
- add that HTTPS domain into WeChat legal request domain

### 1. ESP32 cannot reach backend

Check:

- computer firewall
- backend started with `--host 0.0.0.0`
- `BACKEND_HOST` is your cloud backend host or local test backend host
- ESP32 and computer are on the same Wi-Fi

### 2. Backend says `device not bound`

You must bind the device in mini-program first using the same:

- `hardware_id`
- `board_token`

### 3. Backend says `invalid board_token`

Your sketch `BOARD_TOKEN` does not match mini-program binding value.

### 4. Mini-program shows offline

Usually heartbeat is not reaching backend. Check serial output and backend terminal logs.

## Next step

After this demo runs, replace `readEmgValue()` with your real 8-channel EMG acquisition code.
