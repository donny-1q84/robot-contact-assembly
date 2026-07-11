# Brev Launchable Lifecycle Hold

Date: 2026-06-20

This hold blocks new paid Brev/Launchable creation by default.

Reason:

- `isaac-launchable-b18cd5` / `t7f0c8qh0` reached `STARTING / BUILDING / NOT READY`, then required repeated CLI/UI delete attempts before cleanup was confirmed.
- `isaac-launchable-7ccc42` / `hqo1aftwz` reached `STARTING / BUILDING / NOT READY`, then `UNHEALTHY`, and remained in `DELETING` / `UNHEALTHY` after CLI delete, stop, delete-by-id, and UI delete confirmation.
- Neither attempt reached shell access.
- No RCA bundle was uploaded and no project smoke ran on either attempt.

Do not start another paid Launchable while any workspace is visible in:

```bash
/Users/Shenghan/bin/brev ls instances --json --all
```

After cleanup is confirmed, prefer waiting for Brev service recovery or sending
the incident evidence to Brev support before retrying. If a retry is still
deliberately chosen, it must pass `scripts/paid_compute_preflight.sh` and set:

```bash
RCA_ACK_BREV_LIFECYCLE_RISK=1
RCA_BREV_CREDITS_VERIFIED=1
RCA_PAID_BUDGET_EUR=<explicit-budget>
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour>
RCA_PAID_MAX_MINUTES=<ttl-minutes>
```

That acknowledgement is only for a single consciously chosen retry. It does not
permit controller sweeps, BC, RL, or any job beyond the short contact-physics
smoke gate.

Supporting local tools:

```bash
./scripts/create_brev_lifecycle_incident_bundle.sh
./scripts/check_brev_lifecycle_hold_clearance.sh
./scripts/check_launchable_retry_readiness.sh
```

The clearance script is read-only. It confirms `visible_instances=0` and that
paid preflight is still blocked by this hold before any human considers
removing or bypassing it.
The retry-readiness script is also read-only. It only returns ready when a
single contact-smoke retry has explicit lifecycle-risk acknowledgement plus
budget, hourly estimate, TTL, empty-org state, and current bundle readiness.
