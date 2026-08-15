# Stage K.1 Duo verification commands

Run these commands manually on Duo S after copying this directory to
`/root/duo_fc_competition_v1_1`. They are instructions, not completion evidence.

## 1. Ten-round recorded full-chain

```sh
cd /root/duo_fc_competition_v1_1
mkdir -p logs/stagek1
LD_LIBRARY_PATH="/mnt/system/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
python3 -m duo_s_full_chain.runtime.board_replay \
  --recording fixtures/demo_sequence.bin \
  --expected reference/recorded_bf16_reference.json \
  --model-contract duo_s_full_chain/contracts/model_contract.json \
  --cvimodel model/duo_fc_mlp_3session_v1_retry2_risk_accepted.cvimodel \
  --preprocess model/preprocess.json \
  --feature-lib build/libduo_emg_features.so \
  --runtime-lib /mnt/system/lib/libcviruntime.so \
  --rounds 10 \
  --output logs/stagek1/recorded_10_rounds.json \
  > logs/stagek1/recorded_10_rounds.stdout.log 2>&1
echo "RECORDED_EXIT=$?"
```

## 2. Duo unit tests

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
python3 -m unittest discover -s duo_s_full_chain/tests -v \
  > logs/stagek1/duo_unittest.log 2>&1
echo "DUO_UNIT_EXIT=$?"
```

## 3. Package preflight

```sh
DUO_CONFIG="$PWD/config/mock.env" sh bin/preflight.sh \
  > logs/stagek1/preflight.log 2>&1
echo "PREFLIGHT_EXIT=$?"
```

## 4. Five-minute process smoke

The loop samples both processes every five seconds and stops immediately if either dies.

```sh
set -eu
DUO_CONFIG="$PWD/config/mock.env" sh bin/start_safe_demo.sh \
  > logs/stagek1/start.log 2>&1
runtime_pid="$(cat state/runtime.pid)"
mock_pid="$(cat state/mock_server.pid)"
cleanup() { sh bin/safe_stop.sh >> logs/stagek1/stop.log 2>&1 || true; }
trap cleanup EXIT HUP INT TERM
i=1
while test "$i" -le 60; do
  kill -0 "$runtime_pid"
  kill -0 "$mock_pid"
  printf 'sample=%s runtime_alive=yes mock_alive=yes\n' "$i" >> logs/stagek1/process_samples.log
  sleep 5
  i=$((i + 1))
done
cleanup
trap - EXIT HUP INT TERM
test ! -e "/proc/$runtime_pid"
test ! -e "/proc/$mock_pid"
test ! -d /sys/class/bluetooth/hci0
ip link show wlan0 | grep -F 'UP' | grep -F 'LOWER_UP'
! grep -Ehi 'traceback|out of memory|oom|uncaught exception' logs/runtime.stderr.log logs/runtime.jsonl
echo "STAGEK1_PROCESS_SMOKE_COMMANDS_COMPLETED"
```

Do not assign the final pass token from the command exit codes alone. Inspect the raw logs and mock summary for register, heartbeat, pending command, ACK, zero EMG uploads, and inspect the final six UART bytes for a valid no-stable frame. Live BT-11, J3-to-STM32, real backend, and actuator gates remain `NOT_RUN` unless separately evidenced.
