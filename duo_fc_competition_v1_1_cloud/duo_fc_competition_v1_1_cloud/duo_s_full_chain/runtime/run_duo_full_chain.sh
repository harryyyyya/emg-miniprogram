#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
CONFIG="${DUO_CONFIG:-$ROOT/config/local.env}"
test -r "$CONFIG" || { echo "missing config: $CONFIG" >&2; exit 2; }
set -a
. "$CONFIG"
set +a

: "${DUO_MODEL_CONTRACT:=$ROOT/duo_s_full_chain/contracts/model_contract.json}"
: "${DUO_CVIMODEL_PATH:=$ROOT/model/duo_fc_mlp_3session_v1_retry2_risk_accepted.cvimodel}"
: "${DUO_PREPROCESS_PATH:=$ROOT/model/preprocess.json}"
: "${DUO_FEATURE_LIB:=$ROOT/build/libduo_emg_features.so}"
: "${DUO_BLE_PLATFORM_MODULE:=duo_s_full_chain.runtime.platform_gatttool}"

: "${DUO_MODEL_CONTRACT:?set an uncommitted local model contract path}"
: "${DUO_CVIMODEL_PATH:?set the local cvimodel path}"
: "${DUO_PREPROCESS_PATH:?set the local preprocessing JSON path}"
: "${DUO_BLE_PLATFORM_MODULE:?set the WYH-probed BLE platform module}"
: "${DUO_UART_SINK:=${DUO_UART_DEVICE:-}}"
: "${DUO_UART_SINK:?set DUO_UART_SINK or the verified DUO_UART_DEVICE}"
: "${DUO_BACKEND_URL:?set the backend base URL}"
: "${DUO_BOARD_TOKEN:?set the board token in the environment}"

exec env PYTHONPATH="$ROOT" python3 -m duo_s_full_chain.runtime.main --mode "${DUO_MODE:-FULL_CHAIN_SAFE_DEMO}"
