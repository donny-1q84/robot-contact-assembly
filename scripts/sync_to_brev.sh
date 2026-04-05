#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[sync] local repo:  ${LOCAL_ROOT}"
echo "[sync] remote repo: ${ENV_NAME}:${REMOTE_ROOT}/repo"
/Users/Shenghan/bin/brev copy "${LOCAL_ROOT}" "${ENV_NAME}:${REMOTE_ROOT}/repo"
echo "[sync] done"
