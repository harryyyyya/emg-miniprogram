These are synthetic parser inputs, not hardware logs and not live BLE evidence.

Their line formats are derived only from strings returned from WYH's actual
Duo S binaries on 2026-07-23:

  bluetoothctl: Device %s %s; SetDiscoveryFilter success
  gatttool: attr handle ... end grp handle ... uuid
  gatttool: handle ... char properties ... char value handle ... uuid
  gatttool: handle ... uuid
  gatttool: Notification/Indication handle ... value

The real probe logs must remain separate from these deterministic fixtures.
