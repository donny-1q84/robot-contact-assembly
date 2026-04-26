# 2026-04-26 Phase 2 L4 Scripted Gate Attempt

## Goal

Try a lower-cost Brev GPU for the Phase 2 scripted contact gate before paying for another L40S.

Target job:

- task: `RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0`
- eval type: scripted gate
- envs: `1`
- steps: `240`
- seed: `42`
- timeout: `600s`

## GPU Selection

Live Brev price check showed:

- `g2-standard-4:nvidia-l4:1`, L4 24 GB, about `$0.85/hr`
- L40S candidates were about `$1.86/hr` and higher

Because this was only a cheap scripted gate and not PPO training, the L4 was selected first.

Instance:

- name: `isaac-gate-l4`
- type: `g2-standard-4:nvidia-l4:1`
- GPU: `NVIDIA L4`, `23034 MiB`
- user: `ubuntu`
- root disk observed: `125G`, not the 500 GB target shown in the price table

## Result

The runtime image and Python dependencies installed, and the task container became healthy. The project runtime check passed:

- `numpy 2.3.1`
- `pillow 12.1.1`
- `h5py 3.15.1`
- `hydra-core 1.3.2`
- `isaaclab 4.6.16`
- `isaaclab_rl 0.5.1`
- all five robot-contact-assembly tasks registered

The scripted eval then timed out:

```text
[scripted-eval] seed=42 failed with status=124
```

Pulled local log:

- `artifacts/evaluations/scripted/2026-04-26T12-29-38Z/seed_42.log`

The log stopped during Isaac app startup:

```text
[INFO]: Loading experience file: /workspace/IsaacLab/apps/isaaclab.python.headless.kit
```

No rollout steps were reached, so this run does not measure task/controller quality.

## Diagnosis

The L4 instance could run Docker and install the runtime, but the original headless task container was still started through the Isaac Sim image entrypoint. That caused a background streaming Kit process to run even though the session requested `RCA_SKIP_STREAM_STACK=1`.

Observed process:

```text
/isaac-sim/kit/kit /isaac-sim/apps/isaacsim.exp.full.streaming.kit ...
```

That process consumed CPU while the scripted eval tried to launch a second Isaac app. On a small L4 instance, this made the cheap gate ineffective.

The instance was deleted after log pullback, and `brev ls` returned:

```text
No instances in org NCA-57cf-29515
```

## Follow-up Fix

`scripts/install_remote_isaaclab_runtime.sh` was updated after this run:

- headless task container now starts with `--entrypoint bash -lc "sleep infinity"`
- container setup now runs through `docker exec ... bash -s` heredoc
- the PhysX tensor API compatibility shim is now evaluated inside the container, not prematurely by the remote host shell

## Decision

Do not use a cold L4 instance for Isaac Sim runtime bring-up unless the container startup fix has already been validated.

For the next actual gate, prefer:

- L40S if the goal is to finish the contact-frame scripted validation quickly
- L4 only if the price gap matters and we are explicitly testing the fixed headless-container path
