# 2026-05-17 Phase 2 Near-Success Diagnosis

## Goal

Diagnose the latest real-contact scripted failures without opening another GPU instance.

The question is whether the remaining blocker is:

- another scripted-controller threshold/polish tweak
- a socket pose / robot workspace constraint
- a contact-geometry or insertion-depth constraint
- a reason to stop scripted tuning and move to IL/RL or a simpler contact demo

## Inputs

The diagnosis uses the latest pulled scripted traces:

- `artifacts/evaluations/scripted/2026-05-17T05-43-13Z/seed_42_trace.json`
- `artifacts/evaluations/scripted/2026-05-17T06-08-13Z/seed_42_trace.json`
- `artifacts/evaluations/scripted/2026-05-17T16-51-25Z/seed_42_trace.json`
- `artifacts/evaluations/scripted/2026-05-17T17-21-50Z/seed_42_trace.json`

## Tool Added

Added:

- `scripts/analyze_near_success_windows.py`

The script reads one or more scripted trace JSON files and ranks candidate steps by:

- lateral error
- axial error
- rotation error
- current success tolerances
- contact force
- minimum joint-limit margin
- branch-jump state

It is intentionally offline-only and does not require Isaac Sim, Isaac Lab, or a GPU.

Validation:

```bash
python3 -m py_compile scripts/analyze_near_success_windows.py
```

Command:

```bash
python3 scripts/analyze_near_success_windows.py \
  artifacts/evaluations/scripted/2026-05-17T05-43-13Z/seed_42_trace.json \
  artifacts/evaluations/scripted/2026-05-17T06-08-13Z/seed_42_trace.json \
  artifacts/evaluations/scripted/2026-05-17T16-51-25Z/seed_42_trace.json \
  artifacts/evaluations/scripted/2026-05-17T17-21-50Z/seed_42_trace.json \
  --limit 10
```

## Key Results

Best simultaneous step across the inspected traces:

```text
run:     2026-05-17T16-51-25Z
step:    1273
phase:   insert
lateral: 0.0064 m
axial:   0.0372 m
rot:     0.2327 rad
contact: 21.2309
jlim:    0.0168 rad
jlim_i:  1
```

Current success gate:

```text
lateral <= 0.005 m
axial   <= 0.008 m
rot     <= 0.180 rad
```

Remaining gap at the best simultaneous step:

```text
extra lateral needed: 0.0014 m
extra axial needed:   0.0292 m
extra rotation needed:0.0527 rad
```

Near-seat statistics:

```text
Attempt 59 / 2026-05-17T06-08-13Z:
  near-seat steps (axial <= 0.05 m): 553
  near-seat steps with joint margin <= 0.02 rad: 500

Attempt 62 / 2026-05-17T16-51-25Z:
  near-seat steps (axial <= 0.05 m): 959
  near-seat steps with joint margin <= 0.02 rad: 894

Attempt 63 / 2026-05-17T17-21-50Z:
  near-seat steps (axial <= 0.05 m): 63
  near-seat steps with joint margin <= 0.02 rad: 47
  branch-jump steps: 483
```

The limiting joint in near-seat samples is usually joint index `1`, which repeatedly approaches the lower limit.

## Interpretation

The strongest trace evidence is not "we need one more polish threshold." It is that the controller reaches near-seat depth while the robot is already close to a joint limit.

The best near-contact windows show:

- good XY can be achieved independently
- good rotation can be achieved independently
- near-seat axial depth can be achieved independently
- the three conditions do not stay true at the same step
- near-seat steps repeatedly coincide with low joint-limit margin
- target-orientation polish near contact can trigger branch jumps and axial regression

This points to a workspace/contact/controller coupling problem:

- the current socket pose and insertion path likely put the Franka too close to a constrained joint configuration
- the guide socket/contact shell then amplifies small orientation or lateral corrections near the final 3-4 cm
- threshold-only scripted-controller tuning has reached diminishing returns

## Decision

Do not open another GPU instance for the current scripted polish branch.

Next useful work is local-first:

- use this diagnosis to pick a more reachable socket pose or easier first-demo geometry
- prefer changing socket pose / guide clearance / insertion depth before writing another polish variant
- once a physically reachable configuration is selected, run one cheap guarded scripted gate to verify `success_step != null`
- after one scripted success exists, move to contact-policy learning or imitation learning

## Candidate Next Experiment

A minimal next experiment should change the problem structure, not just controller thresholds:

```text
Option A: workspace-first socket pose
  Move the socket to a less joint-limit-heavy pose and keep the current controller.
  Success criterion: near-seat joint margin stays > 0.05 rad before final insertion.

Option B: geometry-first relaxed socket
  Temporarily increase guide clearance or reduce required insertion depth.
  Success criterion: get one true-contact scripted success, then tighten geometry.

Option C: controller-first lower-level final insertion
  Replace late Cartesian/JointIK polish with a fixed small joint-space descent generated before contact.
  Success criterion: no branch jump while axial error drops below 0.008 m.
```

Recommended next choice: Option A first. It is cheapest because it can be prepared locally and tested with one guarded L4 run.

## Prepared Next Gate

Added a one-instance socket-pose sweep:

- `scripts/run_remote_scripted_socket_sweep.sh`
- `scripts/run_phase2_workspace_socket_sweep_gate.sh`

The guarded wrapper uses:

```text
RCA_GATE_COMMAND=scripted_socket_sweep
RCA_GATE_TASK=RCA-PegInHole-Franka-JointPos-Contact-Play-v0
RCA_GATE_INSTANCE_TYPE=g2-standard-4:nvidia-l4:1
RCA_GATE_STEPS=1600
RCA_GATE_SEEDS=42
RCA_SOCKET_SWEEP_STOP_ON_SUCCESS=1
```

Default socket candidates:

```text
0.22,0.04,0.22
0.24,0.03,0.22
0.26,0.02,0.22
0.28,0.00,0.22
```

Rationale:

- the previous socket pose was `0.22,0.04,0.19`
- near-seat samples repeatedly ran joint index `1` close to its lower limit
- raising the socket by `3cm` reduces final descent demand
- moving gradually outward and toward the centerline tests whether the joint-limit bottleneck is pose-specific

Run command for the next paid test:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-workspace-socket-sweep-l4-r1 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_workspace_socket_sweep_gate.sh
```

Pass condition:

```text
any swept position produces success_step != null
```

Stop condition:

```text
if all four positions have success_step=null, stop and inspect the pulled traces locally before opening another GPU
```
