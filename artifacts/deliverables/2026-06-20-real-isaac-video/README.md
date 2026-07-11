# Real Isaac Viewport Video Deliverable

Date: 2026-06-20

This deliverable is a real Isaac viewport recording captured on NVIDIA Brev's
official AWS Isaac Launchable. It is not the earlier local log-replay
visualization.

## Runtime

| Field | Value |
|---|---|
| Brev instance | `isaac-launchable-e91de9` / `4akhlpjad` |
| Provider/type | AWS `g6e.4xlarge`, NVIDIA L40S |
| Source commit | `045655ab825b11537bfa07577571553a8b1eaa79` |
| Source payload sha256 | `5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f` |
| Run id | `2026-06-20T14-08-28Z-real-video` |
| Task | `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0` |
| Video backend | `viewport` via Gym `RecordVideo` |
| Steps/frames | 900 requested, 901 encoded frames |
| Cleanup | delete confirmed; `brev ls instances --json --all` returned `{"workspaces": null}` and the watchdog reported `target disappeared; cleanup confirmed` |

## Files

| File | Purpose |
|---|---|
| `real_isaac_robot_arm_viewport_30s.mp4` | Friendly copy of the real Isaac viewport recording |
| `real_isaac_robot_arm_viewport_30s.mp4.sha256` | SHA256 for the friendly MP4 |
| `frame_03s.png` | Visual check frame near 3 seconds |
| `frame_15s.png` | Visual check frame near 15 seconds |
| `rca-real-isaac-video-4akhlpjad.tar.gz` | Raw pulled archive from the Launchable host |
| `rca-real-isaac-video-4akhlpjad.tar.gz.sha256` | Remote archive SHA256 |
| `rca-real-video-pull-4akhlpjad/` | Extracted raw video, logs, source manifest, smoke log, and host evidence |

## Video Probe

```text
width: 1280
height: 720
fps: 30
duration: 30.033333 seconds
frames: 901
friendly_mp4_sha256: 2dc1dfd4affe26e165afef481e757d9ab411a25d0d1e5a3e90cbb3fa46e2db60
archive_sha256: 8b2f59ed542f551d4e050fb49d10ceea191f8d8999f5748f249489b80f71f81b
video_exit: 0
```

The extracted frames show the Franka arm, socket fixture, peg frame axes, and
grid floor rendered by Isaac/RTX. The video records a scripted Abs IK contact
task rollout for visual review; it is not a claim of task success.
