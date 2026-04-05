# Phase 1 RL Baseline Record

## Run Summary

- Date: 2026-04-05
- Owner: Shenghan Gao
- Goal: Close Phase 1 into a CV-ready PPO baseline for `peg-in-hole`
- Remote env: `isaac-l40s`

## Fixed Configuration

- Task ID: `RCA-PegInHole-Franka-IK-Rel-v0`
- Experiment name: `franka_peg_in_hole`
- Successful smoke run name: `smoke32`
- Formal run name: `phase1_formal`
- Seed: `42`
- Num envs:
  - successful smoke: `32`
  - formal train: `256`
  - eval: `32`
  - video: `1`
- Max iterations:
  - successful smoke: `10`
  - formal train: `300`
- Eval steps:
  - smoke eval: `200`
  - formal eval: `400`
- Extra train args:
- Extra eval args:

## Smoke Training Command

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 10 42 smoke32
```

## Smoke Evaluation Command

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 200 42 '.*smoke32.*' 'model_9.pt'
```

## Formal Training Command

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 256 300 42 phase1_formal
```

## Formal Evaluation Command

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 400 42 '.*phase1_formal.*' 'model_.*.pt'
```

## Video Command

```bash
./scripts/run_remote_record_video.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 1 400 42 '.*phase1_formal.*' 'model_.*.pt'
```

## Runtime Manifest Command

```bash
./scripts/capture_remote_runtime_manifest.sh
./scripts/pull_artifacts.sh
```

## Key Artifacts

- Train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T13-16-13Z_smoke32/train.log`
- Train command: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T13-16-13Z_smoke32/train_command.txt`
- Train metadata: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T13-16-13Z_smoke32/train_metadata.env`
- Best checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/logs/rsl_rl/franka_peg_in_hole/2026-04-05_13-16-20_smoke32/model_9.pt`
- Eval summary JSON: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T13-24-28Z/summary.json`
- Eval command: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T13-24-28Z/eval_command.txt`
- Eval log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T13-24-28Z/eval.log`
- Video command: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/videos/policy/2026-04-05T13-24-56Z/record_command.txt`
- Video directory: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/videos/policy/2026-04-05T13-24-56Z`
- Runtime manifest:
- Pulled artifact root: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts`

## Results

- Smoke status: `passed`
- Formal train status: `not started`
- Final success rate: `0.000`
- Best success rate: `0.000`
- Final lateral error: `0.4548`
- Final axial error: `0.2093`
- Final rotation error: `2.0887`
- Best checkpoint: `model_9.pt` from `2026-04-05_13-16-20_smoke32`

## Failure Modes

- `256 envs / 30 iters` was too heavy for first-pass smoke validation and was stopped to avoid wasting budget before dependency/runtime fixes were complete.
- The first custom evaluator path was broken in two places: environment launch flow and `rsl-rl >= 4.0` policy access. Both were fixed locally.
- Automated video recording with rendering kit started but never emitted frames or step logs; the run was canceled to avoid wasting GPU time. No usable MP4 was produced in this smoke session.

## Next Decision

- Ship this result to README / CV
- Tune reward or curriculum
- Change controller / environment contract
- Start the first formal PPO training run only after deciding the remaining GPU budget
