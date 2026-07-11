#!/usr/bin/env bash
set -uo pipefail
cd /workspace/robot-contact-assembly
RUN_ID=2026-06-20T14-08-28Z-real-video
RUN_DIR=/workspace/robot-contact-assembly/artifacts/videos/real_isaac/${RUN_ID}
mkdir -p "${RUN_DIR}/eval" "/workspace/robot-contact-assembly/artifacts/hydra/real_video_${RUN_ID}"
{
  echo "[real-video] run_id=${RUN_ID}"
  echo "[real-video] started_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "[real-video] task=RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0"
  echo "[real-video] video_backend=viewport video_length=900 steps=900 seed=42"
  echo "[real-video] source_manifest_begin"
  sed -n '1,20p' .rca_launchable_source_manifest.txt || true
  echo "[real-video] source_manifest_end"
} > "${RUN_DIR}/record.meta"
set +e
(
  export CARB_APP_PATH=/isaac-sim/kit
  export ISAAC_PATH=/isaac-sim
  export EXP_PATH=/isaac-sim/apps
  export PYTHONPATH="${PYTHONPATH:-}"
  export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
  source /isaac-sim/setup_python_env.sh
  export RESOURCE_NAME=IsaacSim
  export LD_PRELOAD=/isaac-sim/kit/libcarb.so
  timeout --foreground --signal=TERM --kill-after=60s 900 \
    /isaac-sim/kit/python/bin/python3 scripts/scripted_agent.py \
      --task RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0 \
      --headless \
      --video \
      --video_backend viewport \
      --video_folder "${RUN_DIR}/eval" \
      --video_length 900 \
      --steps 900 \
      --num_envs 1 \
      --seed 42 \
      --summary-json "${RUN_DIR}/video_summary.json" \
      --watchdog_seconds 600 \
      hydra.run.dir="/workspace/robot-contact-assembly/artifacts/hydra/real_video_${RUN_ID}" \
      hydra.output_subdir=null \
      --kit_args "--enable omni.replicator.core --enable omni.kit.material.library --enable omni.kit.viewport.rtx"
) > "${RUN_DIR}/record.log" 2>&1
status=$?
set -e
echo "video_exit=${status}" > "${RUN_DIR}/record.exit"
echo "finished_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "${RUN_DIR}/record.exit"
find "${RUN_DIR}" -maxdepth 3 -type f -print | sort >> "${RUN_DIR}/record.exit"
exit 0