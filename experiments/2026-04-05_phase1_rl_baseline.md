# Phase 1 RL Baseline Record

## Run Summary

- Date: 2026-04-05
- Owner: Shenghan Gao
- Goal: Close Phase 1 into a CV-ready PPO baseline for `peg-in-hole`
- Remote env: `isaac-l40s`

## Fixed Configuration

- Task ID: `RCA-PegInHole-Franka-IK-Rel-v0`
- Experiment name: `franka_peg_in_hole`
- Smoke run name: `smoke`
- Formal run name: `phase1_formal`
- Seed: `42`
- Num envs:
  - smoke: `256`
  - formal train: `256`
  - eval: `32`
  - video: `1`
- Max iterations:
  - smoke: `30`
  - formal train: `300`
- Eval steps: `400`
- Extra train args:
- Extra eval args:

## Smoke Training Command

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 256 30 42 smoke
```

## Smoke Evaluation Command

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 200 42 '.*smoke.*' 'model_.*.pt'
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

- Train log:
- Train command:
- Train metadata:
- Best checkpoint:
- Eval summary JSON:
- Eval command:
- Eval log:
- Video command:
- Video directory:
- Runtime manifest:
- Pulled artifact root: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts`

## Results

- Smoke status:
- Formal train status:
- Final success rate:
- Best success rate:
- Final lateral error:
- Final axial error:
- Final rotation error:
- Best checkpoint:

## Failure Modes

- 

## Next Decision

- Ship this result to README / CV
- Tune reward or curriculum
- Change controller / environment contract
