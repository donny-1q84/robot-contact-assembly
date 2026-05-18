# Phase 2 Control-Mode Comparison Plan

## Question

Would a Cartesian end-effector action space make the final contact phase more stable than the current joint-position task with a standalone joint-IK pre-controller?

This should be tested as a controlled comparison, not as another broad scripted-controller sweep.

## Current baseline

The closest strict scripted result so far is:

```text
run:     2026-05-17T23-32-18Z
task:    RCA-PegInHole-Franka-JointPos-Contact-Play-v0
control: JointPositionActionCfg + standalone joint-IK pre-controller
step:    1543
lateral: 0.0052 m
axial:   0.0413 m
rot:     0.1812 rad
contact: 0.5298
miss:    0.20 mm lateral and 0.0012 rad rotation
```

The success gate is:

```text
xy < 0.005 m
z < 0.045 m
rot < 0.18 rad
contact >= 0.5
```

## Modes to compare

### A. Joint-position baseline

Script:

```bash
scripts/run_phase2_control_mode_jointpos_gate.sh
```

Task:

```text
RCA-PegInHole-Franka-JointPos-Contact-Play-v0
```

Meaning:

- the Isaac Lab action term accepts 7 Franka joint-position targets
- the scripted controller computes Cartesian peg-tip targets
- a standalone differential IK pre-controller converts those Cartesian targets into joint-position targets
- this is the strongest known scripted branch so far

### B. Relative Cartesian IK

Script:

```bash
scripts/run_phase2_control_mode_rel_ik_gate.sh
```

Task:

```text
RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0
```

Meaning:

- the Isaac Lab action term accepts 6D relative pose deltas
- the task's native differential IK action converts those deltas into robot motion
- this tests whether a direct Cartesian delta action space is more stable than the joint-position wrapper

### C. Absolute Cartesian IK

Script:

```bash
scripts/run_phase2_control_mode_abs_ik_gate.sh
```

Task:

```text
RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0
```

Meaning:

- the Isaac Lab action term accepts absolute 7D pose commands
- the scripted controller sends bounded Cartesian waypoints instead of raw joint targets
- this tests whether Isaac Lab's native absolute Cartesian IK avoids the branch/coupling behavior seen in the joint-position path

## Run policy

Run at most one paid gate at a time.

Before each run:

```bash
/Users/Shenghan/bin/brev refresh
/Users/Shenghan/bin/brev ls instances --all
/Users/Shenghan/bin/brev ls instances --json --all
git status --short
```

After each run:

```bash
/Users/Shenghan/bin/brev ls instances --all
/Users/Shenghan/bin/brev ls instances --json --all
```

The org must be empty before starting the next run.

## Pass/fail criteria

Primary pass:

```text
success_step != null
```

Secondary ranking if all fail:

1. lowest strict-gate miss score
2. no branch jump
3. higher contact force at closest strict step
4. lower lateral error at closest strict step
5. lower rotation error at closest strict step

Summarize pulled results with:

```bash
python3 scripts/summarize_control_mode_comparison.py --since 2026-05-17T23-00-00Z
```

## Decision rule

If either Cartesian IK mode beats the joint-position baseline, use that action space for the next learned contact policy.

If neither Cartesian IK mode beats the joint-position baseline, stop scripted control-mode work. The remaining issue is not action-space expression; it is final-contact policy learning.

## Expected cost

Each gate should use the cheapest live 24GB+ Brev option, normally:

```text
g2-standard-4:nvidia-l4:1
```

Expected runtime per gate is roughly 20-35 minutes including install, eval, artifact pullback, and deletion. Run only the Cartesian candidates first if preserving budget; reuse the existing `2026-05-17T23-32-18Z` joint-position result as the baseline.
