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
