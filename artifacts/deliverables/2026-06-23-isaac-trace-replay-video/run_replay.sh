#!/usr/bin/env bash
set -euo pipefail
child_pid=
cleanup() {
  if [[ -n ${child_pid} ]]; then
    kill ${child_pid} >/dev/null 2>&1 || true
    sleep 2
    kill -9 ${child_pid} >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT TERM INT
export CARB_APP_PATH=/isaac-sim/kit
export ISAAC_PATH=/isaac-sim
export EXP_PATH=/isaac-sim/apps
export PYTHONPATH="${PYTHONPATH:-}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
source /isaac-sim/setup_python_env.sh
export RESOURCE_NAME=IsaacSim
export LD_PRELOAD=/isaac-sim/kit/libcarb.so
export RCA_FORCE_APP_LAUNCHER='1'
/isaac-sim/kit/python/bin/python3 scripts/replay_trace_in_isaac_video.py   --headless   --trace-json '/workspace/robot-contact-assembly/.tmp/trace_replay_inputs/2026-06-23T05-33-52Z/source_trace.json'   --task 'RCA-PegInHole-Franka-JointPos-Contact-Play-v0'   --video-folder '/workspace/artifacts/videos/isaac_trace_replay/2026-06-23T05-33-52Z/eval'   --summary-json '/workspace/artifacts/videos/isaac_trace_replay/2026-06-23T05-33-52Z/replay_summary.json'   --start-step '0'   --end-step '220'   --stride '1'   --fps '30'   --seed '42'   --num-envs 1   --require-source-success   --write-peg-root-from-trace &
child_pid=$!
wait ${child_pid}
