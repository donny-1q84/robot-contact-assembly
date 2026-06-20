# AWS Isaac Launchable Runbook

Date prepared: 2026-05-24
Last local update: 2026-06-18

## Current Status - Contact-Smoke Only

This runbook contains historical AWS Launchable operations and old paid-run examples. As of the 2026-06-18 audit, the only allowed paid use of this path before the Phase 2 gate passes is the shortest contact-physics smoke validation:

```bash
./scripts/run_launchable_contact_physics_smoke.sh
```

Before clicking Create or running any paid wrapper, refresh Brev/NVIDIA CLI auth with `scripts/refresh_brev_login.sh`, then run `scripts/paid_compute_preflight.sh` with an explicit budget, conservative EUR/hour estimate, and TTL. For this one allowed pre-gate run, set `RCA_PAID_RUN_PURPOSE=contact_physics_smoke`. Do not run controller probes, BC, RL, or broad scripted evaluations from this runbook until the pulled smoke log has been installed with `scripts/archive_contact_smoke_log.sh` and `python3 scripts/check_phase2_contact_gate.py` reports PASS from the archived smoke log.

2026-06-20 update: two consecutive official AWS Launchable attempts failed before shell access and required repeated delete/stop cleanup. The active local hold file is `docs/brev_launchable_lifecycle_hold.md`; while it exists, `scripts/paid_compute_preflight.sh` blocks new paid creation unless `RCA_ACK_BREV_LIFECYCLE_RISK=1` is set deliberately after confirming Brev service recovery and empty-org cleanup.

Use `scripts/create_brev_lifecycle_incident_bundle.sh` to package support
evidence, and `scripts/check_brev_lifecycle_hold_clearance.sh` before any
human review of the hold. The clearance script is read-only: it confirms the
visible Brev list is empty and paid preflight remains fail-closed on the hold,
but it does not remove the hold file.
If a single retry is deliberately chosen later, run
`scripts/check_launchable_retry_readiness.sh` first. It is read-only and only
returns ready when budget, hourly estimate, TTL, empty-org state, bundle
readiness, and `RCA_ACK_BREV_LIFECYCLE_RISK=1` all pass.

## Why This Path Exists

The normal Brev CLI create path is currently not reliable for this project. The latest post-login probe on 2026-05-24 failed before SSH with a Brev `CreateWorkspace` `unexpected EOF`, so it never reached Isaac, streaming, or port setup.

Brev support recommended the official Isaac Launchable, preferably on AWS. The official `isaac-sim/isaac-launchable` repository says the Launchable provides a browser VS Code instance, Isaac Lab, Isaac Sim, and the Kit App Streaming viewer. The current official README shows Isaac Lab 2.3 and Isaac Sim 5.1, with `/workspace/isaaclab` as the Isaac Lab path and `/isaac-sim/runheadless.sh` for Isaac Sim.

Official references:

- https://brev.nvidia.com/launchable/deploy/now?launchableID=env-35JP2ywERLgqtD0b0MIeK1HnF46
- https://github.com/isaac-sim/isaac-launchable

## Cost Guard

Do not use this path casually. Brev instances are pay-by-the-hour and stopped instances may still have storage charges. Use AWS only when there is an explicit budget and a manual deletion path, because the 2026-05-26 `rca-jointpos-rotatedesc-vm` run exhausted the org credits after Brev CLI auth expired before copy/delete. Stop the Launchable instance immediately after the smoke or evaluation, and verify deletion from the UI if the CLI is not authenticated.

Latest observed AWS prices:

```text
2026-05-24:
g6e.4xlarge / NVIDIA L40S / 16 CPUs / 128 GiB RAM / 256 GiB disk
Brev UI price: $3.61-$3.64/hr observed across two launches

2026-05-26:
g6e.xlarge / NVIDIA L40S
Used for rca-jointpos-rotatedesc-vm / r2dvf19yi; smoke and two short probes completed,
but CLI auth expired before copy/delete and credits were exhausted afterward.

2026-06-07:
g6e.xlarge / NVIDIA L40S
Used for rca-reachable-approach-vm / 8bk6tylx0. Results and diagnostics were copied locally,
the instance was deleted, and the final CLI check returned {"workspaces": null}.
```

Before launching, first run the read-only safety snapshot:

```bash
cd "/Volumes/Extreme Pro/Projects/robot-contact-assembly"
./scripts/brev_paid_safety_status.sh
```

It must show `visible_instances=0` unless a paid job is intentionally active.
Then verify locally through the paid preflight. If
`docs/brev_launchable_lifecycle_hold.md` exists, this command is expected to
block unless a deliberate one-run lifecycle-risk acknowledgement is supplied:

```bash
cd "/Volumes/Extreme Pro/Projects/robot-contact-assembly"
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_PAID_MAX_MINUTES=60 \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
  ./scripts/paid_compute_preflight.sh
```

Expected empty state:

```text
No instances in org NCA-57cf-29515
{"workspaces": null}
```

The local Brev create wrappers intentionally fail closed unless the paid-create acknowledgement and preflight variables are set:

```bash
export RCA_ALLOW_PAID_BREV_CREATE=1
export RCA_BREV_CREDITS_VERIFIED=1
export RCA_PAID_BUDGET_EUR=<explicit-budget>
export RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour>
export RCA_PAID_MAX_MINUTES=60
export RCA_PAID_RUN_PURPOSE=contact_physics_smoke
```

Only set them after verifying the credit balance in the Brev UI, converting the UI/provider price to a conservative EUR/hour estimate, and keeping the Brev UI open for manual deletion if CLI auth fails. The Brev CLI currently has no read-only balance command, so `RCA_BREV_CREDITS_VERIFIED=1` is the manual UI-check marker. The preflight itself confirms Brev CLI auth, visible empty-org state, and that the estimated max cost fits inside the budget.

Before any new paid UI Launchable, also start a local watchdog. If the Launchable name/id is already known, monitor that target:

```bash
cd "/Volumes/Extreme Pro/Projects/robot-contact-assembly"
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
RCA_BREV_WATCHDOG_INSTANCE_NAME=<launchable-instance-name> \
RCA_BREV_WATCHDOG_MAX_MINUTES=60 \
scripts/brev_paid_run_watchdog.sh
```

If the UI will generate the name and this org is dedicated to the project, start org-scope monitoring before clicking Create:

```bash
cd "/Volumes/Extreme Pro/Projects/robot-contact-assembly"
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
RCA_BREV_WATCHDOG_MAX_MINUTES=60 \
scripts/start_brev_ui_launchable_watchdog.sh
```

This does not make dropped login harmless: when the CLI is logged out, no local script can delete through the CLI. It does make the failure immediate and visible by writing `artifacts/brev_paid_runs/.../manual_delete_required.txt` and sending a macOS notification pointing to the Dashboard deletion page.

## Prepare Upload Bundle

For the current contact-smoke path, prefer the guarded preparation command:

```bash
cd "/Volumes/Extreme Pro/Projects/robot-contact-assembly"
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_BREV_CREDITS_VERIFIED=1 \
  ./scripts/prepare_contact_smoke_run.sh
```

It runs local quality, paid preflight, and then writes the exact contact-smoke
bundle path to upload. If you only need a manual bundle without paid preflight,
run the lower-level helper directly:

```bash
cd "/Volumes/Extreme Pro/Projects/robot-contact-assembly"
./scripts/create_launchable_bundle.sh
```

This writes a tarball under:

```text
artifacts/launchable/
```

The bundle contains the current working tree plus the required preload trace:

```text
artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json
```

It also writes a source-evidence manifest into the bundled project:

```text
/workspace/robot-contact-assembly/.rca_launchable_source_manifest.txt
```

Because the bundle intentionally excludes `.git/`, the contact-smoke gate uses
this manifest to trace the archived PASS log back to the local source commit and
dirty-tree state. A `git_head=unknown` log without this manifest is not accepted
as sufficient evidence.

## Launch

1. Open the Launchable link above.
2. Use the Brev UI, not the failing local CLI create path.
3. Choose AWS compute. Start with the cheapest AWS GPU that still satisfies Isaac Sim/Launchable requirements and has enough disk. The previous visible fallback candidate was `g6e.xlarge` L40S 45 GB at about `$2.23/hr`, but re-check live pricing in the UI.
4. Wait until Brev shows the instance running, built, and the setup script completed.
5. Open the secure VS Code link.

## Restore Project Inside Launchable

In the Launchable VS Code terminal, upload the bundle tarball and extract it:

```bash
cd /workspace
tar -xzf robot-contact-assembly-launchable-*.tar.gz -C /workspace
cd /workspace/robot-contact-assembly
```

If using `git clone` instead of the bundle, also upload/copy the preload trace to:

```text
/workspace/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json
```

## Headless Smoke

Run a short non-streaming smoke first:

```bash
cd /workspace/robot-contact-assembly
./scripts/run_launchable_headless_smoke.sh
```

This only installs the local task extension into `/isaac-sim/python.sh`, verifies `RCA-*` gym task registration, and runs a 10-step headless zero-agent rollout.

The smoke now defaults `RCA_FORCE_APP_LAUNCHER=1` to avoid probing older launcher helpers before `SimulationApp` starts in the Isaac Lab 2.3 Launchable image. It prints explicit `env.reset()` and per-step progress, and passes `--watchdog_seconds`, defaulting to `180` seconds through `RCA_LAUNCHABLE_SMOKE_WATCHDOG_SECONDS`, so a repeated hang should dump a Python traceback and exit instead of silently consuming the whole session.

If this fails due Isaac Lab 2.3 API drift, stop and patch compatibility locally before running the expensive contact evaluation.

After the zero-agent smoke passes, run the contact-physics smoke gate. This is
mandatory after the 2026-06-11 audit (the kinematic peg/wall task had no real
contact physics) and must pass before ANY paid controller/BC/RL run:

```bash
./scripts/run_launchable_contact_physics_smoke.sh
```

It presses the welded dynamic peg onto a guide-wall top with the Abs IK play
task (2 envs to catch per-env joint wiring failures) and marker-checks:
`reset-joints`, `attach`, `free-space`, `free-space-reanchored`,
`press-force`, `press-tracking`, `press-blocked`, `press-no-clip`, `release`,
`joint-integrity`, then appends `[contact-smoke] completed: contact physics is
real` after the wrapper has verified the log. A FAIL marker means the
fixed-joint attachment, peg-wall collision response, or per-env smoke control
is still wrong; stop and fix locally instead of launching any further paid work.

When invoking this through `brev exec`, do not let an expected fail-closed
nonzero exit propagate to the Brev CLI. On 2026-06-20, `brev exec` reconnected
after a contact-smoke failure and repeated the same remote command once. Use an
outer shell that records the smoke exit code in the log or a sidecar file but
returns zero to the CLI, then validate the pulled log locally:

```bash
docker exec vscode bash -lc 'cd /workspace/robot-contact-assembly; ./scripts/run_launchable_contact_physics_smoke.sh; echo smoke_exit=$?' || true
```

The archived `artifacts/launchable_logs/contact_physics_smoke.log` must include
either a non-`unknown` `git_head` or the bundle source manifest block emitted by
the wrapper. Without that source evidence, the local phase gate remains blocked
even if the physical PASS markers are present.

The wrapper also appends the editable task-extension install output to the same
log. If that install step fails, stop there and fix the runtime/package issue;
do not continue into controller probes or policy work.

After the smoke finishes, pull only the smoke log and immediately validate it:

```bash
./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly
```

This is the preferred pre-gate pullback path because it explicitly uses the
`contact_physics_smoke` remote-operation purpose and then runs
`scripts/archive_contact_smoke_log.sh` against the pulled file.

Plain Brev AWS VM / Isaac Sim 6.0.0-dev2 note from 2026-06-07:

```bash
# inside isaac-runner, as root
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth x11-xserver-utils x11-utils
pkill -TERM -x Xvfb 2>/dev/null || true
nohup Xvfb :99 -screen 0 1280x720x24 -ac -extension GLX >/tmp/rca-xvfb.log 2>&1 &
DISPLAY=:99 xdpyinfo | head
```

Use `-extension GLX`; without it, Xvfb segfaulted in NVIDIA EGL/GBM initialization. Then inject the display into remote container commands:

```bash
RCA_REMOTE_DOCKER_EXEC_ENV='-u root -e DISPLAY=:99' \
  bash ./scripts/run_remote_smoke_test.sh <env-name> /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
```

For direct probe execution:

```bash
sudo docker exec -u root -e DISPLAY=:99 -e RCA_FORCE_APP_LAUNCHER=1 isaac-runner bash -lc \
  'cd /workspace/robot-contact-assembly && bash scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh'
```

Known results from 2026-05-24:

```text
first instance:
  instance: isaac-launchable-13e30f / c7hq6t3hp
  provider: AWS
  machine: g6e.4xlarge, NVIDIA L40S
  bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T14-53-58Z.tar.gz
  diagnostics: artifacts/launchable_logs/rca-launchable-diagnostics-20260524.tar.gz

second instance:
  instance: isaac-launchable-5c7e93 / kkekc4hjq
  provider: AWS
  machine: g6e.4xlarge, NVIDIA L40S
  uploaded bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-18-29Z.tar.gz
  latest local bundle after final fixes/docs: artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-51-46Z.tar.gz
  latest local bundle after fresh-preload workflow: artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-06-50Z.tar.gz
  latest local bundle after fresh-preload guardrails: artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-13-11Z.tar.gz
  latest local bundle after historical-replay fail-closed guard: artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-14-14Z.tar.gz
  latest local bundle after Abs IK probe summary wiring: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T09-24-27Z.tar.gz
  latest local bundle after root-frame Abs IK action fix: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-29-24Z.tar.gz
  latest local bundle after Abs IK orientation-current diagnostic wiring: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
  latest local bundle after native MDP arm-joint-limit trace wiring: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T13-27-35Z.tar.gz
  diagnostics: artifacts/launchable_logs/rca-launchable-diagnostics-kkekc4hjq.tar.gz
  post-delete check: no instances in org NCA-57cf-29515, JSON {"workspaces": null}
```

The first official Launchable reached `Running / Built / script Completed`, and `nvidia-smi` worked inside the `vscode` container. It exposed Isaac Lab 2.3 compatibility problems in the RCA code and smoke harness. After patching those issues locally and syncing them to the second Launchable, the marker-checked smoke passed:

```text
task: RCA-PegInHole-Franka-JointPos-Contact-Play-v0
steps: 10
markers:
  Environment reset completed
  Zero-agent step 10/10 completed
  Zero agent smoke test completed
log:
  launchable_logs/headless_smoke_marker_checked.log
```

Compatibility fixes needed for Isaac Lab 2.3 / Isaac Sim 5.1:

- force Launchable scripts through `isaaclab.app.AppLauncher` and `parse_env_cfg`;
- change the RCA per-step peg sync interval from `0.0s` to `sim.dt * decimation`;
- avoid calling `warp.to_torch()` on Isaac Lab data fields that are already `torch.Tensor`;
- handle missing `SimulationContext.visualizers` in headless smoke;
- ignore `SystemExit` during Isaac shutdown so original Python exceptions remain visible;
- make the Launchable shell scripts verify reset/step/summary markers instead of trusting a zero exit code.

The second instance was deleted after diagnostics were pulled.

## Diagnostic Matrix

If the smoke fails or hangs, run the compact matrix instead of guessing:

```bash
cd /workspace/robot-contact-assembly
./scripts/run_launchable_rca_diagnostic_matrix.sh
```

It writes case logs under:

```text
/workspace/artifacts/launchable_diagnostics/
```

The matrix runs:

```text
00_builtin_reach_franka
10_rca_ik_rel_play
20_rca_jointpos_contact_play
21_rca_jointpos_contact_play_no_interval
```

Interpretation:

- if `00_builtin_reach_franka` fails, the Launchable Isaac runtime itself is unhealthy;
- if built-in passes but RCA IK fails, the RCA scene/task registration path is the issue;
- if RCA IK passes but JointPos contact fails, focus on contact observations/action config;
- if `20` fails but `21` passes, the per-step peg sync interval path is the likely culprit.

Known result from the second AWS attempt:

```text
run: 2026-05-24T16-46-41Z_rca_smoke_matrix
00_builtin_reach_franka: 0
10_rca_ik_rel_play: 0
20_rca_jointpos_contact_play: 0
21_rca_jointpos_contact_play_no_interval: 0
```

The RCA per-step peg sync interval was changed after the first AWS attempt from `0.0s` to the actual environment-step period `sim.dt * decimation`. That keeps the rigid peg synchronized every environment step while avoiding a zero interval in Isaac Lab's interval event manager.

## Next Robotics Evaluation

Only after the smoke passes:

```bash
cd /workspace/robot-contact-assembly
./scripts/run_launchable_phase2_fresh_preload_direction.sh
```

This runs the safer current evaluation:

```text
task: RCA-PegInHole-Franka-JointPos-Contact-Play-v0
controller: preload-direction
preload trace: generated fresh inside the current Launchable runtime
steps: 400
seed: 42
strict gate: xy<0.005, z<0.045, rot<0.18, contact>=0.5
rot metric: calibrated sign-invariant cylinder-axis error, not full quaternion distance
```

The script performs:

```text
fresh scripted force-aware contact-retention trace
-> scripts/select_preload_handoff_step.py
-> preload-direction eval using the selected fresh handoff step
```

It also has two fail-closed guards:

```text
RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS=1.0
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_LATERAL_DRIFT=0.02
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_AXIAL_DRIFT=0.02
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_ROT_DRIFT=0.25
```

If the fresh scripted handoff is too far from the strict gate, it skips the post-handoff eval. If the selected source handoff does not replay to a similar measured state, it fails the result as replay drift instead of treating it as a controller result.

The result lands under:

```text
/workspace/artifacts/evaluations/contact_handoff_baseline/
```

Do not replay the historical `2026-05-17T23-32-18Z` trace for the next Launchable controller test. That trace was useful under the earlier Isaac runtime path, but it did not reproduce the old near-success handoff under Isaac Lab 2.3 / Isaac Sim 5.1:

```text
historical source step 1543:
  lateral: 0.0052
  axial: 0.0413
  rot: 0.1812
  contact: 0.5298

Launchable replay at source step 1543:
  lateral: 0.2508
  axial: 0.0464
  rot: 2.1423
  contact: 5.6489
```

The legacy historical-replay script now refuses to run unless `RCA_ALLOW_HISTORICAL_PRELOAD_REPLAY=1` is set for an explicit replay-drift diagnostic.

Known result from the second AWS attempt:

```text
run: 2026-05-24T16-44-26Z_preload-direction
success_step: null
handoff_lateral: 0.2508
handoff_axial: 0.0464
handoff_rot: 2.1423
final_lateral: 0.1303
final_axial: 0.0366
final_rot: 2.5794
best_strict_miss_score: 34.9912
near_contact_fraction: 0.0000
max_contact_force_magnitude: 7.5659
```

Interpretation: the Launchable runtime path works, but this particular result is contaminated by historical trace replay drift. The later fresh-preload runs below satisfy the requirement to generate scripted traces in the same Launchable runtime.

Known result from the `isaac-launchable-fb61a7` / `pk2xmabsc` AWS attempt:

```text
final smoke:
  launchable_logs/headless_smoke_final_legacy_convention.log
fresh scripted run:
  evaluations/scripted/2026-05-24T17-55-26Z_fresh-preload
selected handoff:
  step=14
  lateral=0.0049
  axial=0.5937
  rot=2.4654
  strict_miss_score=77.7206
post-handoff eval:
  skipped by fail-closed guard
```

Follow-up diagnostics on the same instance confirmed the current blocker was the scripted handoff controller, not Launchable setup, task registration, or peg sync. Migrating the calibrated geometry constants/helpers to WXYZ did not improve the gate and made the starting geometry worse. Removing `--rotate-before-descend` improved axial movement in one variant but caused large lateral drift.

Axis-aware validation on `2026-05-24` used `isaac-launchable-837c5c` / `e9v2t2tsw` on AWS `g6e.4xlarge` L40S. The Launchable UI created the host, but cloud-init left `/var/lib/cloud/scripts/per-boot/always.sh` and `/var/lib/cloud/scripts/per-instance/instance.sh` empty, causing `Exec format error`; starting the official `isaac-sim/isaac-launchable` compose stack manually restored the expected `vscode`, `web-viewer`, and `nginx` containers. The 10-step smoke passed.

The changed axis-aware path did not pass the guarded handoff gate:

```text
run: 2026-05-24T19-12-05Z_fresh-preload
mode: --orientation-target-mode axis-align-current
selected handoff: step 7, phase align
lateral=0.0082
axial=0.6031
rot=0.9302
strict_miss_score=63.6295
post-handoff eval: skipped by fail-closed guard
```

A second diagnostic on the same instance removed `--rotate-before-descend`. It improved individual minima but did not create a valid handoff:

```text
run: 2026-05-24T19-20-00Z_axis-current-no-rotate
best_lateral=0.0041@11
best_axial=0.0611@1221
best_rot=0.1868@1092
final_lateral=0.4124
final_axial=1.0118
final_rot=1.4474
success_step=null
```

Diagnostics were pulled to `artifacts/launchable_logs/rca-launchable-diagnostics-e9v2t2tsw.tar.gz` and `artifacts/launchable_logs/rca-host-diagnostics-e9v2t2tsw.tar.gz`. The instance was deleted with `brev delete e9v2t2tsw`; SSH became unavailable, the Brev UI showed no environments, and `brev ls` returned `No instances in org NCA-57cf-29515`.

XY-retention validation was completed later on `isaac-launchable-1e19c4` / `1cozht94s`, again using AWS `g6e.4xlarge` L40S. Cloud-init again failed with empty generated scripts, so the official compose stack was started manually. The 10-step smoke passed.

The guarded XY-retention run still failed closed:

```text
run: 2026-05-24T21-14-20Z_fresh-preload
mode: axis-align-current + rotate/descend XY retention
selected handoff: step 8, phase align
lateral=0.0065
axial=0.6025
rot=0.9335
strict_miss_score=63.4364
post-handoff eval: skipped by fail-closed guard
rotate_xy_recovery_step_count=1767
rotate_xy_recovery_max_lateral=1.0018
descend_xy_recovery_step_count=122
descend_xy_recovery_max_lateral=0.9774
```

Two live-patched diagnostics changed the joint-IK step limiter. Pure `global` scaling never entered a useful XY gate and was stopped around step `1625`; `after-xy-global` reduced the worst drift to about `0.2m` but still plateaued far outside the `0.012m` recovery target and was stopped around step `1450`. These were diagnostic-only attempts; the wrapper default was restored to component clipping.

Diagnostics were pulled to `artifacts/launchable_logs/rca-launchable-diagnostics-1cozht94s.tar.gz` and `artifacts/launchable_logs/rca-host-diagnostics-1cozht94s.tar.gz`. The instance was deleted with `brev delete 1cozht94s`; subsequent SSH lookup failed, and the Brev UI showed an empty environment list. The CLI list endpoint timed out during the final check.

Current interpretation: the AWS Launchable runtime is healthy enough for short RCA smoke/eval runs, but the old joint-position scripted handoff family is exhausted. Do not run another paid Launchable for `preload-direction`, unchanged nullspace, rotate-descend, or unchanged reachable-approach sweeps.

Known result from `rca-reachable-approach-vm` / `8bk6tylx0` on 2026-06-07:

```text
runtime: plain Brev AWS g6e.xlarge VM with manual isaac-sim/isaac-launchable compose
smoke/runtime: task registration and zero/random/scripted diagnostics passed after Xvfb -extension GLX workaround
probe artifacts: artifacts/launchable_logs/rca-reachable-approach-results-8bk6tylx0.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-8bk6tylx0.txt
cleanup: final Brev CLI check returned {"workspaces": null}

reachable baseline:
  joint_ik_step=0.035, steps=900, success_step=null
  final_axial=0.4215, strict_miss_score=40.3082

reachable faster:
  joint_ik_step=0.12, steps=900, success_step=null
  final_axial=0.3539, strict_miss_score=32.2077

reachable aggressive:
  joint_ik_step=0.30, steps=900, success_step=null
  final_axial=0.2733, strict_miss_score=24.3841

reachable long:
  joint_ik_step=0.30, steps=2000, success_step=null
  best_axial=0.1073@1939
  selected handoff: lateral=0.0012 axial=0.1076 rot=0.2103 contact=0.1056
  strict_miss_score=6.9591
  min_arm_joint_limit_margin=0.0173 at panda_joint4 step 1490
```

Interpretation: reachable-approach fixed the gross XY approach but still failed the strict handoff. Running longer improved depth but consumed `panda_joint4` margin and left contact too low. Do not rerun this wrapper unchanged on paid compute.

The reachable joint-limit guard probe has now run:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_probe.sh
```

This was intentionally not an unchanged reachable rerun. It kept early reachable-approach behavior, then applied a larger joint-limit target margin only during insertion/polish/settle/contact-retention and recorded a late hard guard delta through `max_joint_limit_guard_delta_norm`.

Historical wrapper command used for this campaign. Do not run it now without the current `scripts/paid_compute_preflight.sh` and a passed contact gate:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 ./scripts/run_brev_reachable_guard_probe.sh
```

It starts a target-specific watchdog, uses the `Xvfb :99 -extension GLX` workaround, runs compact smoke before the probe, copies result tarballs/diagnostics to `artifacts/launchable_logs/`, then deletes the instance and polls Brev for cleanup.

First wrapper attempt on 2026-06-07 created `rca-reachable-guard-vm` / `d9nx8jtfj` on AWS `g6e.xlarge`, but failed before smoke/probe because Docker returned `grpc: the client connection is closing` while implicitly pulling `nvcr.io/nvidia/isaac-sim:6.0.0-dev2`. Cleanup completed and the final Brev list returned `{"workspaces": null}`. The runtime installer now explicitly retries `sudo docker pull "${ISAAC_SIM_IMAGE}"` three times before `docker run`.

Second wrapper attempt on 2026-06-07 created `rca-reachable-guard-vm` / `avejl6fqo` on AWS `g6e.xlarge`, passed smoke, ran `2026-06-07T21-59-30Z_jointpos-reachable-jointlimit-guard-probe`, copied artifacts, deleted the instance, and the final Brev list returned `{"workspaces": null}`.

```text
artifact: artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-vm-2026-06-07T21-46-17Z.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-vm-2026-06-07T21-46-17Z.txt
result: failed closed
selected handoff: step=1584 lateral=0.0012 axial=0.1989 rot=0.3361 contact=0.0473
strict_miss_score: 17.4066
final: lateral=0.0013 axial=0.1958 rot=0.3693
best_axial=0.1958@1599
min_arm_joint_limit_margin=0.1542 at panda_joint4 step 1492
max_joint_limit_guard_delta_norm=0.0154@1493
```

Interpretation: the strong guard fixed the immediate joint-limit risk, improving the limiting `panda_joint4` margin from `0.0173` to `0.1542`, but it overconstrained insertion and axial progress stalled around `0.196m`. Do not rerun the strong guard unchanged.

The tuned guard variant has now been run:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh
```

For a paid Brev AWS VM, reuse the same wrapper and cleanup path:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-tuned-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

It relaxes the late insertion guard (`insert_joint_limit_margin=0.060`, guard activation/gain/step `0.110/0.060/0.040`) and runs 2000 steps. Treat it as a narrow parameter validation, not a broad sweep.

The paid wrapper run on 2026-06-07 created `rca-reachable-guard-tuned-vm` / `hm27ajjsk` on AWS `g6e.xlarge`, passed smoke, ran `2026-06-07T22-31-05Z_jointpos-reachable-jointlimit-guard-tuned-probe`, copied artifacts, deleted the instance, and the final Brev list returned `{"workspaces": null}`. The target-specific watchdog produced one stale `manual_delete_required.txt` after a transient query failure, but the wrapper cleanup completed; `scripts/brev_paid_run_watchdog.sh` now tolerates transient query failures before alerting.

```text
artifact: artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-tuned-vm-2026-06-07T22-18-02Z.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-tuned-vm-2026-06-07T22-18-02Z.txt
result: failed closed
selected handoff: step=1921 lateral=0.0012 axial=0.1463 rot=0.2862 contact=0.0652
strict_miss_score: 11.6256
final: lateral=0.0029 axial=0.1449 rot=0.4466
best_axial=0.1449@1999
min_arm_joint_limit_margin=0.0738 at panda_joint4 step 1503
max_joint_limit_guard_delta_norm=0.0188@1504
```

Interpretation: the tuned guard improved axial progress relative to the strong guard while preserving more joint-limit margin than the unguarded reachable run, but it still did not reach the z/contact/rotation gates. Do not rerun the tuned guard unchanged. The next paid validation should wait for a local implementation that changes insertion posture, phase sequencing, or controller objectives.

The rotation-gated insertion probe was the next local-first candidate:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_rotgated_probe.sh
```

It reuses the tuned guard parameters, disables insert-entry orientation hold, and enables `--insert-rotation-gated-descent` with `insert_descent_rot_tol=0.35`. This pauses Z descent during high-rotation insert windows while continuing to target the socket orientation.

Historical paid Brev AWS command used for validation. Do not rerun this unchanged, and do not run any replacement without the current paid preflight:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-rotgated-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_rotgated_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

First paid rotgated attempt on 2026-06-07/08 created `rca-reachable-guard-rotgated-vm` / `w57uxy94u` on AWS `g6e.xlarge`, passed host GPU setup, repo sync, Isaac Sim 6.0.0-dev2 container startup, Xvfb startup, and runtime registration. It failed before the rotgated probe because the compact smoke stayed in `zero_agent.py --steps 3` for about 9 minutes with no artifact progress. No probe result tarball was produced. The wrapper deleted the instance, final wrapper output returned `{"workspaces": null}`, an independent CLI check also returned `{"workspaces": null}`, and the watchdog logged `target disappeared; cleanup confirmed`.

The failure exposed a smoke harness bug: `run_brev_reachable_guard_probe.sh` passed `--watchdog_seconds 60` only as the scripted-smoke extra argument, so zero/random smoke had no bounded runtime. `scripts/run_remote_smoke_test.sh` now gives zero, random, and scripted smoke a default `RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300` plus an outer `timeout` of watchdog + 120 seconds. `scripts/random_agent.py` now supports `--watchdog_seconds`, and the paid wrapper no longer passes the old scripted-only watchdog argument.

Second paid rotgated attempt on 2026-06-08 created `rca-reachable-guard-rotgated2-vm` / `6nuie4sss` on AWS `g6e.xlarge`, passed the hardened compact smoke, ran `2026-06-07T23-47-57Z_jointpos-reachable-jointlimit-guard-rotgated-probe`, copied artifacts, deleted the instance, and final wrapper plus repeated independent Brev CLI checks returned `{"workspaces": null}`. The wrapper emitted one stale manual-cleanup warning during a delete/list race, but the final state was confirmed empty.

```text
artifact: artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotgated2-vm-2026-06-07T23-35-59Z.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-rotgated2-vm-2026-06-07T23-35-59Z.txt
result: failed closed
selected handoff: step=2144 phase=insert-rot-recover lateral=0.0010 axial=0.1711 rot=0.3537 contact=0.0934
strict_miss_score: 14.7524
strict_miss_components: axial=12.6084 contact=0.4066 lateral=0 rot=1.7374
final: lateral=0.0007 axial=0.1708 rot=0.5107
best_axial=0.1708@2199
min_arm_joint_limit_margin=0.3923 at panda_joint4 step 2095
insert_rotation_gate_step_count=1034 first_step=177 last_step=2199
max_joint_limit_guard_delta_norm=0.0
max_joint_limit_nullspace_delta_norm=0.0
```

Interpretation: this version preserved joint-limit margin much better than the tuned guard (`0.3923rad` vs `0.0738rad`) but made insertion worse (`best_axial/final_axial=0.1708m` vs `0.1449m`) and raised strict miss (`14.7524` vs `11.6256`). The hard rotation gate stayed active for 1034 of 2200 steps, so it protected XY/posture by over-freezing Z descent. Do not rerun this rotation-gated probe unchanged. The next paid validation should wait for a local implementation with softer insertion progress, for example bounded descent during rotation recovery, a minimum descent budget per rotation window, or an explicit staged depth schedule.

Soft-gated follow-up prepared on 2026-06-08:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh
```

`scripts/scripted_agent.py` now supports `--insert-rotation-gate-descent-scale` and `--insert-rotation-gate-min-descent-step`. Defaults preserve the original hard gate (`scale=0.0`). The soft-gated wrapper uses `scale=0.25`, `min_descent_step=0.002`, `insert_descent_rot_tol=0.35`, `hold_orientation_during_insert=0`, and `steps=2400`.

Historical paid Brev AWS command used for the validation. Empty-org checking is now handled by `scripts/paid_compute_preflight.sh`; do not rerun this unchanged:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-softgated-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

Paid softgated validation on 2026-06-08 created `rca-reachable-guard-softgated-vm` / `hqgphjyta` on AWS `g6e.xlarge`, passed runtime setup and compact smoke, ran `2026-06-08T00-30-27Z_jointpos-reachable-jointlimit-guard-softgated-probe`, copied artifacts, deleted the instance, and final wrapper plus independent Brev CLI checks returned `{"workspaces": null}`.

```text
artifact: artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-softgated-vm-2026-06-08T00-16-12Z.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-softgated-vm-2026-06-08T00-16-12Z.txt
result: failed closed
selected handoff: step=1443 phase=insert lateral=0.00323 axial=0.04343 rot=0.28758 contact=0.69435
strict_miss_score: 1.07584
strict_miss_components: axial=0 contact=0 lateral=0 rot=1.07584
final: lateral=0.01204 axial=0.04058 rot=0.33186
best_axial=0.03333@2322
min_arm_joint_limit_margin=0.10353 at panda_joint4 step 2328
insert_rotation_gate_step_count=1228 first_step=177 last_step=2321 max_rot=0.5180
gate scale=0.25 min_descent_step=0.002 max_allowed_descent=0.0050
ready_counts: xy=1219 z=904 rot=17 strict=0 contact=949
```

Interpretation at the time: this was the closest Launchable probe. The soft gate solved the depth stall and selected a handoff inside XY, Z, and contact gates; it failed only rotation (`0.2876rad` vs `0.18rad`), with strict miss `1.0758` just above the `1.0` fail-closed guard. Do not rerun the same softgated wrapper unchanged. This recommendation was superseded by the depth-aware rotation polish validation below, which preserved XY/Z but still failed rotation.

Latest local bundle after soft-gated insertion wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-softgated-2026-06-08.tar.gz
```

Depth-aware rotation polish follow-up prepared on 2026-06-08:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_rotpolish_probe.sh
```

`scripts/scripted_agent.py` now supports `--depth-rotation-polish` plus entry/exit tolerances. The wrapper keeps the soft-gated insertion setup, enters rotation polish after XY/Z/contact readiness (`xy<0.006`, `z<0.050`, `contact>=0.5`), holds socket XY, applies `0.001m` preload, targets socket orientation, and uses `--depth-rotation-polish-rot-step 0.035`. It exits if XY exceeds `0.012m` or axial exceeds `0.060m`.

Historical paid Brev AWS command for that validation. It is not a current next step; any future command must pass `scripts/paid_compute_preflight.sh` first:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-rotpolish-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_rotpolish_probe.sh \
RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES=75 \
RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300 \
RCA_REMOTE_SMOKE_TIMEOUT_SECONDS=420 \
./scripts/run_brev_reachable_guard_probe.sh
```

Success criteria: enter `depth-rot-polish`, keep selected lateral/axial inside strict gates, and reduce selected or final rotation below `0.18rad`. If the run fails closed, inspect `depth_rotation_polish_step_count`, `depth_rotation_polish_max_lateral`, `depth_rotation_polish_min_axial`, and tail `phase_counts` before changing thresholds. Do not rerun the same softgated wrapper unchanged.

Paid rotpolish validation on 2026-06-08 created `rca-reachable-guard-rotpolish-vm` / `xvkzygbsw` on AWS `g6e.xlarge`, passed runtime setup and compact smoke, ran `2026-06-08T04-37-01Z_jointpos-reachable-jointlimit-guard-rotpolish-probe`, copied artifacts, deleted the instance, and final wrapper plus independent Brev CLI checks returned `{"workspaces": null}`.

```text
artifact: artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.txt
status: fail_closed
selected handoff: step=1386 phase=insert lateral=0.002079 axial=0.044687 rot=0.326000 contact=1.451769 strict_miss=1.460000
final: lateral=0.002581 axial=0.045102 rot=0.352941 success_rate=0.0
depth-rot-polish: active_steps=615 first_step=1311 last_step=2599 max_lateral=0.004365 min_axial=0.044687 max_rot=0.526121 rot_step=0.035
tail: lateral=0.002437 axial=0.052236 rot=0.283574 contact=0.208385 phase_counts={insert:44, depth-rot-polish:6}
limiter: panda_joint4 min_margin=0.100994 at step 2212
diagnosis: tail post-action movement makes little progress along the requested XY command
```

Interpretation: the state machine worked and preserved late XY/depth better than the plain soft-gated run, but it did not solve the rotation gate. Selected/final rotation regressed relative to soft-gated (`0.3260/0.3529` vs `0.2876/0.3319`), and strict miss increased to `1.46`. Do not rerun this wrapper unchanged. Next work should be local-first: replace full-target late-contact rotation polish with a less oscillatory repair that adapts rotation step/target to contact and depth stability.

Adaptive rotpolish follow-up prepared locally after that result:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh
```

This wrapper keeps the soft-gated insertion setup but changes depth polish to `--depth-rotation-polish-orientation-mode stateful-waypoint`, lowers the rotation step to `0.012rad`, lowers preload to `0.0005m`, tightens XY/Z exits to `0.010m`/`0.055m`, and exits polish if contact falls below `0.30`. The purpose is to prevent the previous target-orientation polish from repeatedly cycling between insertion and polish while rotation drifts worse.

Historical paid Brev AWS command for this short candidate validation. It is not a current next step; any future command must pass `scripts/paid_compute_preflight.sh` first:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-adaptive-rotpolish-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh \
RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES=80 \
RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300 \
RCA_REMOTE_SMOKE_TIMEOUT_SECONDS=420 \
./scripts/run_brev_reachable_guard_probe.sh
```

Success criteria: stateful depth polish should activate, keep selected XY/Z inside strict gates, and reduce selected/final rotation materially below the prior rotpolish run (`0.3260/0.3529`), ideally below `0.18rad`. If the run fails closed, inspect `depth_rotation_polish_command_valid`, contact-exit timing, and tail `phase_counts` before changing thresholds. Do not run this as a sweep.

Paid adaptive rotpolish validation on 2026-06-09 created `rca-reachable-guard-adaptive-rotpolish-vm` / `evzxs5mnd` on AWS `g6e.xlarge`, passed runtime setup and compact smoke, ran `2026-06-09T05-30-44Z_jointpos-reachable-jointlimit-guard-adaptive-rotpolish-probe`, copied artifacts, deleted the instance, and final wrapper plus independent Brev CLI checks returned `{"workspaces": null}`.

```text
artifact: artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.txt
status: fail_closed
selected handoff: step=1415 phase=insert lateral=0.002064 axial=0.044518 rot=0.320708 contact=1.847413 strict_miss=1.407076
final: lateral=0.002561 axial=0.045312 rot=0.366785 success_rate=0.0
depth-rot-polish: active_steps=863 first_step=1311 last_step=2999 max_lateral=0.004139 min_axial=0.044509 max_rot=0.506800 rot_step=0.012 orientation_mode=stateful-waypoint exit_contact_min_force=0.30
insert rotation gate: active_steps=1101 first_step=177 last_step=2997 max_rot=0.518001 descent_scale=0.25
tail: lateral=0.002107 axial=0.045669 rot=0.337341 contact=0.468937 phase_counts={depth-rot-polish:30, insert:16, insert-rot-recover:4}
limiter: panda_joint4 min_margin=0.104442 at step 2921
diagnosis: tail post-action movement makes little progress along the requested XY command
```

Interpretation: the adaptive stateful-waypoint mode was active and protected XY/depth, but it did not repair the rotation gate. Compared with target-orientation rotpolish, selected rotation improved only slightly (`0.3207` vs `0.3260`), final rotation worsened (`0.3668` vs `0.3529`), and there were zero strict-ready steps. Do not rerun adaptive rotpolish unchanged. The next useful action is local-first trace analysis around the rotation-ready and depth-polish windows, followed by a real controller change to late-contact orientation targeting or branch selection.

Local trace helper:

```bash
python3 scripts/analyze_rotation_polish_trace.py \
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.tar.gz \
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.tar.gz
```

That helper reports the key difference: the original rotpolish had `25` depth-polish segments with mean length `24.6` and best XY/Z/contact-ready rotation `0.3260`; adaptive rotpolish had `472` depth-polish segments with mean length `1.83` and best XY/Z/contact-ready rotation `0.3207`. Both only reached `rot<0.18` in steps `87-103`, before depth/contact readiness. This makes the next candidate a controller/target change, not another step-size or runtime rerun.

Near-depth rotation-gate candidate prepared locally after that analysis:

```bash
./scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
```

This wrapper inherits the soft-gated insertion behavior, then tightens the insertion rotation gate only when axial error is near the success depth (`z_tol=0.065`, `rot_tol=0.22`, `descent_scale=0.10`, `min_descent_step=0.0005`). The new flags are default-off in `scripts/scripted_agent.py` and are exposed through `scripts/run_launchable_phase2_jointpos_nullspace_probe.sh`, so old archives remain reproducible. It is not GPU-validated yet; if approved, run exactly one short AWS validation with the paid watchdog, then delete and confirm `{"workspaces": null}`.

Latest local bundle after near-depth rotgate wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-neardepth-rotgate-2026-06-09.tar.gz
```

Latest local bundle after documenting the adaptive rotpolish result:

```text
artifacts/launchable/robot-contact-assembly-launchable-adaptive-rotpolish-result-2026-06-09.tar.gz
```

Latest local bundle after adaptive rotpolish wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-adaptive-rotpolish-2026-06-08.tar.gz
```

Latest local bundle after documenting the paid rotpolish result:

```text
artifacts/launchable/robot-contact-assembly-launchable-rotpolish-result-2026-06-08.tar.gz
```

Latest local bundle after depth-aware rotation polish wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-rotpolish-2026-06-08.tar.gz
```

Previous local bundle after rotation-gated probe wiring and smoke watchdog hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T23-35-06Z.tar.gz
```

Previous local bundle after rotation-gated probe wiring only:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-08T00-20-00Z.tar.gz
```

Previous local bundle after tuned guard result documentation and watchdog hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T22-50-00Z.tar.gz
```

Previous local bundle after tuned guard wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T22-17-23Z.tar.gz
```

Previous local bundle after Docker-pull hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T21-45-33Z.tar.gz
```

The Abs IK single-run candidate is:

```bash
./scripts/run_launchable_phase2_absik_handoff_probe.sh
```

This is not a post-handoff policy eval. It probes the Abs IK task (`RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`) and fails closed unless the freshly generated handoff is within `RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS=1.0`. It writes `handoff_selection.json`, `probe_summary.json`, and `tracking_analysis.json`; read the compact probe summary first because it includes strict-miss component contributions, per-axis readiness counts, and the final `pass` / `fail_closed` decision, then read the tracking analysis to see target/command/action/post-action residuals and per-arm-joint limit margins. The wrapper explicitly sends native 7D absolute MDP actions in robot root frame via `--mdp-abs-action-frame root`, matching Isaac Lab's `DifferentialInverseKinematicsAction` frame convention. It also supports a focused initial-posture diagnostic with `RCA_LAUNCHABLE_INITIAL_JOINT_POS`, for example `RCA_LAUNCHABLE_INITIAL_JOINT_POS=panda_joint4=-2.6`. Run it only after the standard Launchable smoke, and delete the instance immediately after diagnostics are pulled.

Known result from `isaac-launchable-4a2c79` / `ij912di64` on 2026-05-25:

```text
smoke: passed
absik probe run: 2026-05-25T09-44-02Z_absik-handoff-probe
decision: fail_closed
selected handoff: step 319, phase reach
lateral=0.1112
axial=0.0171
rot=0.6220
contact=4.9495
strict_miss_score=15.0390
probe_summary: artifacts/launchable_logs/rca-absik-probe-results-ij912di64.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-ij912di64.tar.gz
cleanup: final CLI checks showed no instances and JSON {"workspaces": null}
```

Interpretation: Abs IK reached depth/contact but never reached XY or rotation readiness. It remained in `reach` for the whole 320-step window, and best lateral was at the final step. Follow-up trace review found this run used the old world-frame absolute action write path even though Isaac Lab's native action term computes current pose and Jacobian in robot root frame. The local wrapper default was changed to 1200 steps and now explicitly uses the root-frame action path; do not rerun the 320-step/world-frame probe unchanged.

Known result from the root-frame rerun on `isaac-launchable-fdfaba` / `ez3iyhmlw` on 2026-05-25:

```text
smoke: passed
absik probe run: 2026-05-25T12-47-17Z_absik-handoff-probe
mdp_abs_action_frame: root
decision: fail_closed
selected handoff: step 330, phase reach
lateral=0.1110
axial=0.0172
rot=0.6225
contact=4.9089
strict_miss_score=15.0255
final_lateral=0.0578
final_axial=0.0286
final_rot=1.5049
success_step=null
xy_ready_step_count=0
rot_ready_step_count=0
probe_summary: artifacts/launchable_logs/rca-root-absik-probe-results-ez3iyhmlw.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-ez3iyhmlw.tar.gz
cleanup: delete requested by name and id; Brev UI confirmed DELETING at $0.00/hr, and final CLI check returned {"workspaces": null}
```

Interpretation: the root-frame action fix is correct but not sufficient. The probe still never produced an acceptable handoff, so the next useful work should be local-first controller/action-semantics investigation, not another unchanged paid Launchable rerun.

Orientation-current diagnostic:

```bash
RCA_LAUNCHABLE_MDP_ABS_ORIENTATION_COMMAND_MODE=current \
  ./scripts/run_launchable_phase2_absik_handoff_probe.sh
```

This preserves the native 7D absolute MDP action interface but sends the measured current quaternion instead of the scripted target quaternion, after which the command is still converted to robot root frame. Treat it as a position-only XY diagnostic: it is expected to fail the strict rotation gate, but it should show whether XY can converge when orientation tracking is removed.

Known result from `isaac-launchable-18d403` / `v8g5gmij4` on 2026-05-25:

```text
smoke: passed
absik probe run: 2026-05-25T13-17-53Z_absik-handoff-probe
mdp_abs_action_frame: root
mdp_abs_orientation_command_mode: current
decision: fail_closed
selected handoff: step 325, phase reach
lateral=0.1111
axial=0.0172
rot=0.6251
contact=4.9233
strict_miss_score=15.0579
best_lateral=0.0578@638
final_lateral=0.0578
xy_ready_step_count=0
rot_ready_step_count=0
probe_summary: artifacts/launchable_logs/rca-absik-current-probe-results-v8g5gmij4.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v8g5gmij4.tar.gz
cleanup: delete requested by name and id; final CLI check returned no instances and {"workspaces": null}
```

Interpretation: holding orientation current did not improve XY convergence. Do not rerun either Abs IK waypoint probe unchanged; move next to target/action-frame geometry, body offset convention, collision/contact diagnosis, or a different controller/policy formulation.

After this run, `scripts/scripted_agent.py` was instrumented to trace seven-arm-joint state and joint-limit margins for native MDP Abs IK rollouts. `scripts/analyze_absik_probe_trace.py` was also added and run locally on both root-frame artifacts. It found the same waypoint fixed point in both traces: inferred `abs_pos_step=0.0300m`, tail `command_to_post_action_xy≈0.0315m`, tail `target_to_command_y≈-0.027m`, and tail `post_action_step_delta_xy≈0`. The follow-up paid Abs IK diagnostic used full target commands:

```bash
RCA_LAUNCHABLE_ABS_CONTROL_MODE=target \
  RCA_LAUNCHABLE_SCRIPTED_STEPS=500 \
  RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
  ./scripts/run_launchable_phase2_absik_handoff_probe.sh
```

Use `RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1` when running through `brev exec`; otherwise the expected fail-closed nonzero exit can be retried by the Brev CLI.

Known result from `rca-absik-target-vm` / `6siwq7a2t` on 2026-05-25:

```text
runtime: plain Brev AWS g6e.4xlarge VM with manual isaac-sim/isaac-launchable compose
why not launchable CLI: brev create --launchable still failed with lifecycle script is empty
smoke: passed
absik probe run: 2026-05-25T15-22-37Z_absik-handoff-probe
abs_control_mode: target
mdp_abs_action_frame: root
decision: fail_closed
selected handoff: step 23, phase reach
lateral=0.1067
axial=0.0110
rot=0.7833
contact=1.8385
strict_miss_score=16.2003
best_lateral=0.0556@276
best_axial=0.0003@18
best_rot=0.7833@23
final_lateral=0.0556
final_axial=0.0277
final_rot=1.5167
min_arm_joint_limit_margin=-0.00023@103
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.0556, post_action_step_delta_xy≈0
joint-limit analysis: limiting_joint=panda_joint4, global_min=-0.0002255@103, tail_mean_margin≈2.2e-6, tail limiting_joint_counts={panda_joint4: 50}
probe artifacts: artifacts/launchable_logs/rca-absik-target-probe-results-6siwq7a2t.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-6siwq7a2t.tar.gz
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: full target commands remove the waypoint short-command issue, but the action-frame tip still stalls about `5.6cm` outside the socket in XY. Do not rerun target mode unchanged. The local trace analysis now identifies `panda_joint4` as the limiting joint: global minimum margin `-0.0002255` at step `103`, within `1e-4` for all 500 samples, and the limiting joint throughout the last 50 samples. Next inspect native IK tracking under `panda_joint4` saturation, contact/collision constraints, and controller limits locally before another paid run. The bundle used for this diagnostic is `artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T15-05-37Z.tar.gz`; the latest bundle after strengthening the no-wall-collision diagnostic is `artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz`.

Known result from `rca-absik-j4init-vm` / `v0w2i1mp2` on 2026-05-25:

```text
runtime: plain Brev AWS g6e.4xlarge VM with manual isaac-sim/isaac-launchable compose
smoke: passed
absik probe run: 2026-05-25T17-01-54Z_absik-handoff-probe
abs_control_mode: target
initial_joint_pos_overrides: panda_joint4=-2.6
decision: fail_closed
selected handoff: step 15, phase reach
lateral=0.1334
axial=0.0350
rot=1.2837
contact=3.2904
strict_miss_score=23.8804
best_lateral=0.1184@403
best_axial=0.0230@403
best_rot=1.1633@0
final_lateral=0.1185
final_axial=0.0230
final_rot=1.4629
xy_ready_step_count=0
rot_ready_step_count=0
pre-step global limit: panda_joint6 margin=0.0@0
post-step global limit: panda_joint4 margin=3.34e-6@0
joint-limit tail: limiting_joint_counts={panda_joint4: 50}
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.1185, post_action_step_delta_xy≈5.85e-6
probe artifacts: artifacts/launchable_logs/rca-absik-j4init-probe-results-v0w2i1mp2.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v0w2i1mp2.tar.gz
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: single-joint initial elbow offset is not enough. It immediately returns `panda_joint4` to the lower-limit plateau and makes XY worse than the previous full-target run (`11.8cm` tail residual instead of `5.6cm`). Do not rerun this diagnostic unchanged; next paid validation should only follow a local change that explicitly changes the IK branch, full-arm reset posture, approach target, contact/collision setup, or controller nullspace/joint-limit behavior.

Follow-up contact/collision instrumentation was validated on `rca-absik-nowall-vm` / `11ieede24`. `scripts/scripted_agent.py` has `--disable-socket-wall-collisions`, and this wrapper exposes it through:

```bash
RCA_LAUNCHABLE_ABS_CONTROL_MODE=target \
RCA_LAUNCHABLE_DISABLE_SOCKET_WALL_COLLISIONS=1 \
RCA_LAUNCHABLE_SCRIPTED_STEPS=500 \
RCA_LAUNCHABLE_TIMEOUT_SECONDS=900 \
RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
./scripts/run_launchable_phase2_absik_handoff_probe.sh
```

The first no-wall run only changed the authored collision property and still showed unchanged net contact force, so the flag was strengthened to also park the four guide-wall prims at far-away positions before scene creation. The parked-wall run still failed closed:

```text
runtime: plain Brev AWS g6e.4xlarge VM with manual isaac-sim/isaac-launchable compose
smoke: passed
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz
run: 2026-05-25T18-21-28Z_absik-handoff-probe
decision: fail_closed
selected handoff: step 337, phase reach
lateral=0.0957
axial=0.0086
rot=0.5281
contact=1.8613
strict_miss_score=12.5491
best_lateral=0.0704@129
best_axial=0.0002@322
best_rot=0.5242@340
final_lateral=0.0825
final_axial=0.0255
final_rot=0.7460
xy_ready_step_count=0
rot_ready_step_count=0
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.0825, post_action_step_delta_xy≈1.2e-5
joint-limit analysis: panda_joint4 global_min=-0.0002255@103; tail_mean_margin≈0.1588, tail limiting_joint_counts={panda_joint4: 50}
probe artifacts: artifacts/launchable_logs/rca-absik-nowall-parked-probe-results-11ieede24.tar.gz
cleanup: delete requested by name and id; later CLI polling returned {"workspaces": null}
```

Interpretation: do not spend more paid runs on guide-wall collision variants. Parking the guide walls made XY worse than the full target run (`8.25cm` tail residual instead of `5.56cm`) and did not produce a usable handoff. The persistent contact-force readings come from the peg contact sensor's net force, not a wall-only force channel, so current contact-force magnitude should not be interpreted as socket-wall blockage.

The target-offset Abs IK validation has run. It was useful diagnostically but did not improve true socket alignment:

```text
artifact: artifacts/launchable_logs/rca-absik-target-offset-matrix-results-v2319sjd7.tar.gz
baseline: final_lateral=0.0556, tail true target residual≈0.0556, tail limiting_joint_counts={panda_joint4: 50}
target_y_neg_04: final_lateral=0.0710, tail true target residual≈0.0710, tail limiting_joint_counts={panda_joint4: 50}
target_y_pos_04: final_lateral=0.0778, tail true target residual≈0.0774, tail limiting_joint_counts={panda_joint4: 50}
```

Interpretation: the native Abs IK target path follows the biased command, but simple world-frame target offsets make true socket XY worse. Do not spend another paid run on target offsets or guide-wall collision variants.

The IK solver-method matrix has also run and did not rescue the native Abs IK branch:

```text
artifact: artifacts/launchable_logs/rca-absik-ik-method-matrix-results-h9xqkqowr.tar.gz
dls: final_lateral=0.0556, tail residual≈0.0556, tail limiting_joint_counts={panda_joint4: 50}
pinv: final_lateral=0.0554, tail residual≈0.0554, tail limiting_joint_counts={panda_joint4: 50}
svd: final_lateral=0.0554, tail residual≈0.0554, tail limiting_joint_counts={panda_joint4: 50}
trans: final_lateral=0.1386, tail residual≈0.1386, tail limiting_joint_counts={panda_joint4: 50}
```

Do not spend another paid run on unchanged native Abs IK solver-method variants. The next paid run should first have a genuinely new local implementation, such as explicit joint-limit/nullspace behavior, a full-arm reset/posture search, or a non-native controller formulation. The full-arm reset/posture search is now wired as:

```bash
./scripts/run_launchable_absik_full_arm_posture_matrix.sh
```

The default cases are `baseline`, `ready_mid`, `elbow_open`, `yaw_pos`, and `yaw_neg`. Each case runs the same target-mode fail-closed Abs IK probe while changing only `RCA_LAUNCHABLE_INITIAL_JOINT_POS`, so use it to test whether a complete reset posture can avoid the `panda_joint4` / `panda_joint6` saturation branch before implementing deeper nullspace control.

The full-arm reset/posture matrix has now run and did not rescue native Abs IK:

```text
remote vm: rca-absik-posture-vm / 5sjedqlea
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-full-arm-posture-matrix-2026-05-25.tar.gz
artifact: artifacts/launchable_logs/rca-absik-full-arm-posture-matrix-results-5sjedqlea.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-5sjedqlea.txt
baseline: final_lateral=0.0556, tail residual≈0.0556, tail limiting_joint_counts={panda_joint4: 50}
ready_mid: identical to baseline; final_lateral=0.0556, tail limiting_joint_counts={panda_joint4: 50}
elbow_open: final_lateral=0.2480, final_axial=0.0586, final_rot=0.4168, tail limiting_joint_counts={panda_joint4: 16, panda_joint7: 34}
yaw_pos: final_lateral=0.0818, final_axial=0.0134, final_rot=1.1978, tail limiting_joint_counts={panda_joint4: 50}
yaw_neg: final_lateral=0.3091, final_axial=0.6677, final_rot=1.4626, tail limiting_joint_counts={panda_joint6: 6, panda_joint7: 44}
```

Do not spend another paid run on these coarse initial postures unchanged. `yaw_pos` proved that the joint-limit signature can change without improving true socket XY, and `elbow_open` / `yaw_neg` move the fixed point much farther away. The next paid validation should require a local controller/action implementation that explicitly handles joint limits or nullspace posture, not another reset-only sweep.

That controller/action implementation is wired as a non-native JointPos diagnostic:

```bash
RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
RCA_LAUNCHABLE_SCRIPTED_STEPS=900 \
./scripts/run_launchable_phase2_jointpos_nullspace_probe.sh
```

The probe uses `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`, `--scripted-control-mode joint-ik`, and the new `--joint-limit-nullspace-*` flags. It should only be run after the standard Launchable smoke passes. Treat the expected fail-closed result as diagnostic unless `probe_summary.json` shows strict-miss improvement and `tracking_analysis.json` shows the nullspace term moved the limiting-joint behavior without increasing true socket XY residual.

Known AWS result from `rca-jointpos-nullspace-vm` / `t28in7wiu`:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
bundle: artifacts/launchable/robot-contact-assembly-launchable-jointpos-nullspace-2026-05-26.tar.gz
artifact: artifacts/launchable_logs/rca-jointpos-nullspace-probe-results-t28in7wiu.tar.gz
smoke: passed
probe run: 2026-05-26T05-30-35Z_jointpos-nullspace-probe
result: failed closed
selected_handoff: step 10, lateral=0.00898 axial=0.6344 rot=0.9471
final: lateral=0.0254 axial=0.8910 rot=1.3058 success_step=null
max_joint_limit_nullspace_delta_norm: 0.0
min_arm_joint_limit_margin: 0.3569 at panda_joint4
cleanup: final CLI check returned {"workspaces": null}
```

Do not run the current three-case JointPos nullspace matrix as the next paid step. In this probe the nullspace term never activated, because the joints stayed outside the configured activation margin, and the JointPos surface regressed depth badly compared with native Abs IK. The next paid validation should require a local change to phase/target/action semantics rather than a gain-only sweep.

The phase/target follow-up has run and failed closed:

```bash
RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
RCA_LAUNCHABLE_SCRIPTED_STEPS=900 \
./scripts/run_launchable_phase2_jointpos_rotate_descend_probe.sh
```

This wrapper sets `--rotate-descent-mode approach`, enables rotate/descent XY retention, and disables joint-limit nullspace gain so the result isolates the new staged target behavior. It exists because the previous trace held Z near the high XY-aligned pose while waiting forever for rotation readiness; the desired diagnostic was whether simultaneous rotate-plus-approach descent can reach depth without losing XY.

Known AWS result from `rca-jointpos-rotatedesc-vm` / `r2dvf19yi`:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
bundle: artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
smoke: passed
retention probe: failed closed, selected step=10 phase=rotate-descend lateral=0.00889 axial=0.6345 rot=0.9463 strict_miss=66.9987, final lateral=0.1680 axial=0.8438 rot=1.4707, phase_counts reach=5 rotate-descend=18 rotate-xy-recover=877
open probe without XY retention: failed closed, selected step=11 phase=rotate-descend lateral=0.00814 axial=0.6343 rot=0.9517 strict_miss=66.9568, final lateral=0.1328 axial=0.7083 rot=1.5511, phase_counts reach=5 rotate-descend=495
remote artifacts packaged but not pulled:
  /home/ubuntu/rca-jointpos-rotate-descend-results-r2dvf19yi.tar.gz
  /home/ubuntu/rca-host-diagnostics-r2dvf19yi.txt
local artifact status: not present because Brev CLI auth expired before copy
cost/cleanup status: Brev later reported credits exhausted and auto-stopped environments
```

Interpretation: do not rerun the current rotate-descend wrapper unchanged. Retention blocks descent by falling into recovery almost immediately, while disabling retention allows descent but loses XY. Because credits were exhausted, no further paid Launchable/Brev run should be started from this runbook until the user explicitly approves a new budget.

Bundle for this validation:

```text
artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
```

The wiring remains available for reproducibility. `scripts/scripted_agent.py` supports:

```bash
--mdp-abs-ik-method dls|pinv|svd|trans
```

and this wrapper exposes:

```bash
RCA_LAUNCHABLE_MDP_ABS_IK_METHOD=dls|pinv|svd|trans
```

The completed matrix was run with:

```bash
RCA_LAUNCHABLE_SCRIPTED_STEPS=350 \
RCA_LAUNCHABLE_TIMEOUT_SECONDS=900 \
RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
./scripts/run_launchable_absik_ik_method_matrix.sh
```

Latest local bundle with this matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-ik-method-matrix-2026-05-25.tar.gz
```

## Stop Criteria

Stop the AWS Launchable immediately if:

- the smoke fails before task registration;
- the smoke exposes Isaac Lab 2.3 incompatibility;
- the evaluation fails before producing a summary;
- `preload-direction` is no better than `current-joint` / BC at near-contact retention.
- Brev CLI auth fails before artifact copy/delete; in that case delete from the Brev UI immediately instead of waiting for CLI recovery.

After stopping, verify from the local machine:

```bash
/Users/Shenghan/bin/brev ls instances --all
/Users/Shenghan/bin/brev ls instances --json --all
```
