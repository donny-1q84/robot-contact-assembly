# robot_contact_assembly_tasks

External Isaac Lab task package for the `robot-contact-assembly` repository.

## Scope

Current task shell:

- `RCA-PegInHole-Franka-IK-Rel-v0`
- `RCA-PegInHole-Franka-IK-Rel-Play-v0`

The mainline task shell is now a contact-guided insertion baseline:

- Franka Panda
- relative differential IK
- physical peg rigid body that follows the end-effector
- fixed guide-socket walls around a physical socket frame anchor
- success measured against the physical peg/socket frame, not the old synthetic offset target

The policy observation contract intentionally stays Phase-1 compatible for now so the best proxy checkpoint can be evaluated zero-shot in the new contact shell before adding force terms to the actor.

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
