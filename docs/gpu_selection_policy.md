# GPU Selection Policy

This project should not default to one fixed GPU type. Before every paid GPU session, check the live Brev price table and choose the cheapest instance that matches the actual job.

## Required Preflight

Run these commands before creating an instance:

```bash
/Users/Shenghan/bin/brev ls
/Users/Shenghan/bin/brev search --min-total-vram 24 --min-disk 500 --stoppable --sort price | head -40
/Users/Shenghan/bin/brev search --min-total-vram 32 --min-disk 500 --stoppable --sort price | head -40
/Users/Shenghan/bin/brev search --min-total-vram 40 --min-disk 500 --stoppable --sort price | head -40
```

If any instance is already running and it is not part of the current task, stop and resolve it before creating another one.

## Selection Rules

Use the task, not the GPU name, as the selector.

- For cheap scripted gates, runtime checks, and non-training evals, prefer the cheapest single-GPU instance with enough VRAM to boot Isaac Sim reliably. A single L4 can be acceptable if the job is headless and short.
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
/Users/Shenghan/bin/brev ls
```

Only then try one explicit fallback type. Do not keep retrying indefinitely.

## Billing Rule

After every run:

```bash
/Users/Shenghan/bin/brev delete <instance-name>
/Users/Shenghan/bin/brev ls
```

The session is not complete until `brev ls` shows no unintended running instance.
