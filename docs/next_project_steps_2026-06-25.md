# Next Project Steps After Isaac Replay Deliverable

Date: 2026-06-25

## Current Evidence

The project now has the evidence needed to close the old contact-physics and
single-trace insertion proof loop:

- Phase 2 contact-physics smoke passes on the official AWS Isaac Launchable
  runtime.
- A post-smoke scripted trace reaches sustained peg-in-hole insertion.
- The same successful trace has an Isaac Sim / Isaac Lab rendered replay video.
- The latest Brev safety check reports `SAFE_NO_VISIBLE_PAID_INSTANCE`.
- Draft PR #1 publishes the current deliverables on GitHub.

Primary evidence:

```text
artifacts/deliverables/2026-06-20-contact-smoke/
artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/
artifacts/deliverables/2026-06-23-isaac-trace-replay-video/
```

## What This Does And Does Not Prove

Proved:

- The contact shell can produce real wall reaction under Isaac runtime.
- The scripted controller can produce at least one strict successful insertion
  trace in the validated task.
- The successful trace can be rendered back through Isaac as a visual artifact.
- The paid-compute cleanup path can finish with no visible active instances.

Not proved yet:

- A learned policy can perform the task.
- The success generalizes across socket poses, seeds, object geometry, or robot
  reset states.
- The system can be directly moved to another robot arm.
- The language/VLM layer has a meaningful role in the control loop.

## Recommended Next Phase

The next phase should be a narrow **V0 reproducible assembly skill baseline**.
Do not jump directly to VLMs, RL, or broad paid sweeps.

The goal is:

```text
Turn the one successful scripted trace into a reproducible, tested assembly
skill baseline with negative controls, variation checks, and a clean API shape.
```

## Immediate Work

Status update after the first local continuation:

- `scripts/check_success_deliverable_bundle.py` now validates the success
  deliverable as a complete evidence bundle.
- `scripts/test_local_gates.py` includes positive and negative bundle controls:
  the real 2026-06-21 and 2026-06-23 bundles must pass, while video-only,
  semantically failed-trace, and checksum-corrupted bundles must fail.
- `./scripts/run_local_quality_checks.sh` passes with these checks included.

1. Merge or keep-current the GitHub PR

   - Confirm PR #1 is still draft intentionally.
   - Decide whether to merge it into `master` or keep iterating on the branch.
   - If it remains draft, document what would make it ready.

2. Add a success-bundle validator - done

   Create a small validator that checks a complete deliverable bundle, not just
   one trace file. It should verify:

   - semantic trace exists and passes `check_peg_in_hole_video_candidate.py`;
   - final-contact boundary diagnostic passes;
   - trace-frame alignment audit passes;
   - MP4 exists and `ffprobe` reports nonzero duration/frames;
   - `SHA256SUMS.txt` matches the files in the bundle;
   - Brev safety snapshot contains `SAFE_NO_VISIBLE_PAID_INSTANCE`.

3. Add negative controls before any new paid run - done

   At minimum:

   - perturb the successful trace/socket relation enough that the semantic gate
     must fail;
   - run the bundle validator on a known failed trace and require failure;
   - verify that video existence alone cannot pass the bundle validator.

4. Generate a local project-status report for the post-replay state

   The current handoff doc predates the 2026-06-23 Isaac replay deliverable.
   Update it before another technical branch starts.

## Next Technical Branch

After the validator and negative controls exist, the next technical branch
should be **successful-trace variation and dataset preparation**, not more
hand-coded controller sweeping.

Local-first implementation target:

- parameterize the successful scripted insertion setup by socket pose, seed, and
  small reset perturbations;
- fill the planned traces from
  `artifacts/manifests/success_trace_variations_2026-06-25.json`;
- classify each run as strict success, near success, fail-closed, or missing;
- only after reviewing the manifest and confirming `SAFE_NO_VISIBLE_PAID_INSTANCE`,
  run a small paid trace-only batch with a fixed budget and immediate cleanup.

Useful pass condition for the next batch:

```text
At least 5 successful traces across small socket/reset variations, all passing
the semantic validator and at least one negative control that fails.
```

## Learned Policy Direction

Only start learned policy work after there are multiple successful traces.

The first learned-policy target should not be another one-step BC policy on the
old failed archive. Use one of these instead:

- temporal residual policy with previous action, recent contact force, and
  recent insertion metrics;
- residual correction on top of the scripted stabilizer;
- skill-level policy that chooses between approach, align, insert, preload, and
  recover primitives instead of commanding raw joints directly.

Minimum gate before remote training:

```text
dataset contains several strict-success traces and the negative-control bundle
checks are already passing/failing as expected.
```

## Interface / Language Direction

The language layer should remain high level for now. It should not command raw
joint targets.

Useful V0 interface:

```text
instruction -> task parameters -> skill selection -> scripted/policy controller
             -> semantic validator -> failure explanation
```

Example:

```text
"insert the peg into the left socket"
  -> object=peg, socket=left, tolerance=strict
  -> skill=peg_in_hole
  -> controller=scripted_success_baseline_or_residual_policy
```

The ROS 2 / external robot adapter should be designed after the V0 skill API is
stable. Portability will require a robot-specific adapter, calibration, joint
limits, controller gains, and safety checks.

## Do Not Do Next

- Do not open another paid GPU instance just to make a prettier video.
- Do not rerun the old native Abs IK / target-offset / solver-method / posture
  matrices unchanged.
- Do not run RL/BC before the success dataset and negative controls exist.
- Do not add a VLM as a low-level controller.
- Do not claim sim-to-real or cross-robot precision from the current artifacts.

## Concrete Next Command Sequence

No paid compute:

```bash
./scripts/run_local_quality_checks.sh
python3 scripts/check_peg_in_hole_video_candidate.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
python3 scripts/audit_trace_frame_alignment.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
ffprobe -hide_banner -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,duration,codec_name -of default=noprint_wrappers=1 artifacts/deliverables/2026-06-23-isaac-trace-replay-video/isaac_trace_replay_trimmed.mp4
```

Implemented in the local follow-up:

```text
scripts/create_success_variation_manifest.py
scripts/classify_success_variation_results.py
tests in scripts/test_local_gates.py for the variation manifest / classifier
artifacts/manifests/success_trace_variations_2026-06-25.json
artifacts/analysis/success_trace_variation_classification_2026-06-25.json
artifacts/analysis/success_trace_variation_classification_2026-06-25.md
```

Regenerate and reclassify the current local contract with:

```bash
python3 scripts/create_success_variation_manifest.py \
  --output artifacts/manifests/success_trace_variations_2026-06-25.json \
  --output-trace-root artifacts/videos/success_variations/2026-06-25
python3 scripts/classify_success_variation_results.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json \
  --output-json artifacts/analysis/success_trace_variation_classification_2026-06-25.json \
  --output-md artifacts/analysis/success_trace_variation_classification_2026-06-25.md
```

Only after reviewing that contract should a new fixed-budget trace-only remote
run be considered.
