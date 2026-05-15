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
