#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[sync] local repo:  ${LOCAL_ROOT}"
echo "[sync] remote repo: ${ENV_NAME}:${REMOTE_ROOT}/repo/robot-contact-assembly"
ssh "${ENV_NAME}" "mkdir -p '${REMOTE_ROOT}/repo/robot-contact-assembly'"
rsync -az --delete \
  --exclude '.git/' \
  --exclude 'artifacts/' \
  --exclude 'logs/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${LOCAL_ROOT}/" "${ENV_NAME}:${REMOTE_ROOT}/repo/robot-contact-assembly/"
echo "[sync] done"
