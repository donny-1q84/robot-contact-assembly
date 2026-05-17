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
- `scripts/summarize_socket_sweep_results.py`

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

After artifacts are pulled, summarize all swept results with:

```bash
python3 scripts/summarize_socket_sweep_results.py --since 2026-05-17T00-00-00Z
```

The ranking uses a simple near-success score based on best lateral, axial, and rotation errors. Lower is better; any `success_step != null` ranks above failed near-success runs.

## Socket Sweep Gate Attempt 1

Run:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-workspace-socket-sweep-l4-r1 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=1200 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_workspace_socket_sweep_gate.sh
```

Selected instance:

```text
name: isaac-phase2-workspace-socket-sweep-l4-r1
id:   3b5inj2j7
type: g2-standard-4:nvidia-l4:1
gpu:  NVIDIA L4, 23034 MiB
rate: $0.85/hr
```

Artifacts:

- `artifacts/gpu_gate/2026-05-17T18-09-44Z_isaac-phase2-workspace-socket-sweep-l4-r1/gate.log`
- `artifacts/evaluations/scripted/2026-05-17T18-25-39Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T18-25-39Z/seed_42_trace.json`

Result:

```text
socket:             0.220,0.040,0.220
success_step:       None
final_success_rate: 0.000
final_lateral:      0.0045 m
final_axial:        0.0449 m
final_rot:          0.1590 rad
best_lateral:       0.0003 m @ step 1045
best_axial:         0.0383 m @ step 1430
best_rot:           0.0494 rad @ step 899
max_contact_force:  3.6931
```

Summary command:

```bash
python3 scripts/summarize_socket_sweep_results.py --since 2026-05-17T18-09-44Z --limit 20
```

Interpretation:

- The raised socket-z candidate preserved the previous near-seat pattern: XY and rotation can both become good, but axial depth still stalls around `3.8-4.5 cm`.
- This run is not a full four-position sweep. It stopped after the first candidate because the sweep wrapper tried to parse remote JSON with `python3`, but the Isaac Sim task container exposes Isaac's Python at `/isaac-sim/python.sh`.
- Cleanup was verified after deletion with both Brev views:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Fix applied:

- `scripts/run_remote_scripted_socket_sweep.sh` now uses `RCA_REMOTE_CONTAINER_PYTHON` with default `/isaac-sim/python.sh` for remote success parsing.
- The parser failure path now warns and continues the sweep instead of aborting the guarded GPU session.

Next decision:

- The intended gate is still valid but incomplete. A rerun should complete the remaining socket candidates unless an actual scripted success appears first.
- If the full sweep still produces no success, stop paid runs again and inspect whether the first true success should come from relaxed insertion depth / guide clearance instead of more controller tuning.

## Socket Sweep Gate Attempt 2

Run:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-workspace-socket-sweep-l4-r2 \
RCA_GATE_INSTANCE_TYPE=g2-standard-4:nvidia-l4:1 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=1200 \
RCA_GATE_CREATE_TIMEOUT=600 \
RCA_SOCKET_SWEEP_POSITIONS='0.24,0.03,0.22;0.26,0.02,0.22;0.28,0.00,0.22' \
scripts/run_phase2_workspace_socket_sweep_gate.sh
```

Selected instance after live price comparison:

```text
name: isaac-phase2-workspace-socket-sweep-l4-r2
id:   xxucldahl
type: g2-standard-4:nvidia-l4:1
rate: $0.85/hr
```

Price rationale:

- cheapest visible 24GB+ candidate: `g2-standard-4:nvidia-l4:1` at `$0.85/hr`
- cheapest visible 32GB+ candidate: T4 pair at `$0.90/hr`
- cheapest visible 40GB+ candidate: L40S at `$1.86/hr`

The L4 was still the best value for a single-env scripted gate.

Artifacts:

- `artifacts/gpu_gate/2026-05-17T18-38-29Z_isaac-phase2-workspace-socket-sweep-l4-r2/gate.log`
- `artifacts/evaluations/scripted/2026-05-17T18-54-02Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T18-56-28Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T18-58-30Z/seed_42.json`

Summary:

```bash
python3 scripts/summarize_socket_sweep_results.py --since 2026-05-17T18-09-44Z --limit 20
```

Result table:

```text
socket             success  best_lateral       best_axial        best_rot        final_lateral  final_axial  final_rot
0.220,0.040,0.220 no       0.0003 @ 1045     0.0383 @ 1430    0.0494 @ 899    0.0045         0.0449       0.1590
0.240,0.030,0.220 no       0.0001 @ 828      0.0368 @ 1525    0.0608 @ 1107   0.0034         0.0399       0.2478
0.260,0.020,0.220 no       0.0089 @ 90       0.4756 @ 1598    0.2357 @ 360    0.0251         0.4758       0.2477
0.280,0.000,0.220 no       0.0051 @ 740      0.5212 @ 0       0.7413 @ 677    0.0190         0.7468       0.8057
```

Interpretation:

- The best swept candidate was `0.24,0.03,0.22`, but it still stalled around `3.7-4.0 cm` axial error.
- The original raised-z candidate `0.22,0.04,0.22` remains competitive and has the best final rotation.
- Moving farther outward/centerward (`0.26,0.02,0.22` and `0.28,0.00,0.22`) severely worsened insertion depth.
- The sweep disproves the simple hypothesis that the near-seat failure is solved by moving the socket outward/centerward.

Cleanup:

- The gate completed and pulled artifacts.
- Brev deletion briefly stalled through `DELETING`, `STOPPING`, `STOPPED`, and a transient `DEPLOYING` state.
- Final independent verification after cleanup:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Decision:

- Stop paid GPU runs for this scripted socket-pose branch.
- Do not continue tuning the same controller against the same insertion geometry.
- The next useful change should be a geometry-first first-success gate:
  - temporarily relax insertion depth from the current final success depth to a shallow contact success
  - or increase guide/socket clearance and then tighten it after one true-contact scripted success
  - keep the best pose candidates near `0.22-0.24 x`, `0.03-0.04 y`, `0.22 z`

## Local Relaxed Success Gate

After the full socket-pose sweep produced no strict success, I added an explicit scripted
success-gate override instead of changing the task constants:

- `scripts/scripted_agent.py`
- `scripts/analyze_relaxed_success_gate.py`
- `scripts/run_phase2_shallow_contact_success_gate.sh`

The default strict task gate is unchanged:

```text
lateral < 0.005 m
axial   < 0.008 m
rot     < 0.18 rad
```

The new override is only for a Phase 2 shallow-contact milestone. It can require:

- a relaxed axial threshold
- a relaxed rotation threshold
- a minimum measured peg contact force

This keeps the project honest: a shallow-contact success is not reported as final insertion
success, but it proves that the physical peg/socket/contact shell can reproducibly reach a
contacting near-seat state.

Local trace analysis:

```bash
python3 scripts/analyze_relaxed_success_gate.py \
  --since 2026-05-17T18-09-44Z \
  --xy-tol 0.005 \
  --z-tol 0.045 \
  --rot-tol 0.18 \
  --min-contact-force 0.5 \
  --limit 10
```

Result:

```text
passing steps: 0
closest: 0.22,0.04,0.22 at steps 1538-1539, axial ~= 0.042 m,
         contact force >= 0.5, but rot ~= 0.190 rad
```

Second local analysis:

```bash
python3 scripts/analyze_relaxed_success_gate.py \
  --since 2026-05-17T18-09-44Z \
  --xy-tol 0.005 \
  --z-tol 0.045 \
  --rot-tol 0.20 \
  --min-contact-force 0.5 \
  --limit 10
```

Result:

```text
passing steps: 2
socket: 0.22,0.04,0.22
step 1538: lateral 0.0047, axial 0.0419, rot 0.1909, contact 0.6927
step 1539: lateral 0.0039, axial 0.0421, rot 0.1899, contact 0.5728
```

Alternative deeper gate:

```bash
python3 scripts/analyze_relaxed_success_gate.py \
  --since 2026-05-17T18-09-44Z \
  --xy-tol 0.005 \
  --z-tol 0.040 \
  --rot-tol 0.25 \
  --min-contact-force 0.5 \
  --limit 10
```

Result:

```text
passing steps: 10
socket: 0.24,0.03,0.22
steps 1588-1599: axial ~= 0.0398-0.0399, contact force >= 0.5,
                 but rot ~= 0.236-0.248
```

Decision:

- Prefer the first shallow-contact milestone: `0.22,0.04,0.22`, `z < 0.045`, `rot < 0.20`, `contact >= 0.5`.
- It relaxes rotation only slightly beyond the strict gate and preserves the 5 mm lateral threshold.
- The next GPU run should be exactly one cheap guarded run:

```bash
scripts/run_phase2_shallow_contact_success_gate.sh
```

Expected outcome:

- If it reproduces `success_step != null`, archive it as "Phase 2 shallow true-contact success".
- Then tighten either axial depth or rotation one dimension at a time.
- Do not reopen the socket-pose sweep unless this one-shot gate fails unexpectedly.

## Shallow Contact Success Gate Result

Run:

```bash
scripts/run_phase2_shallow_contact_success_gate.sh
```

Selected instance after live price comparison:

```text
name: isaac-phase2-shallow-contact-success-l4
id:   n9iah3gp1
type: g2-standard-4:nvidia-l4:1
rate: $0.85/hr
```

Price rationale:

- cheapest visible 24GB+ / 500GB-disk candidate: `g2-standard-4:nvidia-l4:1` at `$0.85/hr`
- cheapest visible 32GB+ / 500GB-disk candidate: dual T4 at `$0.90/hr`
- cheapest visible 40GB+ / 500GB-disk candidate: L40S at `$1.86/hr`
- L4 was selected because the previous gates already proved this runtime path works, while cheaper single-T4 options do not meet the 24GB VRAM floor.

Artifacts:

- `artifacts/gpu_gate/2026-05-17T19-32-40Z_isaac-phase2-shallow-contact-success-l4/gate.log`
- `artifacts/gpu_gate/2026-05-17T19-32-40Z_isaac-phase2-shallow-contact-success-l4/gate_metadata.env`
- `artifacts/evaluations/scripted/2026-05-17T19-47-06Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T19-47-06Z/seed_42.log`
- `artifacts/evaluations/scripted/2026-05-17T19-47-06Z/seed_42_trace.json`

Result:

```text
success_step: 1538
final_success_rate: 1.0
socket_pos_override: [0.22, 0.04, 0.22]
active_success_xy_tolerance: 0.005
active_success_z_tolerance: 0.045
active_success_rot_tolerance: 0.2
success_min_contact_force: 0.5
final_lateral: 0.0046655913 m
final_axial:   0.0418793261 m
final_rot:     0.1909276992 rad
best_lateral:  0.0003210883 m @ step 1045
best_axial:    0.0383484066 m @ step 1430
best_rot:      0.0494016446 rad @ step 899
max_contact:   3.6930987835 @ step 1315
```

Cleanup:

```text
brev ls instances --all:       No instances in org NCA-57cf-29515
brev ls instances --json --all: { "workspaces": null }
```

Interpretation:

- This is the first reproducible Phase 2 true-contact success milestone.
- It is not final strict peg-in-hole success, because the final axial tolerance is relaxed from `0.008 m` to `0.045 m`.
- The contact shell is now validated: physical peg, socket guide, contact sensing, fixed-seed scripted controller, artifact pullback, and guarded cleanup all work.
- The remaining technical problem is tightening the gate from shallow contact to strict insertion.

Next tightening order:

1. Keep `socket_pos=0.22,0.04,0.22`, `xy < 0.005`, `contact >= 0.5`.
2. Tighten rotation from `0.20` back to `0.18` while keeping `z < 0.045`.
3. Tighten axial depth gradually from `0.045 -> 0.035 -> 0.025 -> 0.015 -> 0.008`.
4. Only after strict scripted success exists, move to RL/IL on the contact environment.

## Rotation Tightening Gate Plan

Local check against the shallow-success trace:

```bash
python3 scripts/analyze_relaxed_success_gate.py \
  artifacts/evaluations/scripted/2026-05-17T19-47-06Z/seed_42_trace.json \
  --xy-tol 0.005 \
  --z-tol 0.045 \
  --rot-tol 0.18 \
  --min-contact-force 0.5 \
  --limit 10
```

Result:

```text
passing steps: 0
closest step: 1538
lateral: 0.0047 m
axial:   0.0419 m
rot:     0.1909 rad
contact: 0.6927
```

Diagnosis:

- The next strict-rotation gate misses by only `0.0109 rad`.
- The current shallow-success script uses `--polish-rotation-mode current`, so near-contact polish intentionally freezes orientation and cannot remove that residual.
- The next gate should change only near-contact rotation control, not socket pose or axial depth.

Added:

- `scripts/run_phase2_rotation_tight_contact_gate.sh`

Gate definition:

```text
socket_pos: 0.22,0.04,0.22
success_xy_tolerance: 0.005
success_z_tolerance:  0.045
success_rot_tolerance: 0.18
success_min_contact_force: 0.5
polish_rotation_mode: target
polish_rot_gain: 0.35
polish_rot_clamp: 0.012
```

This is a single-hypothesis run: mild target-orientation polish should remove the final
rotation residual without reopening a broad parameter sweep.

## Rotation Tightening Gate Result

Run:

```bash
scripts/run_phase2_rotation_tight_contact_gate.sh
```

Selected instance after live price comparison:

```text
name: isaac-phase2-rotation-tight-contact-l4
id:   x544blsp0
type: g2-standard-4:nvidia-l4:1
rate: $0.85/hr
```

Artifacts:

- `artifacts/gpu_gate/2026-05-17T20-02-23Z_isaac-phase2-rotation-tight-contact-l4/gate.log`
- `artifacts/gpu_gate/2026-05-17T20-02-23Z_isaac-phase2-rotation-tight-contact-l4/gate_metadata.env`
- `artifacts/evaluations/scripted/2026-05-17T20-18-33Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T20-18-33Z/seed_42.log`
- `artifacts/evaluations/scripted/2026-05-17T20-18-33Z/seed_42_trace.json`

Result:

```text
success_step: None
final_success_rate: 0.0
socket_pos_override: [0.22, 0.04, 0.22]
active_success_xy_tolerance: 0.005
active_success_z_tolerance: 0.045
active_success_rot_tolerance: 0.18
success_min_contact_force: 0.5
final_lateral: 0.0039495630 m
final_axial:   0.3297291100 m
final_rot:     2.1501812935 rad
best_lateral:  0.0003210883 m @ step 1045
best_axial:    0.0390089452 m @ step 1416
best_rot:      0.0494016446 rad @ step 899
```

Closest strict-rotation shallow-contact step:

```text
step: 1251
phase: insert
lateral: 0.0050 m
axial:   0.0421 m
rot:     0.2597 rad
contact: 2.1943
```

Failure mode:

- The run reached shallow axial depth and maintained real contact, but the best near-seat orientation was worse than the previous `current`-rotation shallow success.
- `--polish-rotation-mode target` did not remove the last residual; it drove the controller into a joint-limit-constrained near-contact region.
- A branch jump started at step `1468` with lateral `0.0053 m`, axial `0.0614 m`, rotation `0.7587 rad`, contact `0.2171`, and joint margin `0.0033 rad`.
- After the branch jump, the controller backed out axially and rotation diverged, so this configuration is a dead end for tightening the success gate.

Cleanup:

```text
brev ls instances --all:       No instances in org NCA-57cf-29515
brev ls instances --json --all: { "workspaces": null }
```

Interpretation:

- The previous shallow true-contact milestone remains valid.
- Rotation-tightening by simply switching near-contact polish from `current` orientation hold to `target` orientation correction is rejected.
- The bottleneck is not a missing threshold tweak; the controller is operating at very low joint margin near the socket, so extra rotation correction can trigger branch jumps.

Next technical direction:

1. Do not keep sweeping `polish_rot_gain` / `polish_rot_clamp` around this same target-rotation setup.
2. Keep the successful shallow-contact script as the baseline.
3. Before the next paid run, change the controller structure so rotation correction happens before axial seating, or change the socket pose / approach pose to recover joint margin.
4. The next GPU run should only happen after local trace analysis identifies a single concrete controller change, not another broad parameter sweep.

Added follow-up gate:

- `scripts/run_phase2_rotation_strict_passive_contact_gate.sh`

Hypothesis:

- The previous shallow-contact success terminated immediately at `rot=0.1909` because the active success gate was `rot < 0.20`.
- Reusing the stable `current` orientation-hold controller, tightening only `success_rot_tol` to `0.18`, and extending the horizon to `1900` steps tests whether passive/contact dynamics can remove the last `0.0109 rad` without the target-rotation branch jump.
- This is intentionally a one-variable validation, not a new gain sweep.

## Passive Strict-Rotation Gate Result

Run:

```bash
scripts/run_phase2_rotation_strict_passive_contact_gate.sh
```

Selected instance after live price comparison:

```text
name: isaac-phase2-rotation-strict-passive-l4
id:   2hiuugdh2
type: g2-standard-4:nvidia-l4:1
rate: $0.85/hr
```

Artifacts:

- `artifacts/gpu_gate/2026-05-17T20-37-24Z_isaac-phase2-rotation-strict-passive-l4/gate.log`
- `artifacts/gpu_gate/2026-05-17T20-37-24Z_isaac-phase2-rotation-strict-passive-l4/gate_metadata.env`
- `artifacts/evaluations/scripted/2026-05-17T20-54-06Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T20-54-06Z/seed_42.log`
- `artifacts/evaluations/scripted/2026-05-17T20-54-06Z/seed_42_trace.json`

Result:

```text
success_step: None
final_success_rate: 0.0
socket_pos_override: [0.22, 0.04, 0.22]
active_success_xy_tolerance: 0.005
active_success_z_tolerance: 0.045
active_success_rot_tolerance: 0.18
success_min_contact_force: 0.5
final_lateral: 0.0010634502 m
final_axial:   0.0627473295 m
final_rot:     0.2161971629 rad
best_lateral:  0.0003210883 m @ step 1045
best_axial:    0.0383484066 m @ step 1430
best_rot:      0.0494016446 rad @ step 899
```

Closest strict-contact step:

```text
step: 1539
phase: polish
lateral: 0.0039 m
axial:   0.0421 m
rot:     0.1899 rad
contact: 0.5728
```

Best geometric strict-rotation step:

```text
step: 1585
phase: settle
lateral: 0.0045 m
axial:   0.0421 m
rot:     0.1696 rad
contact: 0.0401
```

Cleanup:

```text
brev ls instances --all:       No instances in org NCA-57cf-29515
brev ls instances --json --all: { "workspaces": null }
```

Interpretation:

- Passive continuation avoided branch jumps, unlike the target-rotation run.
- It did reduce rotation below `0.18 rad`, but only after losing contact force.
- With contact retained (`contact >= 0.5`), the best step was still `rot=0.1899`, missing by `0.0099 rad`.
- The remaining issue is therefore not rotation alone. It is contact retention during the settle/polish transition.

Next technical direction:

1. Stop running paid GPU gates around pure rotation tolerance.
2. Implement a contact-retention settle mode that keeps a small downward/axial preload when `xy/z/rot` are geometrically ready but contact force drops below threshold.
3. Keep branch-jump prevention from the passive run: no target-rotation polish in contact.
4. The next GPU run should validate only the new contact-retention settle behavior.

## Contact-Retention Gate Prepared

Change:

- Added `--settle-contact-retention` to `scripts/scripted_agent.py`.
- Added `scripts/run_phase2_contact_retention_gate.sh`.
- The gate keeps the stable shallow-contact controller and changes one thing only: once the rollout satisfies strict geometry (`xy<5mm`, `z<45mm`, `rot<0.18rad`) but contact force is below `0.5`, it latches a contact-retention mode and keeps a small downward preload instead of returning to Z-hold polish.

Why this is the right next gate:

- The passive strict-rotation run already proved that target-rotation polish is destabilizing.
- The same run also proved that strict geometry is reachable: step `1585` had `xy=0.0045m`, `z=0.0421m`, `rot=0.1696rad`.
- The only missing term at that point was contact force: `0.0401 < 0.5`.
- A replay-style check against the previous trace indicates the new retention logic would first latch around step `1580` and remain active until about step `1654`, exactly around the observed contact-loss window.

Planned validation:

```bash
scripts/run_phase2_contact_retention_gate.sh
```

Pass condition:

- `success_step` is not `null` under `xy<0.005`, `z<0.045`, `rot<0.18`, `contact>=0.5`.

Fail condition:

- If geometry remains good but contact still stays below `0.5`, the next fix should move from Cartesian preload to force-aware/action-space contact control.
- If contact is retained but lateral/rotation exits the gate, the preload is too aggressive or the contact-retention exit window is too loose.

## Contact-Retention Gate Result

Run:

```bash
scripts/run_phase2_contact_retention_gate.sh
```

Selected instance after live price comparison:

```text
name: isaac-phase2-contact-retention-l4
id:   nxe4vsi03
type: g2-standard-4:nvidia-l4:1
rate: $0.85/hr
```

Artifacts:

- `artifacts/gpu_gate/2026-05-17T21-18-12Z_isaac-phase2-contact-retention-l4/gate.log`
- `artifacts/gpu_gate/2026-05-17T21-18-12Z_isaac-phase2-contact-retention-l4/gate_metadata.env`
- `artifacts/evaluations/scripted/2026-05-17T21-33-46Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-17T21-33-46Z/seed_42.log`
- `artifacts/evaluations/scripted/2026-05-17T21-33-46Z/seed_42_trace.json`

Result:

```text
success_step: None
final_success_rate: 0.0
final_lateral: 0.0010658705 m
final_axial:   0.0628007948 m
final_rot:     0.2190350294 rad
best_lateral:  0.0003210883 m @ step 1045
best_axial:    0.0383484066 m @ step 1430
best_rot:      0.0494016446 rad @ step 899
max_contact:   3.6930987835 @ step 1315
```

Strict gate:

```text
xy < 0.005
z < 0.045
rot < 0.18
contact >= 0.5
passing steps: 0
```

Closest strict-contact step:

```text
step: 1539
phase: polish
lateral: 0.0039 m
axial:   0.0421 m
rot:     0.1899 rad
contact: 0.5728
```

Contact-retention behavior:

```text
active steps: 12
first active: step 1581, phase settle, lateral 0.0018, axial 0.0435, rot 0.1786, contact 0.0033
last active:  step 1592, phase contact-retention, lateral 0.0080, axial 0.0410, rot 0.1541, contact 0.0313
```

Cleanup:

```text
brev ls instances --all:       No instances in org NCA-57cf-29515
brev ls instances --json --all: { "workspaces": null }
```

Interpretation:

- The implementation works mechanically: contact-retention latched and the trace records the new phase.
- The hypothesis was too late. It waited for strict rotation (`rot < 0.18`) and low contact before latching, so the first active step happened after contact had already collapsed from `~0.57-0.69` to `0.0033`.
- Once contact was lost, a small Cartesian downward preload did not restore it.
- The useful window is earlier: step `1538` already satisfies `xy<0.005`, `z<0.045`, `rot<0.20`, and `contact>=0.5`.

Next technical direction:

1. Do not rerun the same contact-retention gate.
2. Try an early-retention gate that latches at `rot<0.20` and ignores contact force for entry, while keeping the strict success gate unchanged.
3. If early retention still cannot keep contact, move away from scripted Cartesian preload and implement force-aware/action-space contact control.

Prepared script:

```bash
scripts/run_phase2_early_contact_retention_gate.sh
```
