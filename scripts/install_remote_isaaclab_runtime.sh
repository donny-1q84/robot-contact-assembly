#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
REMOTE_REPO_DIR="${REMOTE_ROOT}/repo/robot-contact-assembly"
REMOTE_OVERRIDE_FILE="${REMOTE_REPO_DIR}/docker/isaac-compose.project.yml"
ISAAC_SIM_IMAGE="${ISAAC_SIM_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
WEB_VIEWER_PORT="${WEB_VIEWER_PORT:-8210}"
ISAACSIM_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT:-49100}"
ISAACSIM_STREAM_PORT="${ISAACSIM_STREAM_PORT:-47998}"

COMPOSE_BASE="docker compose -p isim -f tools/docker/docker-compose.yml -f ${REMOTE_OVERRIDE_FILE}"

echo "[runtime] ensuring project mounts are active in ${ENV_NAME}"
/Users/Shenghan/bin/brev exec "${ENV_NAME}" "bash -lc '
set -euo pipefail
HOST_IP=\$(curl -fsS --max-time 5 https://api.ipify.org || curl -fsS --max-time 5 https://ifconfig.me)
if [ -z \"\$HOST_IP\" ]; then
  echo \"[runtime] failed to resolve remote public IP\" >&2
  exit 1
fi
cd \"${REMOTE_COMPOSE_ROOT}\"
ISAAC_SIM_IMAGE=\"${ISAAC_SIM_IMAGE}\" WEB_VIEWER_PORT=\"${WEB_VIEWER_PORT}\" ISAACSIM_SIGNAL_PORT=\"${ISAACSIM_SIGNAL_PORT}\" ISAACSIM_STREAM_PORT=\"${ISAACSIM_STREAM_PORT}\" ISAACSIM_HOST=\"\$HOST_IP\" ${COMPOSE_BASE} up -d
ISAAC_SIM_IMAGE=\"${ISAAC_SIM_IMAGE}\" WEB_VIEWER_PORT=\"${WEB_VIEWER_PORT}\" ISAACSIM_SIGNAL_PORT=\"${ISAACSIM_SIGNAL_PORT}\" ISAACSIM_STREAM_PORT=\"${ISAACSIM_STREAM_PORT}\" ISAACSIM_HOST=\"\$HOST_IP\" ${COMPOSE_BASE} exec -T -u root isaac-sim bash -lc \"
set -euo pipefail
ln -sfn /isaac-sim /workspace/IsaacLab/_isaac_sim
mkdir -p /workspace/artifacts/hydra
chown -R 1234:1234 /workspace/artifacts
cd /workspace/IsaacLab
./isaaclab.sh --install assets,physx,tasks
/isaac-sim/python.sh -m pip install h5py
/isaac-sim/python.sh -m pip install hydra-core
/isaac-sim/python.sh -m pip install --editable /workspace/robot-contact-assembly/source/robot_contact_assembly_tasks
\"
'"

echo "[runtime] remote Isaac Lab runtime ready"
echo "[runtime] next suggested step:"
echo "  ./scripts/run_remote_smoke_test.sh ${ENV_NAME} ${REMOTE_ROOT} ${REMOTE_COMPOSE_ROOT}"
