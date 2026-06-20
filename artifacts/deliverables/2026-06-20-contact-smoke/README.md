# 2026-06-20 Contact Smoke Deliverables

This directory contains the successful Phase 2 contact-smoke evidence from the
official AWS Isaac Launchable run `isaac-launchable-gate-5ecb` / `ak7egbprx`.

## Result

- Run id: `2026-06-20T13-01-54Z-gate`
- Runtime source payload: `5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f`
- Smoke exit: `0`
- Gate validation: PASS
- Brev cleanup: `SAFE_NO_VISIBLE_PAID_INSTANCE`

## Files

- `contact_smoke_success_log_replay.mp4`: local replay visualization generated
  from the successful log. This is not an Isaac viewport/camera recording.
- `contact_physics_smoke_2026-06-20T13-01-54Z-gate.log`: primary successful
  smoke log.
- `contact_physics_smoke_2026-06-20T13-01-54Z-gate.exit`: remote wrapper exit
  sidecar.
- `rca-pull-isaac-launchable-gate-ak7egbprx.tar.gz`: pulled remote evidence
  archive.
- `source_manifest.txt`: Launchable bundle source manifest.
- `nvidia_smi.txt`: remote GPU/runtime snapshot.
- `contact_gate_validation.txt`: `check_phase2_contact_gate.py --run-local-quality`
  output.
- `local_quality_checks.txt`: local no-Isaac quality gate output.
- `brev_paid_safety_status.txt`: final Brev cleanup/safety snapshot.
- `project_status_report.md`: current repo status snapshot.
- `SHA256SUMS.txt`: checksums for all deliverable files above.

## Key Smoke Markers

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE press-force: PASS
CONTACT-SMOKE press-tracking: PASS
CONTACT-SMOKE press-blocked: PASS
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
CONTACT-SMOKE phase-sequence: PASS
Contact physics smoke completed: all checks passed.
[contact-smoke] completed: contact physics is real
```
