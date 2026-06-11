#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL="${RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL:-jointpos-rotate-descend-probe}"
export RCA_LAUNCHABLE_ROTATE_DESCENT_MODE="${RCA_LAUNCHABLE_ROTATE_DESCENT_MODE:-approach}"
export RCA_LAUNCHABLE_ROTATE_XY_RETENTION="${RCA_LAUNCHABLE_ROTATE_XY_RETENTION:-1}"
export RCA_LAUNCHABLE_ROTATE_XY_RETENTION_TOL="${RCA_LAUNCHABLE_ROTATE_XY_RETENTION_TOL:-0.012}"
export RCA_LAUNCHABLE_DESCEND_XY_RETENTION="${RCA_LAUNCHABLE_DESCEND_XY_RETENTION:-1}"
export RCA_LAUNCHABLE_DESCEND_XY_RETENTION_TOL="${RCA_LAUNCHABLE_DESCEND_XY_RETENTION_TOL:-0.012}"

# Isolate the phase/target change first; the previous paid run showed the joint-limit nullspace term
# did not activate under the current margins.
export RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_GAIN="${RCA_LAUNCHABLE_JOINT_LIMIT_NULLSPACE_GAIN:-0.000}"

exec "${SCRIPT_DIR}/run_launchable_phase2_jointpos_nullspace_probe.sh"
