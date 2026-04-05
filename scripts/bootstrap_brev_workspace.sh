#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"

echo "[bootstrap] creating remote project layout on ${ENV_NAME}:${REMOTE_ROOT}"
/Users/Shenghan/bin/brev exec "${ENV_NAME}" "mkdir -p '${REMOTE_ROOT}/repo' '${REMOTE_ROOT}/artifacts' '${REMOTE_ROOT}/third_party'"

echo "[bootstrap] remote layout ready"
echo "[bootstrap] next suggested steps:"
echo "  1. sync local repo: ./scripts/sync_to_brev.sh ${ENV_NAME} ${REMOTE_ROOT}"
echo "  2. clone IsaacLab on remote under ${REMOTE_ROOT}/third_party"
echo "  3. wire task package into the remote runtime"
