# Phase 1 GPU Session Runbook

This runbook is the shortest path to a CV-ready Phase 1 result:

- one PPO baseline run
- one fixed-step evaluation
- one demo video
- one experiment note

Keep scope fixed to:

- task: `RCA-PegInHole-Franka-IK-Rel-v0`
- agent: `rsl_rl`
- seed: `42`
- smoke run name: `smoke`
- formal run name: `phase1_formal`

Use `RCA-PegInHole-Franka-IK-Rel-Play-v0` only for interactive debugging or visual checks.

## Before Starting the GPU

Confirm the local repository is clean enough for a first commit:

- `git status --short`
- no local artifacts under `artifacts/`
- no local `__pycache__/` directories staged for commit

Recommended first commit scope:

- `README.md`
- `docs/`
- `experiments/`
- `scripts/`
- `source/`
- `configs/`
- `pyproject.toml`
- `.gitignore`

Prepare one experiment note from the template:

- copy `experiments/templates/phase1_rl_baseline.md`
- name it `experiments/YYYY-MM-DD_phase1_rl_baseline.md`

## Session 1: Smoke Test

Goal:

- verify the runtime still boots
- verify PPO starts
- verify checkpoints write
- verify evaluation can load the new checkpoint

Expected budget:

- `1-2` GPU hours

Commands:

```bash
./scripts/check_remote_runtime.sh
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 256 30 42 smoke
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 200 42 '.*smoke.*' 'model_.*.pt'
```

Smoke passes if all of these are true:

- training starts without import or runtime errors
- reward and metric lines are moving
- a `model_*.pt` checkpoint exists in the train artifact directory
- evaluation finishes and writes `summary.json`

Stop immediately if:

- Isaac Sim runtime is unhealthy
- `rsl_rl` import fails
- no checkpoint is produced
- evaluation cannot resolve the checkpoint

## Session 2: Formal Training

Goal:

- produce one baseline checkpoint that is good enough to show

Expected budget:

- `8-12` GPU hours

Default command:

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 256 300 42 phase1_formal
```

Watch only a small set of signals:

- train log stability
- checkpoint cadence
- success proxy trends from evaluation checkpoints

Do not:

- change task IDs mid-run
- switch to the play environment
- retune the controller during the formal run
- start grid-searching hyperparameters

## Session 3: Evaluation and Video

Goal:

- lock in a fixed-seed evaluation summary
- record one video from the best checkpoint

Expected budget:

- `2-4` GPU hours

Commands:

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 400 42 '.*phase1_formal.*' 'model_.*.pt'
./scripts/run_remote_record_video.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 1 400 42 '.*phase1_formal.*' 'model_.*.pt'
./scripts/capture_remote_runtime_manifest.sh
./scripts/pull_artifacts.sh
```

Required outputs before deleting the GPU:

- one checkpoint under local `artifacts/`
- one evaluation `summary.json`
- one demo video
- one runtime manifest
- one filled experiment note

## Artifact Map

Remote artifact roots:

- train runs: `/workspace/artifacts/train_runs/`
- policy evaluations: `/workspace/artifacts/evaluations/policy/`
- policy videos: `/workspace/artifacts/videos/policy/`

Each remote wrapper now stores its exact invoked command:

- `train_command.txt`
- `eval_command.txt`
- `record_command.txt`

Keep pulled local artifacts under:

- `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts`

Do not pull them into the system disk.

## Delete-GPU Exit Checklist

Delete the Brev GPU only after all of these are true:

- local checkpoint exists
- local evaluation summary exists
- local video exists
- local runtime manifest exists
- local experiment note is updated
- code and docs are committed locally
