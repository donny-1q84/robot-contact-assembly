# 2026-03-29 Phase-1 Runtime and Eval Validation

## Scope

Validate the first phase-1 reproducibility additions on the active Brev environment `isaac-l40s`.

## What was validated

1. Runtime manifest capture from the live Isaac Sim + Isaac Lab container stack
2. Seeded scripted-baseline evaluation with:
   - per-seed JSON summary
   - per-seed stdout/stderr log
   - timeout protection

## Remote runtime manifest

- Remote path:
  - `/home/ubuntu/projects/robot-contact-assembly/repo/robot-contact-assembly/experiments/runtime_manifests/2026-03-29T15-05-47Z.md`

Observed runtime facts:

- compose services healthy:
  - `isaac-sim`
  - `web-viewer`
- Isaac Sim image:
  - `nvcr.io/nvidia/isaac-sim:6.0.0-dev2`
- key packages:
  - `isaaclab==4.5.24`
  - `isaaclab_rl==0.5.0`
  - `hydra-core==1.3.2`
  - `numpy==1.26.4`

## Remote scripted-eval validation

Command shape:

```bash
bash ./scripts/run_remote_scripted_eval.sh \
  isaac-l40s \
  /home/ubuntu/projects/robot-contact-assembly \
  /home/ubuntu/isaac-compose \
  RCA-PegInHole-Franka-IK-Rel-Play-v0 \
  1 \
  30 \
  42 \
  300
```

Artifacts written on the remote container:

- `/workspace/artifacts/evaluations/scripted/2026-03-29T15-12-21Z/seed_42.log`
- `/workspace/artifacts/evaluations/scripted/2026-03-29T15-12-21Z/seed_42.json`

Summary from `seed_42.json`:

- initial lateral: `0.0430`
- final lateral: `0.0295`
- initial axial: `0.1912`
- final axial: `0.0015`
- initial rot: `2.4074`
- final rot: `1.2654`
- success rate: `0.000`

## Follow-up controller sweep

After the initial phase-1 validation, the controller and remote tooling were extended:

- `scripts/scripted_agent.py`
  - added polish/settle phase gains and clamps
  - added dynamic `settle_state = settle_mask` instead of latching final seating forever
- `scripts/run_remote_scripted_eval.sh`
  - supports pass-through controller arguments
  - no longer uses local shell here-strings, which mattered because the Mac host had almost no free disk space
- `scripts/remote_common.sh`
  - no longer builds remote commands via here-docs for the same reason
- `scripts/push_single_file_to_brev.py`
  - added as a fallback upload path because `brev copy` was unreliable during this session

### Best 160-step run

Command:

```bash
bash ./scripts/run_remote_scripted_eval.sh \
  isaac-l40s \
  /home/ubuntu/projects/robot-contact-assembly \
  /home/ubuntu/isaac-compose \
  RCA-PegInHole-Franka-IK-Rel-Play-v0 \
  1 \
  160 \
  42 \
  300 \
  '--polish-pos-gain 2.0 --polish-pos-clamp 0.015 --polish-rot-gain 10.0 --polish-rot-clamp 0.8 --settle-rot-tol 0.16'
```

Artifacts:

- `/workspace/artifacts/evaluations/scripted/2026-03-29T15-31-22Z/seed_42.log`
- `/workspace/artifacts/evaluations/scripted/2026-03-29T15-31-22Z/seed_42.json`

Result:

- final lateral: `0.0006`
- final axial: `0.0002`
- final rot: `0.1545`
- success rate: `0.000`

Interpretation:

- dynamic settle removed the immediate long-horizon blow-up seen in the earlier 160-step candidate
- but the controller still stopped just outside the success region

### 220-step stability check

Same controller arguments, but `220` steps:

- `/workspace/artifacts/evaluations/scripted/2026-03-29T15-33-08Z/seed_42.log`
- `/workspace/artifacts/evaluations/scripted/2026-03-29T15-33-08Z/seed_42.json`

Result:

- at step `150`: `lateral=0.0006 axial=0.0003 rot=0.1569`
- at step `175`: `lateral=0.0556 axial=0.1392 rot=2.2882`
- final lateral: `0.1315`
- final axial: `0.1245`
- final rot: `0.0000`
- success rate: `0.000`

Interpretation:

- dynamic settle improved short-horizon behavior
- it did **not** solve long-horizon instability
- the controller still exits the near-contact basin after entering final seating

## Conclusion

The phase-1 workflow is now usable:

- runtime capture works
- seeded scripted eval works
- each eval run now leaves machine-readable summaries and human-readable logs
- single-file sync to Brev now works even when `brev copy` is unreliable

The bottleneck is now more specific than before:

- the scripted controller can reach the near-success region
- but its final seating dynamics are still unstable over longer horizons
- the environment is no longer the primary blocker

## Next step

Do **not** continue blind gain tuning on this exact controller.

Instead:

1. replace the final seating logic with a more explicit near-contact controller
2. rerun short single-seed validation
3. rerun fixed multi-seed scripted evaluation
4. only after that, move to BC / Mimic / SkillGen or RL fine-tuning
