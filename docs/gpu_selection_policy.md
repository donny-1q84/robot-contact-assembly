# GPU Selection Policy

This project should not default to one fixed GPU type. Before every paid GPU session, check the live Brev price table and choose the cheapest instance that matches the actual job.

## Required Preflight

Run these commands before creating an instance:

```bash
scripts/brev_paid_safety_status.sh
/Users/Shenghan/bin/brev ls instances --all
/Users/Shenghan/bin/brev ls instances --json --all
/Users/Shenghan/bin/brev search --min-total-vram 24 --min-disk 500 --stoppable --sort price | head -40
/Users/Shenghan/bin/brev search --min-total-vram 32 --min-disk 500 --stoppable --sort price | head -40
/Users/Shenghan/bin/brev search --min-total-vram 40 --min-disk 500 --stoppable --sort price | head -40
```

If any instance is already running and it is not part of the current task, stop and resolve it before creating another one.

## Mandatory Billing Watchdog

Every paid Brev run must have a local watchdog before the instance is created or immediately after a UI-created Launchable appears. The watchdog records a local ledger with the TTL plus any supplied budget/hourly-estimate cost boundary, polls `brev ls instances --json --all`, and enforces a hard TTL. If the Brev CLI login expires, it cannot delete the instance automatically, but it fails loudly by writing `manual_delete_required.txt` and sending a macOS notification with the Dashboard URL.

For target-specific monitoring:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
RCA_BREV_WATCHDOG_INSTANCE_NAME=<instance-name> \
RCA_BREV_WATCHDOG_MAX_MINUTES=60 \
scripts/brev_paid_run_watchdog.sh
```

For a UI Launchable when the exact generated name/id is not known yet, use org-scope only in the dedicated project org and only when deleting all visible instances is acceptable:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
RCA_BREV_WATCHDOG_MAX_MINUTES=60 \
scripts/start_brev_ui_launchable_watchdog.sh
```

Use the UI/provider hourly price converted conservatively to EUR. The paid
preflight rejects runs whose estimated max cost
`RCA_PAID_ESTIMATED_EUR_PER_HOUR * TTL / 60` exceeds the explicit budget.

The guarded CLI wrappers start this watchdog automatically. Default TTLs are:

- `scripts/run_guarded_phase2_gate.sh`: `RCA_GATE_WATCHDOG_MAX_MINUTES=120`
- `scripts/recreate_brev_and_run_polish.sh`: `RCA_RECREATE_WATCHDOG_MAX_MINUTES=180`
- `scripts/start_brev_ui_launchable_watchdog.sh`: `RCA_BREV_WATCHDOG_MAX_MINUTES=60`

Increase the TTL only for an explicit run plan. Do not use Brev credits or low-balance emails as the shutdown mechanism.

## Guarded Gate Wrapper

For the next Phase 2 contact-shell validation, prefer the guarded wrapper instead of manually creating a Brev instance:

```bash
scripts/run_guarded_phase2_gate.sh
```

For the current Joint-IK scripted validation, use the narrower wrapper:

```bash
scripts/run_phase2_jointik_gate.sh
```

What the wrapper does:

- refuses to start if the git tree is dirty, unless `RCA_ALLOW_DIRTY=1`
- refuses to start if Brev already shows an instance in the org
- starts `scripts/brev_paid_run_watchdog.sh` before `brev create`, so an orphaned paid instance is still TTL-limited if the parent script crashes or `brev create` hangs
- records live Brev price tables before creation
- chooses the cheapest visible single L40S by default (`RCA_GATE_PROFILE=balanced`)
- uses L4 only when explicitly requested with `RCA_GATE_PROFILE=cheap`
- installs the headless Isaac Lab runtime with the streaming stack skipped
- runs the scripted Phase 2 contact gate
- pulls artifacts back to the external SSD
- deletes the GPU instance on exit and checks that the org is empty
- aborts early if the instance is stuck in `RUNNING / BUILDING / NOT READY` for `RCA_GATE_BUILD_STUCK_SECONDS` seconds
- retries deletion by both instance name and instance id when Brev keeps showing the target during cleanup

The wrapper also applies short timeouts to Brev list/search/delete calls, because Brev CLI queries have previously printed a result but failed to exit cleanly. It uses `brev ls instances` explicitly instead of plain `brev ls`, because plain `brev ls --json --all` has previously hung. If the JSON query times out only after printing an exact empty-org marker (`null` or `[]`), the wrapper accepts that marker; any other failed query remains fail-closed. Do not bypass this wrapper for short paid validation runs unless there is a specific reason.

Default startup protection:

- `RCA_GATE_READY_TIMEOUT_SECONDS=900`: total ready wait limit.
- `RCA_GATE_BUILD_STUCK_SECONDS=420`: generic guarded gate aborts if Brev stays in `BUILDING`.
- `scripts/run_phase2_jointik_gate.sh` tightens `RCA_GATE_BUILD_STUCK_SECONDS=300` for the short Joint-IK validation.

## Selection Rules

Use the task, not the GPU name, as the selector.

- For cheap scripted gates, runtime checks, and non-training evals, prefer the cheapest single-GPU instance with enough VRAM to boot Isaac Sim reliably. A single L4 can be acceptable only after the fixed headless-container path has been validated; do not use it for cold Isaac bring-up when time matters.
- For PPO/RL training in Isaac Lab, prefer one strong single GPU with at least 40 GB VRAM. L40S is currently the default value target when it is available and not much more expensive than weaker options.
- Avoid multi-T4 as the default even when the total VRAM number looks attractive. Isaac Sim and this repo's wrappers are not designed to benefit from several weak GPUs for one environment/training job.
- Use A100/H100/H200 only when a specific workload needs it. For this project phase, they are usually overkill unless the price is unusually close to L40S.
- Prefer lower hourly cost over high CPU count for short gates. CPU/RAM matter for full training and artifact-heavy sessions, but not enough to justify a much more expensive instance for a 10-30 minute gate.

## Current Snapshot

Checked on `2026-05-21` with 500 GB target disk:

- `g2-standard-4:nvidia-l4:1`, L4 24 GB, `$0.85/hr`: still the cheapest visible candidate, but it failed the probe-only lifecycle gate before SSH. Avoid using this type for Isaac until `scripts/run_brev_probe_only_gate.sh` succeeds or Brev support confirms the org/provider issue is fixed.
- `gpu-l40s-a.1gpu-8vcpu-32gb`, L40S 48 GB, `$1.86/hr`: next explicit non-GCP candidate to consider for a probe-only test if we need to determine whether the issue is specific to GCP L4.
- `g6e.xlarge`, L40S 45 GB, `$2.23/hr`: AWS fallback candidate for probe-only testing if Nebius also fails or is unavailable.

Do not proceed from probe-only to Isaac install/eval unless the probe reaches SSH, prints `nvidia-smi`, and deletes cleanly with both plain and JSON empty-org checks.

Update from `2026-05-21T22-21Z`: the explicit Nebius L40S probe also failed before SSH. It stayed `RUNNING / BUILDING / NOT READY` for `248s`, then cleanup encountered Brev RPC timeouts and repeated `RUNNING / COMPLETED / READY` then `DELETING / COMPLETED / NOT READY` states before finally clearing. This is now a Brev/org lifecycle issue, not just a GCP L4 issue. Do not test the AWS fallback casually; contact Brev support or use a different compute path first.

Update from Brev support on `2026-05-22`: support confirmed that org `NCA-57cf-29515` had no active instances, hidden workspaces, deployments, volumes, or other billable resources. They reported that instance creation worked on their side, suggested the GCP issue may involve required Isaac Sim port opening, noted that Nebius requires manual port management such as `ufw`, and recommended the official Isaac Launchable, preferably on AWS. Because our `probe_only` runs had not reached SSH or Isaac streaming, do not treat this as proof that the existing CLI wrapper is healthy.

Experimental direct-SSH probe:

```bash
scripts/run_brev_probe_direct_ssh_gate.sh
```

This wrapper is still `probe_only`: it does not install Isaac or run evaluation. It keeps the guarded create/delete flow, but sets `RCA_GATE_DIRECT_SSH_AFTER_CREATE_READY=1`. If `brev create` has returned and `brev ls` remains stuck in `RUNNING / BUILDING / NOT READY` for a short grace window, the guarded script runs `brev refresh` and attempts direct SSH / `nvidia-smi` before declaring failure. This tests whether the previous aborts were caused by stale list readiness rather than actual SSH unavailability.

Result from `2026-05-24T14-42-53Z`: after restoring CLI login, the direct-SSH L4 probe selected `g2-standard-4:nvidia-l4:1` but failed before SSH because Brev's `CreateWorkspace` API returned `unexpected EOF`. Cleanup confirmed no visible instances; the final JSON instance list was `{"workspaces": null}`. This is earlier than the port/streaming problem described by support, so do not run a full Isaac job through this Brev GCP path until the create API issue is resolved or an AWS Launchable path is ready.

AWS Launchable fallback:

```bash
docs/aws_isaac_launchable_runbook.md
scripts/create_launchable_bundle.sh
scripts/run_launchable_headless_smoke.sh
scripts/run_launchable_phase2_preload_direction.sh
```

This path intentionally uses the Brev UI and the official Isaac Launchable rather than the failing local CLI `brev create` flow. Run the Launchable smoke before the Phase 2 preload-direction evaluation.

Result from `2026-05-24`: the official AWS Launchable reached `Running / Built / script Completed` on `g6e.4xlarge` with an NVIDIA L40S. The first instance exposed Isaac Lab 2.3 compatibility issues and was deleted after diagnostics were pulled to `artifacts/launchable_logs/rca-launchable-diagnostics-20260524.tar.gz`. A second Launchable, `isaac-launchable-5c7e93` / `kkekc4hjq`, passed the marker-checked 10-step headless smoke and the four-case diagnostic matrix after these fixes:

- force Launchable scripts through `isaaclab.app.AppLauncher`;
- change the per-step peg sync interval from `0.0s` to `sim.dt * decimation`;
- avoid `warp.to_torch()` on Isaac Lab tensors that are already `torch.Tensor`;
- ignore `SystemExit` raised during Isaac shutdown so real Python errors stay visible;
- make Launchable shell scripts verify reset/step/summary markers instead of trusting process exit alone.

The formal `preload-direction` eval also ran and produced a summary, but it exposed historical trace replay drift: the old source trace handoff at step `1543` had `lateral=0.0052`, while the Isaac Lab 2.3 Launchable replay of the same `raw_action` sequence reached `lateral=0.2508`. Diagnostics were pulled to `artifacts/launchable_logs/rca-launchable-diagnostics-kkekc4hjq.tar.gz`, and the Launchable was deleted afterward. Treat this as a valid runtime path for short AWS Launchable runs, but do not spend another run replaying the old trace. Use `scripts/run_launchable_phase2_fresh_preload_direction.sh` so the scripted preload trace is generated in the same runtime as the handoff eval.

Follow-up result from `isaac-launchable-fb61a7` / `pk2xmabsc`: the final smoke passed, and the fresh-preload wrapper correctly failed closed before post-handoff eval because the selected fresh handoff had `strict_miss_score=77.7206` (`lateral=0.0049`, `axial=0.5937`, `rot=2.4654`). WXYZ convention and no-rotate-before-descend diagnostics did not rescue the old scripted-controller family. Treat AWS Launchable as validated infrastructure, but do not spend another paid run on that full-quaternion controller.

Axis-aware follow-up result from `isaac-launchable-837c5c` / `e9v2t2tsw`: the instance was created from the official AWS Isaac Launchable on `g6e.4xlarge` L40S. The official cloud-init scripts were empty and failed with `Exec format error`, so the official `isaac-sim/isaac-launchable` compose stack was started manually on the host. The marker-checked 10-step RCA smoke passed. The guarded fresh-preload run using `--orientation-target-mode axis-align-current` failed closed before post-handoff eval because the selected handoff had `strict_miss_score=63.6295` (`step=7`, `lateral=0.0082`, `axial=0.6031`, `rot=0.9302`). A no-rotate-before-descend diagnostic reached better individual axial/rot minima (`best_axial=0.0611`, `best_rot=0.1868`) but lost XY badly (`final_lateral=0.4124`). Diagnostics were pulled to `artifacts/launchable_logs/rca-launchable-diagnostics-e9v2t2tsw.tar.gz` and `artifacts/launchable_logs/rca-host-diagnostics-e9v2t2tsw.tar.gz`; `brev delete e9v2t2tsw` was issued, SSH became unavailable, the browser UI showed no environments, and `brev ls` confirmed no instances in org `NCA-57cf-29515`.

XY-retention validation result from `isaac-launchable-1e19c4` / `1cozht94s`: the same official AWS Launchable path was created on `g6e.4xlarge` L40S. Cloud-init again failed with empty per-boot/per-instance scripts, and the official compose stack was started manually. The marker-checked 10-step RCA smoke passed. The guarded fresh-preload wrapper with `--rotate-xy-retention` and `--descend-xy-retention` failed closed before post-handoff eval: selected handoff `step=8`, `lateral=0.0065`, `axial=0.6025`, `rot=0.9335`, `strict_miss_score=63.4364`. The full summary shows recovery was detected but ineffective (`rotate_xy_recovery_step_count=1767`, max lateral about `1.00m`; `descend_xy_recovery_step_count=122`). Two live-patched joint-step scaling diagnostics, `global` and `after-xy-global`, were stopped early because they still did not recover to a useful handoff. Diagnostics were pulled to `artifacts/launchable_logs/rca-launchable-diagnostics-1cozht94s.tar.gz` and `artifacts/launchable_logs/rca-host-diagnostics-1cozht94s.tar.gz`; `brev delete 1cozht94s` was issued, subsequent SSH lookup failed, and the browser UI showed an empty environment list. The CLI list endpoint was timing out during the final check.

Current GPU policy: AWS Launchable is validated infrastructure for short Isaac smoke/eval runs, but do not spend another paid run on the current joint-position scripted handoff / `preload-direction` family, unchanged Abs IK waypoint/target probes, single-joint initial-posture probes, guide-wall collision variants, simple target-offset variants, native IK solver-method variants, or coarse full-arm reset/posture variants. The target-offset matrix, `dls/pinv/svd/trans` solver-method matrix, and `baseline/ready_mid/elbow_open/yaw_pos/yaw_neg` full-arm posture matrix already ran and did not improve true socket XY. The next paid run should require a genuinely new controller/policy formulation or explicit joint-limit/nullspace behavior with a local smoke path and a single guarded validation plan.

Explicit probe-only wrappers:

```bash
scripts/run_brev_probe_only_gate.sh
scripts/run_brev_probe_direct_ssh_gate.sh
scripts/run_brev_probe_l40s_nebius_gate.sh
scripts/run_brev_probe_l40s_aws_gate.sh
```

Use only one at a time, and verify empty-org text + JSON output afterward.
After the 2026-05-26 Brev credit exhaustion, these wrappers fail closed unless `RCA_ALLOW_PAID_BREV_CREATE=1` and `RCA_BREV_CREDITS_VERIFIED=1` are set deliberately for that session. Set the credit marker only after checking the Brev UI/org balance, because the CLI has no read-only credit-balance command. They must also pass `scripts/paid_compute_preflight.sh`, which requires an explicit budget, conservative EUR/hour estimate, hard TTL, valid Brev CLI auth, an empty visible org, and an estimated max cost inside the budget. Before the Phase 2 contact gate passes, the only valid paid purpose is `RCA_PAID_RUN_PURPOSE=contact_physics_smoke`.

Checked on `2026-04-26` with 500 GB target disk:

- `g2-standard-4:nvidia-l4:1`, L4 24 GB, about `$0.85/hr`: cheapest candidate for a short headless scripted gate if Isaac boots reliably.
- `n1-standard-1:nvidia-tesla-t4:2`, 2x T4 32 GB total, about `$0.91/hr`: cheap but lower compute capability and not ideal for this single-job Isaac workflow.
- `gpu-l40s-a.1gpu-8vcpu-32gb`, L40S 48 GB, about `$1.86/hr`: best default value for real Isaac Lab training if creation succeeds.
- `g6e.xlarge`, L40S 45 GB, about `$2.23/hr`: AWS fallback when Nebius L40S creation fails.
- `gpu-h100-sxm.1gpu-16vcpu-200gb`, H100 80 GB, about `$3.54/hr`: powerful, but only use if a short high-VRAM/high-throughput job justifies the premium.

These prices are not stable. Re-run the preflight commands every time.

The `2026-04-26` L4 gate attempt showed that a cold L4 can waste time during Isaac startup if the task container accidentally starts an extra streaming Kit process. See `experiments/2026-04-26_phase2_l4_gate_attempt.md`.

## Creation Strategy

Do not let `brev create` automatically fall through a long list of increasingly expensive instances.

Use an explicit type after comparing prices and only after an explicit budget/deletion check. Prefer the guarded wrappers; if a manual `brev create` is unavoidable, first run and record the paid preflight:

```bash
export RCA_ALLOW_PAID_BREV_CREATE=1
export RCA_BREV_CREDITS_VERIFIED=1
export RCA_PAID_BUDGET_EUR=<explicit-budget>
export RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour>
export RCA_PAID_MAX_MINUTES=<ttl-minutes>
export RCA_PAID_RUN_PURPOSE=contact_physics_smoke
scripts/paid_compute_preflight.sh

/Users/Shenghan/bin/brev create isaac-l40s \
  --type <selected-type> \
  --min-disk 500 \
  --stoppable \
  --timeout 900
```

If the selected type fails with a Brev API or provider error, check:

```bash
/Users/Shenghan/bin/brev ls instances --all
```

Only then try one explicit fallback type. Do not keep retrying indefinitely.

## Billing Rule

After every run:

```bash
/Users/Shenghan/bin/brev delete <instance-name>
/Users/Shenghan/bin/brev ls
```

The session is not complete until `brev ls` shows no unintended running instance.
