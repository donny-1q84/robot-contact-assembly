# BC Evaluation Trace Audit

## Gates

```text
target: xy < 0.0050 m, z < 0.0450 m, rot < 0.1800 rad, contact >= 0.500
near:   xy < 0.0150 m, z < 0.0600 m, rot < 0.3500 rad, contact >= 0.200
```

## Summary

| run | action | preload | bc_steps | bc_success | bc_near_frac | bc_longest_near | handoff_miss | bc_best_miss | bc_final_miss | best_delta | final_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-18T21-34-10Z | legacy-absolute | 0 | 400 | 0 | 0.0000 | 0 | n/a | 21.0692 | 57.3366 | n/a | n/a |
| 2026-05-19T05-59-43Z | legacy-absolute | 1544 | 400 | 0 | 0.0125 | 5 | 0.0319 | 0.1865 | 8.4199 | 0.1547 | 8.3880 |

## Interpretation

- `bc_near_frac` measures how much of the BC-controlled rollout stayed in the relaxed near-contact band.
- `best_delta` and `final_delta` are relative to the handoff miss when a preload stage exists; positive values mean BC made the state worse.
- Legacy all-trace BC has no preload handoff, so its deltas are `n/a`.

## Decision

The previous BC policies were not contact-stabilizing policies:

- all-trace BC never entered the relaxed near-contact band during its 400-step rollout;
- staged best-window BC entered near-contact only briefly (`5` consecutive steps max);
- staged best-window BC degraded from handoff miss `0.0319` to final miss `8.4199`.

The next learned-policy run should use the near-contact residual-current dataset and should be judged by:

```text
near_contact_fraction
longest_near_contact_streak
best_vs_handoff_strict_miss_delta
final_vs_handoff_strict_miss_delta
```

Strict `success_step != null` remains a stretch target, not the first pass/fail condition for the next smoke.
