#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
ISAAC_SIM_IMAGE="${ISAAC_SIM_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
TASK_CONTAINER_NAME="${RCA_REMOTE_TASK_CONTAINER:-isaac-runner}"
WEB_VIEWER_PORT="${WEB_VIEWER_PORT:-8210}"
ISAACSIM_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT:-49100}"
ISAACSIM_STREAM_PORT="${ISAACSIM_STREAM_PORT:-47998}"
SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-0}"

printf -v REMOTE_ROOT_Q "%q" "${REMOTE_ROOT}"
printf -v REMOTE_COMPOSE_ROOT_Q "%q" "${REMOTE_COMPOSE_ROOT}"
printf -v ISAAC_SIM_IMAGE_Q "%q" "${ISAAC_SIM_IMAGE}"
printf -v TASK_CONTAINER_NAME_Q "%q" "${TASK_CONTAINER_NAME}"
printf -v WEB_VIEWER_PORT_Q "%q" "${WEB_VIEWER_PORT}"
printf -v ISAACSIM_SIGNAL_PORT_Q "%q" "${ISAACSIM_SIGNAL_PORT}"
printf -v ISAACSIM_STREAM_PORT_Q "%q" "${ISAACSIM_STREAM_PORT}"
printf -v SKIP_STREAM_STACK_Q "%q" "${SKIP_STREAM_STACK}"

echo "[runtime] ensuring project mounts are active in ${ENV_NAME}"
ssh "${ENV_NAME}" \
  "REMOTE_ROOT=${REMOTE_ROOT_Q} REMOTE_COMPOSE_ROOT=${REMOTE_COMPOSE_ROOT_Q} ISAAC_SIM_IMAGE=${ISAAC_SIM_IMAGE_Q} TASK_CONTAINER_NAME=${TASK_CONTAINER_NAME_Q} WEB_VIEWER_PORT=${WEB_VIEWER_PORT_Q} ISAACSIM_SIGNAL_PORT=${ISAACSIM_SIGNAL_PORT_Q} ISAACSIM_STREAM_PORT=${ISAACSIM_STREAM_PORT_Q} SKIP_STREAM_STACK=${SKIP_STREAM_STACK_Q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

REMOTE_LAUNCHABLE_DIR="${REMOTE_ROOT}/third_party/isaac-launchable"
REMOTE_ISAACLAB_DIR="${REMOTE_ROOT}/third_party/IsaacLab"
REMOTE_REPO_DIR="${REMOTE_ROOT}/repo/robot-contact-assembly"
REMOTE_OVERRIDE_FILE="${REMOTE_REPO_DIR}/docker/isaac-compose.project.yml"
COMPOSE_BASE="sudo docker compose -p isim -f ${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml -f ${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml -f ${REMOTE_OVERRIDE_FILE}"

if [ ! -f "${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml" ] || [ ! -f "${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml" ]; then
  if [ ! -d "${REMOTE_LAUNCHABLE_DIR}/.git" ]; then
    git clone --depth 1 https://github.com/isaac-sim/isaac-launchable "${REMOTE_LAUNCHABLE_DIR}"
  else
    cd "${REMOTE_LAUNCHABLE_DIR}"
    git fetch origin --depth 1
    git reset --hard origin/HEAD
  fi
  mkdir -p "${REMOTE_COMPOSE_ROOT}/tools/docker"
  ln -sfn "${REMOTE_LAUNCHABLE_DIR}/isaac-sim/nginx" "${REMOTE_COMPOSE_ROOT}/tools/docker/nginx"
  ln -sfn "${REMOTE_LAUNCHABLE_DIR}/isaac-sim/web-viewer-sample" "${REMOTE_COMPOSE_ROOT}/tools/docker/web-viewer-sample"
  cat > "${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml" <<EOF
volumes:
  shared:
  isaac-sim-cache-ov:
  isaac-sim-cache-pip:
  isaac-sim-cache-glcache:
  isaac-sim-cache-computecache:
  isaac-sim-cache-asset-browser:
  isaac-sim-logs:
  isaac-sim-data:
  isaac-sim-pkg:
  isaac-sim-documents:

services:
  isaac-sim:
    container_name: isaac-sim
    image: ${ISAAC_SIM_IMAGE}
    restart: unless-stopped
    runtime: nvidia
    network_mode: "host"
    environment:
      - ACCEPT_EULA=Y
      - PRIVACY_CONSENT=Y
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  nginx:
    container_name: isaac-nginx
    network_mode: "host"
    restart: unless-stopped

  web-viewer:
    container_name: web-viewer
    build:
      context: ./web-viewer-sample
      network: host
    network_mode: "host"
    restart: unless-stopped
    environment:
      - ENV=brev
EOF
  cat > "${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml" <<EOF
services:
  nginx:
    build:
      context: ./nginx
      network: host
EOF
fi

if [ ! -d "${REMOTE_ISAACLAB_DIR}/.git" ]; then
  sudo rm -rf "${REMOTE_ISAACLAB_DIR}"
  git clone --depth 1 --branch develop https://github.com/isaac-sim/IsaacLab.git "${REMOTE_ISAACLAB_DIR}"
  sudo chown -R "$(id -un):$(id -gn)" "${REMOTE_ISAACLAB_DIR}"
else
  cd "${REMOTE_ISAACLAB_DIR}"
  git fetch origin develop --depth 1
  git checkout develop
  git pull --ff-only origin develop
fi

HOST_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true)"
if [ -z "${HOST_IP}" ]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [ -z "${HOST_IP}" ]; then
  HOST_IP=127.0.0.1
  echo "[runtime] warning: public IP resolution failed; falling back to 127.0.0.1 for viewer config" >&2
fi

cat > "${REMOTE_OVERRIDE_FILE}" <<EOF
services:
  isaac-sim:
    volumes:
      - ${REMOTE_REPO_DIR}:/workspace/robot-contact-assembly:rw
      - ${REMOTE_ISAACLAB_DIR}:/workspace/IsaacLab:rw
      - ${REMOTE_ROOT}/artifacts:/workspace/artifacts:rw
EOF

cd "${REMOTE_COMPOSE_ROOT}"
if [ "${SKIP_STREAM_STACK}" = "1" ]; then
  echo "[runtime] skipping streaming compose stack; headless task container only"
else
  ISAAC_SIM_IMAGE="${ISAAC_SIM_IMAGE}" WEB_VIEWER_PORT="${WEB_VIEWER_PORT}" ISAACSIM_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT}" ISAACSIM_STREAM_PORT="${ISAACSIM_STREAM_PORT}" ISAACSIM_HOST="${HOST_IP}" ${COMPOSE_BASE} up -d --build
fi

sudo docker rm -f "${TASK_CONTAINER_NAME}" >/dev/null 2>&1 || true
sudo docker run -d \
  --name "${TASK_CONTAINER_NAME}" \
  --restart unless-stopped \
  --gpus all \
  --network host \
  --entrypoint bash \
  -e ACCEPT_EULA=Y \
  -e PRIVACY_CONSENT=Y \
  -v "${REMOTE_REPO_DIR}:/workspace/robot-contact-assembly:rw" \
  -v "${REMOTE_ISAACLAB_DIR}:/workspace/IsaacLab:rw" \
  -v "${REMOTE_ROOT}/artifacts:/workspace/artifacts:rw" \
  "${ISAAC_SIM_IMAGE}" \
  -lc "sleep infinity" >/dev/null

sudo docker exec -u root -i "${TASK_CONTAINER_NAME}" bash -s <<'CONTAINER_SCRIPT'
set -euo pipefail
if ! command -v git >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git
fi
ln -sfn /isaac-sim /workspace/IsaacLab/_isaac_sim
mkdir -p /workspace/artifacts/hydra
chown -R 1234:1234 /workspace/artifacts
cd /workspace/IsaacLab
./isaaclab.sh --install assets,physx,tasks
/isaac-sim/python.sh -m pip install --editable /workspace/IsaacLab/source/isaaclab_contrib
/isaac-sim/python.sh -m pip install --editable /workspace/IsaacLab/source/isaaclab_rl
if ! /isaac-sim/python.sh -m pip show rsl-rl-lib >/dev/null 2>&1; then
  /isaac-sim/python.sh -m pip install rsl-rl-lib==5.0.1 onnxscript\>=0.5 numpy==2.3.1 pillow==12.1.1
fi
/isaac-sim/python.sh -m pip install h5py
/isaac-sim/python.sh -m pip install hydra-core
/isaac-sim/python.sh -m pip install --editable /workspace/robot-contact-assembly/source/robot_contact_assembly_tasks
TENSOR_API_DIR="$(find /isaac-sim/extscache -path '*/omni/physics/tensors' -type d 2>/dev/null | head -n 1 || true)"
if [ -n "${TENSOR_API_DIR}" ] && [ ! -f "${TENSOR_API_DIR}/api.py" ] && [ -f "${TENSOR_API_DIR}/impl/api.py" ]; then
  cat > "${TENSOR_API_DIR}/api.py" <<'PYEOF'
from .impl.api import *
PYEOF
fi
CONTAINER_SCRIPT
REMOTE_SCRIPT

echo "[runtime] remote Isaac Lab runtime ready"
echo "[runtime] task container: ${TASK_CONTAINER_NAME}"
echo "[runtime] next suggested step:"
echo "  ./scripts/run_remote_smoke_test.sh ${ENV_NAME} ${REMOTE_ROOT} ${REMOTE_COMPOSE_ROOT}"
