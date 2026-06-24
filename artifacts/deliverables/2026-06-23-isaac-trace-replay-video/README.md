# Isaac Trace-Replay Peg-In-Hole Video Deliverable

Date: 2026-06-23

This deliverable contains an Isaac Sim / Isaac Lab rendered replay video for
the validated peg-in-hole success trace from
`artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json`.

## Result

| Field | Value |
|---|---|
| Source semantic trace | `../2026-06-21-peg-in-hole-success-trace/video_trace.json` |
| Isaac replay video | `isaac_trace_replay_trimmed.mp4` |
| Raw Isaac replay video | `isaac_trace_replay_raw.mp4` |
| Video resolution | `1280x720` |
| Trimmed video duration | `5.5 s` |
| Trimmed video frames | `165` |
| Raw video duration | `6.1 s` |
| Raw video frames | `183` |
| Source success step | `167` |
| Source best axial error | `0.007546612061560154 m` |
| Source best lateral error | `0.00014721538173034787 m` |
| Source best rotation error | `0.0003452669770922512 rad` |
| Source max contact force | `1.0929346084594727 N` |
| Brev cleanup | `SAFE_NO_VISIBLE_PAID_INSTANCE` |

## Files

| File | Purpose |
|---|---|
| `isaac_trace_replay_trimmed.mp4` | Review video with initial black frames trimmed |
| `isaac_trace_replay_raw.mp4` | Raw Isaac-rendered replay pulled from Brev |
| `keyframes_montage.png` | Four-frame visual summary of the approach/insertion motion |
| `replay_summary_recovered.json` | Summary recovered from the source trace and `ffprobe` |
| `peg_video_candidate_validation.txt` | Semantic peg video-candidate gate output for the source trace |
| `final_contact_boundary_validation.txt` | Final contact-boundary diagnostic output |
| `trace_frame_alignment_validation.txt` | Trace frame-alignment audit output |
| `replay.log` | Remote Isaac/Kit replay log |
| `replay_command.txt` | Timeout wrapper used by the remote replay run |
| `run_replay.sh` | Container-side replay command script |
| `brev_paid_safety_status.txt` | Final paid-instance safety snapshot |
| `ffprobe_raw.txt` | Raw replay MP4 stream metadata |
| `ffprobe_trimmed.txt` | Trimmed replay MP4 stream metadata |
| `SHA256SUMS.txt` | Checksums for this deliverable |

## Important Caveat

The success claim is still grounded in the source trace and validators. The MP4
is the Isaac-rendered visual replay of that successful trace, not a separate
closed-loop policy rollout. During the remote run, the MP4 was written before
Isaac environment shutdown interrupted JSON summary writing, so
`replay_summary_recovered.json` is intentionally labeled as locally recovered
from the source trace and video metadata.

## Reproduce Validation

```bash
python3 scripts/check_peg_in_hole_video_candidate.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
python3 scripts/audit_trace_frame_alignment.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
ffprobe -hide_banner -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,duration,codec_name -of default=noprint_wrappers=1 artifacts/deliverables/2026-06-23-isaac-trace-replay-video/isaac_trace_replay_trimmed.mp4
```
