# Stage I BLE adapter evidence basis

This implementation does not claim live BT-11 BLE success.

## Real returned board evidence

- Stage G exact HCI attach command creates UART hci0 with zero RX/TX errors.
- Cleanup removes hci0 and the test-loaded btlpm module; wlan0 remains UP/LOWER_UP.
- BlueZ 5.79, bluetoothctl, gatttool, hcitool, hciconfig and dbus-send exist.
- Python has no bleak/dbus binding and no online package was installed.
- gatttool binary strings prove service, characteristic, descriptor, write,
  MTU, notification and indication output formats.
- A plain pipe into `gatttool -I` timed out and is not used.
- A Python standard-library PTY executed `help`, returned the interactive
  command table, executed `exit`, and the process returned exit code 0.

The returned raw logs are packaged under `evidence/stagei_board_return/raw/`.
The original Stage G HCI archive, sidecar, and command logs are under
`evidence/stageg_original_hci/`. The original Stage H 10-round recorded-replay
result and raw board logs are under `evidence/stageh_board_replay/`.

The raw adapter scan recorded `Discovery started` and one unknown device. It
did not connect to that device and did not observe `BT-11(BLE)`. The explicit
`scan off` command returned `org.bluez.Error.Failed`; later cleanup evidence
shows hci0 absent. These facts are retained together rather than rewriting the
scan-off failure as success.

## Derived test inputs

Files under `duo_s_full_chain/tests/fixtures_stagei/` are deterministic,
synthetic parser inputs derived from the proven binary format strings. They
are not copied hardware transcripts and must never be presented as live BLE
evidence.

## Remaining hardware boundary

No BT-11 target was available. Discovery of BT-11, connection, address type,
MTU negotiation with BT-11, FFE0/FFE2 discovery, CCCD write, real
notifications and reconnect are not hardware-tested and are not claimed.

Evidence directories named `03_target_scan` and `08_adapter_scan` are excluded:
the former was invalidated after a scan-parameter failure was incorrectly
interpreted, and the latter is superseded by the raw-command capture in
`09_adapter_scan_raw`.
