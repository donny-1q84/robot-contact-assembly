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

## GPU Policy

Do not open GPU for dataset extraction; it is local.

Only open GPU for:

1. BC smoke training if local PyTorch is unavailable or too slow.
2. A short learned-policy eval once a checkpoint exists.
3. Additional demonstration collection with a fixed, measurable pass/fail condition.

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
