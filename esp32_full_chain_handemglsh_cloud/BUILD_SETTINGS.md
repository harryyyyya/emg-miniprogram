# LSH second-batch MLP ESP32-S3 candidate build settings

- Framework: Arduino
- Board: ESP32S3 Dev Module
- Arduino-ESP32 core: `3.2.1`
- Fully qualified board name:
  `esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,CPUFreq=240,UploadSpeed=921600`
- Serial monitor baud: `921600`
- Default mode: `FULL_CHAIN_WITH_EMG_UPLOAD`

Compile-only command (run from the workspace PowerShell):

```powershell
& "D:\arduion ide\resources\app\lib\backend\resources\arduino-cli.exe" compile --fqbn "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,CPUFreq=240,UploadSpeed=921600" --build-path "D:\temp\emg_lsh_build" "D:\EMG train\esp32_full_chain_handemglsh_cloud"
```

The Xtensa linker in this local Arduino environment cannot create an ELF in a
build path containing Chinese characters. Keep the sketch in the independent
delivery folder, but use an ASCII-only build cache path such as the one above.

Do not append `--upload`, run `arduino-cli upload`, or invoke a flashing tool
during automated verification. Hardware operation requires a separate user
action gate. The other full-chain modes are selected by explicitly defining
`FULL_CHAIN_MODE` in the inherited project configuration.
