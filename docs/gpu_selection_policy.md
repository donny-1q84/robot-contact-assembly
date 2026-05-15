# GPU Selection Policy

This project should not default to one fixed GPU type. Before every paid GPU session, check the live Brev price table and choose the cheapest instance that matches the actual job.

## Required Preflight

Run these commands before creating an instance:

```bash
/Users/Shenghan/bin/brev ls instances --all
/Users/Shenghan/bin/brev ls instances --json --all
/Users/Shenghan/bin/brev search --min-total-vram 24 --min-disk 500 --stoppable --sort price | head -40
/Users/Shenghan/bin/brev search --min-total-vram 32 --min-disk 500 --stoppable --sort price | head -40
/Users/Shenghan/bin/brev search --min-total-vram 40 --min-disk 500 --stoppable --sort price | head -40
```

If any instance is already running and it is not part of the current task, stop and resolve it before creating another one.

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

Use an explicit type after comparing prices:

```bash
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
