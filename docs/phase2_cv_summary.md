# Phase 2 CV Summary

## One-line project description

Extended the Isaac Lab peg-in-hole precursor into a physical peg/socket contact shell, validated contact sensing and guarded remote GPU execution, and produced a reproducible shallow true-contact scripted success plus strict-gate failure analysis.

## Resume-ready bullets

- Upgraded a proxy peg-in-hole task into a true contact environment with explicit peg geometry, guide-socket collision walls, socket-frame success checks, and contact-force observations.
- Built guarded Brev GPU workflows with live price comparison, remote Isaac runtime installation, artifact pullback, instance deletion, and final empty-org verification to control experiment cost.
- Achieved a reproducible shallow true-contact scripted success under `xy<5mm`, `z<45mm`, `rot<0.20rad`, and `contact>=0.5`, then diagnosed why stricter contact-retention gates still failed.
- Implemented and evaluated multiple final-contact controller variants, including passive strict rotation, early contact retention, XY-hold retention, and force-aware XY correction, with fixed-seed JSON traces for each run.
- Bootstrapped a learned contact-policy path by extracting scripted traces into BC datasets, training MLP checkpoints, and evaluating both reset and staged handoff policies in the true-contact environment.

## Key measured result

Shallow true-contact success:

```text
run:          2026-05-17T19-47-06Z
success_step: 1538
lateral:      0.0047 m
axial:        0.0419 m
rotation:     0.1909 rad
contact:      0.6927
gate:         xy<0.005, z<0.045, rot<0.20, contact>=0.5
```

Closest strict-gate near miss:

```text
run:          2026-05-17T23-32-18Z
step:         1543
lateral:      0.0052 m
axial:        0.0413 m
rotation:     0.1812 rad
contact:      0.5298
strict gate:  xy<0.005, z<0.045, rot<0.18, contact>=0.5
miss:         0.20 mm lateral and 0.0012 rad rotation
```

Learned-policy smoke:

```text
all-trace BC:         success_step=null, best_strict_miss_score=21.0692
best-window staged BC: success_step=null, handoff_miss=0.0319, best_after_bc=0.1865
conclusion:           BC pipeline works, but small-window one-step BC destabilizes the near-success contact state
```

## Honest scope statement

This is not yet a final industrial peg-in-hole insertion policy. The current Phase 2 milestone proves that the contact shell, sensor path, scripted controller, fixed-seed evaluation, artifact capture, and cloud cleanup workflow work end-to-end. The remaining technical problem is strict final-contact control: lateral centering, contact retention, and final orientation correction trade off during the last few millimeters.

## Interview framing

- Why Phase 2 matters: it converts the Phase 1 proxy task into a physically meaningful contact task instead of continuing to tune rewards on a non-contact shell.
- What worked: contact geometry, socket-frame metrics, force observations, reproducible GPU gates, and a shallow contact success.
- What failed: hand-coded contact-retention heuristics got very close but did not satisfy the strict gate.
- What the learned-policy smoke showed: the data/checkpoint/eval pipeline works, but naive one-step BC is not enough for post-handoff contact stabilization.
- What the failure means: the remaining blocker is coupled contact control, not environment setup or quaternion/frame debugging.
- What comes next: generate richer post-contact demonstrations and train either a residual learned correction policy or a temporally conditioned imitation policy for the last contact-retention phase.
