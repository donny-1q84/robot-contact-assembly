# Current Project Status

- Repo: `/Volumes/Extreme Pro/Projects/robot-contact-assembly`
- Branch: `master`
- HEAD: `92465f4 Fix contact physics: weld dynamic peg to hand, wall-filtered forces`
- Runtime source payload scope: `runtime-v1`
- Runtime source payload SHA256: `5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f`
- Paid compute used by this report: none

## Status Checks

| Check | Status | Detail |
| --- | --- | --- |
| Git worktree | DIRTY | 76 changed path(s); review before committing. |
| Local gates | READY | Gate scripts are present; run ./scripts/run_local_quality_checks.sh for enforcement. |
| Brev lifecycle hold | BLOCKED | Active hold file requires service recovery or RCA_ACK_BREV_LIFECYCLE_RISK=1 before any paid retry: /Volumes/Extreme Pro/Projects/robot-contact-assembly/docs/brev_launchable_lifecycle_hold.md |
| Contact-smoke bundle | READY | Latest bundle matches current runtime payload scope/hash: /Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T12-44-48Z.tar.gz |
| Phase 2 contact gate | PASS | [phase2-contact-gate] PASS: validated contact-physics smoke evidence: /Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/launchable_logs/contact_physics_smoke.log |
| Historical docs | READY | Old Phase 2 docs are marked as historical/superseded. |
| Generated metadata | READY | No existing tracked egg-info files remain. |

## Current Decision

The Phase 2 contact-smoke gate is satisfied. Do not start new paid Brev work until the active lifecycle hold is deliberately cleared or acknowledged for a specific short run with explicit budget, TTL, watchdog, artifact pullback, immediate deletion, and final empty-org confirmation.

## Next Allowed Action

Regenerate exactly one short scripted trace under the validated task, then refresh contact-validity and demo-coverage reports before reopening controller/BC/RL work.

## Commands

```bash
./scripts/brev_paid_safety_status.sh
./scripts/run_local_quality_checks.sh
python3 scripts/check_phase2_contact_gate.py
RCA_BREV_LOGIN_EMAIL=<email> ./scripts/refresh_brev_login.sh
RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_BUDGET_EUR=<budget> RCA_PAID_ESTIMATED_EUR_PER_HOUR=<hourly-estimate> ./scripts/check_launchable_retry_readiness.sh
RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_BUDGET_EUR=<budget> RCA_PAID_ESTIMATED_EUR_PER_HOUR=<hourly-estimate> ./scripts/prepare_contact_smoke_run.sh
./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly
./scripts/archive_contact_smoke_log.sh <pulled-contact_physics_smoke.log>
```
