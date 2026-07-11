# Peg-In-Hole Success Trace Deliverable

Date: 2026-06-21

This deliverable contains the first post-smoke trace that passes the strict
peg-in-hole video-candidate gate under the validated contact-physics task.

## Result

| Field | Value |
|---|---|
| Source trace | `video_trace.json` |
| Summary | `video_summary.json` |
| First success step | `167` |
| Final success rate | `1.0` |
| Final lateral error | `0.0015925065381452441 m` |
| Final axial error | `0.007546612061560154 m` |
| Final rotation error | `0.054073676466941833 rad` |
| Final contact force | `0.5527539253234863 N` |
| Contact-smoke gate | PASS |
| Peg video candidate gate | PASS |
| Final contact boundary gate | PASS |
| Trace frame audit | PASS |
| Action response gate | PASS |
| Brev cleanup | `SAFE_NO_VISIBLE_PAID_INSTANCE` |

## Files

| File | Purpose |
|---|---|
| `video_trace.json` | Full scripted trace used by all validators |
| `video_summary.json` | Compact rollout summary |
| `peg_video_candidate_validation.txt` | Fresh `check_peg_in_hole_video_candidate.py` output |
| `final_contact_boundary_validation.txt` | Fresh final-contact boundary diagnostic output |
| `trace_frame_alignment_validation.txt` | Fresh frame-alignment audit output |
| `action_response_validation.txt` | Fresh action-response validator output |
| `*_check.log` | Validator logs pulled from the remote run |
| `contact_physics_smoke.log` | Canonical contact-smoke PASS log |
| `peg_in_hole_trace_render.mp4` | Local diagnostic MP4 rendered from `video_trace.json` |
| `peg_in_hole_trace_render.summary.json` | Metadata for the rendered diagnostic MP4 |
| `preview_final.png` | Final-frame preview showing `SUCCESS TRUE` |
| `local_quality_checks.txt` | Local quality gate output at packaging time |
| `brev_paid_safety_status.txt` | Final no-visible-paid-instance safety snapshot |
| `project_status_report.md` | Read-only project status snapshot at packaging time |
| `SHA256SUMS.txt` | Checksums for this deliverable |

## Important Caveat

`peg_in_hole_trace_render.mp4` is a trace-rendered diagnostic visualization, not
Isaac viewport/camera footage. The success claim comes from `video_trace.json`
and the validators listed above. The earlier real Isaac viewport deliverable is
kept separately for visual review of the scene, not as insertion-success proof.

## Reproduce Local Validation

```bash
python3 scripts/check_peg_in_hole_video_candidate.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
python3 scripts/audit_trace_frame_alignment.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
python3 scripts/check_scripted_action_response_trace.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json --min-command-norm 0.0002 --stop-after-first-success
python3 scripts/render_trace_video.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json artifacts/videos/trace_rendered/2026-06-21T20-05-25Z/peg_in_hole_trace_render.mp4
```
