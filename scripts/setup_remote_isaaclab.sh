#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_ISAACLAB_DIR="${REMOTE_ROOT}/third_party/IsaacLab"

echo "[isaaclab] ensuring IsaacLab develop exists on ${ENV_NAME}:${REMOTE_ISAACLAB_DIR}"
/Users/Shenghan/bin/brev exec "${ENV_NAME}" "bash -lc '
if [ ! -d \"${REMOTE_ISAACLAB_DIR}/.git\" ]; then
  git clone --depth 1 --branch develop https://github.com/isaac-sim/IsaacLab.git \"${REMOTE_ISAACLAB_DIR}\";
else
  cd \"${REMOTE_ISAACLAB_DIR}\";
  git fetch origin develop --depth 1;
  git checkout develop;
  git pull --ff-only origin develop;
fi
'"

echo "[isaaclab] repo ready"
echo "[isaaclab] next suggested steps:"
echo "  1. sync the local repo into ${REMOTE_ROOT}/repo/robot-contact-assembly"
echo "  2. run ./scripts/install_remote_isaaclab_runtime.sh ${ENV_NAME} ${REMOTE_ROOT}"
echo "  3. run ./scripts/run_remote_smoke_test.sh ${ENV_NAME} ${REMOTE_ROOT}"
