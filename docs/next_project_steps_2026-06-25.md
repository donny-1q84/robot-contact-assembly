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
limits, controller gains, and safety checks. The adapter manifest is a separate
gate from the V0 skill request: it is allowed to be safely blocked as a template,
but it must fail if someone claims hardware readiness without robot-specific
model, calibration, safety, ROS 2, and revalidation evidence.

The current V0 contract is now machine-readable:

```text
configs/v0_skill_api_contract.json
scripts/check_v0_skill_api_contract.py
configs/v0_skill_request.example.json
scripts/plan_v0_skill_request.py
scripts/validate_v0_skill_request.py
scripts/check_v0_skill_readiness.py
scripts/prepare_v0_policy_api_review.py
configs/v0_external_robot_adapter.template.json
scripts/plan_v0_robot_adapter_manifest.py
scripts/check_v0_robot_adapter_contract.py
scripts/check_v0_portability_boundary.py
```

It keeps language/VLM behavior at the task-parameter and skill-selection layer,
forbids raw joint or direct force commands from language, records the semantic
validators required before promotion, and defines the minimum robot-specific
adapter gates for future ROS 2 or external-arm work. It explicitly does not
claim sim-to-real readiness or direct drop-in precision on another robot arm.
The example request and validator turn that boundary into an executable local
check: a high-level instruction can select `peg_in_hole`, but requests with raw
joint targets, direct force commands, or VLM-to-raw-control modes fail closed.
The planner is deliberately narrow and deterministic: supported insert
instructions become a normalized request; ambiguous or low-level instructions
do not write a request artifact.
The readiness gate connects that request to the current project evidence:
request and contract validation, Phase 2 contact proof, success-variation result
gate, and the V0 scripted-skill dataset. In the current baseline-only state it
must remain blocked and point to the fixed-budget variation batch as the next
physical step.
After that readiness gate is `READY`, `scripts/prepare_v0_policy_api_review.py`
writes the structured policy/API review packet. It does not train a policy or
start ROS; it packages the validated request, dataset summary, gate summary, API
boundary, manual review checklist, and explicit non-claims.
The robot-adapter checker encodes the portability boundary from the other side:
the committed template is `BLOCKED`, not `READY`, and a future named arm must
supply concrete URDF/USD or equivalent model sources, TCP/base/fixture
calibration, safety gates, ROS 2 interface validation, low-speed contact
validation, and variation-style revalidation before any hardware-use claim.
`docs/v0_robot_adapter_contract.md` adds the explicit command contract, frame
contract, and runtime guard checklist so "portable" means a named, validated
adapter boundary, not direct drop-in precision on arbitrary arms.
`scripts/plan_v0_robot_adapter_manifest.py` turns a named target arm and any
known ROS 2 interface names into a machine-readable adapter manifest, but still
leaves it safely blocked until the checker sees robot-specific model,
calibration, safety, interface-validation, and revalidation evidence.
`scripts/check_v0_portability_boundary.py` is the aggregate claim gate: it
combines V0 skill readiness with the named robot adapter status and keeps
`universal_drop_in_ready=false` even when one named adapter is ready for
low-speed review.

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
python3 scripts/check_v0_skill_api_contract.py
python3 scripts/plan_v0_skill_request.py "insert the peg into the left socket"
python3 scripts/validate_v0_skill_request.py
python3 scripts/check_v0_skill_readiness.py --skip-phase2-contact-gate
python3 scripts/plan_v0_skill_execution.py --skip-phase2-contact-gate --no-output
python3 scripts/prepare_v0_policy_api_review.py --skip-phase2-contact-gate
python3 scripts/audit_v0_policy_dataset.py --no-output
python3 scripts/plan_v0_policy_experiment.py --no-output
python3 scripts/plan_v0_policy_feature_dry_run.py --no-output
python3 scripts/audit_v0_policy_label_sources.py --no-output
python3 scripts/plan_v0_policy_label_dry_run.py --no-output
python3 scripts/extract_v0_policy_label_dataset.py --no-output
python3 scripts/check_v0_policy_training_preflight.py --no-output
python3 scripts/train_v0_residual_policy.py --dry-run --no-output
python3 scripts/evaluate_v0_residual_policy.py --dry-run --no-output
python3 scripts/plan_v0_robot_adapter_manifest.py \
  --robot-id demo_arm_v0 \
  --robot-family demo_6dof_arm \
  --end-effector parallel_gripper_with_peg_fixture \
  --joint-trajectory-action /demo_arm/joint_trajectory_controller/follow_joint_trajectory \
  --joint-state-feedback /joint_states \
  --skill-status /rca/skill_status
python3 scripts/check_v0_robot_adapter_contract.py
python3 scripts/check_v0_portability_boundary.py --skip-phase2-contact-gate
python3 scripts/check_success_variation_batch_plan.py artifacts/manifests/success_trace_variations_2026-06-25.json
python3 scripts/check_peg_in_hole_video_candidate.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
python3 scripts/audit_trace_frame_alignment.py artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json
ffprobe -hide_banner -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,duration,codec_name -of default=noprint_wrappers=1 artifacts/deliverables/2026-06-23-isaac-trace-replay-video/isaac_trace_replay_trimmed.mp4
```

Implemented in the local follow-up:

```text
scripts/create_success_variation_manifest.py
scripts/classify_success_variation_results.py
scripts/plan_success_variation_batch.py
scripts/check_success_variation_batch_plan.py
scripts/run_remote_success_variation_batch.sh
scripts/run_remote_success_variation_batch_as_trace_runner.sh
scripts/recreate_brev_and_run_success_variation_batch.sh
scripts/run_success_variation_batch_from_config.sh
scripts/check_success_variation_batch_readiness.py
scripts/check_success_variation_batch_results.py
scripts/review_success_variation_batch.py
scripts/prepare_success_variation_dataset.py
scripts/finalize_success_variation_batch.sh
scripts/write_success_variation_run_packet.py
scripts/audit_success_variation_assumptions.py
scripts/check_brev_credit_evidence.py
scripts/write_brev_credit_evidence.py
scripts/arm_success_variation_paid_env.py
scripts/check_success_variation_paid_lifecycle_preflight.py
scripts/check_v0_skill_api_contract.py
scripts/plan_v0_skill_request.py
scripts/validate_v0_skill_request.py
scripts/check_v0_skill_readiness.py
scripts/train_v0_residual_policy.py
scripts/evaluate_v0_residual_policy.py
scripts/check_v0_robot_adapter_contract.py
configs/v0_skill_api_contract.json
configs/v0_skill_request.example.json
configs/v0_external_robot_adapter.template.json
configs/brev_credit_verification.template.json
configs/success_variation_batch_run.env.example
tests in scripts/test_local_gates.py for the variation manifest / classifier
artifacts/manifests/success_trace_variations_2026-06-25.json
artifacts/analysis/success_trace_variation_classification_2026-06-25.json
artifacts/analysis/success_trace_variation_classification_2026-06-25.md
artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.json
artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.sh
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
python3 scripts/plan_success_variation_batch.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json \
  --output-json artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.json \
  --output-sh artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.sh
```

Only after reviewing that contract should a new fixed-budget trace-only remote
run be considered.

If a ready remote environment already exists under the normal repo/compose
paths, run the planned traces without creating or deleting Brev resources:

```bash
RCA_SUCCESS_VARIATION_STEPS=220 \
  scripts/run_remote_success_variation_batch.sh \
  artifacts/manifests/success_trace_variations_2026-06-25.json \
  <env-name>
```

If no ready environment exists and a new Brev instance is genuinely needed, use
the config launcher instead of calling `brev create` directly. The committed
template is fail-closed; real one-run acknowledgements belong in the git-ignored
`configs/success_variation_batch_run.local.env` file:

```bash
python3 scripts/write_success_variation_run_packet.py \
  --config configs/success_variation_batch_run.env.example \
  --manifest artifacts/manifests/success_trace_variations_2026-06-25.json
```

This writes the current readiness facts, blockers, estimated cost, one-run env
template, timeout envelope, and exact check/run/finalize commands under
`artifacts/analysis/`. The timeout envelope must show that setup reserve,
same-seed calibration reuse, per-case trace timeouts, and margin fit inside the
paid watchdog TTL. It does not create, delete, copy to, or execute on Brev
instances.
The config launcher also writes this packet automatically before each
`--check-only` or `--run`, then writes the read-only `pre-batch` assumption
audit before the readiness gate and any guarded paid wrapper.

Before writing any one-run local evidence, the read-only aggregate preflight is:

```bash
python3 scripts/check_success_variation_paid_lifecycle_preflight.py --no-output
```

It summarizes Brev UI credit evidence, `SAFE_NO_VISIBLE_PAID_INSTANCE`, local
env armability, and batch-plan readiness. It does not arm the env or create a
paid instance.

After manually reading the current Brev UI balance, the preferred local prepare
step is:

```bash
python3 scripts/prepare_success_variation_paid_batch.py \
  --balance-eur <current-brev-ui-balance> \
  --force-credit \
  --i-understand-this-arms-paid-run
```

That helper writes the git-ignored credit evidence, arms the git-ignored local
env, and runs `--check-only`. It still does not create a paid instance, and it
disarms the local env automatically if `--check-only` is not READY.

For the actual one-shot paid lifecycle, prefer the higher-level wrapper after
the prepare check-only path is READY:

```bash
python3 scripts/run_success_variation_paid_lifecycle.py \
  --balance-eur <current-brev-ui-balance> \
  --run \
  --i-understand-this-can-create-paid-instance
```

That wrapper still requires fresh Brev UI balance evidence. It delegates to the
prepare helper and guarded config runner, then always disarms the local env,
runs Brev safety, and either finalizes the dataset gate or writes the recovery
rerun plan.

Before editing the ignored local env or opening paid compute, run the
read-only assumption-and-metric audit:

```bash
python3 scripts/audit_success_variation_assumptions.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json \
  --phase pre-batch \
  --run-packet artifacts/analysis/success_variation_run_packet_2026-06-25.json \
  --fail-on-blocked
```

This traces `strict_success`, the deliberate negative control, planned
variation coverage, paid-run budget/cleanup, and dataset-promotion policy back
to concrete code/data sources. In `pre-batch` mode, missing planned variation
traces are expected because this is the batch that will generate them; the hard
blockers are invalid baseline/negative-control assumptions, a missing or
non-READY run packet, budget/cleanup issues, or one-run paid acknowledgements
still being fail-closed. In default `post-batch` mode, missing planned traces
are blockers for dataset/policy promotion. The audit does not create, delete,
copy to, or execute on Brev instances.

Prepare the ignored local env file in a fail-closed state with:

```bash
python3 scripts/prepare_success_variation_local_env.py \
  --packet artifacts/analysis/success_variation_run_packet_2026-06-25.json
```

This writes `configs/success_variation_batch_run.local.env` with
`RCA_ALLOW_PAID_BREV_CREATE=0`, `RCA_BREV_CREDITS_VERIFIED=0`, and
`RCA_ACK_BREV_LIFECYCLE_RISK=0`; those three values must only be changed for one
deliberate reviewed run after current Brev credits and deletion safety are
confirmed.

Before setting `RCA_BREV_CREDITS_VERIFIED=1`, record the current Brev UI org
balance into the ignored local evidence file:

```bash
python3 scripts/write_brev_credit_evidence.py \
  --balance-eur <current-brev-ui-balance> \
  --budget-eur 6.00 \
  --force
python3 scripts/check_brev_credit_evidence.py \
  --evidence configs/brev_credit_verification.local.json \
  --required-budget-eur 6.00
```

The readiness gate only treats `RCA_BREV_CREDITS_VERIFIED=1` as valid when this
git-ignored evidence file passes freshness, org, source, and budget checks.
After the evidence passes, arm the ignored local env with the checked helper:

```bash
python3 scripts/arm_success_variation_paid_env.py \
  --i-understand-this-arms-paid-run
```

This only writes the three paid acknowledgement markers into the ignored local
env after credit evidence and Brev safety checks pass. It also writes
`RCA_PAID_ARMED_AT_UTC`; the readiness gate treats the arming as stale after
`RCA_PAID_ARMING_MAX_AGE_MINUTES` and blocks the paid run. It does not create,
delete, copy to, or execute on Brev instances. Run `--check-only` immediately
after arming and before any `--run`. The `--run` launcher automatically disarms
the local env on exit; use this manually if a run is not started or you need to
clear stale acknowledgements:

```bash
python3 scripts/arm_success_variation_paid_env.py --disarm
```

```bash
scripts/run_success_variation_batch_from_config.sh \
  configs/success_variation_batch_run.local.env \
  --check-only

scripts/run_success_variation_batch_from_config.sh \
  configs/success_variation_batch_run.local.env \
  --run
```

Before creation, `scripts/check_success_variation_batch_readiness.py` checks
the manifest/positive-control/negative-control contract, Phase 2 gate, explicit
budget/hourly estimate/TTL, current-credit evidence, lifecycle-risk
acknowledgement, `SAFE_NO_VISIBLE_PAID_INSTANCE`, and the current Brev search
price/availability for the selected instance type. The wrapper then reuses the
existing `paid_compute_preflight.sh`,
`brev_paid_run_watchdog.sh`, artifact pull, delete, and empty-org confirmation
path. The lifecycle-risk acknowledgement is required while
`docs/brev_launchable_lifecycle_hold.md` is active.

After the batch artifacts are pulled and classified, gate promotion to learned
policy work and write the review record with:

```bash
scripts/finalize_success_variation_batch.sh \
  artifacts/manifests/success_trace_variations_2026-06-25.json
```

The finalizer runs the post-batch review, the strict result gate, and the V0
dataset prep in order. It writes a review record even when blocked, and it does
not create or delete Brev instances. The equivalent lower-level commands are:

```bash
python3 scripts/review_success_variation_batch.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json

python3 scripts/check_success_variation_batch_results.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json
python3 scripts/plan_success_variation_recovery_batch.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json
```

The default promotion contract is deliberately strict: `baseline_replay` must
remain `strict_success`, at least 5 non-baseline/non-negative variations must be
`strict_success`, strict successes must cover `seed_or_reset`, `socket_x`,
`socket_y`, and `socket_z` variation groups, the
`socket_x_pos_25mm_negative_control` must be labeled `expected=fail_closed` and
classified `fail_closed`, and no planned trace artifact may be missing.
If a fixed-budget batch only fills some traces, use
`scripts/plan_success_variation_recovery_batch.py` before any rerun. It skips
already satisfied strict-success cases and the fail-closed negative control, and
blocks if the negative control unexpectedly succeeds.

Only after that result gate passes, freeze the first V0 scripted-skill dataset
manifest with:

```bash
python3 scripts/prepare_success_variation_dataset.py \
  artifacts/manifests/success_trace_variations_2026-06-25.json
python3 scripts/prepare_v0_policy_api_review.py
```

The dataset prep script is offline/read-only. In the current baseline-only
state it must fail closed because the planned variation traces and the negative
control trace are missing. When the batch is complete, it writes:

```text
artifacts/datasets/v0_scripted_skill_success_variations/manifest.json
artifacts/datasets/v0_scripted_skill_success_variations/README.md
artifacts/reviews/v0_policy_api/review_packet.json
artifacts/reviews/v0_policy_api/README.md
```

Those files are allowed to support residual-policy and skill-API design, but
they still are not proof of a learned policy, sim-to-real readiness, or direct
cross-robot portability.

After the residual-label dataset is extracted and
`scripts/check_v0_policy_training_preflight.py` is READY, use
`scripts/train_v0_residual_policy.py --dry-run` first. The dry-run writes only a
training plan and no checkpoint. Real training remains local/PyTorch-only and
must still be followed by a separate evaluator before any policy-promotion
claim.
`scripts/evaluate_v0_residual_policy.py --dry-run` then checks the training
metadata, checkpoint checksum, label manifest checksum, and JSONL checksum
without importing PyTorch. Its real evaluation path is still only supervised
residual-label evaluation, not Isaac closed-loop success evidence.
