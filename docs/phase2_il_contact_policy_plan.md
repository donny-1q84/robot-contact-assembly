# Phase 2 IL / Learned Contact Policy Plan

## Decision

Stop spending GPU time on one-off scripted contact-retention heuristics. The current scripted branch has already produced:

- one shallow true-contact success
- a strict near miss within `0.20 mm` lateral and `0.0012 rad` rotation
- enough traces to show the remaining blocker is coupled contact control, not environment setup

The next technical step is to bootstrap a learned final-contact policy from the scripted traces.

## Dataset Source

Use existing pulled scripted traces under:

```text
artifacts/evaluations/scripted/
```

The first dataset should focus on the strongest JointPos + joint-IK branch because it produced the shallow success and the closest strict near miss.

Dataset extraction command:

```bash
python3 scripts/extract_contact_demo_dataset.py
```

Default output:

```text
artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl
artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.metadata.json
```

Current local extraction result:

```text
samples: 3922
observation_dim: 37
action_dim: 7
active shallow-success samples: 1
strict-success samples: 0
```

Observation fields:

```text
physical_tip_rel_socket_pos: 3
pos_error: 3
axis_angle_error: 3
contact_force_socket: 3
contact_force_magnitude: 1
lateral / axial / rot: 3
joint_pos: 7
joint_vel: 7
joint_limit_margin: 7
```

Action field:

```text
raw_action: 7D Franka joint-position target
```

## First BC Smoke

Training script:

```bash
python3 scripts/train_contact_bc_policy.py \
  --dataset artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl \
  --output artifacts/policies/phase2_contact_bc/bc_mlp.pt
```

This is intentionally a small MLP behavior-cloning baseline. It is not expected to solve strict insertion by itself. Its purpose is to verify:

- the dataset shape is stable
- weighted BC training runs
- a checkpoint with observation/action normalization is produced
- the project has a clean handoff from scripted traces to a learned contact-policy artifact

## First BC Eval Smoke

Evaluation script:

```bash
python3 scripts/evaluate_contact_bc_policy.py \
  --task RCA-PegInHole-Franka-JointPos-Contact-Play-v0 \
  --headless \
  --num_envs 1 \
  --steps 400 \
  --seed 42 \
  --checkpoint artifacts/policies/phase2_contact_bc/bc_mlp.pt \
  --deterministic-reset \
  --socket-pos 0.22,0.04,0.22 \
  --success-xy-tol 0.005 \
  --success-z-tol 0.045 \
  --success-rot-tol 0.18 \
  --success-min-contact-force 0.5 \
  --summary-json artifacts/evaluations/bc_policy/local_smoke/summary.json \
  --trace-json artifacts/evaluations/bc_policy/local_smoke/trace.json
```

This eval wrapper reconstructs the same `37D` observation vector used by the dataset extractor, runs the MLP policy, unnormalizes the predicted `7D` joint-position action, clamps it around the current joint state, and reports the same contact success metrics as the scripted gates.

Remote guarded smoke:

```bash
scripts/run_phase2_contact_bc_smoke_gate.sh
```

This one guarded GPU session does:

1. sync source code
2. upload the local JSONL dataset to `/workspace/artifacts/datasets/phase2_contact_bc/`
3. train `bc_mlp.pt`
4. evaluate the checkpoint under the strict shallow-contact gate
5. pull artifacts through the normal guarded cleanup flow

Completed remote smoke:

```text
run dir: artifacts/gpu_gate/2026-05-18T21-17-31Z_isaac-phase2-contact-bc-smoke-l4
checkpoint: artifacts/policies/phase2_contact_bc/bc_mlp.pt
eval: artifacts/evaluations/bc_policy/2026-05-18T21-34-10Z/summary.json
success_step: null
final_success_rate: 0.0
best_lateral: 0.00636 m
best_axial: 0.14536 m
best_rot: 0.52066 rad
best_strict_miss_score: 21.06919
```

Interpretation: the learned-policy pipeline works, but the naive all-trace BC policy is not a successful contact controller. It briefly reaches near-lateral alignment, then drifts instead of stabilizing insertion.

## Important Limitation

The current dataset is not enough for a strong final policy:

- it contains only one active shallow-success sample
- it contains zero strict-success samples
- all samples are from fixed-seed scripted rollouts
- the action target is still 7D joint position, not a compliance or force-control action

Therefore this dataset is a bootstrap / smoke dataset, not the final demonstration set.

## Next Data Collection

The BC smoke is validated. Do not re-run the same all-trace BC setup unchanged.

Before collecting more paid demonstrations, add a local `best-window` dataset profile that filters around the strongest shallow-success and closest near-miss windows. The next GPU comparison should be:

```text
all-traces BC vs best-window BC
```

Local `best-window` extraction:

```bash
python3 scripts/extract_contact_demo_dataset.py \
  --profile best-window \
  --output artifacts/datasets/phase2_contact_bc_best_window/phase2_contact_bc_best_window_dataset.jsonl
```

Current local result:

```text
samples: 314
selected windows:
- 2026-05-17T23-32-18Z step 1543, strict_miss_score 0.03205
- 2026-05-17T22-00-19Z step 1541, strict_miss_score 0.04206
```

Important: this profile is a contact-refinement dataset. It should be evaluated with either a scripted approach stage or a staged initialization near the selected contact window, not as a full reset-to-insertion policy.

The evaluator now supports the staged version through:

```text
--preload-trace-json
--preload-trace-start-step
--preload-trace-end-step
```

The first staged handoff should replay `2026-05-17T23-32-18Z/seed_42_trace.json` through step `1543`, then switch from scripted replay to the BC policy.

Prepared guarded remote wrapper:

```bash
scripts/run_phase2_contact_bc_best_window_smoke_gate.sh
```

This wrapper trains the best-window BC checkpoint and evaluates it with scripted trace preload through step `1543`, so it should be the next paid GPU run if we decide to compare learned refinement.

Completed staged best-window smoke:

```text
run dir: artifacts/gpu_gate/2026-05-19T05-45-11Z_isaac-phase2-contact-bc-best-window-l4
checkpoint: artifacts/policies/phase2_contact_bc_best_window/bc_mlp.pt
eval: artifacts/evaluations/bc_policy/2026-05-19T05-59-43Z/summary.json
success_step: null
bc_success_step: null
final_success_rate: 0.0
handoff_strict_miss_score: 0.03185
best_strict_miss_score_after_bc: 0.18654
final_lateral: 0.07267 m
final_axial: 0.04299 m
final_rot: 0.34532 rad
```

Interpretation: the staged learned-policy handoff infrastructure works, but the `314`-sample best-window BC policy is not a reliable final-contact controller. It starts from a near-success handoff and makes the contact state worse. Do not re-run this setup unchanged.

Then collect more demonstrations by varying:

- seed
- socket pose around `[0.22, 0.04, 0.22]`
- reset posture near the successful contact window
- shallow success gate first, then stricter gates

The goal is not to keep tuning the scripted controller. The goal is to create enough diverse near-contact trajectories for a learned policy to imitate or fine-tune.

## Updated Learned-Policy Direction

The next learned-policy attempt should change the problem formulation:

- Use the scripted controller as a base stabilizer and train a residual policy that predicts small corrections instead of full `7D` joint-position targets.
- Add temporal context, such as previous action and recent contact-force history, before expecting a one-step MLP to handle contact retention.
- Prioritize new demonstrations that include several seconds after near-success contact, because the current dataset mostly teaches approach into the window rather than stable insertion after handoff.
- Keep the shallow success gate as the first learned-policy target before returning to the strict gate.

Local residual-current preparation:

```bash
python3 scripts/extract_contact_demo_dataset.py \
  --profile best-window \
  --action-mode residual-current \
  --output artifacts/datasets/phase2_contact_bc_best_window_residual_current/phase2_contact_bc_best_window_residual_current_dataset.jsonl
```

Local result:

```text
samples: 314
observation_dim: 37
action_dim: 7
action_mode: residual-current
```

The next paid learned-policy run, if used, should be:

```bash
scripts/run_phase2_contact_bc_residual_current_smoke_gate.sh
```

This tests whether predicting small joint corrections from the current state is more stable than predicting absolute joint targets.

Remote status:

The first residual-current remote attempt on 2026-05-19 did not reach training. Brev returned `unexpected EOF` during workspace creation and exposed backend id `rx7dirywd`; guarded cleanup deleted it and independent audit showed `"workspaces": null`.

Completed near-contact residual-current smoke:

```text
run dir: artifacts/gpu_gate/2026-05-20T04-17-08Z_isaac-phase2-contact-bc-near-contact-residual-l4
checkpoint: artifacts/policies/phase2_contact_bc_near_contact_residual_current/bc_mlp.pt
eval: artifacts/evaluations/bc_policy/2026-05-20T04-32-33Z/summary.json
success_step: null
bc_success_step: null
handoff_miss: 0.03185
near_contact_fraction: 0.0175
longest_near_contact_streak: 6
best_strict_miss_score_after_bc: 0.31573
best_delta_vs_handoff: +0.28387
final_strict_miss_score: 45.58740
final_delta_vs_handoff: +45.55555
```

Interpretation: the larger `3187`-sample residual-current dataset slightly increased relaxed near-contact dwell time relative to the staged best-window BC run, but it still degraded the handoff state and eventually diverged. The useful conclusion is now negative: one-step BC on the current scripted trace archive is not sufficient for final-contact stabilization.

Do not repeatedly retry this run until either the Brev create-path stability improves or the next paid run is explicitly worth the remaining risk.

## Demonstration Coverage Audit

Added:

```bash
python3 scripts/analyze_contact_demo_coverage.py \
  --output-md experiments/2026-05-19_phase2_contact_demo_coverage.md \
  --output-json artifacts/analysis/phase2_contact_demo_coverage.json
```

Default scope:

```text
task filter: JointPos
since: 2026-05-17T00-00-00Z
target gate: xy<5mm, z<45mm, rot<0.18rad, contact>=0.5
near gate: xy<15mm, z<60mm, rot<0.35rad, contact>=0.2
```

Result:

```text
traces: 18
steps: 28823
target-gate passing steps: 0
traces with target-gate steps: 0
near-contact steps: 3227
traces with near-contact steps: 14
```

Interpretation:

The available mainline demonstrations are useful for approach and near-contact retention, but they do not contain successful target-gate insertion labels. This explains why one-step BC can fit the dataset and still destabilize after handoff: the data has many near-contact states, but no clean examples of the final successful stabilization behavior under the current target gate.

Prepared a larger near-contact residual-current dataset for a stabilization-prior smoke:

```bash
python3 scripts/extract_contact_demo_dataset.py \
  --since 2026-05-17T00-00-00Z \
  --task-contains JointPos \
  --max-lateral 0.015 \
  --max-axial 0.060 \
  --max-rot 0.35 \
  --min-contact 0.2 \
  --action-mode residual-current \
  --output artifacts/datasets/phase2_contact_bc_near_contact_residual_current/phase2_contact_bc_near_contact_residual_current_dataset.jsonl
```

Result:

```text
samples: 3187
traces: 14
active_success_samples: 1
strict_success_samples: 0
action_mode: residual-current
```

Remote wrapper:

```bash
scripts/run_phase2_contact_bc_near_contact_residual_current_smoke_gate.sh
```

This wrapper has now been run. It did not produce a successful controller, but it did establish the right diagnostic metrics for learned-policy handoff: sustained near-contact and post-handoff degradation.

Evaluator update:

`scripts/evaluate_contact_bc_policy.py` now reports near-contact stabilization metrics in addition to strict success:

```text
handoff_near_contact_rate
final_near_contact_rate
near_contact_step_count
near_contact_fraction
longest_near_contact_streak
first_near_contact_step
best_vs_handoff_strict_miss_delta
final_vs_handoff_strict_miss_delta
```

For the next residual-current smoke, a useful result is not necessarily `success_step != null`. A useful result is:

```text
near_contact_fraction improves and best/final miss does not degrade badly relative to handoff
```

## Existing BC Eval Trace Audit

Added:

```bash
python3 scripts/analyze_bc_eval_traces.py \
  --output-md experiments/2026-05-20_phase2_bc_eval_trace_audit.md \
  --output-json artifacts/analysis/phase2_bc_eval_trace_audit.json
```

Result:

```text
all-trace BC:
  bc_near_frac: 0.0000
  bc_longest_near: 0
  bc_best_miss: 21.0692
  bc_final_miss: 57.3366

staged best-window BC:
  handoff_miss: 0.0319
  bc_near_frac: 0.0125
  bc_longest_near: 5
  bc_best_miss: 0.1865
  bc_final_miss: 8.4199
  best_delta: +0.1547
  final_delta: +8.3880

staged near-contact residual-current BC:
  handoff_miss: 0.0319
  bc_near_frac: 0.0175
  bc_longest_near: 6
  bc_best_miss: 0.3157
  bc_final_miss: 45.5874
  best_delta: +0.2839
  final_delta: +45.5555
```

Interpretation:

The previous BC policies were not contact-stabilizing policies. The staged residual-current policy briefly improved relaxed near-contact dwell time, but it still made the strict handoff state worse and diverged by the end of the rollout. Do not spend another GPU cycle on the same one-step BC formulation.

## GPU Policy

Do not open GPU for dataset extraction; it is local.

Only open GPU for:

1. Additional demonstration collection with a fixed, measurable pass/fail condition.
2. A short learned-policy eval only after the policy formulation changes.
3. BC smoke training only if the dataset/action representation has changed materially.

Each paid run must still use the guarded Brev flow and final empty-org checks.

## Success Criteria For This Phase

Minimum useful milestone:

```text
scripted traces -> JSONL dataset -> BC checkpoint -> fixed-seed eval artifact
```

Better milestone:

```text
learned policy improves the post-handoff strict-gate miss score instead of degrading it
```

Strong milestone:

```text
BC or BC+RL policy achieves strict success_step != null
```

## Immediate Next Step

Do local controller and data work before opening another GPU instance:

1. Add a deterministic post-handoff hold/stabilization baseline. This gives a non-learning reference for whether a policy actually improves contact retention.
2. Extend the BC observation with temporal context: previous action, previous error, and recent contact-force history.
3. Generate new demonstrations that continue for several seconds after the near-success handoff instead of only reaching the handoff point.
4. Re-run the trace audit locally and require evidence of target-gate or sustained near-contact labels before the next paid GPU run.

Implemented local harness for step 1:

```bash
scripts/run_phase2_contact_handoff_hold_gate.sh
```

This guarded wrapper runs the same staged preload through step `1543`, then evaluates a deterministic controller through the existing contact-policy evaluator:

```text
--controller current-joint
```

It writes results under:

```text
artifacts/evaluations/contact_handoff_baseline/
```

Completed current-joint handoff baseline:

```text
run dir: artifacts/gpu_gate/2026-05-20T19-34-58Z_isaac-phase2-contact-handoff-hold-l4
eval: artifacts/evaluations/contact_handoff_baseline/2026-05-20T19-52-13Z_current-joint/summary.json
controller: current-joint
success_step: null
handoff_miss: 0.03185
near_contact_fraction: 0.0000
longest_near_contact_streak: 0
best_strict_miss_score_after_handoff: 0.44359
best_delta_vs_handoff: +0.41174
final_strict_miss_score: 58.88280
final_delta_vs_handoff: +58.85095
```

Interpretation: simply holding the measured joint position is worse than both staged BC variants. It immediately loses the relaxed contact-force condition and never re-enters near-contact. The handoff state is therefore not a stable passive contact state; it requires active maintenance.

Implemented local harness for step 2:

```bash
python3 scripts/extract_contact_demo_dataset.py \
  --since 2026-05-17T00-00-00Z \
  --task-contains JointPos \
  --max-lateral 0.015 \
  --max-axial 0.060 \
  --max-rot 0.35 \
  --min-contact 0.2 \
  --action-mode residual-current \
  --history-steps 2 \
  --output artifacts/datasets/phase2_contact_bc_near_contact_temporal_residual_current/phase2_contact_bc_near_contact_temporal_residual_current_dataset.jsonl
```

Local result:

```text
samples: 3187
observation_dim: 77
action_dim: 7
observation_mode: temporal-history
history_steps: 2
active_success_samples: 1
strict_success_samples: 0
```

The additional observation terms are the two most recent snapshots of:

```text
raw_action
pos_error
axis_angle_error
contact_force_socket
contact_force_magnitude
lateral / axial / rot
```

Prepared guarded wrapper:

```bash
scripts/run_phase2_contact_bc_temporal_residual_current_smoke_gate.sh
```

Status: dataset and wrapper are prepared and syntax-checked, but not yet run on GPU. This is a materially different learned-policy hypothesis than the failed one-step `37D` residual-current BC run.

Follow-up static-hold attempt:

```text
run dir: artifacts/gpu_gate/2026-05-20T20-02-49Z_isaac-phase2-contact-handoff-last-action-l4
controller: last-preload-action
status: aborted during Brev provisioning before Isaac runtime or eval
instance id: a8i77l2b3
cleanup: confirmed no visible instances, JSON workspaces=null
```

This is not a robotics result. It only shows that the Brev lifecycle can still stall during create/delete, so the next wrapper should use a shorter readiness window.

Implemented local harness for an active non-learning baseline:

```bash
scripts/run_phase2_contact_handoff_preload_direction_gate.sh
```

This wrapper evaluates:

```text
--controller preload-direction
```

The controller uses the last two scripted preload actions to estimate the final joint-space insertion direction, then applies:

```text
joint_delta =
  preload_direction_hold_gain * (last_preload_action - current_joint_pos)
  + preload_direction_scale * (last_preload_action - penultimate_preload_action)
```

with `--max-action-delta 0.02`.

Updated priority:

The first `preload-direction` GPU attempt also aborted during Brev provisioning:

```text
run dir: artifacts/gpu_gate/2026-05-20T20-30-57Z_isaac-phase2-contact-handoff-preload-dir-l4
controller: preload-direction
status: aborted before SSH / Isaac runtime / eval
instance id: 8ewsb9mo9
reason: RUNNING / BUILDING / NOT READY for 185s
cleanup: confirmed no visible instances, JSON workspaces=null
```

This is not a controller result. It indicates the compute backend is currently the blocker.

Updated priority:

1. Do not open another Brev GPU instance immediately.
2. Keep `preload-direction` as the next robotics eval once the GPU backend is stable.
3. Before the next paid Isaac run, do a tiny provider smoke that only creates, SSH-probes, and deletes the chosen instance.
4. If `preload-direction` preserves near-contact longer than BC/current-joint, use it to generate post-contact demonstrations.
5. If it also fails after a valid eval, stop deterministic joint-position baselines and move to richer demonstrations or a Cartesian/IK contact-maintenance controller.
6. Only run the temporal residual-current BC smoke after the demonstration labels contain sustained near-contact behavior.
