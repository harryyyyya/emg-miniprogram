# Duo S full-chain compatible runtime

This is the Linux/Duo S behavior port of the authoritative ESP32
`FULL_CHAIN_SAFE_DEMO`. The default formal mode remains
`FULL_CHAIN_SAFE_DEMO`. Windows evidence is limited to host/mock/recorded
replay and is not BLE, UART, Wi-Fi, TPU, or complete hardware evidence.

Host verification from the workspace root:

```powershell
python -m unittest discover -s duo_s_full_chain/tests -v
python -m duo_s_full_chain.runtime.replay
python duo_s_full_chain/tests/verify_host.py
```

See `artifacts/duo_s_full_chain_runtime_f2/00_RUNTIME_HANDOFF_START_HERE.md`
for the board handoff.
