#!/bin/sh
set -eu

cd "$(dirname "$0")"
mkdir -p build results

on_exit() {
  code=$?
  trap - EXIT
  printf '%s
' "$code" > results/exit_code.txt
  exit "$code"
}
trap on_exit EXIT

sha256sum -c PACKAGE_FILES.sha256

{
  date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
  uname -a
  python3 --version
  python3 -c 'import numpy; print("numpy=" + numpy.__version__)'
  echo 'native_feature=prebuilt_riscv64_no_dynamic_dependencies'
  sha256sum /mnt/system/lib/libcviruntime.so /mnt/system/usr/bin/tpu/model_runner
  cat /proc/meminfo | head -n 5
} > results/environment.txt 2>&1
cat results/environment.txt

sha256sum build/libduo_emg_features.so > results/native_feature_sha256.txt
cat results/native_feature_sha256.txt

set +e
LD_LIBRARY_PATH=/mnt/system/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} PYTHONPATH=. python3 -m duo_s_full_chain.runtime.board_replay   --recording fixtures/demo_sequence.bin   --expected reference/recorded_bf16_reference.json   --model-contract duo_s_full_chain/contracts/model_contract.json   --cvimodel model/duo_fc_mlp_3session_v1_retry2_risk_accepted.cvimodel   --preprocess model/preprocess.json   --feature-lib build/libduo_emg_features.so   --runtime-lib /mnt/system/lib/libcviruntime.so   --rounds 10   --output results/board_replay_10rounds.json   > results/board_replay_stdout.txt 2>&1
replay_code=$?
set -e
cat results/board_replay_stdout.txt
if [ "$replay_code" -ne 0 ]; then
  echo "DUO_STAGEH_RECORDED_REPLAY=FAIL exit_code=$replay_code"
  exit "$replay_code"
fi

python3 -c 'import json; report=json.load(open("results/board_replay_10rounds.json", encoding="utf-8")); assert report["status"] == "PASS" and report["rounds_passed"] == 10'

echo 'DUO_STAGEH_RECORDED_REPLAY=PASS'
