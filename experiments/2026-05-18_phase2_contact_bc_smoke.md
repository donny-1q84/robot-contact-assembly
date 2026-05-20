# Phase 2 Contact BC Smoke

Date: 2026-05-18

## Goal

Validate the first learned-policy handoff:

```text
scripted true-contact traces -> JSONL dataset -> BC checkpoint -> fixed-seed true-contact eval
```

This was a pipeline smoke test, not a final policy training run.

## Preflight

- Brev org: `NCA-57cf-29515`
- Target profile: `cheap`
- Target instance type: `g2-standard-4:nvidia-l4:1`
- Listed price during preflight: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Dataset: `artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl`
- Dataset samples: `3922`
- Observation/action dims: `37 -> 7`
- Dataset strict-success samples: `0`
- Dataset active shallow-success samples: `1`

## Attempt 1: Upload Permission Failure

Run dir:

```text
artifacts/gpu_gate/2026-05-18T20-34-20Z_isaac-phase2-contact-bc-smoke-l4
```

Failure:

```text
mkdir: cannot create directory '/home/ubuntu/projects/robot-contact-assembly/artifacts/datasets': Permission denied
```

Root cause:

The remote Isaac container bind-mounted `${REMOTE_ROOT}/artifacts` to `/workspace/artifacts` and then `chown`ed the mounted directory for container use. The SSH user `ubuntu` could no longer create the dataset subdirectory on the host path.

Fix:

`scripts/run_remote_train_contact_bc_policy.sh` now maps `/workspace/artifacts/...` back to `${REMOTE_ROOT}/artifacts/...` and uploads with `sudo mkdir` plus `sudo rsync`.

Commit:

```text
959a4e2 Fix BC dataset upload permissions
```

Cleanup:

Brev eventually confirmed no visible instances.

## Attempt 2: Brev EOF During Create

Run dir:

```text
artifacts/gpu_gate/2026-05-18T21-13-57Z_isaac-phase2-contact-bc-smoke-l4
```

Failure:

```text
unexpected EOF
```

The CLI reported create failure, but a backend workspace id appeared:

```text
n9accol9z
```

Cleanup:

The guarded cleanup deleted by both workspace name and id. Brev then confirmed no visible instances.

Interpretation:

This matches the Brev support explanation from earlier incidents: a temporary network interruption can make the CLI report a failed create while the backend has partially accepted the request.

## Attempt 3: Successful BC Smoke

Run dir:

```text
artifacts/gpu_gate/2026-05-18T21-17-31Z_isaac-phase2-contact-bc-smoke-l4
```

Instance:

```text
name: isaac-phase2-contact-bc-smoke-l4
id: si6rxkwjj
type: g2-standard-4:nvidia-l4:1
gpu: L4
```

Training artifacts:

```text
artifacts/policies/phase2_contact_bc/bc_mlp.pt
artifacts/policies/phase2_contact_bc/bc_mlp.metadata.json
artifacts/policies/phase2_contact_bc/train.log
artifacts/policies/phase2_contact_bc/train_command.txt
```

BC training result:

```text
epochs: 250
train_loss: 0.000122
val_loss: 0.000195
best_val_loss: 0.00019504809461068362
```

Evaluation artifacts:

```text
artifacts/evaluations/bc_policy/2026-05-18T21-34-10Z/summary.json
artifacts/evaluations/bc_policy/2026-05-18T21-34-10Z/trace.json
artifacts/evaluations/bc_policy/2026-05-18T21-34-10Z/eval.log
artifacts/evaluations/bc_policy/2026-05-18T21-34-10Z/eval_command.txt
```

Eval command used strict shallow-contact thresholds:

```text
xy < 0.005 m
z < 0.045 m
rot < 0.18 rad
contact >= 0.5 N
```

Evaluation result:

```text
success_step: null
final_success_rate: 0.0
best_lateral: 0.006358198821544647 at step 226
best_axial: 0.145359605550766 at step 282
best_rot: 0.5206574201583862 at step 344
best_strict_miss_score: 21.06919049918652 at step 240
max_contact_force_magnitude: 3.203319549560547 at step 138
final_lateral: 0.2980678081512451
final_axial: 0.26261621713638306
final_rot: 0.7595453858375549
```

Cleanup:

Brev confirmed no visible instances after delete.

## Interpretation

What succeeded:

- The guarded Brev flow can run BC train and eval end to end.
- Dataset upload into the remote `/workspace/artifacts` mount works after the permission fix.
- The BC trainer produces a checkpoint and metadata from the scripted trace dataset.
- The BC evaluator can reconstruct the same `37D` observation vector and execute a learned `7D` joint-position policy in the true-contact environment.
- All artifacts are pulled back locally before deleting the GPU instance.

What failed:

- The naive BC policy did not achieve strict or shallow success.
- It reduced lateral error to `6.36 mm` once, but axial and rotation were still far outside the gate.
- After the near-lateral alignment point, the policy drifted away instead of stabilizing contact and inserting.

Likely causes:

- The dataset has only `1` active shallow-success sample and `0` strict-success samples.
- The dataset mixes failed trajectories with the one shallow-success trace.
- The policy is one-step BC, so it imitates actions without a stabilizing closed-loop objective.
- The action target is absolute-ish joint-position behavior from scripted traces, not a compliance/contact action.

## Decision

Do not spend another GPU cycle on the same BC setup unchanged.

Next work should be local first:

1. Add dataset filtering modes so the first BC policy can train only on the best shallow-success trace or closest near-miss windows.
2. Add a `best-window` dataset profile around the closest successful/near-success timesteps instead of mixing all phases from all traces.
3. Add evaluation diagnostics that report the best composite gate margin, not only per-metric minima.
4. Only after those local changes, run one more guarded GPU smoke to compare:

```text
all-traces BC vs best-window BC
```

The immediate next target is not `success_step != null`; it is showing that the learned policy improves the closest-gate score over this naive BC baseline.

## Local Follow-Up

Implemented a `best-window` dataset profile in `scripts/extract_contact_demo_dataset.py`.

Generation command:

```bash
python3 scripts/extract_contact_demo_dataset.py \
  --profile best-window \
  --output artifacts/datasets/phase2_contact_bc_best_window/phase2_contact_bc_best_window_dataset.jsonl
```

Local result:

```text
samples: 314
observation_dim: 37
action_dim: 7
active_success_samples: 0
strict_success_samples: 0
```

Selected windows:

```text
2026-05-17T23-32-18Z step 1543 score 0.03205 lateral 0.00520 axial 0.04126 rot 0.18121 contact 0.52982
2026-05-17T22-00-19Z step 1541 score 0.04206 lateral 0.00434 axial 0.04123 rot 0.18421 contact 0.52631
```

This is intentionally a contact-refinement dataset. It should not be evaluated as a full reset-to-insertion policy without either an approach stage or staged initialization.

Implemented the staged option in `scripts/evaluate_contact_bc_policy.py`:

```text
--preload-trace-json
--preload-trace-start-step
--preload-trace-end-step
```

Prepared first staged handoff:

```text
preload trace: artifacts/evaluations/scripted/2026-05-17T23-32-18Z/seed_42_trace.json
preload end step: 1543
handoff state from trace: lateral 0.00520, axial 0.04126, rot 0.18121, contact 0.52982
```

Prepared guarded wrapper:

```bash
scripts/run_phase2_contact_bc_best_window_smoke_gate.sh
```

The next paid run should train the `best-window` BC checkpoint and evaluate it only after the scripted replay handoff. The pass condition is improvement over the naive BC smoke's `best_strict_miss_score=21.06919`, not immediate strict success.

## Attempt 4: Staged Best-Window BC Smoke

Date: 2026-05-19

Goal:

Validate the contact-refinement version of the learned-policy handoff:

```text
scripted replay to near-success window -> best-window BC policy -> strict shallow-contact eval
```

This run should not be interpreted as a reset-to-insertion policy test. The best-window dataset only contains local contact-refinement samples around the strongest near-success windows.

### Create Retry

The first create attempt failed during Brev instance creation:

```text
run dir: artifacts/gpu_gate/2026-05-19T05-42-03Z_isaac-phase2-contact-bc-best-window-l4
error: unexpected EOF
backend id observed during cleanup: kp40fi7fm
```

Cleanup deleted by both instance name and id. Brev then confirmed:

```text
No instances in org NCA-57cf-29515
JSON: { "workspaces": null }
```

Interpretation:

This is the same Brev create-path failure mode previously confirmed by Brev support: the CLI can lose the final response while the backend has partially accepted a workspace create request. The guarded cleanup path handled it correctly.

### Successful Run

Run dir:

```text
artifacts/gpu_gate/2026-05-19T05-45-11Z_isaac-phase2-contact-bc-best-window-l4
```

Instance:

```text
name: isaac-phase2-contact-bc-best-window-l4
id: yeqmoahzv
type: g2-standard-4:nvidia-l4:1
gpu: L4
listed price: $0.85/hr
```

Dataset:

```text
artifacts/datasets/phase2_contact_bc_best_window/phase2_contact_bc_best_window_dataset.jsonl
samples: 314
obs_dim: 37
action_dim: 7
selected windows:
- 2026-05-17T23-32-18Z step 1543
- 2026-05-17T22-00-19Z step 1541
```

Training artifacts:

```text
artifacts/policies/phase2_contact_bc_best_window/bc_mlp.pt
artifacts/policies/phase2_contact_bc_best_window/bc_mlp.metadata.json
artifacts/policies/phase2_contact_bc_best_window/train.log
artifacts/policies/phase2_contact_bc_best_window/train_command.txt
```

BC training result:

```text
epochs: 300
train_loss: 0.001471
val_loss: 0.002569
best_val_loss: 0.002461758442223072
```

Evaluation artifacts:

```text
artifacts/evaluations/bc_policy/2026-05-19T05-59-43Z/summary.json
artifacts/evaluations/bc_policy/2026-05-19T05-59-43Z/trace.json
artifacts/evaluations/bc_policy/2026-05-19T05-59-43Z/eval.log
artifacts/evaluations/bc_policy/2026-05-19T05-59-43Z/eval_command.txt
```

Staged handoff:

```text
preload trace: artifacts/evaluations/scripted/2026-05-17T23-32-18Z/seed_42_trace.json
preload steps executed: 1544
handoff lateral: 0.005198 m
handoff axial: 0.041265 m
handoff rot: 0.181203 rad
handoff contact: 0.530984
handoff strict_miss_score: 0.031854
```

Evaluation result after switching to BC:

```text
success_step: null
bc_success_step: null
final_success_rate: 0.0
best_lateral: 0.006824 m at step 0
best_axial: 0.041086 m at step 6
best_rot: 0.161221 rad at step 13
best_strict_miss_score: 0.186539 at step 0
final_lateral: 0.072666 m
final_axial: 0.042993 m
final_rot: 0.345323 rad
max_contact_force_magnitude: 1.209288
```

Cleanup:

The artifact pullback completed before shutdown. Brev deletion stayed visible as `DELETING` for several polling rounds, then the guarded cleanup confirmed:

```text
No instances in org NCA-57cf-29515
JSON: { "workspaces": null }
```

### Interpretation

What succeeded:

- The `best-window` dataset profile, BC trainer, staged evaluator, preload trace upload, artifact pullback, and guarded deletion path all work end to end.
- The checkpoint learned the tiny dataset distribution in the supervised sense.
- The staged evaluator correctly replays a scripted near-success trace before handing control to a learned policy.

What failed:

- The learned BC policy did not achieve strict success.
- The policy did not improve the handoff state. It started from a near-success `strict_miss_score=0.031854`, but the best score after BC control was `0.186539`.
- The policy quickly lost lateral/contact stability. By the end of the rollout, lateral error had grown to `72.7 mm`.

Important comparison:

The staged best-window BC score is numerically much better than the naive all-trace reset eval (`0.1865` vs `21.0692`), but this is mostly because the staged eval starts from a preloaded near-success state. The meaningful comparison is against the handoff state itself, and by that measure the BC policy made the state worse.

### Decision

Do not spend another GPU cycle on the same `314`-sample best-window BC setup unchanged.

The current learned-policy conclusion is:

```text
BC infrastructure works; small-window one-step BC is not yet a reliable final-contact controller.
```

Next work should change the data/control problem, not just re-run this training:

1. Collect more near-contact demonstrations with actual post-handoff stabilization labels.
2. Add a residual policy formulation where the scripted controller remains the stabilizing base action and the learned policy predicts a small correction.
3. Add temporal context or action history beyond the current one-step MLP.
4. Only then run another paid BC/IL smoke.

## Local Follow-Up: Residual-Current Action Mode

Implemented a first residual action representation:

```text
action_mode: residual-current
target: raw_action - current_joint_pos
```

This is a smaller local step toward residual contact control. It does not yet use the full scripted controller as a base action, but it changes the learned target from an absolute joint-position command into a bounded correction around the current robot state.

Generation command:

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
active_success_samples: 0
strict_success_samples: 0
```

Training could not be run locally because this machine's active Python does not have PyTorch installed. The next guarded remote wrapper is prepared:

```bash
scripts/run_phase2_contact_bc_residual_current_smoke_gate.sh
```

## Attempt 5: Residual-Current Remote Create Failure

Date: 2026-05-19

Goal:

Run the prepared residual-current BC smoke on the same low-cost L4 instance type.

Run dir:

```text
artifacts/gpu_gate/2026-05-19T06-14-46Z_isaac-phase2-contact-bc-residual-current-l4
```

Failure:

```text
error: unexpected EOF
backend id observed during cleanup: rx7dirywd
```

Result:

No BC training or Isaac evaluation ran. The failure occurred during Brev workspace creation.

Cleanup:

The guarded script deleted by both instance name and id. Independent post-run audit confirmed:

```text
No instances in org NCA-57cf-29515
JSON: { "workspaces": null }
```

Decision:

Do not immediately retry the residual-current run in a loop. The code path is prepared, but repeated Brev create-path EOFs are now a cost/risk issue rather than a robotics issue.

## Attempt 6: Near-Contact Residual-Current Smoke

Date: 2026-05-20

Goal:

Train on the larger near-contact residual-current dataset and test whether a one-step MLP can preserve the staged near-contact handoff better than the earlier all-trace and best-window BC policies.

Preflight:

```text
Brev org: NCA-57cf-29515
Selected profile: cheap
Selected instance type: g2-standard-4:nvidia-l4:1
Listed price during preflight: $0.85/hr
Task: RCA-PegInHole-Franka-JointPos-Contact-Play-v0
Dataset: artifacts/datasets/phase2_contact_bc_near_contact_residual_current/phase2_contact_bc_near_contact_residual_current_dataset.jsonl
Dataset samples: 3187
Action mode: residual-current
```

Run dir:

```text
artifacts/gpu_gate/2026-05-20T04-17-08Z_isaac-phase2-contact-bc-near-contact-residual-l4
```

Instance:

```text
name: isaac-phase2-contact-bc-near-contact-residual-l4
id: idlgz45tf
type: g2-standard-4:nvidia-l4:1
gpu: L4
```

Training artifacts:

```text
artifacts/policies/phase2_contact_bc_near_contact_residual_current/bc_mlp.pt
artifacts/policies/phase2_contact_bc_near_contact_residual_current/bc_mlp.metadata.json
artifacts/policies/phase2_contact_bc_near_contact_residual_current/train.log
artifacts/policies/phase2_contact_bc_near_contact_residual_current/train_command.txt
```

BC training result:

```text
epochs: 300
num_samples: 3187
train_samples: 2709
val_samples: 478
best_val_loss: 0.03591490909457207
```

Evaluation artifacts:

```text
artifacts/evaluations/bc_policy/2026-05-20T04-32-33Z/summary.json
artifacts/evaluations/bc_policy/2026-05-20T04-32-33Z/trace.json
artifacts/evaluations/bc_policy/2026-05-20T04-32-33Z/eval.log
artifacts/evaluations/bc_policy/2026-05-20T04-32-33Z/eval_command.txt
```

Staged handoff state:

```text
handoff_lateral: 0.005198 m
handoff_axial: 0.041265 m
handoff_rot: 0.181203 rad
handoff_contact_force_magnitude: 0.530984 N
handoff_strict_miss_score: 0.031854
handoff_near_contact_rate: 1.000
```

BC rollout result:

```text
success_step: null
bc_success_step: null
final_success_rate: 0.0
near_contact_fraction: 0.0175
near_contact_step_count: 7 / 400
longest_near_contact_streak: 6
best_strict_miss_score: 0.315726
best_vs_handoff_strict_miss_delta: +0.283872
final_strict_miss_score: 45.587402
final_vs_handoff_strict_miss_delta: +45.555549
final_lateral: 0.271593 m
final_axial: 0.007078 m
final_rot: 2.072810 rad
max_contact_force_magnitude: 24.307920 N
```

Cleanup:

The artifact pullback completed before shutdown. Brev showed the instance as `DELETING` for several polling rounds and briefly flipped back to `DEPLOYING`, then the guarded cleanup re-issued delete by both name and id. Independent post-run checks confirmed:

```text
No instances in org NCA-57cf-29515
JSON: { "workspaces": null }
```

### Interpretation

What succeeded:

- The guarded low-cost L4 workflow completed end to end again.
- The larger residual-current dataset trained successfully and produced a checkpoint plus metadata.
- The staged evaluator confirmed the scripted handoff starts inside the relaxed near-contact band.
- The new near-contact metrics correctly captured short-term retention after BC handoff.

What failed:

- The learned policy still did not achieve strict success.
- It only stayed in the relaxed near-contact band for `7 / 400` BC-controlled steps.
- It made the handoff state worse: best miss increased from `0.031854` to `0.315726`, and final miss increased to `45.587402`.
- The failure mode is lateral and orientation drift after handoff, not lack of dataset fitting.

Comparison:

```text
all-trace BC:
  near_contact_fraction: 0.0000
  best_miss: 21.0692
  final_miss: 57.3366

staged best-window BC:
  near_contact_fraction: 0.0125
  longest_near_contact_streak: 5
  best_delta_vs_handoff: +0.1547
  final_delta_vs_handoff: +8.3880

staged near-contact residual-current BC:
  near_contact_fraction: 0.0175
  longest_near_contact_streak: 6
  best_delta_vs_handoff: +0.2839
  final_delta_vs_handoff: +45.5555
```

The residual-current formulation marginally improved relaxed near-contact dwell time, but it degraded the strict-gate score more than the smaller best-window policy. This is not a useful learned controller yet.

### Decision

Stop running one-step BC variants on the current trace archive.

The current evidence says the blocker is not GPU training or artifact plumbing. The blocker is that the demonstrations do not contain enough successful post-contact stabilization behavior, and the policy class has no temporal or stabilizing structure.

Next work should be local-first:

1. Add a controller-side hold/stabilization baseline at the handoff state, so learned policies are compared against a non-learning contact retention baseline.
2. Add temporal context to the BC observation, such as previous actions and recent contact-force history.
3. Collect new demonstrations that intentionally remain in near-contact for several seconds after the best scripted handoff instead of stopping at the closest point.
4. Only open GPU again once the next run has a different hypothesis than "more one-step BC on the same labels."

## Local Follow-Up: Post-Handoff Hold Baseline Harness

Implemented a deterministic non-learning baseline path for the next comparison.

Code changes:

```text
scripts/evaluate_contact_bc_policy.py
scripts/run_remote_eval_contact_handoff_baseline.sh
scripts/run_phase2_contact_handoff_hold_gate.sh
scripts/run_guarded_phase2_gate.sh
```

New evaluator modes:

```text
--controller bc
--controller current-joint
--controller last-preload-action
```

Purpose:

The current BC failures are only meaningful if they are compared against a simple hold baseline at the same handoff state. If `current-joint` or `last-preload-action` holds near-contact longer than BC, the learned policy is objectively worse than a non-learning stabilizer. If the hold baseline also fails quickly, the contact state itself is dynamically unstable and the next work should focus on controller compliance or better post-contact data.

Prepared guarded command:

```bash
scripts/run_phase2_contact_handoff_hold_gate.sh
```

Status:

The harness is implemented and syntax-checked, but not yet run on GPU.

## Local Follow-Up: Temporal Residual-Current Dataset

Implemented temporal-context support in the BC dataset, trainer, and evaluator.

Code changes:

```text
scripts/extract_contact_demo_dataset.py
scripts/train_contact_bc_policy.py
scripts/evaluate_contact_bc_policy.py
scripts/run_phase2_contact_bc_temporal_residual_current_smoke_gate.sh
```

New dataset option:

```text
--history-steps 2
```

Generated local dataset:

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

Interpretation:

The previous residual-current run used a memoryless `37D` observation and diverged after handoff. This new dataset keeps the same near-contact sample set but adds two previous-step snapshots of action, pose error, contact force, and insertion metrics. It gives the next BC policy a chance to infer drift direction and contact trend instead of reacting only to the instantaneous state.

Prepared guarded command:

```bash
scripts/run_phase2_contact_bc_temporal_residual_current_smoke_gate.sh
```

Status:

The dataset and wrapper are prepared and syntax-checked, but not yet run on GPU.

## Attempt 7: Post-Handoff Current-Joint Hold Baseline

Date: 2026-05-20

Goal:

Evaluate a deterministic non-learning baseline at the same staged handoff state used by BC. This answers whether the near-success handoff can be held by simply commanding the measured joint positions, without any learned correction.

Preflight:

```text
Brev org: NCA-57cf-29515
Selected profile: cheap
Selected instance type: g2-standard-4:nvidia-l4:1
Listed price during preflight: $0.85/hr
Task: RCA-PegInHole-Franka-JointPos-Contact-Play-v0
Controller: current-joint
Preload trace: artifacts/evaluations/scripted/2026-05-17T23-32-18Z/seed_42_trace.json
Preload end step: 1543
```

Run dir:

```text
artifacts/gpu_gate/2026-05-20T19-34-58Z_isaac-phase2-contact-handoff-hold-l4
```

Instance:

```text
name: isaac-phase2-contact-handoff-hold-l4
id: eh3tyfddz
type: g2-standard-4:nvidia-l4:1
gpu: L4
```

Evaluation artifacts:

```text
artifacts/evaluations/contact_handoff_baseline/2026-05-20T19-52-13Z_current-joint/summary.json
artifacts/evaluations/contact_handoff_baseline/2026-05-20T19-52-13Z_current-joint/trace.json
artifacts/evaluations/contact_handoff_baseline/2026-05-20T19-52-13Z_current-joint/eval.log
artifacts/evaluations/contact_handoff_baseline/2026-05-20T19-52-13Z_current-joint/eval_command.txt
```

Staged handoff state:

```text
handoff_lateral: 0.005198 m
handoff_axial: 0.041265 m
handoff_rot: 0.181203 rad
handoff_contact_force_magnitude: 0.530984 N
handoff_strict_miss_score: 0.031854
handoff_near_contact_rate: 1.000
```

Hold rollout result:

```text
success_step: null
near_contact_fraction: 0.0000
near_contact_step_count: 0 / 400
longest_near_contact_streak: 0
best_strict_miss_score: 0.443591
best_vs_handoff_strict_miss_delta: +0.411738
final_strict_miss_score: 58.882805
final_vs_handoff_strict_miss_delta: +58.850951
final_lateral: 0.246677 m
final_axial: 0.165500 m
final_rot: 2.397971 rad
max_contact_force_magnitude: 0.089430 N
```

Cleanup:

The artifact pullback completed before shutdown. Brev showed the instance as `DELETING`/`STOPPING` for several polling rounds, then the guarded cleanup re-issued delete by both name and id. Independent post-run checks confirmed:

```text
No instances in org NCA-57cf-29515
JSON: { "workspaces": null }
```

### Interpretation

What succeeded:

- The non-learning handoff baseline wrapper works end to end.
- The run uses the same staged preload and same strict/near-contact metrics as BC, so the comparison is fair.
- Artifact pullback and deletion worked.

What failed:

- `current-joint` hold did not preserve near-contact.
- Contact force dropped below the `0.2 N` near-contact threshold immediately after handoff.
- It never entered the relaxed near-contact band during the 400-step hold rollout.
- Around step `225`, the peg/socket state jumped to the same large-error basin seen in previous failed rollouts.

Comparison against learned BC:

```text
staged best-window BC:
  near_contact_fraction: 0.0125
  longest_near_contact_streak: 5
  best_delta_vs_handoff: +0.1547
  final_delta_vs_handoff: +8.3880

staged near-contact residual-current BC:
  near_contact_fraction: 0.0175
  longest_near_contact_streak: 6
  best_delta_vs_handoff: +0.2839
  final_delta_vs_handoff: +45.5555

current-joint hold:
  near_contact_fraction: 0.0000
  longest_near_contact_streak: 0
  best_delta_vs_handoff: +0.4117
  final_delta_vs_handoff: +58.8510
```

The hold baseline is worse than both learned BC variants on short near-contact dwell time. However, all three fail. This means the next blocker is not just policy overfitting; the staged handoff is a marginal contact state that needs active contact maintenance, compliance, or better post-contact demonstrations.

### Decision

Do not run another static hold baseline unchanged.

Next useful work should target active stabilization:

1. Compare `last-preload-action` hold once, because it may preserve the scripted preload better than `current-joint`.
2. Add a small deterministic contact-maintenance controller that keeps downward preload and bounded lateral correction.
3. Use that controller to generate post-contact demonstrations with sustained contact labels.
4. Then run temporal residual-current BC against those richer labels.
