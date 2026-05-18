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
