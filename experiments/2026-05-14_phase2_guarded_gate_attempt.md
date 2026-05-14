# 2026-05-14 Phase 2 Guarded Gate Attempt

## Goal

Run the first remote scripted validation gate after the Phase 2 contact-frame fix.

Target job:

- task: `RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0`
- envs: `1`
- steps: `240`
- seed: `42`
- objective: validate whether the frame fix makes the scripted controller converge before spending on PPO

## Preflight

- Git tree was clean.
- Brev CLI was initially logged out; login was completed for org `NCA-57cf-29515`.
- The Brev optional agent skill install prompt was skipped.

## Price Snapshot

The guarded gate recorded live Brev price tables under:

- `artifacts/gpu_gate/2026-05-14T15-45-25Z_isaac-phase2-gate/`

Relevant candidates:

- `g2-standard-4:nvidia-l4:1`, L4 24 GB, about `$0.85/hr`
- `gpu-l40s-a.1gpu-8vcpu-32gb`, L40S 48 GB, about `$1.86/hr`
- `g6e.xlarge`, L40S 45 GB, about `$2.23/hr`

Because the goal was to get a reliable result rather than re-test the cheaper L4 cold-start path, the first attempt used the default balanced profile and selected the cheapest visible single L40S.

## Attempt 1: Nebius L40S

Command:

```bash
scripts/run_guarded_phase2_gate.sh
```

Selected type:

- `gpu-l40s-a.1gpu-8vcpu-32gb`

Result:

- Brev successfully created `isaac-phase2-gate`.
- The instance remained in `STARTING / PENDING / NOT READY`.
- `brev create` reported `Timeout waiting for ready state`.
- The gate was interrupted before any SSH/runtime setup.
- Cleanup deleted the instance.
- The script confirmed `no visible instances after delete`.

Local log:

- `artifacts/gpu_gate/2026-05-14T15-45-25Z_isaac-phase2-gate/gate.log`

This attempt did not run Isaac, so it does not measure the task or controller.

## Safety Fix

The attempt exposed a safety bug in `scripts/run_guarded_phase2_gate.sh`:

- If `brev ls --json --all` timed out, the old `org_is_empty` helper could treat empty command output as an empty org.

Fix:

- `org_is_empty` now fails closed.
- Brev JSON query failure is treated as "not safe to create a new instance."

Commit:

- `965dda0 Fail closed on Brev instance query errors`

## Attempt 2: AWS L40S Fallback

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-gate-aws \
RCA_GATE_INSTANCE_TYPE=g6e.xlarge \
scripts/run_guarded_phase2_gate.sh
```

Result:

- No GPU instance was created.
- Brev JSON instance query failed during preflight.
- The fixed script refused to create a new instance.

Local log:

- `artifacts/gpu_gate/2026-05-14T15-59-26Z_isaac-phase2-gate-aws/gate.log`

## State After Attempt 2

- No remote scripted gate result was produced.
- No Isaac runtime was started.
- No PPO training was run.
- No Brev process remained locally after cleanup.
- Git remained clean after committing the safety fix.

## Follow-up CLI Diagnosis

Later probing showed the Brev backend was healthy and the org query worked, but the plain instance-list command path was unreliable:

- `brev healthcheck`: passed
- `brev ls orgs --json`: passed
- `brev ls instances --json --all`: returned `null`
- plain `brev ls --json --all`: timed out

Follow-up fix:

- `scripts/run_guarded_phase2_gate.sh` now uses `brev ls instances --all` and `brev ls instances --json --all` instead of plain `brev ls`.
- If the JSON query times out only after printing an exact empty-org marker (`null` or `[]`), the guarded script accepts that marker; any other failed instance query remains fail-closed.

## Attempt 3: GCP L4 Fallback

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-gate-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
scripts/run_guarded_phase2_gate.sh
```

Selected type:

- `g2-standard-4:nvidia-l4:1`
- NVIDIA L4, 24 GB VRAM
- recorded price: about `$0.85/hr`

Result:

- Brev successfully created `isaac-phase2-gate-l4`.
- The instance became `RUNNING / COMPLETED / READY`.
- Remote probe succeeded:
  - GPU: `NVIDIA L4`, 23034 MiB
  - driver: `580.126.20`
  - root disk: 125 GB
- Docker successfully pulled `nvcr.io/nvidia/isaac-sim:6.0.0-dev2`.
- Runtime setup failed inside `./isaaclab.sh --install assets,physx,tasks` while installing `setuptools<82.0.0`:

```text
ERROR: Could not install packages due to an OSError: ('Connection broken: IncompleteRead(0 bytes read, 1 more expected)', IncompleteRead(0 bytes read, 1 more expected))
```

Interpretation:

- This was a transient pip/network failure during runtime bootstrap, not a task-code failure.
- Isaac did not reach the scripted controller gate.
- No PPO training was run.

Cleanup:

- Artifacts were pulled before shutdown.
- The guarded script deleted `isaac-phase2-gate-l4`.
- Deletion stayed in `DELETING` for several minutes, then the script confirmed `No instances in org NCA-57cf-29515`.
- An independent post-cleanup query also returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Local log:

- `artifacts/gpu_gate/2026-05-14T16-21-21Z_isaac-phase2-gate-l4/gate.log`

Follow-up fix:

- `scripts/install_remote_isaaclab_runtime.sh` now exports longer pip timeout/retry settings.
- IsaacLab and project pip installs are wrapped in `retry_cmd` so transient `IncompleteRead` failures retry before the whole GPU gate fails.

## Current State

- No Brev instances are visible in org `NCA-57cf-29515`.
- Runtime setup is now solved on the L4 fallback.
- The scripted contact gate still fails because the remote wrapper was overriding the scripted controller thresholds.
- The next attempt should reuse the L4 fallback after the wrapper fix.

## Attempt 4: L4 With Retry-Hardened Installer

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-gate-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
scripts/run_guarded_phase2_gate.sh
```

Result:

- Brev successfully created `isaac-phase2-gate-l4`.
- Runtime bootstrap completed with the retry-hardened installer.
- Isaac Lab runtime check passed.
- The contact play task registered correctly with force-aware observations:
  - task: `RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0`
  - observation width: `42`
  - action width: `6`
- Scripted gate ran for seed `42` and 240 steps.
- Artifacts were pulled locally.
- Cleanup deleted the instance, and an independent post-cleanup query returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "initial_lateral": 0.09503934532403946,
  "final_lateral": 0.11525661498308182,
  "initial_axial": 0.2692160904407501,
  "final_axial": 0.23030611872673035,
  "initial_rot": 2.3476452827453613,
  "final_rot": 2.450565814971924,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Interpretation:

- Runtime setup is now solved.
- The scripted controller gate is still failing.
- The failure is not a PPO issue yet; PPO should still not be run.
- The log showed `insert_ready=1.000` from the beginning despite socket-frame lateral error being about `9.5 cm` and rotation error about `2.35 rad`.
- Root cause: scripted/live/debug controller gating used `compute_pose_error(...)` in the action/source frame, while success metrics use socket-frame errors from `mdp.insertion_metrics(...)`. This caused premature insertion instead of first aligning over the socket.

Follow-up fix:

- `scripts/scripted_agent.py` now gates approach/polish/settle phases using `mdp.insertion_metrics(...)`.
- `scripts/live_step_scripted_baseline.py` now uses the same socket-frame metrics.
- `scripts/debug_pose_alignment.py` now uses socket-frame lateral error for phase debugging.

Local outputs:

- `artifacts/evaluations/scripted/2026-05-14T17-13-48Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-14T17-13-48Z/seed_42.log`
- `artifacts/gpu_gate/2026-05-14T16-51-36Z_isaac-phase2-gate-l4/gate.log`

## Attempt 5: L4 After Scripted Gating Patch

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-gate-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
scripts/run_guarded_phase2_gate.sh
```

Result:

- Brev successfully created `isaac-phase2-gate-l4`.
- Runtime bootstrap completed again.
- Scripted gate ran for seed `42`.
- Metrics were unchanged from Attempt 4.
- Cleanup deleted the instance, and post-cleanup checks showed no visible instances.

Metrics:

```json
{
  "initial_lateral": 0.09503934532403946,
  "final_lateral": 0.11525661498308182,
  "initial_axial": 0.2692160904407501,
  "final_axial": 0.23030611872673035,
  "initial_rot": 2.3476452827453613,
  "final_rot": 2.450565814971924,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Interpretation:

- The attempted scripted gating patch was not actually exercised.
- `scripts/run_remote_scripted_eval.sh` was forcing these permissive arguments:
  - `--approach-height 0.0`
  - `--approach-xy-tol 1.0`
  - `--approach-rot-tol 10.0`
- Those overrides make `insert_ready=1.000` from the beginning, bypassing the realistic approach gate.

Follow-up fix:

- `scripts/run_remote_scripted_eval.sh` no longer hard-codes permissive scripted-controller thresholds.
- It now uses `scripted_agent.py` defaults unless `RCA_SCRIPTED_AGENT_ARGS` or explicit extra args are supplied.

Local outputs:

- `artifacts/evaluations/scripted/2026-05-14T17-50-13Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-14T17-50-13Z/seed_42.log`
- `artifacts/gpu_gate/2026-05-14T17-29-50Z_isaac-phase2-gate-l4/gate.log`

## Next Decision

Do not run PPO yet.

Next useful action:

1. Confirm `brev ls instances --all` and `brev ls instances --json --all` both return normally.
2. Re-run the guarded gate on the L4 fallback after the wrapper threshold fix:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-gate-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
scripts/run_guarded_phase2_gate.sh
```

Pass condition remains:

- scripted final lateral and axial errors improve from reset
- rotation does not remain near `~2 rad`
- `insertion_progress` becomes non-zero or final pose is close enough to justify one short PPO smoke

If the fallback also fails to provision or Brev API remains unstable, pause GPU work and continue local code/documentation cleanup instead of retrying repeatedly.
