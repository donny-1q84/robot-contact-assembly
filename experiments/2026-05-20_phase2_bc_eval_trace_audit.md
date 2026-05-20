# Handoff Controller Evaluation Trace Audit

## Gates

```text
target: xy < 0.0050 m, z < 0.0450 m, rot < 0.1800 rad, contact >= 0.500
near:   xy < 0.0150 m, z < 0.0600 m, rot < 0.3500 rad, contact >= 0.200
```

## Summary

| run | controller | preload | controlled_steps | controlled_success | near_frac | longest_near | handoff_miss | best_miss | final_miss | best_delta | final_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-18T21-34-10Z | legacy-absolute | 0 | 400 | 0 | 0.0000 | 0 | n/a | 21.0692 | 57.3366 | n/a | n/a |
| 2026-05-19T05-59-43Z | legacy-absolute | 1544 | 400 | 0 | 0.0125 | 5 | 0.0319 | 0.1865 | 8.4199 | 0.1547 | 8.3880 |
| 2026-05-20T04-32-33Z | residual-current | 1544 | 400 | 0 | 0.0175 | 6 | 0.0319 | 0.3157 | 45.5874 | 0.2839 | 45.5555 |
| 2026-05-20T19-52-13Z_current-joint | current-joint | 1544 | 400 | 0 | 0.0000 | 0 | 0.0319 | 0.4436 | 58.8828 | 0.4117 | 58.8510 |

## Interpretation

- `near_frac` measures how much of the controlled rollout stayed in the relaxed near-contact band.
- `best_delta` and `final_delta` are relative to the handoff miss when a preload stage exists; positive values mean the controller made the state worse.
- Legacy all-trace BC has no preload handoff, so its deltas are `n/a`.
- `current-joint` hold is worse than the staged learned policies on every controlled near-contact metric.

## Decision

The handoff state is not passively stable. The next useful branch should add active contact maintenance or collect richer post-contact demonstrations; do not spend another run on unchanged static hold or one-step BC.
