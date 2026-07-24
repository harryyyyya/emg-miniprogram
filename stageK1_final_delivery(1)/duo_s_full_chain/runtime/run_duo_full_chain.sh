#!/bin/sh
set -eu

: "${DUO_MODEL_CONTRACT:?set an uncommitted local model contract path}"
: "${DUO_CVIMODEL_PATH:?set the local cvimodel path}"
: "${DUO_PREPROCESS_PATH:?set the local preprocessing JSON path}"
: "${DUO_BLE_PLATFORM_MODULE:?set the WYH-probed BLE platform module}"
: "${DUO_UART_DEVICE:?set the verified J3 UART device}"
: "${DUO_BACKEND_URL:?set the backend base URL}"
: "${DUO_BOARD_TOKEN:?set the board token in the environment}"

exec python3 -m duo_s_full_chain.runtime.main --mode "${DUO_MODE:-FULL_CHAIN_SAFE_DEMO}"
