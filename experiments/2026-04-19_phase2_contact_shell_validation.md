# Phase 2A Contact-Shell Validation

## Run Summary

- Date: `2026-04-19`
- Owner: `Shenghan Gao`
- Goal: validate the first contact-guided peg + guide-wall shell before any new training
- Remote env: `isaac-l40s`
- Base checkpoint under test: `phase1_fix6_formal/model_50.pt`

## Scope

This run was intentionally narrow. It did **not** train a new policy. It only answered three questions:

1. Does the new contact shell boot and run stably?
2. Does the scripted baseline behave sensibly in the new shell?
3. Does the best proxy checkpoint transfer zero-shot into the new shell?

## Commands

Runtime bootstrap:

```bash
./scripts/install_remote_isaaclab_runtime.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
```

Smoke suite:

```bash
./scripts/run_remote_smoke_test.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
```

Scripted viewport recording:

```bash
./scripts/run_remote_record_scripted_video.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
```

Zero-shot transfer eval:

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 400 42 '.*phase1_fix6_formal.*' model_50.pt
```

Artifact pullback:

```bash
./scripts/pull_artifacts.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly
```

## Key Artifacts

- Zero-shot eval summary:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-19T10-28-10Z/summary.json`
- Zero-shot eval log:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-19T10-28-10Z/eval.log`
- Scripted video log:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/videos/scripted/2026-04-19T10-23-48Z/record.log`

## Results

### Smoke

- status: `passed`
- zero-action rollout: booted and exited cleanly
- random-action rollout: booted and exited cleanly

### Scripted baseline

- status: `completed`
- final success rate: `0.000`
- final lateral error: `0.6042`
- final axial error: `0.1477`
- final rotation error: `0.3168`
- interpretation:
  - the contact shell itself is stable enough to run
  - the old scripted baseline is no longer a meaningful controller under contact
  - the policy/controller mismatch now shows up immediately once the peg interacts with the guide walls

### Scripted video

- status: `timed out`
- timeout: `240s`
- usable mp4: `not produced`
- interpretation:
  - the first contact-shell validation has logs but not a stable viewport artifact
  - this is a recording/runtime issue, not the main scientific result of the transfer test

### Zero-shot transfer from `phase1_fix6_formal/model_50.pt`

- status: `completed`
- best success rate: `0.000`
- final success rate: `0.000`
- initial lateral error: `0.0615`
- initial axial error: `0.2069`
- initial rotation error: `2.3415`
- final lateral error: `0.5667`
- final axial error: `0.4202`
- final rotation error: `1.9165`
- interpretation:
  - the best proxy checkpoint does **not** transfer zero-shot into the first contact shell
  - the policy drifts outward under contact instead of converging into the guide
  - this confirms that the Phase 1 proxy policy mainly learned the old pose-tracking shell, not a robust contact insertion behavior

## Decision

The contact shell is now real enough to invalidate further reward polishing on the archived proxy task.

The next useful step is **not** another proxy PPO run. It is one of:

1. add contact/force observations to the actor and train directly on the contact shell
2. retune or replace the scripted baseline so the first video/debugging path is meaningful again
3. simplify the contact geometry further if the rigid peg sync introduces contact artifacts that dominate early behavior

## Follow-up: Force-Aware Contact Smoke

After the failed zero-shot transfer, the next step was to add explicit contact-force observations to the actor and verify that a direct contact-training task could at least boot, train for a few PPO iterations, and produce a checkpoint that evaluated cleanly.

### Commands

Short force-aware PPO smoke:

```bash
./scripts/run_remote_train_ppo.sh isaac-contact /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Contact-v0 64 5 42 phase2_contact_force_smoke
```

Fixed-step eval of the smoke checkpoint:

```bash
./scripts/run_remote_eval_policy.sh isaac-contact /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Contact-v0 16 200 42 '.*phase2_contact_force_smoke.*' model_4.pt
```

Artifact pullback:

```bash
./scripts/pull_artifacts.sh isaac-contact /home/ubuntu/projects/robot-contact-assembly
```

### Key Artifacts

- Train run:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-19T11-53-04Z_phase2_contact_force_smoke/train.log`
- Train metadata:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-19T11-53-04Z_phase2_contact_force_smoke/train_metadata.env`
- Eval summary:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-19T11-59-03Z/summary.json`
- Smoke checkpoint:
  - `/Volumes/Extreme Pro/Projects/robot-contact-assembly/logs/rsl_rl/franka_peg_in_hole/2026-04-19_11-55-18_phase2_contact_force_smoke/model_4.pt`

### Results

- status: `completed`
- task: `RCA-PegInHole-Franka-IK-Rel-Contact-v0`
- observation width: `42`
- smoke training outcome:
  - environment booted cleanly
  - PPO actor/critic resized to the new `42`-dim observation contract
  - training produced `model_4.pt` after `5` iterations without shape or runtime failures
- eval outcome:
  - best success rate: `0.000`
  - final success rate: `0.000`
  - initial lateral error: `0.0751`
  - initial axial error: `0.2089`
  - initial rotation error: `2.3887`
  - final lateral error: `0.6005`
  - final axial error: `0.6296`
  - final rotation error: `2.4156`
- interpretation:
  - the first force-aware contact-training path is now technically alive end-to-end
  - a short `5`-iteration smoke run is nowhere near enough to learn useful contact behavior
  - the policy drifts outward under contact, so the next question is no longer whether the task can boot, but whether the reward and reset distribution can support a real contact baseline

### Decision After Smoke

The project now has the minimum ingredients required for a real Phase 2 baseline:

1. physical peg + guide-wall contact shell
2. force-aware policy observations
3. PPO training and evaluation flow that works on the new task

The next useful experiment is a longer direct contact-baseline run on `RCA-PegInHole-Franka-IK-Rel-Contact-v0`, not another proxy transfer test.
