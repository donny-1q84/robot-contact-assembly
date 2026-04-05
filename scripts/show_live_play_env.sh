#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "${SCRIPT_DIR}/send_live_app_script.py" "${SCRIPT_DIR}/live_visualize_play_env.py"
