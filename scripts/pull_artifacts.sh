#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
LOCAL_ARTIFACT_ROOT="${3:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/artifacts}"

mkdir -p "${LOCAL_ARTIFACT_ROOT}"
echo "[pull] remote artifacts: ${ENV_NAME}:${REMOTE_ROOT}/artifacts"
echo "[pull] local artifacts:  ${LOCAL_ARTIFACT_ROOT}"
rsync -av --ignore-existing "${ENV_NAME}:${REMOTE_ROOT}/artifacts/" "${LOCAL_ARTIFACT_ROOT}/"
echo "[pull] done"
