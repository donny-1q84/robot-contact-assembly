# Runtime Validation: 2026-03-29

## Scope

This note captures the first remotely validated Isaac Lab runtime for the `peg-in-hole` baseline.

## Verified flows

- `docker compose ... ps` reports `isaac-sim` and `web-viewer` as `healthy`
- env registry lists:
  - `RCA-PegInHole-Franka-IK-Rel-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Play-v0`
- headless zero-action smoke completes
- headless random-action smoke completes

## Key runtime packages observed

- `numpy==1.26.4`
- `pillow==11.3.0`
- `lxml==4.9.4`
- `h5py==3.16.0`
- `hydra-core==1.3.2`
- `isaaclab==4.5.24`
- `isaaclab-rl==0.5.0`

## Current caution

The environment is usable for environment bring-up and smoke tests, but the RL package install path is not yet considered pinned or reproducible. Avoid treating the current package mix as a final training image.
