# AGENTS.md

## Project Hard Gate
- This repository is currently blocked on contact-physics runtime validation.
- The 2026-06-11 audit found that the historical Phase 2 peg/socket contact metrics were not trustworthy: the old peg/wall setup did not prove real peg-vs-wall reaction, and the old contact force was not proven to be a wall-only signal.
- Commit `92465f4` implements the intended fix path locally: a dynamic peg welded to the hand, no per-step peg teleportation, and wall-filtered contact forces. This is still not sufficient evidence until the Isaac runtime wall-reaction smoke passes.
- Do not run paid GPU/Brev/AWS work, controller sweeps, BC training/evaluation, or RL training until `scripts/run_launchable_contact_physics_smoke.sh` passes on an Isaac runtime and its log is archived.
- Use `python3 scripts/check_phase2_contact_gate.py` as the fail-closed phase gate. Until it reports PASS, the only allowed paid action is the shortest contact-smoke validation run with an active watchdog and deletion plan.

## Required Next Technical Step
- Validate the implemented environment fix by running the contact-physics smoke on a real Isaac runtime:
  - `./scripts/run_launchable_contact_physics_smoke.sh`
- After pulling the log back locally, archive and verify it with:
  - `./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly`
  - `./scripts/archive_contact_smoke_log.sh <pulled-contact_physics_smoke.log>`
  - `python3 scripts/check_phase2_contact_gate.py`
- The archived smoke log must show all required PASS markers and phase markers: `phase free-space-settle: end`, attach, free-space, `phase local-guide-reanchor: end`, local-guide reanchored, free-space-reanchored, `phase press-hold: end`, press-force, press-tracking, press-blocked, press-no-clip, `phase retreat-hold: end`, release, joint-integrity, `phase-sequence: PASS`, `Contact physics smoke completed: all checks passed`, plus the wrapper completion marker `[contact-smoke] completed: contact physics is real`.
- The smoke log must include source evidence and the current runtime `source_payload_sha256`. The runtime payload hash is the hard freshness check; documentation-only commits should not force another paid smoke.
- If the smoke fails, fix the environment locally; do not tune controllers or policies around the failure.
- If the smoke passes, regenerate one short scripted trace under the validated task before trusting any success, contact, BC, or reset-candidate metric.
- Preserve these invariants: dynamic peg attached through physics, no per-step peg teleport, socket guide walls as colliders, and contact gates routed through wall-filtered force.

## Experiment Rules
- Before trusting a metric, trace it to the exact code/data/sensor source.
- Before any expensive run, execute a semantic smoke test and at least one negative control.
- If moving or disabling the wall does not change the contact metric, stop and debug the task definition before any controller or policy work.
- Treat existing "true-contact", strict near-miss, near-contact BC, and final-contact candidate artifacts as diagnostic history only until regenerated under a physically valid contact model.

## Paid Compute Guard
- Paid compute requires an explicit budget, timeout, artifact pullback plan, and deletion/cleanup monitor.
- If Brev CLI auth is expired or instance state cannot be verified, do not create or continue paid work.
- Use `scripts/refresh_brev_login.sh` to refresh Brev/NVIDIA CLI auth before paid preflight. It is read-only after login and must not create resources.
- Use `scripts/brev_paid_safety_status.sh` as the read-only safety snapshot before and after any paid/Brev work; it must show `visible_instances=0` when no paid job is intentionally running.
- Before any Brev/Launchable paid action, run `scripts/paid_compute_preflight.sh` with `RCA_BREV_CREDITS_VERIFIED=1`, `RCA_PAID_BUDGET_EUR`, `RCA_PAID_ESTIMATED_EUR_PER_HOUR`, `RCA_PAID_MAX_MINUTES`, and `RCA_PAID_RUN_PURPOSE` set. Only set the credit marker after manually checking the Brev UI/org balance, because the CLI has no read-only credit-balance command. The estimated max cost must fit inside the explicit budget. The only allowed purpose before the Phase 2 contact gate passes is `contact_physics_smoke`.
- Do not add bypass flags for phase-gate checks, nonempty Brev org checks, or remote-operation preflight completion; those guards must fail closed.
- Helpers that operate on an existing Brev environment must run `scripts/remote_operation_preflight.sh`; before the contact gate passes, the only accepted remote-operation purpose is `RCA_REMOTE_OPERATION_PURPOSE=contact_physics_smoke`.
- Launchable workload scripts other than `scripts/run_launchable_contact_physics_smoke.sh` must call `scripts/launchable_post_contact_gate.sh` before running any Isaac evaluation, matrix, controller, BC, or RL work.

## Status Command
- Use `python3 scripts/project_status_report.py` for the current repo decision snapshot. It is read-only and does not call Brev or Isaac.
- `./scripts/run_local_quality_checks.sh` also runs project structure checks through `scripts/check_project_structure.py`, contact-physics wiring checks through `scripts/check_contact_physics_wiring.py`, and offline gate behavior tests through `scripts/test_local_gates.py`; these tests must not call Brev or Isaac.
- Use `RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_BUDGET_EUR=<budget> RCA_PAID_ESTIMATED_EUR_PER_HOUR=<hourly-estimate> ./scripts/prepare_contact_smoke_run.sh` before the one allowed paid contact-smoke run. It runs local quality and paid preflight, but does not create a Launchable unless explicitly told to start the watchdog.
- Use `./scripts/check_launchable_retry_readiness.sh` as a read-only final check before any deliberate one-run Launchable retry; it must remain blocked unless the lifecycle risk is explicitly acknowledged for that single smoke retry.
- Use `./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly` as the preferred pullback path after the remote smoke. It is explicitly scoped to the one allowed pre-gate artifact.
- Use `./scripts/archive_contact_smoke_log.sh <pulled-contact_physics_smoke.log>` after the remote smoke finishes; it validates the source log before installing it as `artifacts/launchable_logs/contact_physics_smoke.log`.
