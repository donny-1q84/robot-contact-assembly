# robot_contact_assembly_tasks

External Isaac Lab task package for the `robot-contact-assembly` repository.

## Scope

Current task shell:

- `RCA-PegInHole-Franka-IK-Rel-v0`
- `RCA-PegInHole-Franka-IK-Rel-Play-v0`

The first shell is an insertion-only baseline:

- Franka Panda
- relative differential IK
- peg tip modeled as a fixed tool offset
- socket target modeled as a commanded pose in the robot root frame

This is a deliberate first step. It is enough to validate task registration, action/observation contracts, reward shaping, and PPO wiring before adding a grasped rigid peg, explicit socket geometry, and contact-driven success logic.

## Install

Inside an Isaac Lab Python environment:

```bash
python -m pip install -e source/robot_contact_assembly_tasks
```

## Quick checks

```bash
python scripts/list_envs.py --keyword PegInHole
python scripts/zero_agent.py --task RCA-PegInHole-Franka-IK-Rel-Play-v0
python scripts/random_agent.py --task RCA-PegInHole-Franka-IK-Rel-Play-v0
```
