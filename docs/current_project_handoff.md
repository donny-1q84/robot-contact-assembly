# Current Project Handoff

Date: 2026-06-09

## Repository State

- Repo path: `/Volumes/Extreme Pro/Projects/robot-contact-assembly`
- Branch: `master`
- Remote: `https://github.com/donny-1q84/robot-contact-assembly.git`
- Latest checked commit: `8d9b3d8 Record Nebius probe lifecycle failure`
- Local tree now contains uncommitted Launchable compatibility fixes, runbook updates, and helper scripts.

## What This Project Is

This is an Isaac Lab peg-in-hole contact assembly project around a Franka Panda. Phase 1 was a proxy pose-target task. Phase 2 converted the task into a physical peg/socket contact shell with explicit peg geometry, guide-wall socket collisions, socket-frame insertion metrics, and contact-force sensing.

The current technical problem is final contact stabilization: the scripted controller can reach a shallow true-contact success and a strict near miss, but it cannot robustly maintain the final contact state under the strict gate.

## Audit Decision After 2026-06-09 Review

After reviewing the full repo, controller implementation, Launchable wrappers, cost guard scripts, and all local result archives, the next step should not be another broad sweep or another rot-polish variant. The one remaining scripted-controller candidate was:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
```

This was a one-shot validation candidate, not a new sweep family. It inherited the best prior Launchable branch (`softgated`) and only tightened the rotation gate near insertion depth. The reason was specific: the best Launchable result reached XY/Z/contact readiness and missed only rotation, while both later rot-polish runs made selected/final rotation worse.

Paid validation on 2026-06-09 completed and failed closed:

```text
instance: rca-neardepth-rotgate-vm / 5x0dmseey
provider/type: AWS g6e.xlarge L40S
smoke/runtime: passed
probe: 2026-06-09T06-45-39Z_jointpos-reachable-jointlimit-guard-neardepth-rotgate-probe
status: fail_closed
selected: step=1763 phase=align lateral=0.001235 axial=0.049536 rot=0.350150 contact=0.500092 strict_miss=2.155097
final: lateral=0.002205 axial=0.060102 rot=0.313013 success_rate=0.0
best: lateral=0.000371@1236 axial=0.047266@1760 rot=0.171399@98
tail: lateral=0.002955 axial=0.061385 rot=0.262909 contact=0.070176
limiter: panda_joint4 min_margin=0.096164 at step 1766
diagnosis: tail post-action movement makes little progress along the requested XY command
cleanup: artifacts copied; delete confirmed; final Brev list returned {"workspaces": null}
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.txt
```

Do not rerun unchanged or threshold-sweep these closed branches:

```text
softgated
rotpolish
adaptive rotpolish
near-depth rotgate
Abs IK/root/current/target/posture/solver/offset/no-wall variants
preload-direction historical replay
reachable-approach / tuned guard / hard rotgate unchanged
```

The near-depth probe also failed closed, so stop scripted-controller tuning in this branch. The next useful work is a different formulation: final-contact policy/data collection, a new posture/branch objective before insertion, or a controller that explicitly optimizes axis alignment and contact stability together.

Local follow-up after the paid run: `scripts/analyze_contact_demo_coverage.py` now accepts Launchable result `.tar.gz` archives directly. A combined audit of local scripted traces plus Launchable archives is saved at:

```text
artifacts/reports/contact_demo_coverage_with_launchable_2026-06-09.md
artifacts/reports/contact_demo_coverage_with_launchable_2026-06-09.json
```

Combined audit result:

```text
traces: 38
steps: 52947
target-gate passing steps: 0
traces with target-gate steps: 0
near-contact steps: 3773
traces with near-contact steps: 18
```

This confirms that the existing data is diagnostic/near-contact data, not a strict-success demonstration set. Do not train or pay for another ordinary one-step BC run expecting strict insertion success from these labels.

Next local formulation artifact prepared after that audit:

```text
scripts/select_final_contact_reset_candidates.py
artifacts/reports/final_contact_reset_candidates_2026-06-09.md
artifacts/reports/final_contact_reset_candidates_2026-06-09.json
```

This selector reads local traces plus Launchable result archives and classifies candidate reset/handoff states. Current manifest:

```text
candidates: 64
target_gate_success: 0
strict_near_miss: 8
rotation_only_miss: 29
depth_contact_rotation_conflict: 3
near_contact: 15
low_rot_no_contact: 9
```

Best reset seeds:

```text
2026-05-17T23-32-18Z step 1543 contact-retention miss=0.0320 lateral=0.0052 axial=0.0413 rot=0.1812 contact=0.5298
2026-05-17T22-00-19Z step 1541 contact-retention miss=0.0421 lateral=0.0043 axial=0.0412 rot=0.1842 contact=0.5263
```

Interpretation: these are good reset/handoff seeds for a final-contact stabilizer or reset-based RL/IL formulation, but they are not positive strict-success labels. The next implementation should consume this manifest to build a final-contact reset/evaluation path or generate new success-bearing demonstrations from these seeds.

Evaluator support prepared after the manifest:

```text
scripts/evaluate_contact_bc_policy.py
  --preload-candidate-json
  --preload-candidate-category
  --preload-candidate-index
```

The evaluator can now load a candidate from the manifest, set `--preload-trace-json` and `--preload-trace-end-step` automatically, and replay either a normal trace path or a Launchable `archive.tar.gz::member_trace.json` reference. This makes the manifest actionable for future final-contact stabilizer checks without manually copying trace paths.

Example command shape inside an Isaac runtime:

```bash
python3 scripts/evaluate_contact_bc_policy.py \
  --controller current-joint \
  --preload-candidate-json artifacts/reports/final_contact_reset_candidates_2026-06-09.json \
  --preload-candidate-category strict_near_miss \
  --preload-candidate-index 0 \
  --steps 400 \
  --deterministic-reset
```

This is only an evaluator preload convenience. It is not a new recommended paid run by itself.

Candidate-window dataset prepared locally:

```text
script: scripts/extract_final_contact_candidate_dataset.py
dataset: artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.jsonl
metadata: artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.metadata.json
samples: 3188
observation_mode: temporal-history
history_steps: 2
observation_dim: 77
action_dim: 7
action_mode: residual-current
strict_success_samples: 0
active_success_samples: 1
candidate windows: 40
category sample counts:
  strict_near_miss: 608
  rotation_only_miss: 2337
  depth_contact_rotation_conflict: 243
```

This dataset is useful as a stabilization prior or reset-window dataset around known hard final-contact states. It is not a positive final-success BC dataset because it still has zero strict-success samples.

Local training attempt:

```bash
python3 scripts/train_contact_bc_policy.py \
  --dataset artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.jsonl \
  --output artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt \
  --epochs 120 \
  --batch-size 256 \
  --hidden-dim 128 \
  --layers 3 \
  --device cpu
```

Result: not run locally because the host Python environment does not have PyTorch installed. The dataset is ready; checkpoint training needs the Isaac/PyTorch runtime.

Remote/runtime wrappers prepared for that next step:

```text
scripts/run_remote_train_final_contact_candidate_bc.sh
scripts/run_remote_eval_final_contact_candidate_bc.sh
```

These wrappers do not create Brev instances. They assume an existing Isaac/PyTorch runtime, sync the repo plus the required dataset/manifest artifacts, and run the existing train/eval entrypoints with reproducible defaults.

Training command shape:

```bash
scripts/run_remote_train_final_contact_candidate_bc.sh \
  <env-name> \
  <remote-root> \
  <remote-compose-root>
```

Default output:

```text
/workspace/artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt
```

Evaluation command shape after the checkpoint exists:

```bash
scripts/run_remote_eval_final_contact_candidate_bc.sh \
  <env-name> \
  <remote-root> \
  <remote-compose-root>
```

Default evaluation uses:

```text
controller: bc
candidate manifest: /workspace/artifacts/reports/final_contact_reset_candidates_2026-06-09.json
candidate category: strict_near_miss
candidate index: 0
checkpoint: /workspace/artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt
```

For a deterministic baseline from the same manifest seed, set:

```bash
RCA_FINAL_CONTACT_BC_CONTROLLER=current-joint \
scripts/run_remote_eval_final_contact_candidate_bc.sh <env-name> <remote-root> <remote-compose-root>
```

## Best Robotics Results

Shallow true-contact success:

```text
run: 2026-05-17T19-47-06Z
success_step: 1538
lateral: 0.0047 m
axial: 0.0419 m
rot: 0.1909 rad
contact: 0.6927
gate: xy<0.005, z<0.045, rot<0.20, contact>=0.5
```

Closest strict near miss:

```text
run: 2026-05-17T23-32-18Z
step: 1543
lateral: 0.0052 m
axial: 0.0413 m
rot: 0.1812 rad
contact: 0.5298
strict gate: xy<0.005, z<0.045, rot<0.18, contact>=0.5
miss: about 0.20 mm lateral and 0.0012 rad rotation
```

## Learned Policy Status

The BC/IL pipeline works end to end:

```text
scripted trace JSON -> dataset JSONL -> MLP checkpoint -> staged handoff eval -> pulled artifacts
```

But all one-step BC variants tested so far failed as contact stabilizers:

```text
all-trace BC:
  success_step: null
  near_contact_fraction: 0.0000
  best_strict_miss_score: 21.0692

best-window staged BC:
  success_step: null
  handoff_miss: 0.0319
  near_contact_fraction: 0.0125
  best_after_bc: 0.1865

near-contact residual-current BC:
  success_step: null
  handoff_miss: 0.0319
  near_contact_fraction: 0.0175
  longest_near_contact_streak: 6
  final_delta_vs_handoff: +45.5555
```

The current trace archive is not a final insertion success dataset:

```text
mainline JointPos traces: 18
near-contact steps: 3227
strict/target-gate passing steps: 0
```

Prepared but not yet run:

```text
artifacts/datasets/phase2_contact_bc_near_contact_temporal_residual_current/
samples: 3187
observation_dim: 77
action_dim: 7
observation_mode: temporal-history
history_steps: 2
```

Do not run the temporal BC smoke until either the data contains better sustained post-contact labels or there is a specific reason to test the temporal formulation despite the current label limitation.

## Deterministic Handoff Baselines

Completed:

```text
controller: current-joint
run: 2026-05-20T19-52-13Z_current-joint
success_step: null
near_contact_fraction: 0.0000
longest_near_contact_streak: 0
final_delta_vs_handoff: +58.8510
```

This means the handoff state is not passively stable.

Attempted but no robotics result:

```text
controller: last-preload-action
run dir: artifacts/gpu_gate/2026-05-20T20-02-49Z_isaac-phase2-contact-handoff-last-action-l4
status: Brev provisioning abort before SSH / Isaac / eval
```

Prepared but no robotics result:

```text
controller: preload-direction
script: scripts/run_phase2_contact_handoff_preload_direction_gate.sh
run dir: artifacts/gpu_gate/2026-05-20T20-30-57Z_isaac-phase2-contact-handoff-preload-dir-l4
status: Brev provisioning abort before SSH / Isaac / eval
```

This `preload-direction` line is now superseded by the later Launchable evidence. Do not run the historical replay/preload-direction family as the next robotics evaluation unless there is a deliberate replay-drift diagnostic.

## Brev / Compute Status

Brev support email sent:

```text
to: brev-support@nvidia.com
subject: Follow-up: repeated probe-only Brev lifecycle failures in org NCA-57cf-29515
sent id: 19e4e182e6100df1
```

Brev support replied on 2026-05-22:

- They confirmed no active instances, hidden workspaces, deployments, volumes, or other billable resources remained in org `NCA-57cf-29515`.
- They said GCP instance creation was working on their side.
- They interpreted the GCP issue as missing required port opening for Isaac Sim video streaming.
- They said Nebius does not provide native port-opening through the platform and suggested configuring ports manually with `ufw`.
- They recommended the official Isaac Launchable, preferably on AWS.

Weekly Brev summary received on 2026-05-24:

```text
credits remaining: $21.88
currently running instances: none
weekly cost May 17-24: $11.86
storage fees may still apply
```

Current local Brev CLI status:

```text
2026-05-24: CLI login was restored for org NCA-57cf-29515 during the probe.
2026-05-24 later: CLI login was restored again for the official AWS Launchable run and was used to upload patches, pull diagnostics, and delete the paid instance.
```

Post-probe resource checks on 2026-05-24:

```text
/Users/Shenghan/bin/brev ls instances --all
  No instances in org NCA-57cf-29515

/Users/Shenghan/bin/brev ls instances --json --all
  {"workspaces": null}
```

## Important Compute Interpretation

The previous probe-only wrappers aborted because `brev ls instances --all` stayed at:

```text
RUNNING / BUILDING / NOT READY
```

even after `brev create` printed:

```text
<instance-name>: Ready
```

The wrapper did not attempt SSH until `brev ls` showed `RUNNING / COMPLETED / READY`.

Implemented on 2026-05-24:

```bash
scripts/run_brev_probe_direct_ssh_gate.sh
```

This wrapper is still probe-only. It sets `RCA_GATE_DIRECT_SSH_AFTER_CREATE_READY=1`, shortens the list-readiness grace window, runs `brev refresh`, and tries direct SSH / `nvidia-smi` before declaring failure. Keep deletion guards strict.

Probe result after login on 2026-05-24:

```text
run dir: artifacts/gpu_gate/2026-05-24T14-42-53Z_isaac-probe-direct-ssh-l4
selected instance type: g2-standard-4:nvidia-l4:1
result: failure before SSH
failure point: Brev CreateWorkspace API returned unexpected EOF
cleanup: confirmed no visible instances after delete
final plain list: no instances in org NCA-57cf-29515
final JSON list: {"workspaces": null}
```

This did not reach the support-described "instance exists but ports are missing" state. It failed earlier at Brev's workspace creation API, so repeating Isaac jobs through the same Brev path is not currently justified.

Follow-up sent to Brev support on 2026-05-24:

```text
gmail message id: 19e5a76b4bfa654c
thread id: 19e4e182e6100df1
attachment: artifacts/gpu_gate/2026-05-24T14-42-53Z_isaac-probe-direct-ssh-l4/gate.log
summary: reported the post-login direct-SSH probe failure at CreateWorkspace unexpected EOF before SSH/Isaac/ports, and asked support to investigate the org/CLI create API path and reconfirm no hidden billable resources.
```

## AWS Isaac Launchable Attempts

Official AWS Launchable was tested on 2026-05-24 after Brev support recommended it:

```text
instance name: isaac-launchable-13e30f
instance id: c7hq6t3hp
provider: AWS
region shown by UI: Columbus, OH, USA
ip shown by UI: 3.148.248.184
machine: g6e.4xlarge
gpu: NVIDIA L40S, 44.70 GiB shown by UI / 46068 MiB from nvidia-smi
cpus/ram/disk: 16 CPUs / 128 GiB RAM / 256 GiB disk
price shown by UI: $3.64/hr
launchable setup: Running / Built / script Completed
deleted: 2026-05-24 18:05 CEST from the Brev UI after diagnostics were pulled
post-delete UI check: after page reload, the Environments list showed the "Create your first environment" empty state
```

The first instance proved that the official Launchable could bring up Isaac Sim, Isaac Lab, the containers, and the GPU, but exposed Isaac Lab 2.3 compatibility issues in the RCA code and smoke harness.

First-instance local bundle and diagnostics:

```text
bundle uploaded:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T14-53-58Z.tar.gz
latest local bundle after watchdog/AppLauncher diagnostics patch:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-11-12Z.tar.gz
latest local bundle after interval fix and diagnostic matrix:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-18-29Z.tar.gz
diagnostics pulled:
  artifacts/launchable_logs/rca-launchable-diagnostics-20260524.tar.gz
contains:
  headless_smoke_retry.log
  Isaac Sim Kit log kit_20260524_155616.log
```

Second AWS Launchable run on 2026-05-24:

```text
instance name: isaac-launchable-5c7e93
instance id: kkekc4hjq
provider: AWS
machine: g6e.4xlarge
gpu: NVIDIA L40S, 46068 MiB from nvidia-smi
price shown by UI: about $3.61/hr
uploaded bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-18-29Z.tar.gz
latest local bundle after final Launchable fixes/docs:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-51-46Z.tar.gz
latest local bundle after fresh-preload workflow:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-06-50Z.tar.gz
latest local bundle after fresh-preload guardrails:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-13-11Z.tar.gz
latest local bundle after historical-replay fail-closed guard:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-14-14Z.tar.gz
latest local bundle after Abs IK probe summary wiring:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T09-24-27Z.tar.gz
latest local bundle after root-frame Abs IK action fix:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-29-24Z.tar.gz
latest local bundle after Abs IK orientation-current diagnostic wiring:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
latest local bundle after native MDP arm-joint-limit trace wiring:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T13-27-35Z.tar.gz
diagnostics pulled:
  artifacts/launchable_logs/rca-launchable-diagnostics-kkekc4hjq.tar.gz
deleted:
  2026-05-24 after diagnostics were pulled; CLI deletion by name and id completed after Brev showed DELETING for several minutes
post-delete check:
  /Users/Shenghan/bin/brev ls instances --all -> No instances in org NCA-57cf-29515
  /Users/Shenghan/bin/brev ls instances --json --all -> {"workspaces": null}
remote project path:
  /workspace/robot-contact-assembly
preload trace:
  /workspace/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json
```

The official warmup Kit process initially held GPU memory and a Kit database lock; after it exited/was killed, GPU memory returned to 0 MiB and the RCA tests ran cleanly.

Isaac Lab 2.3 / Isaac Sim 5.1 compatibility fixes applied:

```text
scripts/zero_agent.py
scripts/evaluate_contact_bc_policy.py
```

These now fall back to `isaaclab.app.AppLauncher` / `parse_env_cfg` if the newer `isaaclab_tasks.utils` launcher helpers are unavailable, and avoid importing the RCA task before `SimulationApp` starts.

Additional fixes after the first Launchable attempt:

```text
source/robot_contact_assembly_tasks/.../peg_in_hole_env_cfg.py
  sync_peg_each_step interval changed from (0.0, 0.0) to sim.dt * decimation.

source/robot_contact_assembly_tasks/.../mdp/events.py
  sync_peg_to_hand now accepts Isaac Lab fields that are already torch.Tensor and only calls warp.to_torch() for non-torch data.

scripts/zero_agent.py
  missing SimulationContext.visualizers is handled in headless Launchable smoke.
  SystemExit during env/simulation close is ignored after logging, so real Python exceptions remain visible.

scripts/run_launchable_headless_smoke.sh
scripts/run_launchable_rca_diagnostic_matrix.sh
scripts/run_launchable_phase2_preload_direction.sh
  marker checks were added so reset/step/summary evidence is required; a misleading zero exit code is not enough.
```

Why: Isaac Lab's EventManager handles `interval` terms by subtracting the environment `dt` and firing terms whose sampled interval has elapsed. A zero interval therefore fires every manager call and leaves no positive countdown. The RCA term also writes the kinematic peg pose to simulation each time, so the safer equivalent is to use the actual environment-step period.

Marker-checked smoke result:

```text
command:
  ./scripts/run_launchable_headless_smoke.sh
task:
  RCA-PegInHole-Franka-JointPos-Contact-Play-v0
status:
  passed
markers:
  Environment reset completed
  Zero-agent step 10/10 completed
  Zero agent smoke test completed
log:
  launchable_logs/headless_smoke_marker_checked.log
```

Diagnostic matrix result:

```text
run: 2026-05-24T16-46-41Z_rca_smoke_matrix
00_builtin_reach_franka: 0
10_rca_ik_rel_play: 0
20_rca_jointpos_contact_play: 0
21_rca_jointpos_contact_play_no_interval: 0
log:
  launchable_logs/rca_diagnostic_matrix_marker_checked.log
```

Formal preload-direction eval:

```text
run: 2026-05-24T16-44-26Z_preload-direction
success_step: null
preload_success_step: null
bc_steps_executed: 400
preload_steps_executed: 1544
handoff_lateral: 0.2508
handoff_axial: 0.0464
handoff_rot: 2.1423
final_lateral: 0.1303
final_axial: 0.0366
final_rot: 2.5794
best_strict_miss_score: 34.9912
best_vs_handoff_strict_miss_delta: -9.3471
near_contact_fraction: 0.0000
max_contact_force_magnitude: 7.5659
summary:
  contact_handoff_baseline/2026-05-24T16-44-26Z_preload-direction/summary.json
```

Important replay finding:

```text
historical source step 1543:
  lateral: 0.0052
  axial: 0.0413
  rot: 0.1812
  contact: 0.5298

Launchable replay at source step 1543:
  lateral: 0.2508
  axial: 0.0464
  rot: 2.1423
  contact: 5.6489
```

Interpretation: the official AWS Launchable path now works for short Isaac Lab headless RCA runs, but the historical joint-position `raw_action` trace is not portable enough across the old Isaac runtime and Isaac Lab 2.3. The `2026-05-24T16-44-26Z_preload-direction` result should be treated as a valid runtime/replay-drift diagnostic, not a fair controller-quality result. That requirement to generate fresh traces inside the Launchable runtime was later satisfied by the fresh-controller runs below.

## Fresh Launchable Controller Result

A later official AWS Launchable run, `isaac-launchable-fb61a7` / `pk2xmabsc`, tested the fresh-trace path in the same Isaac Lab 2.3 / Isaac Sim 5.1 runtime.

Passed runtime checks:

```text
smoke log:
  artifacts/launchable_logs/headless_smoke_final_legacy_convention.log
bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T18-13-18Z.tar.gz
latest local bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T09-24-27Z.tar.gz
```

Main fresh-preload result:

```text
run:
  evaluations/scripted/2026-05-24T17-55-26Z_fresh-preload
scripted status:
  completed 1900 steps
selected handoff step:
  14
selected handoff:
  lateral=0.0049
  axial=0.5937
  rot=2.4654
  contact=6.9205
  strict_miss_score=77.7206
post-handoff eval:
  skipped fail-closed because strict_miss_score > 1.0
```

Additional diagnostics on the same Launchable showed:

```text
geom-debug-20260524T180147Z:
  action frame and physical peg tip remain aligned; the blocker is controller/target behavior, not sync_peg_to_hand drift.

2026-05-24T18-06-31Z_fresh-preload:
  naive WXYZ constant migration made the initial geometry worse and still failed closed.

wxyz-no-rotate-before-descend-20260524T180931Z:
  improved axial motion but let lateral drift badly.

legacy-const-wxyz-helper-20260524T181152Z:
  WXYZ local quaternion helpers were incompatible with the calibrated legacy constants.

legacy-no-rotate-before-descend-20260524T181338Z:
  removing rotate-before-descend under the calibrated legacy convention also drifted laterally.
```

Interpretation: the current Launchable runtime is usable, but the previous scripted handoff generator is not. Do not spend another paid run sweeping the old full-quaternion controller family. Keep the calibrated legacy frame constants/helper convention unless a dedicated remote calibration replaces it end to end.

Implemented after this result:

```text
source/.../constants.py
  SOCKET_INSERTION_AXIS_LOCAL = (0, 0, 1)
  SOCKET_INSERTION_AXIS_SIGN_INVARIANT = True

source/.../mdp/observations.py
source/.../mdp/terminations.py
source/.../mdp/rewards.py
  success / reward rotation now uses calibrated sign-invariant cylinder-axis error,
  not full quaternion distance.

scripts/scripted_agent.py
  adds --orientation-target-mode axis-align-current
  This aligns the insertion axis while preserving the current twist about the cylindrical peg.

scripts/run_launchable_phase2_fresh_preload_direction.sh
  uses --orientation-target-mode axis-align-current by default.
```

Offline analysis of the failed fresh Launchable trace confirmed that full-quaternion alignment pushed the robot toward a joint limit while lateral error grew from the early `0.0043m` near-center state to about `0.58m`.

The axis-aware paid validation has now been run:

```text
instance: isaac-launchable-837c5c / e9v2t2tsw
provider: AWS g6e.4xlarge L40S
smoke: passed
fresh-preload: failed closed before post-handoff eval
selected_handoff_step: 7
selected_handoff: lateral=0.0082 axial=0.6031 rot=0.9302
strict_miss_score: 63.6295
diagnostics: artifacts/launchable_logs/rca-launchable-diagnostics-e9v2t2tsw.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-e9v2t2tsw.tar.gz
cleanup: brev delete e9v2t2tsw; browser UI and brev ls confirmed no remaining instances
```

The official Launchable cloud-init path also failed on this instance because the generated per-boot/per-instance scripts were empty and produced `Exec format error`; manually starting the official `isaac-sim/isaac-launchable` compose stack brought up `vscode`, `web-viewer`, and `nginx`.

A short no-rotate-before-descend diagnostic on the same instance produced useful but still failing evidence: `best_lateral=0.0041@11`, `best_axial=0.0611@1221`, `best_rot=0.1868@1092`, `final_lateral=0.4124`, `success_step=null`. This shows depth/axis alignment are individually reachable, but XY retention collapses during rotation/descent.

Implemented after this result:

```text
scripts/scripted_agent.py
  adds --rotate-xy-retention / --rotate-xy-retention-tol
  adds --descend-xy-retention / --descend-xy-retention-tol
  When lateral error exceeds the threshold during staged rotation/descent, the controller freezes orientation/Z progress,
  clears the stateful rotate command, and uses the existing socket-XY target to recover lateral alignment.
  Summary JSON reports recovery step counts, first/last recovery steps, and max lateral error seen during recovery.

scripts/run_launchable_phase2_fresh_preload_direction.sh
  enables both retention gates by default with 0.012m thresholds.

scripts/select_preload_handoff_step.py
  includes rotate_xy_recovery / descend_xy_recovery in the selected handoff JSON.
```

The XY-retention paid validation has now also been run:

```text
instance: isaac-launchable-1e19c4 / 1cozht94s
provider: AWS g6e.4xlarge L40S
smoke: passed
fresh-preload: failed closed before post-handoff eval
run: 2026-05-24T21-14-20Z_fresh-preload
selected_handoff_step: 8
selected_handoff: lateral=0.0065 axial=0.6025 rot=0.9335
strict_miss_score: 63.4364
rotate_xy_recovery_step_count: 1767
rotate_xy_recovery_max_lateral: 1.0018
descend_xy_recovery_step_count: 122
descend_xy_recovery_max_lateral: 0.9774
diagnostics: artifacts/launchable_logs/rca-launchable-diagnostics-1cozht94s.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-1cozht94s.tar.gz
cleanup: brev delete 1cozht94s; subsequent SSH lookup failed; browser UI showed empty environments
note: brev ls/list JSON timed out during the final post-delete check
```

Interpretation: the XY-retention flags are being detected, but they do not recover the current joint-IK branch. Two live-patched joint-step limiter diagnostics were also tried on the same instance:

```text
--joint-step-limit-mode global
  stopped early around step 1625
  never produced a useful handoff; XY approach was too slow/poor and axial/rot worsened

--joint-step-limit-mode after-xy-global
  stopped early around step 1450
  improved worst lateral drift versus the component baseline, but still plateaued around 0.17-0.20m
```

`scripts/scripted_agent.py` keeps `--joint-step-limit-mode {component,global,after-xy-global}` as a diagnostic switch, but `scripts/run_launchable_phase2_fresh_preload_direction.sh` uses the original component clipping by default. Do not spend another paid run on this scripted handoff family.

Prepared after this result:

```text
scripts/run_launchable_phase2_absik_handoff_probe.sh
```

This is a new Launchable-only probe for the older, more promising Abs IK control surface (`RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`). It is intentionally scripted-only: it generates a fresh Abs IK trace, selects the best handoff with `scripts/select_preload_handoff_step.py`, and fails closed if `strict_miss_score > 1.0`. It does not run `preload-direction`.

The wrapper now also writes:

```text
probe_summary.json
```

That compact summary records the scripted final/best metrics, the selected handoff, strict-miss component contributions, first per-axis ready steps, phase counts, and the final `pass` / `fail_closed` decision. Use it first before opening long Isaac logs.

Why this branch is different: the failed Launchable family wrote joint targets through a standalone JointIK pre-controller. The Abs IK branch lets Isaac Lab's native `DifferentialInverseKinematicsActionCfg` action term solve the pose target. Historical Brev evidence from 2026-05-15/16 showed this surface could reach `best_lateral=0.0005`, `best_axial=0.0467`, and `best_rot=0.0041`; the remaining blocker was contact-induced jump/retention, not initial handoff generation.

The Abs IK probe was then run on AWS Launchable:

```text
instance: isaac-launchable-4a2c79 / ij912di64
provider: AWS g6e.4xlarge L40S
observed price: $3.61/hr while running; UI showed $0.04/hr while DELETING
cloud-init: failed again because generated per-boot/per-instance scripts were empty
manual recovery: cloned isaac-sim/isaac-launchable and ran docker compose in isaac-lab
smoke: passed
run: 2026-05-25T09-44-02Z_absik-handoff-probe
post-handoff eval: not run by design
decision: fail_closed
selected_handoff_step: 319
selected_handoff: lateral=0.1112 axial=0.0171 rot=0.6220 contact=4.9495
strict_miss_score: 15.0390
strict_miss_components: lateral=10.6192 rot=4.4198 axial=0 contact=0
z_ready_step_count: 285
contact_ready_step_count: 320
xy_ready_step_count: 0
rot_ready_step_count: 0
artifacts: artifacts/launchable_logs/rca-absik-probe-results-ij912di64.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-ij912di64.tar.gz
cleanup: delete requested by name and id; final CLI checks showed no instances and JSON {"workspaces": null}
```

Interpretation: this short Abs IK probe solved depth/contact but never came close on XY or rotation in the Launchable runtime. It also stayed in `reach` phase for all 320 steps, and best lateral was the final step. The first local fix was to change the wrapper default from 320 to 1200 steps; follow-up trace/source review then found the more important issue: the native 7D MDP Abs IK branch was writing world-frame absolute pose targets into Isaac Lab's root-frame `DifferentialInverseKinematicsAction` command. `scripts/scripted_agent.py` now defaults to `--mdp-abs-action-frame root`, keeps `world` only as a legacy diagnostic path, and the Launchable Abs IK wrapper explicitly passes `--mdp-abs-action-frame root`. Do not rerun the old 320-step/world-frame probe.

The root-frame Abs IK probe was then run on AWS Launchable:

```text
instance: isaac-launchable-fdfaba / ez3iyhmlw
provider: AWS g6e.4xlarge L40S
observed price: $3.61/hr while running
cloud-init: failed again because generated per-boot/per-instance scripts were empty
manual recovery: reused the official isaac-sim/isaac-launchable compose stack
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-29-24Z.tar.gz
smoke: passed
run: 2026-05-25T12-47-17Z_absik-handoff-probe
post-handoff eval: not run by design
decision: fail_closed
mdp_abs_action_frame: root
selected_handoff_step: 330
selected_handoff: lateral=0.1110 axial=0.0172 rot=0.6225 contact=4.9089
strict_miss_score: 15.0255
strict_miss_components: lateral=10.6001 rot=4.4254 axial=0 contact=0
final_lateral: 0.0578
final_axial: 0.0286
final_rot: 1.5049
success_step: null
z_ready_step_count: 1165
contact_ready_step_count: 1200
xy_ready_step_count: 0
rot_ready_step_count: 0
artifacts: artifacts/launchable_logs/rca-root-absik-probe-results-ez3iyhmlw.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-ez3iyhmlw.tar.gz
cleanup: delete requested by name and id; Brev UI confirmed DELETING at $0.00/hr, and final CLI check returned {"workspaces": null}
```

Interpretation: converting the native 7D MDP Abs IK action from world frame to robot root frame did not materially solve the Launchable handoff blocker. Root frame is still the correct Isaac Lab action convention, but the probe stayed in `reach`, never reached XY/rotation readiness, and selected essentially the same guarded handoff as the earlier 320-step run. The likely issue is now deeper in the scripted Abs IK target/action semantics, quaternion/axis handling, or controller formulation; do not spend another paid Launchable run on the same Abs IK probe unchanged.

Prepared after this result:

```text
scripts/scripted_agent.py
  --mdp-abs-orientation-command-mode {target,current}

scripts/run_launchable_phase2_absik_handoff_probe.sh
  RCA_LAUNCHABLE_MDP_ABS_ORIENTATION_COMMAND_MODE=current
latest bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
```

Default `target` preserves the previous behavior. Diagnostic `current` keeps sending a valid native 7D absolute MDP command but replaces the commanded quaternion with the measured current action-frame quaternion before converting to robot root frame. This intentionally makes the run position-only for the native IK action; if XY then converges, the blocker is the pose/orientation coupling. If XY still does not converge, focus next on target-frame geometry, body offset convention, collision/contact, or controller formulation rather than quaternion tracking.

That orientation-current diagnostic was then run on AWS Launchable:

```text
instance: isaac-launchable-18d403 / v8g5gmij4
provider: AWS g6e.4xlarge L40S
cloud-init: failed again with empty per-boot/per-instance scripts
manual recovery: official isaac-sim/isaac-launchable compose stack
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
smoke: passed
run: 2026-05-25T13-17-53Z_absik-handoff-probe
post-handoff eval: not run by design
decision: fail_closed
mdp_abs_action_frame: root
mdp_abs_orientation_command_mode: current
selected_handoff_step: 325
selected_handoff: lateral=0.1111 axial=0.0172 rot=0.6251 contact=4.9233
strict_miss_score: 15.0579
strict_miss_components: lateral=10.6068 rot=4.4511 axial=0 contact=0
best_lateral: 0.0578@638
best_axial: 0.0006@56
best_rot: 0.6235@302
final_lateral: 0.0578
final_axial: 0.0286
final_rot: 1.5048
success_step: null
z_ready_step_count: 665
contact_ready_step_count: 700
xy_ready_step_count: 0
rot_ready_step_count: 0
artifacts: artifacts/launchable_logs/rca-absik-current-probe-results-v8g5gmij4.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v8g5gmij4.tar.gz
cleanup: delete requested by name and id; final CLI check returned no instances and {"workspaces": null}
```

Interpretation: holding the commanded orientation at the measured current quaternion did not improve XY at all. The curve and selected handoff are effectively the same as the target-orientation root-frame run, so the blocker is not simply full-pose orientation coupling. Next focus should be local-first target/action-frame geometry, body offset convention, contact/collision constraints during XY approach, or replacing this scripted native Abs IK handoff formulation.

Prepared after this result:

```text
scripts/scripted_agent.py
  trace rows include post_arm_joint_pos, post_arm_joint_vel, post_arm_joint_limit_margin
  summary includes min_arm_joint_limit_margin and min_arm_joint_limit_margin_step

scripts/analyze_absik_probe_trace.py
  reads trace JSON or a pulled diagnostics tarball
  summarizes target/command/action/post-action tracking residuals

scripts/run_launchable_phase2_absik_handoff_probe.sh
  writes tracking_analysis.json
  RCA_LAUNCHABLE_ABS_CONTROL_MODE={waypoint,target}
  RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 for diagnostic runs through brev exec
```

The new analyzer was run locally against both `artifacts/launchable_logs/rca-root-absik-probe-results-ez3iyhmlw.tar.gz` and `artifacts/launchable_logs/rca-absik-current-probe-results-v8g5gmij4.tar.gz`. Both show the same fixed point: inferred `abs_pos_step=0.0300m`, tail `command_to_post_action_xy≈0.0315m`, tail `target_to_command_y≈-0.027m`, and tail `post_action_step_delta_xy≈0`. Interpretation: the waypoint command stays one step short in Y while the measured action-frame tip has stopped moving. The follow-up paid Abs IK diagnostic therefore used full target commands, not another waypoint run:

```bash
RCA_LAUNCHABLE_ABS_CONTROL_MODE=target \
  RCA_LAUNCHABLE_SCRIPTED_STEPS=500 \
  RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
  ./scripts/run_launchable_phase2_absik_handoff_probe.sh
```

Use `RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1` when running through `brev exec`; otherwise the expected fail-closed nonzero exit can be misclassified by the Brev CLI as a connection failure and retried.

Target-command diagnostic result:

```text
instance: rca-absik-target-vm / 6siwq7a2t
provider: AWS g6e.4xlarge L40S plain Brev VM
reason for plain VM: brev create --launchable still failed with lifecycle script is empty
manual runtime: cloned isaac-sim/isaac-launchable, docker compose up -d in isaac-lab
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T15-05-37Z.tar.gz
smoke: passed
run: 2026-05-25T15-22-37Z_absik-handoff-probe
decision: fail_closed
abs_control_mode: target
mdp_abs_action_frame: root
mdp_abs_orientation_command_mode: target
selected_handoff_step: 23
selected_handoff: lateral=0.1067 axial=0.0110 rot=0.7833 contact=1.8385
strict_miss_score: 16.2003
best_lateral: 0.0556@276
best_axial: 0.0003@18
best_rot: 0.7833@23
final_lateral: 0.0556
final_axial: 0.0277
final_rot: 1.5167
success_step: null
xy_ready_step_count: 0
rot_ready_step_count: 0
z_ready_step_count: 488
contact_ready_step_count: 498
min_arm_joint_limit_margin: -0.00023@103
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.0556, post_action_step_delta_xy≈0
joint-limit analysis: limiting_joint=panda_joint4, global_min=-0.0002255@103, tail_mean_margin≈2.2e-6, tail limiting_joint_counts={panda_joint4: 50}
artifacts: artifacts/launchable_logs/rca-absik-target-probe-results-6siwq7a2t.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-6siwq7a2t.tar.gz
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: full target commands remove the waypoint short-command issue (`target_to_command_xy=0.0`) but do not move the measured action-frame tip to the socket. The tail has `command_to_post_action_xy≈0.0556m` and almost zero post-action motion, so the remaining blocker is not the waypoint formulation. The trace now points specifically at `panda_joint4` lower-limit saturation: it is the global minimum-margin joint, remains within `1e-4` for all 500 samples, and is still the limiting tail joint. The next local-first change should reduce or avoid that posture pressure before another paid run: change the approach/target pose, add joint-limit avoidance/nullspace behavior, or test whether contact/collision constraints are forcing the same joint-limit plateau.

Initial `panda_joint4=-2.6` diagnostic result:

```text
instance: rca-absik-j4init-vm / v0w2i1mp2
provider: AWS g6e.4xlarge L40S plain Brev VM
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T16-49-17Z.tar.gz
smoke: passed
run: 2026-05-25T17-01-54Z_absik-handoff-probe
decision: fail_closed
abs_control_mode: target
initial_joint_pos_overrides: panda_joint4=-2.6
selected_handoff_step: 15
selected_handoff: lateral=0.1334 axial=0.0350 rot=1.2837 contact=3.2904
strict_miss_score: 23.8804
best_lateral: 0.1184@403
best_axial: 0.0230@403
best_rot: 1.1633@0
final_lateral: 0.1185
final_axial: 0.0230
final_rot: 1.4629
success_step: null
xy_ready_step_count: 0
rot_ready_step_count: 0
z_ready_step_count: 486
contact_ready_step_count: 500
pre-step global limit: panda_joint6 margin=0.0@0
post-step global limit: panda_joint4 margin=3.34e-6@0
joint-limit tail: limiting_joint_counts={panda_joint4: 50}
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.1185, post_action_step_delta_xy≈5.85e-6
artifacts: artifacts/launchable_logs/rca-absik-j4init-probe-results-v0w2i1mp2.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v0w2i1mp2.tar.gz
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: moving only `panda_joint4` away from the lower limit before reset made the native Abs IK target-mode run worse, not better. The first commanded action immediately pushed `panda_joint4` back to the lower-limit plateau, while the pre-step trace also shows `panda_joint6` at its upper limit at step `0`. Do not spend another paid run on a single-joint initial elbow offset. The next useful work is a controller/action formulation that can avoid joint limits explicitly, a different full-arm initial posture, or a target/approach pose change that does not drive the native IK solver into the same branch.

Contact/collision diagnostic after the j4-init result:

```text
new scripted flag: --disable-socket-wall-collisions
new wrapper env: RCA_LAUNCHABLE_DISABLE_SOCKET_WALL_COLLISIONS=1
analyzer additions: tail socket-frame contact force and physical peg-tip residual summaries
```

Re-analysis of the two latest artifacts showed the target command was already exactly at the desired XY (`target_to_command_xy=0.0`) while contact force persisted and the action-frame tip stalled. A no-wall-collision target-mode probe was run on a plain AWS Brev VM:

```text
instance: rca-absik-nowall-vm / 11ieede24
provider: AWS g6e.4xlarge L40S plain Brev VM
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz
smoke: passed
run: 2026-05-25T18-21-28Z_absik-handoff-probe
decision: fail_closed
abs_control_mode: target
disable_socket_wall_collisions: true
selected_handoff_step: 337
selected_handoff: lateral=0.0957 axial=0.0086 rot=0.5281 contact=1.8613
strict_miss_score: 12.5491
best_lateral: 0.0704@129
best_axial: 0.0002@322
best_rot: 0.5242@340
final_lateral: 0.0825
final_axial: 0.0255
final_rot: 0.7460
success_step: null
xy_ready_step_count: 0
rot_ready_step_count: 0
z_ready_step_count: 488
contact_ready_step_count: 498
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.0825, post_action_step_delta_xy≈1.2e-5
joint-limit analysis: panda_joint4 global_min=-0.0002255@103; tail_mean_margin≈0.1588; tail limiting_joint_counts={panda_joint4: 50}
artifacts: artifacts/launchable_logs/rca-absik-nowall-parked-probe-results-11ieede24.tar.gz
cleanup: delete requested by name and id; later CLI polling returned {"workspaces": null}
```

The first no-wall attempt only changed the authored collision property and still showed unchanged contact force, so the flag was strengthened to also park all four guide-wall prims far away before scene creation. The parked-wall run was still fail-closed and worse than full-target baseline (`8.25cm` final/tail residual instead of `5.56cm`). Interpretation: guide-wall collision is not the main XY blocker. Also, `peg_contact_force_magnitude` is based on the peg sensor's `net_forces_w`, not a wall-only force channel, so do not interpret persistent contact force as proof of socket-wall blockage.

Target-offset tracking diagnostic result:

```text
remote vm: rca-absik-offset-vm / v2319sjd7
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-target-offset-matrix-2026-05-25.tar.gz
matrix script: scripts/run_launchable_absik_target_offset_matrix.sh
artifact: artifacts/launchable_logs/rca-absik-target-offset-matrix-results-v2319sjd7.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v2319sjd7.txt
```

Cases:

```text
baseline:
  decision: fail_closed
  selected: step=23 lateral=0.1067 axial=0.0110 rot=0.7833 strict_miss=16.2003
  final: lateral=0.0556 axial=0.0277 rot=1.5167
  best_lateral: 0.0556@276
  ready_counts: xy=0 rot=0 success_step=null
  tracking tail: command_to_post_action_xy≈0.0556, true target tail≈0.0556, post_action_step_delta_xy≈3.1e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

target_y_neg_04, offset=0,-0.04,0:
  decision: fail_closed
  selected: step=88 lateral=0.0709 axial=0.0117 rot=1.4063 strict_miss=18.8528
  final: lateral=0.0710 axial=0.0117 rot=1.4070
  best_lateral: 0.0709@88
  ready_counts: xy=0 rot=0 success_step=null
  tracking tail: biased command_to_post_action_xy≈0.0973, true target tail≈0.0710, post_action_step_delta_xy≈3.8e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

target_y_pos_04, offset=0,0.04,0:
  decision: fail_closed
  selected: step=282 lateral=0.0765 axial=0.0268 rot=0.4895 strict_miss=10.2475
  final: lateral=0.0778 axial=0.0331 rot=0.8050
  best_lateral: 0.0765@284
  ready_counts: xy=0 rot=0 success_step=null
  tracking tail: biased command_to_post_action_xy≈0.0396, true target tail≈0.0774, post_action_step_delta_xy≈1.8e-5
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}
```

Interpretation: the commanded fixed point moves with a biased target, so the action path is not completely ignored. But neither sign of the simple Y bias improves true socket XY, and all three cases remain locked on the `panda_joint4` limiting branch with no XY/rotation readiness. Do not spend another paid run on target offsets or guide-wall collision. The next local-first diagnostic is the native IK solver-method matrix:

```text
new scripted flag: --mdp-abs-ik-method dls|pinv|svd|trans
new wrapper env: RCA_LAUNCHABLE_MDP_ABS_IK_METHOD=dls|pinv|svd|trans
new matrix script: scripts/run_launchable_absik_ik_method_matrix.sh
default matrix cases: dls, pinv, svd, trans
```

IK solver-method matrix result:

```text
remote vm: rca-absik-ikmethod-vm / h9xqkqowr
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-ik-method-matrix-2026-05-25.tar.gz
matrix script: scripts/run_launchable_absik_ik_method_matrix.sh
artifact: artifacts/launchable_logs/rca-absik-ik-method-matrix-results-h9xqkqowr.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-h9xqkqowr.txt
```

Cases:

```text
dls:
  decision: fail_closed
  selected: step=23 lateral=0.1067 axial=0.0110 rot=0.7833 strict_miss=16.2003
  final: lateral=0.0556 axial=0.0277 rot=1.5167
  best_lateral: 0.0556@276
  ready_counts: xy=0 rot=0 z=338 contact=348 success_step=null
  tracking tail: command_to_post_action_xy≈0.0556, post_action_step_delta_xy≈3.1e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

pinv:
  decision: fail_closed
  selected: step=23 lateral=0.1061 axial=0.0110 rot=0.8223 strict_miss=16.5356
  final: lateral=0.0554 axial=0.0273 rot=1.5201
  best_lateral: 0.0554@311
  ready_counts: xy=0 rot=0 z=338 contact=348 success_step=null
  tracking tail: command_to_post_action_xy≈0.0554, post_action_step_delta_xy≈2.5e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

svd:
  decision: fail_closed
  selected/final/tracking: effectively identical to pinv
  final: lateral=0.0554 axial=0.0273 rot=1.5201
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

trans:
  decision: fail_closed
  selected: step=13 lateral=0.1349 axial=0.0305 rot=0.4393 strict_miss=15.5812
  final: lateral=0.1386 axial=0.0348 rot=0.4472
  best_lateral: 0.1349@13
  ready_counts: xy=0 rot=0 z=350 contact=350 success_step=null
  tracking tail: command_to_post_action_xy≈0.1386, post_action_step_delta_xy≈3.3e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}
```

Interpretation: changing Isaac Lab's native IK solver method does not remove the failure. `pinv`/`svd` are a numerically tiny lateral change from `dls` and still saturate `panda_joint4`; `trans` changes the posture enough to improve rotation but loses true XY badly. The native Abs IK solver-method sweep is closed. The next useful diagnostic is now wired as a full-arm reset/posture matrix:

```text
new matrix script: scripts/run_launchable_absik_full_arm_posture_matrix.sh
default matrix cases: baseline, ready_mid, elbow_open, yaw_pos, yaw_neg
case variable: RCA_LAUNCHABLE_ABS_IK_POSTURE_CASES=name:panda_joint1=...,panda_joint2=...
```

Full-arm reset/posture matrix result:

```text
remote vm: rca-absik-posture-vm / 5sjedqlea
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-full-arm-posture-matrix-2026-05-25.tar.gz
matrix script: scripts/run_launchable_absik_full_arm_posture_matrix.sh
artifact: artifacts/launchable_logs/rca-absik-full-arm-posture-matrix-results-5sjedqlea.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-5sjedqlea.txt
```

Cases:

```text
baseline:
  decision: fail_closed
  selected: step=23 lateral=0.1067 axial=0.0110 rot=0.7833 strict_miss=16.2003
  final: lateral=0.0556 axial=0.0277 rot=1.5167
  best_lateral: 0.0556@276
  ready_counts: xy=0 z=338 rot=0 contact=348 success_step=null
  tracking tail: target_to_post_action_xy≈0.0556, post_action_step_delta_xy≈3.1e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

ready_mid:
  result: identical to baseline; explicit Franka ready pose is effectively the current default reset posture

elbow_open:
  decision: fail_closed
  selected: step=207 lateral=0.2479 axial=0.0583 rot=0.3714 strict_miss=27.5402
  final: lateral=0.2480 axial=0.0586 rot=0.4168
  best_lateral: 0.1998@0
  ready_counts: xy=0 z=7 rot=0 contact=349 success_step=null
  tracking tail: target_to_post_action_xy≈0.2480, post_action_step_delta_xy≈2.1e-4
  joint-limit tail: limiting_joint_counts={panda_joint4: 16, panda_joint7: 34}

yaw_pos:
  decision: fail_closed
  selected/final: step=349 lateral=0.0818 axial=0.0134 rot=1.1978 strict_miss=17.8626
  best_lateral: 0.0818@349
  ready_counts: xy=0 z=331 rot=0 contact=350 success_step=null
  tracking tail: target_to_post_action_xy≈0.0819, post_action_step_delta_xy≈1.0e-6
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

yaw_neg:
  decision: fail_closed
  selected: step=20 lateral=0.3034 axial=0.5843 rot=0.8790 strict_miss=90.7569
  final: lateral=0.3091 axial=0.6677 rot=1.4626
  best_lateral: 0.2212@3
  ready_counts: xy=0 z=0 rot=0 contact=349 success_step=null
  tracking tail: target_to_post_action_xy≈0.3094, post_action_step_delta_xy≈3.2e-4
  joint-limit tail: limiting_joint_counts={panda_joint6: 6, panda_joint7: 44}
```

Interpretation: coarse full-arm reset posture does not solve the native Abs IK fixed point. `ready_mid` confirms the default reset posture; `elbow_open` and `yaw_neg` move into worse branches; `yaw_pos` avoids negative joint-limit margin but still worsens true socket XY. The reset/posture-only sweep is closed. The next useful implementation should explicitly change controller behavior, for example adding joint-limit/nullspace behavior or replacing the native Abs IK action formulation.

Local controller follow-up implemented on 2026-05-26:

```text
scripts/scripted_agent.py
  --joint-limit-nullspace-gain
  --joint-limit-nullspace-activation-margin
  --joint-limit-nullspace-step
  --joint-limit-nullspace-damping

scripts/run_launchable_phase2_jointpos_nullspace_probe.sh
scripts/run_launchable_jointpos_nullspace_matrix.sh
scripts/summarize_absik_handoff_probe.py
scripts/analyze_absik_probe_trace.py
```

This is a non-native JointPos action-surface diagnostic. The standalone joint-IK path can now add a joint-limit centering delta, project it through the IK Jacobian nullspace, clamp it per step, and then apply the existing joint target limit guards. The default scripted behavior is unchanged because the nullspace gain defaults to `0.0`; the Launchable JointPos nullspace probe enables it explicitly. Summaries and trace analysis now report the nullspace parameters plus `max_joint_limit_nullspace_delta_norm`.

AWS validation result:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
instance: rca-jointpos-nullspace-vm / t28in7wiu
bundle: artifacts/launchable/robot-contact-assembly-launchable-jointpos-nullspace-2026-05-26.tar.gz
artifact: artifacts/launchable_logs/rca-jointpos-nullspace-probe-results-t28in7wiu.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-t28in7wiu.txt
smoke: passed
probe run: 2026-05-26T05-30-35Z_jointpos-nullspace-probe
result: failed closed
steps_requested: 900
selected_handoff_step: 10
selected_handoff: lateral=0.00898 axial=0.6344 rot=0.9471 contact=6.0025
strict_miss_score: 67.0077
final: lateral=0.0254 axial=0.8910 rot=1.3058 success_step=null
best_lateral: 0.00793 @ step 14
xy_ready_step_count: 0
z_ready_step_count: 0
rot_ready_step_count: 0
phase_counts: reach=5 align=895
min_arm_joint_limit_margin: 0.3569 at panda_joint4 step 374
max_joint_limit_nullspace_delta_norm: 0.0
tail_limiting_joint_counts: panda_joint4=50
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: the non-native JointPos nullspace probe is also closed in its current form. The nullspace term never activated because all joints stayed outside the configured activation margin, so a gain-only sweep using the current matrix would be uninformative. More importantly, this action surface regressed depth badly (`axial` stayed around `0.63-0.89m`) and remained stuck in `align`; it did not reproduce the native Abs IK `5.6cm` XY fixed point in a useful way. The next local-first change should alter phase/target/action semantics, for example approach height, alignment/descent ordering, command frame/body offset, or a genuinely different controller surface. Do not run `scripts/run_launchable_jointpos_nullspace_matrix.sh` unchanged as the next paid job.

Local phase/target follow-up implemented after reviewing the failed trace:

```text
scripts/scripted_agent.py
  --rotate-descent-mode hold|approach

scripts/run_launchable_phase2_jointpos_rotate_descend_probe.sh
```

The failed JointPos trace showed that after `xy_state` latched, `rotate_before_descend` kept the position target at the high XY-aligned pose (`command_z≈0.824m`) while waiting for orientation readiness. The socket target was `z=0.190m` and the approach target was `z=0.240m`; because orientation never became ready, descent never started and the action-frame Z drifted upward to `1.08m`. The new `approach` mode keeps the default behavior unchanged for existing repros, but the new wrapper runs a diagnostic that rotates while commanding the approach-height pose, with XY retention enabled and joint-limit nullspace disabled (`gain=0`) to isolate the phase/target change.

AWS validation result:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
instance: rca-jointpos-rotatedesc-vm / r2dvf19yi
bundle: artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
smoke: passed

probe run: 2026-05-26T11-03-11Z_jointpos-rotate-descend-probe
mode: rotate_descent_mode=approach, rotate/descent XY retention enabled, nullspace gain=0
result: failed closed
steps_requested: 900
selected_handoff_step: 10
selected_handoff_phase: rotate-descend
selected_handoff: lateral=0.00889 axial=0.6345 rot=0.9463 contact=5.9769
strict_miss_score: 66.9987
final: lateral=0.1680 axial=0.8438 rot=1.4707 success_step=null
phase_counts: reach=5 rotate-descend=18 rotate-xy-recover=877
min_arm_joint_limit_margin: 0.0163 at panda_joint7 step 590

probe run: 2026-05-26T11-04-30Z_jointpos-rotate-descend-open-probe
mode: rotate_descent_mode=approach, XY retention disabled, nullspace gain=0
result: failed closed
steps_requested: 500
selected_handoff_step: 11
selected_handoff_phase: rotate-descend
selected_handoff: lateral=0.00814 axial=0.6343 rot=0.9517
strict_miss_score: 66.9568
final: lateral=0.1328 axial=0.7083 rot=1.5511 success_step=null
phase_counts: reach=5 rotate-descend=495
tail limiting joint: panda_joint6

remote artifacts packaged but not pulled:
  /home/ubuntu/rca-jointpos-rotate-descend-results-r2dvf19yi.tar.gz
  /home/ubuntu/rca-host-diagnostics-r2dvf19yi.txt
local artifact status:
  not present under artifacts/launchable_logs because Brev CLI auth expired before copy
cleanup/cost status:
  Brev CLI repeatedly returned logged-out EOF before copy/delete.
  Brev later reported org credits exhausted, current balance -1.94, and auto-stopped environments.
  The cleanup heartbeat was deleted after the credit-exhaustion notification.
```

Interpretation: the phase/target change was diagnostic but not a rescue. With retention enabled, the controller immediately fell into XY recovery and did not make descent progress. With retention disabled, it continued rotate-descend and improved axial relative to the retained run, but XY still drifted far outside the handoff gate. Do not spend another paid run on the current JointPos nullspace or rotate-descend branch.

Local probe archive index generated on 2026-05-26:

```bash
python3 scripts/summarize_launchable_probe_archives.py \
  --output-json artifacts/analysis/launchable_probe_archive_summary_2026-05-26.json \
  --output-markdown artifacts/analysis/launchable_probe_archive_summary_2026-05-26.md
```

The index scanned 23 local tar archives, found 20 `probe_summary.json` files, and every probe was `fail_closed`; there were no parsing warnings. The best selected strict-miss score among the local archives is still a failed Abs IK target-offset case (`target_y_pos_04`, `selected_strict_miss_score=10.2475`, final lateral `0.0778m`). The best final lateral/tail command residual is still the failed JointPos nullspace probe (`final_lateral=0.0254m`, tail command-to-post-action XY `0.0139m`), but it is axially unusable (`final_axial=0.8910m`). Use the generated Markdown/JSON files for future comparisons instead of manually reopening every archive.

Local next-controller candidate implemented on 2026-05-27:

```text
scripts/scripted_agent.py
  --reachable-approach
  --reachable-approach-start-radius
  --reachable-approach-min-radius
  --reachable-approach-shrink-step
  --reachable-approach-shrink-xy-tol
  --reachable-approach-joint-margin-min

scripts/select_reachable_approach_candidates.py
scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh
```

`reachable-approach` is a local-first target-generation change. Instead of commanding the socket action-frame target immediately, it initializes a world-XY offset direction from the socket target toward the current action-frame position, starts at an outside radius, and only shrinks that radius after the offset target is reached while the previous-step arm joint-limit margin is above threshold. This is meant to avoid driving the controller directly into the known `panda_joint4`/fixed-point branch before a pre-insertion pose has been reached.

The offline candidate selector was run locally:

```bash
python3 scripts/select_reachable_approach_candidates.py \
  --output-json artifacts/analysis/reachable_approach_candidates_2026-05-27.json \
  --output-markdown artifacts/analysis/reachable_approach_candidates_2026-05-27.md
```

It found the best existing reachable-waypoint candidates in the Abs IK `target_y_pos_04` trace around steps `259-284`: lateral around `0.077m`, axial around `0.022-0.027m`, rotation around `0.49rad`, joint margin around `0.15-0.17rad`, and target-to-post-action XY residual around `0.039m`. This supports a first diagnostic radius around `0.060m` with margin-gated shrink steps rather than another direct-to-socket command. This has not been GPU-validated yet; do not run it remotely without a fresh explicit budget.

Local bundle prepared for this branch:

```text
artifacts/launchable/robot-contact-assembly-launchable-reachable-approach-2026-05-27.tar.gz
```

GPU validation completed on 2026-06-07:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
instance: rca-reachable-approach-vm / 8bk6tylx0
bundle: artifacts/launchable/robot-contact-assembly-launchable-reachable-approach-2026-06-07.tar.gz
local results: artifacts/launchable_logs/rca-reachable-approach-results-8bk6tylx0.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-8bk6tylx0.txt
cleanup: final Brev CLI check returned {"workspaces": null}
```

Runtime notes from this run:

```text
Isaac Sim image: nvcr.io/nvidia/isaac-sim:6.0.0-dev2
Isaac Lab: 6.5.0
GPU: NVIDIA L40S, driver 580.159.04
headless startup issue: SimulationApp could segfault in libX11/XOpenDisplay
working display workaround: Xvfb :99 -screen 0 1280x720x24 -ac -extension GLX
docker exec env for smoke/probes: -u root -e DISPLAY=:99
```

`scripts/random_agent.py` was patched to use the same AppLauncher fallback pattern as `zero_agent.py` and `scripted_agent.py`, because Isaac Lab 6.5.0 no longer exposes `isaaclab_tasks.utils.add_launcher_args`. `scripts/remote_common.sh` now supports optional `RCA_REMOTE_DOCKER_EXEC_ENV` so remote smoke can inject `-u root -e DISPLAY=:99`.

Reachable-approach result summary:

```text
baseline reachable probe:
  run: 2026-06-07T20-58-38Z_jointpos-reachable-approach-probe
  joint_ik_step: 0.035
  steps: 900
  success_step: null
  final_axial: 0.4215
  best_lateral: 0.000024@345
  best_rot: 0.0300@142
  selected strict_miss_score: 40.3082
  min joint margin: 0.5267 at panda_joint2 step 899

faster joint-IK probe:
  run: 2026-06-07T21-00-11Z_jointpos-reachable-approach-jik012
  joint_ik_step: 0.12
  steps: 900
  success_step: null
  final_axial: 0.3539
  selected strict_miss_score: 32.2077
  min joint margin: 0.3996 at panda_joint2 step 859

more aggressive joint-IK probe:
  run: 2026-06-07T21-01-36Z_jointpos-reachable-approach-jik030
  joint_ik_step: 0.30
  steps: 900
  success_step: null
  final_axial: 0.2733
  best_rot: 0.0033@714
  selected strict_miss_score: 24.3841
  min joint margin: 0.2509 at panda_joint2 step 843

long validation:
  run: 2026-06-07T21-03-02Z_jointpos-reachable-approach-jik030-steps2000
  joint_ik_step: 0.30
  steps: 2000
  success_step: null
  best_axial: 0.1073@1939
  final_axial: 0.1094
  selected strict_miss_score: 6.9591
  selected handoff: lateral=0.0012 axial=0.1076 rot=0.2103 contact=0.1056
  min joint margin: 0.0173 at panda_joint4 step 1490
```

Interpretation: `reachable-approach` solved the initial XY reach problem and showed that increasing `joint_ik_step` improves axial progress, but it still did not produce a valid strict handoff. The 2000-step run got closest on axial but still missed the `z<0.045`, `rot<0.18`, and `contact>=0.5` gates. It also drove `panda_joint4` close to its lower limit (`margin=0.0173`), so simply running longer or increasing step size further is not the next useful action.

Next local-first direction after this run: change posture/target generation so descent does not consume the remaining `panda_joint4` margin, or add an explicit posture/nullspace term that activates before joint 4 reaches the lower limit. Do not rerun `reachable-approach` unchanged on paid compute.

Implemented immediately after that result:

```text
scripts/scripted_agent.py
  --insert-joint-limit-margin
  --joint-limit-guard-gain
  --joint-limit-guard-activation-margin
  --joint-limit-guard-step

scripts/run_launchable_phase2_jointpos_reachable_guard_probe.sh
scripts/run_brev_reachable_guard_probe.sh
```

The new guard path keeps default scripted behavior unchanged, but lets a focused probe preserve early reachable-approach freedom while applying a larger joint-limit margin only during insertion/polish/settle/contact-retention. It also adds a late unprojected joint-limit guard delta and records `max_joint_limit_guard_delta_norm` in summaries/traces. This directly targeted the 2026-06-07 failure mode: reachable radius reached zero safely by step 98, but late insert consumed `panda_joint4` margin down to `0.0173rad`.

Local bundle prepared after this change:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T21-45-33Z.tar.gz
```

The paid wrapper defaults to AWS/L40S, starts a target-specific 90-minute watchdog, syncs the working tree, starts the Isaac Sim 6.0.0-dev2 task container with the `Xvfb :99 ... -extension GLX` workaround, runs compact smoke, runs the guard probe, copies results/diagnostics, then deletes and polls Brev for cleanup.

First paid wrapper attempt:

```text
timestamp: 2026-06-07T21:32Z
instance: rca-reachable-guard-vm / d9nx8jtfj
provider/type: AWS g6e.xlarge L40S, 100GB disk
result: infrastructure failure before smoke/probe
failure: docker run implicitly pulling nvcr.io/nvidia/isaac-sim:6.0.0-dev2 returned "grpc: the client connection is closing"
cleanup: script deleted the instance; final Brev list returned {"workspaces": null}
local audit files:
  artifacts/launchable_logs/brev_pre_rca-reachable-guard-vm_2026-06-07T21-32-31Z.json
  artifacts/launchable_logs/latest_brev_instances_after_rca-reachable-guard-vm.json
```

`scripts/install_remote_isaaclab_runtime.sh` was then hardened to run `sudo docker pull "${ISAAC_SIM_IMAGE}"` with three attempts before `docker run`, so a transient image-pull failure does not abort the paid run immediately.

Second paid wrapper attempt:

```text
timestamp: 2026-06-07T21:46Z
instance: rca-reachable-guard-vm / avejl6fqo
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed
probe run: 2026-06-07T21-59-30Z_jointpos-reachable-jointlimit-guard-probe
result: failed closed
success_step: null
selected handoff: step=1584 lateral=0.0012 axial=0.1989 rot=0.3361 contact=0.0473
strict_miss_score: 17.4066
final: lateral=0.0013 axial=0.1958 rot=0.3693
best_lateral=0.00008@741
best_axial=0.1958@1599
best_rot=0.0033@714
min_arm_joint_limit_margin=0.1542 at panda_joint4 step 1492
max_joint_limit_nullspace_delta_norm=0.0127@1493
max_joint_limit_guard_delta_norm=0.0154@1493
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-vm-2026-06-07T21-46-17Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-vm-2026-06-07T21-46-17Z.txt
cleanup: delete completed; final Brev list returned {"workspaces": null}
```

Interpretation: the guard worked on its direct safety target, increasing the limiting `panda_joint4` margin from `0.0173` to `0.1542`. It was too conservative for insertion: axial progress stalled around `0.196m`, contact dropped to near zero, and the strict miss was worse than the unguarded long reachable run. Do not rerun this strong guard unchanged.

The focused tuned guard variant was run after the strong-guard result:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh
```

It kept the same reachable approach, relaxed insertion guard defaults (`insert_joint_limit_margin=0.060`, guard gain/step `0.060/0.040`, activation `0.110`), and extended to 2000 steps. The paid wrapper command was:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-tuned-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

```text
timestamp: 2026-06-07T22:18Z
instance: rca-reachable-guard-tuned-vm / hm27ajjsk
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed
probe run: 2026-06-07T22-31-05Z_jointpos-reachable-jointlimit-guard-tuned-probe
result: failed closed
success_step: null
selected handoff: step=1921 lateral=0.0012 axial=0.1463 rot=0.2862 contact=0.0652
strict_miss_score: 11.6256
final: lateral=0.0029 axial=0.1449 rot=0.4466
best_lateral=0.00008@741
best_axial=0.1449@1999
best_rot=0.0033@714
min_arm_joint_limit_margin=0.0738 at panda_joint4 step 1503
max_joint_limit_nullspace_delta_norm=0.0101@1820
max_joint_limit_guard_delta_norm=0.0188@1504
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-tuned-vm-2026-06-07T22-18-02Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-tuned-vm-2026-06-07T22-18-02Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final Brev list returned {"workspaces": null}
```

Watchdog note: the target-specific watchdog wrote a stale `manual_delete_required.txt` after one transient Brev CLI query failure at 2026-06-07T22:28Z. The main wrapper continued, copied artifacts, deleted the instance, and confirmed `{"workspaces": null}`. The watchdog script has been hardened so transient query failures are tolerated before a manual-cleanup alert.

Interpretation: the tuned guard moved farther than the strong guard (`best_axial` improved from `0.1958m` to `0.1449m`) while keeping the limiting `panda_joint4` margin safer than the unguarded reachable run (`0.0738rad` vs `0.0173rad`). It still failed every strict-ready/z-ready gate: final axial was still far above `0.045m`, selected contact was only `0.065`, and rotation drifted back up during late insertion. Do not rerun the tuned guard unchanged. The next useful work is a local-first controller or phase change that gives insertion more depth without consuming the elbow branch, for example changing the pre-insertion posture/approach target, decoupling descent from rotation, or adding a more explicit posture objective before the final insertion phase.

Next local-first implementation prepared on 2026-06-08:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_rotgated_probe.sh
```

This is not an unchanged tuned rerun. It reuses the tuned guard parameters but enables `--insert-rotation-gated-descent`, disables `--hold-orientation-during-insert`, and defaults `insert_descent_rot_tol=0.35`. Offline replay of the tuned trace showed a 0.20rad gate would freeze almost the entire insertion segment, while 0.35rad targets only the high-rotation windows. The intent is to pause Z descent when rotation is clearly drifting, keep XY/orientation control active at the current depth, and then resume insertion after the controller repairs orientation.

Paid validation command, only after confirming `brev ls instances --json --all` is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-rotgated-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_rotgated_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

First paid rotgated attempt on 2026-06-07/08:

```text
instance: rca-reachable-guard-rotgated-vm / w57uxy94u
provider/type: AWS g6e.xlarge L40S, 100GB disk
runtime: created, nvidia-smi passed, repo synced, Isaac Sim 6.0.0-dev2 container started, Xvfb/runtime check passed
result: infrastructure/smoke failure before the rotgated probe started
failure point: compact smoke stayed in zero_agent.py --steps 3 for about 9 minutes with no artifact progress; smoke watchdog was not being passed to zero/random smoke
artifacts: no probe result tarball or host diagnostics were produced before cleanup
cleanup: wrapper deleted the instance; final wrapper output and independent CLI check both returned {"workspaces": null}; watchdog logged "target disappeared; cleanup confirmed"
```

After this failed attempt, `scripts/run_remote_smoke_test.sh` was hardened so zero, random, and scripted smoke commands all receive a default `RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300` plus an outer `timeout` (`watchdog + 120s`). `scripts/random_agent.py` now also supports `--watchdog_seconds`, matching `zero_agent.py`. The paid wrapper no longer passes a misleading scripted-only smoke watchdog argument.

Second paid rotgated attempt on 2026-06-08:

```text
timestamp: 2026-06-07T23:35Z
instance: rca-reachable-guard-rotgated2-vm / 6nuie4sss
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed after smoke watchdog hardening
probe run: 2026-06-07T23-47-57Z_jointpos-reachable-jointlimit-guard-rotgated-probe
result: failed closed
success_step: null
selected handoff: step=2144 phase=insert-rot-recover lateral=0.0010 axial=0.1711 rot=0.3537 contact=0.0934
strict_miss_score: 14.7524
strict_miss_components: axial=12.6084 contact=0.4066 lateral=0 rot=1.7374
final: lateral=0.0007 axial=0.1708 rot=0.5107
best_lateral=0.0004@211
best_axial=0.1708@2199
best_rot=0.1714@98
min_arm_joint_limit_margin=0.3923 at panda_joint4 step 2095
insert_rotation_gate_step_count=1034 first_step=177 last_step=2199 max_rot=0.5204
max_joint_limit_guard_delta_norm=0.0
max_joint_limit_nullspace_delta_norm=0.0
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotgated2-vm-2026-06-07T23-35-59Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-rotgated2-vm-2026-06-07T23-35-59Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final wrapper output and repeated independent Brev CLI checks returned {"workspaces": null}
```

Run note: the Docker pull failed once with `grpc: the client connection is closing`, retried successfully, and the instance completed the probe. The wrapper printed one stale manual-cleanup warning during a delete/list race, but immediately afterwards returned `{"workspaces": null}`; repeated independent `brev ls instances --json --all` checks also returned `{"workspaces": null}`.

Interpretation: rotation-gated insertion is now a real, smoke-passing Launchable result, and it should be considered closed in this form. Compared with the tuned guard, it preserved much more arm joint-limit margin (`0.3923rad` vs `0.0738rad`) and did not need joint-limit guard/nullspace corrections, but it regressed insertion depth (`best_axial/final_axial=0.1708m` vs `0.1449m`) and strict miss (`14.7524` vs `11.6256`). The rotation gate was active for 1034 of 2200 steps, from step 177 through the end, so it protected XY and posture by choking descent. Do not rerun the rotation-gated probe unchanged. The next useful work is local-first: replace the hard Z hold with a softer insertion policy, such as bounded descent during rotation recovery, a minimum descent budget per rotation window, or an explicit staged depth schedule that can continue making axial progress while orientation is being repaired.

Next local-first implementation prepared on 2026-06-08:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh
```

This is a narrow follow-up to the hard rotation-gated result, not an unchanged rerun. `scripts/scripted_agent.py` now supports `--insert-rotation-gate-descent-scale` and `--insert-rotation-gate-min-descent-step`; the default hard-gate behavior remains `scale=0.0`, while the new wrapper uses `scale=0.25`, `min_descent_step=0.002`, `insert_descent_rot_tol=0.35`, `hold_orientation_during_insert=0`, and `steps=2400`. The intent is to keep XY/orientation repair active during high-rotation insertion windows while still allowing bounded axial progress.

Paid validation command, only after confirming `brev ls instances --json --all` is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-softgated-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

Paid softgated validation on 2026-06-08:

```text
timestamp: 2026-06-08T00:16Z
instance: rca-reachable-guard-softgated-vm / hqgphjyta
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed
probe run: 2026-06-08T00-30-27Z_jointpos-reachable-jointlimit-guard-softgated-probe
result: failed closed
success_step: null
selected handoff: step=1443 phase=insert lateral=0.00323 axial=0.04343 rot=0.28758 contact=0.69435
strict_miss_score: 1.07584
strict_miss_components: axial=0 contact=0 lateral=0 rot=1.07584
final: lateral=0.01204 axial=0.04058 rot=0.33186
best_lateral=0.00037@1236
best_axial=0.03333@2322
best_rot=0.17140@98
min_arm_joint_limit_margin=0.10353 at panda_joint4 step 2328
insert_rotation_gate_step_count=1228 first_step=177 last_step=2321 max_rot=0.5180
insert_rotation_gate_descent_scale=0.25 min_descent_step=0.002 max_allowed_descent=0.0050
ready_counts: xy=1219 z=904 rot=17 strict=0 contact=949
tail means: lateral=0.01053 axial=0.04124 rot=0.30073 contact=1.48027 command_to_post_action_xy=0.00409 post_action_step_delta_xy=0.000104
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-softgated-vm-2026-06-08T00-16-12Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-softgated-vm-2026-06-08T00-16-12Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final wrapper output and independent Brev CLI check returned {"workspaces": null}
```

Interpretation at the time: soft-gated descent was the closest Launchable result and changed the blocker materially. It solved the hard-gate depth stall: the selected handoff was already inside the XY, Z, and contact gates, and failed only rotation (`rot=0.2876` vs `0.18`, strict miss `1.0758` vs guard `1.0`). It also reached much deeper than tuned/rotgated (`best_axial=0.0333m`, final `0.0406m`) while retaining a usable joint-limit margin (`0.1035rad` at `panda_joint4`). Do not rerun the same softgated probe unchanged. This recommendation was superseded by the depth-aware rotation polish validation below, which preserved XY/Z but still failed rotation.

Latest local bundle after soft-gated insertion wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-softgated-2026-06-08.tar.gz
```

Depth-aware rotation polish implementation prepared on 2026-06-08:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_rotpolish_probe.sh
```

This is the intended next non-duplicate paid validation. It keeps the soft-gated insertion settings and adds a default-off `--depth-rotation-polish` state to `scripts/scripted_agent.py`. The state latches only after insertion is active and XY/Z/contact are ready (`xy<0.006`, `z<0.050`, `contact>=0.5` in the wrapper), then holds socket XY, applies a `0.001m` Z preload, and targets the socket orientation with a `0.035rad` polish rotation step. It exits if XY exceeds `0.012m` or axial exceeds `0.060m`, letting normal insertion recover instead of continuing to rotate while drifting away.

Validation command, only after confirming Brev is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-rotpolish-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_rotpolish_probe.sh \
RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES=75 \
RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300 \
RCA_REMOTE_SMOKE_TIMEOUT_SECONDS=420 \
./scripts/run_brev_reachable_guard_probe.sh
```

Expected improvement criteria: the run should enter `depth-rot-polish`, keep selected lateral under `0.005m` and axial under `0.045m`, and reduce selected/final rotation below `0.18rad`. If it fails closed, compare `depth_rotation_polish_step_count`, `depth_rotation_polish_max_lateral`, `depth_rotation_polish_min_axial`, and tail phase counts before changing thresholds. Do not rerun softgated unchanged.

Paid depth-aware rotation polish validation on 2026-06-08:

```text
timestamp: 2026-06-08T04:25Z
instance: rca-reachable-guard-rotpolish-vm / xvkzygbsw
provider: AWS g6e.xlarge / L40S
probe run: 2026-06-08T04-37-01Z_jointpos-reachable-jointlimit-guard-rotpolish-probe
status: fail_closed
cleanup: copied result archive and host diagnostics, deleted instance, final Brev check returned {"workspaces": null}
```

Key result:

```text
selected handoff: step=1386 phase=insert lateral=0.002079 axial=0.044687 rot=0.326000 contact=1.451769 strict_miss=1.460000
final: lateral=0.002581 axial=0.045102 rot=0.352941 success_rate=0.0
depth-rot-polish: active_steps=615 first_step=1311 last_step=2599 max_lateral=0.004365 min_axial=0.044687 max_rot=0.526121 rot_step=0.035
tail window: lateral=0.002437 axial=0.052236 rot=0.283574 contact=0.208385 phase_counts={insert:44, depth-rot-polish:6}
limiter: panda_joint4 min_margin=0.100994 at step 2212
diagnosis: tail post-action movement makes little progress along the requested XY command
```

Artifacts:

```text
artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.tar.gz
artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.txt
```

Interpretation: the new state entered and kept XY tightly inside gate, so the latch/hold/preload plumbing worked. It did not solve the actual blocker: rotation during/after depth polish stayed above the `0.18rad` gate and ended worse than the prior soft-gated run (`selected rot 0.3260` vs `0.2876`, final rot `0.3529` vs `0.3319`). The failure is therefore not worth a duplicate paid rerun with the same wrapper. Next local-first change should replace the full-target orientation polish with a less oscillatory late-contact rotation repair: adaptive smaller rotation step, a contact/Z-aware orientation target, or a phase that rotates only while depth/contact remain stable instead of repeatedly cycling polish and insertion.

Adaptive late-contact rotation repair prepared after that result:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh
```

What changed locally:

```text
--depth-rotation-polish-orientation-mode stateful-waypoint
--depth-rotation-polish-exit-contact-min-force 0.30
--depth-rotation-polish-rot-step 0.012
--depth-rotation-polish-preload-step 0.0005
--depth-rotation-polish-exit-xy-tol 0.010
--depth-rotation-polish-exit-z-tol 0.055
```

The new mode seeds a persistent quaternion command at depth-polish entry and advances it toward the orientation target by a bounded step instead of recomputing a fresh full target every frame. It also exits the phase when contact falls below `0.30`, so late rotation only continues while contact/depth remain stable. This is the next non-duplicate paid validation candidate, but it still needs only a short AWS run after confirming Brev is empty; do not run it together with any sweep.

Validation command, only after confirming Brev is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-adaptive-rotpolish-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh \
RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES=80 \
RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300 \
RCA_REMOTE_SMOKE_TIMEOUT_SECONDS=420 \
./scripts/run_brev_reachable_guard_probe.sh
```

Expected improvement criteria: `depth_rotation_polish_orientation_mode=stateful-waypoint`, nonzero `depth_rotation_polish_step_count`, selected lateral under `0.005m`, selected axial under `0.045m`, and selected/final rotation materially below the old rotpolish run (`0.326/0.353`) with a target of `<0.18rad`. If it fails closed, compare contact-exit timing and whether `depth_rotation_polish_command_valid` stayed continuous before changing the step size.

Paid adaptive rotpolish validation on 2026-06-09:

```text
timestamp: 2026-06-09T05:17Z
instance: rca-reachable-guard-adaptive-rotpolish-vm / evzxs5mnd
provider: AWS g6e.xlarge / L40S
probe run: 2026-06-09T05-30-44Z_jointpos-reachable-jointlimit-guard-adaptive-rotpolish-probe
status: fail_closed
cleanup: copied result archive and host diagnostics, deleted instance, final Brev check returned {"workspaces": null}
```

Key result:

```text
selected handoff: step=1415 phase=insert lateral=0.002064 axial=0.044518 rot=0.320708 contact=1.847413 strict_miss=1.407076
final: lateral=0.002561 axial=0.045312 rot=0.366785 success_rate=0.0
depth-rot-polish: active_steps=863 first_step=1311 last_step=2999 max_lateral=0.004139 min_axial=0.044509 max_rot=0.506800 rot_step=0.012 orientation_mode=stateful-waypoint exit_contact_min_force=0.30
insert rotation gate: active_steps=1101 first_step=177 last_step=2997 max_rot=0.518001 descent_scale=0.25
ready counts: strict=0 xy=2865 z=150 contact=919 rot=17
tail window: lateral=0.002107 axial=0.045669 rot=0.337341 contact=0.468937 phase_counts={depth-rot-polish:30, insert:16, insert-rot-recover:4}
limiter: panda_joint4 min_margin=0.104442 at step 2921
diagnosis: tail post-action movement makes little progress along the requested XY command
```

Artifacts:

```text
artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.tar.gz
artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.txt
```

Interpretation: adaptive stateful waypoint polish was active and protected XY/depth, but it still did not repair rotation. Compared with the 2026-06-08 target-orientation rotpolish run, selected rotation improved only slightly (`0.3207` vs `0.3260`), final rotation worsened (`0.3668` vs `0.3529`), and no strict-ready step was produced. Do not rerun adaptive rotpolish unchanged or as a threshold sweep. The next useful step is local-first trace analysis around the `rot_ready` / `depth-rot-polish` windows and then a controller change to the late-contact orientation target or branch selection; only after that should another short paid validation be considered.

Local trace analysis helper added after the run:

```text
scripts/analyze_rotation_polish_trace.py
```

Running it on the 2026-06-08 rotpolish and 2026-06-09 adaptive rotpolish archives shows the rotation blocker is not a simple missing runtime or threshold issue:

```text
rotpolish: 2600 steps, 80 phase segments, 25 depth-rot-polish segments, mean segment len 24.6, best XY/Z/contact-ready rot 0.3260
adaptive rotpolish: 3000 steps, 983 phase segments, 472 depth-rot-polish segments, mean segment len 1.83, best XY/Z/contact-ready rot 0.3207
rot-ready range for both: only steps 87-103, before contact/depth readiness
```

This supports the controller diagnosis: near the actual handoff depth, the current `axis-align-current`/stateful-polish target keeps XY and depth usable but does not drive the trace toward the strict rotation metric. The next implementation should change the late-contact orientation target/branch behavior, not just lower polish step size or rerun with longer time.

Near-depth rotation-gate candidate prepared after that analysis:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
```

This adds default-off near-depth rotation-gate overrides to `scripts/scripted_agent.py` and exposes them through `scripts/run_launchable_phase2_jointpos_nullspace_probe.sh`:

```text
--insert-rotation-gate-near-depth-z-tol
--insert-rotation-gate-near-depth-rot-tol
--insert-rotation-gate-near-depth-descent-scale
--insert-rotation-gate-near-depth-min-descent-step
```

The wrapper inherits the soft-gated run but tightens only once `axial < 0.065m`: `rot_tol=0.22`, `descent_scale=0.10`, `min_descent_step=0.0005`. The intent was to avoid the observed redescend at `rot≈0.24` before the strict `0.18rad` gate is reached, while keeping early insertion permissive.

Paid validation on 2026-06-09:

```text
timestamp: 2026-06-09T06:31Z
instance: rca-neardepth-rotgate-vm / 5x0dmseey
provider/type: AWS g6e.xlarge L40S
smoke/runtime: passed
probe run: 2026-06-09T06-45-39Z_jointpos-reachable-jointlimit-guard-neardepth-rotgate-probe
result: failed closed
success_step: null
selected handoff: step=1763 phase=align lateral=0.001235 axial=0.049536 rot=0.350150 contact=0.500092
strict_miss_score: 2.155097
final: lateral=0.002205 axial=0.060102 rot=0.313013
best_lateral=0.000371@1236
best_axial=0.047266@1760
best_rot=0.171399@98
insert_rotation_gate_step_count=2101
min_arm_joint_limit_margin=0.096164 at panda_joint4 step 1766
tail means: lateral=0.002955 axial=0.061385 rot=0.262909 contact=0.070176
diagnosis: tail post-action movement makes little progress along the requested XY command
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final wrapper output and independent Brev CLI check returned {"workspaces": null}
```

Interpretation: tightening the rotation gate near depth did not close the strict handoff gap. The run again reached excellent XY and briefly achieved low rotation early, but at useful depth the controller could not satisfy depth/contact/rotation together. It selected a contact-qualified but too-shallow/high-rotation state (`axial=0.0495`, `rot=0.3502`) and the tail lost contact while making little XY progress. This closes the current scripted-controller branch; do not rerun near-depth rotgate unchanged or as a threshold sweep.

Latest local bundle after near-depth rotgate wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-neardepth-rotgate-2026-06-09.tar.gz
```

Latest local bundle after documenting the adaptive rotpolish result:

```text
artifacts/launchable/robot-contact-assembly-launchable-adaptive-rotpolish-result-2026-06-09.tar.gz
```

Latest local bundle after adaptive rotpolish wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-adaptive-rotpolish-2026-06-08.tar.gz
```

Latest local bundle after documenting the paid rotpolish result:

```text
artifacts/launchable/robot-contact-assembly-launchable-rotpolish-result-2026-06-08.tar.gz
```

Latest local bundle after depth-aware rotation polish wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-rotpolish-2026-06-08.tar.gz
```

Previous local bundle after rotation-gated probe wiring and smoke watchdog hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T23-35-06Z.tar.gz
```

Previous local bundle after rotation-gated probe wiring only:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-08T00-20-00Z.tar.gz
```

Previous local bundle after tuned guard result documentation and watchdog hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T22-50-00Z.tar.gz
```

Previous local bundle after tuned guard wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T22-17-23Z.tar.gz
```

Bundle used for the target-command run:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T15-05-37Z.tar.gz
```

Latest bundle after strengthening the no-wall-collision diagnostic:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz
```

Latest bundle after target-offset matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-target-offset-matrix-2026-05-25.tar.gz
```

Latest bundle after IK-method matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-ik-method-matrix-2026-05-25.tar.gz
```

Latest bundle after full-arm posture matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-full-arm-posture-matrix-2026-05-25.tar.gz
```

Latest bundle after JointPos nullspace wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-jointpos-nullspace-2026-05-26.tar.gz
```

Latest bundle after JointPos rotate-descend wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
```

## 2026-06-11 Contact Physics Validity Audit

A geometric audit of all recorded traces found that the Phase 2 task has no
real peg/socket contact physics, which invalidates the physical premise of
the entire scripted-controller and BC campaign.

```text
script: scripts/analyze_contact_physics_validity.py
report: artifacts/analysis/contact_physics_validity_2026-06-11.md
        artifacts/analysis/contact_physics_validity_2026-06-11.json
traces analyzed: 78
traces with free-space contact force: 72
traces with silent wall penetration: 15
verdicts: no_wall_physics=15, contact_signal_not_socket=57, consistent=3 (tiny smokes)
```

Root cause: both the peg and the socket guide walls are spawned with
`kinematic_enabled=True`, and `sync_peg_to_hand` teleports the peg to the
hand pose every step. PhysX does not resolve kinematic-kinematic pairs, so
the guide walls have never exerted any force on the peg. The
`contact_force_magnitude` signal is not socket reaction either; it is
consistent with gripper-finger interaction with the kinematically synced
peg.

Decisive evidence:

```text
softgated trace step 2322:
  peg axis passes 10mm through both left and right walls; contact reads 0.00
softgated trace step 98:
  peg in free space at z=0.745, >0.3m from any wall; contact reads 1.00
softgated trace steps 1399-1403:
  inserting end 52-58mm deep inside the channel at tilt 0.21rad,
  4x the geometric two-point maximum (0.05rad) for that depth
best near-miss trace 2026-05-17T23-32-18Z:
  816 steps with contact>=0.3 while >=2mm clear of every wall (max 3.35)
  298 steps with wall penetration >=2mm while contact < 0.1
  penetration/contact correlation: -0.113
note: the logged physical_tip_pos_w is the gripped upper end of the peg;
  the inserting end is one peg length farther along the peg axis.
  Trace quaternions are XYZW.
```

Implications:

1. Every paid probe optimized against a non-physical gate: `contact>=0.5`
   measured the gripper, not insertion, and the rotation plateau happened
   in a world where walls cannot block anything, so it is a
   controller/kinematics artifact, not contact jamming.
2. The earlier no-wall-collision diagnostic result (parking the walls
   changed nothing) is fully explained: the walls were never interacting.
3. The "shallow true-contact success", the strict near-miss labels, the
   near-contact BC datasets, and the final-contact reset candidates are all
   labeled by a gripper-force artifact and do not represent physical
   insertion contact.
4. Do not spend any further paid compute on any controller, BC, or RL run
   until the environment is fixed and a smoke test demonstrates real
   peg-wall collision response.

Required environment fix before any new run:

```text
- give the task a dynamic peg with real collision response: either a
  dynamic rigid body rigidly attached to the hand (fixed joint) or an
  extra link on the robot articulation
- keep the socket guide walls as colliders against that dynamic peg so
  PhysX generates real contact constraints
- remove sync_peg_to_hand teleportation during contact phases; a
  teleported kinematic body cannot experience reaction forces
- route the success-gate contact signal through a peg-vs-wall filtered
  contact pair, not the peg net-force sensor
- add a contact-physics smoke: command the peg straight into a wall and
  assert nonzero wall reaction and blocked motion before any paid run
```

The environment fix was implemented locally on 2026-06-13:

```text
source/.../peg_in_hole/assets.py (new)
  AttachedPegCylinderCfg / spawn_attached_peg_cylinder: spawns the peg as a
  DYNAMIC rigid body and authors a USD PhysicsFixedJoint from panda_hand to
  the peg inside the env_0 template (before sim start; cloner replicates it
  per env). Joint local pose = PEG_CENTER_BODY_OFFSET_POS/ROT, i.e. the same
  hand-to-peg transform the old kinematic sync enforced (XYZW constants are
  converted explicitly to USD scalar-first quaternions). The joint sets
  excludeFromArticulation so the peg stays a standalone RigidObject view.
  Gripper hand/finger collisions against the peg are disabled via
  UsdPhysics.FilteredPairsAPI (they interpenetrate by construction and only
  pollute forces/dynamics).

source/.../peg_in_hole/peg_in_hole_env_cfg.py
  peg: kinematic_enabled=False, max_depenetration_velocity=5.0, solver
  iterations 16/1, contact_offset=0.001 / rest_offset=0.0 (clearance is
  1.5mm per side, the offset must stay below it), friction 0.3, attached
  spawner wired with the calibrated joint transform.
  walls: same contact offsets/material, still kinematic colliders (valid
  against a dynamic peg).
  events: sync_peg_each_step REMOVED (a per-step teleport would fight the
  joint and erase contact impulses); sync_peg_on_reset kept as best-effort
  placement so the joint starts near zero error after arm reset.

source/.../peg_in_hole/mdp/observations.py
  peg_contact_force_magnitude / peg_contact_force_socket now read the
  wall-filtered force_matrix_w (summed over the four guide-wall pairs)
  instead of net_forces_w. scripted_agent.py and
  evaluate_contact_bc_policy.py consume these mdp functions directly, so
  every contact gate in the stack switches to the wall-only signal without
  script changes. Observation widths are unchanged.

source/.../peg_in_hole/config/franka/ik_rel_env_cfg.py
  sync_peg_each_step references removed. zero_agent's
  --disable_peg_sync_interval / --peg_sync_interval_seconds flags use
  defensive getattr and now no-op.

scripts/contact_physics_smoke.py (new)
scripts/run_launchable_contact_physics_smoke.sh (new)
  The audit-mandated gate. Runs the Abs IK play task with num_envs=2
  (catches per-env joint wiring failures after cloning), then checks
  markers: attach (peg tracks its own hand through the fixed joint),
  free-space (wall-filtered force ~0 when hovering), press-force
  (sustained reaction >0.5N pressing 20mm into a wall top), press-blocked
  (the peg end stays within 8mm of the wall-top plane instead of passing
  through), release, joint-integrity. The smoke overrides
  episode_length_s to 60s so the phase sequence cannot be interrupted by
  the play cfg's 240-step timeout.
```

Status: implemented and lint/syntax-checked locally; NOT yet validated on an
Isaac runtime because no local GPU/Isaac is available. The first action on
the next approved GPU session must be
`./scripts/run_launchable_contact_physics_smoke.sh`, before any other
evaluation. Until that smoke passes, treat the contact physics as unproven.

Verified runtime conventions used by the fix (empirically, from the June
Launchable traces): quaternions are XYZW end-to-end in the deployed Isaac
Lab runtimes (tip = hand ⊗ (0,0,0.1034) reproduces logged positions to
<1mm under XYZW and is ~17cm off under WXYZ), and the logged
`physical_tip_pos_w` is the gripped UPPER end of the peg — the inserting
end is one peg length farther along the peg axis. An earlier automated
review claimed a systemic XYZW/WXYZ mismatch against Isaac Lab math utils;
that claim is wrong for the deployed runtimes and was refuted with the
trace check above.

## Recommended Next Steps

0. Before anything else: apply the environment contact-physics fix from the
   2026-06-11 audit above and validate it with the wall-reaction smoke.
   All downstream recommendations assume a physically valid task.
1. Do not run a full Isaac install/evaluation through the current Brev GCP path.
2. Treat the AWS Isaac Launchable as technically validated but expensive; do not create another paid Brev/AWS/GPU environment unless there is an explicit budget and a deletion monitor is active.
   Local create scripts now also require `RCA_ALLOW_PAID_BREV_CREATE=1` before they will call `brev create`, and the paid CLI wrappers start `scripts/brev_paid_run_watchdog.sh` before creation. For UI Launchable runs, run `scripts/start_brev_ui_launchable_watchdog.sh` before clicking Create, or start `scripts/brev_paid_run_watchdog.sh` with a target name/id immediately after creation.
3. Do not run another paid sweep on the current scripted handoff / `preload-direction` family; full-quaternion, axis-aware, XY-retention, and joint-step limiter variants all failed closed before a useful post-handoff eval.
4. Keep Brev support focused on the separate `CreateWorkspace unexpected EOF` CLI create failure; that failure happens before SSH/Isaac/ports and is not explained by Launchable runtime behavior.
5. If another AWS Launchable is ever approved for a short validation of a new formulation, use the same smoke/runtime/deletion discipline:

```bash
docs/aws_isaac_launchable_runbook.md
scripts/create_launchable_bundle.sh
scripts/run_launchable_headless_smoke.sh
scripts/run_launchable_rca_diagnostic_matrix.sh
scripts/run_launchable_phase2_fresh_preload_direction.sh
   scripts/run_launchable_phase2_absik_handoff_probe.sh
   scripts/run_launchable_phase2_jointpos_nullspace_probe.sh
   scripts/run_launchable_phase2_jointpos_rotate_descend_probe.sh
   scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh
scripts/run_launchable_phase2_jointpos_reachable_guard_probe.sh
scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh
scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
scripts/analyze_rotation_polish_trace.py
scripts/run_brev_reachable_guard_probe.sh
```

6. If Brev support confirms the create API is healthy, rerun only a tiny probe first. No Isaac install, no evaluation:

```bash
RCA_ALLOW_DIRTY=1 scripts/run_brev_probe_direct_ssh_gate.sh
```

7. Do not rerun root-frame waypoint, orientation-current waypoint, full-target Abs IK, the single-joint `panda_joint4=-2.6` initial-posture diagnostic, no-wall-collision target diagnostics, simple target-offset variants, native IK solver-method variants, the current JointPos nullspace matrix, the current JointPos rotate-descend wrapper, `reachable-approach` unchanged, the strong reachable guard unchanged, the tuned reachable guard unchanged, the rotation-gated reachable guard unchanged, the soft-gated reachable guard unchanged, the depth-aware rotation polish wrapper unchanged, adaptive rotpolish unchanged, or near-depth rotgate unchanged. The no-wall run was worse than full-target baseline, the contact-force signal is not wall-only, target offsets did not improve true socket XY, `dls/pinv/svd/trans` all failed closed with the same `panda_joint4` signature, the JointPos nullspace probe did not activate its nullspace term while regressing depth, rotate-descend either fell into XY recovery or drifted laterally when recovery was disabled, reachable-approach still failed strict handoff while consuming `panda_joint4` margin, the strong guard preserved too much margin while stalling axial progress, the tuned guard improved depth but still missed z/contact/rotation gates, the rotation gate protected margin by over-freezing descent, the soft gate reached depth/contact but still missed rotation and late XY retention, depth-aware rotation polish preserved XY/Z but worsened rotation, adaptive rotpolish only slightly improved selected rotation while worsening final rotation, and near-depth rotgate still missed depth/rotation/contact together. No prepared non-duplicate scripted-controller candidate remains; the next work should change the formulation rather than launch another paid scripted probe.
   The legacy historical-replay script now fails closed unless `RCA_ALLOW_HISTORICAL_PRELOAD_REPLAY=1` is set for a deliberate replay-drift diagnostic.
8. Keep the fresh-preload guards enabled unless there is a specific diagnostic reason:

```text
RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS=1.0
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_LATERAL_DRIFT=0.02
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_AXIAL_DRIFT=0.02
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_ROT_DRIFT=0.25
```

9. If a new controller is implemented, run the Launchable smoke first, then a short eval with marker checks and immediate deletion.
10. Only run temporal residual-current BC after the demonstration labels show sustained post-contact behavior. Use `scripts/analyze_contact_demo_coverage.py` with local traces plus Launchable archives before any paid learned-policy run; the 2026-06-09 combined report still shows zero target-gate passing steps across 38 traces.
11. For the next local implementation, use `scripts/select_final_contact_reset_candidates.py` and `artifacts/reports/final_contact_reset_candidates_2026-06-09.json` as the seed source for a reset-based final-contact stabilizer/evaluator. Do not treat those candidates as success labels unless a future report contains `target_gate_success > 0`.
12. `scripts/evaluate_contact_bc_policy.py` can now consume the candidate manifest directly via `--preload-candidate-json`; use this for future stabilizer baselines so the handoff seed is reproducible.
13. `scripts/extract_final_contact_candidate_dataset.py` generated a candidate-window temporal residual-current dataset from the manifest. Use it only as a stabilization/reset prior unless new data adds strict-success samples.
14. Training `artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt` has not been completed locally because PyTorch is unavailable in the host Python. Run `scripts/train_contact_bc_policy.py` in the Isaac/PyTorch runtime if a local prior checkpoint is needed.
15. Use `scripts/run_remote_train_final_contact_candidate_bc.sh` and `scripts/run_remote_eval_final_contact_candidate_bc.sh` only on an already-running Isaac/PyTorch environment. They do not provision Brev and therefore should be paired with the existing paid-run watchdog only if a new environment has been deliberately created elsewhere.

## Main Files To Read First

- `README.md`
- `docs/phase2_il_contact_policy_plan.md`
- `docs/gpu_selection_policy.md`
- `docs/aws_isaac_launchable_runbook.md`
- `artifacts/analysis/launchable_probe_archive_summary_2026-05-26.md`
- `experiments/2026-05-18_phase2_contact_bc_smoke.md`
- `experiments/2026-05-19_phase2_contact_demo_coverage.md`
- `experiments/2026-05-20_phase2_bc_eval_trace_audit.md`
- `scripts/summarize_launchable_probe_archives.py`
- `scripts/select_reachable_approach_candidates.py`
- `scripts/run_guarded_phase2_gate.sh`
- `scripts/evaluate_contact_bc_policy.py`
- `scripts/extract_contact_demo_dataset.py`
- `scripts/run_phase2_contact_handoff_preload_direction_gate.sh`
