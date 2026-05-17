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

## Attempt 6: L4 After Wrapper Threshold Fix

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
- Runtime bootstrap completed.
- Scripted gate ran for seed `42`.
- The wrapper threshold fix was exercised: `insert_ready=0.000` from step `0000` through step `0239`.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- Deletion lingered in `DELETING`, then `STOPPING`, but the guarded script eventually confirmed no visible instances.
- Independent post-cleanup checks returned:
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

- Runtime setup is solved.
- The wrapper bug is solved.
- The remaining blocker is the scripted controller, not PPO.
- Since `insert_ready=0.000` throughout, the controller correctly refused to insert before alignment.
- However, lateral error still failed to improve, which means the approach action itself is not reliably driving the peg tip toward the socket corridor.
- The likely issue is that the controller is coupling a large orientation correction with the gross approach motion, causing the tip to arc away from the socket during relative IK.

Follow-up fix:

- `scripts/scripted_agent.py` now uses a position-first state machine by default:
  - translate the peg tip to a hold pose above the socket while keeping the current orientation,
  - rotate in place only after the lateral and approach-height tolerances are met,
  - insert only after lateral and orientation tolerances are met.
- `scripts/live_step_scripted_baseline.py` now uses the same realistic thresholds and phase logic.
- `scripts/debug_pose_alignment.py` now matches the same phase logic for diagnostics.
- The legacy coupled controller remains available with `--coupled-approach`.

Local outputs:

- `artifacts/evaluations/scripted/2026-05-14T18-17-39Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-14T18-17-39Z/seed_42.log`
- `artifacts/gpu_gate/2026-05-14T17-56-39Z_isaac-phase2-gate-l4/gate.log`

## Next Decision

Do not run PPO yet.

## Attempt 7: L4 With Position-First Scripted Controller

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
- Runtime bootstrap completed.
- Scripted gate ran for seed `42`.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- Deletion lingered in `DELETING`/`STOPPING`, then the guarded script confirmed no visible instances.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "coupled_approach": false,
  "initial_lateral": 0.0942068099975586,
  "final_lateral": 0.11525661498308182,
  "initial_axial": 0.2691607177257538,
  "final_axial": 0.23030611872673035,
  "initial_rot": 2.351423501968384,
  "final_rot": 2.450565814971924,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Key rollout trace:

```text
step=0000 lateral=0.0942 axial=0.2692 rot=2.3514 position_ready=0.000
step=0025 lateral=0.4303 axial=0.3573 rot=2.8790 position_ready=0.000
step=0075 lateral=0.7936 axial=0.4869 rot=1.1157 position_ready=0.000
step=0175 lateral=0.2801 axial=0.6904 rot=1.5295 position_ready=0.000
step=0225 lateral=0.1691 axial=0.0264 rot=1.1143 position_ready=0.000
step=0239 lateral=0.1153 axial=0.2303 rot=2.4506 position_ready=0.000
```

Interpretation:

- The controller still does not pass the gate.
- The position-first patch prevented the scripted state machine from prematurely rotating/inserting, but the approach action itself still does not reliably reduce socket-frame lateral error.
- `position_ready=0.000` throughout, so the failure is earlier than rotation or insertion.
- The final row is suspect because `240` steps matches the default `8.0s` episode timeout. Isaac Lab can auto-reset at timeout, making `final_*` potentially post-reset rather than terminal rollout state.

Follow-up fix:

- `scripts/scripted_agent.py` now extends `env_cfg.episode_length_s` to cover the requested scripted horizon.
- The summary now records `best_lateral`, `best_axial`, and `best_rot` with step indices, so timeout/reset artifacts do not hide mid-rollout behavior.
- The script now supports `--debug-action-steps N` to print first-step action-frame diagnostics before opening a longer GPU run.

Local outputs:

- `artifacts/evaluations/scripted/2026-05-14T18-58-33Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-14T18-58-33Z/seed_42.log`
- `artifacts/gpu_gate/2026-05-14T18-34-53Z_isaac-phase2-gate-l4/gate.log`

## Revised Next Decision

Do not run PPO yet.

## Attempt 8: Short L4 Action-Frame Diagnostic

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-action-debug-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_STEPS=20 \
RCA_GATE_EXTRA_AGENT_ARGS='--debug-action-steps 5' \
scripts/run_guarded_phase2_gate.sh
```

Result:

- Brev successfully created `isaac-phase2-action-debug-l4`.
- Runtime bootstrap completed.
- A 20-step scripted diagnostic ran with the first 5 actions printed.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- Deletion lingered in `DELETING`, then the guarded script confirmed no visible instances.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "initial_lateral": 0.0942068099975586,
  "final_lateral": 0.36806532740592957,
  "best_lateral": 0.0711970403790474,
  "best_lateral_step": 3,
  "initial_axial": 0.2691607177257538,
  "final_axial": 0.4828592538833618,
  "best_axial": 0.2691607177257538,
  "best_axial_step": 0,
  "initial_rot": 2.351423501968384,
  "final_rot": 2.542243480682373,
  "best_rot": 2.0225918292999268,
  "best_rot_step": 10,
  "final_success_rate": 0.0
}
```

Key diagnostic evidence:

```text
step=0000 action_pos.z=0.3812 approach_pos.z=0.2400 pos_error.z=-0.1412 raw_action.z=-0.1200
step=0001 action_pos.z=0.4169
step=0002 action_pos.z=0.4531
step=0003 action_pos.z=0.4897
step=0004 action_pos.z=0.5256
```

Interpretation:

- The raw command asked the tip to move downward in world Z, but the next action-frame poses moved upward.
- Y also drifted opposite the world-frame correction direction.
- X moved in the expected direction.
- This strongly indicates that `DifferentialInverseKinematicsAction` interprets the translational delta in the controlled frame, not directly in world coordinates.
- The previous scripted controller fed world-frame position error into a frame-local relative IK action.

Follow-up fix:

- `scripts/scripted_agent.py` now rotates world-frame `pos_error` into the current action frame before filling `actions[:, :3]`.
- `scripts/live_step_scripted_baseline.py` now uses the same local-frame translation command.
- `scripts/debug_pose_alignment.py` now uses the same local-frame translation command.
- The next validation should be another short 20-step diagnostic first, not PPO.

Local outputs:

- `artifacts/evaluations/scripted/2026-05-14T19-25-50Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-14T19-25-50Z/seed_42.log`
- `artifacts/gpu_gate/2026-05-14T19-07-57Z_isaac-phase2-action-debug-l4/gate.log`

## Revised Next Decision 2

Do not run PPO yet.

## Attempt 9: L4 Diagnostic With Inverse-Rotated Translation

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-local-frame-debug-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_STEPS=20 \
RCA_GATE_EXTRA_AGENT_ARGS='--debug-action-steps 5' \
scripts/run_guarded_phase2_gate.sh
```

Result:

- Brev successfully created `isaac-phase2-local-frame-debug-l4`.
- Runtime bootstrap completed.
- A 20-step diagnostic ran with inverse-rotated translation commands.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- The guarded script and independent checks confirmed no visible instances:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "initial_lateral": 0.09411080181598663,
  "final_lateral": 0.3611857295036316,
  "best_lateral": 0.06679326295852661,
  "best_lateral_step": 3,
  "initial_axial": 0.2691607177257538,
  "final_axial": 0.5302352905273438,
  "best_axial": 0.2691607177257538,
  "best_axial_step": 0,
  "initial_rot": 2.3528833389282227,
  "final_rot": 2.4263880252838135,
  "best_rot": 2.040851354598999,
  "best_rot_step": 9,
  "final_success_rate": 0.0
}
```

Key diagnostic evidence:

```text
step=0000 pos_error.z=-0.1412 action_pos_error.z=-0.1254 raw_action.z=-0.1200
step=0001 action_pos.z=0.4169
step=0002 action_pos.z=0.4530
step=0003 action_pos.z=0.4890
step=0004 action_pos.z=0.5252
```

Interpretation:

- Inverse-rotating the world error was not the correct action mapping.
- The command still moved the tip upward when the desired world correction was downward.
- The observed mapping suggests the action-space translation basis needs the opposite y/z signs from the inverse-rotated vector.

Follow-up fix:

- Replace the inverse rotation with forward quaternion rotation for the action-space translation vector.
- Keep the debug output label as `action_pos_error` so future logs show the command-space vector directly.

Local outputs:

- `artifacts/evaluations/scripted/2026-05-14T19-59-23Z/seed_42.json`
- `artifacts/evaluations/scripted/2026-05-14T19-59-23Z/seed_42.log`
- `artifacts/gpu_gate/2026-05-14T19-37-29Z_isaac-phase2-local-frame-debug-l4/gate.log`

## Revised Next Decision 3

Do not run PPO yet.

Next useful action:

1. Commit the forward-rotated action-space translation fix.
2. Run one more 20-step L4 diagnostic with `--debug-action-steps 5`.
3. Pass condition for the diagnostic: after a negative world-Z error, the next `action_pos.z` must decrease toward the approach pose instead of increase.
4. Only if the diagnostic passes should a 240-step scripted gate be run.

Pass condition remains:

- scripted final lateral and axial errors improve from reset
- rotation no longer remains near `~2 rad`
- `best_lateral` reaches the approach corridor or final pose is close enough to justify one short PPO smoke

## Attempt 10: L4 Diagnostic With Forward-Rotated Translation

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-forward-debug-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_STEPS=20 \
RCA_GATE_EXTRA_AGENT_ARGS='--debug-action-steps 5' \
scripts/run_guarded_phase2_gate.sh
```

Result:

- Brev successfully created `isaac-phase2-forward-debug-l4`.
- Runtime bootstrap completed and registered the contact task.
- The scripted evaluation timed out with status `124`.
- No eval JSON was produced.
- The pulled log stopped during Isaac headless startup before `AppLauncher initialization complete`, environment setup, or any `[ACTION-DEBUG]` output.
- Cleanup deleted the instance.
- The guarded script and independent checks confirmed no visible instances:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Key evidence:

```text
[INFO]: Loading experience file: /workspace/IsaacLab/apps/isaaclab.python.headless.kit
E0000 ... descriptor_database.cc:633] File already exists in database: grpc/health/v1/health.proto
W0000 ... message.cc:301] Protobuf GeneratedMessageFactory: File is already registered: grpc/health/v1/health.proto
[scripted-eval] seed=42 failed with status=124
```

Interpretation:

- This attempt did not validate or invalidate the forward-rotated action mapping.
- The timeout happened before the task entered the control loop, so there are no action-frame diagnostics to interpret.
- Older L4 runs reached `AppLauncher initialization complete` and the action loop from the same `health: starting` container state, so this is best treated as an intermittent Isaac/Brev headless startup hang rather than a controller regression.

Follow-up fix:

- `scripts/run_remote_scripted_eval.sh` now supports same-instance retries through `RCA_SCRIPTED_EVAL_RETRIES` and defaults to one retry.
- Each retry writes a distinct log path (`seed_<seed>_attempt_<n>.log`) while keeping the final summary path stable.
- Failed attempts remove stale summary JSON before rerun and kill any leftover `scripts/scripted_agent.py` process before retrying.

Next useful action:

1. Do not run PPO yet.
2. Re-run the same 20-step diagnostic once, relying on the same-instance retry wrapper if the first Isaac launch hangs.
3. Pass condition remains unchanged: after a negative world-Z error, the next `action_pos.z` must decrease toward the approach pose instead of increasing.

## Attempt 11: Forward-Rotated Translation With Same-Instance Retry Wrapper

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-forward-retry-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=1 \
RCA_GATE_STEPS=20 \
RCA_GATE_EXTRA_AGENT_ARGS='--debug-action-steps 5' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- The live price table showed `g2-standard-4:nvidia-l4:1` at `$0.85/hr`.
- The cheapest visible L40S candidate was about `$1.86/hr`.
- L4 remained the cheapest viable option for short scripted diagnostics.

Result:

- Brev successfully created `isaac-phase2-forward-retry-l4`.
- Runtime bootstrap completed.
- The first scripted attempt ran successfully; the retry path was not needed.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "initial_lateral": 0.0947134792804718,
  "final_lateral": 0.36225566267967224,
  "best_lateral": 0.06749198585748672,
  "best_lateral_step": 3,
  "initial_axial": 0.2692587077617645,
  "final_axial": 0.5294179320335388,
  "best_axial": 0.2692587077617645,
  "best_axial_step": 0,
  "initial_rot": 2.3530170917510986,
  "final_rot": 2.4446558952331543,
  "best_rot": 2.036428689956665,
  "best_rot_step": 9,
  "final_success_rate": 0.0
}
```

Key diagnostic evidence:

```text
step=0000 pos_error.z=-0.1412 action_pos_error.z=-0.1384 raw_action.z=-0.1200
step=0001 action_pos.z=0.4170
step=0002 action_pos.z=0.4532
step=0003 action_pos.z=0.4893
step=0004 action_pos.z=0.5253
```

Interpretation:

- Forward-rotating the world error still produced a negative Z action command.
- A negative Z action command still moved the action frame upward in world Z.
- Across the direct, inverse-rotated, and forward-rotated diagnostics, the observed translational action mapping is consistent with:
  - action X: same sign as desired world correction
  - action Y: opposite sign
  - action Z: opposite sign
- The controller problem is therefore no longer "which quaternion transform"; it is a translational action-axis sign convention mismatch.

Follow-up fix:

- `scripts/scripted_agent.py` now applies explicit translational action-axis signs, defaulting to `1,-1,-1`.
- The sign convention is configurable with `--action-axis-signs`.
- Debug output now prints both `action_pos_error` and `signed_action_pos_error`.
- `scripts/live_step_scripted_baseline.py` and `scripts/debug_pose_alignment.py` were updated to use the same default sign convention.

Next useful action:

1. Do not run PPO yet.
2. Locally validate the updated scripts with `py_compile`, `bash -n`, and `git diff --check`.
3. Commit the axis-sign fix.
4. Only then run one last 20-step diagnostic; pass condition is `raw_action.z > 0` at step 0 and `action_pos.z` decreasing on subsequent steps.

## Attempt 12: Explicit Axis Signs Still Diverge; Switch to Empirical Action Calibration

Command:

```bash
RCA_GATE_INSTANCE_NAME=isaac-phase2-axis-sign-debug-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=1 \
RCA_GATE_STEPS=20 \
RCA_GATE_EXTRA_AGENT_ARGS='--debug-action-steps 5' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- The live price table again showed `g2-standard-4:nvidia-l4:1` at `$0.85/hr`.
- L4 was kept as the cheapest viable GPU for short diagnostics.

Result:

- Brev created `isaac-phase2-axis-sign-debug-l4`.
- Runtime bootstrap completed and the scripted diagnostic ran successfully.
- Artifacts were pulled locally:
  - `artifacts/evaluations/scripted/2026-05-14T21-21-42Z/seed_42.json`
  - `artifacts/evaluations/scripted/2026-05-14T21-21-42Z/seed_42.log`
- Cleanup deleted the instance.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "action_axis_signs": [1.0, -1.0, -1.0],
  "initial_lateral": 0.09528831392526627,
  "final_lateral": 0.4290759265422821,
  "best_lateral": 0.07055511325597763,
  "best_lateral_step": 3,
  "initial_axial": 0.27065590023994446,
  "final_axial": 0.5879666209220886,
  "best_axial": 0.27065590023994446,
  "best_axial_step": 0,
  "initial_rot": 2.3564226627349854,
  "final_rot": 2.34665846824646,
  "best_rot": 1.9514362812042236,
  "best_rot_step": 11,
  "final_success_rate": 0.0
}
```

Key diagnostic evidence:

```text
step=0000 pos_error.z=-0.1412 action_pos_error.z=-0.1384 signed_action_pos_error.z=0.1384 raw_action.z=0.1200
step=0001 action_pos.z=0.4181
step=0002 action_pos.z=0.4553
step=0003 action_pos.z=0.4927
step=0004 action_pos.z=0.5301
```

Interpretation:

- The explicit axis-sign hypothesis was invalidated.
- The corrected command changed `raw_action.z` from negative to positive, but the action frame still moved upward and farther away from the approach pose.
- The failure is not a simple per-axis sign mismatch. X/Y/Z responses are coupled under the relative IK action, and saturated multi-axis scripted commands are not sufficient evidence for selecting signs.
- Re-reading the Isaac Lab relative IK implementation clarifies that the translational part of `apply_delta_pose()` is applied as `target_pos = source_pos + delta_pose[:, 0:3]`; the scripted controller should not rotate position error into the end-effector frame.

Follow-up fix:

- Reverted the scripted controller, live visual stepper, and pose debug script to root-frame translational deltas.
- Reset default `--action-axis-signs` to `1,1,1`; the option remains available for controlled experiments.
- Added `scripts/calibrate_relative_ik_action.py` to empirically probe one-hot `+/-X`, `+/-Y`, and `+/-Z` actions from the same deterministic reset.
- Added `scripts/run_remote_action_calibration.sh`.
- Extended `scripts/run_guarded_phase2_gate.sh` with `RCA_GATE_COMMAND=action_calibration` so calibration uses the same guarded create/pull/delete flow and post-delete checks.

Next useful action:

1. Do not run PPO yet.
2. Run one minimal action calibration gate on L4:

```bash
RCA_GATE_COMMAND=action_calibration \
RCA_GATE_INSTANCE_NAME=isaac-phase2-action-calibration-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_ACTION_CALIBRATION_RETRIES=1 \
RCA_GATE_STEPS=4 \
scripts/run_guarded_phase2_gate.sh
```

3. Use the measured `response_matrix_world_delta_per_raw_action` to decide whether the scripted baseline can stay in relative IK mode or should switch to an absolute target-pose IK wrapper.

## Attempt 13: Warmup Calibration Then Scripted Gate on the Same L4

Command:

```bash
RCA_GATE_COMMAND=calibration_then_scripted_eval \
RCA_GATE_INSTANCE_NAME=isaac-phase2-warmup-combined-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_ACTION_CALIBRATION_RETRIES=1 \
RCA_SCRIPTED_EVAL_RETRIES=1 \
RCA_GATE_CALIBRATION_STEPS=4 \
RCA_GATE_SCRIPTED_STEPS=80 \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Explicitly used `g2-standard-4:nvidia-l4:1`.
- The live price table again showed the L4 as the cheapest viable option at about `$0.85/hr`.

Artifacts:

- Calibration JSON: `artifacts/calibration/relative_ik_action/2026-05-14T22-20-37Z/seed_42.json`
- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-14T22-21-36Z/seed_42.json`
- Gate log: `artifacts/gpu_gate/2026-05-14T22-05-29Z_isaac-phase2-warmup-combined-l4/gate.log`

Result:

- Runtime bootstrap completed.
- Calibration and scripted eval both ran successfully on the same instance.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- The guarded script confirmed `No instances in org NCA-57cf-29515`.
- Independent checks also returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Calibration metrics:

```json
{
  "zero_delta_action_pos": [-0.001131683588027954, 0.014671146869659424, 0.0016485750675201416],
  "response_matrix_world_delta_per_raw_action": [
    [0.06291121244430542, -0.035278186202049255, 0.05632166936993599],
    [-0.019952405244112015, 0.04557172209024429, 0.019709020853042603],
    [-0.003956382162868977, 0.020646551623940468, 0.05501943081617355]
  ]
}
```

Scripted metrics:

```json
{
  "initial_lateral": 0.533628523349762,
  "final_lateral": 0.5557739734649658,
  "best_lateral": 0.26182493567466736,
  "best_lateral_step": 19,
  "initial_axial": 0.26867949962615967,
  "final_axial": 0.34838253259658813,
  "best_axial": 0.10499545931816101,
  "best_axial_step": 12,
  "initial_rot": 3.1094396114349365,
  "final_rot": 1.0175015926361084,
  "best_rot": 0.14498676359653473,
  "best_rot_step": 50,
  "final_success_rate": 0.0
}
```

Interpretation:

- The 30-step zero-action warmup fixed the major reset transient. Previous calibration saw about `+0.147 m` z drift under zero action; this run reduced zero-action z drift over four steps to about `+0.0016 m`.
- The direct proportional scripted controller still fails because the relative IK action response is coupled. It briefly improves both lateral and axial errors, but then overshoots/diverges.
- The controller should stop issuing saturated multi-axis position commands. The useful next step is a calibrated one-hot scripted controller that chooses the empirically best one-hot raw action from the calibration JSON at each control step.

Follow-up fix:

- `scripts/scripted_agent.py` now supports `--position-control-mode calibrated-onehot`.
- The calibrated mode loads the calibration JSON and greedily selects the one-hot raw action predicted to reduce root-frame position error, avoiding cancellation from saturated multi-axis commands.
- `scripts/run_remote_action_calibration.sh` now copies the latest calibration JSON to a stable path:
  - `/workspace/artifacts/calibration/relative_ik_action/latest_seed_<seed>.json`
- `scripts/run_guarded_phase2_gate.sh` now supports separate calibration/scripted extra args and `RCA_GATE_USE_CALIBRATED_SCRIPTED=1` for calibration-then-scripted gates.

Next useful action:

1. Run local syntax checks.
2. Commit the calibrated scripted-controller plumbing.
3. Run one short L4 gate with `RCA_GATE_USE_CALIBRATED_SCRIPTED=1`, `RCA_GATE_SCRIPTED_STEPS=80`, and `--debug-action-steps 8`.
4. Pass condition: final lateral/axial should be better than initial, or at least best lateral/axial should improve without the late-run divergence seen in this attempt.

## Attempt 14: Calibrated One-Hot Gate Blocked by Partial Brev Create Failure

Command:

```bash
RCA_GATE_COMMAND=calibration_then_scripted_eval \
RCA_GATE_USE_CALIBRATED_SCRIPTED=1 \
RCA_GATE_INSTANCE_NAME=isaac-phase2-calibrated-onehot-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_ACTION_CALIBRATION_RETRIES=1 \
RCA_SCRIPTED_EVAL_RETRIES=1 \
RCA_GATE_CALIBRATION_STEPS=4 \
RCA_GATE_SCRIPTED_STEPS=80 \
RCA_GATE_SCRIPTED_EXTRA_AGENT_ARGS='--debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Result:

- The price snapshot was recorded.
- The L4 remained the cheapest viable option at about `$0.85/hr`.
- Brev API returned `unexpected EOF` during `createWorkspace`.
- The CLI reported `created 0/1 instances`.
- Despite that failure, the org later showed a partially created instance:
  - name: `isaac-phase2-calibrated-onehot-l4`
  - id: `ongdllsy5`
  - type: `g2-standard-4:nvidia-l4:1`
  - status sequence observed: `STARTING/PENDING` -> `RUNNING/BUILDING` -> `DELETING`
- No Isaac runtime was installed.
- No calibration or scripted eval ran.
- The instance was manually deleted after the first cleanup delete hit a Brev backend timeout.
- Final independent checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Local log:

- `artifacts/gpu_gate/2026-05-14T22-32-20Z_isaac-phase2-calibrated-onehot-l4/gate.log`

Interpretation:

- This was a Brev control-plane partial-create failure, not a project-code failure.
- The key safety lesson is that `brev create` can return failure while a billable instance still appears shortly afterward.
- This is the same class of risk as the previous ghost-instance incidents; do not retry immediately when the control plane behaves this way.

Follow-up safety fix:

- `scripts/run_guarded_phase2_gate.sh` now re-issues `brev delete <instance>` during cleanup if the target instance remains visible.
- The retry is rate-limited by `RCA_GATE_DELETE_RETRY_INTERVAL_SECONDS` and only targets the instance name created by the current gate.

Next useful action:

1. Do not open another GPU immediately after this partial-create failure.
2. Commit the repeated-delete cleanup fix.
3. Later, rerun the calibrated one-hot gate only after Brev instance listing is stable and the org is confirmed empty.

## Attempt 15: Calibrated One-Hot Gate Runs but Diverges

Command:

```bash
RCA_GATE_COMMAND=calibration_then_scripted_eval \
RCA_GATE_USE_CALIBRATED_SCRIPTED=1 \
RCA_GATE_INSTANCE_NAME=isaac-phase2-calibrated-onehot-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_ACTION_CALIBRATION_RETRIES=1 \
RCA_SCRIPTED_EVAL_RETRIES=1 \
RCA_GATE_CALIBRATION_STEPS=4 \
RCA_GATE_SCRIPTED_STEPS=80 \
RCA_GATE_SCRIPTED_EXTRA_AGENT_ARGS='--debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Explicitly used `g2-standard-4:nvidia-l4:1`.
- The live price table showed L4 at about `$0.85/hr`; the cheapest visible L40S was about `$1.86/hr`.

Artifacts:

- Calibration JSON: `artifacts/calibration/relative_ik_action/2026-05-15T07-32-28Z/seed_42.json`
- Latest calibration copy: `artifacts/calibration/relative_ik_action/latest_seed_42.json`
- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T07-33-27Z/seed_42.json`
- Gate log: `artifacts/gpu_gate/2026-05-15T07-18-37Z_isaac-phase2-calibrated-onehot-l4/gate.log`

Result:

- Brev created the L4 instance successfully.
- Runtime bootstrap completed.
- Calibration and calibrated scripted eval both ran successfully.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- Repeated delete retries fired while the instance remained visible in `DELETING`.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "position_control_mode": "calibrated-onehot",
  "action_dim": 6,
  "initial_lateral": 0.5341109037399292,
  "final_lateral": 0.9221593737602234,
  "best_lateral": 0.25000542402267456,
  "best_lateral_step": 15,
  "initial_axial": 0.26906704902648926,
  "final_axial": 0.3946937918663025,
  "best_axial": 0.17156338691711426,
  "best_axial_step": 6,
  "initial_rot": 3.1208298206329346,
  "final_rot": 1.2936623096466064,
  "best_rot": 0.5582655072212219,
  "best_rot_step": 36,
  "final_success_rate": 0.0
}
```

Key debug evidence:

```text
step=0000 selected_calibrated_action=z_pos raw_action=[0.0, 0.0, 0.12, ...]
step=0001 selected_calibrated_action=z_pos raw_action=[0.0, 0.0, 0.12, ...]
...
step=0007 selected_calibrated_action=z_pos raw_action=[0.0, 0.0, 0.12, ...]
```

Interpretation:

- The calibrated one-hot controller reduced axial error early, but it behaved like a repeated `z_pos` macro-action and did not switch phases soon enough.
- It is worse than the direct controller in final metrics.
- This invalidates further reward/controller polishing on the 6D relative IK scripted path.
- The next controller-level baseline should use absolute pose IK instead of relative deltas.

Follow-up fix:

- Added absolute-pose contact task configs:
  - `FrankaPegInHoleContactAbsEnvCfg`
  - `FrankaPegInHoleContactAbsEnvCfg_PLAY`
- Registered new task IDs:
  - `RCA-PegInHole-Franka-IK-Abs-Contact-v0`
  - `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
- Updated `scripts/scripted_agent.py` to detect 7D action spaces and send absolute pose commands as `(x, y, z, qw, qx, qy, qz)`.

Next useful action:

1. Commit the absolute-pose fallback locally.
2. Run one short scripted gate on `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`.
3. If absolute pose IK produces a stable approach trajectory, use that as the scripted baseline and stop trying to rescue relative scripted control.
4. If absolute pose IK also fails, move the baseline to joint-space waypoints or an explicit motion-planning/IK pre-controller before PPO.

## Attempt 16: Absolute-Pose IK Gate Runs but Does Not Yet Insert

Command:

```bash
RCA_GATE_COMMAND=scripted_eval \
RCA_GATE_TASK='RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0' \
RCA_GATE_INSTANCE_NAME=isaac-phase2-abs-scripted-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=1 \
RCA_GATE_STEPS=80 \
RCA_GATE_EXTRA_AGENT_ARGS='--debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Explicitly used `g2-standard-4:nvidia-l4:1`.
- The live price table showed L4 at about `$0.85/hr`; the cheapest visible L40S was about `$1.86/hr`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T08-00-41Z/seed_42.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T08-00-41Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T07-45-08Z_isaac-phase2-abs-scripted-l4/gate.log`
- Gate metadata: `artifacts/gpu_gate/2026-05-15T07-45-08Z_isaac-phase2-abs-scripted-l4/gate_metadata.env`

Runtime result:

- Brev created the L4 instance successfully.
- Runtime bootstrap completed.
- The new absolute-pose contact task registered successfully:
  - `RCA-PegInHole-Franka-IK-Abs-Contact-v0`
  - `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
- Isaac Lab reported `Action Manager` shape `(7)`, confirming the absolute pose controller path is active.
- The scripted agent sent 7D absolute pose commands as `(x, y, z, qw, qx, qy, qz)`.
- Artifacts were pulled locally.
- Cleanup deleted the instance.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "position_control_mode": "direct",
  "action_dim": 7,
  "task": "RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0",
  "initial_lateral": 0.46553295850753784,
  "final_lateral": 0.13741105794906616,
  "best_lateral": 0.11433365195989609,
  "best_lateral_step": 74,
  "initial_axial": 0.3015425503253937,
  "final_axial": 0.31580662727355957,
  "best_axial": 0.06215125322341919,
  "best_axial_step": 21,
  "initial_rot": 3.053060293197632,
  "final_rot": 2.415803909301758,
  "best_rot": 0.9065385460853577,
  "best_rot_step": 36,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Interpretation:

- Absolute-pose IK is a better controller interface than the 6D relative IK path: it launched cleanly, exposed the expected 7D action space, and reduced final lateral error from `0.4655 m` to `0.1374 m`.
- It is still not a successful scripted baseline. Axial error briefly improved to `0.0622 m` but ended at `0.3158 m`, and rotation improved only transiently.
- The debug trace shows the policy repeatedly commanding the fixed approach pose while the end-effector oscillates around it. This suggests the remaining issue is not task registration or action dimensionality; it is the scripted controller strategy and/or the initial EE-to-socket reach problem.
- PPO should not be run yet. A learned policy would be learning around a controller/task setup that does not have a sane deterministic baseline.

Next useful action:

1. Stop spending GPU time on the current 80-step scripted rollout.
2. Locally improve the baseline before opening another instance:
   - add a deterministic reset/debug command that places the socket closer to the Franka reachable workspace;
   - add a staged absolute-pose scripted controller with explicit reach, align, descend, and settle phases;
   - reduce or disable random socket pose for the first deterministic gate;
   - record per-step commanded pose, achieved tip pose, and socket pose in JSON for controller debugging.
3. Reopen one short L4 gate only after the local changes compile.
4. Pass condition for the next gate: deterministic scripted rollout should monotonically reduce lateral error below `5 cm` and axial error below `8 cm` before any PPO attempt.

Follow-up fix:

- `scripts/scripted_agent.py` now supports deterministic controller gates:
  - `--deterministic-reset` disables reset joint randomization.
  - `--socket-pos x,y,z` overrides the fixed socket and guide-wall positions for reachability debugging.
  - `--abs-control-mode waypoint` sends small absolute waypoints toward the phase target instead of commanding the full target pose in one step.
  - `--trace-json <path>` writes per-step action-frame pose, socket pose, command pose, raw action, phase, and insertion metrics.
- `scripts/run_remote_scripted_eval.sh` now supports `RCA_SCRIPTED_TRACE_JSON=1` to pull per-seed trace files with the normal evaluation artifacts.

## Attempt 17: Absolute Waypoint Gate Reaches Axial Depth but Loses Lateral Control

Command:

```bash
RCA_SCRIPTED_TRACE_JSON=1 \
RCA_GATE_COMMAND=scripted_eval \
RCA_GATE_TASK='RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0' \
RCA_GATE_INSTANCE_NAME=isaac-phase2-abs-waypoint-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=360 \
RCA_SCRIPTED_EVAL_RETRIES=0 \
RCA_GATE_STEPS=160 \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --abs-control-mode waypoint --abs-pos-step 0.015 --abs-rot-step 0.12 --debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Live price table was recorded in the gate log.
- Explicitly used `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The cheapest visible L40S was about `$1.86/hr`, so L4 remained the better fit for this short scripted gate.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T08-30-05Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T08-30-05Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T08-30-05Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T08-15-21Z_isaac-phase2-abs-waypoint-l4/gate.log`

Cleanup:

- Artifacts were pulled locally.
- The instance was deleted.
- Repeated delete retries fired while the instance remained visible in `DELETING`.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "abs_control_mode": "waypoint",
  "action_dim": 7,
  "deterministic_reset": true,
  "initial_lateral": 0.46638020873069763,
  "final_lateral": 0.8070624470710754,
  "best_lateral": 0.37033623456954956,
  "best_lateral_step": 55,
  "initial_axial": 0.30189695954322815,
  "final_axial": 0.2839994430541992,
  "best_axial": 0.00064048171043396,
  "best_axial_step": 86,
  "initial_rot": 2.9845430850982666,
  "final_rot": 2.9356377124786377,
  "best_rot": 2.187131404876709,
  "best_rot_step": 114,
  "final_success_rate": 0.0
}
```

Trace highlights:

```text
best_lateral_step=55:  lateral=0.3703, axial not solved, action_pos=[0.2134, 0.0369, 0.4303]
best_axial_step=86:   axial=0.0006, lateral still high, action_pos=[0.2088, 0.2143, 0.2316]
final_step=159:       lateral=0.8071, action_pos=[-0.2230, -0.4969, 0.4683]
```

Interpretation:

- The new trace proves the 7D absolute waypoint code path is active and producing bounded local commands.
- The controller can reach the socket depth transiently (`best_axial=0.0006 m`) but cannot maintain lateral alignment.
- Because `position_ready` never becomes true, the controller never leaves the reach phase; the failure is not an insertion/rotation phase issue yet.
- The achieved end-effector pose eventually drifts into negative world x/y, which suggests the current default socket location plus fixed orientation is a poor deterministic target for this IK setup.

Next useful action:

1. Do one cheaper debug gate using the same waypoint controller but override the socket to a reachable target near the best lateral waypoint, for example `--socket-pos 0.22,0.04,0.19`.
2. If the near-socket gate also fails, stop using DifferentialIK as the scripted baseline and move to joint-space waypoint control or a motion-planning pre-controller.
3. If the near-socket gate succeeds, keep the controller and then gradually move the socket back toward the default location.

## Attempt 18: Near-Socket Absolute Waypoint Gate Still Fails

Command:

```bash
RCA_SCRIPTED_TRACE_JSON=1 \
RCA_GATE_COMMAND=scripted_eval \
RCA_GATE_TASK='RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0' \
RCA_GATE_INSTANCE_NAME=isaac-phase2-abs-near-socket-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=0 \
RCA_GATE_STEPS=120 \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --socket-pos 0.22,0.04,0.19 --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Live price table again showed `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The cheapest visible L40S was about `$1.86/hr`.
- L4 was selected because this was a short deterministic gate, not a PPO training run.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T08-52-59Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T08-52-59Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T08-52-59Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T08-37-14Z_isaac-phase2-abs-near-socket-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance entered `DELETING` and required repeated delete retries plus one manual delete by instance id `vniudqpkw`.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "abs_control_mode": "waypoint",
  "action_dim": 7,
  "deterministic_reset": true,
  "socket_pos_override": [0.22, 0.04, 0.19],
  "initial_lateral": 0.21771036088466644,
  "final_lateral": 0.39793357253074646,
  "best_lateral": 0.08073757588863373,
  "best_lateral_step": 58,
  "initial_axial": 0.3017815947532654,
  "final_axial": 0.14066651463508606,
  "best_axial": 0.004813969135284424,
  "best_axial_step": 95,
  "initial_rot": 2.9826011657714844,
  "final_rot": 2.190831184387207,
  "best_rot": 2.0773112773895264,
  "best_rot_step": 115,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step=0:   lateral=0.2177, axial=0.3018, rot=2.9826, phase=reach
step=58:  best lateral=0.0807, axial=0.2043, rot=2.9757, phase=reach
step=95:  best axial=0.0048, lateral=0.2170, rot=2.4041, phase=reach
step=115: best rot=2.0773, lateral=0.3874, axial=0.1583, phase=reach
step=119: final lateral=0.3979, axial=0.1407, rot=2.1908, phase=reach
```

Interpretation:

- Moving the socket close to the most reachable previous region reduced the initial lateral error from `0.4664 m` to `0.2177 m`, but still did not produce a deterministic success.
- The controller can transiently optimize one metric at a time: lateral improves at step 58, axial improves at step 95, and rotation improves late. They do not converge together.
- The rollout never leaves the `reach` phase because the lateral threshold is never reached. This means the remaining issue is not insertion reward shaping or PPO; it is the scripted control interface.
- Continuing to tune DifferentialIK waypoints is now low-value. The project needs a more reliable baseline controller before another RL run.

Next useful action:

1. Stop spending GPU on the current DifferentialIK scripted baseline.
2. Implement a joint-space waypoint or motion-planning pre-controller for deterministic approach/alignment.
3. Keep the current contact task, contact observations, artifact pipeline, and guarded GPU workflow.
4. Reopen one short L4 gate only after the new controller passes local syntax checks and has a fixed pass/fail criterion.

## Attempt 19: Joint-IK Gate Added Locally, Brev Startup Did Not Reach Ready

Local implementation:

- Added `RCA-PegInHole-Franka-JointPos-Contact-v0`.
- Added `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`.
- Added `--scripted-control-mode joint-ik` to `scripts/scripted_agent.py`.
- The new scripted path uses Isaac Lab's standalone `DifferentialIKController` with the robot Jacobian and sends direct 7-DoF Franka joint-position targets to the task action term.
- Local checks passed:
  - `python3 -m py_compile scripts/scripted_agent.py`
  - `python3 -m py_compile source/.../config/franka/ik_rel_env_cfg.py source/.../config/franka/__init__.py`
  - `git diff --check`

First launch attempt:

```bash
RCA_GATE_TASK='RCA-PegInHole-Franka-JointPos-Contact-Play-v0' \
RCA_GATE_INSTANCE_NAME=isaac-phase2-jointik-l4 \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --socket-pos 0.22,0.04,0.19 --scripted-control-mode joint-ik --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Result:

- No instance was created.
- Brev API failed during workspace creation with `unexpected EOF`.
- Guard cleanup still issued a delete by name.
- Independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Second launch attempt:

```bash
RCA_SCRIPTED_TRACE_JSON=1 \
RCA_GATE_COMMAND=scripted_eval \
RCA_GATE_TASK='RCA-PegInHole-Franka-JointPos-Contact-Play-v0' \
RCA_GATE_INSTANCE_NAME=isaac-phase2-jointik-l4-retry \
RCA_GATE_INSTANCE_TYPE='g2-standard-4:nvidia-l4:1' \
RCA_GATE_CREATE_TIMEOUT=900 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=240 \
RCA_SCRIPTED_EVAL_RETRIES=0 \
RCA_GATE_STEPS=100 \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --socket-pos 0.22,0.04,0.19 --scripted-control-mode joint-ik --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --debug-action-steps 8' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Live price table again selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- Lowest visible L40S remained about `$1.86/hr`.
- L4 was the correct cost/performance choice for a short registration/controller gate.

Result:

- Instance was created: `isaac-phase2-jointik-l4-retry`, id `g1z7kfpp3`.
- The instance stayed in `RUNNING / BUILDING / NOT READY` too long to justify continued waiting.
- It never reached runtime setup and no scripted eval was executed.
- Manual delete was issued by id and by name.
- The instance moved through `DELETING` and `STOPPING`, then disappeared from the org.

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-15T09-11-59Z_isaac-phase2-jointik-l4-retry/gate.log`
- Price tables:
  - `artifacts/gpu_gate/2026-05-15T09-11-59Z_isaac-phase2-jointik-l4-retry/brev_search_24gb.txt`
  - `artifacts/gpu_gate/2026-05-15T09-11-59Z_isaac-phase2-jointik-l4-retry/brev_search_32gb.txt`
  - `artifacts/gpu_gate/2026-05-15T09-11-59Z_isaac-phase2-jointik-l4-retry/brev_search_40gb.txt`

Cleanup:

- Final guarded check returned no visible instances.
- Final independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Interpretation:

- The project now has the right next controller path in code: a joint-position task plus standalone Jacobian IK scripted controller.
- This attempt did not validate the controller because Brev startup failed before runtime setup.
- Do not run PPO yet.
- Next GPU attempt should be another short L4 validation of the same joint-IK task, but only after confirming Brev startup is healthy. If Brev repeats `BUILDING/NOT READY`, stop and avoid more cloud time.

Follow-up guard hardening:

- `scripts/run_guarded_phase2_gate.sh` now aborts early when the instance stays in `RUNNING / BUILDING / NOT READY` for `RCA_GATE_BUILD_STUCK_SECONDS` seconds.
- Cleanup now deletes by instance name first, then queries the JSON instance list and also deletes by exact instance id if the target is still visible.
- `scripts/run_phase2_jointik_gate.sh` captures the next Joint-IK validation command as a one-command wrapper with a tighter `RCA_GATE_BUILD_STUCK_SECONDS=300`.
- No GPU was started for this hardening change.

## Attempt 20: Joint-IK Runtime Reached Isaac, Failed on Warp Jacobian Indexing

Command:

```bash
scripts/run_phase2_jointik_gate.sh
```

Price selection:

- Live price table again selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S remained about `$1.86/hr`.
- L4 was the correct cost/performance choice for this short controller validation.

Result:

- Instance was created: `isaac-phase2-jointik-l4`, id `as04ieyo0`.
- The instance initially reported `RUNNING / BUILDING / NOT READY`, then became `RUNNING / COMPLETED / READY` before the build-stuck guard fired.
- Remote probe succeeded:
  - GPU: `NVIDIA L4`, 23034 MiB
  - driver: `580.126.20`
  - root disk: 125 GB, about 119 GB free
- Isaac Lab runtime setup completed.
- The joint-position contact play task registered correctly:
  - task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
  - observation width: `43`
  - action width: `7`
- The scripted eval failed immediately after warmup when the Joint-IK controller tried to index the robot Jacobian.

Failure:

```text
TypeError: '<' not supported between instances of 'list' and 'int'
```

Root cause:

- `robot.root_physx_view.get_jacobians()` returned a Warp array.
- The code indexed that Warp array with a Python list of joint ids:
  `[:, ee_jacobi_idx, :, robot_entity_cfg.joint_ids]`.
- Warp array indexing does not support that Python-list advanced indexing path.

Artifacts:

- Eval log: `artifacts/evaluations/scripted/2026-05-15T10-05-00Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T09-50-43Z_isaac-phase2-jointik-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance stayed visible in `DELETING` for several polling cycles.
- The guarded script repeatedly deleted by name and id until the org was empty.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Follow-up fix:

- `scripts/scripted_agent.py` now converts the Warp Jacobian to a Torch tensor before selecting arm joints.
- Joint selection now uses Torch `index_select` for both the Jacobian and joint-position tensors.
- Local check passed:
  - `python3 -m py_compile scripts/scripted_agent.py`

Interpretation:

- This attempt validates the runtime path up to Isaac task creation and controller initialization.
- The failure is a narrow controller implementation bug, not a task registration, runtime bootstrap, or Brev readiness failure.
- The next step is one more short L4 Joint-IK gate using the same wrapper to verify the fixed Jacobian path.

## Attempt 21: Joint-IK Relaunch Failed Before Sync Due to SSH Carriage Return in Remote Path

Command:

```bash
scripts/run_phase2_jointik_gate.sh
```

Price selection:

- Live price table again selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S remained about `$1.86/hr`.
- L4 remained the correct choice for this short wrapper/controller validation.

Result:

- Instance was created: `isaac-phase2-jointik-l4`, id `7oklg0s2m`.
- The instance spent several minutes in `RUNNING / BUILDING / NOT READY`, then became `RUNNING / COMPLETED / READY`.
- Remote probe succeeded:
  - user: `ubuntu`
  - host: `brev-7oklg0s2m`
  - GPU: `NVIDIA L4`, 23034 MiB
  - driver: `580.126.20`
  - root disk: 125 GB, about 119 GB free
- The gate failed during remote workspace bootstrap before repo sync and before Isaac runtime setup.

Failure:

```text
mkdir: cannot create directory '/home/ubuntu\r': Permission denied
```

Root cause:

- The wrapper captured `REMOTE_USER` from SSH output without stripping carriage-return characters.
- The derived paths became:
  - `/home/ubuntu\r/projects/robot-contact-assembly`
  - `/home/ubuntu\r/isaac-compose`
- This corrupted the path passed to `bootstrap_brev_workspace.sh`.

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-15T10-13-02Z_isaac-phase2-jointik-l4/gate.log`
- Metadata: `artifacts/gpu_gate/2026-05-15T10-13-02Z_isaac-phase2-jointik-l4/gate_metadata.env`

Cleanup:

- Artifact pull was attempted but failed because the remote path was also corrupted.
- The guarded script deleted by name and id.
- The instance remained visible in `DELETING` for several minutes, then disappeared.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Follow-up fix:

- `scripts/run_guarded_phase2_gate.sh` now strips `\r` from `REMOTE_USER`, `REMOTE_ROOT`, and `REMOTE_COMPOSE_ROOT`.

Interpretation:

- This attempt did not exercise the Jacobian fix because it failed before repo sync.
- The remaining blocker is wrapper robustness, not task code.
- After the path sanitization fix is committed, the next short L4 gate can validate the Joint-IK controller again.

## Attempt 22: Brev Create API Returned EOF and Left a Short-Lived Deploying Record

Command:

```bash
scripts/run_phase2_jointik_gate.sh
```

Price selection:

- Live price table again selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S remained about `$1.86/hr`.
- L4 remained the correct cost/performance choice for the short validation.

Result:

- Brev `createWorkspace` returned `unexpected EOF` during workspace creation.
- The CLI reported `Warning: Only created 0/1 instances`.
- During cleanup, a short-lived partial instance was still visible:
  - name: `isaac-phase2-jointik-l4`
  - id: `elldimlih`
  - status: `DEPLOYING`
  - shell: `NOT READY`
  - type: `g2-standard-4:nvidia-l4:1`
- The gate never reached ready state, repo sync, runtime setup, or Isaac execution.

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-15T10-32-15Z_isaac-phase2-jointik-l4/gate.log`
- Metadata: `artifacts/gpu_gate/2026-05-15T10-32-15Z_isaac-phase2-jointik-l4/gate_metadata.env`

Cleanup:

- The guarded script attempted delete by name and by discovered id.
- Brev list/query APIs were intermittently returning timeout errors during cleanup.
- The script failed closed until it observed an exact empty-org state.
- Independent post-cleanup checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Follow-up check:

- `brev healthcheck` returned `Healthy!` immediately after cleanup.

Interpretation:

- This attempt did not test project code; it was a Brev API/workspace creation failure.
- The guarded cleanup behavior worked as intended and prevented a hidden partial instance from being ignored.
- One more short retry is reasonable only because healthcheck is healthy and the org is independently empty. If create fails again, stop cloud attempts and wait before retrying.

## Attempt 23: Joint-IK Gate Runs to Completion, But Unbounded IK Targets Diverge

Command:

```bash
scripts/run_phase2_jointik_gate.sh
```

Execution note:

- This attempt was run without allocating a local TTY to reduce SSH/control-character noise.

Price selection:

- Live price table again selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S remained about `$1.86/hr`.
- L4 remained the right choice for this short validation.

Result:

- Instance was created: `isaac-phase2-jointik-l4`, id `uso4ax721`.
- The instance eventually reached `RUNNING / COMPLETED / READY`.
- Remote path sanitization worked:
  - `remote_user=ubuntu`
  - `remote_root=/home/ubuntu/projects/robot-contact-assembly`
  - `remote_compose_root=/home/ubuntu/isaac-compose`
- Repo sync completed.
- Isaac Lab runtime setup completed.
- The joint-position contact play task registered correctly:
  - task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
  - observation width: `43`
  - action width: `7`
- Scripted eval completed for seed `42` and 100 steps.
- The previous Warp Jacobian list-indexing crash did not recur.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T10-53-50Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T10-53-50Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T10-53-50Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T10-38-02Z_isaac-phase2-jointik-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance was deleted by name and id.
- The instance lingered as `STOPPED` and then briefly showed `DEPLOYING` during cleanup, so the guarded script kept polling and reissuing delete.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "scripted_control_mode": "joint-ik",
  "abs_control_mode": "waypoint",
  "action_dim": 7,
  "deterministic_reset": true,
  "socket_pos_override": [0.22, 0.04, 0.19],
  "initial_lateral": 0.20348849892616272,
  "final_lateral": 0.6051559448242188,
  "best_lateral": 0.20348849892616272,
  "best_lateral_step": 0,
  "initial_axial": 0.9719375967979431,
  "final_axial": 0.547279953956604,
  "best_axial": 0.547279953956604,
  "best_axial_step": 99,
  "initial_rot": 0.8071869015693665,
  "final_rot": 2.932037353515625,
  "best_rot": 0.6570419669151306,
  "best_rot_step": 16,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step=0:  lateral=0.2035, axial=0.9719, rot=0.8072, phase=reach
step=16: best rot=0.6570, but raw joint target includes panda_joint1 ~= 14.7 rad
step=99: best axial=0.5473, lateral=0.6052, rot=2.9320, phase=reach
```

Interpretation:

- The Joint-IK runtime bug is fixed.
- The new failure is control stability: the standalone IK controller is solving a far Cartesian waypoint by producing very large absolute joint targets.
- Sending those unbounded joint-position targets directly to `JointPositionActionCfg` makes the arm move away from the socket instead of approaching it.
- This confirms PPO should still not be run yet.

Follow-up fix:

- `scripts/scripted_agent.py` now clamps standalone Joint-IK output by:
  - maximum per-step joint delta: `--joint-ik-step`, default `0.05 rad`
  - reported joint position limits with `--joint-limit-margin`, default `0.02 rad`
- The trace now records both `joint_pos_des_raw` and clamped `joint_pos_des`.
- `scripts/run_phase2_jointik_gate.sh` now passes the clamp options explicitly.

Next useful action:

- Run one more short L4 Joint-IK gate to validate whether the bounded joint target path produces stable approach behavior.

## Attempt 24: Bounded Joint-IK Gate Runs, But Still Does Not Approach the Socket

Command:

```bash
scripts/run_phase2_jointik_gate.sh
```

Price selection:

- Live price table selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S option was about `$1.86/hr`.
- L4 remained the correct choice because this was a short scripted-controller validation, not a PPO training run.

Result:

- Instance was created: `isaac-phase2-jointik-l4`, id `fezvc0vjt`.
- The instance reached `RUNNING / COMPLETED / READY`.
- Remote GPU probe succeeded:
  - GPU: `NVIDIA L4`
  - VRAM: `23034 MiB`
  - driver: `580.126.20`
- Isaac Lab runtime setup completed.
- Scripted eval completed for seed `42` and 100 steps.
- The bounded Joint-IK path ran end-to-end with no Jacobian indexing error and no unbounded joint-command crash.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T11-24-47Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T11-24-47Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T11-24-47Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T11-07-39Z_isaac-phase2-jointik-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The guarded script deleted the instance by name and id.
- The instance lingered in `DELETING`, so the guarded script kept polling and reissuing delete.
- One late delete-by-id returned `instance with id/name fezvc0vjt not found`, while list output still briefly showed the name in `DELETING`.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "scripted_control_mode": "joint-ik",
  "abs_control_mode": "waypoint",
  "action_dim": 7,
  "deterministic_reset": true,
  "socket_pos_override": [0.22, 0.04, 0.19],
  "joint_ik_step": 0.05,
  "joint_limit_margin": 0.02,
  "initial_lateral": 0.2067292034626007,
  "final_lateral": 0.3312975764274597,
  "best_lateral": 0.2067292034626007,
  "best_lateral_step": 0,
  "initial_axial": 0.9732748866081238,
  "final_axial": 0.9187385439872742,
  "best_axial": 0.9152539372444153,
  "best_axial_step": 98,
  "initial_rot": 0.8291767835617065,
  "final_rot": 0.6629066467285156,
  "best_rot": 0.654979407787323,
  "best_rot_step": 91,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step=0:
  phase=reach
  lateral=0.2067, axial=0.9733, rot=0.8292
  raw joint target=[-0.333, 2.414, -2.474, 4.533, -3.300, 0.840, 6.516]
  clamped joint target=[0.088, -0.024, -0.005, -0.471, -0.183, 3.637, 0.592]

step=91:
  best rot=0.6550, but lateral remains poor and the controller is still in reach phase

step=99:
  phase=reach
  lateral=0.3313, axial=0.9187, rot=0.6629
```

Interpretation:

- The bounded target fix worked mechanically: raw IK targets are still very large, but the commands sent to `JointPositionActionCfg` are clamped and stable.
- The remaining failure is not the previous blow-up; the controller is still not driving the tool tip toward the socket.
- Lateral error worsened from `0.2067` to `0.3313`, axial improved only slightly, and success stayed at `0.0`.
- PPO remains blocked because the scripted gate does not yet demonstrate a usable approach behavior.

Next useful action:

- Do not run another GPU attempt until the controller is changed locally.
- Diagnose the deterministic reset, socket override, tool-tip body offset, and hand-target mapping from the trace.
- Prefer either a reachable socket/waypoint target near the deterministic initial pose or a simpler deterministic joint-space waypoint baseline before returning to cloud validation.

## Attempt 25: Built-in Absolute IK Gate Improves Axial Approach, But Still Fails Lateral/Rotation

Command:

```bash
scripts/run_phase2_absik_gate.sh
```

Code state:

- Commit before run: `889abde Add Abs IK gate and richer scripted trace`
- Added richer trace fields for hand pose, controller action-frame pose, physical peg-tip pose, socket-relative physical tip position, and action-to-physical-tip delta.
- Added `scripts/run_phase2_absik_gate.sh` to compare Isaac Lab's built-in absolute IK action term against the custom standalone Joint-IK pre-controller.

Price selection:

- Live price table selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S option was about `$1.86/hr`.
- L4 remained the correct choice for this short controller diagnostic.

Result:

- Instance was created: `isaac-phase2-absik-l4`, id `3r8vzmme8`.
- The instance reached `RUNNING / COMPLETED / READY`.
- Remote GPU probe succeeded:
  - GPU: `NVIDIA L4`
  - VRAM: `23034 MiB`
  - driver: `580.126.20`
- Isaac Lab runtime setup completed.
- The absolute IK contact play task registered and ran:
  - task: `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
  - observation width: `43`
  - action width: `7`
- Scripted eval completed for seed `42` and 100 steps.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T11-55-39Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T11-55-39Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T11-55-39Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T11-38-57Z_isaac-phase2-absik-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- Initial delete attempts hit Brev API `context deadline exceeded` while the instance was still `RUNNING / COMPLETED / READY`.
- Manual and guarded delete retries by both name and id eventually moved the instance to `DELETING`.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "task": "RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0",
  "scripted_control_mode": "mdp",
  "abs_control_mode": "waypoint",
  "action_dim": 7,
  "deterministic_reset": true,
  "socket_pos_override": [0.22, 0.04, 0.19],
  "initial_lateral": 0.21771036088466644,
  "final_lateral": 0.2411496788263321,
  "best_lateral": 0.08073757588863373,
  "best_lateral_step": 58,
  "initial_axial": 0.3017815947532654,
  "final_axial": 0.015910804271697998,
  "best_axial": 0.004813969135284424,
  "best_axial_step": 95,
  "initial_rot": 2.9826011657714844,
  "final_rot": 2.6274900436401367,
  "best_rot": 2.404057502746582,
  "best_rot_step": 95,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step=0:
  action_pos=[0.1326, -0.1409, 0.5328]
  physical_tip=[0.0637, -0.1185, 0.5254]
  action_to_physical_tip_delta=[-0.0689, 0.0224, -0.0073]
  lateral=0.2177, axial=0.3018, rot=2.9826

step=58:
  best lateral=0.0807
  action_pos=[0.2068, 0.0526, 0.4442]
  physical_tip=[0.1376, 0.0674, 0.4268]
  action_to_physical_tip_delta=[-0.0691, 0.0149, -0.0174]

step=95:
  best axial=0.0048 and best rot=2.4041
  physical_tip_rel_socket_pos=[0.1267, -0.1683, 0.0363]

step=99:
  lateral=0.2411, axial=0.0159, rot=2.6275
  physical_tip_rel_socket_pos=[0.1575, -0.1690, -0.0200]
```

Interpretation:

- Built-in absolute IK is materially better than the custom standalone Joint-IK for this task: axial error reached `0.0048 m`, while the previous bounded Joint-IK gate only reached `0.9153 m`.
- The controller still fails the task because lateral error does not converge; it improves to `0.0807 m` and then worsens to `0.2411 m`.
- Rotation never enters a useful correction phase because the state machine remains in `reach`; the current transition requires much tighter lateral alignment before rotation starts.
- The richer trace exposed a persistent offset between the controller action frame and the physical peg tip, roughly `6-7 cm` in world position during this rollout.
- This suggests the current kinematic peg sync / frame mapping is not reliable enough for PPO yet.

Next useful action:

- Keep PPO blocked.
- Replace the coupled XYZ reach with a staged scripted approach:
  - first align XY while holding current height,
  - then descend to the pre-insertion height,
  - then rotate,
  - then insert.
- Investigate replacing the kinematic `sync_peg_to_hand` event with a more robust fixed attachment/link representation, or make metrics/rewards consistently use the same physical tip frame as the controller until a fixed attachment is implemented.

## Attempt 26: Staged Absolute IK Gate Does Not Improve Lateral Convergence

Command:

```bash
scripts/run_phase2_absik_gate.sh
```

Code state:

- Commit before run: `fb31128 Add staged Abs IK approach diagnostic`
- Default gate args used staged absolute IK:
  - `--deterministic-reset`
  - `--socket-pos 0.22,0.04,0.19`
  - `--staged-approach`
  - `--approach-xy-tol 0.04`
  - `--abs-control-mode waypoint`
  - `--abs-pos-step 0.012`
  - `--abs-rot-step 0.12`
  - `--debug-action-steps 8`

Price selection:

- Live price table selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- The lowest visible L40S option was about `$1.86/hr`.
- L4 remained the correct choice for this short scripted diagnostic.

Result:

- Instance was created: `isaac-phase2-absik-l4`, id `iuiwsq0ty`.
- The instance reached `RUNNING / COMPLETED / READY`.
- Remote GPU probe succeeded:
  - GPU: `NVIDIA L4`
  - VRAM: `23034 MiB`
  - driver: `580.126.20`
- Isaac Lab runtime setup completed.
- The staged absolute IK contact play task registered and ran:
  - task: `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
  - observation width: `43`
  - action width: `7`
- Scripted eval completed for seed `42` and 100 steps.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T12-27-38Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T12-27-38Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T12-27-38Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T12-11-57Z_isaac-phase2-absik-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The wrapper issued guarded delete by both name and id.
- The delete phase timed out while the instance was still visible as `DELETING / COMPLETED / NOT READY`.
- Independent cleanup then reissued:
  - `brev delete isaac-phase2-absik-l4`
  - `brev delete iuiwsq0ty`
- Both delete commands eventually returned `instance with id/name ... not found`.
- Final independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "task": "RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0",
  "scripted_control_mode": "mdp",
  "abs_control_mode": "waypoint",
  "action_dim": 7,
  "deterministic_reset": true,
  "socket_pos_override": [0.22, 0.04, 0.19],
  "staged_approach": true,
  "initial_lateral": 0.21798858046531677,
  "final_lateral": 0.24804161489009857,
  "best_lateral": 0.10084731876850128,
  "best_lateral_step": 52,
  "initial_axial": 0.3016265332698822,
  "final_axial": 0.09232127666473389,
  "best_axial": 0.09232127666473389,
  "best_axial_step": 99,
  "initial_rot": 2.9816055297851562,
  "final_rot": 1.9946519136428833,
  "best_rot": 1.9946519136428833,
  "best_rot_step": 99,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
best controller_lateral_error:
  step=55
  controller_lateral_error=0.0329844
  physical lateral=0.1025
  phase=descend
  xy_ready=True
  position_ready=False
  rotate_ready=False

best physical lateral:
  step=52
  physical lateral=0.1008
  axial=0.1163
  rot=2.4937
  phase=descend

final:
  step=99
  lateral=0.2480
  axial=0.0923
  rot=1.9947
  controller_lateral_error=0.2249
  action_pos=[0.1302, 0.2462, 0.3303]
  physical_tip=[0.0694, 0.2125, 0.3085]
  action_to_physical_tip_delta=[-0.0608, -0.0336, -0.0218]
  physical_tip_rel_socket_pos=[0.1506, -0.1725, 0.1185]
```

Comparison with Attempt 25:

- Attempt 25 non-staged absolute IK:
  - best lateral: `0.0807 m`
  - best axial: `0.0048 m`
  - best rotation: `2.4041 rad`
- Attempt 26 staged absolute IK:
  - best lateral: `0.1008 m`
  - best axial: `0.0923 m`
  - best rotation: `1.9947 rad`

Interpretation:

- The staged approach did not improve the diagnostic; it made lateral and axial convergence worse than the previous non-staged absolute IK gate.
- `xy_ready` became true by the descend phase, but `position_ready` and `rotate_ready` never became true.
- The controller's internal lateral error reached about `3.3 cm`, but the physical peg-tip lateral error never got below about `10.1 cm`.
- This reinforces the deeper diagnosis: the blocker is not mainly reward shaping, PPO, or descending too early. The likely blocker is inconsistency between the controller action frame, the kinematically synced peg, and the physical peg-tip frame used by task metrics.
- PPO remains blocked until the frame/attachment issue is fixed.

Next useful action:

- Stop adding controller schedules and reward terms.
- Fix physical peg attachment/frame consistency before the next GPU gate:
  - Prefer replacing `sync_peg_to_hand` with a fixed-link or fixed-joint-style representation if feasible in the current Isaac Lab task structure.
  - If a fixed attachment is too expensive for the next step, make controller target, reward, termination, and metric computation all use one explicitly documented physical tip frame.
- After that fix, rerun a cheap L4 scripted gate before any PPO training.

## Attempt 27: Tip-to-Root Sync Patch Exposes Wrong Peg-End Sign

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-sync-l4 \
RCA_GATE_TASK=RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0 \
RCA_GATE_COMMAND=scripted_eval \
RCA_SCRIPTED_TRACE_JSON=1 \
RCA_GATE_STEPS=80 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=240 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=1200 \
RCA_GATE_BUILD_STUCK_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=0 \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --socket-pos 0.22,0.04,0.19 --staged-approach --approach-xy-tol 0.04 --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --debug-action-steps 4' \
scripts/run_guarded_phase2_gate.sh
```

Code state:

- Commit before run: `6987229 Align physical peg sync with controller tip frame`
- The sync event computed a controller tip pose first, then derived the peg root with `PEG_ROOT_FROM_TIP_POS=(0, 0, -0.04)`.
- `scripts/scripted_agent.py` logged `action_tip_alignment` to directly measure controller action-frame to physical metric-tip consistency.

Price selection:

- Live price table selected `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.
- L4 remained the correct choice for this short diagnostic.

Result:

- Instance was created: `isaac-phase2-sync-l4`, id `7ht4yfbru`.
- The instance reached `RUNNING / COMPLETED / READY`.
- Remote GPU probe succeeded:
  - GPU: `NVIDIA L4`
  - VRAM: `23034 MiB`
  - driver: `580.126.20`
- Isaac Lab runtime setup completed.
- Scripted eval completed for seed `42` and 80 steps.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T13-11-00Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T13-11-00Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T13-11-00Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T12-54-40Z_isaac-phase2-sync-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- Delete by name and id initially left the instance visible as `DELETING / COMPLETED / NOT READY`.
- The wrapper and independent CLI checks kept reissuing delete by both name and id.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "task": "RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0",
  "scripted_control_mode": "mdp",
  "abs_control_mode": "waypoint",
  "deterministic_reset": true,
  "socket_pos_override": [0.22, 0.04, 0.19],
  "staged_approach": true,
  "steps_requested": 80,
  "initial_action_tip_alignment": 0.07999999076128006,
  "final_action_tip_alignment": 0.08000000566244125,
  "best_action_tip_alignment": 0.07999996095895767,
  "best_action_tip_alignment_step": 14,
  "initial_lateral": 0.18753014504909515,
  "final_lateral": 0.09579933434724808,
  "best_lateral": 0.09579933434724808,
  "best_lateral_step": 79,
  "initial_axial": 0.3541536331176758,
  "final_axial": 0.41987764835357666,
  "best_axial": 0.3541536331176758,
  "best_axial_step": 0,
  "initial_rot": 2.817500114440918,
  "final_rot": 2.8085837364196777,
  "best_rot": 2.8085837364196777,
  "best_rot_step": 79,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Interpretation:

- The run failed the primary pass condition: `best_action_tip_alignment` needed to be `<0.005 m`, but stayed at exactly one peg length, about `0.080 m`.
- This is still useful: a full-length constant offset strongly indicates the metric/controller are using opposite ends of the cylinder.
- Lateral improved from `0.1875 m` to `0.0958 m`, but this is not enough to unblock PPO because the frame alignment invariant is still false.
- The local follow-up fix flips the selected physical tip end:
  - `PEG_TIP_FROM_CENTER_POS` becomes `(0.0, 0.0, -0.5 * PEG_LENGTH_M)`.
  - `PEG_ROOT_FROM_TIP_POS` becomes `(0.0, 0.0, +0.5 * PEG_LENGTH_M)`.
  - `PEG_CENTER_BODY_OFFSET_POS` is updated accordingly for consistency checks.

Next useful action:

- Rerun one more cheap L4 scripted gate after the sign flip.
- Pass/fail is again dominated by `best_action_tip_alignment < 0.005 m`.
- Do not run PPO until this metric passes.

## Attempt 28: Sign Flip Still Fails, Quaternion Convention Mismatch Identified

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-sign-l4 \
RCA_GATE_TASK=RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0 \
RCA_GATE_COMMAND=scripted_eval \
RCA_SCRIPTED_TRACE_JSON=1 \
RCA_GATE_STEPS=40 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=180 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=1200 \
RCA_GATE_BUILD_STUCK_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=0 \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --socket-pos 0.22,0.04,0.19 --staged-approach --approach-xy-tol 0.04 --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --debug-action-steps 4' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- L40S was not used because this was a short diagnostic gate.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T13-40-38Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T13-40-38Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T13-40-38Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T13-25-07Z_isaac-phase2-sign-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance initially remained visible as `DELETING`, so the wrapper reissued delete by name and id.
- Final wrapper check returned `No instances in org NCA-57cf-29515`.
- Two independent post-run checks also returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "steps_requested": 40,
  "initial_action_tip_alignment": 0.08000001311302185,
  "final_action_tip_alignment": 0.07999999076128006,
  "best_action_tip_alignment": 0.07999997586011887,
  "best_action_tip_alignment_step": 9,
  "initial_lateral": 0.402599573135376,
  "final_lateral": 0.24435606598854065,
  "best_lateral": 0.24435606598854065,
  "best_lateral_step": 39,
  "initial_rot": 2.8071746826171875,
  "final_rot": 1.2628461122512817,
  "best_rot": 1.187615156173706,
  "final_success_rate": 0.0
}
```

Interpretation:

- The sign flip did not change the fixed one-peg-length alignment error.
- This rules out simple upper-end/lower-end selection as the root cause.
- The stronger diagnosis is that the remote Isaac Lab develop / Isaac Sim 6 runtime uses `XYZW` hard-coded quaternions, while this repo still had legacy `WXYZ` constants and helper functions.
- The identity quaternion bug is especially severe: `(1, 0, 0, 0)` is identity in `WXYZ`, but not identity in `XYZW`.

Local follow-up fix:

- Migrated task constants to `XYZW`.
- Added `IDENTITY_QUAT = (0, 0, 0, 1)`.
- Migrated scripted-agent quaternion math to `XYZW`.
- Migrated force-frame inverse rotation helper to `XYZW`.

Next useful action:

- Run exactly one more cheap L4 scripted gate after committing this migration.
- Primary pass condition remains `best_action_tip_alignment < 0.005 m`.
- No PPO until this invariant passes.

## Attempt 29: XYZW Migration Validates Frame Alignment

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-xyzw-l4 \
RCA_GATE_TASK=RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0 \
RCA_GATE_COMMAND=scripted_eval \
RCA_SCRIPTED_TRACE_JSON=1 \
RCA_GATE_STEPS=40 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=180 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=1200 \
RCA_GATE_BUILD_STUCK_SECONDS=300 \
RCA_SCRIPTED_EVAL_RETRIES=0 \
RCA_GATE_EXTRA_AGENT_ARGS='--deterministic-reset --socket-pos 0.22,0.04,0.19 --staged-approach --approach-xy-tol 0.04 --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --debug-action-steps 4' \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T14-13-20Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T14-13-20Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T14-13-20Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T13-58-04Z_isaac-phase2-xyzw-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance remained visible in `DELETING` for several minutes, so the wrapper kept reissuing delete by name and id.
- Final wrapper check returned `No instances in org NCA-57cf-29515`.
- Two independent post-run checks also returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "steps_requested": 40,
  "initial_action_tip_alignment": 0.0,
  "final_action_tip_alignment": 0.0,
  "best_action_tip_alignment": 0.0,
  "best_action_tip_alignment_step": 0,
  "initial_lateral": 0.19297145307064056,
  "final_lateral": 0.10373983532190323,
  "best_lateral": 0.10373983532190323,
  "best_lateral_step": 39,
  "initial_axial": 0.40741926431655884,
  "final_axial": 0.4401460886001587,
  "initial_rot": 2.8727784156799316,
  "final_rot": 2.858823537826538,
  "best_rot": 2.858823537826538,
  "best_rot_step": 39,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Interpretation:

- Primary pass condition succeeded: `best_action_tip_alignment=0.0 < 0.005 m`.
- The physical peg tip, action frame, and scripted trace metric now agree.
- This validates the `XYZW` migration and closes the quaternion/frame bug.
- The task still does not solve insertion. The scripted controller only improves lateral error from `0.193 m` to `0.104 m`; it never reaches `approach_xy_tol=0.04`, so insertion never starts.

Next useful action:

- Stop spending GPU on frame debugging.
- Locally redesign the scripted controller target sequence for the aligned frame.
- The next remote gate should test reachability/staging, not PPO.

## Attempt 30: Scripted Reachability Sweep Finds a Viable XY Gate Setting

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-reach-sweep-l4 \
RCA_GATE_TASK=RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0 \
RCA_GATE_COMMAND=scripted_reach_sweep \
RCA_GATE_NUM_ENVS=1 \
RCA_GATE_EVAL_TIMEOUT_SECONDS=300 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=1200 \
RCA_GATE_BUILD_STUCK_SECONDS=300 \
scripts/run_guarded_phase2_gate.sh
```

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.
- L4 remained the right choice for a short diagnostic sweep.

Artifacts:

- Sweep root: `artifacts/evaluations/scripted_reach_sweep/2026-05-15T14-54-08Z/`
- Gate log: `artifacts/gpu_gate/2026-05-15T14-37-33Z_isaac-phase2-reach-sweep-l4/gate.log`
- Gate metadata: `artifacts/gpu_gate/2026-05-15T14-37-33Z_isaac-phase2-reach-sweep-l4/gate_metadata.env`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance remained visible as `STOPPED / COMPLETED / NOT READY` after initial delete.
- The guarded script and manual checks reissued delete by both name and id.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Sweep metrics:

```json
{
  "waypoint_40_step012": {
    "steps_requested": 40,
    "initial_lateral": 0.19297145307064056,
    "final_lateral": 0.10373983532190323,
    "best_lateral": 0.10373983532190323,
    "best_lateral_step": 39,
    "final_axial": 0.4401460886001587,
    "best_rot": 2.858823537826538,
    "final_success_rate": 0.0
  },
  "target_40": {
    "steps_requested": 40,
    "initial_lateral": 0.18083271384239197,
    "final_lateral": 0.3291814625263214,
    "best_lateral": 0.02998097613453865,
    "best_lateral_step": 16,
    "final_axial": 0.2104201316833496,
    "best_rot": 1.9280742406845093,
    "final_success_rate": 0.0
  },
  "waypoint_80_step030": {
    "steps_requested": 80,
    "initial_lateral": 0.19102078676223755,
    "final_lateral": 0.030349547043442726,
    "best_lateral": 0.012698001228272915,
    "best_lateral_step": 37,
    "final_axial": 0.3308665156364441,
    "best_rot": 2.612150192260742,
    "final_success_rate": 0.0
  }
}
```

Interpretation:

- The frame alignment bug remains fixed: `action_tip_alignment=0.0` for all sweep cases.
- The 40-step small-waypoint controller is too slow and never enters the `4 cm` approach corridor.
- Direct target mode reaches the approach corridor transiently (`best_lateral=0.0300 m`) but overshoots badly by the end (`final_lateral=0.3292 m`).
- The best setting from this sweep is `waypoint_80_step030`: it reaches `best_lateral=0.0127 m` and finishes inside the approach corridor at `final_lateral=0.0303 m`.
- This means the XY reach gate is now solvable with the aligned frame. The remaining blocker is staged transition after XY alignment: axial and rotation are still not converging enough for insertion success.

Non-task issue found:

- The remote sweep itself completed and pulled artifacts successfully.
- The wrapper returned status `127` because the final tabular summary used `python3` inside the Isaac container, where only `/isaac-sim/python.sh` is reliable.
- Follow-up local fix changed the summary command to `/isaac-sim/python.sh`.

Next useful action:

- Promote the `waypoint_80_step030` parameters into the default deterministic scripted gate.
- Add or tune a post-XY stage: hold XY, lower axial target, then rotate, then insert.
- Run one more cheap L4 scripted gate only after local syntax checks pass.
- PPO remains blocked until a scripted rollout reaches the XY gate and makes nonzero axial/rotation progress in the same rollout.

## Attempt 31: Tuned Staged Abs IK Solves XY But Stalls Before Descent/Rotation

Command:

```bash
RCA_GATE_PROFILE=cheap scripts/run_phase2_absik_gate.sh
```

Code state:

- Commit before run: `2fb5dba Tune Abs IK gate after reach sweep`
- Default Abs IK gate parameters:
  - `--deterministic-reset`
  - `--socket-pos 0.22,0.04,0.19`
  - `--staged-approach`
  - `--approach-xy-tol 0.04`
  - `--abs-control-mode waypoint`
  - `--abs-pos-step 0.030`
  - `--abs-rot-step 0.12`
  - `--debug-action-steps 4`
  - `steps=180`

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T15-25-13Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T15-25-13Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T15-25-13Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T15-08-42Z_isaac-phase2-absik-l4/gate.log`

Cleanup:

- Artifacts were pulled locally before shutdown.
- The instance stayed visible as `DELETING / COMPLETED / NOT READY` for several polling cycles.
- The guarded script reissued delete by both name and id.
- Delete-by-id eventually returned `instance with id/name fy11rd5jk not found`, and the list then converged to empty.
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `null`

Metrics:

```json
{
  "steps_requested": 180,
  "initial_action_tip_alignment": 0.0,
  "final_action_tip_alignment": 1.5359765015432458e-08,
  "best_action_tip_alignment": 0.0,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.0018624793738126755,
  "best_lateral": 0.0018624793738126755,
  "best_lateral_step": 179,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.23933672904968262,
  "best_axial": 0.23933672904968262,
  "best_axial_step": 179,
  "initial_rot": 2.87626576423645,
  "final_rot": 2.492908000946045,
  "best_rot": 2.4786386489868164,
  "best_rot_step": 135,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step=50:
  phase=descend
  lateral=0.0224
  axial=0.4190
  rot=2.7913
  action_pos.z=0.6107
  approach_pos.z=0.2400

step=125:
  phase=descend
  lateral=0.0069
  axial=0.2446
  rot=2.4802
  action_pos.z=0.4350
  approach_pos.z=0.2400

step=179:
  phase=descend
  lateral=0.0019
  axial=0.2393
  rot=2.4929
  action_pos.z=0.4293
  command_pos.z=0.3993
```

Interpretation:

- This is the best deterministic XY result so far: lateral reaches `1.9 mm`, and action-to-physical-tip alignment remains effectively zero.
- The blocker moved from frame alignment / XY reach to post-XY progress.
- The current staged order is `XY -> descend -> rotate -> insert`. It gets excellent XY alignment but stalls around `action_pos.z=0.429 m`, far above the approach pose `z=0.240 m`.
- Because `position_ready` never becomes true, rotation and insertion never start.
- The likely issue is that keeping the original high-error orientation during descent makes the absolute IK controller unable to continue lowering the tool.

Follow-up fix:

- Added `--rotate-before-descend` to `scripts/scripted_agent.py`.
- In staged mode, this changes the sequence to `XY -> rotate at current height -> descend -> insert`.
- Updated `scripts/run_phase2_absik_gate.sh` defaults to:
  - `--rotate-before-descend`
  - `steps=220`
  - eval timeout `360s`
- Commit: `ba0b883 Add rotate-before-descend scripted stage`

Next useful action:

- Run one more cheap L4 Abs IK gate with `--rotate-before-descend`.
- Pass condition: rotation should drop before descent, and the rollout should either reduce axial below the previous `0.239 m` floor or enter `position_ready/insert_ready`.
- PPO remains blocked.

## Attempt 32: Rotate-Before-Descend Gate Blocked By Brev Startup/Delete State

Command:

```bash
RCA_GATE_PROFILE=cheap scripts/run_phase2_absik_gate.sh
```

Intended test:

- Validate the new `--rotate-before-descend` staged scripted controller.
- Keep the cheap profile and explicitly use `g2-standard-4:nvidia-l4:1`.
- Run only the scripted Abs IK gate, not PPO.

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.

Brev instance:

- Name: `isaac-phase2-absik-l4`
- ID: `9x25awk9s`
- Type: `g2-standard-4:nvidia-l4:1`
- GPU: `L4`

Outcome:

- The instance was created but remained stuck in `STARTING / PENDING / NOT READY`.
- The gate was aborted before any Isaac Lab runtime install, scripted evaluation, or PPO work.
- No Phase 2 task metrics were produced by this attempt.

Cleanup issue:

- `brev delete isaac-phase2-absik-l4` and `brev delete 9x25awk9s` both returned success.
- The instance then remained visible as `STOPPED / NOT READY / UNHEALTHY`.
- `brev stop isaac-phase2-absik-l4` returned `rpc error: code = Internal desc = context deadline exceeded`.
- Evidence and support draft were saved locally under `artifacts/brev_incidents/2026-05-15_absik_l4_delete_stuck/`.

Brev CLI mitigation:

- Local Brev CLI was upgraded from `v0.6.322` to `v0.6.324` without sudo by replacing `/Users/Shenghan/bin/brev`.
- The old binary was backed up under `/Users/Shenghan/bin/.brev-backups/`.
- The new CLI changed JSON output from list/null to a dict shape such as `{ "workspaces": null }`.
- `scripts/run_guarded_phase2_gate.sh` was updated to treat the org as empty only when both conditions hold:
  - plain `brev ls instances --all` contains `No instances in org`
  - JSON output is empty by either old or new CLI format

Final cleanup verification:

- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- This attempt does not change the robotics result. The latest valid task result remains Attempt 31.
- The project-side next action is still to run the rotate-before-descend Abs IK scripted gate.
- The infrastructure-side requirement is stricter now: do not create a new GPU unless the guarded script sees both plain and JSON empty-org checks pass.
- PPO remains blocked until the scripted gate produces coherent XY, axial, and orientation progress in one rollout.

## Attempt 33: Rotate-Before-Descend Gate Runs, Improves Axial But Stalls In Rotate Phase

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-absik-l4b \
RCA_GATE_READY_TIMEOUT_SECONDS=480 \
RCA_GATE_BUILD_STUCK_SECONDS=240 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_absik_gate.sh
```

Code state:

- Commit before run: `2f84b6b Harden Brev empty-org guard`
- Scripted gate parameters:
  - `--deterministic-reset`
  - `--socket-pos 0.22,0.04,0.19`
  - `--staged-approach`
  - `--rotate-before-descend`
  - `--approach-xy-tol 0.04`
  - `--abs-control-mode waypoint`
  - `--abs-pos-step 0.030`
  - `--abs-rot-step 0.12`
  - `--debug-action-steps 4`
  - `steps=220`

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.
- This was the right choice for a short scripted gate because the workload does not need 48GB VRAM.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T16-47-54Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T16-47-54Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T16-47-54Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T16-31-59Z_isaac-phase2-absik-l4b/gate.log`

Cleanup:

- The instance reached `RUNNING / COMPLETED / READY` after a long `BUILDING` phase.
- Isaac Lab runtime installed and the scripted eval completed.
- Artifacts were pulled locally before shutdown.
- During cleanup, the Brev control plane briefly showed inconsistent states (`DELETING`, then `DEPLOYING`, while delete-by-name returned `not found`).
- Final guarded and independent checks returned:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Metrics:

```json
{
  "steps_requested": 220,
  "rotate_before_descend": true,
  "initial_action_tip_alignment": 0.0,
  "final_action_tip_alignment": 3.003425064207477e-08,
  "best_action_tip_alignment": 0.0,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.19516903162002563,
  "best_lateral": 0.002564318710938096,
  "best_lateral_step": 180,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.19286027550697327,
  "best_axial": 0.19286027550697327,
  "best_axial_step": 219,
  "initial_rot": 2.87626576423645,
  "final_rot": 2.5631189346313477,
  "best_rot": 2.3980886936187744,
  "best_rot_step": 209,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step=50:
  phase=rotate
  lateral=0.0199
  axial=0.4290
  rot=3.1313
  xy_state=True
  rotate_state=True
  insert_mask=False

step=125:
  phase=rotate
  lateral=0.0052
  axial=0.2942
  rot=3.1360
  xy_state=True
  rotate_state=True
  insert_mask=False

step=180:
  best_lateral=0.0026

step=209:
  best_rot=2.3981
  lateral=0.2466
  axial=0.1955

step=219:
  phase=rotate
  lateral=0.1952
  axial=0.1929
  rot=2.5631
  insert_mask=False
```

Interpretation:

- This is not a success run; `success_rate=0.0`.
- The good result is axial progress: best/final axial improved from Attempt 31's `0.2393 m` to `0.1929 m`.
- XY alignment is still solvable: best lateral is `2.6 mm`.
- The new blocker is the rotate phase. The rollout enters `phase=rotate`, but orientation error remains very high (`2.4-3.1 rad`), and the policy never reaches `position_ready` or `insert_mask`.
- The final lateral jump suggests the controller becomes unstable while trying to satisfy the high-error orientation target.
- PPO is still blocked. The scripted gate can now solve XY and improve axial, but it cannot yet produce coherent XY + axial + orientation progress in one rollout.

Next useful local fix:

- Do not run another GPU gate yet.
- Inspect the rotate-stage target orientation and the measured `tip_to_socket_orientation` convention.
- Add a local/offline trace summary that compares commanded quaternion, socket quaternion, action quaternion, and measured tip-to-socket quaternion around steps `50`, `125`, `180`, `209`, and `219`.
- The next scripted controller change should reduce the rotate-phase orientation error without sacrificing the `2-5 mm` lateral alignment. Only then run another cheap L4 gate.

## Attempt 34: Target-Quaternion Gate Fails During Runtime Registration

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-rot-target-l4 \
RCA_GATE_READY_TIMEOUT_SECONDS=480 \
RCA_GATE_BUILD_STUCK_SECONDS=240 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_absik_gate.sh
```

Code state:

- Commit before run: `9a8ab37 Use target quaternion during rotate gate`
- Scripted gate added `--rotate-control-mode target`.
- Selected instance type: `g2-standard-4:nvidia-l4:1` at about `$0.85/hr`.

Result:

- The instance reached `RUNNING / COMPLETED / READY`.
- Runtime install completed, but the environment registration check failed before scripted eval.
- Error:

```text
TypeError: 'module' object is not callable
```

- Failure path:

```text
peg_in_hole_env_cfg.py
  from isaaclab_physx.physics import PhysxCfg
isaaclab_physx/physics/physx_manager_cfg.py
  @configclass
```

Interpretation:

- This was an Isaac Lab 5.2.1 runtime compatibility issue, not a robotics result.
- The task configuration imported `PhysxCfg` only to set `bounce_threshold_velocity=0.2`; that setting was non-essential for the scripted gate.
- Fix: remove the direct `PhysxCfg` import and the optional `self.sim.physics = PhysxCfg(...)` override.

Cleanup verification:

- Artifacts were pulled before shutdown, but no eval JSON was produced.
- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Follow-up commit:

- `8025ceb Avoid IsaacLab PhysxCfg import in peg env`

## Attempt 35: Target Quaternion Reduces Rotation Error But Breaks Lateral Hold

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-rot-target-l4c \
RCA_GATE_READY_TIMEOUT_SECONDS=480 \
RCA_GATE_BUILD_STUCK_SECONDS=240 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_absik_gate.sh
```

Code state:

- Commit before run: `8025ceb Avoid IsaacLab PhysxCfg import in peg env`
- Scripted gate parameters included:
  - `--rotate-before-descend`
  - `--rotate-control-mode target`
  - `--abs-control-mode waypoint`
  - `--abs-pos-step 0.030`
  - `--abs-rot-step 0.12`

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.
- L4 remained the right choice for this short scripted gate.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T17-39-03Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T17-39-03Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T17-39-03Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T17-24-15Z_isaac-phase2-rot-target-l4c/gate.log`

Cleanup verification:

- Artifacts were pulled locally before shutdown.
- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Metrics:

```json
{
  "steps_requested": 220,
  "rotate_before_descend": true,
  "initial_action_tip_alignment": 0.0,
  "final_action_tip_alignment": 3.003425064207477e-08,
  "best_action_tip_alignment": 0.0,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.2338368445634842,
  "best_lateral": 0.039388321340084076,
  "best_lateral_step": 30,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.2880937159061432,
  "best_axial": 0.19548767805099487,
  "best_axial_step": 209,
  "initial_rot": 2.87626576423645,
  "final_rot": 1.3000329732894897,
  "best_rot": 0.834111213684082,
  "best_rot_step": 66,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     act_cmd  act_target  cmd_target
30    rotate  0.0394  0.4501  2.7621  2.8771   2.8771      0.0000
50    rotate  0.1340  0.5767  1.5501  1.5815   1.5815      0.0000
66    rotate  0.3708  0.5812  0.8341  0.8356   0.8356      0.0000
125   rotate  0.3922  0.6290  1.1396  1.1408   1.1408      0.0000
209   rotate  0.2466  0.1955  2.3981  1.0582   1.0582      0.0000
219   rotate  0.2338  0.2881  1.3000  1.3745   1.3745      0.0000
```

Interpretation:

- This is not a success run; `success_rate=0.0`.
- The target-quaternion change fixed the previous orientation bottleneck directionally:
  - Attempt 33 best rotation error: `2.3981 rad`
  - Attempt 35 best rotation error: `0.8341 rad`
- The new failure mode is position drift during rotation:
  - best lateral only reached `3.94 cm`, versus Attempt 33's `2.6 mm`
  - lateral drifted to `37-41 cm` around the best-rotation region
- `cmd_target=0.0000` confirms the commanded quaternion is now the target quaternion during rotate, but the end effector cannot hold the approach position while rotating.

Next useful local fix:

- Do not run another GPU gate yet.
- Modify rotate-stage command generation so rotation uses the target quaternion while position is held at the socket approach pose, not at the moving current-Z waypoint.
- Add trace fields or summary rows that expose `command_pos_w`, `target_action_pos_w`, and `approach_pos_w` at rotate steps.
- The next gate should pass only if lateral stays below `4 cm` while rotation improves below `1 rad`; otherwise switch from MDP abs IK to explicit joint-IK for the rotate stage.

## Attempt 36: rotate-stage position hold

Date: 2026-05-15

Local commit:

- `68371ca Lock rotate hold pose in scripted gate`

Goal:

- Fix the Attempt 35 regression where target-quaternion rotation improved orientation but allowed large lateral drift.
- Lock the rotate-stage hold position at the socket approach pose when entering rotate mode.
- Add trace fields for the held command position so lateral drift can be diagnosed directly.

Remote run:

- Run id: `2026-05-15T17-50-48Z`
- Instance: `isaac-phase2-rotate-hold-l4`
- Machine: `g2-standard-4:nvidia-l4:1`

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T18-07-19Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T18-07-19Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T18-07-19Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T17-50-48Z_isaac-phase2-rotate-hold-l4/gate.log`

Cleanup verification:

- Artifacts were pulled locally before shutdown.
- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Metrics:

```json
{
  "steps_requested": 220,
  "rotate_before_descend": true,
  "rotate_control_mode": "target",
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.2278691530227661,
  "best_lateral": 0.0002867463044822216,
  "best_lateral_step": 162,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.3234337568283081,
  "best_axial": 0.19548767805099487,
  "best_axial_step": 209,
  "initial_rot": 2.87626576423645,
  "final_rot": 1.3620718717575073,
  "best_rot": 0.21948815882205963,
  "best_rot_step": 108,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     act_cmd  act_target  cmd_target  cmd_target_pos  cmd_hold_pos
30    rotate  0.0394  0.4501  2.7621  2.8771   2.8771      0.0000      0.4486          0.0099
75    rotate  0.3551  0.4452  0.5287  0.5406   0.5406      0.0000      0.5513          0.3207
108   rotate  0.1983  0.4287  0.2195  0.2519   0.2519      0.0000      0.4808          0.1734
150   rotate  0.0090  0.3771  0.2413  0.2284   0.1200      0.3483      0.3496          0.0989
162   rotate  0.0003  0.3620  0.2411  0.2290   0.1200      0.3489      0.3344          0.1141
209   rotate  0.2466  0.1955  2.3981  0.2516   0.2516      0.0000      0.3320          0.1165
219   rotate  0.2279  0.3234  1.3621  1.4236   1.4236      0.0000      0.4003          0.2197
```

Interpretation:

- This is not a success run; `success_rate=0.0`.
- The rotate hold fix worked directionally:
  - Attempt 35 best lateral: `3.94 cm`
  - Attempt 36 best lateral: `0.29 mm`
  - Attempt 35 best rotation: `0.834 rad`
  - Attempt 36 best rotation: `0.219 rad`
- The new problem is that once orientation becomes ready, the controller no longer consistently keeps commanding the target quaternion through descent.
- At step 209, the axial metric improves, but rotation spikes back to `2.398 rad`, which prevents success.

Next useful local fix:

- Keep target-quaternion override active through rotate descent until insertion or polish mode, not only while orientation is not ready.
- Do not change the environment or reward yet; this is still a scripted-control state-machine bug.

## Attempt 37: hold target quaternion through rotate descent

Date: 2026-05-15

Local commit:

- `12f503e Hold target quaternion through rotate descent`

Goal:

- Preserve the target quaternion after `orientation_ready=True` while the scripted controller descends toward insertion.
- Test whether the contact gate can reach the insertion success condition after fixing the orientation drop-out seen in Attempt 36.

Remote run:

- Run id: `2026-05-15T18-15-12Z`
- Instance: `isaac-phase2-quat-hold-l4`
- Machine: `g2-standard-4:nvidia-l4:1`

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was about `$0.85/hr`.
- Lowest visible L40S option was about `$1.86/hr`.
- L4 remained the right choice for this short scripted gate.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T18-31-28Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T18-31-28Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T18-31-28Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T18-15-12Z_isaac-phase2-quat-hold-l4/gate.log`

Cleanup verification:

- Artifacts were pulled locally before shutdown.
- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`
- During cleanup, Brev briefly reported the target instance as `DELETING` and then `DEPLOYING` before the final empty-org confirmation. The guarded cleanup loop and a separate manual CLI check both confirmed the organization ended empty.

Metrics:

```json
{
  "steps_requested": 220,
  "rotate_before_descend": true,
  "rotate_control_mode": "target",
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.2278691530227661,
  "best_lateral": 0.0005068883765488863,
  "best_lateral_step": 165,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.3234337568283081,
  "best_axial": 0.03698286414146423,
  "best_axial_step": 208,
  "initial_rot": 2.87626576423645,
  "final_rot": 1.3620718717575073,
  "best_rot": 0.004081662744283676,
  "best_rot_step": 119,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     act_cmd  act_target  cmd_target  cmd_target_pos  insert
100   rotate  0.2293  0.4375  0.0991  0.1137   0.1137      0.0000      0.4572          0
119   rotate  0.1102  0.3567  0.0041  0.0049   0.0049      0.0000      0.3418          0
150   rotate  0.0027  0.2275  0.0186  0.0186   0.0186      0.0000      0.2016          0
165   rotate  0.0005  0.1665  0.0207  0.0205   0.0205      0.0000      0.1406          0
175   rotate  0.0006  0.1259  0.0215  0.0215   0.0215      0.0000      0.0999          0
200   insert  0.0058  0.0382  0.0511  0.0398   0.0398      0.0297      0.0083          1
208   insert  0.0050  0.0370  0.1739  0.1539   0.1200      0.2613      0.0071          1
219   rotate  0.2279  0.3234  1.3621  1.4236   1.4236      0.0000      0.4003          0
```

Interpretation:

- This is not a success run; `success_rate=0.0`.
- The target-quaternion hold fix worked:
  - Attempt 36 best rotation: `0.219 rad`
  - Attempt 37 best rotation: `0.004 rad`
  - Attempt 36 best axial: `19.5 cm`
  - Attempt 37 best axial: `3.7 cm`
- The scripted controller now reaches a near-solved pre-insertion state:
  - lateral around `5-6 mm`
  - axial around `37-38 mm`
  - rotation around `0.05-0.17 rad`
  - `insert_ready=1` at steps 200 and 208
- The remaining failure is at the contact/insert transition:
  - success is still not triggered before the controller loses the near-insertion state
  - after step 208, the system falls back to rotate mode and the pose jumps away
- This means the next useful work is not more rotate alignment. The rotate gate is effectively solved for this scripted baseline.

Next useful local fix:

- Inspect the insertion success threshold and the insert-stage transition logic.
- Determine whether the physical socket collision is blocking before the configured success depth, or whether the success condition is too strict relative to the current asset dimensions.
- Add trace fields for contact force magnitude and the exact success-term components around steps 190-210.
- Keep the next GPU run short and targeted: only verify the insert transition after local instrumentation, not a full new exploration run.

## Attempt 38: strict insert gate and contact diagnostics

Date: 2026-05-15

Local commit:

- `a2ab901 Tighten insert gate diagnostics`

Goal:

- Separate "approach gate" from "insert gate" so the controller does not start insertion with a lateral error that exceeds the physical guide clearance.
- Add success-component and contact-force trace fields to determine whether the remaining failure is thresholding, contact blocking, or state-machine oscillation.

Remote run:

- Run id: `2026-05-15T18-44-59Z`
- Instance: `isaac-phase2-insert-gate-l4`
- Machine: `g2-standard-4:nvidia-l4:1`

Price selection:

- Selected `g2-standard-4:nvidia-l4:1`.
- Live L4 price was `$0.85/hr`.
- Lowest visible L40S option was `$1.86/hr`.
- L4 remained the right choice for this short scripted gate.

Command changes:

- `--insert-xy-tol 0.0015`
- `--insert-rot-tol 0.12`
- `--insert-pos-step 0.010`
- `--insert-rot-step 0.06`
- `--steps 260`

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T19-01-27Z/seed_42.json`
- Scripted eval trace: `artifacts/evaluations/scripted/2026-05-15T19-01-27Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T19-01-27Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T18-44-59Z_isaac-phase2-insert-gate-l4/gate.log`

Cleanup verification:

- Artifacts were pulled locally before shutdown.
- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Metrics:

```json
{
  "steps_requested": 260,
  "insert_xy_tolerance": 0.0015,
  "insert_rot_tolerance": 0.12,
  "insert_pos_step": 0.01,
  "insert_rot_step": 0.06,
  "socket_guide_clearance": 0.0015,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.1590428203344345,
  "best_lateral": 0.0005068883765488863,
  "best_lateral_step": 165,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.36730825901031494,
  "best_axial": 0.04435622692108154,
  "best_axial_step": 229,
  "initial_rot": 2.87626576423645,
  "final_rot": 0.31706488132476807,
  "best_rot": 0.004081662744283676,
  "best_rot_step": 119,
  "max_contact_force_magnitude": 28.8151798248291,
  "max_contact_force_magnitude_step": 62,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     cmd_target_pos  insert_xy  succ_xy  succ_z  succ_rot  contact
165   rotate  0.0005  0.1665  0.0207  0.1406          1          1        0       1         4.7125
175   rotate  0.0006  0.1259  0.0215  0.0999          1          1        0       1         4.7161
200   rotate  0.0015  0.0567  0.0288  0.0500          0          1        0       1         4.2086
220   insert  0.0018  0.0465  0.0412  0.0374          1          1        0       1         4.1512
225   rotate  0.0012  0.0465  0.0391  0.0500          0          1        0       1         3.1774
229   insert  0.0020  0.0444  0.0507  0.0353          1          1        0       1         4.0715
231   insert  0.2466  0.1955  2.3981  0.0353          1          0        0       0         4.0304
240   rotate  0.2331  0.3190  1.4236  0.3972          0          0        0       0         3.9135
```

Interpretation:

- This is not a success run; `success_rate=0.0`.
- The stricter insert gate did its job: insertion no longer starts at `5-6 mm` lateral error.
- The new trace exposes a state-machine bug:
  - `insert_mask` toggles on and off between steps `220-230`.
  - When `insert_mask=0`, the command target returns to the approach pose (`cmd_target_pos ~= 0.0500`).
  - When `insert_mask=1`, the command target moves downward toward insertion (`cmd_target_pos ~= 0.035-0.037`).
  - This produces a target flip-flop just above the socket instead of a stable final descent.
- The contact force is already nonzero around the guide, so the flip-flop happens under contact, which explains the large jump at step `231`.

Local fix applied after this run:

- Added a latched `insert_state` to `scripts/scripted_agent.py`.
- Once the current pose satisfies the insert gate, the controller stays in insertion mode instead of returning to rotate/approach every other step.
- Added abort hysteresis:
  - `--insert-abort-xy-tol`
  - `--insert-abort-rot-tol`
- Updated `scripts/summarize_scripted_trace.py` to show `insert_state`, `insert_entry`, and `insert_aborted`.
- Updated `scripts/run_phase2_absik_gate.sh` default args to include `--insert-abort-xy-tol 0.04 --insert-abort-rot-tol 0.35`.

Next useful verification:

- Run one more short L4 gate only after committing the latch fix.
- Pass condition:
  - `insert_state` should remain true across the 220-230 descent region.
  - `cmd_target_pos` should decrease monotonically instead of toggling between `0.0500` and `0.035-0.037`.
  - If the pose still jumps, the remaining blocker is physical/contact instability or absolute IK behavior, not the high-level state machine.

## Attempt 39: latch verification aborted before eval

Date: 2026-05-15

Local commit:

- `47487cc Latch scripted insert state`

Goal:

- Verify the new latched `insert_state` behavior from Attempt 38.

Remote run:

- Run id: `2026-05-15T19-11-03Z`
- Instance: `isaac-phase2-insert-latch-l4`
- Machine: `g2-standard-4:nvidia-l4:1`

Result:

- No scripted eval was run.
- The Brev instance stayed in `RUNNING / BUILDING / NOT READY` for more than the guarded `BUILD_STUCK=240s` threshold.
- The guarded script aborted before remote runtime setup, then deleted the instance.

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-15T19-11-03Z_isaac-phase2-insert-latch-l4/gate.log`
- No new `artifacts/evaluations/scripted/.../seed_42.json` was produced.

Cleanup verification:

- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- This attempt does not validate or invalidate the latch fix.
- It is a Brev bootstrap/ready failure, not a robotics-code failure.
- Do not count it as an experiment result when comparing controller behavior.

## Attempt 40: latch verification retry failed during Brev create

Date: 2026-05-15

Goal:

- Retry the Attempt 39 latch verification with the same guarded create/delete flow.
- Keep cost low by comparing live instance prices before launch.

Remote run:

- Run id: `2026-05-15T19-27-55Z`
- Instance: `isaac-phase2-insert-latch-retry-l4`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Lowest observed L40S price in the same search: `$1.86/hr`

Result:

- No scripted eval was run.
- Brev failed during workspace creation before an instance became ready.
- The CLI/API returned:

```text
Post "https://brevapi.us-west-2-prod.control-plane.brev.dev/api/organizations/.../workspaces?...": unexpected EOF
Warning: Only created 0/1 instances
could only create 0/1 instances
```

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-15T19-27-55Z_isaac-phase2-insert-latch-retry-l4/gate.log`
- Metadata: `artifacts/gpu_gate/2026-05-15T19-27-55Z_isaac-phase2-insert-latch-retry-l4/gate_metadata.env`
- Price snapshots:
  - `artifacts/gpu_gate/2026-05-15T19-27-55Z_isaac-phase2-insert-latch-retry-l4/brev_search_24gb.txt`
  - `artifacts/gpu_gate/2026-05-15T19-27-55Z_isaac-phase2-insert-latch-retry-l4/brev_search_32gb.txt`
  - `artifacts/gpu_gate/2026-05-15T19-27-55Z_isaac-phase2-insert-latch-retry-l4/brev_search_40gb.txt`

Cleanup verification:

- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- This attempt does not validate or invalidate the latched insert-state fix.
- It is a Brev workspace-create/API failure, not a robotics-code failure.
- The guarded script still performed cleanup and the org was confirmed empty through both text and JSON listing.

## Attempt 41: latch verified, abort hysteresis too tight

Date: 2026-05-15

Local base commit:

- `570be03 Record Brev create failure on latch retry`

Goal:

- Verify whether the latched insert-state fix from Attempt 38 removes the insert/rotate target flip-flop.
- Keep the run cheap by using the live price table before creation.

Remote run:

- Run id: `2026-05-15T19-31-42Z`
- Instance: `isaac-phase2-insert-latch-retry2-l4`
- Instance id: `4avspx131`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
- Steps: `260`
- Seed: `42`

Result:

- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The latch fix changed the failure mode:
  - `insert_state` stayed true from step `200` through step `226`.
  - The old rapid insert/rotate flip-flop from Attempt 38 is no longer the primary issue.
  - At step `226`, lateral error reached `0.04145 m`, slightly above the configured `--insert-abort-xy-tol 0.04`.
  - Step `227` set `insert_aborted=true`, returned to rotate mode, and the pose jumped at step `231`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-15T19-46-45Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-15T19-46-45Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-15T19-46-45Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-15T19-31-42Z_isaac-phase2-insert-latch-retry2-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 260,
  "insert_xy_tolerance": 0.0015,
  "insert_rot_tolerance": 0.12,
  "insert_abort_xy_tolerance": 0.04,
  "insert_abort_rot_tolerance": 0.35,
  "insert_pos_step": 0.01,
  "insert_rot_step": 0.06,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.1590428203344345,
  "best_lateral": 0.0005068883765488863,
  "best_lateral_step": 165,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.36730825901031494,
  "best_axial": 0.04665598273277283,
  "best_axial_step": 210,
  "initial_rot": 2.87626576423645,
  "final_rot": 0.31706488132476807,
  "best_rot": 0.004081662744283676,
  "best_rot_step": 119,
  "max_contact_force_magnitude": 28.8151798248291,
  "max_contact_force_magnitude_step": 62,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     insert_state  insert_aborted  succ_xy  succ_z  succ_rot  contact
200   insert  0.0019  0.0563  0.0322  1             0               1        0       1         4.3140
210   insert  0.0086  0.0467  0.0818  1             0               0        0       1         3.6819
220   insert  0.0284  0.0513  0.1413  1             0               0        0       1         3.7295
226   insert  0.0415  0.0561  0.1864  1             0               0        0       0         3.8363
227   rotate  0.0379  0.0570  0.1705  0             1               0        0       1         4.2520
231   rotate  0.2466  0.1955  2.3981  0             0               0        0       0         3.1198
```

Cleanup verification:

- Guarded cleanup initially timed out while the workspace was still visible as `DELETING` / `STOPPED`.
- Additional manual cleanup loop repeatedly issued `brev delete isaac-phase2-insert-latch-retry2-l4 4avspx131`.
- Final cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The latch fix is partially validated: the previous target flip-flop is not the primary blocker anymore.
- The new blocker is too-tight abort hysteresis under contact. The controller aborts insertion after a recoverable lateral drift just above `4 cm`.
- The next local change should relax the insert abort thresholds before another GPU run.

Local fix after this run:

- Relaxed `scripts/run_phase2_absik_gate.sh` default abort thresholds:
  - `--insert-abort-xy-tol 0.04` -> `--insert-abort-xy-tol 0.08`
  - `--insert-abort-rot-tol 0.35` -> `--insert-abort-rot-tol 0.50`

Next useful verification:

- Run one more guarded eval only if Brev deletion behavior looks normal.
- Pass condition is not necessarily success; the immediate pass condition is that `insert_state` remains true past step `227` and the controller no longer returns to rotate before the contact-induced jump.

## Attempt 42: Isaac Lab 5.3 configclass import drift

Date: 2026-05-16

Local base commit:

- `bb7a20b Debounce insert abort hysteresis`

Goal:

- Verify the debounced insert-abort hysteresis change on the live Isaac Lab runtime.
- Keep the run cheap by using the guarded `cheap` profile and L4 pricing.

Remote run:

- Run id: `2026-05-16T18-20-36Z`
- Instance: `isaac-phase2-abort-debounce-l4`
- Instance id: `vgtlogh5k`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`

Result:

- No scripted eval was executed.
- The run failed during runtime environment registration after the remote image reported:
  - `isaaclab==5.3.0`
  - `isaaclab_rl==0.5.2`
- Failure:

```text
TypeError: 'module' object is not callable
```

- The traceback pointed to `@configclass` in `peg_in_hole_env_cfg.py`.

Artifacts:

- Gate run dir: `artifacts/gpu_gate/2026-05-16T18-20-36Z_isaac-phase2-abort-debounce-l4`

Cleanup verification:

- `brev ls instances --all`: `No instances in org NCA-57cf-29515`
- `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- This attempt does not validate or invalidate the debounced abort logic.
- The blocker is Isaac Lab API/version drift: Isaac Lab 5.3 exposes `configclass` differently than the older runtime used by previous successful attempts.
- The correct local fix is a small compatibility layer, not a controller or reward change.

Local fix after this run:

- Added `robot_contact_assembly_tasks._compat.configclass`.
- Updated all local task config imports to use the compatibility helper instead of importing `configclass` directly from `isaaclab.utils`.
- Local syntax verification:

```text
python3 -m py_compile source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/_compat.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/peg_in_hole_env_cfg.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/config/franka/ik_rel_env_cfg.py \
  source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole/config/franka/agents/rsl_rl_ppo_cfg.py
```

Next useful verification:

- Run one short guarded eval with the compatibility import fix.
- Pass condition for the runtime fix is that environment registration reaches scripted eval startup.
- Pass condition for the controller change remains: `insert_state` stays true beyond the old abort point around step `227`.

## Attempt 43: configclass fix verified, contact jump remains

Date: 2026-05-16

Local base commit:

- `ab25388 Handle Isaac Lab configclass version drift`

Goal:

- Verify the Isaac Lab 5.3 `configclass` compatibility fix on a live Brev runtime.
- Re-run the debounced insert-abort gate after environment registration succeeds.

Remote run:

- Run id: `2026-05-16T18-50-03Z`
- Instance: `isaac-phase2-configclass-compat-l4`
- Instance id: `mx1f6iaeq`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
- Steps: `260`
- Seed: `42`

Result:

- Runtime registration succeeded under:
  - `isaaclab==5.3.0`
  - `isaaclab_rl==0.5.2`
- The `configclass` API drift blocker from Attempt 42 is fixed.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T19-04-04Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T19-04-04Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T19-04-04Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T18-50-03Z_isaac-phase2-configclass-compat-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 260,
  "insert_abort_xy_tolerance": 0.08,
  "insert_abort_rot_tolerance": 0.5,
  "insert_abort_grace_steps": 8,
  "insert_pos_step": 0.01,
  "insert_rot_step": 0.06,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.18682925403118134,
  "best_lateral": 0.0005068883765488863,
  "best_lateral_step": 165,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.3670172095298767,
  "best_axial": 0.04665598273277283,
  "best_axial_step": 210,
  "initial_rot": 2.87626576423645,
  "final_rot": 0.7406370043754578,
  "best_rot": 0.004081662744283676,
  "best_rot_step": 119,
  "max_contact_force_magnitude": 28.8151798248291,
  "max_contact_force_magnitude_step": 62,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     insert_state  violation  count  aborted
200   insert  0.0019  0.0563  0.0322  1             0          0      0
225   insert  0.0393  0.0553  0.1783  1             0          0      0
226   insert  0.0415  0.0561  0.1864  1             0          0      0
227   insert  0.0435  0.0569  0.1948  1             0          0      0
230   insert  0.0497  0.0594  0.2211  1             0          0      0
231   insert  0.2466  0.1955  2.3981  1             0          0      0
232   insert  0.2452  0.1945  2.4054  1             1          1      0
238   insert  0.2345  0.1863  2.4561  1             1          7      0
239   rotate  0.2416  0.1960  2.3388  0             1          0      1
```

Cleanup verification:

- Guarded cleanup initially saw the instance as `DELETING` and repeatedly re-issued delete.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The runtime compatibility issue is fixed.
- The debounced abort logic is validated against the old failure mode: `insert_state` now stays true past step `227`.
- The new blocker is a contact/dynamics jump during insertion. Lateral error grows gradually to about `5 cm`, then jumps to about `24.7 cm` at step `231` while still in insert mode.
- The next change should reduce insert-phase aggressiveness, not loosen abort thresholds again.

Local fix after this run:

- Reduced default insert waypoint speed in `scripts/run_phase2_absik_gate.sh`:
  - `--insert-pos-step 0.010` -> `--insert-pos-step 0.004`
  - `--insert-rot-step 0.06` -> `--insert-rot-step 0.02`

Next useful verification:

- Run one more guarded eval only after confirming Brev billing is stable.
- Pass condition: the large step-231 jump is delayed or eliminated; success is secondary.

## Attempt 44: slower insert still jumps; AbsIK is the likely blocker

Date: 2026-05-16

Local base commit:

- `c7c2f28 Record compat gate and slow insert motion`

Goal:

- Verify whether slower insert-stage Cartesian waypointing removes the large contact-induced jump seen in Attempt 43.
- Keep the run cheap by using the guarded `cheap` profile and L4 pricing.

Remote run:

- Run id: `2026-05-16T19-16-12Z`
- Instance: `isaac-phase2-slow-insert-l4`
- Instance id: `svife0deq`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
- Steps: `260`
- Seed: `42`

Result:

- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- Runtime and environment registration remained healthy under Isaac Lab 5.3.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T19-30-33Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T19-30-33Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T19-30-33Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T19-16-12Z_isaac-phase2-slow-insert-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 260,
  "insert_abort_xy_tolerance": 0.08,
  "insert_abort_rot_tolerance": 0.5,
  "insert_abort_grace_steps": 8,
  "insert_pos_step": 0.004,
  "insert_rot_step": 0.02,
  "initial_lateral": 0.19102078676223755,
  "final_lateral": 0.18592825531959534,
  "best_lateral": 0.0004320175212342292,
  "best_lateral_step": 195,
  "initial_axial": 0.4095129370689392,
  "final_axial": 0.3684142827987671,
  "best_axial": 0.05908873677253723,
  "best_axial_step": 230,
  "initial_rot": 2.87626576423645,
  "final_rot": 0.7124825119972229,
  "best_rot": 0.004081662744283676,
  "best_rot_step": 119,
  "max_contact_force_magnitude": 28.8151798248291,
  "max_contact_force_magnitude_step": 62,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat     ax      rot     insert_state  violation  count  aborted
195   insert  0.0004  0.0660  0.0232  1             0          0      0
200   insert  0.0006  0.0649  0.0281  1             0          0      0
225   insert  0.0015  0.0600  0.0838  1             0          0      0
230   insert  0.0015  0.0591  0.0977  1             0          0      0
231   insert  0.2466  0.1955  2.3981  1             0          0      0
232   insert  0.2460  0.1951  2.4004  1             1          1      0
238   insert  0.2420  0.1924  2.4176  1             1          7      0
239   rotate  0.2489  0.2025  2.3080  0             1          0      1
```

Cleanup verification:

- Guarded cleanup initially saw the instance as `DELETING` and repeatedly re-issued delete.
- A delete-by-id attempt later reported `instance with id/name svife0deq not found`, while the list briefly still showed the name as `DELETING`; this resolved without support escalation.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- Reducing insert velocity did not solve the jump. The lateral error stayed excellent through step `230`, then jumped at step `231` exactly as before.
- The likely blocker is the absolute differential-IK action path under contact, not simply excessive insert step size.
- The previous trace format mixed pre-step poses with post-step metrics; this made the first jump row look inconsistent. The next local fix should record post-step poses too.

Local fix after this run:

- Added post-step pose fields to scripted traces:
  - `post_hand_pos_w`
  - `post_action_pos_w`
  - `post_physical_tip_pos_w`
  - `post_socket_pos_w`
  - `post_physical_tip_rel_socket_pos`
  - `post_action_tip_alignment`
- Updated `scripts/summarize_scripted_trace.py` to prefer post-step poses when present.

Next useful verification:

- Stop tuning the AbsIK gate for now.
- Run the existing JointPos + bounded joint-IK gate next:
  - `scripts/run_phase2_jointik_gate.sh`
- Pass condition: no large jump after entering the near-socket contact corridor. Success is secondary.

## Attempt 45: JointIK gate aborted during startup cost guard

Date: 2026-05-16

Local base commit:

- `2e1c725 Record slow insert gate and trace post-step poses`

Goal:

- Run the existing JointPos + bounded joint-IK gate after adding post-step trace fields.
- Use the cheapest viable live-priced GPU option instead of defaulting to the previous L40S choice.

Remote run:

- Run id: `2026-05-16T19-40-03Z`
- Instance: `isaac-phase2-jointik-posttrace-l4`
- Instance id: `vvxjhm9bq`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps: `100`
- Seed: `42`

Result:

- No Isaac Lab evaluation result was produced.
- The instance spent several minutes in `RUNNING / BUILDING / NOT READY`.
- To avoid repeating prior Brev ghost-billing exposure, the instance was manually deleted before the runtime setup finished.
- The later log shows the instance did become `RUNNING / COMPLETED / READY`, but the manual deletion had already been triggered; Docker image pull/runtime setup was then interrupted by shutdown.
- This attempt is therefore an infrastructure/cost-guard abort, not evidence about the JointIK controller.

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-16T19-40-03Z_isaac-phase2-jointik-posttrace-l4/gate.log`
- Gate metadata: `artifacts/gpu_gate/2026-05-16T19-40-03Z_isaac-phase2-jointik-posttrace-l4/gate_metadata.env`

Cleanup verification:

- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The cost guard did the safe thing from a billing-risk standpoint, but it also aborted the run before the actual robotics test.
- The next attempt should allow the instance to pass through the normal image-pull/runtime setup path, while continuing to require final double-check cleanup.
- Do not interpret this run as a JointIK failure.

Next useful verification:

- Re-run `scripts/run_phase2_jointik_gate.sh` with the same L4 cheap profile.
- Do not manually delete while the instance is still progressing through first-time Docker image pull unless billing visibly continues after delete or the instance becomes stuck beyond the configured timeout.

## Attempt 46: JointIK gate completes but 100 steps only reaches laterally

Date: 2026-05-16

Local base commit:

- `b5333d0 Record aborted JointIK gate startup`

Goal:

- Re-run the JointPos + bounded joint-IK gate without prematurely deleting during normal startup.
- Verify whether the JointIK controller avoids the large AbsIK contact jump and can enter the near-socket corridor.

Remote run:

- Run id: `2026-05-16T19-54-03Z`
- Instance: `isaac-phase2-jointik-retry-l4`
- Instance id: `38p29648n`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps: `100`
- Seed: `42`

Result:

- Runtime setup completed under Isaac Lab `5.3.0`.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The controller did not reach the rotate/insert phase within 100 steps; all sampled rows remained in `reach`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T20-07-36Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T20-07-36Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T20-07-36Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T19-54-03Z_isaac-phase2-jointik-retry-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 100,
  "initial_lateral": 0.15123368799686432,
  "final_lateral": 0.04914068430662155,
  "best_lateral": 0.04914068430662155,
  "best_lateral_step": 99,
  "initial_axial": 0.5511814951896667,
  "final_axial": 0.5991832613945007,
  "best_axial": 0.5511814951896667,
  "best_axial_step": 0,
  "initial_rot": 3.048175811767578,
  "final_rot": 3.082163095474243,
  "best_rot": 3.032543420791626,
  "best_rot_step": 24,
  "max_contact_force_magnitude": 1.758440613746643,
  "max_contact_force_magnitude_step": 2,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase  lat     ax      rot     insert  contact
0     reach  0.1512  0.5512  3.0482  0       0.7986
25    reach  0.1243  0.5752  3.0327  0       1.2514
50    reach  0.1066  0.5919  3.0505  0       0.4093
75    reach  0.0827  0.6012  3.0676  0       0.6857
99    reach  0.0491  0.5992  3.0822  0       0.9389
```

Cleanup verification:

- Guarded cleanup repeatedly re-issued delete while Brev showed the instance as `DELETING`; the list briefly changed to `DEPLOYING / NOT READY` before disappearing.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- JointIK did not reproduce the AbsIK near-contact jump because it never reached the near-contact corridor in this short run.
- Lateral error improved monotonically from `0.1512 m` to `0.0491 m`, so the controller is moving in a useful direction.
- Axial error worsened because the early joint-limited path raises the action/tip frame while reducing lateral error. This does not yet prove the z direction is wrong; the run is too short.
- The next JointIK verification should use a longer horizon and a slightly less conservative joint step so it can actually reach rotate/insert.

Next useful verification:

- Increase the JointIK gate horizon from `100` to at least `300` steps.
- Increase `--joint-ik-step` modestly from `0.05` to `0.08`.
- Pass condition: the trace reaches `rotate` or `insert` and does not show the large AbsIK-style discontinuity.

## Attempt 47: longer JointIK reaches deep alignment but jumps before rotate

Date: 2026-05-16

Local base commit:

- `e158388 Extend JointIK gate horizon`

Goal:

- Give JointIK enough horizon to move beyond the first 100-step lateral approach.
- Check whether bounded joint-space IK avoids the large discontinuity seen in AbsIK when approaching the socket.

Remote run:

- Run id: `2026-05-16T20-18-26Z`
- Instance: `isaac-phase2-jointik-300-l4`
- Instance id: `ivgjctcyx`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps: `300`
- Seed: `42`

Result:

- Runtime setup completed under Isaac Lab `5.3.0`.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The controller stayed in `reach` for the full rollout and never entered `rotate` or `insert`.
- A large discontinuity appeared around step `271`, while still in `reach`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T20-32-11Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T20-32-11Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T20-32-11Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T20-18-26Z_isaac-phase2-jointik-300-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 300,
  "joint_ik_step": 0.08,
  "initial_lateral": 0.15152442455291748,
  "final_lateral": 0.19721953570842743,
  "best_lateral": 0.00010250138439005241,
  "best_lateral_step": 162,
  "initial_axial": 0.5511776804924011,
  "final_axial": 0.1583719551563263,
  "best_axial": 0.1583719551563263,
  "best_axial_step": 299,
  "initial_rot": 3.048088312149048,
  "final_rot": 2.404402017593384,
  "best_rot": 2.395254373550415,
  "best_rot_step": 275,
  "max_contact_force_magnitude": 1.8983913660049438,
  "max_contact_force_magnitude_step": 2,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase  lat     ax      rot     insert  contact
100   reach  0.0002  0.5215  3.0686  0       0.2659
150   reach  0.0001  0.4456  3.0683  0       0.2917
200   reach  0.0002  0.3716  3.0688  0       0.3305
250   reach  0.0003  0.2994  3.0703  0       0.3630
270   reach  0.0004  0.2710  3.0712  0       0.3770
271   reach  0.2466  0.1955  2.3981  0       0.3800
299   reach  0.1972  0.1584  2.4044  0       0.3702
```

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The longer horizon proved that JointIK can hold sub-millimeter lateral alignment while descending for many steps.
- The discontinuity is not an insert/contact event. It occurs during the unconstrained `reach` descent while the orientation error remains near `pi`.
- The current phase logic descends before rotating; this is unsafe for the JointPos + standalone JointIK controller because it can approach a bad kinematic branch before correcting orientation.
- The next useful fix is not more horizon. It is staged approach: align XY at current height, rotate before descent, then descend.

Next useful verification:

- Enable `--staged-approach --rotate-before-descend` for JointIK.
- Increase horizon to `500` steps so the staged sequence has enough time for XY, rotation, descent, and possible insertion.
- Pass condition: the trace reaches `rotate` before z descent and avoids the step-271-style lateral discontinuity.

## Attempt 48: staged JointIK reaches rotate but stalls at the 180-degree branch

Date: 2026-05-16

Local base commit:

- `4d4de00 Stage JointIK approach before descent`

Goal:

- Verify the staged sequence: align XY first, rotate before z descent, then allow insertion.
- Check whether the step-271-style discontinuity was caused by descending before orientation alignment.

Remote run:

- Run id: `2026-05-16T20-39-57Z`
- Instance: `isaac-phase2-jointik-staged-l4`
- Instance id: `4z56xfo9m`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps: `500`
- Seed: `42`
- Extra controller flags: `--staged-approach --rotate-before-descend`

Result:

- Runtime setup completed under Isaac Lab `5.3.0`.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The staged state machine worked: it entered `rotate` around step `100` and held XY alignment for hundreds of steps.
- Rotation did not converge; the controller stayed near a `pi`-radian orientation error until a late kinematic branch jump around step `472`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T20-53-36Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T20-53-36Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T20-53-36Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T20-39-57Z_isaac-phase2-jointik-staged-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 500,
  "joint_ik_step": 0.08,
  "initial_lateral": 0.15045957267284393,
  "final_lateral": 0.19186298549175262,
  "best_lateral": 0.0000070654918999935035,
  "best_lateral_step": 142,
  "initial_axial": 0.5510136485099792,
  "final_axial": 0.23291534185409546,
  "best_axial": 0.19548767805099487,
  "best_axial_step": 472,
  "initial_rot": 3.048344850540161,
  "final_rot": 2.84551739692688,
  "best_rot": 2.3980886936187744,
  "best_rot_step": 472,
  "max_contact_force_magnitude": 2.543524980545044,
  "max_contact_force_magnitude_step": 2,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     contact
075   reach   0.0182   0.5623  3.0822  0.9224
100   rotate  0.0016   0.5627  3.1386  0.0987
150   rotate  0.0000   0.5624  3.1351  0.0711
250   rotate  0.0000   0.5624  3.1346  0.0677
350   rotate  0.0000   0.5624  3.1341  0.0660
450   rotate  0.0000   0.5624  3.1337  0.0698
471   rotate  0.0000   0.5624  3.1358  0.0142
472   rotate  0.2466   0.1955  2.3981  0.0696
499   rotate  0.1919   0.2329  2.8455  0.4805
```

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- Staging fixed the previous diagnosis: the system no longer descends before trying to rotate.
- The new bottleneck is a quaternion branch issue in the scripted rotate waypoint. The target pose is close to a 180-degree rotation from the current action frame, so recomputing an axis-angle waypoint from the measured pose alternates between antipodal `+pi/-pi` branches.
- The trace confirms the oscillation: `command_quat_w` flips sign across adjacent rotate steps while the measured `rot` remains near `3.13` rad.
- This is a controller artifact, not a contact asset failure. It happens high above the socket, before insertion.

Next useful verification:

- Add a stateful rotate waypoint that advances a persistent quaternion command toward the target and preserves sign continuity across steps.
- Run the same staged JointIK gate with `--rotate-control-mode stateful-waypoint`.
- Pass condition: `rot` should decrease monotonically or at least drop well below `1.0` rad before any z descent or branch jump.

## Attempt 49: stateful rotate fixes orientation but exposes unstable post-rotate descent

Date: 2026-05-16

Local base commit:

- `b388c0d Add stateful rotate waypoint for JointIK`

Goal:

- Verify that `--rotate-control-mode stateful-waypoint` fixes the 180-degree quaternion branch oscillation from Attempt 48.
- Keep the same staged JointIK gate otherwise unchanged.

Remote run:

- Run id: `2026-05-16T21-06-47Z`
- Instance: `isaac-phase2-jointik-stateful-rot-l4`
- Instance id: `cvyfoyyn2`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps: `500`
- Seed: `42`
- Extra controller flags: `--rotate-control-mode stateful-waypoint --staged-approach --rotate-before-descend`

Result:

- Runtime setup completed under Isaac Lab `5.3.0`.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The stateful quaternion command worked: best rotation error improved from Attempt 48's `2.3981` rad to `0.2232` rad.
- The rollout then exposed the next bottleneck: after rotation becomes acceptable, JointIK descends toward the approach height very slowly and eventually jumps to a bad kinematic branch around step `475`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T21-21-00Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T21-21-00Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T21-21-00Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T21-06-47Z_isaac-phase2-jointik-stateful-rot-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 500,
  "joint_ik_step": 0.08,
  "initial_lateral": 0.15045957267284393,
  "final_lateral": 0.2889006435871124,
  "best_lateral": 0.0027058895211666822,
  "best_lateral_step": 412,
  "initial_axial": 0.5510136485099792,
  "final_axial": 0.2738342881202698,
  "best_axial": 0.1939792037010193,
  "best_axial_step": 475,
  "initial_rot": 3.048344850540161,
  "final_rot": 2.209791421890259,
  "best_rot": 0.2232261598110199,
  "best_rot_step": 197,
  "max_contact_force_magnitude": 4.209502220153809,
  "max_contact_force_magnitude_step": 110,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     note
100   rotate  0.0922   0.5611  2.8951  stateful rotation has started
150   rotate  0.3509   0.5774  1.6631  orientation improving, XY drifting
197   rotate  0.2657   0.5632  0.2232  best rotation
225   rotate  0.2221   0.5498  0.2525  orientation ready, descent begins
350   rotate  0.0282   0.5394  0.2530  XY recovered, z descent still slow
412   rotate  0.0027   0.5287  0.2657  best XY, still high above socket
470   rotate  0.0034   0.5169  0.2582  aligned but still far above approach height
475   rotate  0.2543   0.1940  2.3312  branch jump
499   rotate  0.2889   0.2738  2.2098  failed recovery
```

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The quaternion branch fix is validated. Attempt 49 is a useful positive result even though insertion still fails.
- The remaining failure is trajectory/controller stability after the high-altitude rotation. The controller reaches a near-correct orientation, recovers XY alignment, but cannot descend efficiently to the approach pose before a late IK branch jump.
- This suggests that the next fix should be a post-rotate descent strategy, not more rotation logic.

Next useful verification:

- Add a dedicated post-rotate descent phase with a larger joint step or a lower intermediate hold height, while keeping orientation target fixed.
- Alternatively test the same staged state machine on the absolute-IK task, because the stateful rotate fix may make AbsIK usable again.
- Pass condition: after rotation, the trace should reduce axial error below `0.1` while keeping `lateral < 0.015` and `rot < 0.25` before entering insertion.

## Attempt 50: post-rotate descent hold improves alignment but still hits late IK branch jump

Date: 2026-05-16

Local base commit:

- `08995b3 Hold orientation during post-rotate descent`

Goal:

- Verify whether holding the current action-frame orientation during post-rotate descent lets JointIK reduce axial error faster than Attempt 49.
- Keep the stateful rotate waypoint and staged approach unchanged.

Remote run:

- Run id: `2026-05-16T21-32-26Z`
- Instance: `isaac-phase2-jointik-descend-hold-l4`
- Instance id: `vuicephzj`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps: `500`
- Seed: `42`
- Extra controller flags: `--rotate-control-mode stateful-waypoint --staged-approach --rotate-before-descend --hold-orientation-during-descend`

Result:

- Runtime setup completed under Isaac Lab `5.3.0`.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The post-rotate descent hold improved the rollout compared with Attempt 49:
  - best rotation crossed the success threshold: `0.1707 < 0.18` rad.
  - best lateral alignment crossed the success threshold: `0.0008 < 0.005` m.
  - axial error decreased much faster after rotation, reaching `0.19398` m by step `475`.
- The same late IK branch jump still occurs near step `475`, before axial insertion reaches the `0.008` m success threshold.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T21-45-50Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T21-45-50Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T21-45-50Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T21-32-26Z_isaac-phase2-jointik-descend-hold-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 500,
  "joint_ik_step": 0.08,
  "hold_orientation_during_descend": true,
  "initial_lateral": 0.15045957267284393,
  "final_lateral": 0.2889006435871124,
  "best_lateral": 0.0008446893189102411,
  "best_lateral_step": 345,
  "initial_axial": 0.5510136485099792,
  "final_axial": 0.2738342881202698,
  "best_axial": 0.1939792037010193,
  "best_axial_step": 475,
  "initial_rot": 3.048344850540161,
  "final_rot": 2.209791421890259,
  "best_rot": 0.17067496478557587,
  "best_rot_step": 380,
  "max_contact_force_magnitude": 4.209502220153809,
  "max_contact_force_magnitude_step": 110,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     note
200   rotate  0.2586   0.5602  0.2240  orientation becomes usable
300   rotate  0.0559   0.3974  0.2494  descent is much faster than Attempt 49
325   rotate  0.0129   0.3582  0.2316  XY and orientation ready for insertion tolerances
345   rotate  0.0008   0.3244  0.2383  best XY
375   rotate  0.0059   0.2835  0.1733  rotation success threshold crossed
380   rotate  0.0058   0.2769  0.1707  best rotation
400   rotate  0.0048   0.2498  0.2061  XY remains within success threshold
450   rotate  0.0029   0.2086  0.2392  still aligned, axial still too high
470   rotate  0.0027   0.1967  0.2386  final stable aligned state before jump
475   rotate  0.2543   0.1940  2.3312  branch jump
499   rotate  0.2889   0.2738  2.2098  failed recovery
```

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The descent-hold change is validated as an incremental improvement: the controller can now independently hit the XY and rotation success thresholds in the real contact scene.
- It still does not solve the whole scripted gate because insertion requires XY, axial, and rotation to be good at the same time, and the rollout jumps to a bad IK branch while still about `0.19` m above the target axial threshold.
- Additional random tuning of this JointIK controller has diminishing returns. The next useful work should add a safer post-alignment insertion transition or replace the final descent with a planner-generated nominal joint path.

Next useful verification:

- Add branch-jump detection to abort when lateral or rotation error spikes after an aligned state, so failed traces terminate cleanly instead of hiding the root cause.
- Split the current `rotate` stage into explicit `align`, `descend`, and `insert` states. Enter controlled insertion once `lateral < 0.015` and `rot < 0.25`, instead of waiting for the high-level approach target to be fully reached.
- Consider generating the final descent with a motion planner or a cached nominal joint trajectory, then use JointIK only for small corrections near the socket.

## Prepared next gate: early insert after alignment plus branch-jump stop

Date: 2026-05-16

Local change:

- Added `--insert-after-alignment` to let the staged controller latch insertion as soon as lateral and orientation errors are inside insertion tolerances.
- Added `--stop-on-branch-jump` and branch-jump thresholds so a rollout stops when it has already been aligned and then suddenly jumps to a bad lateral or orientation state.
- Updated the trace summarizer to show `desc`, `aligned`, and `branch` columns.
- Updated `scripts/run_phase2_jointik_gate.sh` so the next guarded GPU gate uses these flags by default.

Why:

- Attempt 50 showed the controller could reach both `lateral < 0.005` and `rot < 0.18`, but it kept waiting for the approach-height waypoint and then jumped branches around step `475`.
- The next verification should test whether entering insertion immediately after alignment avoids that late branch jump.
- If it still jumps, the new stop condition will shorten the paid GPU run and record the jump step directly in summary/trace JSON.

Next pass condition:

- Better than Attempt 50 if insertion enters before step `475` and axial error drops below `0.1` without a branch jump.
- Successful if the rollout reaches `success_step != null`.
- Failed but useful if `branch_jump_step` is recorded earlier with a trace showing which phase triggered it.

## Attempt 51: early insert enters but aborts too aggressively before late branch jump

Date: 2026-05-16

Local base commit:

- `7f5bdcb Add early insertion gate diagnostics`

Goal:

- Test whether `--insert-after-alignment` can enter insertion before the late JointIK branch jump observed in Attempt 50.
- Use `--stop-on-branch-jump` to terminate as soon as the already-aligned rollout jumps to a bad IK branch.

Remote run:

- Run id: `2026-05-16T22-18-16Z`
- Instance: `isaac-phase2-early-insert-l4`
- Instance id: `gurs4smx9`
- Selected machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`
- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Steps requested: `500`
- Seed: `42`
- Extra controller flags: `--rotate-control-mode stateful-waypoint --hold-orientation-during-descend --insert-after-alignment --stop-on-branch-jump --staged-approach --rotate-before-descend`

Result:

- Runtime setup completed under Isaac Lab `5.3.0`.
- Scripted eval completed and artifacts were pulled locally.
- `success_rate=0.0`; no insertion success.
- The new early-insert logic worked mechanically: the rollout entered `insert` at step `325`, instead of waiting until the approach-height waypoint was reached.
- The rollout still failed because the insertion latch is too brittle. It repeatedly toggled between `insert` and `align` due to the immediate abort condition, then hit the same late IK branch jump at step `472`.

Artifacts:

- Scripted eval JSON: `artifacts/evaluations/scripted/2026-05-16T22-33-24Z/seed_42.json`
- Scripted trace: `artifacts/evaluations/scripted/2026-05-16T22-33-24Z/seed_42_trace.json`
- Scripted eval log: `artifacts/evaluations/scripted/2026-05-16T22-33-24Z/seed_42.log`
- Gate log: `artifacts/gpu_gate/2026-05-16T22-18-16Z_isaac-phase2-early-insert-l4/gate.log`

Metrics:

```json
{
  "steps_requested": 500,
  "joint_ik_step": 0.08,
  "insert_after_alignment": true,
  "stop_on_branch_jump": true,
  "branch_jump_step": 472,
  "branch_jump_reason": "lateral=0.2466 rot=2.3981 after_aligned=True",
  "initial_lateral": 0.15045957267284393,
  "final_lateral": 0.24659933149814606,
  "best_lateral": 0.0004201083502266556,
  "best_lateral_step": 340,
  "initial_axial": 0.5510136485099792,
  "final_axial": 0.19548767805099487,
  "best_axial": 0.19548767805099487,
  "best_axial_step": 472,
  "initial_rot": 3.048344850540161,
  "final_rot": 2.3980886936187744,
  "best_rot": 0.22196103632450104,
  "best_rot_step": 217,
  "max_contact_force_magnitude": 4.209502220153809,
  "max_contact_force_magnitude_step": 110,
  "final_success_rate": 0.0,
  "success_step": null
}
```

Trace highlights:

```text
step  phase    lat      ax      rot     insert  aligned  branch  note
300   descend  0.0559   0.3974  0.2494  0       0        0       alignment almost ready
325   insert   0.0131   0.3581  0.2459  1       1        0       early insertion entered
340   align    0.0004   0.3564  0.2432  0       1        0       insert latch aborted despite good post-step pose
350   insert   0.0026   0.3546  0.2551  1       1        0       insert re-entered
375   insert   0.0039   0.3532  0.2487  1       1        0       stable XY, axial still high
400   insert   0.0052   0.3509  0.2535  1       1        0       rot/XY near threshold
425   insert   0.0052   0.3487  0.2507  1       1        0       slow axial progress
450   align    0.0040   0.3458  0.2429  0       1        0       latch aborted again
470   insert   0.0058   0.3421  0.2462  1       1        0       still far above axial threshold
472   align    0.2466   0.1955  2.3981  0       1        1       branch jump, stopped early
```

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- Attempt 51 answered the intended question: early insertion avoids waiting for `position_ready`, but it does not yet solve the controller failure.
- The next blocker is not task registration, contact assets, or frame alignment. It is the scripted insertion latch and final descent controller.
- Immediate abort with `insert_abort_grace_steps=1` is too strict for this noisy near-contact phase. It causes the state machine to oscillate out of insertion even when the post-step pose is visually aligned.
- Axial progress during insertion is too slow: from step `325` to `470`, axial error only improves from `0.3581` to `0.3421` before the late branch jump. The final insertion command needs either a less constrained joint-space path or a stronger controlled z descent.

Next useful verification:

- Relax the insertion latch before another GPU run:
  - `--insert-abort-grace-steps 8`
  - `--insert-abort-xy-tol 0.03`
  - `--insert-abort-rot-tol 0.35`
- Keep `--stop-on-branch-jump` enabled so the run still terminates early if the IK branch jump persists.
- If relaxed insertion still makes little axial progress, stop tuning this scripted JointIK gate and switch to a nominal joint trajectory or planner-generated final descent.

## Prepared next gate: relaxed insertion latch

Date: 2026-05-16

Local change:

- Updated `scripts/run_phase2_jointik_gate.sh` to keep early insertion enabled but relax insertion abort:
  - `--insert-abort-grace-steps 8`
  - `--insert-abort-xy-tol 0.03`
  - `--insert-abort-rot-tol 0.35`
- Kept `--stop-on-branch-jump` enabled to limit cost and preserve a clean diagnostic if the IK branch jump remains.

Why:

- Attempt 51 showed that early insertion enters at step `325`, but the latch exits insertion on single-step tolerance violations.
- The next run should answer whether continuous insertion command improves axial progress before the branch jump.

Next pass condition:

- Better than Attempt 51 if `insert_state` remains active continuously after first entry and `best_axial < 0.15`.
- Successful if `success_step != null`.
- Failed but useful if branch jump still occurs with continuous insertion, because that would justify replacing the final JointIK descent with a nominal joint trajectory or planner-generated path.

## Attempt 52: relaxed insertion gate aborted during Brev create

Date: 2026-05-16

Local base commit:

- `de3cc3e Record early insert gate result`

Goal:

- Run the relaxed insertion latch gate prepared after Attempt 51.

Remote run:

- Run id: `2026-05-16T22-41-55Z`
- Requested instance: `isaac-phase2-relaxed-insert-l4`
- Requested machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`

Result:

- No scripted evaluation ran.
- Brev returned `unexpected EOF` while creating the workspace:
  - `CreateWorkspace ... Post ... unexpected EOF`
  - `Warning: Only created 0/1 instances`
  - `could only create 0/1 instances`
- The guarded cleanup still found a potential half-created instance id `2d6qquumg` and deleted it.

Artifacts:

- Gate log: `artifacts/gpu_gate/2026-05-16T22-41-55Z_isaac-phase2-relaxed-insert-l4/gate.log`

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- This was a Brev workspace creation/backend failure, not a project-code failure.
- The relaxed insertion latch remains untested.
- A single retry is reasonable because the guarded cleanup confirmed the org is empty.

## Attempt 53: relaxed insertion latch gate

Date: 2026-05-16

Local base commit:

- `7f06d21 Record aborted relaxed insert gate create`

Goal:

- Retry Attempt 52 after the Brev create failure.
- Test whether a relaxed insertion latch can keep the scripted controller in `insert` long enough to improve axial progress.

Remote run:

- Run id: `2026-05-16T22-45-03Z`
- Instance: `isaac-phase2-relaxed-insert-retry-l4`
- Instance id: `7xxno8b0a`
- Machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`

Artifacts:

- Gate archive: `artifacts/gpu_gate/2026-05-16T22-45-03Z_isaac-phase2-relaxed-insert-retry-l4/`
- Eval JSON: `artifacts/evaluations/scripted/2026-05-16T22-58-58Z/seed_42.json`
- Trace JSON: `artifacts/evaluations/scripted/2026-05-16T22-58-58Z/seed_42_trace.json`
- Eval log: `artifacts/evaluations/scripted/2026-05-16T22-58-58Z/eval.log`

Configuration highlights:

- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Seed: `42`
- Socket override: `0.22,0.04,0.19`
- Control mode: `joint-ik`
- Joint IK step: `0.08`
- Abort grace: `8`
- Abort XY tolerance: `0.03`
- Abort rotation tolerance: `0.35`
- Branch-jump stop: enabled

Result:

```json
{
  "final_success_rate": 0.0,
  "success_step": null,
  "initial_lateral": 0.15045957267284393,
  "final_lateral": 0.24659933149814606,
  "best_lateral": 0.002389051951467991,
  "best_lateral_step": 454,
  "initial_axial": 0.5510136485099792,
  "final_axial": 0.19548767805099487,
  "best_axial": 0.19548767805099487,
  "best_axial_step": 472,
  "initial_rot": 3.048344850540161,
  "final_rot": 2.3980886936187744,
  "best_rot": 0.22196103632450104,
  "best_rot_step": 217,
  "max_contact_force_magnitude": 4.209502220153809,
  "max_contact_force_magnitude_step": 110,
  "branch_jump_step": 472,
  "branch_jump_reason": "lateral=0.2466 rot=2.3981 after_aligned=True"
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     insert  aligned  branch  note
325   insert  0.0131   0.3581  0.2459  1       1        0       early insertion entered
350   insert  0.0087   0.3509  0.2787  1       1        0       latch stayed active
375   insert  0.0092   0.3463  0.2942  1       1        0       axial still high
400   insert  0.0075   0.3420  0.3138  1       1        0       continuous insert
425   insert  0.0053   0.3379  0.3440  1       1        0       near XY threshold
450   insert  0.0038   0.3380  0.3483  1       1        0       best XY region
458   insert  0.0038   0.3260  0.4873  1       1        0       rotation drift reached abort threshold
459   align   0.0028   0.3280  0.4675  0       1        0       relaxed latch aborted after 8 violating steps
468   align   0.0052   0.3499  0.2477  0       1        0       re-aligned near insertion tolerance
469   insert  0.0067   0.3484  0.2587  1       1        0       insertion re-entered
470   insert  0.0063   0.3466  0.2751  1       1        0       axial still far above success threshold
472   insert  0.2466   0.1955  2.3981  1       1        1       branch jump, stopped early
```

Cleanup verification:

- Guarded cleanup completed.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- The relaxed latch reduced the immediate insert/align oscillation observed in Attempt 51. It stayed in `insert` from step `325` through `458`, then aborted at `459` after eight over-rotation steps and re-entered at `469`.
- The controller still did not produce useful axial insertion. From step `325` to `470`, axial error only moved from `0.3581` to `0.3466`; the apparent best axial at step `472` coincided with a branch jump and should not be treated as a valid insertion improvement.
- This is now strong evidence against spending more GPU time on scripted JointIK threshold tuning.
- The next useful local change is a new final-descent strategy: either a nominal joint trajectory, a planner-generated final descent path, or a cached waypoint replay that keeps the arm on the same IK branch during insertion.

Decision:

- Stop running more GPU gates until the final descent controller changes.
- Keep the current artifacts as the diagnostic evidence for why Phase 2 needs a controller change rather than another reward or threshold tweak.

## Prepared next gate: vertical insertion descent

Date: 2026-05-17

Local change:

- Added `--insert-descent-mode vertical` to `scripts/scripted_agent.py`.
- Added `--hold-orientation-during-insert` so the insertion phase can freeze the action-frame orientation at insertion entry instead of continuing to rotate toward the socket.
- Added trace fields for insertion descent mode, frozen insertion orientation state, and true first insertion entry.
- Updated `scripts/run_phase2_jointik_gate.sh` so the next guarded gate uses:
  - `--insert-descent-mode vertical`
  - `--insert-vertical-step 0.018`
  - `--hold-orientation-during-insert`

Why:

- Attempt 53 showed that full pose-target insertion over-constrains the final descent: lateral error stayed good, but rotation drifted until the latch aborted, then the rollout re-entered insertion and hit the same branch jump.
- The next test should isolate vertical insertion from socket-orientation chasing. If this avoids the branch jump, the remaining issue is orientation refinement near contact. If it still jumps, the next step should be a planner/cached joint trajectory rather than another Cartesian JointIK variant.

Pass condition:

- Better than Attempt 53 if no branch jump occurs before step `500` and axial error improves below `0.25` without losing lateral alignment.
- Successful if `success_step != null`.
- Failed but useful if branch jump still appears, because that would justify replacing this controller path with a planned/cached joint trajectory.

## Attempt 54: vertical insertion descent gate

Date: 2026-05-16 / 2026-05-17 local

Local base commit:

- `e502d35 Add vertical insert descent gate`

Goal:

- Test the new final descent path from the prepared gate above.
- Isolate vertical insertion from socket-orientation chasing by freezing the action-frame orientation at insertion entry.

Remote run:

- Run id: `2026-05-16T23-12-50Z`
- Instance: `isaac-phase2-vertical-insert-l4`
- Instance id: `4md4qpsj`
- Machine: `g2-standard-4:nvidia-l4:1`
- Selected live price: `$0.85/hr`

Price selection:

- The guarded wrapper recorded the live 24 GB / 32 GB / 40 GB Brev price tables before creating the instance.
- The selected L4 was the cheapest suitable single-GPU candidate for this short scripted gate.
- The cheapest visible L40S candidate in the same table was `gpu-l40s-a.1gpu-8vcpu-32gb` at `$1.86/hr`, so L4 was the better value for this validation.

Artifacts:

- Gate archive: `artifacts/gpu_gate/2026-05-16T23-12-50Z_isaac-phase2-vertical-insert-l4/`
- Eval JSON: `artifacts/evaluations/scripted/2026-05-16T23-26-56Z/seed_42.json`
- Trace JSON: `artifacts/evaluations/scripted/2026-05-16T23-26-56Z/seed_42_trace.json`
- Eval log: `artifacts/evaluations/scripted/2026-05-16T23-26-56Z/seed_42.log`

Configuration highlights:

- Task: `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`
- Seed: `42`
- Socket override: `0.22,0.04,0.19`
- Control mode: `joint-ik`
- Insert descent mode: `vertical`
- Insert vertical step: `0.018`
- Hold orientation during insert: enabled
- Branch-jump stop: enabled

Result:

```json
{
  "final_success_rate": 0.0,
  "success_step": null,
  "initial_lateral": 0.15045957267284393,
  "final_lateral": 0.24659933149814606,
  "best_lateral": 0.0002292781719006598,
  "best_lateral_step": 455,
  "initial_axial": 0.5510136485099792,
  "final_axial": 0.19548767805099487,
  "best_axial": 0.19468888640403748,
  "best_axial_step": 471,
  "initial_rot": 3.048344850540161,
  "final_rot": 2.3980886936187744,
  "best_rot": 0.12049026042222977,
  "best_rot_step": 362,
  "branch_jump_step": 472,
  "branch_jump_reason": "lateral=0.2466 rot=2.3981 after_aligned=True"
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     succ_xy  succ_z  succ_rot  mode      note
325   insert  0.0129   0.3582  0.2316  0        0       0         vertical  insertion entered
350   insert  0.0058   0.3202  0.2162  0        0       0         vertical  faster axial progress than Attempt 53
362   insert  0.0068   0.3058  0.1205  0        0       1         vertical  rotation success reached
425   insert  0.0022   0.2500  0.2908  1        0       0         vertical  XY success reached, axial still high
450   insert  0.0015   0.2288  0.2304  1        0       0         vertical  strong XY, still no insertion depth
471   insert  0.0005   0.1947  0.3061  1        0       0         vertical  best axial before jump
472   insert  0.2466   0.1955  2.3981  0        0       0         vertical  same branch jump, stopped early
```

Cleanup verification:

- Guarded cleanup completed after repeated delete retries while Brev showed the instance as `DELETING`.
- Final independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Interpretation:

- Vertical insertion descent improved the useful metrics, but did not solve the rollout.
- Compared with Attempt 53:
  - best lateral improved from `0.002389 m` to `0.000229 m`
  - best rotation improved from `0.221961 rad` to `0.120490 rad`
  - best axial was effectively unchanged at about `0.195 m`
- The policy/controller can now independently satisfy XY and rotation thresholds in the real contact scene, but not insertion depth.
- The same branch jump at step `472` means the next blocker is not another insertion threshold or orientation-hold tweak. The final descent still drives the arm into an unstable branch/contact event before axial success.

Decision:

- Do not run another paid GPU gate until the controller path changes again.
- Next local work should focus on one of:
  - adding branch-jump forensics to trace current joint position, joint velocity, joint limits, and contact force at the exact jump;
  - moving the socket pose to a kinematically safer height/position and documenting the reachability reason;
  - replacing the final descent with a planned/cached joint trajectory that avoids the unstable branch.

## Prepared next diagnostic: branch-jump joint forensics

Date: 2026-05-17

Local change:

- Extended `scripts/scripted_agent.py` trace output with:
  - pre-step selected joint positions and velocities
  - post-step selected joint positions and velocities
  - selected joint lower/upper limits
  - pre-step and post-step joint-limit margin vectors
  - min joint-limit margin at the branch-jump step
  - contact force at the branch-jump step
- Extended `scripts/summarize_scripted_trace.py` with a `jlim` column for quick branch-jump review.

Why:

- Attempts 53 and 54 both failed at the same branch-jump step (`472`) after the rollout had already reached aligned states.
- The existing trace proves that the end-effector pose jumps, but not whether the jump is caused by joint-limit saturation, velocity spike, contact impulse, or the direct joint-position action path.
- The next paid run should collect these diagnostics before trying a new controller family.

Next diagnostic pass condition:

- Useful if it identifies whether the step-472 jump coincides with near-zero joint-limit margin, large joint velocity, or contact force spike.
- If the joint-limit margin is the root cause, move the socket pose or reset posture before another controller experiment.
- If the joint limits are not implicated, switch to a planned/cached final joint trajectory or lower-level action smoothing.

## Prepared next gate: timeout-safe success attempt

Date: 2026-05-17

Local change:

- Fixed scripted episode horizon calculation in `scripts/scripted_agent.py`.
- The horizon now includes `warmup_steps + steps + episode_buffer_steps` instead of only `steps + 2`.
- Added summary fields:
  - `warmup_steps`
  - `episode_buffer_steps`
  - `scripted_required_steps`
  - `scripted_episode_length_s`
  - `effective_episode_length_s`
- Increased `scripts/run_phase2_jointik_gate.sh` default evaluation length from `500` to `800` steps and timeout from `240` to `420` seconds.

Why:

- Attempts 53 and 54 both stopped at step `472` after a 30-step warmup.
- With the old horizon calculation, the environment could reach timeout/reset around the same point even though the scripted loop requested 500 steps.
- This means the repeated step-472 "branch jump" may be a timeout/reset artifact rather than an IK branch jump.

Next pass condition:

- Successful if `success_step != null`.
- Better than Attempt 54 if the rollout passes step `500` without the reset-like branch jump and keeps reducing axial error.
- Failed but useful if no reset occurs and axial still plateaus, because that would confirm final insertion depth is a real controller/contact problem.

## Attempt 55: timeout-safe success attempt startup failure

Date: 2026-05-17

Run:

- Gate run id: `2026-05-17T01-10-05Z`
- Instance: `isaac-phase2-timeout-safe-success-l4`
- Instance id: `u19wx2ecb`
- Instance type: `g2-standard-4:nvidia-l4:1`
- Recorded cheapest relevant price: L4 `g2-standard-4:nvidia-l4:1` at `$0.85/hr`
- Output dir: `artifacts/evaluations/scripted/2026-05-17T01-25-51Z/`

Result:

- No valid rollout.
- Isaac Lab launched and created the environment, but the scripted controller crashed before the first controlled step.
- Error:

```text
NameError: name 'limit_margin' is not defined
```

Root cause:

- The new joint-limit helper accepted a parameter named `margin`, but its body used the old local name `limit_margin`.
- This was a bookkeeping bug introduced while adding branch-jump forensics, not a controller or environment failure.

Fix:

- Commit `cb54e9e Fix joint limit margin helper`
- `python3 -m py_compile scripts/scripted_agent.py` passed.
- Commit was pushed to GitHub before the next GPU run.

Cleanup verification:

- Guarded cleanup completed after repeated delete retries.
- Independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

## Attempt 56: timeout-safe 800-step insertion gate

Date: 2026-05-17

Run:

- Gate run id: `2026-05-17T01-35-11Z`
- Instance: `isaac-phase2-success-l4-r2`
- Instance id: `tpbo4quc9`
- Instance type: `g2-standard-4:nvidia-l4:1`
- Recorded cheapest relevant price: L4 `g2-standard-4:nvidia-l4:1` at `$0.85/hr`
- Output dir: `artifacts/evaluations/scripted/2026-05-17T01-52-32Z/`
- Steps: `800`
- Effective episode length: `28.333333333333332s`
- Required scripted steps including warmup/buffer: `850`

Configuration:

- Deterministic reset at socket position `(0.22, 0.04, 0.19)`
- Joint-IK pre-controller
- Staged approach
- Rotate before descend
- Vertical insert descent
- Insert vertical step: `0.018`
- Hold orientation during insert: enabled
- Branch-jump stop: enabled

Result:

```json
{
  "final_success_rate": 0.0,
  "success_step": null,
  "final_lateral": 0.010781876742839813,
  "final_axial": 0.04254131019115448,
  "final_rot": 0.442598819732666,
  "best_lateral": 0.0002292781719006598,
  "best_lateral_step": 455,
  "best_axial": 0.038863569498062134,
  "best_axial_step": 788,
  "best_rot": 0.12049026042222977,
  "best_rot_step": 362
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     succ_xy  succ_z  succ_rot  contact  note
362   insert  0.0068   0.3058  0.1205  0        0       1         0.1245   rotation success reached
425   insert  0.0022   0.2500  0.2908  1        0       0         0.2662   XY success reached
475   insert  0.0005   0.1878  0.3510  1        0       0         0.1759   passed old step-472 reset point
600   align   0.0029   0.1456  0.4590  1        0       0         0.5842   axial still improving
775   insert  0.0062   0.0416  0.2445  0        0       0         5.3462   contact spike near deep insertion
788   insert  0.0091   0.0389  0.3178  0        0       0         0.0687   best axial
799   align   0.0108   0.0425  0.4426  0        0       0         0.8422   insert aborted near the end
```

Interpretation:

- The old step-472 failure was confirmed to be mostly a timeout/reset artifact, not the original branch-jump diagnosis.
- The horizon fix worked: the rollout passed step `500` and reached step `799`.
- This is the best real-contact scripted result so far:
  - `best_axial` improved from about `0.1947m` to `0.0389m`
  - XY alignment remained sub-millimeter at best
  - rotation success was reached earlier in the rollout
- Remaining blocker: final 3-4 cm insertion depth with coupled contact/rotation instability.

Decision after Attempt 56:

- One more paid run was allowed, but only with a different hypothesis:
  - require stricter insert entry (`insert_rot_tol=0.18`, `insert_xy_tol=0.008`)
  - slow the vertical insert step
  - extend rollout to `1400` steps
  - widen abort grace to avoid early insert cancellation

Cleanup verification:

- Guarded cleanup completed after repeated delete retries while Brev showed the instance as `DELETING`/`STOPPING`.
- Independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

## Attempt 57: strict insert-entry and slow-insert gate

Date: 2026-05-17

Run:

- Gate run id: `2026-05-17T02-01-42Z`
- Instance: `isaac-phase2-success-l4-r3`
- Instance id: `s1vat3i14`
- Instance type: `g2-standard-4:nvidia-l4:1`
- Recorded cheapest relevant price: L4 `g2-standard-4:nvidia-l4:1` at `$0.85/hr`
- Output dir: `artifacts/evaluations/scripted/2026-05-17T02-14-50Z/`
- Steps requested: `1400`
- Eval timeout: `900s`

Configuration delta from Attempt 56:

- `--insert-xy-tol 0.008`
- `--insert-rot-tol 0.18`
- `--insert-vertical-step 0.010`
- `--insert-abort-grace-steps 50`
- `--insert-abort-xy-tol 0.05`
- `--insert-abort-rot-tol 0.55`

Result:

```json
{
  "final_success_rate": 0.0,
  "success_step": null,
  "final_lateral": 0.001716297585517168,
  "final_axial": 0.20860570669174194,
  "final_rot": 0.7634401321411133,
  "best_lateral": 0.0008446893189102411,
  "best_lateral_step": 345,
  "best_axial": 0.20860570669174194,
  "best_axial_step": 423,
  "best_rot": 0.16883118450641632,
  "best_rot_step": 381,
  "branch_jump_step": 423
}
```

Trace highlights:

```text
step  phase    lat      ax      rot     succ_xy  succ_z  succ_rot  contact  jlim    note
350   descend  0.0019   0.3169  0.2320  1        0       0         0.0487   0.0292  good XY, waiting for stricter rotation
375   insert   0.0053   0.2843  0.1731  0        0       1         0.0968   0.0206  strict insert entry reached
381   insert   0.0033   0.2765  0.1688  1        0       1         0.1319   0.0208  XY and rotation success together, axial still high
400   insert   0.0024   0.2475  0.3610  1        0       0         0.1727   0.1406  orientation drifts after insert
423   insert   0.0017   0.2086  0.7634  1        0       0         0.4160   0.3477  branch jump, stopped
```

Interpretation:

- The stricter entry hypothesis was falsified.
- It did produce a clean moment where XY and rotation were both within success thresholds (`step 381`), but axial error was still `0.2765m`.
- During insertion, rotation diverged quickly even though joint-limit margin was healthy (`jlim=0.3477` at the detected jump).
- This points away from joint-limit saturation and toward the current target-generation/controller path being unsuitable for final constrained insertion.

Decision:

- Stop paid GPU attempts for this controller family.
- Do not keep tuning `insert_rot_tol`, `insert_xy_tol`, vertical step size, or abort grace in isolation.
- Next work should be local until the controller path changes materially.

Next controller direction:

- Replace frame-by-frame Cartesian descent with a cached joint-space insertion segment:
  - first solve/record a stable pre-insert joint posture;
  - then replay a short, bounded joint-space descent segment;
  - keep the contact task and success metrics unchanged.
- Alternative if joint-space replay is too brittle:
  - run a small local/remote sweep over socket pose height and XY placement to find a kinematic sweet spot;
  - document the workspace constraint before attempting another paid success gate.

Cleanup verification:

- Guarded cleanup completed after repeated delete retries while Brev showed the instance as `DELETING`.
- Independent cleanup confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

## Prepared next controller: cached joint-space insertion

Date: 2026-05-17

Local change:

- Added `--insert-descent-mode joint-cache` to `scripts/scripted_agent.py`.
- Added a new guarded wrapper:
  - `scripts/run_phase2_jointcache_gate.sh`
- Extended trace summaries with joint-cache columns:
  - `jcache`
  - `jcache_seed`
  - `jcache_steps`

Why:

- Attempts 56 and 57 showed that repeated Cartesian target generation during final insertion is the wrong layer to keep tuning.
- Attempt 56 got close in axial depth (`best_axial=0.0389m`) but lost orientation/XY stability near contact.
- Attempt 57 showed that stricter insert entry can satisfy XY and rotation together, but the final Cartesian IK insertion still diverges.
- The branch-jump forensics did not point to joint-limit saturation as the primary cause.

Controller design:

- Before insertion, behavior is unchanged:
  - staged XY alignment
  - stateful orientation waypointing
  - optional orientation hold during descent
- At insertion entry, `joint-cache` still uses one local IK solve to seed the insertion direction.
- After that, final insertion is driven by a cached joint-space delta:
  - per-step joint delta bounded by `--joint-cache-step`
  - total deviation from insertion-entry posture bounded by `--joint-cache-total-limit`
  - final command still passes through `--joint-ik-step` and joint-limit margin clamping
- The point is to avoid frame-by-frame Cartesian IK target regeneration while the peg is constrained by contact.

Default next gate:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-jointcache-l4 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_jointcache_gate.sh
```

Default controller args:

```text
--insert-descent-mode joint-cache
--insert-vertical-step 0.030
--joint-cache-step 0.035
--joint-cache-step-scale 1.0
--joint-cache-total-limit 1.0
--insert-abort-grace-steps 30
--insert-abort-xy-tol 0.06
--insert-abort-rot-tol 0.65
```

Expected outcome:

- Useful if it avoids the immediate post-insert orientation divergence seen in Attempt 57.
- Successful if `success_step != null`.
- Failed but informative if axial still stalls above `0.03m`, because that would suggest the next blocker is task geometry/contact rather than IK branch switching.

Local verification:

- `python3 -m py_compile scripts/scripted_agent.py scripts/summarize_scripted_trace.py` passed.

## Attempt 58: cached joint-space insertion

Date: 2026-05-17

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-jointcache-l4-r2 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_jointcache_gate.sh
```

Instance:

- Type: `g2-standard-4:nvidia-l4:1`
- Live price: `$0.85/hr`
- Instance id: `yaw5b4ha3`

Output:

- Gate log: `artifacts/gpu_gate/2026-05-17T05-30-22Z_isaac-phase2-jointcache-l4-r2/gate.log`
- Summary: `artifacts/evaluations/scripted/2026-05-17T05-43-13Z/seed_42.json`
- Trace: `artifacts/evaluations/scripted/2026-05-17T05-43-13Z/seed_42_trace.json`

Result:

```json
{
  "success_step": null,
  "final_success_rate": 0.0,
  "final_lateral": 0.05056338012218475,
  "final_axial": 0.28460294008255005,
  "final_rot": 0.19571426510810852,
  "best_lateral": 0.0013305959291756153,
  "best_lateral_step": 424,
  "best_axial": 0.28460294008255005,
  "best_axial_step": 459,
  "best_rot": 0.19571426510810852,
  "best_rot_step": 459,
  "branch_jump_step": 459
}
```

Trace highlights:

```text
step  phase    lat      ax      rot     jcache  jcache_steps  contact  jlim    note
416   insert   0.0131   0.3575  0.2416  1       1             0.8824   0.1406  joint-cache seeded
422   insert   0.0037   0.3473  0.2439  1       7             0.8648   0.1165  success XY reached
424   insert   0.0013   0.3439  0.2445  1       9             0.8617   0.1084  best lateral
440   insert   0.0234   0.3158  0.2483  1       25            0.8329   0.0440  cached joint direction drifting laterally
459   insert   0.0506   0.2846  0.1957  1       44            0.9990   0.0209  branch jump, stopped
```

Interpretation:

- The cache worked mechanically: `joint_cache_active=True` from insertion entry onward.
- It did not solve the task because the cached joint delta included a lateral component.
- The first few insertion steps improved XY, but replaying the same joint direction carried the tip past the socket center.
- After step 424, lateral error grew from `1.3mm` to `50.6mm` while axial improved only to `0.2846m`.
- This falsifies "one cached joint direction can be replayed through the full insertion" for the current posture.

Cleanup verification:

- Guarded cleanup needed repeated delete retries while Brev reported `DELETING`, `STOPPING`, then briefly `DEPLOYING`.
- Final independent confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

## Prepared next controller: cached insertion with drift recovery

Date: 2026-05-17

Local change:

- Added `scripts/run_phase2_jointcache_recovery_gate.sh`.

Why:

- Attempt 58 showed the useful part of joint-cache is early stable insertion, not long open-loop replay.
- The next gate uses short cached insertion segments and recovers when lateral drift exceeds a tight corridor.

Controller changes relative to Attempt 58:

- Lower per-step joint command:
  - `--joint-ik-step 0.035`
  - `--joint-cache-step 0.020`
  - `--joint-cache-step-scale 0.55`
- Allow deeper motion before joint-limit clamping:
  - `--joint-limit-margin 0.005`
- Reduce vertical insertion step:
  - `--insert-vertical-step 0.020`
- Abort/re-align quickly when insertion drifts laterally:
  - `--insert-abort-xy-tol 0.012`
  - `--insert-abort-grace-steps 2`
- Do not stop immediately on the first branch-jump diagnostic:
  - no `--stop-on-branch-jump`
  - `--branch-jump-xy-tol 0.08`

Next gate:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-jointcache-recovery-l4 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_jointcache_recovery_gate.sh
```

Decision rule:

- If `success_step != null`, stop controller work and preserve the result.
- If axial improves but no success, keep the recovery design and tune only corridor/step values.
- If axial still stalls far above success, stop scripted controller work and move to policy learning or lower-level operational-space control.

## Attempt 59: cached insertion with drift recovery

Date: 2026-05-17

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-jointcache-recovery-l4 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_jointcache_recovery_gate.sh
```

Instance:

- Type: `g2-standard-4:nvidia-l4:1`
- Live price: `$0.85/hr`
- Instance id: `adkcns9fa`

Output:

- Gate log: `artifacts/gpu_gate/2026-05-17T05-54-56Z_isaac-phase2-jointcache-recovery-l4/gate.log`
- Summary: `artifacts/evaluations/scripted/2026-05-17T06-08-13Z/seed_42.json`
- Trace: `artifacts/evaluations/scripted/2026-05-17T06-08-13Z/seed_42_trace.json`

Result:

```json
{
  "success_step": null,
  "final_success_rate": 0.0,
  "final_lateral": 0.012324226088821888,
  "final_axial": 0.04038706421852112,
  "final_rot": 0.2508377134799957,
  "best_lateral": 0.000303548586089164,
  "best_lateral_step": 1034,
  "best_axial": 0.03803670406341553,
  "best_axial_step": 1701,
  "best_rot": 0.05771917477250099,
  "best_rot_step": 896,
  "max_contact_force_magnitude": 13.828883171081543,
  "max_contact_force_magnitude_step": 1534
}
```

Trace highlights:

```text
step  phase   lat      ax      rot     contact  jlim    note
1252  insert  0.0047   0.0460  0.2625  0.34     0.0103  XY inside success tolerance, rotation still high
1325  insert  0.0011   0.0419  0.2519  1.78     0.0000  very good XY, near joint limit
1432  insert  0.0117   0.0394  0.1796  0.20     0.0000  rotation inside tolerance, XY outside
1457  insert  0.0153   0.0389  0.1718  0.18     0.0000  best combined near-success window, still too high and off-center
1534  insert  0.0138   0.0420  0.1742  13.83    0.0002  contact spike while joint limit margin is exhausted
1701  align   0.0205   0.0380  0.2478  0.65     0.0129  best axial value, no simultaneous success
```

Interpretation:

- Recovery fixed the Attempt 58 failure mode. The controller no longer branch-jumped immediately after first alignment.
- Axial error improved from `0.2846m` in Attempt 58 to `0.0380m`, so the next blocker is not the same controller jump.
- No success occurred because the three success gates were never true at the same step:
  `lateral < 0.005`, `axial < 0.008`, `rot < 0.18`.
- The controller repeatedly reached good XY and good rotation separately, but near `axial ~= 0.04m` it hit contact and joint-limit constraints.
- `polish_state` never triggered because the previous polish threshold required `axial < 0.012m`; the rollout never got below `0.038m`.

Cleanup verification:

- Guarded cleanup deleted the instance, then an extra manual delete by id was issued because Brev briefly reported a nonterminal state.
- Final independent confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

## Prepared next controller: pre-seat live-IK polish

Date: 2026-05-17

Local change:

- Added `--joint-cache-live-polish` to `scripts/scripted_agent.py`.
- Added `scripts/run_phase2_preseat_polish_gate.sh`.
- Added the new trace column to `scripts/summarize_scripted_trace.py`.

Why:

- Attempt 59 showed that long joint-cache replay can bring the peg to the near-contact region, but it cannot recover alignment once contact and joint limits appear.
- The next gate keeps joint-cache for the early insertion segment, then switches back to live IK when the pre-seat polish window is reached.
- The polish window is intentionally earlier than the old setting:
  - old: `polish-z-tol=0.012`
  - next: `polish-z-tol=0.055`
- During polish, the controller holds current Z while correcting socket XY and target orientation. If lateral and rotation both enter success tolerances, it resumes final seating.

Next gate:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-preseat-polish-l4 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_preseat_polish_gate.sh
```

Decision rule:

- If `success_step != null`, stop scripted-controller work and preserve the result.
- If it reaches polish but still stalls around `axial ~= 0.04m`, stop burning GPU on controller tuning and change the task geometry/workspace or move to policy learning.
- If it cannot enter polish, revert to a small socket-pose sweep before running more controller attempts.

## Attempt 60: pre-seat live-IK polish gate aborted during Brev create

Date: 2026-05-17

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-preseat-polish-l4 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_preseat_polish_gate.sh
```

Price check:

- The guarded preflight recorded live 24GB/32GB/40GB price tables.
- The selected instance was `g2-standard-4:nvidia-l4:1` at `$0.85/hr`.
- Cheaper non-stoppable Shadeform A6000 rows were visible in manual search, but this guarded path intentionally stayed on the previously validated stoppable GCP L4 route to reduce runtime and cleanup risk.

Result:

- No Isaac runtime was reached.
- No scripted eval ran.
- No `success_step` was measured.
- Brev returned `unexpected EOF` during `create`.
- Despite the create failure, Brev briefly materialized a backend workspace:
  - Name: `isaac-phase2-preseat-polish-l4`
  - ID: `iitajrx7m`
  - State observed by independent query: `STARTING`, then `DELETING`

Cleanup verification:

- The guarded cleanup deleted by name and id.
- Manual cleanup also deleted by id and name while the workspace remained visible.
- Final independent confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Decision:

- Treat this as a Brev provisioning abort, not a controller result.
- Do not mark `scripts/run_phase2_preseat_polish_gate.sh` as validated.
- Given repeated Brev `unexpected EOF -> ghost workspace` behavior, do not keep retrying create loops blindly. The next compute attempt should either use a different provisioning route or start with an explicit support escalation before a longer run.

## Attempt 61: pre-seat live-IK polish gate

Date: 2026-05-17

Command:

```bash
RCA_GATE_PROFILE=cheap \
RCA_GATE_INSTANCE_NAME=isaac-phase2-preseat-polish-l4-r2 \
RCA_GATE_READY_TIMEOUT_SECONDS=900 \
RCA_GATE_BUILD_STUCK_SECONDS=600 \
RCA_GATE_DELETE_TIMEOUT_SECONDS=900 \
RCA_GATE_CREATE_TIMEOUT=600 \
scripts/run_phase2_preseat_polish_gate.sh
```

Instance:

- Type: `g2-standard-4:nvidia-l4:1`
- Live price: `$0.85/hr`
- Instance id: `m9fieygv3`

Output:

- Gate log: `artifacts/gpu_gate/2026-05-17T16-03-22Z_isaac-phase2-preseat-polish-l4-r2/gate.log`
- Summary: `artifacts/evaluations/scripted/2026-05-17T16-19-10Z/seed_42.json`
- Trace: `artifacts/evaluations/scripted/2026-05-17T16-19-10Z/seed_42_trace.json`

Result:

```json
{
  "success_step": null,
  "final_success_rate": 0.0,
  "final_lateral": 0.0005378754576668143,
  "final_axial": 0.15058284997940063,
  "final_rot": 3.1394870281219482,
  "best_lateral": 0.00010433992429170758,
  "best_lateral_step": 2142,
  "best_axial": 0.04934975504875183,
  "best_axial_step": 1317,
  "best_rot": 0.06304673850536346,
  "best_rot_step": 907,
  "max_contact_force_magnitude": 3.346665382385254,
  "max_contact_force_magnitude_step": 174
}
```

Trace highlights:

```text
step  phase    lat      ax      rot     polish  jcache  contact  jlim    note
1230  insert   0.0041   0.0634  0.2838  false   true    0.396    0.0063  near socket, still in joint-cache descent
1240  insert   0.0076   0.0552  0.3179  false   true    0.402    0.0049  about to enter pre-seat polish
1250  polish   0.0030   0.0548  0.3859  true    false   0.340    0.0467  live-polish triggered
1300  polish   0.0036   0.0508  0.7587  true    false   0.106    0.0717  XY good, rotation diverging
1317  polish   0.0075   0.0493  0.8695  true    false   0.734    0.0916  best axial, no success
1700  polish   0.0014   0.1248  3.1407  true    false   0.290    -       XY excellent, axial/rotation regressed
2199  polish   0.0005   0.1506  3.1395  true    false   0.320    -       final state, no success
```

Interpretation:

- The provisioning path succeeded after `brev refresh`; no `unexpected EOF` occurred.
- Pre-seat polish did trigger at step `1242`, so the new gate is executable.
- The change did not produce success. It improved XY dramatically, but it made orientation diverge toward roughly `pi` radians and axial depth regressed after the polish phase.
- This falsifies the current live-polish design:
  - holding Z while commanding the full target orientation is not stable in this geometry;
  - the controller leaves the useful insertion manifold and ends up centered above the socket but flipped/misaligned.
- The best axial value, `0.0493m`, is worse than Attempt 59's `0.0380m`.

Cleanup verification:

- Artifacts were pulled locally.
- The instance remained visible in `DELETING` for several delete cycles, then disappeared.
- Final independent confirmation:
  - `brev ls instances --all`: `No instances in org NCA-57cf-29515`
  - `brev ls instances --json --all`: `{ "workspaces": null }`

Decision:

- Do not continue tuning pre-seat live-polish in its current form.
- Revert the control idea conceptually: the useful part of Attempt 59 was insertion descent, not free live orientation polish.
- The next controller attempt, if any, should either:
  - keep insertion orientation frozen and only polish XY at current depth, or
  - stop scripted controller tuning and run a small socket-pose/workspace sweep to find a physically reachable successful configuration.
