#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Do not source this script; execute it as a command." >&2
  return 2
fi

BREV_BIN="${RCA_BREV_CLI:-${BREV_BIN:-/Users/Shenghan/bin/brev}}"
AUTH_PROVIDER="${RCA_BREV_LOGIN_AUTH_PROVIDER:-nvidia}"
EMAIL="${RCA_BREV_LOGIN_EMAIL:-}"
SKIP_BROWSER="${RCA_BREV_LOGIN_SKIP_BROWSER:-0}"

args=(login --auth "${AUTH_PROVIDER}")
if [[ -n "${EMAIL}" ]]; then
  args+=(--email "${EMAIL}")
fi
if [[ "${SKIP_BROWSER}" == "1" ]]; then
  args+=(--skip-browser)
fi

echo "[brev-login] refreshing Brev/NVIDIA CLI auth"
echo "[brev-login] this command creates no paid resources"
"${BREV_BIN}" "${args[@]}"

echo "[brev-login] verifying Brev CLI auth with read-only instance list"
"${BREV_BIN}" ls instances --json --all >/dev/null
echo "[brev-login] PASS: Brev CLI auth is usable"
