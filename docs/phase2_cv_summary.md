# Phase 2 CV Summary

## Current Status - Superseded by 2026-06-18 Audit

Do not use this document as a resume/CV claim in its current form. The 2026-06-11 contact-physics audit invalidated the older "shallow true-contact" and strict near-miss metrics as proof of real peg-vs-wall reaction. They remain useful historical controller diagnostics, but they are not completion evidence.

Before any public-facing Phase 2 claim, first pass `./scripts/run_launchable_contact_physics_smoke.sh` on an Isaac runtime, pull/archive the log with `./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly`, and confirm `python3 scripts/check_phase2_contact_gate.py` reports PASS. Then regenerate one short trace under the validated dynamic-peg/wall-filtered-force task and rewrite this summary from the new evidence.

## One-line project description

Historical pre-audit wording: extended the Isaac Lab peg-in-hole precursor into a physical peg/socket contact shell, validated guarded remote GPU execution, and produced a shallow contact-labeled scripted result plus strict-gate failure analysis.

## Resume-ready bullets

- Not ready for public use until the contact-physics smoke passes and a fresh trace is regenerated.
- Safe historical claim: built guarded Brev/Launchable GPU workflows with live price comparison, remote Isaac runtime installation, artifact pullback, instance deletion, and final empty-org verification.
- Safe historical claim: implemented and evaluated multiple final-contact controller variants with fixed-seed JSON traces, all currently treated as diagnostics.
- Unsafe until regenerated: "true-contact success", contact-force-based success labels, BC/reset-candidate labels, and any claim that the task has proven wall-reaction insertion.

## Key measured result

Historical shallow contact label, now invalidated as physical-contact proof:

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

This is not yet a final industrial peg-in-hole insertion policy, and the current Phase 2 milestone does not yet prove real physical contact. The immediate blocker is runtime validation of the dynamic-peg / socket-wall contact model. Only after that smoke passes should final-contact control, BC, RL, or public claims be reopened.

## Interview framing

- Why Phase 2 matters: it converts the Phase 1 proxy task into a physically meaningful contact task instead of continuing to tune rewards on a non-contact shell.
- What worked: guarded GPU gates, trace/artifact capture, and a concrete diagnosis of invalid old contact metrics.
- What failed: old contact-force labels did not prove socket-wall reaction, so pre-audit controller/BC results cannot be used as completion evidence.
- What the learned-policy smoke showed: the data/checkpoint/eval pipeline works, but naive one-step BC is not enough for post-handoff contact stabilization.
- What the failure means: the remaining blocker is coupled contact control, not environment setup or quaternion/frame debugging.
- What comes next: pass the contact-physics smoke, regenerate one short validated trace, then decide whether richer demonstrations or learned correction policies are justified.
