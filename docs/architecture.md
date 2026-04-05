# Architecture

## Goal

Build a contact-rich robot manipulation baseline that can grow into:

1. scripted baseline
2. RL baseline
3. sim-to-real constrained stack
4. IL augmentation
5. language-conditioned high-level interface

## Runtime split

### Local control plane

Runs on the Mac mini:

- Cursor and repo editing
- Codex-assisted development
- local port-forwarding and tooling
- artifact review and archive management

### Remote execution plane

Runs on Brev:

- Isaac Sim
- Isaac Lab tasks
- ROS 2 graph for sim-facing nodes
- training and evaluation jobs
- video render and checkpoint creation

## Phase-1 constraints

- one task only
- one robot only
- one policy only
- no language model in the control loop
- no multi-task generalization claims

## Why this split

- it keeps cost bounded
- it avoids local hardware bottlenecks
- it preserves a clean migration path to later sim-to-real work
