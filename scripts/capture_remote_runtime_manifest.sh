#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_MANIFEST_DIR="${RCA_REMOTE_REPO_DIR}/experiments/runtime_manifests"
REMOTE_MANIFEST_FILE="${REMOTE_MANIFEST_DIR}/${TIMESTAMP_UTC}.md"

echo "[runtime-manifest] env=${RCA_ENV_NAME}"
echo "[runtime-manifest] writing ${REMOTE_MANIFEST_FILE}"

rca_remote_host_exec "
set -euo pipefail
mkdir -p '${REMOTE_MANIFEST_DIR}'
cd '${RCA_REMOTE_COMPOSE_ROOT}'
cat > '${REMOTE_MANIFEST_FILE}' <<'EOF'
# Runtime Manifest

- timestamp_utc: ${TIMESTAMP_UTC}
- env_name: ${RCA_ENV_NAME}
- remote_root: ${RCA_REMOTE_ROOT}
- remote_compose_root: ${RCA_REMOTE_COMPOSE_ROOT}

## Compose status
EOF
${RCA_COMPOSE_BASE} ps >> '${REMOTE_MANIFEST_FILE}'
cat >> '${REMOTE_MANIFEST_FILE}' <<'EOF'

## Container package versions
EOF
${RCA_COMPOSE_BASE} exec -T isaac-sim bash -lc \"/isaac-sim/python.sh -m pip show numpy pillow lxml h5py hydra-core isaaclab isaaclab-rl 2>/dev/null | egrep '^(Name|Version):'\" >> '${REMOTE_MANIFEST_FILE}'
cat >> '${REMOTE_MANIFEST_FILE}' <<'EOF'

## Python runtime
EOF
${RCA_COMPOSE_BASE} exec -T isaac-sim bash -lc \"/isaac-sim/python.sh --version\" >> '${REMOTE_MANIFEST_FILE}'
cat >> '${REMOTE_MANIFEST_FILE}' <<'EOF'

## Registered peg-in-hole environments
EOF
${RCA_COMPOSE_BASE} exec -T isaac-sim bash -lc \"cd /workspace/robot-contact-assembly && /isaac-sim/python.sh scripts/list_envs.py --keyword PegInHole\" >> '${REMOTE_MANIFEST_FILE}'
cat >> '${REMOTE_MANIFEST_FILE}' <<'EOF'

## Git status
EOF
cd '${RCA_REMOTE_REPO_DIR}'
git status --short >> '${REMOTE_MANIFEST_FILE}'
git rev-parse HEAD >> '${REMOTE_MANIFEST_FILE}'
"

echo "[runtime-manifest] wrote ${REMOTE_MANIFEST_FILE}"
