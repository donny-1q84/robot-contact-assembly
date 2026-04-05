# Robot Contact Assembly

Contact-rich robot assembly project scaffold for Isaac Sim / Isaac Lab.

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

## Current runtime scaffold

The first runnable Isaac Lab shell is intentionally narrower than the final project:

- Robot: Franka Panda
- Control: relative differential IK
- Task scope: insertion-only baseline with a fixed peg-tip offset
- Task IDs:
  - `RCA-PegInHole-Franka-IK-Rel-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Play-v0`

This keeps the first environment aligned with the eventual peg-in-hole goal, while avoiding the extra moving parts of a full pick-and-insert pipeline in week one.

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
- Full smoke test:
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
- End-to-end polish cycle wrapper:
  - `./scripts/run_remote_polish_cycle.sh`
- Cold-start Brev reprovision + polish cycle:
  - `./scripts/recreate_brev_and_run_polish.sh`
- Fixed-step policy evaluation with JSON summary export:
  - `./scripts/run_remote_eval_policy.sh`
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
- `./scripts/run_remote_polish_cycle.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish '.*phase1_fix6_formal.*' model_299.pt 400 0`
- `./scripts/recreate_brev_and_run_polish.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish_v2 '.*phase1_fix6_formal.*' model_299.pt 400 0`
- `./scripts/run_remote_eval_checkpoint_sweep.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 400 42 '.*phase1_polish.*' 'model_.*\.pt' 0`

After pulling artifacts, summarize a sweep locally with:

- `python3 scripts/summarize_eval_sweep.py --checkpoint-substring phase1_polish`

## Current remote runtime decision

The Brev host currently runs the streamed Isaac Sim stack via Docker. Because of that, the executable path for V1 is:

- Isaac Sim runtime: `/isaac-sim/python.sh` inside the `isaac-sim` container
- Isaac Lab repo: mounted at `/workspace/IsaacLab`
- Project repo: mounted from `/home/ubuntu/projects/robot-contact-assembly/repo/robot-contact-assembly`

This avoids relying on the Brev host's system Python, which is not the right runtime for Isaac Lab + Isaac Sim.

## Current validated state

Validated on `2026-03-29`:

- remote `isaac-sim` container healthy
- env registry works
- `RCA-PegInHole-Franka-IK-Rel-Play-v0` launches in headless mode
- zero-action smoke passes
- random-action smoke passes

The RL stack is not yet treated as stable. Do not assume `rsl_rl` installation is reproducible until the runtime is pinned more tightly.

## Phase-1 reproducibility additions

- `scripts/capture_remote_runtime_manifest.sh`
  - snapshots compose status, key package versions, registered envs, and git state into `experiments/runtime_manifests/`
- `scripts/run_remote_scripted_eval.sh`
  - runs the scripted peg-in-hole baseline over a fixed seed sweep and writes one JSON summary per seed under `/workspace/artifacts/evaluations/scripted/`
- `scripts/scripted_agent.py --seed --summary-json`
  - supports deterministic replay and machine-readable summaries for evaluation
