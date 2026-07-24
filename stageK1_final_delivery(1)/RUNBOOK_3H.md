# Three-hour competition runbook

## Before the window

1. Upload the ZIP and its `.sha256` sidecar to `/root` with MobaXterm.
2. On Duo S, verify and extract into a new path:

```sh
cd /root
sha256sum -c duo_fc_competition_v1.zip.sha256
test ! -e /root/duo_fc_competition_v1
unzip duo_fc_competition_v1.zip
cd /root/duo_fc_competition_v1
```

3. Run the read-only/default-mock preflight and recorded acceptance:

```sh
DUO_UART_SINK="file:$PWD/logs/uart_acceptance.bin" DUO_BACKEND_MODE=mock sh bin/preflight.sh
sh bin/run_board_acceptance.sh
```

Do not continue if either command fails. Do not guess a J3 UART device.

## 0:00-0:30 — physical gates

- Confirm PCB revision and official pinout.
- Use live device-tree/pinmux and read-only device inspection to identify J3 UART.
- Never select `/dev/ttyS0` (console) or `/dev/ttyS4` (Bluetooth HCI).
- Wire UART at 3.3 V only; common ground; 115200 8N1.
- Record STM32 receive evidence before setting `DUO_J3_UART_EVIDENCE=LIVE_VERIFIED`.
- Place BT-11 nearby and save logs proving target name, connection, MTU 28, FFE0, FFE2, continuous 98-byte notifications, disconnect, and reconnect.

If any physical gate is absent, retain the file UART and/or record `BT-11 live NOT_RUN`.

## 0:30-1:00 — backend gate

- Use `config/mock.env` first and inspect `logs/mock_http_summary.json`.
- Required mock behavior: register, heartbeat, pending command, ACK; EMG upload count exactly 0.
- Put real credentials only in `/root/duo_fc_competition_v1/config/local.env`.
- Never return `config/local.env` in the result archive.
- Set `DUO_BACKEND_MODE=real` and `DUO_REAL_BACKEND_GATE=LIVE_VERIFIED` only after real endpoint acceptance.

## 1:00-2:30 — controlled run

Mock/file-sink rehearsal:

```sh
DUO_CONFIG="$PWD/config/mock.env" sh bin/start_safe_demo.sh
tail -f logs/runtime.jsonl
```

For accepted physical integration, copy `config/local.env.example` to the unreturned `config/local.env`, fill only verified values, then:

```sh
DUO_CONFIG="$PWD/config/local.env" sh bin/start_safe_demo.sh
```

Watch for parser errors, queue overflow, `signal_timeout`, `fatal_inference`, HTTP timeout, and disconnect/reconnect. HTTP failure must not stop BLE/TPU/UART polling.

## 2:30-3:00 — stop and return evidence

```sh
sh bin/safe_stop.sh
sh bin/collect_logs.sh
```

Confirm `hci0` is absent if the wrapper created it, Wi-Fi is still up, and the returned archive excludes `config/local.env`.

## Emergency stop

```sh
cd /root/duo_fc_competition_v1
sh bin/safe_stop.sh
```

The rollback target is safe stop only. Do not switch to ESP32 or an old model.

