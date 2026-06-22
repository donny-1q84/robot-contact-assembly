# Current Project Status

- Repo: `/Volumes/Extreme Pro/Projects/robot-contact-assembly`
- Branch: `codex/contact-smoke-gate-pass`
- HEAD: `06dd385 Add real Isaac viewport video deliverable`
- Runtime source payload scope: `runtime-v1`
- Runtime source payload SHA256: `5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f`
- Paid compute used by this report: none

## Status Checks

| Check | Status | Detail |
| --- | --- | --- |
| Git worktree | DIRTY | 38 changed path(s); review before committing. |
| Local gates | READY | Gate scripts are present; run ./scripts/run_local_quality_checks.sh for enforcement. |
| Brev lifecycle hold | BLOCKED | Active hold file requires service recovery or RCA_ACK_BREV_LIFECYCLE_RISK=1 before any paid retry: /Volumes/Extreme Pro/Projects/robot-contact-assembly/docs/brev_launchable_lifecycle_hold.md |
| Contact-smoke bundle | READY | Latest bundle matches current runtime payload scope/hash: /Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/launchable/robot-contact-assembly-contact-smoke-gate-test.tar.gz |
| Phase 2 contact gate | PASS | [phase2-contact-gate] PASS: validated contact-physics smoke evidence: /Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/launchable_logs/contact_physics_smoke.log |
| Post-smoke insertion trace | PASS | Latest trace reports insertion success at /Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_summary.json: success_step=167, final_success_rate=1.000. |
| Action semantics probe | PASS | Latest action-semantics probe: /Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/videos/trace_only/2026-06-21T09-49-34Z/video_trace.json; bad_steps=0/8, min_cosine=0.10695686554840875, command_delta=[0.0, 0.0, 0.0015000104904174805], actual_delta=[-5.793571472167969e-05, -9.641866199672222e-06, 6.318092346191406e-06]. |
| Historical docs | READY | Old Phase 2 docs are marked as historical/superseded. |
| Generated metadata | READY | No existing tracked egg-info files remain. |

## Current Decision

The Phase 2 contact-smoke gate and post-smoke insertion trace are satisfied. The current milestone is no longer blocked on controller insertion evidence; the remaining optional gap is only real Isaac viewport/camera footage of the same semantic setup.

## Next Allowed Action

The Phase 2 contact-smoke gate, action/trace validators, and post-smoke insertion trace are satisfied. The current required evidence is packaged in artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/. Do not open another paid GPU run for this milestone unless the explicit next goal is a full Isaac viewport/camera recording, with a full runtime profile and a fresh budget/cleanup plan.

## Commands

```bash
./scripts/brev_paid_safety_status.sh
./scripts/run_local_quality_checks.sh
python3 scripts/check_phase2_contact_gate.py
python3 scripts/check_peg_in_hole_video_candidate.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
python3 scripts/audit_trace_frame_alignment.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
python3 scripts/check_scripted_action_response_trace.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json --min-command-norm 0.0002 --stop-after-first-success
python3 scripts/render_trace_video.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json artifacts/videos/trace_rendered/2026-06-21T20-05-25Z/peg_in_hole_trace_render.mp4
python3 scripts/check_action_calibration_summary.py artifacts/calibration/relative_ik_action/latest_seed_42.json
python3 scripts/joint_response_control.py artifacts/calibration/joint_position_action/latest_seed_42.json --desired-delta 0,0,-0.0015
./scripts/run_remote_joint_response_calibration.sh <env-name> /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
./scripts/run_remote_joint_response_semantics_probe_suite.sh <env-name> /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
./scripts/recreate_brev_and_run_joint_response_semantics_probe_suite.sh
# no unchanged socket-insertion/final-contact/action-semantics paid trace is currently approved
# do not rerun ./scripts/recreate_brev_and_run_action_semantics_probe_suite.sh unchanged
RCA_BREV_LOGIN_EMAIL=<email> ./scripts/refresh_brev_login.sh
RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_BUDGET_EUR=<budget> RCA_PAID_ESTIMATED_EUR_PER_HOUR=<hourly-estimate> ./scripts/check_launchable_retry_readiness.sh
RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_BUDGET_EUR=<budget> RCA_PAID_ESTIMATED_EUR_PER_HOUR=<hourly-estimate> ./scripts/prepare_contact_smoke_run.sh
./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly
./scripts/archive_contact_smoke_log.sh <pulled-contact_physics_smoke.log>
```
