# Robot Contact Assembly

Robot assembly project built around a narrow Isaac Lab `peg-in-hole` workflow. Phase 1 closed the full remote training/evaluation/artifact loop with a proxy tip-to-socket task, and the current mainline runtime now upgrades that shell to a simple physical peg + guide-socket contact environment.

## Project snapshot

- Task: `peg-in-hole`
- Simulator stack: Isaac Sim + Isaac Lab
- Robot: Franka Panda
- Control: relative differential IK
- Policy: PPO (`rsl_rl`)
- Execution model: local planning and artifact archive + remote Brev GPU runtime
- Latest measured results: stable near-insertion alignment under the archived Phase 1 proxy task
- Current runtime shell: explicit peg geometry, fixed guide-socket contact walls, and physical socket-frame success logic

## Phase 1 Scope

Phase 1 was intentionally a proxy precursor, not a finished contact assembly task:

- peg tip was modeled as a fixed tool offset
- socket target was modeled as a commanded pose
- success was computed from pose thresholds instead of peg/socket geometry

Those limitations are important context for every Phase 1 metric in this repo. The current runtime code has now moved to a contact-guided shell, and the first contact-shell transfer eval has now been recorded separately from the archived proxy metrics.

## Highlights

- Custom Isaac Lab external task package that started as a proxy insertion task and now includes a contact-guided peg/socket shell
- Reproducible remote experiment workflow on Brev for training, evaluation, checkpoint sweep, and artifact pullback
- Structured failure analysis across multiple reward and curriculum variants instead of one-off PPO runs
- CV-ready Phase 1 summary with concrete best-run metrics and next-step technical direction

## Best results so far

The strongest published Phase 1 runs were:

- Base run `phase1_fix6_formal`
  - `lateral=0.0074`
  - `axial=0.0027`
  - `rot=0.7190`
  - `success=0.000`
- Continuation run `finetune_fix8_from_fix6`
  - `lateral=0.0105`
  - `axial=0.0092`
  - `rot=0.6265`
  - `success=0.000`

Interpretation:

- the policy reliably learns socket approach and near-insertion alignment
- those metrics were achieved under the archived proxy task, not the new contact shell
- under the proxy task design, late-stage reward retuning showed diminishing returns

See [experiments/2026-04-05_phase1_rl_baseline.md](experiments/2026-04-05_phase1_rl_baseline.md) for the full run history and [docs/phase1_cv_summary.md](docs/phase1_cv_summary.md) for the concise CV/interview framing.

## V1 scope

The first version is intentionally narrow:

- Task: `peg-in-hole`
- Robot: Isaac-provided arm
- Control: end-effector delta pose
- Training: single task, single workstation, single policy
- Output: reproducible baseline with scripted, RL, and evaluation flows

## Working split

Local machine:

- Cursor / Codex
- planning docs and configs
- lightweight control tools
- artifact archive on the external SSD

## Local storage policy

Keep all local project state on the external SSD under:

- `/Volumes/Extreme Pro/Projects/robot-contact-assembly`

This repository is intended to be the local source of truth for:

- source code
- pulled checkpoints
- pulled evaluation JSON and logs
- pulled videos
- experiment notes

Do not pull artifacts into `~/Downloads`, `~/Desktop`, or other paths on the system disk.

Remote Brev GPU VM:

- Isaac Sim / Isaac Lab runtime
- ROS 2 processes tied to the sim
- training jobs
- rendered videos and checkpoints before sync back

See [architecture.md](docs/architecture.md) and [task_breakdown.md](docs/task_breakdown.md).
For the shortest GPU-session workflow, use [phase1_gpu_session_runbook.md](docs/phase1_gpu_session_runbook.md).

## Repository layout

- `configs/`: task and experiment configuration
- `docs/`: project and system design notes
- `experiments/`: run logs and experiment notes
- `scripts/`: local-to-remote workflow helpers
- `src/robot_contact_assembly/`: planning-side specs and lightweight local utilities
- `source/robot_contact_assembly_tasks/`: Isaac Lab external task package for runtime registration

## Current milestone

Phase 1 is to finish the `peg-in-hole` baseline contract:

1. Freeze task spec
2. Freeze observation and action interfaces
3. Add scripted baseline
4. Add RL environment shell
5. Add evaluation and artifact export flow

## Current Runtime Scaffold

The current runnable Isaac Lab shell is still intentionally simple, but it now includes explicit contact geometry:

- Robot: Franka Panda
- Control: relative differential IK
- Task scope: physical peg rigid body + fixed guide socket walls
- Task IDs:
  - `RCA-PegInHole-Franka-IK-Rel-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Play-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Polish-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Contact-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0`

The policy observation contract is still kept Phase-1 compatible so the best proxy checkpoint can be evaluated zero-shot in the new contact shell before adding force terms to the actor.

The new `Contact` task IDs are the first force-aware training path. They preserve the same core pose observations as `v0`, but add:

- peg contact force vector in the socket frame
- peg contact force magnitude

Keep using `RCA-PegInHole-Franka-IK-Rel-v0` for transfer/regression. Use `RCA-PegInHole-Franka-IK-Rel-Contact-v0` for the first direct contact-training baseline.

## Current Limitation

The current task is no longer a pure proxy shell, but it is still not a final industrial socket model:

- the socket is a simple fixed guide built from collision walls, not a CAD-accurate round hole with chamfer
- the first zero-shot transfer eval from `phase1_fix6_formal/model_50.pt` failed with `success=0.000`, `final_lateral=0.5667`, `final_axial=0.4202`, and `final_rot=1.9165`
- force/contact sensing is present at the scene level, but the default policy observation width is still frozen for checkpoint compatibility

This is enough to turn the project back into a real contact problem without taking on grasping, CAD assets, or sim-to-real scope yet.

## First Contact-Shell Validation

The first contact-shell validation was run on `2026-04-19` against the upgraded peg + guide-wall scene.

- smoke suite: passed
- scripted baseline on the play task: unstable under contact, ending at `final_lateral=0.6042`, `final_axial=0.1477`, `final_rot=0.3168`, `success=0.000`
- zero-shot transfer from `phase1_fix6_formal/model_50.pt`: failed, ending at `final_lateral=0.5667`, `final_axial=0.4202`, `final_rot=1.9165`, `success=0.000`
- scripted viewport recording: timed out at `240s`, so the first contact-shell validation currently has logs and JSON metrics but no stable mp4 artifact

See [experiments/2026-04-19_phase2_contact_shell_validation.md](experiments/2026-04-19_phase2_contact_shell_validation.md) for the exact commands, artifact paths, and interpretation.

## First Contact Validation

The first useful validation sequence for the new contact shell is:

1. Run the remote smoke suite:
   - `./scripts/run_remote_smoke_test.sh`
2. Run the zero-shot transfer eval from the best Phase 1 proxy checkpoint:
   - `./scripts/run_remote_contact_transfer_eval.sh`
3. Pull the resulting artifacts back to the local archive:
   - `./scripts/pull_artifacts.sh`

What those commands do:

- `run_remote_smoke_test.sh` now syncs the repo first, then runs compose health, env listing, zero-action rollout, random-action rollout, and scripted baseline sanity on the play task.
- `run_remote_contact_transfer_eval.sh` runs both fixed-step policy eval and an optional recorded video for the default transfer target:
  - run pattern: `.*phase1_fix6_formal.*`
  - checkpoint: `model_50.pt`
  - task: `RCA-PegInHole-Franka-IK-Rel-v0`
- the video stage now defaults to `RCA_VIDEO_BACKEND=viewport`
- the viewport path auto-injects the minimal rendering extensions with `--kit_args "--enable omni.replicator.core --enable omni.kit.material.library --enable omni.kit.viewport.rtx"` when no custom `--kit_args` are provided
- `RCA_VIDEO_BACKEND=camera` is still available for explicit sensor debugging, but it is not the stable path on the current Brev setup
- by default the wrapper keeps the eval artifacts even if the video step times out
- `run_remote_record_video.sh` now force-kills lingering recorder jobs after the grace period with `RCA_VIDEO_TIMEOUT_KILL_SECONDS` so failed probes do not leave orphaned Isaac processes behind

Useful overrides:

- use a different play-task smoke target:
  - `./scripts/run_remote_smoke_test.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Play-v0 5 10 120`
- evaluate a different checkpoint:
  - `./scripts/run_remote_contact_transfer_eval.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 400 42 '.*phase1_fix6_formal.*' model_50.pt 400`
- make the video step optional and cap its runtime:
  - `RCA_VIDEO_REQUIRED=0 RCA_VIDEO_TIMEOUT_SECONDS=60 ./scripts/run_remote_contact_transfer_eval.sh`
- shorten the hard-kill grace period when debugging stuck video jobs:
  - `RCA_VIDEO_TIMEOUT_SECONDS=60 RCA_VIDEO_TIMEOUT_KILL_SECONDS=10 ./scripts/run_remote_record_video.sh`
- force explicit camera-sensor recording for debugging:
  - `RCA_VIDEO_BACKEND=camera ./scripts/run_remote_contact_transfer_eval.sh`
- force the wrapper to fail when video recording fails:
  - `RCA_VIDEO_REQUIRED=1 ./scripts/run_remote_contact_transfer_eval.sh`

## Remote workflow

1. Bootstrap the Brev workspace:
   - `./scripts/bootstrap_brev_workspace.sh`
2. Sync the repo:
   - `./scripts/sync_to_brev.sh`
3. Clone or refresh Isaac Lab on the remote VM:
   - `./scripts/setup_remote_isaaclab.sh`
4. Mount the project and Isaac Lab into the running Isaac Sim container, then install the required Isaac Lab packages into the container's Python runtime:
   - `./scripts/install_remote_isaaclab_runtime.sh`
5. Run the first smoke test:
   - `./scripts/run_remote_smoke_test.sh`

## Day-1 commands

Once the runtime is bootstrapped, the shortest useful commands are:

- Inspect remote runtime health:
  - `./scripts/check_remote_runtime.sh`
- Full smoke suite for the contact shell:
  - `./scripts/run_remote_smoke_test.sh`
- Headless zero-action rollout:
  - `./scripts/run_remote_zero_agent.sh`
- Headless random-action rollout:
  - `./scripts/run_remote_random_agent.sh`
- Headless scripted baseline:
  - `./scripts/run_remote_scripted_baseline.sh`
- Fixed-seed scripted baseline sweep with per-seed JSON summaries:
  - `./scripts/run_remote_scripted_eval.sh`
- PPO training wrapper for the custom peg-in-hole task package:
  - `./scripts/run_remote_train_ppo.sh`
- Short contact-baseline smoke run:
  - `./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 64 5 42 phase2_contact_smoke`
- Short force-aware contact smoke run:
  - `./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Contact-v0 64 5 42 phase2_contact_force_smoke`
- End-to-end polish cycle wrapper:
  - `./scripts/run_remote_polish_cycle.sh`
- Cold-start Brev reprovision + polish cycle:
  - `./scripts/recreate_brev_and_run_polish.sh`
- Fixed-step policy evaluation with JSON summary export:
  - `./scripts/run_remote_eval_policy.sh`
- Zero-shot Phase-1-to-contact transfer eval + video wrapper:
  - `./scripts/run_remote_contact_transfer_eval.sh`
- Fixed-step checkpoint sweep over a matched run:
  - `./scripts/run_remote_eval_checkpoint_sweep.sh`
- One-shot policy video recording:
  - `./scripts/run_remote_record_video.sh`
- Capture a runtime manifest for reproducibility:
  - `./scripts/capture_remote_runtime_manifest.sh`
- Start the local live-app code port forward:
  - `bash ./scripts/start_live_code_port_forward.sh`
- Load the play environment into the currently running streamed Isaac Sim app:
  - `bash ./scripts/show_live_play_env.sh`
- Run the first scripted live baseline:
  - `bash ./scripts/run_live_scripted_baseline.sh`

Default target is `isaac-l40s`. Optional positional arguments are:

- `ENV_NAME`
- `REMOTE_ROOT`
- `REMOTE_COMPOSE_ROOT`
- `TASK_NAME`
- `NUM_ENVS`
- `STEPS`

Example:

- `./scripts/run_remote_random_agent.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Play-v0 1 20`
- `./scripts/run_remote_polish_cycle.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish '.*phase1_fix6_formal.*' model_50.pt 400 0`
- `./scripts/recreate_brev_and_run_polish.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish_v2 '.*phase1_fix6_formal.*' model_50.pt 400 0`
- `./scripts/run_remote_eval_checkpoint_sweep.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 400 42 '.*phase1_polish.*' 'model_.*\.pt' 0`

After pulling artifacts, summarize a sweep locally with:

- `python3 scripts/summarize_eval_sweep.py --checkpoint-substring phase1_polish`

## Current remote runtime decision

The Brev host currently runs the streamed Isaac Sim stack via Docker. Because of that, the executable path for V1 is:

- Streaming stack: `isaac-sim` container for WebRTC / viewer services
- Task execution runtime: `/isaac-sim/python.sh` inside the `isaac-runner` container
- Isaac Lab repo: mounted at `/workspace/IsaacLab`
- Project repo: mounted from `/home/ubuntu/projects/robot-contact-assembly/repo/robot-contact-assembly`

This avoids relying on the Brev host's system Python, which is not the right runtime for Isaac Lab + Isaac Sim, and avoids running evaluation or training scripts inside the long-lived streaming container.

## Current validated state

Validated on `2026-03-29` for the original proxy-task runtime:

- remote `isaac-sim` container healthy
- env registry works
- `RCA-PegInHole-Franka-IK-Rel-Play-v0` launches in headless mode
- zero-action smoke passes
- random-action smoke passes

Current contact-task work uses a split runtime:

- `isaac-sim`: streaming / viewer service
- `isaac-runner`: smoke, eval, and training execution target

The RL stack is not yet treated as stable. Do not assume `rsl_rl` installation is reproducible until the runtime is pinned more tightly.

## Final Phase 1 status

Validated through the `2026-04-05` experiment series:

- A complete remote training/evaluation/artifact loop is in place for PPO baseline runs.
- The strongest base run was `phase1_fix6_formal`, which reached:
  - `lateral=0.0074`
  - `axial=0.0027`
  - `rot=0.7190`
  - `success=0.000`
- The strongest continuation run was `finetune_fix8_from_fix6`, which improved rotation while preserving near-socket alignment:
  - `lateral=0.0105`
  - `axial=0.0092`
  - `rot=0.6265`
  - `success=0.000`
- Three dedicated late-stage `Polish` variants (`v2`, `v3`, and scheduled curriculum) ran successfully but did not beat the continuation baseline.

Phase 1 therefore closes with a clear technical conclusion:

- the policy can reliably learn socket approach and near-insertion alignment
- the remaining gap is late-stage rotational convergence under the current proxy task design
- further reward retuning was stopped after the scheduled curriculum failed to beat `finetune_fix8_from_fix6`

For the concise CV-facing summary and interview framing, see [phase1_cv_summary.md](docs/phase1_cv_summary.md).

## What comes next

The next meaningful technical step is not another PPO retune on the same proxy shell. It is to replace the current proxy setup with:

- explicit peg/socket geometry
- contact-driven success logic
- late-stage curriculum or imitation-style polishing on top of that more realistic task

## Phase-1 reproducibility additions

- `scripts/capture_remote_runtime_manifest.sh`
  - snapshots compose status, key package versions, registered envs, and git state into `experiments/runtime_manifests/`
- `scripts/run_remote_scripted_eval.sh`
  - runs the scripted peg-in-hole baseline over a fixed seed sweep and writes one JSON summary per seed under `/workspace/artifacts/evaluations/scripted/`
- `scripts/scripted_agent.py --seed --summary-json`
  - supports deterministic replay and machine-readable summaries for evaluation
