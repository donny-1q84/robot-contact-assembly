#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-isaac-l40s}"
LOCAL_PORT="${2:-8226}"
REMOTE_PORT="${3:-8226}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/remote_operation_preflight.sh"

echo "[port-forward] ${ENV_NAME} ${LOCAL_PORT}:${REMOTE_PORT}"
/Users/Shenghan/bin/brev port-forward "${ENV_NAME}" -p "${LOCAL_PORT}:${REMOTE_PORT}"
