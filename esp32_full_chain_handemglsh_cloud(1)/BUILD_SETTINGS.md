# Stage 6.1C Full Chain Build Settings

- Framework: Arduino
- Board: ESP32S3 Dev Module
- Target Arduino-ESP32 core: `3.2.1`
- Fully qualified board name:
  `esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,CPUFreq=240,UploadSpeed=921600`
- Serial monitor baud: `921600`
- Default mode: `FULL_CHAIN_WITH_EMG_UPLOAD`

Full compile-only command to run after `arduino-cli` is installed:

```powershell
arduino-cli compile --fqbn "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,CPUFreq=240,UploadSpeed=921600" "D:\weixin\esp32_full_chain_handemglsh_cloud(1)"
```

`arduino-cli` was not available during the current repository verification.
The modified network worker, upload queue, and BLE ingestion translation units
passed syntax checks with the locally installed ESP32-S3 toolchain and
Arduino-ESP32 3.3.10. Run the full command above with the target 3.2.1 core
before flashing.

Do not append `--upload`, run `arduino-cli upload`, or invoke a flashing tool
during automated verification. Hardware operation requires a separate user
action gate.
