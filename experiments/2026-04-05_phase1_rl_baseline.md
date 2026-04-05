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
- Formal train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T13-37-03Z_phase1_formal/train.log`
- Formal train command: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T13-37-03Z_phase1_formal/train_command.txt`
- Formal train metadata: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T13-37-03Z_phase1_formal/train_metadata.env`
- Formal checkpoints: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/logs/rsl_rl/franka_peg_in_hole/2026-04-05_13-37-10_phase1_formal/`
- Formal eval summary JSON: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T13-41-02Z/summary.json`
- Formal eval command: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T13-41-02Z/eval_command.txt`
- Formal eval log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T13-41-02Z/eval.log`
- Runtime manifest:
- Pulled artifact root: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts`

## Results

- Smoke status: `passed`
- Formal train status: `completed`
- Final success rate: `0.000`
- Best success rate: `0.000`
- Final lateral error: `0.4548`
- Final axial error: `0.2093`
- Final rotation error: `2.0887`
- Best checkpoint: `model_9.pt` from `2026-04-05_13-16-20_smoke32`

## Formal Run Results

- Formal checkpoint used for eval: `model_50.pt`
- Formal eval final success rate: `0.000`
- Formal eval best success rate: `0.000`
- Formal eval final lateral error: `0.3731`
- Formal eval final axial error: `0.1095`
- Formal eval final rotation error: `0.1800`
- Formal eval initial rotation error: `2.4620`
- Training signal summary:
  - late-stage mean reward reached roughly `3.5+`
  - orientation error dropped substantially during training
  - `insertion_success` stayed at `0.0000` throughout the observed training and eval logs

## Retuned Smoke Results

- Retuned smoke run name: `smoke_retune_fix3`
- Retuned smoke command:

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 30 42 smoke_retune_fix3
```

- Retuned smoke eval command:

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 200 42 '.*smoke_retune_fix3.*' 'model_29.pt'
```

- Retuned smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-08-23Z_smoke_retune_fix3/model_29.pt`
- Retuned smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-09-02Z/summary.json`
- Retuned smoke final success rate: `0.000`
- Retuned smoke final lateral error: `0.5667`
- Retuned smoke final axial error: `0.2727`
- Retuned smoke final rotation error: `2.2674`
- Retuned smoke interpretation:
  - the softer shaping and tighter command curriculum did not improve insertion
  - the policy drifted farther from the socket over rollout instead of converging into alignment
  - the next iteration should restore stronger geometric tracking and make insertion reward conditional on staying near the socket, not simply soften all gates

## Smoke Fix4 Results

- Smoke run name: `smoke_fix4`
- Smoke command:

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 30 42 smoke_fix4
```

- Smoke eval command:

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 200 42 '.*smoke_fix4.*' 'model_29.pt'
```

- Smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-19-46Z_smoke_fix4/model_29.pt`
- Smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-20-29Z/summary.json`
- Smoke final success rate: `0.000`
- Smoke final lateral error: `0.4137`
- Smoke final axial error: `0.1176`
- Smoke final rotation error: `2.1098`
- Smoke interpretation:
  - restoring a dedicated coarse `approach_pose` term revived the geometric reward signal
  - `approach_pose`, `tip_position_tracking`, and `tip_orientation_tracking` all became non-zero during training
  - fixed-step eval still drifted away from the socket over rollout, but the endpoint was materially better than the failed `smoke_retune_fix3` run on lateral and axial alignment
  - insertion reward and success remained at zero, so the policy was still stuck in coarse approach behavior

## Smoke Fix5 Orient Results

- Smoke run name: `smoke_fix5_orient`
- Smoke command:

```bash
./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 30 42 smoke_fix5_orient
```

- Smoke eval command:

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 200 42 '.*smoke_fix5_orient.*' 'model_29.pt'
```

- Smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-22-33Z_smoke_fix5_orient/model_29.pt`
- Smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-23-12Z/summary.json`
- Smoke final success rate: `0.000`
- Smoke final lateral error: `0.6625`
- Smoke final axial error: `0.1971`
- Smoke final rotation error: `1.8791`
- Smoke interpretation:
  - increasing the orientation emphasis improved early-rollout orientation substantially (`rot` dropped from `2.3549` to `0.7985` by step 50)
  - the same change destabilized position holding, and the policy then spiraled outward in lateral/axial error over the rest of the rollout
  - compared with `smoke_fix4`, this run traded better orientation for much worse position retention
- the reward design is now clearly oscillating between “position wins” and “orientation wins”, which means another blind scalar retune is unlikely to produce first success

## Smoke Fix6 Coupled Results

- Smoke run name: `smoke_fix6_coupled`
- Smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-25-35Z_smoke_fix6_coupled/model_29.pt`
- Smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-26-16Z/summary.json`
- Smoke final success rate: `0.000`
- Smoke final lateral error: `0.3745`
- Smoke final axial error: `0.2029`
- Smoke final rotation error: `0.6237`
- Smoke interpretation:
  - the coupled `approach_pose` term was the first reward change that clearly unlocked insertion-stage shaping
  - `insertion_progress` became non-zero in training for the first time, while rotation stayed materially better than the earlier `fix4` / `fix5` runs
  - even though fixed-step eval still ended far outside the success tolerances, this run was good enough to justify longer training

## Smoke Fix6 Long Results

- Smoke run name: `smoke_fix6_long`
- Smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-26-52Z_smoke_fix6_long/model_99.pt`
- Smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-28-21Z/summary.json`
- Smoke final success rate: `0.000`
- Smoke final lateral error: `0.1185`
- Smoke final axial error: `0.1155`
- Smoke final rotation error: `0.8387`
- Smoke interpretation:
  - running the coupled reward for 100 iterations improved coarse centering and axial approach substantially
  - this was the first short run that looked plausibly “one design change away” from success, so it became the launch point for the first serious formal run

## Fix6 Formal Results

- Formal run name: `phase1_fix6_formal`
- Formal train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-29-19Z_phase1_fix6_formal/train.log`
- Formal eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-33-18Z/summary.json`
- Formal final success rate: `0.000`
- Formal final lateral error: `0.0074`
- Formal final axial error: `0.0027`
- Formal final rotation error: `0.7190`
- Formal interpretation:
  - this is the strongest “near-success” checkpoint so far
  - the policy reliably drives the peg tip into the correct lateral and axial neighborhood, but it plateaus at a residual orientation error of about `0.7 rad`
  - by the end of this run, the main problem had collapsed from “can the policy reach the socket at all?” to “how do we polish the last bit of rotation without losing position?”

## Smoke Fix7 Tiprot Results

- Smoke run name: `smoke_fix7_tiprot`
- Smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-36-10Z_smoke_fix7_tiprot/model_29.pt`
- Smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-36-52Z/summary.json`
- Smoke final success rate: `0.000`
- Smoke final lateral error: `0.3745`
- Smoke final axial error: `0.2029`
- Smoke final rotation error: `0.6237`
- Smoke interpretation:
  - adding the tip rotation offset directly to the IK action config did not improve the learned fixed-step behavior
  - this ruled out the simple “controller frame mismatch” fix as the main path forward

## Smoke Fix8 From Scratch Results

- Smoke run name: `smoke_fix8_sync`
- Smoke checkpoint: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-44-46Z_smoke_fix8_sync/model_29.pt`
- Smoke eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-45-31Z/summary.json`
- Smoke final success rate: `0.000`
- Smoke final lateral error: `0.4036`
- Smoke final axial error: `0.2109`
- Smoke final rotation error: `1.3884`
- Smoke interpretation:
  - the new `insertion_orientation_fine` reward was active after the sync fix, but from random initialization it never meaningfully took over
  - the policy failed to re-enter the near-socket regime often enough for the late-stage orientation reward to matter
  - this showed that the reward may still be useful, but not as a from-scratch training objective

## Fix8 Fine-Tune Results

- Fine-tune run name: `finetune_fix8_from_fix6`
- Fine-tune train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-46-20Z_finetune_fix8_from_fix6/train.log`
- Fine-tune eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-47-31Z/summary.json`
- Fine-tune final success rate: `0.000`
- Fine-tune final lateral error: `0.0105`
- Fine-tune final axial error: `0.0092`
- Fine-tune final rotation error: `0.6265`
- Fine-tune interpretation:
  - resuming from `phase1_fix6_formal` is the first setup where `insertion_orientation_fine` contributes non-trivially during training
  - compared with the baseline formal checkpoint, fixed-step eval improved rotation from `0.7190` to `0.6265`
  - the tradeoff is that lateral and axial errors worsened slightly, so the run still ends outside the success tolerances

## Dedicated Polish Task Results

- Fine-tune run name: `phase1_polish`
- Fine-tune task id: `RCA-PegInHole-Franka-IK-Rel-Polish-v0`
- Fine-tune wrapper:

```bash
./scripts/run_remote_finetune_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish '.*phase1_fix6_formal.*' model_50.pt
```

- Fine-tune train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T14-58-23Z_phase1_polish/train.log`
- Fine-tune eval summary: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/evaluations/policy/2026-04-05T14-59-24Z/summary.json`
- Fine-tune final success rate: `0.000`
- Fine-tune final lateral error: `0.0086`
- Fine-tune final axial error: `0.0047`
- Fine-tune final rotation error: `0.6933`
- Fine-tune interpretation:
  - the dedicated polish runner and task registration worked end-to-end and successfully resumed from the `phase1_fix6_formal` checkpoint
  - `insertion_orientation_fine` stayed active throughout training, but the fixed-step eval result only improved rotation slightly relative to the base checkpoint (`0.7190 -> 0.6933`)
  - this run did not beat the earlier manual `finetune_fix8_from_fix6` result (`0.6265` rotation), so the dedicated polish config is operational but not yet the best-performing continuation path

### Dedicated Polish Checkpoint Sweep

- `model_300.pt`: `lateral=0.0062`, `axial=0.0037`, `rot=0.7143`
- `model_310.pt`: `lateral=0.0066`, `axial=0.0047`, `rot=0.7137`
- `model_320.pt`: `lateral=0.0067`, `axial=0.0030`, `rot=0.7147`
- `model_330.pt`: `lateral=0.0081`, `axial=0.0082`, `rot=0.7244`
- `model_340.pt`: `lateral=0.0073`, `axial=0.0038`, `rot=0.7071`
- `model_348.pt`: `lateral=0.0086`, `axial=0.0047`, `rot=0.6933`
- Sweep interpretation:
  - within the dedicated polish run, `model_348.pt` is the best checkpoint on rotation
  - none of the dedicated polish checkpoints outperform the earlier manual `finetune_fix8_from_fix6` run on rotation
  - the sweep confirms that another rerun of the same dedicated polish setup is unlikely to beat the current best continuation result

## Synchronization Notes

- The original remote wrappers did not sync the local repo before running on Brev. This invalidated the first `smoke_fix8_fineorient` attempt because the remote environment still used stale source files.
- `scripts/sync_to_brev.sh` now uses `rsync` with excludes for `.git/`, `artifacts/`, `logs/`, and cache files.
- `run_remote_train_ppo.sh`, `run_remote_eval_policy.sh`, and `run_remote_record_video.sh` now sync automatically before launching remote work.
- Ignore `smoke_fix8_fineorient` as a stale remote-code run; `smoke_fix8_sync` is the valid from-scratch result for that reward design.

## Failure Modes

- `256 envs / 30 iters` was too heavy for first-pass smoke validation and was stopped to avoid wasting budget before dependency/runtime fixes were complete.
- The first custom evaluator path was broken in two places: environment launch flow and `rsl-rl >= 4.0` policy access. Both were fixed locally.
- Automated video recording with rendering kit started but never emitted frames or step logs; the run was canceled to avoid wasting GPU time. No usable MP4 was produced in this smoke session.
- The formal PPO run learned coarse alignment/orientation behavior, but still failed to achieve contact-rich insertion. The reward appears to over-value orientation alignment relative to actual insertion completion.
- `smoke_fix4` and `smoke_fix5_orient` show the next bottleneck more clearly:
  - `smoke_fix4` restores position-tracking gradients but leaves orientation too weak
  - `smoke_fix5_orient` fixes early orientation but causes large lateral drift
  - the next iteration should change reward structure, not just weights, for example by making approach reward depend on both lateral and orientation simultaneously before enabling insertion-specific shaping

## Next Decision

- Ship this result to README / CV
- Tune reward or curriculum
- Change controller / environment contract
- Start the first formal PPO training run only after deciding the remaining GPU budget

## Recommended Next Run

- Preferred path: do not train the late-stage orientation reward from scratch
- Resume from the strongest base checkpoint instead:
  - source run regex: `.*phase1_fix6_formal.*`
  - source checkpoint: `model_50.pt`
- Use the dedicated polish task and wrapper:

```bash
./scripts/run_remote_finetune_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish '.*phase1_fix6_formal.*' model_50.pt
```

- Then evaluate with:

```bash
./scripts/run_remote_eval_policy.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 400 42 '.*phase1_polish.*' 'model_.*.pt'
```

- Target outcome:
  - keep `lateral` and `axial` near the `phase1_fix6_formal` level
  - reduce `rotation` below the current fine-tune result of `0.6265`

- Current status after `phase1_polish`:
  - the dedicated polish entry point is now stable and reproducible
  - the best measured continuation result is still the earlier manual `finetune_fix8_from_fix6`
  - the next local iteration should focus on better late-stage curriculum or checkpoint selection, not another blind rerun of the same polish config

## Next Local Change After GPU Shutdown

- `RCA-PegInHole-Franka-IK-Rel-Polish-v0` now points to a dedicated `FrankaPegInHoleEnvCfg_POLISH`
- the polish env keeps the same reward structure but narrows the socket command ranges to a near-socket band:
  - `pos_x=(0.505, 0.545)`
  - `pos_y=(-0.025, 0.025)`
  - `pos_z=(0.178, 0.202)`
  - `yaw=(-pi/48, pi/48)`
- the polish env now also replaces the broad `approach_pose_reward` with a dedicated `late_stage_pose_reward`
  that rewards simultaneous lateral, axial, and rotational convergence instead of broad coarse approach
- polish reward emphasis is now:
  - stronger coupled late-stage pose reward
  - slightly weaker standalone coarse tracking terms
  - stronger insertion-stage and success terms
- intent:
  - stop using the wide Phase 1 approach curriculum during checkpoint polishing
  - force the resumed policy to spend most of its rollout budget in the late-stage refinement regime
  - reduce the old failure mode where rotation improved only by giving back some lateral or axial accuracy
- this change has not been re-run yet; it is the next thing to validate when GPU time is resumed


## Polish V2 Fix6 Validation

- Cold-start restore wrapper: `./scripts/recreate_brev_and_run_polish.sh`
- Validation task id: `RCA-PegInHole-Franka-IK-Rel-Polish-v0`
- Validation run name: `phase1_polish_v2_fix6`
- Source run regex: `.*phase1_fix6_formal.*`
- Source checkpoint: `model_50.pt`
- Runtime restore result:
  - recreated a fresh Brev `isaac-l40s` instance
  - restored Isaac Sim + IsaacLab runtime on the new instance
  - fixed remote compose calls to use `sudo docker compose`
  - fixed runtime installation to include `isaaclab_rl`
  - fixed local checkpoint sweep script for macOS Bash 3.2 by removing `mapfile`
- Validation train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T15-38-30Z_phase1_polish_v2_fix6/train.log`
- Validation checkpoint sweep summary:
  - `model_50.pt`: `lateral=0.0812`, `axial=0.2132`, `rot=1.3847`
  - `model_60.pt`: `lateral=0.0734`, `axial=0.1579`, `rot=1.3648`
  - `model_70.pt`: `lateral=0.0552`, `axial=0.1124`, `rot=1.2086`
  - `model_80.pt`: `lateral=0.0650`, `axial=0.1284`, `rot=1.8030`
  - `model_90.pt`: `lateral=0.0523`, `axial=0.1306`, `rot=1.5202`
  - `model_99.pt`: `lateral=0.0435`, `axial=0.0538`, `rot=0.8301`
- Validation interpretation:
  - the new narrow-curriculum `Polish` task is operational and trains from a fresh cold-start runtime
  - the joint late-stage reward clearly activates during training, but the resulting policy still underperforms the earlier manual continuation
  - the best checkpoint in this run is `model_99.pt`, but `rot=0.8301` is worse than both the base `phase1_fix6_formal` result (`0.7190`) and the earlier manual `finetune_fix8_from_fix6` result (`0.6265`)
  - this validates the new task and workflow end-to-end, but rejects the current `Polish v2` reward/curriculum as the next resume path
- Current best continuation remains:
  - `finetune_fix8_from_fix6` with `lateral=0.0105`, `axial=0.0092`, `rot=0.6265`
- Next local change should focus on:
  - preserving the `fix6` positional gains while making late-stage rotation shaping less destabilizing
  - checkpoint selection or curriculum staging based on actual metric windows, not a fixed 50-iteration polish schedule


## Polish V3 Fix6b Validation

- Validation run name: `phase1_polish_v3_fix6b`
- Source run regex: `.*phase1_fix6_formal.*`
- Source checkpoint: `model_50.pt`
- Local train log: `/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/train_runs/2026-04-05T15-53-44Z_phase1_polish_v3_fix6b/train.log`
- Completed fixed-step evals:
  - `model_50.pt`: `lateral=0.0816`, `axial=0.2035`, `rot=1.8454`
  - `model_99.pt`: `lateral=0.0682`, `axial=0.1037`, `rot=0.8494`
- Interpretation:
  - `Polish v3` is more stable than the rejected `Polish v2` path in the sense that the final checkpoint no longer explodes away from the socket neighborhood.
  - But it still does not beat the current best continuation result `finetune_fix8_from_fix6` (`lateral=0.0105`, `axial=0.0092`, `rot=0.6265`), and it is also worse than the base `phase1_fix6_formal` checkpoint on all three fixed-step eval metrics.
  - The new `late_stage_position_hold_reward` avoided the worst `Polish v2` drift pattern, but the late-stage orientation / insertion terms still are not strong enough to turn that stability into a better final checkpoint.
- Runtime note:
  - repeated evals on the same live `isaac-sim` container can hang after the first successful checkpoint evaluation
  - restarting `isaac-sim` before each subsequent eval restored correct behavior
  - the remote checkpoint sweep wrapper now forces a container restart before every checkpoint evaluation


## Next Local Change: Scheduled Polish Curriculum

- Status: implemented locally, not yet re-run on GPU
- Motivation:
  - `Polish v2` drifted away from the socket while chasing orientation
  - `Polish v3` stabilized the pose neighborhood but still kept fine orientation / insertion too weak to beat `fix8`
- Local change summary:
  - `approach_pose` in `RCA-PegInHole-Franka-IK-Rel-Polish-v0` now uses `scheduled_position_hold_reward`
  - `insertion_orientation_fine` now uses `scheduled_insertion_orientation_reward`
  - `insertion_progress` now uses `scheduled_insertion_progress_reward`
  - the schedule is driven by `env.common_step_counter`, so the reward mix shifts online during the same resumed run instead of relying on one static set of weights
- Intended curriculum shape:
  - start: strongly preserve the `fix6` near-socket lateral / axial pose
  - middle: gradually hand off reward mass to gated fine orientation
  - later: ramp insertion progress after the orientation gate is already active
- Next validation target:
  - reuse `.*phase1_fix6_formal.* / model_50.pt`
  - check whether the final checkpoint beats `Polish v3` (`0.0682 / 0.1037 / 0.8494`) without regressing all the way back to `Polish v2`
