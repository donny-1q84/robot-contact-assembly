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
| 2026-05-20T04-32-33Z | residual-current | 1544 | 400 | 0 | 0.0175 | 6 | 0.0319 | 0.3157 | 45.5874 | 0.2839 | 45.5555 |

## Interpretation

- `bc_near_frac` measures how much of the BC-controlled rollout stayed in the relaxed near-contact band.
- `best_delta` and `final_delta` are relative to the handoff miss when a preload stage exists; positive values mean BC made the state worse.
- Legacy all-trace BC has no preload handoff, so its deltas are `n/a`.
- The residual-current policy slightly improves relaxed near-contact dwell time over best-window BC, but it worsens both best and final strict-miss deltas. This is not a useful controller improvement.

## Decision

Stop one-step BC retries on the current trace archive. The next learned-policy run must change either the data, the observation history, or the controller structure before using another paid GPU session.
