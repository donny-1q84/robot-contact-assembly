# 2026-04-26 Phase 2 Contact Frame Fix

## Goal

Diagnose why the first direct-contact PPO baseline trained and evaluated end-to-end but never entered the insertion-progress region.

The key symptom from `phase2_contact_baseline_v2` was:

- `Episode_Reward/insertion_progress = 0.0000`
- `Episode_Reward/insertion_success = 0.0000`
- fixed eval `success_rate = 0.000`

## Finding

The direct-contact task had a frame-consistency bug before reward tuning should be trusted.

The constant named `PEG_TIP_BODY_OFFSET_ROT` was written in `xyzw` order:

```python
(0.0, 0.0, 0.41435253798529015, 0.9101164619240488)
```

Isaac Lab action offsets and math utilities use quaternion order `(w, x, y, z)`. The intended value is the yaw-only quaternion derived from `PEG_TIP_YAW_OFFSET_RAD`:

```python
(0.9101164619240488, 0.0, 0.0, 0.41435253798529015)
```

That matters because the same offset is used to:

- place the physical peg on the Franka hand
- compute the peg-tip pose
- define the relative IK action frame
- drive the scripted baseline toward the socket frame

With the old ordering, the physical peg frame and the controller target frame were not actually the same peg tip frame. The observed PPO failure can therefore not be cleanly interpreted as a reward-design failure yet.

## Changes

- corrected `PEG_TIP_BODY_OFFSET_ROT` to Isaac Lab `(w, x, y, z)` order
- passed both `pos` and `rot` to `DifferentialInverseKinematicsActionCfg.OffsetCfg`
- updated scripted and live scripted controllers so their action frame target is the socket frame directly, not a hand-frame compensation target
- updated live/scripted diagnostics to read the physical `socket_frame`
- added a local geometry check that verifies:
  - the quaternion matches `PEG_TIP_YAW_OFFSET_RAD`
  - the physical peg-tip offset reconstructed from the peg center equals `PEG_TIP_BODY_OFFSET_POS`

Local check:

```bash
python3 scripts/check_contact_geometry_constants.py
```

Result:

```text
[geometry-check] contact geometry constants are self-consistent
[geometry-check] tip_rot_wxyz=(0.9101164619240488, 0.0, 0.0, 0.41435253798529015)
[geometry-check] physical_tip_offset=(0.0, 0.0, 0.10340000000000002)
```

## Verification Completed Locally

No GPU was started for this fix.

Completed local checks:

```bash
python3 scripts/check_contact_geometry_constants.py
python3 -m py_compile \
  scripts/check_contact_geometry_constants.py \
  scripts/scripted_agent.py \
  scripts/live_step_scripted_baseline.py \
  scripts/debug_pose_alignment.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/constants.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/config/franka/ik_rel_env_cfg.py
git diff --check
```

## Next Remote Gate

Do not run another long PPO job first.

The next GPU session should only run a cheap gate:

```bash
RCA_SKIP_STREAM_STACK=1 ./scripts/install_remote_isaaclab_runtime.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose
```

```bash
./scripts/run_remote_scripted_eval.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose \
  RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0 \
  1 \
  240 \
  42 \
  600
```

Pass condition:

- scripted final lateral and axial errors improve from reset
- the controller reaches a lower final rotation error than the previous contact-shell scripted run
- `insertion_progress` is non-zero or the final pose is close enough to justify one short PPO smoke

Fail condition:

- final lateral or axial error still diverges strongly
- rotation remains around `~2 rad`
- contact forces push the peg out of the guide

If the gate fails, inspect socket-frame sign conventions and guide-wall placement before spending on PPO.

## 2026-05-15 Follow-up: Runtime Tip-to-Root Sync Fix

### New Symptom

The May 15 guarded absolute-IK gates showed a persistent mismatch between the scripted controller action frame and the physical peg-tip metric frame.

From `artifacts/evaluations/scripted/2026-05-15T12-27-38Z/seed_42_trace.json`:

- `action_to_physical_tip_delta_w` had a constant norm of about `0.0728 m`.
- The controller's internal lateral error briefly reached about `0.033 m`.
- The physical peg-tip lateral error never went below about `0.101 m`.
- The staged approach did not improve the result, so this was not primarily a trajectory staging problem.

### Root Cause Hypothesis

The previous sync event placed the physical peg root using a hand-authored center offset:

```python
PEG_CENTER_BODY_OFFSET_POS = (0.0, 0.0, PEG_TIP_BODY_OFFSET_POS[2] - 0.5 * PEG_LENGTH_M)
```

That passed the local constant check, but the remote trace proved the runtime action frame and physical peg-tip frame were still separated. The safer invariant is:

1. Compute the controller tip pose with the exact same offset used by the IK action term.
2. Derive the physical peg root from that tip pose.
3. Compute rewards, terminations, and metrics from the same physical tip.

### Changes

- Added `PEG_ROOT_FROM_TIP_POS` and `PEG_ROOT_FROM_TIP_ROT`.
- Updated `mdp.sync_peg_to_hand` so `body_offset` / `body_rot_offset` now describe the intended controller tip frame, not the peg center.
- The sync event now computes:
  - `tip_pose = hand_pose * controller_tip_offset`
  - `peg_root_pose = tip_pose * peg_root_from_tip_offset`
- Updated env event params to pass `PEG_TIP_BODY_OFFSET_*` and `PEG_ROOT_FROM_TIP_*`.
- Updated `scripts/scripted_agent.py` to report:
  - `initial_action_tip_alignment`
  - `final_action_tip_alignment`
  - `best_action_tip_alignment`
  - per-step `action_tip_alignment`
- Changed staged scripted gating to use physical `lateral_error` instead of controller-only lateral error for `xy_ready` and `insert_ready`.

### Local Verification

No GPU was started for this fix.

Completed checks:

```bash
python3 scripts/check_contact_geometry_constants.py
python3 -m py_compile \
  scripts/scripted_agent.py \
  scripts/check_contact_geometry_constants.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/constants.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/mdp/events.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/peg_in_hole_env_cfg.py
```

The old remote trace is still the baseline for comparison:

```text
old_trace_action_tip_alignment_norm_first = 0.0728093148
old_trace_action_tip_alignment_norm_last  = 0.0728092992
```

### Next Gate

The next GPU session should be a short L4 scripted gate only.

Primary pass condition:

- `best_action_tip_alignment < 0.005 m`

Secondary pass condition:

- physical `best_lateral` improves relative to Attempt 26's `0.1008 m`
- physical `best_axial` improves relative to Attempt 26's `0.0923 m`
- no PPO training unless the alignment metric is fixed first
