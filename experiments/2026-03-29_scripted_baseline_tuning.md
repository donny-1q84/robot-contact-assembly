# 2026-03-29 Scripted Baseline Tuning

## Goal

Push the first `peg-in-hole` scripted baseline from "scene loads and steps" to a geometry-consistent controller that can approach task success.

## Key fixes

1. Added a shared peg tool-frame constant:
   - position offset: `(0.0, 0.0, 0.1034)`
   - rotation offset: `(0.0, 0.0, 0.41435254, 0.91011646)`

2. Applied the tool-frame correction to:
   - task observations
   - reward/termination metrics
   - scripted baseline logging

3. Reverted the IK action frame back to:
   - `panda_hand + position offset`

4. Updated the scripted baseline to:
   - target the action frame pose explicitly
   - use a latched `polish` phase
   - use a latched `settle` phase

## Important finding

The original controller was not just "under-tuned". It was geometrically inconsistent.

Before the frame correction, the rollout converged to a nearly fixed residual orientation error of about `0.854 rad` around tool `Z`, which indicated a persistent frame mismatch between the assumed peg frame and the `panda_hand` frame.

The debug script confirmed this:

- initial residual axis-angle: approximately `[-1.187, 0.058, 2.810]`
- converged residual axis-angle before correction: approximately `[0.0, 0.0, -0.854]`

## Best current runs

### Stable near-success run

Command shape:

```bash
bash scripts/run_remote_scripted_baseline.sh
```

Current wrapper parameters:

- direct insertion target (`approach-height 0.0`)
- always align to the socket target (`approach-xy-tol 1.0`, `approach-rot-tol 10.0`)
- settle tuning:
  - `settle-pos-gain 0.5`
  - `settle-pos-clamp 0.012`
  - `settle-rot-gain 3.0`
  - `settle-rot-clamp 0.24`

Observed summary:

- initial lateral: `0.0430`
- final lateral: `0.0005`
- initial axial: `0.1912`
- final axial: `0.0001`
- initial rot: `2.4074`
- final rot: `0.1857`
- success rate: `0.000`

### Aggressive polish run

Observed summary:

- final lateral: `0.0088`
- final axial: `0.0012`
- final rot: `0.0744`

This run proved the orientation threshold can be beaten, but the position drift became too large to satisfy the full success condition.

## Current blocker

The remaining gap is a near-contact controller issue, not a geometry issue:

- one set of gains keeps position inside tolerance but stalls rotation near `0.18-0.20 rad`
- a more aggressive polish phase drives rotation below `0.15 rad` but lets lateral error drift above the `0.003 m` success threshold

## Recommended next step

Do not spend more time on blind gain sweeps.

The next implementation step should be one of:

1. a damped near-contact controller that jointly constrains lateral drift while finishing orientation
2. a short-horizon optimization or resolved-rate controller specialized for the final insertion centimeters
3. handing off this now-consistent environment to RL/IL, since the environment and metric definitions are no longer the primary blocker
