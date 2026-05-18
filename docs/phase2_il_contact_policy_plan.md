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

## Important Limitation

The current dataset is not enough for a strong final policy:

- it contains only one active shallow-success sample
- it contains zero strict-success samples
- all samples are from fixed-seed scripted rollouts
- the action target is still 7D joint position, not a compliance or force-control action

Therefore this dataset is a bootstrap / smoke dataset, not the final demonstration set.

## Next Data Collection

After the BC smoke is validated, collect more demonstrations by varying:

- seed
- socket pose around `[0.22, 0.04, 0.22]`
- reset posture near the successful contact window
- shallow success gate first, then stricter gates

The goal is not to keep tuning the scripted controller. The goal is to create enough diverse near-contact trajectories for a learned policy to imitate or fine-tune.

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
BC policy improves closest strict-gate miss score over scripted baseline
```

Strong milestone:

```text
BC or BC+RL policy achieves strict success_step != null
```
