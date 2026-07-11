#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISAAC_SIM_IMAGE="${ISAAC_SIM_IMAGE:-nvcr.io/nvidia/isaac-sim:6.0.0-dev2}"
TASK_CONTAINER_NAME="${RCA_REMOTE_TASK_CONTAINER:-isaac-runner}"
WEB_VIEWER_PORT="${WEB_VIEWER_PORT:-8210}"
ISAACSIM_SIGNAL_PORT="${ISAACSIM_SIGNAL_PORT:-49100}"
ISAACSIM_STREAM_PORT="${ISAACSIM_STREAM_PORT:-47998}"
SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-0}"
RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-full}"
ISAACLAB_GIT_REF="${RCA_ISAACLAB_GIT_REF:-develop}"

"${SCRIPT_DIR}/remote_operation_preflight.sh"

printf -v REMOTE_ROOT_Q "%q" "${REMOTE_ROOT}"
printf -v REMOTE_COMPOSE_ROOT_Q "%q" "${REMOTE_COMPOSE_ROOT}"
printf -v ISAAC_SIM_IMAGE_Q "%q" "${ISAAC_SIM_IMAGE}"
printf -v TASK_CONTAINER_NAME_Q "%q" "${TASK_CONTAINER_NAME}"
printf -v WEB_VIEWER_PORT_Q "%q" "${WEB_VIEWER_PORT}"
printf -v ISAACSIM_SIGNAL_PORT_Q "%q" "${ISAACSIM_SIGNAL_PORT}"
printf -v ISAACSIM_STREAM_PORT_Q "%q" "${ISAACSIM_STREAM_PORT}"
printf -v SKIP_STREAM_STACK_Q "%q" "${SKIP_STREAM_STACK}"
printf -v RUNTIME_PROFILE_Q "%q" "${RUNTIME_PROFILE}"
printf -v ISAACLAB_GIT_REF_Q "%q" "${ISAACLAB_GIT_REF}"

echo "[runtime] ensuring project mounts are active in ${ENV_NAME}"
ssh "${ENV_NAME}" \
  "REMOTE_ROOT=${REMOTE_ROOT_Q} REMOTE_COMPOSE_ROOT=${REMOTE_COMPOSE_ROOT_Q} ISAAC_SIM_IMAGE=${ISAAC_SIM_IMAGE_Q} TASK_CONTAINER_NAME=${TASK_CONTAINER_NAME_Q} WEB_VIEWER_PORT=${WEB_VIEWER_PORT_Q} ISAACSIM_SIGNAL_PORT=${ISAACSIM_SIGNAL_PORT_Q} ISAACSIM_STREAM_PORT=${ISAACSIM_STREAM_PORT_Q} SKIP_STREAM_STACK=${SKIP_STREAM_STACK_Q} RCA_ISAACLAB_RUNTIME_PROFILE=${RUNTIME_PROFILE_Q} RCA_ISAACLAB_GIT_REF=${ISAACLAB_GIT_REF_Q} bash -s" <<'REMOTE_SCRIPT'
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

echo "[runtime] IsaacLab git ref: ${RCA_ISAACLAB_GIT_REF}"
if [ ! -d "${REMOTE_ISAACLAB_DIR}/.git" ]; then
  sudo rm -rf "${REMOTE_ISAACLAB_DIR}"
  git clone --depth 1 --branch "${RCA_ISAACLAB_GIT_REF}" https://github.com/isaac-sim/IsaacLab.git "${REMOTE_ISAACLAB_DIR}"
  sudo chown -R "$(id -un):$(id -gn)" "${REMOTE_ISAACLAB_DIR}"
else
  cd "${REMOTE_ISAACLAB_DIR}"
  if git ls-remote --exit-code --heads origin "${RCA_ISAACLAB_GIT_REF}" >/dev/null 2>&1; then
    git fetch origin "refs/heads/${RCA_ISAACLAB_GIT_REF}:refs/remotes/origin/${RCA_ISAACLAB_GIT_REF}" --depth 1
    git checkout --detach "refs/remotes/origin/${RCA_ISAACLAB_GIT_REF}"
  elif git ls-remote --exit-code --tags origin "${RCA_ISAACLAB_GIT_REF}" >/dev/null 2>&1; then
    git fetch origin "refs/tags/${RCA_ISAACLAB_GIT_REF}:refs/tags/${RCA_ISAACLAB_GIT_REF}" --depth 1
    git checkout --detach "refs/tags/${RCA_ISAACLAB_GIT_REF}"
  else
    git fetch origin "${RCA_ISAACLAB_GIT_REF}" --depth 1
    git checkout --detach FETCH_HEAD
  fi
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

pull_attempt=1
while true; do
  if sudo docker pull "${ISAAC_SIM_IMAGE}"; then
    break
  fi
  if [ "${pull_attempt}" -ge 3 ]; then
    echo "[runtime] docker pull failed after ${pull_attempt} attempts: ${ISAAC_SIM_IMAGE}" >&2
    exit 1
  fi
  echo "[runtime] docker pull failed for ${ISAAC_SIM_IMAGE}; retrying attempt $((pull_attempt + 1))/3" >&2
  pull_attempt=$((pull_attempt + 1))
  sleep 20
done

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

sudo docker exec -u root -i \
  -e RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE}" \
  -e RCA_ISAACLAB_GIT_REF="${RCA_ISAACLAB_GIT_REF}" \
  "${TASK_CONTAINER_NAME}" bash -s <<'CONTAINER_SCRIPT'
set -euo pipefail

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-120}"
export PIP_RETRIES="${PIP_RETRIES:-10}"
RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-full}"
RCA_ISAACLAB_GIT_REF="${RCA_ISAACLAB_GIT_REF:-develop}"

retry_cmd() {
  local attempts="$1"
  local delay_seconds="$2"
  shift 2

  local attempt status
  status=0
  for attempt in $(seq 1 "${attempts}"); do
    set +e
    "$@"
    status=$?
    set -e
    if [ "${status}" -eq 0 ]; then
      return 0
    fi
    echo "[runtime] command failed with status ${status} (attempt ${attempt}/${attempts}): $*" >&2
    if [ "${attempt}" -lt "${attempts}" ]; then
      sleep "${delay_seconds}"
    fi
  done
  return "${status}"
}

install_editable_package() {
  local package_path="$1"
  local required="${2:-required}"

  if [ ! -d "${package_path}" ] || { [ ! -f "${package_path}/pyproject.toml" ] && [ ! -f "${package_path}/setup.py" ]; }; then
    if [ "${required}" = "required" ]; then
      echo "[runtime] missing required editable package: ${package_path}" >&2
      exit 1
    fi
    echo "[runtime] skipping optional editable package: ${package_path}"
    return 0
  fi

  retry_cmd 3 20 /isaac-sim/python.sh -m pip install --no-build-isolation --editable "${package_path}"
}

install_isaaclab_core_runtime() {
  install_editable_package /workspace/IsaacLab/source/isaaclab required
  install_editable_package /workspace/IsaacLab/source/isaaclab_assets required
  install_editable_package /workspace/IsaacLab/source/isaaclab_physx optional
  install_editable_package /workspace/IsaacLab/source/isaaclab_tasks required
  install_editable_package /workspace/IsaacLab/source/isaaclab_rl required
}

validate_runtime_imports() {
  echo "[runtime] validating IsaacLab imports"
  /isaac-sim/python.sh - <<'PY'
import importlib
import importlib.util
import os

for module_name in (
    "isaaclab",
    "isaaclab.app",
    "isaaclab_rl",
):
    importlib.import_module(module_name)
    print(f"[runtime-import] OK {module_name}")

for module_name in (
    "isaaclab_tasks",
    "robot_contact_assembly_tasks",
):
    if importlib.util.find_spec(module_name) is None:
        raise ModuleNotFoundError(module_name)
    print(f"[runtime-import] FOUND {module_name}")

if os.environ.get("RCA_ISAACLAB_RUNTIME_PROFILE") in {"camera", "viewport"}:
    import warp

    if not hasattr(warp, "context"):
        raise RuntimeError("rendering profile requires a warp package with warp.context")
    if not hasattr(getattr(warp, "types", None), "array"):
        raise RuntimeError("rendering profile requires a warp package with warp.types.array")
    print("[runtime-import] OK rendering warp compatibility")
PY
}

if ! command -v git >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git
fi
export TERM="${TERM:-xterm-256color}"
ln -sfn /isaac-sim /workspace/IsaacLab/_isaac_sim
mkdir -p /workspace/artifacts/hydra
chown -R 1234:1234 /workspace/artifacts
cd /workspace/IsaacLab
echo "[runtime] installing IsaacLab ref ${RCA_ISAACLAB_GIT_REF} with profile ${RCA_ISAACLAB_RUNTIME_PROFILE}"
retry_cmd 3 20 /isaac-sim/python.sh -m pip install "setuptools<80"
retry_cmd 3 20 /isaac-sim/python.sh -m pip install --no-build-isolation flatdict==4.0.1
if [ "${RCA_ISAACLAB_RUNTIME_PROFILE}" = "trace-only" ]; then
  echo "[runtime] trace-only profile: installing required IsaacLab runtime submodules only"
  install_isaaclab_core_runtime
  retry_cmd 3 20 /isaac-sim/python.sh -m pip install warp-lang==1.12.1 pillow==12.1.1
  echo "[runtime] trace-only profile: skipping optional IsaacLab contrib/newton/visualizer/rsl-rl explicit installs"
elif [ "${RCA_ISAACLAB_RUNTIME_PROFILE}" = "camera" ]; then
  echo "[runtime] camera profile: installing headless IsaacLab runtime plus video writer dependencies"
  install_isaaclab_core_runtime
  retry_cmd 3 20 /isaac-sim/python.sh -m pip install warp-lang==1.12.1 pillow==12.1.1 imageio imageio-ffmpeg
  echo "[runtime] camera profile: skipping optional IsaacLab contrib/newton/visualizer/rsl-rl explicit installs"
elif [ "${RCA_ISAACLAB_RUNTIME_PROFILE}" = "viewport" ]; then
  echo "[runtime] viewport profile: installing IsaacLab runtime plus screen/video dependencies"
  install_isaaclab_core_runtime
  retry_cmd 3 20 /isaac-sim/python.sh -m pip install warp-lang==1.12.1 imageio imageio-ffmpeg
  echo "[runtime] viewport profile: skipping optional training extras"
else
  retry_cmd 3 20 ./isaaclab.sh --install
  install_editable_package /workspace/IsaacLab/source/isaaclab_contrib optional
  install_editable_package /workspace/IsaacLab/source/isaaclab_rl required
  retry_cmd 3 20 /isaac-sim/python.sh -m pip install h5py
fi
retry_cmd 3 20 /isaac-sim/python.sh -m pip install hydra-core
retry_cmd 3 20 /isaac-sim/python.sh -m pip install --editable /workspace/robot-contact-assembly/source/robot_contact_assembly_tasks
validate_runtime_imports
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
