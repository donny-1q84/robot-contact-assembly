#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
REMOTE_LAUNCHABLE_DIR="${REMOTE_ROOT}/third_party/isaac-launchable"
REMOTE_ISAACLAB_DIR="${REMOTE_ROOT}/third_party/IsaacLab"
REMOTE_REPO_DIR="${REMOTE_ROOT}/repo/robot-contact-assembly"
REMOTE_OVERRIDE_FILE="${REMOTE_REPO_DIR}/docker/isaac-compose.project.yml"
ISAAC_SIM_IMAGE="${ISAAC_SIM_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
TASK_CONTAINER_NAME="${RCA_REMOTE_TASK_CONTAINER:-isaac-runner}"
WEB_VIEWER_PORT="${WEB_VIEWER_PORT:-8210}"
ISAACSIM_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT:-49100}"
ISAACSIM_STREAM_PORT="${ISAACSIM_STREAM_PORT:-47998}"

COMPOSE_BASE="sudo docker compose -p isim -f ${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml -f ${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml -f ${REMOTE_OVERRIDE_FILE}"

echo "[runtime] ensuring project mounts are active in ${ENV_NAME}"
ssh "${ENV_NAME}" "bash -lc '
set -euo pipefail
if [ ! -f \"${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml\" ] || [ ! -f \"${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml\" ]; then
  if [ ! -d \"${REMOTE_LAUNCHABLE_DIR}/.git\" ]; then
    git clone --depth 1 https://github.com/isaac-sim/isaac-launchable \"${REMOTE_LAUNCHABLE_DIR}\"
  else
    cd \"${REMOTE_LAUNCHABLE_DIR}\"
    git fetch origin --depth 1
    git reset --hard origin/HEAD
  fi
  mkdir -p \"${REMOTE_COMPOSE_ROOT}/tools/docker\"
  ln -sfn \"${REMOTE_LAUNCHABLE_DIR}/isaac-sim/nginx\" \"${REMOTE_COMPOSE_ROOT}/tools/docker/nginx\"
  ln -sfn \"${REMOTE_LAUNCHABLE_DIR}/isaac-sim/web-viewer-sample\" \"${REMOTE_COMPOSE_ROOT}/tools/docker/web-viewer-sample\"
  cat > \"${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.yml\" <<EOF
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
    network_mode: \"host\"
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
    network_mode: \"host\"
    restart: unless-stopped

  web-viewer:
    container_name: web-viewer
    build:
      context: ./web-viewer-sample
      network: host
    network_mode: \"host\"
    restart: unless-stopped
    environment:
      - ENV=brev
EOF
  cat > \"${REMOTE_COMPOSE_ROOT}/tools/docker/docker-compose.override.yml\" <<EOF
services:
  nginx:
    build:
      context: ./nginx
      network: host
EOF
fi
if [ ! -d \"${REMOTE_ISAACLAB_DIR}/.git\" ]; then
  sudo rm -rf \"${REMOTE_ISAACLAB_DIR}\"
  git clone --depth 1 --branch develop https://github.com/isaac-sim/IsaacLab.git \"${REMOTE_ISAACLAB_DIR}\"
  sudo chown -R ubuntu:ubuntu \"${REMOTE_ISAACLAB_DIR}\"
else
  cd \"${REMOTE_ISAACLAB_DIR}\"
  git fetch origin develop --depth 1
  git checkout develop
  git pull --ff-only origin develop
fi
HOST_IP=\$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true)
if [ -z \"\$HOST_IP\" ]; then
  HOST_IP=\$(hostname -I 2>/dev/null | awk '\''{print \$1}'\'')
fi
if [ -z \"\$HOST_IP\" ]; then
  HOST_IP=127.0.0.1
  echo \"[runtime] warning: public IP resolution failed; falling back to 127.0.0.1 for viewer config\" >&2
fi
cd \"${REMOTE_COMPOSE_ROOT}\"
ISAAC_SIM_IMAGE=\"${ISAAC_SIM_IMAGE}\" WEB_VIEWER_PORT=\"${WEB_VIEWER_PORT}\" ISAACSIM_SIGNAL_PORT=\"${ISAACSIM_SIGNAL_PORT}\" ISAACSIM_STREAM_PORT=\"${ISAACSIM_STREAM_PORT}\" ISAACSIM_HOST=\"\$HOST_IP\" ${COMPOSE_BASE} up -d --build
sudo docker rm -f \"${TASK_CONTAINER_NAME}\" >/dev/null 2>&1 || true
sudo docker run -d \
  --name \"${TASK_CONTAINER_NAME}\" \
  --restart unless-stopped \
  --gpus all \
  --network host \
  -e ACCEPT_EULA=Y \
  -e PRIVACY_CONSENT=Y \
  -v \"${REMOTE_REPO_DIR}:/workspace/robot-contact-assembly:rw\" \
  -v \"${REMOTE_ISAACLAB_DIR}:/workspace/IsaacLab:rw\" \
  -v \"${REMOTE_ROOT}/artifacts:/workspace/artifacts:rw\" \
  \"${ISAAC_SIM_IMAGE}\" \
  bash -lc \"sleep infinity\" >/dev/null
sudo docker exec -u root -i \"${TASK_CONTAINER_NAME}\" bash -lc \"
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
  /isaac-sim/python.sh -m pip install rsl-rl-lib==5.0.1 onnxscript\\>=0.5 numpy==2.3.1 pillow==12.1.1
fi
/isaac-sim/python.sh -m pip install h5py
/isaac-sim/python.sh -m pip install hydra-core
/isaac-sim/python.sh -m pip install --editable /workspace/robot-contact-assembly/source/robot_contact_assembly_tasks
\"
'"

echo "[runtime] remote Isaac Lab runtime ready"
echo "[runtime] task container: ${TASK_CONTAINER_NAME}"
echo "[runtime] next suggested step:"
echo "  ./scripts/run_remote_smoke_test.sh ${ENV_NAME} ${REMOTE_ROOT} ${REMOTE_COMPOSE_ROOT}"
