# Contact Demonstration Coverage Audit

## Gate

```text
target gate: xy < 0.0050 m, z < 0.0450 m, rot < 0.1800 rad, contact >= 0.500
near gate:   xy < 0.0150 m, z < 0.0600 m, rot < 0.3500 rad, contact >= 0.200
```

## Aggregate

```text
traces: 18
steps: 28823
target-gate passing steps: 0
traces with target-gate steps: 0
near-contact steps: 3227
traces with near-contact steps: 14
```

## Closest Target-Gate Steps

| run | task | mode | socket | step | phase | miss | lat | ax | rot | contact | near_streak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-17T23-32-18Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1543 | contact-retention | 0.0320 | 0.0052 | 0.0413 | 0.1812 | 0.5298 | 111 |
| 2026-05-17T22-00-19Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1541 | contact-retention | 0.0421 | 0.0043 | 0.0412 | 0.1842 | 0.5263 | 111 |
| 2026-05-17T18-25-39Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1539 | polish | 0.0992 | 0.0039 | 0.0421 | 0.1899 | 0.5728 | 111 |
| 2026-05-17T20-54-06Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1539 | polish | 0.0992 | 0.0039 | 0.0421 | 0.1899 | 0.5728 | 111 |
| 2026-05-17T21-33-46Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1539 | polish | 0.0992 | 0.0039 | 0.0421 | 0.1899 | 0.5728 | 111 |
| 2026-05-17T22-30-33Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1543 | contact-retention | 0.1070 | 0.0061 | 0.0403 | 0.1787 | 1.7956 | 111 |
| 2026-05-17T19-47-06Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.220 | 1538 | polish | 0.1093 | 0.0047 | 0.0419 | 0.1909 | 0.6927 | 111 |
| 2026-05-17T16-51-25Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.190 | 1275 | polish | 0.1143 | 0.0041 | 0.0423 | 0.1914 | 1.7236 | 210 |
| 2026-05-17T18-54-02Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.240,0.030,0.220 | 1586 | insert | 0.5472 | 0.0051 | 0.0399 | 0.2337 | 1.7829 | 50 |
| 2026-05-17T17-21-50Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.190 | 1274 | polish | 0.5844 | 0.0021 | 0.0409 | 0.2384 | 5.2523 | 11 |
| 2026-05-17T06-08-13Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.190 | 1483 | insert | 0.5858 | 0.0109 | 0.0399 | 0.1791 | 1.7109 | 77 |
| 2026-05-17T01-52-32Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 0.220,0.040,0.190 | 774 | insert | 0.7574 | 0.0061 | 0.0419 | 0.2449 | 2.0953 | 19 |

## Traces With Target-Gate Passing Steps

_No target-gate passing steps._

## Sustained Near-Contact Traces

| run | task | mode | near_steps | longest_near | best_step | best_miss | final_delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-17T16-51-25Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 520 | 210 | 1275 | 0.1143 | 1.4893 |
| 2026-05-17T23-32-18Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 269 | 111 | 1543 | 0.0320 | 2.6647 |
| 2026-05-17T22-00-19Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 269 | 111 | 1541 | 0.0421 | 2.6360 |
| 2026-05-17T18-25-39Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 265 | 111 | 1539 | 0.0992 | 0.3086 |
| 2026-05-17T20-54-06Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 265 | 111 | 1539 | 0.0992 | 2.4774 |
| 2026-05-17T21-33-46Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 265 | 111 | 1539 | 0.0992 | 2.5084 |
| 2026-05-17T22-30-33Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 272 | 111 | 1543 | 0.1070 | 2.5749 |
| 2026-05-17T19-47-06Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 260 | 111 | 1538 | 0.1093 | 0.0000 |
| 2026-05-17T20-18-33Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 209 | 111 | 1251 | 0.7968 | 47.5895 |
| 2026-05-17T06-08-13Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 471 | 77 | 1483 | 0.5858 | 0.8550 |
| 2026-05-17T18-54-02Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 111 | 50 | 1586 | 0.5472 | 0.1303 |
| 2026-05-17T01-52-32Z | RCA-PegInHole-Franka-JointPos-Contact-Play-v0 | joint-ik | 22 | 19 | 774 | 0.7574 | 2.4468 |

## IL Interpretation

- If a trace has many near-contact steps but few or no target-gate passing steps, it is useful for approach/contact-retention data but weak as a final insertion success label.
- A positive final_delta means the rollout drifted away after its best contact state; one-step BC trained on that window can learn the approach but still destabilize after handoff.
- Use this report to choose demonstration sources before spending GPU time on another learned-policy run.

## Decision

Do not treat the current `JointPos` scripted trace archive as a success-demonstration dataset. It has enough near-contact data to train a contact approach/refinement prior, but it has zero target-gate passing samples under the learned-policy gate used by the BC evaluator.

The next data step should be one of:

- Collect additional demonstrations from a reset state already close to the best near-contact window, with the explicit goal of producing target-gate passing samples.
- Relax the first learned-policy target to sustained near-contact and train only a stabilization prior, not a final insertion policy.
- Switch from direct BC to a residual/temporal policy objective that is evaluated against post-handoff degradation, not just supervised loss.
