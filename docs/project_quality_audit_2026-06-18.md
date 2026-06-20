# Project Quality Audit - 2026-06-18

## Scope

This audit uses the current local worktree as the source of truth:

- repo: `/Volumes/Extreme Pro/Projects/robot-contact-assembly`
- branch: `master`
- HEAD at audit start: `92465f4 Fix contact physics: weld dynamic peg to hand, wall-filtered forces`
- paid compute used: none

## Executive Decision

The project should not proceed to controller sweeps, BC, RL, or any broad paid GPU run yet.

The immediate next step is a single semantic validation: run the wall-reaction contact-physics smoke on a real Isaac runtime and archive its log. The local code now contains the intended environment fix, but completion is still unproven until that smoke passes.

If the smoke passes, regenerate one short scripted trace under the validated task and only then re-open controller/data/policy work. If it fails, fix the environment model first.

Use `python3 scripts/check_phase2_contact_gate.py` as the fail-closed local decision point. It must report `BLOCKED` until a valid archived `contact_physics_smoke.log` contains the required PASS markers plus the wrapper completion marker. The current marker set is: phase free-space-settle end, attach, free-space, phase local-guide-reanchor end, local-guide reanchored, free-space-reanchored, phase press-hold end, press-force, press-tracking, press-blocked, press-no-clip, phase retreat-hold end, release, joint-integrity, `CONTACT-SMOKE phase-sequence: PASS`, `Contact physics smoke completed: all checks passed`, and `[contact-smoke] completed: contact physics is real`. The smoke log source evidence must include the current runtime `source_payload_sha256`; stale PASS logs from older runtime code remain blocked, but documentation-only commits should not force another paid smoke.

## 2026-06-19 Local Guard Overlay

After the initial audit, the local no-Isaac gates were hardened further without using paid compute:

- `scripts/run_local_quality_checks.sh` now runs with `PYTHONDONTWRITEBYTECODE=1`, checks Python syntax without `py_compile`, and fails if `__pycache__`, `.pyc`, `.DS_Store`, or `*.egg-info` generated files are present.
- `scripts/check_project_policy_compliance.py` now statically rejects scripts that perform direct `ssh`/`rsync`/`scp`/`sftp` or `brev exec/copy/port-forward/shell/open` unless they route through `scripts/remote_operation_preflight.sh`, `scripts/remote_common.sh` plus `rca_init_remote_vars`, or the paid-compute preflight.
- `scripts/run_remote_eval_final_contact_candidate_bc.sh` was brought under the remote-operation preflight before its manifest upload step.
- `scripts/contact_physics_smoke.py` now emits a separate `press-no-clip` marker so the archived smoke explicitly proves bounded geometric penetration, not only wall-force and blocked-depth behavior.
- `scripts/check_phase2_contact_gate.py` now rejects stale smoke logs whose runtime `source_payload_sha256` does not match the current runtime source state. The logged git/source-manifest HEAD remains provenance, not a documentation-change invalidation trigger.
- Guard bypasses were removed: paid preflight no longer accepts phase-gate skip or nonempty-org overrides, and `remote_common.sh` no longer trusts externally supplied remote-preflight completion state.
- Non-contact-smoke Launchable workload scripts now call `scripts/launchable_post_contact_gate.sh`, so even inside a paid Launchable runtime, historical evaluation/matrix/probe scripts remain blocked until the current runtime source payload has an archived contact-smoke PASS log.
- Local preauth bundles match `artifacts/launchable/robot-contact-assembly-contact-smoke-manual-preauth-*.tar.gz`. They are convenience packages only; they do not replace `scripts/prepare_contact_smoke_run.sh` or the Brev auth/empty-org paid preflight. For a real paid run, use the exact bundle path printed by `scripts/prepare_contact_smoke_run.sh`. Bundles exclude generated caches and local tool configuration such as `.claude/`; `source_payload_sha256` fingerprints the `runtime-v1` source scope that affects the contact smoke, not documentation-only bundle content.

## Evidence Checked

| Area | Evidence | Result |
| --- | --- | --- |
| Git state | `git status --short`, `git log --oneline -12` | Clean tree at audit start; HEAD was `92465f4` |
| Geometry constants | `python3 scripts/check_contact_geometry_constants.py` | Passed |
| Python syntax | `./scripts/run_local_quality_checks.sh` source-compile pass | Passed without writing `.pyc` |
| Shell syntax | `bash -n` over `scripts/*.sh` | Passed for 87 shell scripts |
| Unit tests | searched `tests/`, `test_*.py`, `*_test.py` | No test suite present |
| Contact fix wiring | `peg_in_hole_env_cfg.py`, `assets.py`, `observations.py`, `events.py` | Dynamic peg, fixed joint, reset-only sync, wall-filtered contact are implemented |
| Contact smoke | `scripts/contact_physics_smoke.py`, `scripts/run_launchable_contact_physics_smoke.sh` | Smoke exists and checks attach/free/press/press-no-clip/release markers plus wrapper completion, but no pass artifact was found locally |
| Phase gate | `scripts/check_phase2_contact_gate.py` | Added fail-closed checker; it blocks downstream work until a valid smoke PASS log exists |
| Paid-compute preflight | `scripts/paid_compute_preflight.sh` | Added fail-closed budget/TTL/auth/empty-org/phase-gate guard before any paid Brev/Launchable action |
| Remote-operation preflight | `scripts/remote_operation_preflight.sh`, `scripts/check_project_policy_compliance.py` | Existing-env remote helpers are statically required to use a preflight or shared remote gate |
| Generated-cache and local-config hygiene | `scripts/run_local_quality_checks.sh`, `scripts/create_launchable_bundle.sh`, `scripts/source_payload_fingerprint.py` | Local quality fails on generated caches; Launchable bundles exclude generated metadata/cache files and local tool config such as `.claude/` |
| Historical contact validity | `artifacts/analysis/contact_physics_validity_2026-06-11.md` | Old contact metrics are not valid proof of socket-wall reaction |
| Probe archive summary | regenerated `scripts/summarize_launchable_probe_archives.py` locally | 31 probe summaries scanned, all `fail_closed` |
| Brev state | `/Users/Shenghan/bin/brev ls instances --json --all` | CLI is logged out; do not create or continue paid work in this state |

## P0 Blockers

1. Contact physics is implemented but not runtime-validated.

   The current code fixes the known failure mode, but no local artifact proves the Isaac runtime actually blocks the dynamic peg on the wall, prevents meaningful clipping, and reports wall-only reaction. The pass condition is `./scripts/run_launchable_contact_physics_smoke.sh` producing all PASS markers plus the wrapper completion marker.

2. Historical success claims are unsafe.

   The old "shallow true-contact" and strict near-miss results were generated before the 2026-06-11 audit. Keep them as controller-development history only. Do not use them as completion, CV, or training-data evidence until regenerated after the wall-reaction smoke passes.

3. Paid compute is blocked while Brev auth is expired.

   The Brev CLI prompts for login and fails with EOF in noninteractive use. This means watchdog deletion cannot be trusted from the CLI until login is refreshed.

4. Paid compute is blocked without explicit preflight evidence.

   `scripts/paid_compute_preflight.sh` now requires `RCA_ALLOW_PAID_BREV_CREATE=1`, `RCA_BREV_CREDITS_VERIFIED=1`, `RCA_PAID_BUDGET_EUR`, `RCA_PAID_ESTIMATED_EUR_PER_HOUR`, `RCA_PAID_MAX_MINUTES`, a successful Brev instance query, an empty visible org, and an estimated max cost inside the explicit budget. For anything except `RCA_PAID_RUN_PURPOSE=contact_physics_smoke`, it also requires the Phase 2 contact gate to pass. These checks have no supported skip or nonempty-org bypass.

## P1 Structural Issues

1. Documentation has conflicting current-state summaries.

   `README.md` and the top of `docs/current_project_handoff.md` still emphasized older contact results. This audit updates them, but future readers should use this file plus `AGENTS.md` as the current state summary.

2. The project has no automated local test suite.

   The repo has useful semantic scripts, but no `tests/` suite or external CI. The current no-Isaac gate is:

   ```bash
   ./scripts/run_local_quality_checks.sh
   ```

   This local gate now covers contact wiring, paid/remote policy, offline gate behavior, Python/shell syntax, whitespace, and generated-cache hygiene.

3. Runtime task entrypoints are broader than the older README list.

   The actual registered task IDs include Rel IK, Abs IK, and JointPos contact variants. Running the wrong task is easy if using older notes.

4. Append-only experiment logs are too long for next-step decisions.

   `README.md` and `docs/current_project_handoff.md` are valuable but too long and partly historical. Future work should append detailed logs there only after updating a short current-state section.

5. Brev auth is the remaining external gate before the next paid preflight.

   Local preparation is ready, but `scripts/prepare_contact_smoke_run.sh` still cannot pass until `/Users/Shenghan/bin/brev ls instances --json --all` succeeds and the visible org is empty.

## P2 Repository Hygiene

1. Generated package metadata was tracked.

   The tracked `source/robot_contact_assembly_tasks/robot_contact_assembly_tasks.egg-info/*` files are generated packaging output and should not remain in version control.

2. Artifacts are intentionally local and ignored.

   This is acceptable for cost-heavy robotics work, but any claim in docs should point to a specific local artifact path and explain whether the artifact is tracked or ignored.

## Next Action Plan

1. Refresh NVIDIA/Brev login only when ready to run the smoke.
2. Before creating any paid environment, run the paid-compute preflight:

   ```bash
   RCA_ALLOW_PAID_BREV_CREATE=1 \
   RCA_BREV_CREDITS_VERIFIED=1 \
   RCA_PAID_BUDGET_EUR=<explicit-budget> \
   RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
   RCA_PAID_MAX_MINUTES=60 \
   RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
     ./scripts/paid_compute_preflight.sh
   ```

3. Start the UI/org watchdog:

   ```bash
   RCA_ALLOW_PAID_BREV_CREATE=1 \
   RCA_BREV_CREDITS_VERIFIED=1 \
   RCA_PAID_BUDGET_EUR=<explicit-budget> \
   RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
   RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
   RCA_BREV_WATCHDOG_MAX_MINUTES=60 \
     scripts/start_brev_ui_launchable_watchdog.sh
   ```

4. Create the smallest AWS Launchable/Isaac runtime suitable for the smoke.
5. Run only:

   ```bash
   ./scripts/run_launchable_contact_physics_smoke.sh
   ```

6. Pull, install, and verify `artifacts/launchable_logs/contact_physics_smoke.log` with `./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly`.
7. If the log was obtained by some other route, install and verify it locally with `./scripts/archive_contact_smoke_log.sh <pulled-contact_physics_smoke.log>`.
8. Delete the instance immediately and confirm `brev ls instances --json --all` returns no visible workspace.
9. Run `python3 scripts/check_phase2_contact_gate.py` locally against the archived log.
10. If and only if the gate passes, run one short scripted trace under the validated task and regenerate the contact-validity and demo-coverage reports.

## Definition of Done for This Phase

This phase is done only when all are true:

- Contact-physics smoke passes on Isaac runtime.
- The pass log is archived locally.
- The pass log includes the full current marker set, including `press-no-clip`.
- A fresh post-smoke trace is generated under the validated task.
- Contact metrics in that trace come from wall-filtered `force_matrix_w`.
- Old pre-audit contact metrics are clearly labeled as historical in user-facing docs.
- No paid instance remains visible after cleanup.
