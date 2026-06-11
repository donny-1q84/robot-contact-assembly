#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
OUT_DIR="${RCA_LAUNCHABLE_BUNDLE_DIR:-${REPO_ROOT}/artifacts/launchable}"
OUT_PATH="${1:-${OUT_DIR}/robot-contact-assembly-launchable-${RUN_ID}.tar.gz}"
PRELOAD_TRACE="${RCA_LAUNCHABLE_PRELOAD_TRACE_LOCAL:-${REPO_ROOT}/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

mkdir -p "${OUT_DIR}" "${TMP_DIR}/robot-contact-assembly" "${TMP_DIR}/artifacts/preload_traces"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'artifacts/' \
  --exclude 'logs/' \
  --exclude 'videos/' \
  --exclude 'checkpoints/' \
  --exclude 'tmp/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${REPO_ROOT}/" "${TMP_DIR}/robot-contact-assembly/"

if [[ -s "${PRELOAD_TRACE}" ]]; then
  cp "${PRELOAD_TRACE}" "${TMP_DIR}/artifacts/preload_traces/$(basename "${PRELOAD_TRACE}")"
else
  echo "[launchable-bundle] warning: preload trace missing, bundle will not include it: ${PRELOAD_TRACE}" >&2
fi

COPYFILE_DISABLE=1 tar -C "${TMP_DIR}" --no-xattrs --exclude='._*' -czf "${OUT_PATH}" robot-contact-assembly artifacts

echo "[launchable-bundle] wrote ${OUT_PATH}"
echo "[launchable-bundle] upload/extract inside Launchable with:"
echo "  tar -xzf $(basename "${OUT_PATH}") -C /workspace"
