# 2026-04-26 Phase 2 Direct Contact Baseline

## Goal

Run the first longer direct-contact PPO baseline on the force-aware contact task after the Brev refund and runtime reset.

Target task:

- `RCA-PegInHole-Franka-IK-Rel-Contact-v0`

Target run:

- `phase2_contact_baseline_v2`

## Remote Runtime

- Brev org: `NCA-57cf-29515`
- Instance name: `isaac-l40s`
- Instance type: `massedcompute_L40S`
- Quoted dry-run cost: `$1.06/hr`
- GPU: `NVIDIA L40S`, `46068 MiB`
- Remote user: `shadeform`
- Remote root: `/home/shadeform/projects/robot-contact-assembly`
- Compose root: `/home/shadeform/isaac-compose`

The instance was deleted after artifact pullback, and `brev ls` returned:

```text
No instances in org NCA-57cf-29515
```

## Runtime Fixes

The fresh `massedcompute_L40S` instance used `shadeform` instead of `ubuntu`, so the runtime scripts needed two portability fixes:

- `install_remote_isaaclab_runtime.sh` now writes the compose project override from the requested `REMOTE_ROOT` instead of relying on the committed `/home/ubuntu` paths.
- the IsaacLab clone is chowned to the current remote user instead of `ubuntu:ubuntu`.

The streaming stack also failed while building `web-viewer`:

```text
target web-viewer: failed to receive status: rpc error: code = Unavailable desc = error reading from server: EOF
```

For this run, the training path did not need WebRTC or the viewer. The installer now supports:

```bash
RCA_SKIP_STREAM_STACK=1 ./scripts/install_remote_isaaclab_runtime.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose
```

This creates only the headless `isaac-runner` container.

The current IsaacLab `develop` commit expected:

```python
import omni.physics.tensors.api
```

but `nvcr.io/nvidia/isaac-sim:6.0.0-dev2` exposed the API under:

```python
omni.physics.tensors.impl.api
```

The installer now adds a small compatibility shim:

```python
from .impl.api import *
```

under the container's `omni.physics.tensors` extension when needed.

Finally, `run_remote_train_ppo.sh` now fails if no checkpoint is produced. This prevents Isaac/Kit tracebacks from being misclassified as successful training runs.

## Commands

Runtime install:

```bash
RCA_SKIP_STREAM_STACK=1 ./scripts/install_remote_isaaclab_runtime.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose
```

Runtime check:

```bash
bash ./scripts/check_remote_runtime.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose
```

Smoke that validated the contact training path after the tensor API shim:

```bash
./scripts/run_remote_train_ppo.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose \
  RCA-PegInHole-Franka-IK-Rel-Contact-v0 \
  64 \
  5 \
  42 \
  phase2_contact_baseline_v2_smoke2
```

Formal direct-contact baseline:

```bash
./scripts/run_remote_train_ppo.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose \
  RCA-PegInHole-Franka-IK-Rel-Contact-v0 \
  64 \
  100 \
  42 \
  phase2_contact_baseline_v2
```

Fixed eval:

```bash
./scripts/run_remote_eval_policy.sh \
  isaac-l40s \
  /home/shadeform/projects/robot-contact-assembly \
  /home/shadeform/isaac-compose \
  RCA-PegInHole-Franka-IK-Rel-Contact-v0 \
  16 \
  400 \
  42 \
  '.*phase2_contact_baseline_v2$' \
  model_99.pt
```

## Artifacts

Training artifacts:

- `artifacts/train_runs/2026-04-26T11-33-17Z_phase2_contact_baseline_v2/train.log`
- `artifacts/train_runs/2026-04-26T11-33-17Z_phase2_contact_baseline_v2/train_command.txt`
- `artifacts/train_runs/2026-04-26T11-33-17Z_phase2_contact_baseline_v2/train_metadata.env`
- `artifacts/train_runs/2026-04-26T11-33-17Z_phase2_contact_baseline_v2/model_99.pt`

Full local checkpoint directory:

- `logs/rsl_rl/franka_peg_in_hole/2026-04-26_11-33-23_phase2_contact_baseline_v2/`

Saved checkpoints:

- `model_0.pt`
- `model_25.pt`
- `model_50.pt`
- `model_75.pt`
- `model_99.pt`

Evaluation artifacts:

- `artifacts/evaluations/policy/2026-04-26T11-35-43Z/summary.json`
- `artifacts/evaluations/policy/2026-04-26T11-35-43Z/eval.log`
- `artifacts/evaluations/policy/2026-04-26T11-35-43Z/eval_command.txt`

## Training Result

The formal run trained successfully and saved `model_99.pt`.

Late training behavior:

- mean reward reached approximately `1.9`
- mean episode length saturated at `240`
- `Episode_Reward/insertion_progress` stayed at `0.0000`
- `Episode_Reward/insertion_success` stayed at `0.0000`
- `Episode_Termination/insertion_success` stayed at `0.0000`

This means the policy learned some pose/orientation reward, but did not enter the insertion-progress region.

## Fixed Eval Result

Summary from `artifacts/evaluations/policy/2026-04-26T11-35-43Z/summary.json`:

```json
{
  "best_success_rate": 0.0,
  "final_success_rate": 0.0,
  "final_lateral": 0.47245967388153076,
  "final_axial": 0.421664834022522,
  "final_rot": 1.9343479871749878,
  "initial_lateral": 0.035149648785591125,
  "initial_axial": 0.23663230240345,
  "initial_rot": 2.4025182723999023
}
```

Checkpoint sweep was attempted after the fixed eval, but evaluating `model_0.pt` was killed with status `137`. It was not retried because the key result was already clear and the GPU session was closed to avoid extra cost.

## Interpretation

This run answers the Phase 2 baseline question:

- the force-aware contact task can boot, train, save checkpoints, and run fixed evaluation on a fresh Brev L40S instance
- the first direct-contact PPO baseline does not solve insertion
- the failure is no longer infrastructure; it is task/reward design

The most important signal is that `insertion_progress` stayed at zero throughout training. More PPO time on the same setup is unlikely to fix this by itself.

## Next Decision

Do not run another long PPO job yet.

Next local work should inspect:

- whether the reset distribution starts too far from the contact/insertion basin
- whether `insertion_progress` is gated so tightly that the policy receives no useful gradient
- whether the guide-wall contact geometry pushes the peg away instead of funneling it
- whether a short scripted or teleop demonstration should replace PPO-only exploration for the next milestone

The next GPU spend should only happen after a local task-level change that makes `insertion_progress` non-zero under either scripted actions or a narrow reset distribution.
