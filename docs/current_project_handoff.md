# Current Project Handoff

Date: 2026-06-22

## Repository State

- Repo path: `/Volumes/Extreme Pro/Projects/robot-contact-assembly`
- Branch: `codex/contact-smoke-gate-pass`
- Remote: `https://github.com/donny-1q84/robot-contact-assembly.git`
- Latest checked commit as of 2026-06-18 audit: `92465f4 Fix contact physics: weld dynamic peg to hand, wall-filtered forces`
- Local tree was clean at the start of the 2026-06-18 audit.

## 2026-06-25 Next-Step Overlay

The 2026-06-21 success trace and 2026-06-23 Isaac replay deliverable are now
published on the draft GitHub PR:

```text
PR: https://github.com/donny-1q84/robot-contact-assembly/pull/1
branch: codex/contact-smoke-gate-pass
latest pushed commit before variation-tooling follow-up: 0ce7091 Add success deliverable bundle gate
```

Current evidence is enough to close the old contact-smoke / single-success-trace
loop, but not enough to claim a learned policy, cross-pose generalization,
sim-to-real readiness, or direct portability to another robot arm.

The next phase should be a local-first V0 reproducible assembly skill baseline:

1. keep or merge the draft PR intentionally;
2. use `scripts/check_success_deliverable_bundle.py` to validate semantic trace
   success, final-contact boundary diagnostics, trace-frame alignment, MP4
   metadata, checksums, and `SAFE_NO_VISIBLE_PAID_INSTANCE`;
3. keep the local negative controls in `scripts/test_local_gates.py` so failed
   traces, video-only bundles, and checksum-corrupted bundles cannot pass;
4. build successful-trace variation and dataset preparation across small
   socket/reset perturbations;
5. use `scripts/create_success_variation_manifest.py` and
   `scripts/classify_success_variation_results.py` to keep the next paid batch
   bounded, classifiable, and negative-control checked before opening compute;
6. use `scripts/plan_success_variation_batch.py` and
   `scripts/run_remote_success_variation_batch.sh` so each remote trace writes
   to the manifest planned path with explicit socket/reset variation metadata;
   the runner now attempts artifact pullback and local classification even when
   one generated case command fails, then returns the original failure status.
   The batch runner also forwards explicit per-case calibration/trace timeouts
   and reuses same-seed calibration summaries by default, so repeated cases do
   not spend a full calibration timeout each time;
7. if a new Brev instance is required for the batch, use
   the fail-closed `configs/success_variation_batch_run.env.example` as the
   reviewed template, put real one-run values in the git-ignored
   `configs/success_variation_batch_run.local.env`, generate the current
   read-only packet with `scripts/write_success_variation_run_packet.py`, run
   `scripts/check_success_variation_batch_plan.py` to prove the generated plan
   covers exactly the planned cases, remote artifact paths, and fail-closed
   negative control before any paid create. Also rely on
   `scripts/check_success_variation_batch_readiness.py` to verify that the
   configured setup reserve, per-seed calibration timeout, per-case trace
   timeout, and margin fit inside the paid watchdog TTL before any paid create.
   Then run
   `scripts/audit_success_variation_assumptions.py --phase pre-batch` to trace
   every critical success/negative-control/budget/promotion metric back to
   concrete sources without treating the still-missing planned traces as a paid
   run blocker, and only then run
   `scripts/prepare_success_variation_local_env.py` if the local env file needs
   to be created in its default fail-closed state before editing for a single
   reviewed run. Before setting `RCA_BREV_CREDITS_VERIFIED=1`, run
   `scripts/write_brev_credit_evidence.py --balance-eur <current-brev-ui-balance> --budget-eur 6.00 --force`
   to write the git-ignored `configs/brev_credit_verification.local.json` from
   the current Brev UI org balance and validate it covers the run budget. Add
   `--dry-run` first to emit machine-readable preview facts without writing the
   evidence file, validating a written file, or creating paid resources. Or
   use `scripts/prepare_success_variation_paid_batch.py --balance-eur <current-brev-ui-balance> --force-credit --i-understand-this-arms-paid-run`
   to write credit evidence, arm the local env, refresh the run packet through
   the read-only `--check-only` gate, and rerun the aggregate paid lifecycle
   preflight in one fail-closed sequence. That helper still does not create a
   paid instance. Its `--dry-run` mode emits machine-readable facts showing the
   exact write-credit, arm, check-only, and aggregate-preflight steps while
   confirming it will not write evidence, arm the env, or create a paid instance.
   It disarms automatically if either local readiness gate fails.
   The underlying arming step writes the one-run paid acknowledgements
   only after credit evidence and Brev safety checks pass. The armed env records
   `RCA_PAID_ARMED_AT_UTC` and
   expires by `RCA_PAID_ARMING_MAX_AGE_MINUTES` so stale acknowledgements cannot
   be reused; `scripts/run_success_variation_batch_from_config.sh --run`
   automatically disarms the local env on exit, and
   `scripts/arm_success_variation_paid_env.py --disarm` is the manual fallback
   that restores the three paid acknowledgement values to `0`. Then run
   `scripts/run_success_variation_batch_from_config.sh configs/success_variation_batch_run.local.env --check-only` before
   `scripts/recreate_brev_and_run_success_variation_batch.sh`, which delegates
   paid preflight, watchdog, artifact pull, deletion, and empty-org confirmation
   to the existing lifecycle wrapper. The lifecycle wrapper also bounds its
   direct Brev list/delete cleanup calls with
   `RCA_FINAL_CONTACT_BREV_QUERY_TIMEOUT_SECONDS` and
   `RCA_FINAL_CONTACT_BREV_MUTATION_TIMEOUT_SECONDS`, so login or network
   failures cannot leave the main cleanup path waiting forever while the
   independent watchdog remains armed. The config launcher now also writes the
   read-only run packet automatically before each check/run;
8. after the pulled artifacts are classified, use
   `scripts/finalize_success_variation_batch.sh` to write the review record,
   enforce the strict result gate, and prepare the V0 scripted-skill dataset
   only if the gate passes. The result gate requires at least 5
   non-baseline/non-negative strict successes, strict-success coverage across
   `seed_or_reset`, `socket_x`, `socket_y`, and `socket_z` variation groups,
   `baseline_replay` still `strict_success`, the 25 mm socket-shift negative
   control labeled `expected=fail_closed` and classified `fail_closed`, and no
   missing planned trace artifacts before learned policy, VLM, ROS, or
   sim-to-real claims. The finalizer does not create or delete Brev instances
   and must fail closed in the current baseline-only state. The high-level paid
   lifecycle wrapper now runs `scripts/run_v0_offline_policy_readiness_pipeline.py`
   after finalize succeeds, so a passing batch advances into the local
   post-batch handoff before reporting lifecycle PASS. The pipeline chains the
   policy/API review, dataset audit, residual-policy experiment plan, feature
   dry-run, label-source audit, label dry-run, label dataset extraction,
   training preflight, and residual-policy training dry-run. It must stay
   `BLOCKED` while the variation gate or dataset is missing, and it is
   explicitly not a paid run, Brev/Isaac launcher, ROS integration, hardware
   execution, sim-to-real proof, or cross-robot drop-in claim.
9. keep the V0 language/skill/robot-adapter boundary checked by
   `configs/v0_skill_api_contract.json` and
   `scripts/check_v0_skill_api_contract.py`, with request-level examples checked
   by `configs/v0_skill_request.example.json` and
   `scripts/validate_v0_skill_request.py`; `scripts/plan_v0_skill_request.py`
   provides the narrow deterministic language-to-skill shim, and
   `configs/v0_language_instruction_suite.json` plus
   `scripts/check_v0_language_instruction_suite.py` keep supported
   left/right/center insert instructions and rejected low-level/ambiguous
   instructions under regression, and `scripts/project_status_report.py`
   surfaces that language suite before the downstream V0 readiness gates.
   `scripts/check_v0_skill_readiness.py` connects a validated request to the
   current Phase 2, variation-result, and dataset evidence.
   `scripts/run_v0_language_skill_dry_run.py` is the one-command local
   language-to-skill report: it runs the deterministic request planner,
   validates the request, and connects it to the gated execution plan without
   calling an LLM/VLM, Brev, Isaac, ROS, or hardware. In the current state it
   should accept supported insert instructions but stay `BLOCKED` on V0
   readiness until the success-variation batch and dataset exist, and
   `scripts/project_status_report.py` surfaces this dry-run as its own V0 row
   so the instruction-to-skill boundary is visible before downstream policy or
   adapter claims.
   `scripts/prepare_v0_policy_api_review.py` writes the post-readiness
   policy/API review packet only after those gates and the dataset are ready.
   The future external-robot adapter shape is checked separately by
   `configs/v0_external_robot_adapter.template.json` and
   `scripts/plan_v0_robot_adapter_manifest.py` plus
   `scripts/check_v0_robot_adapter_contract.py`, which must remain blocked until
   a named robot has model, calibration, safety, ROS 2 interface, and
   revalidation evidence. The planner can fill target-robot identity and known
   ROS 2 interface names, but it still emits a not-ready adapter manifest. This
   contract keeps language at task-parameter and skill-selection level, forbids
   raw joint/force commands from language requests, and requires robot-specific
   model, calibration, safety, ROS 2 interface, and revalidation gates before
   any external-arm portability claim.

The first local variation contract is:

```text
manifest: artifacts/manifests/success_trace_variations_2026-06-25.json
classification_json: artifacts/analysis/success_trace_variation_classification_2026-06-25.json
classification_md: artifacts/analysis/success_trace_variation_classification_2026-06-25.md
batch_plan_json: artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.json
batch_plan_sh: artifacts/analysis/success_trace_variation_batch_plan_2026-06-25.sh
result: 1 strict_success positive control, 8 missing planned cases
negative_control: socket_x_pos_25mm_negative_control expected fail_closed
paid_compute_allowed: false
credit_evidence: configs/brev_credit_verification.local.json is ignored and must pass scripts/check_brev_credit_evidence.py; use scripts/write_brev_credit_evidence.py --dry-run to preview the payload with no write/create side effects, then write evidence and arm via scripts/arm_success_variation_paid_env.py after checking the Brev UI balance before RCA_BREV_CREDITS_VERIFIED=1
paid_success_variation_preflight: scripts/check_success_variation_paid_lifecycle_preflight.py summarizes clean source state, current contact-smoke bundle, credit evidence, Brev safety, local-env armability, batch-plan readiness, and the pre-batch assumption audit without arming or creating a paid instance
brev_credit_review_packet: scripts/prepare_brev_credit_review.py exposes the Brev org dashboard URL, current credit-evidence blocker, preview/write-credit commands, preview/real prepare_success_variation_paid_batch.py commands, rerun-preflight command, and paid lifecycle command without opening paid compute by default; pass --balance-eur <current-brev-ui-balance> to replace placeholders with concrete preview commands; write_brev_credit_evidence.py --dry-run and prepare_success_variation_paid_batch.py --dry-run emit parseable facts with no write/arm/create side effects
pre_batch_assumption_audit: scripts/audit_success_variation_assumptions.py --phase pre-batch --no-output is surfaced in scripts/project_status_report.py; blocked until one-run paid acknowledgements exist, while planned traces may still be missing
post_batch_assumption_audit: blocked until planned traces and negative control results exist
paid_success_variation_lifecycle: scripts/run_success_variation_paid_lifecycle.py is the one-shot paid entrypoint after current UI balance evidence; it prepares/arms local evidence, reruns the aggregate paid lifecycle preflight with fail-on-blocked before the guarded paid runner, then disarms/safety-checks before finalizing/running the offline policy-readiness pipeline or writing a recovery plan; preflight failure, preflight interrupt, run/finalize failures, and KeyboardInterrupt are covered by local cleanup-path tests
skill_api_contract: configs/v0_skill_api_contract.json passes local contract check
skill_api_promotion_coverage: requires strict-success seed/reset plus socket X/Y/Z variation coverage before policy/API promotion
success_variation_recovery: scripts/plan_success_variation_recovery_batch.py skips already satisfied traces and plans only unresolved reruns after a partial batch
skill_request_contract: configs/v0_skill_request.example.json passes local request check
skill_request_planner: scripts/plan_v0_skill_request.py maps supported insert instructions only
language_instruction_suite: configs/v0_language_instruction_suite.json and scripts/check_v0_language_instruction_suite.py cover supported left/right/center insert instructions plus rejected low-level/ambiguous instructions and are surfaced in scripts/project_status_report.py before downstream V0 readiness
language_skill_dry_run: scripts/run_v0_language_skill_dry_run.py chains instruction parsing, request validation, and gated execution planning while forbidding raw joint/force commands; scripts/project_status_report.py surfaces the current blocked dry-run row before downstream policy or adapter claims
skill_execution_plan: scripts/plan_v0_skill_execution.py stays blocked until V0 readiness is READY and never emits raw joint/force commands
skill_readiness: scripts/check_v0_skill_readiness.py is blocked until variation traces and dataset exist
policy_api_review_packet: scripts/prepare_v0_policy_api_review.py is blocked until skill readiness is READY
policy_dataset_audit: scripts/audit_v0_policy_dataset.py checks dataset provenance, case coverage, negative-control exclusion, and review-packet alignment before policy experiment work
policy_experiment_plan: scripts/plan_v0_policy_experiment.py stays blocked until the V0 policy/API review packet and dataset exist; it only designs a residual-policy experiment
policy_feature_dry_run: scripts/plan_v0_policy_feature_dry_run.py stays blocked until the dataset audit and experiment plan are ready; it previews local features only and never generates training targets
policy_label_source_audit: scripts/audit_v0_policy_label_sources.py stays blocked until the feature dry-run is ready; it audits allowed skill-controller residual target sources while excluding raw_action/joint targets
policy_label_dry_run: scripts/plan_v0_policy_label_dry_run.py stays blocked until the label-source audit is ready; it previews allowed residual labels only and never writes a training dataset/checkpoint
policy_label_dataset: scripts/extract_v0_policy_label_dataset.py stays blocked until label dry-run is ready; it writes JSONL plus manifest/checksum for allowed residual labels only, not a trained policy
policy_training_preflight: scripts/check_v0_policy_training_preflight.py stays blocked until the label dataset exists; it checks JSONL checksum/schema and the implemented scripts/train_v0_residual_policy.py entrypoint before local training
policy_training_entrypoint: scripts/train_v0_residual_policy.py supports fail-closed dry-run planning without torch and real local PyTorch training only after the label-dataset preflight passes
policy_readiness_pipeline: scripts/run_v0_offline_policy_readiness_pipeline.py chains the offline post-batch review/audit/feature/label/training-preflight/training-dry-run gates; it stays blocked until the V0 variation dataset exists and never creates paid resources
policy_eval_entrypoint: scripts/evaluate_v0_residual_policy.py verifies training metadata, checkpoint checksum, label manifest checksum, and JSONL checksum before supervised residual-label evaluation; it is not an Isaac closed-loop policy gate
policy_promotion_gate: scripts/check_v0_policy_promotion_gate.py stays blocked until V0 skill readiness, supervised residual-policy evaluation, and an Isaac closed-loop policy evaluation with the same checkpoint checksum, strict successes, fail-closed negative control, and scripted-baseline comparison are all present
external_robot_adapter_planner: scripts/plan_v0_robot_adapter_manifest.py writes named-arm manifests that remain safely blocked
external_robot_adapter: configs/v0_external_robot_adapter.template.json is safely blocked by scripts/check_v0_robot_adapter_contract.py; docs/v0_robot_adapter_contract.md defines command/frame/runtime guards so portability is adapter-specific, not drop-in
portability_boundary: scripts/check_v0_portability_boundary.py combines V0 skill readiness with the named adapter contract and keeps universal_drop_in_ready=false
portability_review_packet: scripts/prepare_v0_portability_review.py packages the portability boundary, reusable layers, robot-specific layers, current blockers, and exact non-drop-in answer into JSON/Markdown without touching Brev, Isaac, ROS, or hardware
dataset_preparation: blocked until the result gate passes
```

Do not open another paid GPU run for a prettier video, old Abs IK/JointPos
sweeps, RL/BC, or VLM work until the variation manifest/classifier has been
reviewed and a fixed-budget trace-only batch plan is explicit. The current batch
execution script assumes an already ready remote environment; it does not create
or delete Brev instances. If creation is needed, the dedicated success-variation
paid wrapper must still pass the success-variation readiness gate,
`paid_compute_preflight.sh`, fresh Brev UI credit evidence, fixed budget/TTL,
`SAFE_NO_VISIBLE_PAID_INSTANCE`, live Brev instance price/availability check,
and lifecycle-risk acknowledgement while `docs/brev_launchable_lifecycle_hold.md`
is active. After the run, the success-variation result gate must pass before
this project can move from scripted reproducibility into dataset/policy work.
The dataset-prep gate then freezes only strict-success non-negative traces and
keeps explicit non-claims: not learned policy, not sim-to-real, and not
cross-robot-ready.

The portability boundary is also explicit: the current artifacts can support a
future ROS 2 / external robot adapter contract, but they do not prove direct
drop-in precision on another robot arm. A new arm will need its own model,
TCP/tool calibration, controller adapter, limits/gains, sensing setup, and
validation gates before any precise contact-rich insertion claim.

Detailed plan:

```text
docs/next_project_steps_2026-06-25.md
```

## 2026-06-21 Peg-In-Hole Success Trace Overlay

The current post-smoke scripted insertion trace now passes the strict semantic
success gates. This is the first trace in the current validated contact-physics
runtime that proves sustained peg-in-hole insertion.

```text
trace: artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_summary.json
deliverable: artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/
first_success_step: 167
final_success_rate: 1.0
final_lateral: 0.0015925065381452441 m
final_axial: 0.007546612061560154 m
final_rot: 0.054073676466941833 rad
final_contact_force_magnitude: 0.5527539253234863 N
cleanup: ./scripts/brev_paid_safety_status.sh reported SAFE_NO_VISIBLE_PAID_INSTANCE
```

Validation evidence:

```text
python3 scripts/check_peg_in_hole_video_candidate.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
  PASS: video_candidate_pass=True, first_video_sustained_step=166

python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
  PASS: first_sustained_success_step=178, unsafe_boundary_descent_count=0, pop_event_count=0

python3 scripts/audit_trace_frame_alignment.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json
  PASS

python3 scripts/check_scripted_action_response_trace.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json --min-command-norm 0.0002 --stop-after-first-success
  PASS
```

A local diagnostic video was rendered from the passing trace:

```text
artifacts/videos/trace_rendered/2026-06-21T20-05-25Z/peg_in_hole_trace_render.mp4
artifacts/videos/trace_rendered/2026-06-21T20-05-25Z/peg_in_hole_trace_render.summary.json
```

This MP4 is not Isaac viewport footage. It is a trace-rendered diagnostic
visualization that shows top-down XY, axial descent, rotation, contact force,
and final `SUCCESS TRUE`. The success claim is the trace plus validator output,
not the visualization itself.

To prevent repeating the previous paid-run mistake, the paid video wrapper now
refuses `screen` or `viewport` recording when
`RCA_ISAACLAB_RUNTIME_PROFILE=trace-only`. Trace-only is for semantic/headless
validation; full UI recording requires a full Isaac runtime profile.

## 2026-06-20 Current PASS Overlay

The Phase 2 contact-physics smoke gate now passes on the official AWS Isaac
Launchable runtime.

```text
instance: isaac-launchable-gate-5ecb / ak7egbprx
run_id: 2026-06-20T13-01-54Z-gate
provider/type: AWS g6e.4xlarge L40S
source_payload_sha256: 5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f
pulled_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-gate-ak7egbprx.tar.gz
pulled_archive_sha256: 4c595d7098c8b760ba3af603246ccf5c485f3d9251984ce372d9f52eafb3ec92
canonical_log: artifacts/launchable_logs/contact_physics_smoke.log
deliverables: artifacts/deliverables/2026-06-20-contact-smoke/
cleanup: brev ls instances --json --all returned {"workspaces": null}; watchdog confirmed target disappeared
```

The successful runtime markers were:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE press-control: local-wall-sweep
CONTACT-SMOKE press-force: PASS (mean wall force [29.153621673583984, 37.27742004394531] N)
CONTACT-SMOKE press-tracking: PASS (lower-end lateral error [0.005723054055124521, 0.008925105445086956] m)
CONTACT-SMOKE press-blocked: PASS (lower_end_z - wall_top_z [0.009471744298934937, 0.008838444948196411] m)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
CONTACT-SMOKE phase-sequence: PASS
Contact physics smoke completed: all checks passed.
[contact-smoke] completed: contact physics is real
```

Validation and cleanup evidence:

```text
python3 scripts/check_phase2_contact_gate.py --log artifacts/launchable_logs/pulled_contact_smoke/rca-pull-gate/contact_physics_smoke_2026-06-20T13-01-54Z-gate.log --run-local-quality
  PASS: validated contact-physics smoke evidence

./scripts/run_local_quality_checks.sh
  passed

./scripts/brev_paid_safety_status.sh
  status=SAFE_NO_VISIBLE_PAID_INSTANCE
```

The smoke did not record an Isaac viewport video. A local log-replay mp4 was
generated for handoff review at
`artifacts/deliverables/2026-06-20-contact-smoke/contact_smoke_success_log_replay.mp4`;
it is an evidence visualization from the successful log, not simulator camera
footage.

A follow-up real Isaac viewport recording was captured on a separate official
AWS Isaac Launchable run:

```text
instance: isaac-launchable-e91de9 / 4akhlpjad
run_id: 2026-06-20T14-08-28Z-real-video
task: RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0
video_backend: viewport, Gym RecordVideo
video: artifacts/deliverables/2026-06-20-real-isaac-video/real_isaac_robot_arm_viewport_30s.mp4
video_probe: 1280x720, 30fps, 901 frames, 30.033333s
video_sha256: 2dc1dfd4affe26e165afef481e757d9ab411a25d0d1e5a3e90cbb3fa46e2db60
pulled_archive: artifacts/deliverables/2026-06-20-real-isaac-video/rca-real-isaac-video-4akhlpjad.tar.gz
pulled_archive_sha256: 8b2f59ed542f551d4e050fb49d10ceea191f8d8999f5748f249489b80f71f81b
cleanup: brev ls instances --json --all returned {"workspaces": null}; watchdog confirmed target disappeared
```

This mp4 is real simulator viewport/camera footage from Isaac/RTX. It is
included only for visual review of the mechanical scene and scripted arm motion;
it is not a success metric for peg insertion.

## 2026-06-20 Peg-In-Hole Video Candidate Overlay

The current goal is a real Isaac viewport video that visibly shows successful
peg-in-hole insertion. Existing 2026-06-20 `success_demo` traces do not satisfy
that goal: the best offset run reached lateral `0.004551m` but remained
axially high at `0.032649m`, while the close-depth runs reached about
`0.0079m` axial error but stayed laterally outside the hole at about `0.0086m`.
Do not label those mp4/trace artifacts as successful insertion.

The follow-up paid video-candidate run on `rca-peg-video-candidate-vm`
(`dzek7kcvq`) also failed the semantic insertion check. Artifacts were pulled
locally under:

```text
artifacts/videos/trace_only/2026-06-20T20-01-02Z/
artifacts/videos/trace_only/2026-06-20T20-03-01Z/
artifacts/videos/trace_only/2026-06-20T20-04-09Z/
artifacts/videos/scripted_screen/2026-06-20T19-54-53Z/
artifacts/videos/scripted_screen/2026-06-20T19-56-47Z/
```

The best fresh trace was
`artifacts/videos/trace_only/2026-06-20T20-04-09Z/video_trace.json`:

```text
success_step: null
final_success_rate: 0.0
initial_lateral: 0.009844m
best_lateral: 0.005550m
initial_axial: 0.059494m
best_axial: 0.030969m
best_rot: 0.013093rad
max_contact_force_magnitude: 1.211N
```

`scripts/check_peg_in_hole_video_candidate.py` correctly rejected it:

```text
task_gate_pass=False
video_candidate_pass=False
fail: task gate never reached sustained configured success tolerances
fail: pose never reached stricter guide-clearance lateral tolerance
fail: trace does not show enough visible insertion descent from above the socket
```

Decision: stop treating viewport-video capture as the main project route. The
video route is useful only after a trace already passes the semantic insertion
checker. Continuing to tune the same scripted/video wrapper is likely to repeat
the old dead-end loop.

The fail-closed validator is:

```bash
python3 scripts/check_peg_in_hole_video_candidate.py <video_trace.json>
```

It requires the task success gate, guide-clearance-level lateral alignment,
visible insertion descent, orientation readiness, and wall-contact evidence.
`scripts/run_remote_record_scripted_video.sh` now always writes
`video_trace.json`; set `RCA_VALIDATE_PEG_VIDEO_CANDIDATE=1` to make the remote
recording fail if the trace is not a valid insertion candidate.

The most recent one-shot paid wrapper was:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_ACK_BREV_LIFECYCLE_RISK=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
scripts/recreate_brev_and_record_peg_video_candidate.sh
```

The wrapper created one `g6e.xlarge` candidate VM with a watchdog, installed the
Isaac runtime, and pulled trace/video artifacts. IsaacLab's native `--video`
path triggered `omni.replicator.core` / `warp.context` failures in this runtime,
so the useful evidence came from trace-only runs rather than a verified success
mp4.

Current decision: the contact-smoke gate is no longer the blocker, and one fresh
post-smoke trace has now confirmed the controller is still the blocker. The
active Brev lifecycle hold still means any future paid GPU action needs a
specific budget, TTL, watchdog, artifact pullback, immediate deletion, and final
empty-org confirmation. The next technical step is now a structurally different
trace-only controller validation, not a video run:

```bash
scripts/run_remote_final_contact_servo_trace.sh <env-name> /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
```

This wrapper keeps the old success/video checker standards, but enables
`--final-contact-servo` and `--joint-cache-live-polish` so the late-contact
phase uses measured physical-tip socket-frame XY error instead of replaying the
same cached joint descent through polish.

The current route audit is documented in:

```text
docs/peg_in_hole_success_video_audit_2026-06-20.md
```

The first final-contact-servo trace-only validation ran on
`rca-final-contact-servo-vm` / `a19458wmx` and was rejected by the same
semantic checker:

```text
trace: artifacts/videos/trace_only/2026-06-20T20-56-43Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-20T20-56-43Z/video_summary.json
task_gate_pass: False
video_candidate_pass: False
best_lateral: 0.006714m
best_axial: 0.030362m
best_rot: 0.006569rad
max_contact_force_magnitude: 1.352N
final_contact_servo_step_count: 0
cleanup: independent brev ls returned {"workspaces": null}; brev safety returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

This failed run is still useful: it shows the controller reached the polish /
near-seat region with contact, but the new final-contact branch never activated.
The immediate bug was the entry gate in `scripts/scripted_agent.py`: it required
`insert_mask & polish_state`, while the trace had `polish_state=True` for all
steps and `insert_mask=False` for all steps. The local fix widens the
final-contact-servo phase mask to `insert_mask | polish_state` while retaining
the XY/Z/rotation entry and exit thresholds.

Next action after cleanup confirmation: run local quality, then decide whether
one more short trace-only paid validation is justified. Do not record a viewport
video unless the trace first passes `scripts/check_peg_in_hole_video_candidate.py`.

The patched final-contact-servo validation then ran on
`rca-final-contact-servo-vm` / `p5kzgtfdv`:

```text
trace: artifacts/videos/trace_only/2026-06-20T21-34-52Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-20T21-34-52Z/video_summary.json
task_gate_pass: False
video_candidate_pass: False
best_lateral: 0.001174m
best_axial: 0.000013m
best_rot: 0.010770rad
max_contact_force_magnitude: 8.715N
final_contact_servo_step_count: 701
```

This proves the final-contact branch now activates and can independently hit
the best XY, axial, rotation, and contact conditions, but not all at the same
sustained time. The closest simultaneous window was step `787`, phase
`final-contact-servo`, with lateral `0.0057m`, axial `0.0080m`, rotation
`0.0190rad`, and contact `1.242N`: about `0.7mm` outside the strict XY gate.
After that, XY improved below the success gate while axial error grew again.

The next attempted local fix made final-contact servo use the same signed
`mdp.tip_to_socket_position()` metric as the success checker for all XYZ
corrections. That full metric-error route was validated once and failed worse:

```text
trace: artifacts/videos/trace_only/2026-06-20T22-10-50Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-20T22-10-50Z/video_summary.json
instance: rca-final-contact-servo-vm / yht02yf57
task_gate_pass: False
video_candidate_pass: False
best_lateral: 0.007921m
best_axial: 0.031092m
best_rot: 0.008429rad
max_contact_force_magnitude: 1.066N
final_contact_servo_step_count: 26
cleanup: independent brev ls returned {"workspaces": null}; brev safety returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

Trace inspection shows the branch no longer holds the near-contact servo state:
`success_xy_ready=0`, `success_axial_ready=0`, and final-contact-servo is active
only briefly. Do not rerun the full `--final-contact-servo-metric-error` route
unchanged.

The narrower metric-Z-only route was then validated on
`rca-final-contact-servo-vm` / `3so4zayge` and also failed:

```text
trace: artifacts/videos/trace_only/2026-06-20T23-26-30Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-20T23-26-30Z/video_summary.json
task_gate_pass: False
video_candidate_pass: False
best_lateral: 0.007897m
best_axial: 0.028896m
best_rot: 0.008192rad
max_contact_force_magnitude: 26.991N
success_xy_ready: 0 steps
success_axial_ready: 0 steps
final_contact_servo_step_count: 54
cleanup: independent brev ls returned {"workspaces": null}; brev safety returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

Do not rerun metric-Z-only unchanged. The latest trace exposed a controller /
metric source mismatch: the task success metric uses the articulated `Peg` body
through `mdp.tip_to_socket_position()`, while the scripted controller's
`_physical_peg_tip_pose_w()` could fall back to the calibrated action frame.
The local fix now makes `_physical_peg_tip_pose_w()` prefer the same articulated
`Peg` body source before any legacy scene-asset or action-frame fallback.
`scripts/run_remote_final_contact_servo_trace.sh` no longer enables
`--final-contact-servo-metric-z` by default; set
`RCA_FINAL_CONTACT_SERVO_METRIC_Z=1` only for an explicit rerun diagnostic.

The canonical-tip validation after that local source fix ran on
`rca-final-contact-canonical2-vm` / `j2ktmtkoc` and failed the same semantic
checker:

```text
trace: artifacts/videos/trace_only/2026-06-21T00-34-31Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-21T00-34-31Z/video_summary.json
task_gate_pass: False
video_candidate_pass: False
best_lateral: 0.001173m
best_axial: 0.000015m
best_rot: 0.010770rad
max_contact_force_magnitude: 8.714N
success_xy_ready: 391 steps, first 809
success_axial_ready: 98 steps, first 690, last 787
success_contact_ready: 670 steps, first 520
success: 0 steps
cleanup: brev ls instances --json --all returned {"workspaces": null}; brev safety returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

The closest simultaneous step was still step `787`, phase
`final-contact-servo`, with lateral `0.0057m`, axial `0.0080m`, rotation
`0.0190rad`, and contact `1.237N`. After that point, XY moved into the
success window, but axial error moved back out to about `0.040m` by the end.

Current decision: do not record a viewport video from this route and do not run
broad paid sweeps of the scripted/video wrapper. The canonical-tip/no-metric-Z
route is closed as a success-video candidate. The subsequent hold-Z validation
also failed:

```text
artifact: artifacts/videos/trace_only/2026-06-21T01-17-49Z/video_trace.json
result: peg-video-candidate FAIL
best_lateral: 0.007927m
best_axial: 0.004304m
best_rot: 0.010770rad
max_contact_force_magnitude: 8.714N
success_xy_ready: 0 steps
success_axial_ready: 510 steps, first 690, last 1199
success_contact_ready: 170 steps, first 520
success: 0 steps
```

That trace is still useful because it isolates the next controller mismatch:
hold-Z kept the axial metric inside the success window, but the legacy
final-contact XY source was nearly zero while `mdp.tip_to_socket_position()`
still reported about `9.7mm` lateral error at the end. The next local candidate
is now `--final-contact-servo-metric-xy` plus hold-Z, not another plain hold-Z
rerun. It uses the task success metric only for final-contact XY centering while
leaving axial motion under the existing guarded descent/hold-Z policy. Only
after local quality passes and Brev safety returns
`SAFE_NO_VISIBLE_PAID_INSTANCE` should one short trace-only paid validation be
considered.

That metric-XY plus hold-Z validation then ran on
`rca-final-contact-metricxy-holdz-vm` / `qmo9s7hiu` and failed:

```text
trace: artifacts/videos/trace_only/2026-06-21T01-56-21Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-21T01-56-21Z/video_summary.json
task_gate_pass: False
video_candidate_pass: False
best_lateral: 0.000550m
best_axial: 0.029598m
best_rot: 0.009174rad
max_contact_force_magnitude: 11.841N
success_xy_ready: 409 steps, first 791, last 1199
success_axial_ready: 0 steps
success_contact_ready: 173 steps, first 603, last 785
success: 0 steps
cleanup: brev ls instances --json --all returned {"workspaces": null}; brev safety returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

This closes the metric-XY route as a success-video candidate. It fixed lateral
centering but did not produce insertion: axial depth never got closer than
about `29.6mm`, contact readiness ended before XY was ready, and rotation drifted
past the success gate by the late steps. Do not run another near-duplicate
final-contact-servo trace or any viewport video from this branch. The next work
should change the insertion/control formulation itself: for example, a stateful
socket-frame insertion controller that jointly holds XY, axial depth, contact,
and orientation, with a negative control, before any further paid run.

That next local controller candidate is now implemented but not yet remotely
validated. The new `--socket-insertion-servo` route:

1. uses `mdp.tip_to_socket_position()` for socket-frame XY correction,
2. refuses to spend socket-axis insertion depth unless XY and rotation are both
   inside configured descent tolerances,
3. steps orientation statefully toward the socket target instead of freezing the
   drifting current orientation,
4. applies a small contact preload only when axial depth is already ready but
   contact evidence is missing.

The pure command rule lives in `scripts/socket_insertion_servo_logic.py` and is
covered by offline negative controls in `scripts/test_local_gates.py`.
`./scripts/run_local_quality_checks.sh` passes after the implementation. The
prepared paid path is:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_ACK_BREV_LIFECYCLE_RISK=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
./scripts/recreate_brev_and_run_socket_insertion_servo_trace.sh rca-socket-insertion-servo-vm
```

Run this only after `./scripts/brev_paid_safety_status.sh` reports
`SAFE_NO_VISIBLE_PAID_INSTANCE`. Do not record a viewport video unless that
trace passes `scripts/check_peg_in_hole_video_candidate.py`.

## 2026-06-18 Current Overlay

The append-only history below contains useful controller and infrastructure evidence, but its early summary predates the 2026-06-11 contact-physics audit and is superseded by the 2026-06-20 PASS overlay above. The historical pre-PASS state was:

1. The contact-physics fix is implemented locally: dynamic peg welded to the hand, reset-only peg placement, socket walls as colliders, and wall-filtered force observations.
2. The fix has not yet been validated on an Isaac runtime. No archived `CONTACT-SMOKE ... PASS` log was found locally.
3. Older "true-contact", strict near-miss, BC, and reset-candidate metrics are diagnostic history only until regenerated under the validated contact model.
4. `python3 scripts/check_phase2_contact_gate.py` is the fail-closed local phase gate. It must report `BLOCKED` until a valid archived `contact_physics_smoke.log` exists.
5. `scripts/refresh_brev_login.sh` is the explicit Brev/NVIDIA CLI auth refresh step before paid preflight. It verifies auth with a read-only instance-list query and creates no resources.
6. `scripts/brev_paid_safety_status.sh` is the read-only Brev safety snapshot. It checks backend health, active org, `brev ls instances --json --all`, watchdog processes, watchdog ledgers, and the active lifecycle hold. When no paid job is intentionally active, it must show `visible_instances=0`.
7. `scripts/paid_compute_preflight.sh` is the fail-closed paid-compute gate. It requires explicit budget, conservative EUR/hour estimate, manual Brev UI credit verification (`RCA_BREV_CREDITS_VERIFIED=1`), TTL, Brev CLI auth, an empty visible org, estimated max cost inside the budget, and no active `docs/brev_launchable_lifecycle_hold.md` before any paid action.
8. `RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_BUDGET_EUR=<budget> RCA_PAID_ESTIMATED_EUR_PER_HOUR=<hourly-estimate> ./scripts/prepare_contact_smoke_run.sh` is the guarded preparation command for the one allowed paid contact-smoke run. It creates the exact current bundle to upload after local quality and paid preflight pass.
9. `scripts/remote_operation_preflight.sh` guards helpers that operate on an existing Brev environment. Before the contact gate passes, only `RCA_REMOTE_OPERATION_PURPOSE=contact_physics_smoke` is allowed.
10. `python3 scripts/project_status_report.py` is the read-only current-state snapshot command.
11. The next paid action, if any, is only the short contact-physics smoke gate with a watchdog and immediate deletion. Do not run training, BC, controller sweeps, or broad scripted probes before that.

## 2026-06-19 Local Guard Overlay

Additional local hardening after the 2026-06-18 audit:

1. `scripts/run_local_quality_checks.sh` no longer writes Python bytecode. It runs with `PYTHONDONTWRITEBYTECODE=1`, checks Python syntax by compiling source strings, and fails if generated cache/metadata (`__pycache__`, `.pyc`, `.DS_Store`, `*.egg-info`) is present.
2. `scripts/check_project_policy_compliance.py` now scans direct remote operations. Any script using direct `ssh`, `rsync`, `scp`, `sftp`, or `brev exec/copy/port-forward/shell/open` must use `scripts/remote_operation_preflight.sh`, `scripts/remote_common.sh` plus `rca_init_remote_vars`, or the paid-compute preflight.
3. `scripts/run_remote_eval_final_contact_candidate_bc.sh` now runs remote-operation preflight before uploading its manifest.
4. `scripts/contact_physics_smoke.py` and the phase gate require `press-no-clip` in addition to attach, free-space, press-force, press-blocked, release, joint-integrity, and wrapper completion markers.
5. Local preauth bundles match `artifacts/launchable/robot-contact-assembly-contact-smoke-manual-preauth-*.tar.gz`. These packages are only useful after Brev login is restored; for a real paid run, use the exact bundle path printed by `scripts/prepare_contact_smoke_run.sh`.
6. `scripts/pull_contact_smoke_log.sh` is the preferred pullback step after a remote contact smoke. It is scoped to `artifacts/launchable_logs/contact_physics_smoke.log`, uses the pre-gate `contact_physics_smoke` remote-operation purpose, and then runs the archive verifier.
7. `scripts/archive_contact_smoke_log.sh` is the local finalization step when the smoke log was obtained by another route. It validates the pulled log before installing it as `artifacts/launchable_logs/contact_physics_smoke.log`, then reruns the phase gate against the archived log.

## 2026-06-20 Launchable Runtime Evidence Overlay

Official AWS Isaac Launchable did reach a real Isaac Lab runtime on:

```text
instance: isaac-launchable-bcd83f / 9sm5kfu70
provider/type: AWS g6e.4xlarge L40S
runtime: nvcr.io/nvidia/isaac-lab:2.3.0 inside the official vscode container
cleanup: delete requested; watchdog confirmed target disappeared; final Brev list returned {"workspaces": null}
failure log:
  artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-bcd83f_2026-06-20T03-46-58Z_FAIL.log
```

The smoke failed on real semantic checks, not on setup:

```text
attach: FAIL
free-space: PASS
press-force: FAIL
press-blocked: FAIL
press-no-clip: FAIL
release: PASS
joint-integrity: FAIL
```

The important measurements were:

```text
after reset hand-peg error: [0.0032, 0.0068] m
after free-space settle hand-peg error: [0.1104, 0.2561] m
press wall force: [0.0, 0.0] N
lower-end sink below wall top: [0.2961, 0.3168] m
after retreat hand-peg error: [0.0648, 0.1091] m
```

Interpretation: the Launchable runtime is usable, but the contact shell was still using an invalid pose/quaternion assumption. Isaac Lab 2.x and Isaac Sim APIs use WXYZ quaternions, while the local contact shell still had legacy XYZW helpers and hard-coded rotations. This made action-frame targets, expected hand-to-peg transforms, and MDP peg pose metrics inconsistent once the hand moved.

Local fix after the run:

1. Core task constants now use Isaac Lab WXYZ quaternions.
2. USD joint authoring now accepts WXYZ and writes scalar-first USD quaternions directly.
3. MDP pose math and `scripts/contact_physics_smoke.py` now use WXYZ rotate/compose/subtract helpers.
4. MDP peg pose now prefers the actual `robot` articulation body named `Peg` and only falls back to hand-derived pose for legacy diagnostics.
5. Smoke diagnostics now log the measured local `hand -> peg` offset for the next runtime validation.
6. Local quality passes after the fix: `./scripts/run_local_quality_checks.sh`.

The later strict fixed-socket retry on `isaac-launchable-a6354c` / `xxv4vn1te`
used the WXYZ payload and kept attach/joint integrity valid, but still failed
before contact:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error about 0.16-0.19m)
CONTACT-SMOKE press-blocked: FAIL (lower end remained above the wall top)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
failure log:
  artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-a6354c_2026-06-20T05-12-01Z_FAIL.log
cleanup:
  delete requested; `brev ls instances --json --all` returned {"workspaces": null};
  watchdog printed `target disappeared; cleanup confirmed`
```

Interpretation: fixed-joint attachment is no longer the blocker. The strict
fixed-socket smoke still entangled contact-physics validation with long-range
absolute-IK reachability. Local follow-up changed `scripts/contact_physics_smoke.py`
to default to `--contact_setup local-guide`, which relocates the kinematic
socket walls under the current insertion tip and preserves `fixed-socket` as a
separate reachability diagnostic mode. `scripts/check_contact_physics_wiring.py`
now requires that local-guide relocation support.

The first `local-guide` runtime retry on `isaac-launchable-b8fc1e` /
`c51fxe4d3` used payload
`834a7f478ea8d225c3cd7a828266d5092ba9ae1f2a127411902af91fb1c9cc85`.
It again proved fixed-joint attachment and the free-space negative control, but
still failed before wall contact:

```text
CONTACT-SMOKE contact-setup: local-guide
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error [0.2286, 0.2145] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.0457, -0.0709] m)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
failure log:
  artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-b8fc1e_2026-06-20T05-50-21Z_FAIL.log
cleanup:
  delete was retried after Brev briefly reported the environment as DEPLOYING again;
  watchdog printed `target disappeared; cleanup confirmed`; final
  `brev ls instances --json --all` returned {"workspaces": null}
```

Interpretation: `local-guide` was still anchored too early. The arm moved
laterally during free-space settle, so the subsequent press still tested an old
pre-settle wall target instead of a vertical press from the actual settled lower
peg end. Local follow-up now re-anchors the guide after free-space settle,
re-checks free-space force as `CONTACT-SMOKE free-space-reanchored`, and then
presses straight down from the settled pose.

The phase-sentinel retry on `isaac-launchable-57032f` / `km6cr6mj0` used
payload `6c7513c22e56819c1402b358e66e5e252eeca83c648dcb3f30e41228b0d35345`
and first exposed an Isaac Lab/PyTorch inference-mode write failure in the
kinematic socket-guide root-pose write. After patching that targeted path, the
smoke reached all phases but still failed the semantic contact checks:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE phase-sequence: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error [0.04027855396270752, 0.36005330085754395] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.0764109194278717, 0.190305694937706] m)
CONTACT-SMOKE press-no-clip: FAIL (lower-end wall penetration [0.0, 0.190305694937706] m)
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
failure log:
  artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-29-28Z-1770.log
cleanup:
  delete requested and retried while Brev reported DELETING; final
  `brev ls instances --json --all` returned {"workspaces": null};
  `./scripts/brev_paid_safety_status.sh` returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

The Phase 2 contact gate remains BLOCKED because no current PASS smoke log
exists yet. Do not run controller sweeps, BC, RL, or broad scripted probes.
The smoke script's post-free-space control flow now reaches the press phase,
so local follow-up changed the press phase to use physical lower-end feedback
instead of a one-shot action-frame target. A future paid smoke is allowed only
after rebuilding the current bundle, local quality pass, watchdog, pullback,
immediate deletion, and final empty-org confirmation. Current prepared bundle:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T08-52-37Z.tar.gz
source_payload_sha256=87e962fe4ab08ceb2650dd9478208005a886e66d5b6288a909c6d11ff1954fb6
archive_sha256=30ebd5f89285c8313bd5bac23f70e6a626753926f19ca3195ff052b9b3b776b5
```

The lower-end feedback payload was then run once on `isaac-launchable-b4f35a`
(`/r6osffjlb` in the Brev CLI output) on AWS g6e.4xlarge L40S. It reached all
phases and preserved attachment, but still failed contact semantics:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE phase-sequence: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error [0.4718092679977417, 0.15390245616436005] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.6918212175369263, -0.03502988815307617] m)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
failure log:
  artifacts/launchable_logs/pulled_contact_smoke/rca-pull-b4f35a/contact_physics_smoke_2026-06-20T09-15-45Z-newfeedback.log
pull archive:
  artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-b4f35a-r6osffjlb.tar.gz
cleanup:
  final `brev ls instances --json --all` returned {"workspaces": null};
  watchdog printed `target disappeared; cleanup confirmed`;
  `./scripts/brev_paid_safety_status.sh` returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

Interpretation: the feedback loop was still wrong because it accumulated a
world target while IK lagged or saturated. The final target wound up far away
from the robot, so the run was useful as a control-diagnostic failure but not
as contact proof.

Current local follow-up:

1. `local-guide-reanchor` holds the current physical tip pose, not a lower-end
   hover point misused as an IK tip target.
2. The local guide is reanchored from the post-hold physical lower-end pose.
3. `step_track_lower_end()` now commands the current physical tip plus a
   bounded lower-end correction each step, preventing cumulative target
   windup.
4. Retreat also uses the bounded lower-end servo.

Current prepared bundle after this fix:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T09-32-10Z.tar.gz
source_payload_sha256=14da96a2a87e74c81220b3da09143b075ea933e33ec56a9f98faf54cdc9a34ef
archive_sha256=ccaa8a2f9e3e1afd3d05e702d91fd67934d1fc2bde3a7dbb10b163452d0fceea
local_quality: ./scripts/run_local_quality_checks.sh passed
```

The later deterministic reset / z-only lateral-lock retry on
`isaac-launchable-zlock-9b3c` (`hzekq6qqz`) used payload
`9b3cd761fb8843047260cc4a3be21cefe22268b7e2d85160c2014cbba4ab0182`.
Pulled evidence:

```text
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-zlock/contact_physics_smoke_2026-06-20T11-10-08Z-zlock.log
pull_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-zlock-hzekq6qqz.tar.gz
pull_archive_sha256: 2405e40d0477671a38c91a629c339fb9d020843f1e3864897ff3fd4020f20db1
```

The run improved the smoke controller but still did not prove contact physics:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE phase-sequence: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: PASS (lower-end lateral error about 0.0074m)
CONTACT-SMOKE press-blocked: FAIL (lower end remained about 0.016m above the wall top)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: FAIL (residual wall force [0.4584, 6.8527] N)
CONTACT-SMOKE joint-integrity: PASS
```

Interpretation: deterministic reset and z-only lateral locking removed the
large lateral runaway, but the arm-servo press still entangled the first
contact-physics gate with Franka IK reachability. Local follow-up now changes
the default smoke press mechanism to `guide-wall-sweep`: the robot holds the
reanchored pose while the local kinematic guide sweeps vertically into the
dynamic peg. This preserves `arm-servo` as a later controller diagnostic but
makes the Phase 2 gate isolate peg-vs-wall collision response first.

Current prepared bundle after the `guide-wall-sweep` change:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T11-21-30Z.tar.gz
source_payload_sha256=9a36b8041d8440fe7822c9711c8c4aa6047eb9582ec3b3e2d71f2accc009b1e2
archive_sha256=3248793a7ebbc52fde17936e6e814962be59fdcb3e093193673b49de174ad0dc
local_quality: ./scripts/run_local_quality_checks.sh passed
```

Do not open another paid retry until `hzekq6qqz` is no longer visible in
`brev ls instances --json --all` and `./scripts/brev_paid_safety_status.sh`
returns safe/no visible paid instance.

Cleanup after the zlock retry was confirmed: `brev ls instances --json --all`
returned `{"workspaces": null}`, the watchdog printed `target disappeared;
cleanup confirmed`, and `./scripts/brev_paid_safety_status.sh` returned
`SAFE_NO_VISIBLE_PAID_INSTANCE` with no watchdog processes.

## What This Project Is

This is an Isaac Lab peg-in-hole contact assembly project around a Franka Panda. Phase 1 was a proxy pose-target task. Phase 2 is being converted into a physical peg/socket contact shell with explicit peg geometry, guide-wall socket collisions, socket-frame insertion metrics, and contact-force sensing.

The current technical problem is contact-physics validation. Final contact stabilization remains downstream and should not be optimized until the wall-reaction smoke proves the task has real peg-vs-wall collision response.

## Audit Decision After 2026-06-09 Review

After reviewing the full repo, controller implementation, Launchable wrappers, cost guard scripts, and all local result archives, the next step should not be another broad sweep or another rot-polish variant. The one remaining scripted-controller candidate was:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
```

This was a one-shot validation candidate, not a new sweep family. It inherited the best prior Launchable branch (`softgated`) and only tightened the rotation gate near insertion depth. The reason was specific: the best Launchable result reached XY/Z/contact readiness and missed only rotation, while both later rot-polish runs made selected/final rotation worse.

Paid validation on 2026-06-09 completed and failed closed:

```text
instance: rca-neardepth-rotgate-vm / 5x0dmseey
provider/type: AWS g6e.xlarge L40S
smoke/runtime: passed
probe: 2026-06-09T06-45-39Z_jointpos-reachable-jointlimit-guard-neardepth-rotgate-probe
status: fail_closed
selected: step=1763 phase=align lateral=0.001235 axial=0.049536 rot=0.350150 contact=0.500092 strict_miss=2.155097
final: lateral=0.002205 axial=0.060102 rot=0.313013 success_rate=0.0
best: lateral=0.000371@1236 axial=0.047266@1760 rot=0.171399@98
tail: lateral=0.002955 axial=0.061385 rot=0.262909 contact=0.070176
limiter: panda_joint4 min_margin=0.096164 at step 1766
diagnosis: tail post-action movement makes little progress along the requested XY command
cleanup: artifacts copied; delete confirmed; final Brev list returned {"workspaces": null}
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.txt
```

Do not rerun unchanged or threshold-sweep these closed branches:

```text
softgated
rotpolish
adaptive rotpolish
near-depth rotgate
Abs IK/root/current/target/posture/solver/offset/no-wall variants
preload-direction historical replay
reachable-approach / tuned guard / hard rotgate unchanged
```

The near-depth probe also failed closed, so stop scripted-controller tuning in this branch. The next useful work is a different formulation: final-contact policy/data collection, a new posture/branch objective before insertion, or a controller that explicitly optimizes axis alignment and contact stability together.

Local follow-up after the paid run: `scripts/analyze_contact_demo_coverage.py` now accepts Launchable result `.tar.gz` archives directly. A combined audit of local scripted traces plus Launchable archives is saved at:

```text
artifacts/reports/contact_demo_coverage_with_launchable_2026-06-09.md
artifacts/reports/contact_demo_coverage_with_launchable_2026-06-09.json
```

Combined audit result:

```text
traces: 38
steps: 52947
target-gate passing steps: 0
traces with target-gate steps: 0
near-contact steps: 3773
traces with near-contact steps: 18
```

This confirms that the existing data is diagnostic/near-contact data, not a strict-success demonstration set. Do not train or pay for another ordinary one-step BC run expecting strict insertion success from these labels.

Next local formulation artifact prepared after that audit:

```text
scripts/select_final_contact_reset_candidates.py
artifacts/reports/final_contact_reset_candidates_2026-06-09.md
artifacts/reports/final_contact_reset_candidates_2026-06-09.json
```

This selector reads local traces plus Launchable result archives and classifies candidate reset/handoff states. Current manifest:

```text
candidates: 64
target_gate_success: 0
strict_near_miss: 8
rotation_only_miss: 29
depth_contact_rotation_conflict: 3
near_contact: 15
low_rot_no_contact: 9
```

Best reset seeds:

```text
2026-05-17T23-32-18Z step 1543 contact-retention miss=0.0320 lateral=0.0052 axial=0.0413 rot=0.1812 contact=0.5298
2026-05-17T22-00-19Z step 1541 contact-retention miss=0.0421 lateral=0.0043 axial=0.0412 rot=0.1842 contact=0.5263
```

Interpretation: these are good reset/handoff seeds for a final-contact stabilizer or reset-based RL/IL formulation, but they are not positive strict-success labels. The next implementation should consume this manifest to build a final-contact reset/evaluation path or generate new success-bearing demonstrations from these seeds.

Evaluator support prepared after the manifest:

```text
scripts/evaluate_contact_bc_policy.py
  --preload-candidate-json
  --preload-candidate-category
  --preload-candidate-index
```

The evaluator can now load a candidate from the manifest, set `--preload-trace-json` and `--preload-trace-end-step` automatically, and replay either a normal trace path or a Launchable `archive.tar.gz::member_trace.json` reference. This makes the manifest actionable for future final-contact stabilizer checks without manually copying trace paths.

Example command shape inside an Isaac runtime:

```bash
python3 scripts/evaluate_contact_bc_policy.py \
  --controller current-joint \
  --preload-candidate-json artifacts/reports/final_contact_reset_candidates_2026-06-09.json \
  --preload-candidate-category strict_near_miss \
  --preload-candidate-index 0 \
  --steps 400 \
  --deterministic-reset
```

This is only an evaluator preload convenience. It is not a new recommended paid run by itself.

Candidate-window dataset prepared locally:

```text
script: scripts/extract_final_contact_candidate_dataset.py
dataset: artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.jsonl
metadata: artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.metadata.json
samples: 3188
observation_mode: temporal-history
history_steps: 2
observation_dim: 77
action_dim: 7
action_mode: residual-current
strict_success_samples: 0
active_success_samples: 1
candidate windows: 40
category sample counts:
  strict_near_miss: 608
  rotation_only_miss: 2337
  depth_contact_rotation_conflict: 243
```

This dataset is useful as a stabilization prior or reset-window dataset around known hard final-contact states. It is not a positive final-success BC dataset because it still has zero strict-success samples.

Local training attempt:

```bash
python3 scripts/train_contact_bc_policy.py \
  --dataset artifacts/datasets/phase2_contact_bc_final_contact_candidates/phase2_contact_bc_final_contact_candidates_dataset.jsonl \
  --output artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt \
  --epochs 120 \
  --batch-size 256 \
  --hidden-dim 128 \
  --layers 3 \
  --device cpu
```

Result: not run locally because the host Python environment does not have PyTorch installed. The dataset is ready; checkpoint training needs the Isaac/PyTorch runtime.

Remote/runtime wrappers prepared for that next step:

```text
scripts/run_remote_train_final_contact_candidate_bc.sh
scripts/run_remote_eval_final_contact_candidate_bc.sh
```

These wrappers do not create Brev instances. They assume an existing Isaac/PyTorch runtime, sync the repo plus the required dataset/manifest artifacts, and run the existing train/eval entrypoints with reproducible defaults.

Training command shape:

```bash
scripts/run_remote_train_final_contact_candidate_bc.sh \
  <env-name> \
  <remote-root> \
  <remote-compose-root>
```

Default output:

```text
/workspace/artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt
```

Evaluation command shape after the checkpoint exists:

```bash
scripts/run_remote_eval_final_contact_candidate_bc.sh \
  <env-name> \
  <remote-root> \
  <remote-compose-root>
```

Default evaluation uses:

```text
controller: bc
candidate manifest: /workspace/artifacts/reports/final_contact_reset_candidates_2026-06-09.json
candidate category: strict_near_miss
candidate index: 0
checkpoint: /workspace/artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt
```

For a deterministic baseline from the same manifest seed, set:

```bash
RCA_FINAL_CONTACT_BC_CONTROLLER=current-joint \
scripts/run_remote_eval_final_contact_candidate_bc.sh <env-name> <remote-root> <remote-compose-root>
```

## Best Robotics Results

Historical shallow contact label, now invalidated as physical-contact proof:

```text
run: 2026-05-17T19-47-06Z
success_step: 1538
lateral: 0.0047 m
axial: 0.0419 m
rot: 0.1909 rad
contact: 0.6927
gate: xy<0.005, z<0.045, rot<0.20, contact>=0.5
```

Closest strict near miss:

```text
run: 2026-05-17T23-32-18Z
step: 1543
lateral: 0.0052 m
axial: 0.0413 m
rot: 0.1812 rad
contact: 0.5298
strict gate: xy<0.005, z<0.045, rot<0.18, contact>=0.5
miss: about 0.20 mm lateral and 0.0012 rad rotation
```

## Learned Policy Status

The BC/IL pipeline works end to end:

```text
scripted trace JSON -> dataset JSONL -> MLP checkpoint -> staged handoff eval -> pulled artifacts
```

But all one-step BC variants tested so far failed as contact stabilizers:

```text
all-trace BC:
  success_step: null
  near_contact_fraction: 0.0000
  best_strict_miss_score: 21.0692

best-window staged BC:
  success_step: null
  handoff_miss: 0.0319
  near_contact_fraction: 0.0125
  best_after_bc: 0.1865

near-contact residual-current BC:
  success_step: null
  handoff_miss: 0.0319
  near_contact_fraction: 0.0175
  longest_near_contact_streak: 6
  final_delta_vs_handoff: +45.5555
```

The current trace archive is not a final insertion success dataset:

```text
mainline JointPos traces: 18
near-contact steps: 3227
strict/target-gate passing steps: 0
```

Prepared but not yet run:

```text
artifacts/datasets/phase2_contact_bc_near_contact_temporal_residual_current/
samples: 3187
observation_dim: 77
action_dim: 7
observation_mode: temporal-history
history_steps: 2
```

Do not run the temporal BC smoke until either the data contains better sustained post-contact labels or there is a specific reason to test the temporal formulation despite the current label limitation.

## Deterministic Handoff Baselines

Completed:

```text
controller: current-joint
run: 2026-05-20T19-52-13Z_current-joint
success_step: null
near_contact_fraction: 0.0000
longest_near_contact_streak: 0
final_delta_vs_handoff: +58.8510
```

This means the handoff state is not passively stable.

Attempted but no robotics result:

```text
controller: last-preload-action
run dir: artifacts/gpu_gate/2026-05-20T20-02-49Z_isaac-phase2-contact-handoff-last-action-l4
status: Brev provisioning abort before SSH / Isaac / eval
```

Prepared but no robotics result:

```text
controller: preload-direction
script: scripts/run_phase2_contact_handoff_preload_direction_gate.sh
run dir: artifacts/gpu_gate/2026-05-20T20-30-57Z_isaac-phase2-contact-handoff-preload-dir-l4
status: Brev provisioning abort before SSH / Isaac / eval
```

This `preload-direction` line is now superseded by the later Launchable evidence. Do not run the historical replay/preload-direction family as the next robotics evaluation unless there is a deliberate replay-drift diagnostic.

## Brev / Compute Status

Brev support email sent:

```text
to: brev-support@nvidia.com
subject: Follow-up: repeated probe-only Brev lifecycle failures in org NCA-57cf-29515
sent id: 19e4e182e6100df1
```

Brev support replied on 2026-05-22:

- They confirmed no active instances, hidden workspaces, deployments, volumes, or other billable resources remained in org `NCA-57cf-29515`.
- They said GCP instance creation was working on their side.
- They interpreted the GCP issue as missing required port opening for Isaac Sim video streaming.
- They said Nebius does not provide native port-opening through the platform and suggested configuring ports manually with `ufw`.
- They recommended the official Isaac Launchable, preferably on AWS.

Weekly Brev summary received on 2026-05-24:

```text
credits remaining: $21.88
currently running instances: none
weekly cost May 17-24: $11.86
storage fees may still apply
```

Current local Brev CLI status:

```text
2026-05-24: CLI login was restored for org NCA-57cf-29515 during the probe.
2026-05-24 later: CLI login was restored again for the official AWS Launchable run and was used to upload patches, pull diagnostics, and delete the paid instance.
```

Post-probe resource checks on 2026-05-24:

```text
/Users/Shenghan/bin/brev ls instances --all
  No instances in org NCA-57cf-29515

/Users/Shenghan/bin/brev ls instances --json --all
  {"workspaces": null}
```

## Important Compute Interpretation

The previous probe-only wrappers aborted because `brev ls instances --all` stayed at:

```text
RUNNING / BUILDING / NOT READY
```

even after `brev create` printed:

```text
<instance-name>: Ready
```

The wrapper did not attempt SSH until `brev ls` showed `RUNNING / COMPLETED / READY`.

Implemented on 2026-05-24:

```bash
scripts/run_brev_probe_direct_ssh_gate.sh
```

This wrapper is still probe-only. It sets `RCA_GATE_DIRECT_SSH_AFTER_CREATE_READY=1`, shortens the list-readiness grace window, runs `brev refresh`, and tries direct SSH / `nvidia-smi` before declaring failure. Keep deletion guards strict.

Probe result after login on 2026-05-24:

```text
run dir: artifacts/gpu_gate/2026-05-24T14-42-53Z_isaac-probe-direct-ssh-l4
selected instance type: g2-standard-4:nvidia-l4:1
result: failure before SSH
failure point: Brev CreateWorkspace API returned unexpected EOF
cleanup: confirmed no visible instances after delete
final plain list: no instances in org NCA-57cf-29515
final JSON list: {"workspaces": null}
```

This did not reach the support-described "instance exists but ports are missing" state. It failed earlier at Brev's workspace creation API, so repeating Isaac jobs through the same Brev path is not currently justified.

Follow-up sent to Brev support on 2026-05-24:

```text
gmail message id: 19e5a76b4bfa654c
thread id: 19e4e182e6100df1
attachment: artifacts/gpu_gate/2026-05-24T14-42-53Z_isaac-probe-direct-ssh-l4/gate.log
summary: reported the post-login direct-SSH probe failure at CreateWorkspace unexpected EOF before SSH/Isaac/ports, and asked support to investigate the org/CLI create API path and reconfirm no hidden billable resources.
```

## AWS Isaac Launchable Attempts

Official AWS Launchable was tested on 2026-05-24 after Brev support recommended it:

```text
instance name: isaac-launchable-13e30f
instance id: c7hq6t3hp
provider: AWS
region shown by UI: Columbus, OH, USA
ip shown by UI: 3.148.248.184
machine: g6e.4xlarge
gpu: NVIDIA L40S, 44.70 GiB shown by UI / 46068 MiB from nvidia-smi
cpus/ram/disk: 16 CPUs / 128 GiB RAM / 256 GiB disk
price shown by UI: $3.64/hr
launchable setup: Running / Built / script Completed
deleted: 2026-05-24 18:05 CEST from the Brev UI after diagnostics were pulled
post-delete UI check: after page reload, the Environments list showed the "Create your first environment" empty state
```

The first instance proved that the official Launchable could bring up Isaac Sim, Isaac Lab, the containers, and the GPU, but exposed Isaac Lab 2.3 compatibility issues in the RCA code and smoke harness.

First-instance local bundle and diagnostics:

```text
bundle uploaded:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T14-53-58Z.tar.gz
latest local bundle after watchdog/AppLauncher diagnostics patch:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-11-12Z.tar.gz
latest local bundle after interval fix and diagnostic matrix:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-18-29Z.tar.gz
diagnostics pulled:
  artifacts/launchable_logs/rca-launchable-diagnostics-20260524.tar.gz
contains:
  headless_smoke_retry.log
  Isaac Sim Kit log kit_20260524_155616.log
```

Second AWS Launchable run on 2026-05-24:

```text
instance name: isaac-launchable-5c7e93
instance id: kkekc4hjq
provider: AWS
machine: g6e.4xlarge
gpu: NVIDIA L40S, 46068 MiB from nvidia-smi
price shown by UI: about $3.61/hr
uploaded bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-18-29Z.tar.gz
latest local bundle after final Launchable fixes/docs:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T16-51-46Z.tar.gz
latest local bundle after fresh-preload workflow:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-06-50Z.tar.gz
latest local bundle after fresh-preload guardrails:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-13-11Z.tar.gz
latest local bundle after historical-replay fail-closed guard:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T17-14-14Z.tar.gz
latest local bundle after Abs IK probe summary wiring:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T09-24-27Z.tar.gz
latest local bundle after root-frame Abs IK action fix:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-29-24Z.tar.gz
latest local bundle after Abs IK orientation-current diagnostic wiring:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
latest local bundle after native MDP arm-joint-limit trace wiring:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T13-27-35Z.tar.gz
diagnostics pulled:
  artifacts/launchable_logs/rca-launchable-diagnostics-kkekc4hjq.tar.gz
deleted:
  2026-05-24 after diagnostics were pulled; CLI deletion by name and id completed after Brev showed DELETING for several minutes
post-delete check:
  /Users/Shenghan/bin/brev ls instances --all -> No instances in org NCA-57cf-29515
  /Users/Shenghan/bin/brev ls instances --json --all -> {"workspaces": null}
remote project path:
  /workspace/robot-contact-assembly
preload trace:
  /workspace/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json
```

The official warmup Kit process initially held GPU memory and a Kit database lock; after it exited/was killed, GPU memory returned to 0 MiB and the RCA tests ran cleanly.

Isaac Lab 2.3 / Isaac Sim 5.1 compatibility fixes applied:

```text
scripts/zero_agent.py
scripts/evaluate_contact_bc_policy.py
```

These now fall back to `isaaclab.app.AppLauncher` / `parse_env_cfg` if the newer `isaaclab_tasks.utils` launcher helpers are unavailable, and avoid importing the RCA task before `SimulationApp` starts.

Additional fixes after the first Launchable attempt:

```text
source/robot_contact_assembly_tasks/.../peg_in_hole_env_cfg.py
  sync_peg_each_step interval changed from (0.0, 0.0) to sim.dt * decimation.

source/robot_contact_assembly_tasks/.../mdp/events.py
  sync_peg_to_hand now accepts Isaac Lab fields that are already torch.Tensor and only calls warp.to_torch() for non-torch data.

scripts/zero_agent.py
  missing SimulationContext.visualizers is handled in headless Launchable smoke.
  SystemExit during env/simulation close is ignored after logging, so real Python exceptions remain visible.

scripts/run_launchable_headless_smoke.sh
scripts/run_launchable_rca_diagnostic_matrix.sh
scripts/run_launchable_phase2_preload_direction.sh
  marker checks were added so reset/step/summary evidence is required; a misleading zero exit code is not enough.
```

Why: Isaac Lab's EventManager handles `interval` terms by subtracting the environment `dt` and firing terms whose sampled interval has elapsed. A zero interval therefore fires every manager call and leaves no positive countdown. The RCA term also writes the kinematic peg pose to simulation each time, so the safer equivalent is to use the actual environment-step period.

Marker-checked smoke result:

```text
command:
  ./scripts/run_launchable_headless_smoke.sh
task:
  RCA-PegInHole-Franka-JointPos-Contact-Play-v0
status:
  passed
markers:
  Environment reset completed
  Zero-agent step 10/10 completed
  Zero agent smoke test completed
log:
  launchable_logs/headless_smoke_marker_checked.log
```

Diagnostic matrix result:

```text
run: 2026-05-24T16-46-41Z_rca_smoke_matrix
00_builtin_reach_franka: 0
10_rca_ik_rel_play: 0
20_rca_jointpos_contact_play: 0
21_rca_jointpos_contact_play_no_interval: 0
log:
  launchable_logs/rca_diagnostic_matrix_marker_checked.log
```

Formal preload-direction eval:

```text
run: 2026-05-24T16-44-26Z_preload-direction
success_step: null
preload_success_step: null
bc_steps_executed: 400
preload_steps_executed: 1544
handoff_lateral: 0.2508
handoff_axial: 0.0464
handoff_rot: 2.1423
final_lateral: 0.1303
final_axial: 0.0366
final_rot: 2.5794
best_strict_miss_score: 34.9912
best_vs_handoff_strict_miss_delta: -9.3471
near_contact_fraction: 0.0000
max_contact_force_magnitude: 7.5659
summary:
  contact_handoff_baseline/2026-05-24T16-44-26Z_preload-direction/summary.json
```

Important replay finding:

```text
historical source step 1543:
  lateral: 0.0052
  axial: 0.0413
  rot: 0.1812
  contact: 0.5298

Launchable replay at source step 1543:
  lateral: 0.2508
  axial: 0.0464
  rot: 2.1423
  contact: 5.6489
```

Interpretation: the official AWS Launchable path now works for short Isaac Lab headless RCA runs, but the historical joint-position `raw_action` trace is not portable enough across the old Isaac runtime and Isaac Lab 2.3. The `2026-05-24T16-44-26Z_preload-direction` result should be treated as a valid runtime/replay-drift diagnostic, not a fair controller-quality result. That requirement to generate fresh traces inside the Launchable runtime was later satisfied by the fresh-controller runs below.

## Fresh Launchable Controller Result

A later official AWS Launchable run, `isaac-launchable-fb61a7` / `pk2xmabsc`, tested the fresh-trace path in the same Isaac Lab 2.3 / Isaac Sim 5.1 runtime.

Passed runtime checks:

```text
smoke log:
  artifacts/launchable_logs/headless_smoke_final_legacy_convention.log
bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-24T18-13-18Z.tar.gz
latest local bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T09-24-27Z.tar.gz
```

Main fresh-preload result:

```text
run:
  evaluations/scripted/2026-05-24T17-55-26Z_fresh-preload
scripted status:
  completed 1900 steps
selected handoff step:
  14
selected handoff:
  lateral=0.0049
  axial=0.5937
  rot=2.4654
  contact=6.9205
  strict_miss_score=77.7206
post-handoff eval:
  skipped fail-closed because strict_miss_score > 1.0
```

Additional diagnostics on the same Launchable showed:

```text
geom-debug-20260524T180147Z:
  action frame and physical peg tip remain aligned; the blocker is controller/target behavior, not sync_peg_to_hand drift.

2026-05-24T18-06-31Z_fresh-preload:
  naive WXYZ constant migration made the initial geometry worse and still failed closed.

wxyz-no-rotate-before-descend-20260524T180931Z:
  improved axial motion but let lateral drift badly.

legacy-const-wxyz-helper-20260524T181152Z:
  WXYZ local quaternion helpers were incompatible with the calibrated legacy constants.

legacy-no-rotate-before-descend-20260524T181338Z:
  removing rotate-before-descend under the calibrated legacy convention also drifted laterally.
```

Interpretation: the current Launchable runtime is usable, but the previous scripted handoff generator is not. Do not spend another paid run sweeping the old full-quaternion controller family. Keep the calibrated legacy frame constants/helper convention unless a dedicated remote calibration replaces it end to end.

Implemented after this result:

```text
source/.../constants.py
  SOCKET_INSERTION_AXIS_LOCAL = (0, 0, 1)
  SOCKET_INSERTION_AXIS_SIGN_INVARIANT = True

source/.../mdp/observations.py
source/.../mdp/terminations.py
source/.../mdp/rewards.py
  success / reward rotation now uses calibrated sign-invariant cylinder-axis error,
  not full quaternion distance.

scripts/scripted_agent.py
  adds --orientation-target-mode axis-align-current
  This aligns the insertion axis while preserving the current twist about the cylindrical peg.

scripts/run_launchable_phase2_fresh_preload_direction.sh
  uses --orientation-target-mode axis-align-current by default.
```

Offline analysis of the failed fresh Launchable trace confirmed that full-quaternion alignment pushed the robot toward a joint limit while lateral error grew from the early `0.0043m` near-center state to about `0.58m`.

The axis-aware paid validation has now been run:

```text
instance: isaac-launchable-837c5c / e9v2t2tsw
provider: AWS g6e.4xlarge L40S
smoke: passed
fresh-preload: failed closed before post-handoff eval
selected_handoff_step: 7
selected_handoff: lateral=0.0082 axial=0.6031 rot=0.9302
strict_miss_score: 63.6295
diagnostics: artifacts/launchable_logs/rca-launchable-diagnostics-e9v2t2tsw.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-e9v2t2tsw.tar.gz
cleanup: brev delete e9v2t2tsw; browser UI and brev ls confirmed no remaining instances
```

The official Launchable cloud-init path also failed on this instance because the generated per-boot/per-instance scripts were empty and produced `Exec format error`; manually starting the official `isaac-sim/isaac-launchable` compose stack brought up `vscode`, `web-viewer`, and `nginx`.

A short no-rotate-before-descend diagnostic on the same instance produced useful but still failing evidence: `best_lateral=0.0041@11`, `best_axial=0.0611@1221`, `best_rot=0.1868@1092`, `final_lateral=0.4124`, `success_step=null`. This shows depth/axis alignment are individually reachable, but XY retention collapses during rotation/descent.

Implemented after this result:

```text
scripts/scripted_agent.py
  adds --rotate-xy-retention / --rotate-xy-retention-tol
  adds --descend-xy-retention / --descend-xy-retention-tol
  When lateral error exceeds the threshold during staged rotation/descent, the controller freezes orientation/Z progress,
  clears the stateful rotate command, and uses the existing socket-XY target to recover lateral alignment.
  Summary JSON reports recovery step counts, first/last recovery steps, and max lateral error seen during recovery.

scripts/run_launchable_phase2_fresh_preload_direction.sh
  enables both retention gates by default with 0.012m thresholds.

scripts/select_preload_handoff_step.py
  includes rotate_xy_recovery / descend_xy_recovery in the selected handoff JSON.
```

The XY-retention paid validation has now also been run:

```text
instance: isaac-launchable-1e19c4 / 1cozht94s
provider: AWS g6e.4xlarge L40S
smoke: passed
fresh-preload: failed closed before post-handoff eval
run: 2026-05-24T21-14-20Z_fresh-preload
selected_handoff_step: 8
selected_handoff: lateral=0.0065 axial=0.6025 rot=0.9335
strict_miss_score: 63.4364
rotate_xy_recovery_step_count: 1767
rotate_xy_recovery_max_lateral: 1.0018
descend_xy_recovery_step_count: 122
descend_xy_recovery_max_lateral: 0.9774
diagnostics: artifacts/launchable_logs/rca-launchable-diagnostics-1cozht94s.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-1cozht94s.tar.gz
cleanup: brev delete 1cozht94s; subsequent SSH lookup failed; browser UI showed empty environments
note: brev ls/list JSON timed out during the final post-delete check
```

Interpretation: the XY-retention flags are being detected, but they do not recover the current joint-IK branch. Two live-patched joint-step limiter diagnostics were also tried on the same instance:

```text
--joint-step-limit-mode global
  stopped early around step 1625
  never produced a useful handoff; XY approach was too slow/poor and axial/rot worsened

--joint-step-limit-mode after-xy-global
  stopped early around step 1450
  improved worst lateral drift versus the component baseline, but still plateaued around 0.17-0.20m
```

`scripts/scripted_agent.py` keeps `--joint-step-limit-mode {component,global,after-xy-global}` as a diagnostic switch, but `scripts/run_launchable_phase2_fresh_preload_direction.sh` uses the original component clipping by default. Do not spend another paid run on this scripted handoff family.

Prepared after this result:

```text
scripts/run_launchable_phase2_absik_handoff_probe.sh
```

This is a new Launchable-only probe for the older, more promising Abs IK control surface (`RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`). It is intentionally scripted-only: it generates a fresh Abs IK trace, selects the best handoff with `scripts/select_preload_handoff_step.py`, and fails closed if `strict_miss_score > 1.0`. It does not run `preload-direction`.

The wrapper now also writes:

```text
probe_summary.json
```

That compact summary records the scripted final/best metrics, the selected handoff, strict-miss component contributions, first per-axis ready steps, phase counts, and the final `pass` / `fail_closed` decision. Use it first before opening long Isaac logs.

Why this branch is different: the failed Launchable family wrote joint targets through a standalone JointIK pre-controller. The Abs IK branch lets Isaac Lab's native `DifferentialInverseKinematicsActionCfg` action term solve the pose target. Historical Brev evidence from 2026-05-15/16 showed this surface could reach `best_lateral=0.0005`, `best_axial=0.0467`, and `best_rot=0.0041`; the remaining blocker was contact-induced jump/retention, not initial handoff generation.

The Abs IK probe was then run on AWS Launchable:

```text
instance: isaac-launchable-4a2c79 / ij912di64
provider: AWS g6e.4xlarge L40S
observed price: $3.61/hr while running; UI showed $0.04/hr while DELETING
cloud-init: failed again because generated per-boot/per-instance scripts were empty
manual recovery: cloned isaac-sim/isaac-launchable and ran docker compose in isaac-lab
smoke: passed
run: 2026-05-25T09-44-02Z_absik-handoff-probe
post-handoff eval: not run by design
decision: fail_closed
selected_handoff_step: 319
selected_handoff: lateral=0.1112 axial=0.0171 rot=0.6220 contact=4.9495
strict_miss_score: 15.0390
strict_miss_components: lateral=10.6192 rot=4.4198 axial=0 contact=0
z_ready_step_count: 285
contact_ready_step_count: 320
xy_ready_step_count: 0
rot_ready_step_count: 0
artifacts: artifacts/launchable_logs/rca-absik-probe-results-ij912di64.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-ij912di64.tar.gz
cleanup: delete requested by name and id; final CLI checks showed no instances and JSON {"workspaces": null}
```

Interpretation: this short Abs IK probe solved depth/contact but never came close on XY or rotation in the Launchable runtime. It also stayed in `reach` phase for all 320 steps, and best lateral was the final step. The first local fix was to change the wrapper default from 320 to 1200 steps; follow-up trace/source review then found the more important issue: the native 7D MDP Abs IK branch was writing world-frame absolute pose targets into Isaac Lab's root-frame `DifferentialInverseKinematicsAction` command. `scripts/scripted_agent.py` now defaults to `--mdp-abs-action-frame root`, keeps `world` only as a legacy diagnostic path, and the Launchable Abs IK wrapper explicitly passes `--mdp-abs-action-frame root`. Do not rerun the old 320-step/world-frame probe.

The root-frame Abs IK probe was then run on AWS Launchable:

```text
instance: isaac-launchable-fdfaba / ez3iyhmlw
provider: AWS g6e.4xlarge L40S
observed price: $3.61/hr while running
cloud-init: failed again because generated per-boot/per-instance scripts were empty
manual recovery: reused the official isaac-sim/isaac-launchable compose stack
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-29-24Z.tar.gz
smoke: passed
run: 2026-05-25T12-47-17Z_absik-handoff-probe
post-handoff eval: not run by design
decision: fail_closed
mdp_abs_action_frame: root
selected_handoff_step: 330
selected_handoff: lateral=0.1110 axial=0.0172 rot=0.6225 contact=4.9089
strict_miss_score: 15.0255
strict_miss_components: lateral=10.6001 rot=4.4254 axial=0 contact=0
final_lateral: 0.0578
final_axial: 0.0286
final_rot: 1.5049
success_step: null
z_ready_step_count: 1165
contact_ready_step_count: 1200
xy_ready_step_count: 0
rot_ready_step_count: 0
artifacts: artifacts/launchable_logs/rca-root-absik-probe-results-ez3iyhmlw.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-ez3iyhmlw.tar.gz
cleanup: delete requested by name and id; Brev UI confirmed DELETING at $0.00/hr, and final CLI check returned {"workspaces": null}
```

Interpretation: converting the native 7D MDP Abs IK action from world frame to robot root frame did not materially solve the Launchable handoff blocker. Root frame is still the correct Isaac Lab action convention, but the probe stayed in `reach`, never reached XY/rotation readiness, and selected essentially the same guarded handoff as the earlier 320-step run. The likely issue is now deeper in the scripted Abs IK target/action semantics, quaternion/axis handling, or controller formulation; do not spend another paid Launchable run on the same Abs IK probe unchanged.

Prepared after this result:

```text
scripts/scripted_agent.py
  --mdp-abs-orientation-command-mode {target,current}

scripts/run_launchable_phase2_absik_handoff_probe.sh
  RCA_LAUNCHABLE_MDP_ABS_ORIENTATION_COMMAND_MODE=current
latest bundle:
  artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
```

Default `target` preserves the previous behavior. Diagnostic `current` keeps sending a valid native 7D absolute MDP command but replaces the commanded quaternion with the measured current action-frame quaternion before converting to robot root frame. This intentionally makes the run position-only for the native IK action; if XY then converges, the blocker is the pose/orientation coupling. If XY still does not converge, focus next on target-frame geometry, body offset convention, collision/contact, or controller formulation rather than quaternion tracking.

That orientation-current diagnostic was then run on AWS Launchable:

```text
instance: isaac-launchable-18d403 / v8g5gmij4
provider: AWS g6e.4xlarge L40S
cloud-init: failed again with empty per-boot/per-instance scripts
manual recovery: official isaac-sim/isaac-launchable compose stack
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-57-19Z.tar.gz
smoke: passed
run: 2026-05-25T13-17-53Z_absik-handoff-probe
post-handoff eval: not run by design
decision: fail_closed
mdp_abs_action_frame: root
mdp_abs_orientation_command_mode: current
selected_handoff_step: 325
selected_handoff: lateral=0.1111 axial=0.0172 rot=0.6251 contact=4.9233
strict_miss_score: 15.0579
strict_miss_components: lateral=10.6068 rot=4.4511 axial=0 contact=0
best_lateral: 0.0578@638
best_axial: 0.0006@56
best_rot: 0.6235@302
final_lateral: 0.0578
final_axial: 0.0286
final_rot: 1.5048
success_step: null
z_ready_step_count: 665
contact_ready_step_count: 700
xy_ready_step_count: 0
rot_ready_step_count: 0
artifacts: artifacts/launchable_logs/rca-absik-current-probe-results-v8g5gmij4.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v8g5gmij4.tar.gz
cleanup: delete requested by name and id; final CLI check returned no instances and {"workspaces": null}
```

Interpretation: holding the commanded orientation at the measured current quaternion did not improve XY at all. The curve and selected handoff are effectively the same as the target-orientation root-frame run, so the blocker is not simply full-pose orientation coupling. Next focus should be local-first target/action-frame geometry, body offset convention, contact/collision constraints during XY approach, or replacing this scripted native Abs IK handoff formulation.

Prepared after this result:

```text
scripts/scripted_agent.py
  trace rows include post_arm_joint_pos, post_arm_joint_vel, post_arm_joint_limit_margin
  summary includes min_arm_joint_limit_margin and min_arm_joint_limit_margin_step

scripts/analyze_absik_probe_trace.py
  reads trace JSON or a pulled diagnostics tarball
  summarizes target/command/action/post-action tracking residuals

scripts/run_launchable_phase2_absik_handoff_probe.sh
  writes tracking_analysis.json
  RCA_LAUNCHABLE_ABS_CONTROL_MODE={waypoint,target}
  RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 for diagnostic runs through brev exec
```

The new analyzer was run locally against both `artifacts/launchable_logs/rca-root-absik-probe-results-ez3iyhmlw.tar.gz` and `artifacts/launchable_logs/rca-absik-current-probe-results-v8g5gmij4.tar.gz`. Both show the same fixed point: inferred `abs_pos_step=0.0300m`, tail `command_to_post_action_xy≈0.0315m`, tail `target_to_command_y≈-0.027m`, and tail `post_action_step_delta_xy≈0`. Interpretation: the waypoint command stays one step short in Y while the measured action-frame tip has stopped moving. The follow-up paid Abs IK diagnostic therefore used full target commands, not another waypoint run:

```bash
RCA_LAUNCHABLE_ABS_CONTROL_MODE=target \
  RCA_LAUNCHABLE_SCRIPTED_STEPS=500 \
  RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1 \
  ./scripts/run_launchable_phase2_absik_handoff_probe.sh
```

Use `RCA_LAUNCHABLE_FAIL_CLOSED_EXIT_ZERO=1` when running through `brev exec`; otherwise the expected fail-closed nonzero exit can be misclassified by the Brev CLI as a connection failure and retried.

Target-command diagnostic result:

```text
instance: rca-absik-target-vm / 6siwq7a2t
provider: AWS g6e.4xlarge L40S plain Brev VM
reason for plain VM: brev create --launchable still failed with lifecycle script is empty
manual runtime: cloned isaac-sim/isaac-launchable, docker compose up -d in isaac-lab
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T15-05-37Z.tar.gz
smoke: passed
run: 2026-05-25T15-22-37Z_absik-handoff-probe
decision: fail_closed
abs_control_mode: target
mdp_abs_action_frame: root
mdp_abs_orientation_command_mode: target
selected_handoff_step: 23
selected_handoff: lateral=0.1067 axial=0.0110 rot=0.7833 contact=1.8385
strict_miss_score: 16.2003
best_lateral: 0.0556@276
best_axial: 0.0003@18
best_rot: 0.7833@23
final_lateral: 0.0556
final_axial: 0.0277
final_rot: 1.5167
success_step: null
xy_ready_step_count: 0
rot_ready_step_count: 0
z_ready_step_count: 488
contact_ready_step_count: 498
min_arm_joint_limit_margin: -0.00023@103
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.0556, post_action_step_delta_xy≈0
joint-limit analysis: limiting_joint=panda_joint4, global_min=-0.0002255@103, tail_mean_margin≈2.2e-6, tail limiting_joint_counts={panda_joint4: 50}
artifacts: artifacts/launchable_logs/rca-absik-target-probe-results-6siwq7a2t.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-6siwq7a2t.tar.gz
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: full target commands remove the waypoint short-command issue (`target_to_command_xy=0.0`) but do not move the measured action-frame tip to the socket. The tail has `command_to_post_action_xy≈0.0556m` and almost zero post-action motion, so the remaining blocker is not the waypoint formulation. The trace now points specifically at `panda_joint4` lower-limit saturation: it is the global minimum-margin joint, remains within `1e-4` for all 500 samples, and is still the limiting tail joint. The next local-first change should reduce or avoid that posture pressure before another paid run: change the approach/target pose, add joint-limit avoidance/nullspace behavior, or test whether contact/collision constraints are forcing the same joint-limit plateau.

Initial `panda_joint4=-2.6` diagnostic result:

```text
instance: rca-absik-j4init-vm / v0w2i1mp2
provider: AWS g6e.4xlarge L40S plain Brev VM
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T16-49-17Z.tar.gz
smoke: passed
run: 2026-05-25T17-01-54Z_absik-handoff-probe
decision: fail_closed
abs_control_mode: target
initial_joint_pos_overrides: panda_joint4=-2.6
selected_handoff_step: 15
selected_handoff: lateral=0.1334 axial=0.0350 rot=1.2837 contact=3.2904
strict_miss_score: 23.8804
best_lateral: 0.1184@403
best_axial: 0.0230@403
best_rot: 1.1633@0
final_lateral: 0.1185
final_axial: 0.0230
final_rot: 1.4629
success_step: null
xy_ready_step_count: 0
rot_ready_step_count: 0
z_ready_step_count: 486
contact_ready_step_count: 500
pre-step global limit: panda_joint6 margin=0.0@0
post-step global limit: panda_joint4 margin=3.34e-6@0
joint-limit tail: limiting_joint_counts={panda_joint4: 50}
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.1185, post_action_step_delta_xy≈5.85e-6
artifacts: artifacts/launchable_logs/rca-absik-j4init-probe-results-v0w2i1mp2.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v0w2i1mp2.tar.gz
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: moving only `panda_joint4` away from the lower limit before reset made the native Abs IK target-mode run worse, not better. The first commanded action immediately pushed `panda_joint4` back to the lower-limit plateau, while the pre-step trace also shows `panda_joint6` at its upper limit at step `0`. Do not spend another paid run on a single-joint initial elbow offset. The next useful work is a controller/action formulation that can avoid joint limits explicitly, a different full-arm initial posture, or a target/approach pose change that does not drive the native IK solver into the same branch.

Contact/collision diagnostic after the j4-init result:

```text
new scripted flag: --disable-socket-wall-collisions
new wrapper env: RCA_LAUNCHABLE_DISABLE_SOCKET_WALL_COLLISIONS=1
analyzer additions: tail socket-frame contact force and physical peg-tip residual summaries
```

Re-analysis of the two latest artifacts showed the target command was already exactly at the desired XY (`target_to_command_xy=0.0`) while contact force persisted and the action-frame tip stalled. A no-wall-collision target-mode probe was run on a plain AWS Brev VM:

```text
instance: rca-absik-nowall-vm / 11ieede24
provider: AWS g6e.4xlarge L40S plain Brev VM
bundle: artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz
smoke: passed
run: 2026-05-25T18-21-28Z_absik-handoff-probe
decision: fail_closed
abs_control_mode: target
disable_socket_wall_collisions: true
selected_handoff_step: 337
selected_handoff: lateral=0.0957 axial=0.0086 rot=0.5281 contact=1.8613
strict_miss_score: 12.5491
best_lateral: 0.0704@129
best_axial: 0.0002@322
best_rot: 0.5242@340
final_lateral: 0.0825
final_axial: 0.0255
final_rot: 0.7460
success_step: null
xy_ready_step_count: 0
rot_ready_step_count: 0
z_ready_step_count: 488
contact_ready_step_count: 498
tracking tail: target_to_command_xy=0.0, command_to_post_action_xy≈0.0825, post_action_step_delta_xy≈1.2e-5
joint-limit analysis: panda_joint4 global_min=-0.0002255@103; tail_mean_margin≈0.1588; tail limiting_joint_counts={panda_joint4: 50}
artifacts: artifacts/launchable_logs/rca-absik-nowall-parked-probe-results-11ieede24.tar.gz
cleanup: delete requested by name and id; later CLI polling returned {"workspaces": null}
```

The first no-wall attempt only changed the authored collision property and still showed unchanged contact force, so the flag was strengthened to also park all four guide-wall prims far away before scene creation. The parked-wall run was still fail-closed and worse than full-target baseline (`8.25cm` final/tail residual instead of `5.56cm`). Interpretation: guide-wall collision is not the main XY blocker. Also, `peg_contact_force_magnitude` is based on the peg sensor's `net_forces_w`, not a wall-only force channel, so do not interpret persistent contact force as proof of socket-wall blockage.

Target-offset tracking diagnostic result:

```text
remote vm: rca-absik-offset-vm / v2319sjd7
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-target-offset-matrix-2026-05-25.tar.gz
matrix script: scripts/run_launchable_absik_target_offset_matrix.sh
artifact: artifacts/launchable_logs/rca-absik-target-offset-matrix-results-v2319sjd7.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-v2319sjd7.txt
```

Cases:

```text
baseline:
  decision: fail_closed
  selected: step=23 lateral=0.1067 axial=0.0110 rot=0.7833 strict_miss=16.2003
  final: lateral=0.0556 axial=0.0277 rot=1.5167
  best_lateral: 0.0556@276
  ready_counts: xy=0 rot=0 success_step=null
  tracking tail: command_to_post_action_xy≈0.0556, true target tail≈0.0556, post_action_step_delta_xy≈3.1e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

target_y_neg_04, offset=0,-0.04,0:
  decision: fail_closed
  selected: step=88 lateral=0.0709 axial=0.0117 rot=1.4063 strict_miss=18.8528
  final: lateral=0.0710 axial=0.0117 rot=1.4070
  best_lateral: 0.0709@88
  ready_counts: xy=0 rot=0 success_step=null
  tracking tail: biased command_to_post_action_xy≈0.0973, true target tail≈0.0710, post_action_step_delta_xy≈3.8e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

target_y_pos_04, offset=0,0.04,0:
  decision: fail_closed
  selected: step=282 lateral=0.0765 axial=0.0268 rot=0.4895 strict_miss=10.2475
  final: lateral=0.0778 axial=0.0331 rot=0.8050
  best_lateral: 0.0765@284
  ready_counts: xy=0 rot=0 success_step=null
  tracking tail: biased command_to_post_action_xy≈0.0396, true target tail≈0.0774, post_action_step_delta_xy≈1.8e-5
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}
```

Interpretation: the commanded fixed point moves with a biased target, so the action path is not completely ignored. But neither sign of the simple Y bias improves true socket XY, and all three cases remain locked on the `panda_joint4` limiting branch with no XY/rotation readiness. Do not spend another paid run on target offsets or guide-wall collision. The next local-first diagnostic is the native IK solver-method matrix:

```text
new scripted flag: --mdp-abs-ik-method dls|pinv|svd|trans
new wrapper env: RCA_LAUNCHABLE_MDP_ABS_IK_METHOD=dls|pinv|svd|trans
new matrix script: scripts/run_launchable_absik_ik_method_matrix.sh
default matrix cases: dls, pinv, svd, trans
```

IK solver-method matrix result:

```text
remote vm: rca-absik-ikmethod-vm / h9xqkqowr
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-ik-method-matrix-2026-05-25.tar.gz
matrix script: scripts/run_launchable_absik_ik_method_matrix.sh
artifact: artifacts/launchable_logs/rca-absik-ik-method-matrix-results-h9xqkqowr.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-h9xqkqowr.txt
```

Cases:

```text
dls:
  decision: fail_closed
  selected: step=23 lateral=0.1067 axial=0.0110 rot=0.7833 strict_miss=16.2003
  final: lateral=0.0556 axial=0.0277 rot=1.5167
  best_lateral: 0.0556@276
  ready_counts: xy=0 rot=0 z=338 contact=348 success_step=null
  tracking tail: command_to_post_action_xy≈0.0556, post_action_step_delta_xy≈3.1e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

pinv:
  decision: fail_closed
  selected: step=23 lateral=0.1061 axial=0.0110 rot=0.8223 strict_miss=16.5356
  final: lateral=0.0554 axial=0.0273 rot=1.5201
  best_lateral: 0.0554@311
  ready_counts: xy=0 rot=0 z=338 contact=348 success_step=null
  tracking tail: command_to_post_action_xy≈0.0554, post_action_step_delta_xy≈2.5e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

svd:
  decision: fail_closed
  selected/final/tracking: effectively identical to pinv
  final: lateral=0.0554 axial=0.0273 rot=1.5201
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

trans:
  decision: fail_closed
  selected: step=13 lateral=0.1349 axial=0.0305 rot=0.4393 strict_miss=15.5812
  final: lateral=0.1386 axial=0.0348 rot=0.4472
  best_lateral: 0.1349@13
  ready_counts: xy=0 rot=0 z=350 contact=350 success_step=null
  tracking tail: command_to_post_action_xy≈0.1386, post_action_step_delta_xy≈3.3e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}
```

Interpretation: changing Isaac Lab's native IK solver method does not remove the failure. `pinv`/`svd` are a numerically tiny lateral change from `dls` and still saturate `panda_joint4`; `trans` changes the posture enough to improve rotation but loses true XY badly. The native Abs IK solver-method sweep is closed. The next useful diagnostic is now wired as a full-arm reset/posture matrix:

```text
new matrix script: scripts/run_launchable_absik_full_arm_posture_matrix.sh
default matrix cases: baseline, ready_mid, elbow_open, yaw_pos, yaw_neg
case variable: RCA_LAUNCHABLE_ABS_IK_POSTURE_CASES=name:panda_joint1=...,panda_joint2=...
```

Full-arm reset/posture matrix result:

```text
remote vm: rca-absik-posture-vm / 5sjedqlea
gpu: AWS g6e.4xlarge / L40S
bundle: artifacts/launchable/robot-contact-assembly-launchable-full-arm-posture-matrix-2026-05-25.tar.gz
matrix script: scripts/run_launchable_absik_full_arm_posture_matrix.sh
artifact: artifacts/launchable_logs/rca-absik-full-arm-posture-matrix-results-5sjedqlea.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-5sjedqlea.txt
```

Cases:

```text
baseline:
  decision: fail_closed
  selected: step=23 lateral=0.1067 axial=0.0110 rot=0.7833 strict_miss=16.2003
  final: lateral=0.0556 axial=0.0277 rot=1.5167
  best_lateral: 0.0556@276
  ready_counts: xy=0 z=338 rot=0 contact=348 success_step=null
  tracking tail: target_to_post_action_xy≈0.0556, post_action_step_delta_xy≈3.1e-7
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

ready_mid:
  result: identical to baseline; explicit Franka ready pose is effectively the current default reset posture

elbow_open:
  decision: fail_closed
  selected: step=207 lateral=0.2479 axial=0.0583 rot=0.3714 strict_miss=27.5402
  final: lateral=0.2480 axial=0.0586 rot=0.4168
  best_lateral: 0.1998@0
  ready_counts: xy=0 z=7 rot=0 contact=349 success_step=null
  tracking tail: target_to_post_action_xy≈0.2480, post_action_step_delta_xy≈2.1e-4
  joint-limit tail: limiting_joint_counts={panda_joint4: 16, panda_joint7: 34}

yaw_pos:
  decision: fail_closed
  selected/final: step=349 lateral=0.0818 axial=0.0134 rot=1.1978 strict_miss=17.8626
  best_lateral: 0.0818@349
  ready_counts: xy=0 z=331 rot=0 contact=350 success_step=null
  tracking tail: target_to_post_action_xy≈0.0819, post_action_step_delta_xy≈1.0e-6
  joint-limit tail: limiting_joint_counts={panda_joint4: 50}

yaw_neg:
  decision: fail_closed
  selected: step=20 lateral=0.3034 axial=0.5843 rot=0.8790 strict_miss=90.7569
  final: lateral=0.3091 axial=0.6677 rot=1.4626
  best_lateral: 0.2212@3
  ready_counts: xy=0 z=0 rot=0 contact=349 success_step=null
  tracking tail: target_to_post_action_xy≈0.3094, post_action_step_delta_xy≈3.2e-4
  joint-limit tail: limiting_joint_counts={panda_joint6: 6, panda_joint7: 44}
```

Interpretation: coarse full-arm reset posture does not solve the native Abs IK fixed point. `ready_mid` confirms the default reset posture; `elbow_open` and `yaw_neg` move into worse branches; `yaw_pos` avoids negative joint-limit margin but still worsens true socket XY. The reset/posture-only sweep is closed. The next useful implementation should explicitly change controller behavior, for example adding joint-limit/nullspace behavior or replacing the native Abs IK action formulation.

Local controller follow-up implemented on 2026-05-26:

```text
scripts/scripted_agent.py
  --joint-limit-nullspace-gain
  --joint-limit-nullspace-activation-margin
  --joint-limit-nullspace-step
  --joint-limit-nullspace-damping

scripts/run_launchable_phase2_jointpos_nullspace_probe.sh
scripts/run_launchable_jointpos_nullspace_matrix.sh
scripts/summarize_absik_handoff_probe.py
scripts/analyze_absik_probe_trace.py
```

This is a non-native JointPos action-surface diagnostic. The standalone joint-IK path can now add a joint-limit centering delta, project it through the IK Jacobian nullspace, clamp it per step, and then apply the existing joint target limit guards. The default scripted behavior is unchanged because the nullspace gain defaults to `0.0`; the Launchable JointPos nullspace probe enables it explicitly. Summaries and trace analysis now report the nullspace parameters plus `max_joint_limit_nullspace_delta_norm`.

AWS validation result:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
instance: rca-jointpos-nullspace-vm / t28in7wiu
bundle: artifacts/launchable/robot-contact-assembly-launchable-jointpos-nullspace-2026-05-26.tar.gz
artifact: artifacts/launchable_logs/rca-jointpos-nullspace-probe-results-t28in7wiu.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-t28in7wiu.txt
smoke: passed
probe run: 2026-05-26T05-30-35Z_jointpos-nullspace-probe
result: failed closed
steps_requested: 900
selected_handoff_step: 10
selected_handoff: lateral=0.00898 axial=0.6344 rot=0.9471 contact=6.0025
strict_miss_score: 67.0077
final: lateral=0.0254 axial=0.8910 rot=1.3058 success_step=null
best_lateral: 0.00793 @ step 14
xy_ready_step_count: 0
z_ready_step_count: 0
rot_ready_step_count: 0
phase_counts: reach=5 align=895
min_arm_joint_limit_margin: 0.3569 at panda_joint4 step 374
max_joint_limit_nullspace_delta_norm: 0.0
tail_limiting_joint_counts: panda_joint4=50
cleanup: delete requested by name and id; final CLI check returned {"workspaces": null}
```

Interpretation: the non-native JointPos nullspace probe is also closed in its current form. The nullspace term never activated because all joints stayed outside the configured activation margin, so a gain-only sweep using the current matrix would be uninformative. More importantly, this action surface regressed depth badly (`axial` stayed around `0.63-0.89m`) and remained stuck in `align`; it did not reproduce the native Abs IK `5.6cm` XY fixed point in a useful way. The next local-first change should alter phase/target/action semantics, for example approach height, alignment/descent ordering, command frame/body offset, or a genuinely different controller surface. Do not run `scripts/run_launchable_jointpos_nullspace_matrix.sh` unchanged as the next paid job.

Local phase/target follow-up implemented after reviewing the failed trace:

```text
scripts/scripted_agent.py
  --rotate-descent-mode hold|approach

scripts/run_launchable_phase2_jointpos_rotate_descend_probe.sh
```

The failed JointPos trace showed that after `xy_state` latched, `rotate_before_descend` kept the position target at the high XY-aligned pose (`command_z≈0.824m`) while waiting for orientation readiness. The socket target was `z=0.190m` and the approach target was `z=0.240m`; because orientation never became ready, descent never started and the action-frame Z drifted upward to `1.08m`. The new `approach` mode keeps the default behavior unchanged for existing repros, but the new wrapper runs a diagnostic that rotates while commanding the approach-height pose, with XY retention enabled and joint-limit nullspace disabled (`gain=0`) to isolate the phase/target change.

AWS validation result:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
instance: rca-jointpos-rotatedesc-vm / r2dvf19yi
bundle: artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
smoke: passed

probe run: 2026-05-26T11-03-11Z_jointpos-rotate-descend-probe
mode: rotate_descent_mode=approach, rotate/descent XY retention enabled, nullspace gain=0
result: failed closed
steps_requested: 900
selected_handoff_step: 10
selected_handoff_phase: rotate-descend
selected_handoff: lateral=0.00889 axial=0.6345 rot=0.9463 contact=5.9769
strict_miss_score: 66.9987
final: lateral=0.1680 axial=0.8438 rot=1.4707 success_step=null
phase_counts: reach=5 rotate-descend=18 rotate-xy-recover=877
min_arm_joint_limit_margin: 0.0163 at panda_joint7 step 590

probe run: 2026-05-26T11-04-30Z_jointpos-rotate-descend-open-probe
mode: rotate_descent_mode=approach, XY retention disabled, nullspace gain=0
result: failed closed
steps_requested: 500
selected_handoff_step: 11
selected_handoff_phase: rotate-descend
selected_handoff: lateral=0.00814 axial=0.6343 rot=0.9517
strict_miss_score: 66.9568
final: lateral=0.1328 axial=0.7083 rot=1.5511 success_step=null
phase_counts: reach=5 rotate-descend=495
tail limiting joint: panda_joint6

remote artifacts packaged but not pulled:
  /home/ubuntu/rca-jointpos-rotate-descend-results-r2dvf19yi.tar.gz
  /home/ubuntu/rca-host-diagnostics-r2dvf19yi.txt
local artifact status:
  not present under artifacts/launchable_logs because Brev CLI auth expired before copy
cleanup/cost status:
  Brev CLI repeatedly returned logged-out EOF before copy/delete.
  Brev later reported org credits exhausted, current balance -1.94, and auto-stopped environments.
  The cleanup heartbeat was deleted after the credit-exhaustion notification.
```

Interpretation: the phase/target change was diagnostic but not a rescue. With retention enabled, the controller immediately fell into XY recovery and did not make descent progress. With retention disabled, it continued rotate-descend and improved axial relative to the retained run, but XY still drifted far outside the handoff gate. Do not spend another paid run on the current JointPos nullspace or rotate-descend branch.

Local probe archive index generated on 2026-05-26:

```bash
python3 scripts/summarize_launchable_probe_archives.py \
  --output-json artifacts/analysis/launchable_probe_archive_summary_2026-05-26.json \
  --output-markdown artifacts/analysis/launchable_probe_archive_summary_2026-05-26.md
```

The index scanned 23 local tar archives, found 20 `probe_summary.json` files, and every probe was `fail_closed`; there were no parsing warnings. The best selected strict-miss score among the local archives is still a failed Abs IK target-offset case (`target_y_pos_04`, `selected_strict_miss_score=10.2475`, final lateral `0.0778m`). The best final lateral/tail command residual is still the failed JointPos nullspace probe (`final_lateral=0.0254m`, tail command-to-post-action XY `0.0139m`), but it is axially unusable (`final_axial=0.8910m`). Use the generated Markdown/JSON files for future comparisons instead of manually reopening every archive.

Local next-controller candidate implemented on 2026-05-27:

```text
scripts/scripted_agent.py
  --reachable-approach
  --reachable-approach-start-radius
  --reachable-approach-min-radius
  --reachable-approach-shrink-step
  --reachable-approach-shrink-xy-tol
  --reachable-approach-joint-margin-min

scripts/select_reachable_approach_candidates.py
scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh
```

`reachable-approach` is a local-first target-generation change. Instead of commanding the socket action-frame target immediately, it initializes a world-XY offset direction from the socket target toward the current action-frame position, starts at an outside radius, and only shrinks that radius after the offset target is reached while the previous-step arm joint-limit margin is above threshold. This is meant to avoid driving the controller directly into the known `panda_joint4`/fixed-point branch before a pre-insertion pose has been reached.

The offline candidate selector was run locally:

```bash
python3 scripts/select_reachable_approach_candidates.py \
  --output-json artifacts/analysis/reachable_approach_candidates_2026-05-27.json \
  --output-markdown artifacts/analysis/reachable_approach_candidates_2026-05-27.md
```

It found the best existing reachable-waypoint candidates in the Abs IK `target_y_pos_04` trace around steps `259-284`: lateral around `0.077m`, axial around `0.022-0.027m`, rotation around `0.49rad`, joint margin around `0.15-0.17rad`, and target-to-post-action XY residual around `0.039m`. This supports a first diagnostic radius around `0.060m` with margin-gated shrink steps rather than another direct-to-socket command. This has not been GPU-validated yet; do not run it remotely without a fresh explicit budget.

Local bundle prepared for this branch:

```text
artifacts/launchable/robot-contact-assembly-launchable-reachable-approach-2026-05-27.tar.gz
```

GPU validation completed on 2026-06-07:

```text
runtime: plain Brev AWS g6e.xlarge L40S VM with manual isaac-sim/isaac-launchable compose
instance: rca-reachable-approach-vm / 8bk6tylx0
bundle: artifacts/launchable/robot-contact-assembly-launchable-reachable-approach-2026-06-07.tar.gz
local results: artifacts/launchable_logs/rca-reachable-approach-results-8bk6tylx0.tar.gz
host diagnostics: artifacts/launchable_logs/rca-host-diagnostics-8bk6tylx0.txt
cleanup: final Brev CLI check returned {"workspaces": null}
```

Runtime notes from this run:

```text
Isaac Sim image: nvcr.io/nvidia/isaac-sim:6.0.0-dev2
Isaac Lab: 6.5.0
GPU: NVIDIA L40S, driver 580.159.04
headless startup issue: SimulationApp could segfault in libX11/XOpenDisplay
working display workaround: Xvfb :99 -screen 0 1280x720x24 -ac -extension GLX
docker exec env for smoke/probes: -u root -e DISPLAY=:99
```

`scripts/random_agent.py` was patched to use the same AppLauncher fallback pattern as `zero_agent.py` and `scripted_agent.py`, because Isaac Lab 6.5.0 no longer exposes `isaaclab_tasks.utils.add_launcher_args`. `scripts/remote_common.sh` now supports optional `RCA_REMOTE_DOCKER_EXEC_ENV` so remote smoke can inject `-u root -e DISPLAY=:99`.

Reachable-approach result summary:

```text
baseline reachable probe:
  run: 2026-06-07T20-58-38Z_jointpos-reachable-approach-probe
  joint_ik_step: 0.035
  steps: 900
  success_step: null
  final_axial: 0.4215
  best_lateral: 0.000024@345
  best_rot: 0.0300@142
  selected strict_miss_score: 40.3082
  min joint margin: 0.5267 at panda_joint2 step 899

faster joint-IK probe:
  run: 2026-06-07T21-00-11Z_jointpos-reachable-approach-jik012
  joint_ik_step: 0.12
  steps: 900
  success_step: null
  final_axial: 0.3539
  selected strict_miss_score: 32.2077
  min joint margin: 0.3996 at panda_joint2 step 859

more aggressive joint-IK probe:
  run: 2026-06-07T21-01-36Z_jointpos-reachable-approach-jik030
  joint_ik_step: 0.30
  steps: 900
  success_step: null
  final_axial: 0.2733
  best_rot: 0.0033@714
  selected strict_miss_score: 24.3841
  min joint margin: 0.2509 at panda_joint2 step 843

long validation:
  run: 2026-06-07T21-03-02Z_jointpos-reachable-approach-jik030-steps2000
  joint_ik_step: 0.30
  steps: 2000
  success_step: null
  best_axial: 0.1073@1939
  final_axial: 0.1094
  selected strict_miss_score: 6.9591
  selected handoff: lateral=0.0012 axial=0.1076 rot=0.2103 contact=0.1056
  min joint margin: 0.0173 at panda_joint4 step 1490
```

Interpretation: `reachable-approach` solved the initial XY reach problem and showed that increasing `joint_ik_step` improves axial progress, but it still did not produce a valid strict handoff. The 2000-step run got closest on axial but still missed the `z<0.045`, `rot<0.18`, and `contact>=0.5` gates. It also drove `panda_joint4` close to its lower limit (`margin=0.0173`), so simply running longer or increasing step size further is not the next useful action.

Next local-first direction after this run: change posture/target generation so descent does not consume the remaining `panda_joint4` margin, or add an explicit posture/nullspace term that activates before joint 4 reaches the lower limit. Do not rerun `reachable-approach` unchanged on paid compute.

Implemented immediately after that result:

```text
scripts/scripted_agent.py
  --insert-joint-limit-margin
  --joint-limit-guard-gain
  --joint-limit-guard-activation-margin
  --joint-limit-guard-step

scripts/run_launchable_phase2_jointpos_reachable_guard_probe.sh
scripts/run_brev_reachable_guard_probe.sh
```

The new guard path keeps default scripted behavior unchanged, but lets a focused probe preserve early reachable-approach freedom while applying a larger joint-limit margin only during insertion/polish/settle/contact-retention. It also adds a late unprojected joint-limit guard delta and records `max_joint_limit_guard_delta_norm` in summaries/traces. This directly targeted the 2026-06-07 failure mode: reachable radius reached zero safely by step 98, but late insert consumed `panda_joint4` margin down to `0.0173rad`.

Local bundle prepared after this change:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T21-45-33Z.tar.gz
```

The paid wrapper defaults to AWS/L40S, starts a target-specific 90-minute watchdog, syncs the working tree, starts the Isaac Sim 6.0.0-dev2 task container with the `Xvfb :99 ... -extension GLX` workaround, runs compact smoke, runs the guard probe, copies results/diagnostics, then deletes and polls Brev for cleanup.

First paid wrapper attempt:

```text
timestamp: 2026-06-07T21:32Z
instance: rca-reachable-guard-vm / d9nx8jtfj
provider/type: AWS g6e.xlarge L40S, 100GB disk
result: infrastructure failure before smoke/probe
failure: docker run implicitly pulling nvcr.io/nvidia/isaac-sim:6.0.0-dev2 returned "grpc: the client connection is closing"
cleanup: script deleted the instance; final Brev list returned {"workspaces": null}
local audit files:
  artifacts/launchable_logs/brev_pre_rca-reachable-guard-vm_2026-06-07T21-32-31Z.json
  artifacts/launchable_logs/latest_brev_instances_after_rca-reachable-guard-vm.json
```

`scripts/install_remote_isaaclab_runtime.sh` was then hardened to run `sudo docker pull "${ISAAC_SIM_IMAGE}"` with three attempts before `docker run`, so a transient image-pull failure does not abort the paid run immediately.

Second paid wrapper attempt:

```text
timestamp: 2026-06-07T21:46Z
instance: rca-reachable-guard-vm / avejl6fqo
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed
probe run: 2026-06-07T21-59-30Z_jointpos-reachable-jointlimit-guard-probe
result: failed closed
success_step: null
selected handoff: step=1584 lateral=0.0012 axial=0.1989 rot=0.3361 contact=0.0473
strict_miss_score: 17.4066
final: lateral=0.0013 axial=0.1958 rot=0.3693
best_lateral=0.00008@741
best_axial=0.1958@1599
best_rot=0.0033@714
min_arm_joint_limit_margin=0.1542 at panda_joint4 step 1492
max_joint_limit_nullspace_delta_norm=0.0127@1493
max_joint_limit_guard_delta_norm=0.0154@1493
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-vm-2026-06-07T21-46-17Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-vm-2026-06-07T21-46-17Z.txt
cleanup: delete completed; final Brev list returned {"workspaces": null}
```

Interpretation: the guard worked on its direct safety target, increasing the limiting `panda_joint4` margin from `0.0173` to `0.1542`. It was too conservative for insertion: axial progress stalled around `0.196m`, contact dropped to near zero, and the strict miss was worse than the unguarded long reachable run. Do not rerun this strong guard unchanged.

The focused tuned guard variant was run after the strong-guard result:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh
```

It kept the same reachable approach, relaxed insertion guard defaults (`insert_joint_limit_margin=0.060`, guard gain/step `0.060/0.040`, activation `0.110`), and extended to 2000 steps. The paid wrapper command was:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-tuned-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

```text
timestamp: 2026-06-07T22:18Z
instance: rca-reachable-guard-tuned-vm / hm27ajjsk
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed
probe run: 2026-06-07T22-31-05Z_jointpos-reachable-jointlimit-guard-tuned-probe
result: failed closed
success_step: null
selected handoff: step=1921 lateral=0.0012 axial=0.1463 rot=0.2862 contact=0.0652
strict_miss_score: 11.6256
final: lateral=0.0029 axial=0.1449 rot=0.4466
best_lateral=0.00008@741
best_axial=0.1449@1999
best_rot=0.0033@714
min_arm_joint_limit_margin=0.0738 at panda_joint4 step 1503
max_joint_limit_nullspace_delta_norm=0.0101@1820
max_joint_limit_guard_delta_norm=0.0188@1504
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-tuned-vm-2026-06-07T22-18-02Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-tuned-vm-2026-06-07T22-18-02Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final Brev list returned {"workspaces": null}
```

Watchdog note: the target-specific watchdog wrote a stale `manual_delete_required.txt` after one transient Brev CLI query failure at 2026-06-07T22:28Z. The main wrapper continued, copied artifacts, deleted the instance, and confirmed `{"workspaces": null}`. The watchdog script has been hardened so transient query failures are tolerated before a manual-cleanup alert.

Interpretation: the tuned guard moved farther than the strong guard (`best_axial` improved from `0.1958m` to `0.1449m`) while keeping the limiting `panda_joint4` margin safer than the unguarded reachable run (`0.0738rad` vs `0.0173rad`). It still failed every strict-ready/z-ready gate: final axial was still far above `0.045m`, selected contact was only `0.065`, and rotation drifted back up during late insertion. Do not rerun the tuned guard unchanged. The next useful work is a local-first controller or phase change that gives insertion more depth without consuming the elbow branch, for example changing the pre-insertion posture/approach target, decoupling descent from rotation, or adding a more explicit posture objective before the final insertion phase.

Next local-first implementation prepared on 2026-06-08:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_rotgated_probe.sh
```

This is not an unchanged tuned rerun. It reuses the tuned guard parameters but enables `--insert-rotation-gated-descent`, disables `--hold-orientation-during-insert`, and defaults `insert_descent_rot_tol=0.35`. Offline replay of the tuned trace showed a 0.20rad gate would freeze almost the entire insertion segment, while 0.35rad targets only the high-rotation windows. The intent is to pause Z descent when rotation is clearly drifting, keep XY/orientation control active at the current depth, and then resume insertion after the controller repairs orientation.

Paid validation command, only after confirming `brev ls instances --json --all` is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-rotgated-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_rotgated_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

First paid rotgated attempt on 2026-06-07/08:

```text
instance: rca-reachable-guard-rotgated-vm / w57uxy94u
provider/type: AWS g6e.xlarge L40S, 100GB disk
runtime: created, nvidia-smi passed, repo synced, Isaac Sim 6.0.0-dev2 container started, Xvfb/runtime check passed
result: infrastructure/smoke failure before the rotgated probe started
failure point: compact smoke stayed in zero_agent.py --steps 3 for about 9 minutes with no artifact progress; smoke watchdog was not being passed to zero/random smoke
artifacts: no probe result tarball or host diagnostics were produced before cleanup
cleanup: wrapper deleted the instance; final wrapper output and independent CLI check both returned {"workspaces": null}; watchdog logged "target disappeared; cleanup confirmed"
```

After this failed attempt, `scripts/run_remote_smoke_test.sh` was hardened so zero, random, and scripted smoke commands all receive a default `RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300` plus an outer `timeout` (`watchdog + 120s`). `scripts/random_agent.py` now also supports `--watchdog_seconds`, matching `zero_agent.py`. The paid wrapper no longer passes a misleading scripted-only smoke watchdog argument.

Second paid rotgated attempt on 2026-06-08:

```text
timestamp: 2026-06-07T23:35Z
instance: rca-reachable-guard-rotgated2-vm / 6nuie4sss
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed after smoke watchdog hardening
probe run: 2026-06-07T23-47-57Z_jointpos-reachable-jointlimit-guard-rotgated-probe
result: failed closed
success_step: null
selected handoff: step=2144 phase=insert-rot-recover lateral=0.0010 axial=0.1711 rot=0.3537 contact=0.0934
strict_miss_score: 14.7524
strict_miss_components: axial=12.6084 contact=0.4066 lateral=0 rot=1.7374
final: lateral=0.0007 axial=0.1708 rot=0.5107
best_lateral=0.0004@211
best_axial=0.1708@2199
best_rot=0.1714@98
min_arm_joint_limit_margin=0.3923 at panda_joint4 step 2095
insert_rotation_gate_step_count=1034 first_step=177 last_step=2199 max_rot=0.5204
max_joint_limit_guard_delta_norm=0.0
max_joint_limit_nullspace_delta_norm=0.0
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotgated2-vm-2026-06-07T23-35-59Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-rotgated2-vm-2026-06-07T23-35-59Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final wrapper output and repeated independent Brev CLI checks returned {"workspaces": null}
```

Run note: the Docker pull failed once with `grpc: the client connection is closing`, retried successfully, and the instance completed the probe. The wrapper printed one stale manual-cleanup warning during a delete/list race, but immediately afterwards returned `{"workspaces": null}`; repeated independent `brev ls instances --json --all` checks also returned `{"workspaces": null}`.

Interpretation: rotation-gated insertion is now a real, smoke-passing Launchable result, and it should be considered closed in this form. Compared with the tuned guard, it preserved much more arm joint-limit margin (`0.3923rad` vs `0.0738rad`) and did not need joint-limit guard/nullspace corrections, but it regressed insertion depth (`best_axial/final_axial=0.1708m` vs `0.1449m`) and strict miss (`14.7524` vs `11.6256`). The rotation gate was active for 1034 of 2200 steps, from step 177 through the end, so it protected XY and posture by choking descent. Do not rerun the rotation-gated probe unchanged. The next useful work is local-first: replace the hard Z hold with a softer insertion policy, such as bounded descent during rotation recovery, a minimum descent budget per rotation window, or an explicit staged depth schedule that can continue making axial progress while orientation is being repaired.

Next local-first implementation prepared on 2026-06-08:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh
```

This is a narrow follow-up to the hard rotation-gated result, not an unchanged rerun. `scripts/scripted_agent.py` now supports `--insert-rotation-gate-descent-scale` and `--insert-rotation-gate-min-descent-step`; the default hard-gate behavior remains `scale=0.0`, while the new wrapper uses `scale=0.25`, `min_descent_step=0.002`, `insert_descent_rot_tol=0.35`, `hold_orientation_during_insert=0`, and `steps=2400`. The intent is to keep XY/orientation repair active during high-rotation insertion windows while still allowing bounded axial progress.

Paid validation command, only after confirming `brev ls instances --json --all` is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-softgated-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh \
./scripts/run_brev_reachable_guard_probe.sh
```

Paid softgated validation on 2026-06-08:

```text
timestamp: 2026-06-08T00:16Z
instance: rca-reachable-guard-softgated-vm / hqgphjyta
provider/type: AWS g6e.xlarge L40S, 100GB disk
smoke/runtime: passed
probe run: 2026-06-08T00-30-27Z_jointpos-reachable-jointlimit-guard-softgated-probe
result: failed closed
success_step: null
selected handoff: step=1443 phase=insert lateral=0.00323 axial=0.04343 rot=0.28758 contact=0.69435
strict_miss_score: 1.07584
strict_miss_components: axial=0 contact=0 lateral=0 rot=1.07584
final: lateral=0.01204 axial=0.04058 rot=0.33186
best_lateral=0.00037@1236
best_axial=0.03333@2322
best_rot=0.17140@98
min_arm_joint_limit_margin=0.10353 at panda_joint4 step 2328
insert_rotation_gate_step_count=1228 first_step=177 last_step=2321 max_rot=0.5180
insert_rotation_gate_descent_scale=0.25 min_descent_step=0.002 max_allowed_descent=0.0050
ready_counts: xy=1219 z=904 rot=17 strict=0 contact=949
tail means: lateral=0.01053 axial=0.04124 rot=0.30073 contact=1.48027 command_to_post_action_xy=0.00409 post_action_step_delta_xy=0.000104
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-softgated-vm-2026-06-08T00-16-12Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-softgated-vm-2026-06-08T00-16-12Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final wrapper output and independent Brev CLI check returned {"workspaces": null}
```

Interpretation at the time: soft-gated descent was the closest Launchable result and changed the blocker materially. It solved the hard-gate depth stall: the selected handoff was already inside the XY, Z, and contact gates, and failed only rotation (`rot=0.2876` vs `0.18`, strict miss `1.0758` vs guard `1.0`). It also reached much deeper than tuned/rotgated (`best_axial=0.0333m`, final `0.0406m`) while retaining a usable joint-limit margin (`0.1035rad` at `panda_joint4`). Do not rerun the same softgated probe unchanged. This recommendation was superseded by the depth-aware rotation polish validation below, which preserved XY/Z but still failed rotation.

Latest local bundle after soft-gated insertion wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-softgated-2026-06-08.tar.gz
```

Depth-aware rotation polish implementation prepared on 2026-06-08:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_rotpolish_probe.sh
```

This is the intended next non-duplicate paid validation. It keeps the soft-gated insertion settings and adds a default-off `--depth-rotation-polish` state to `scripts/scripted_agent.py`. The state latches only after insertion is active and XY/Z/contact are ready (`xy<0.006`, `z<0.050`, `contact>=0.5` in the wrapper), then holds socket XY, applies a `0.001m` Z preload, and targets the socket orientation with a `0.035rad` polish rotation step. It exits if XY exceeds `0.012m` or axial exceeds `0.060m`, letting normal insertion recover instead of continuing to rotate while drifting away.

Validation command, only after confirming Brev is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-rotpolish-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_rotpolish_probe.sh \
RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES=75 \
RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300 \
RCA_REMOTE_SMOKE_TIMEOUT_SECONDS=420 \
./scripts/run_brev_reachable_guard_probe.sh
```

Expected improvement criteria: the run should enter `depth-rot-polish`, keep selected lateral under `0.005m` and axial under `0.045m`, and reduce selected/final rotation below `0.18rad`. If it fails closed, compare `depth_rotation_polish_step_count`, `depth_rotation_polish_max_lateral`, `depth_rotation_polish_min_axial`, and tail phase counts before changing thresholds. Do not rerun softgated unchanged.

Paid depth-aware rotation polish validation on 2026-06-08:

```text
timestamp: 2026-06-08T04:25Z
instance: rca-reachable-guard-rotpolish-vm / xvkzygbsw
provider: AWS g6e.xlarge / L40S
probe run: 2026-06-08T04-37-01Z_jointpos-reachable-jointlimit-guard-rotpolish-probe
status: fail_closed
cleanup: copied result archive and host diagnostics, deleted instance, final Brev check returned {"workspaces": null}
```

Key result:

```text
selected handoff: step=1386 phase=insert lateral=0.002079 axial=0.044687 rot=0.326000 contact=1.451769 strict_miss=1.460000
final: lateral=0.002581 axial=0.045102 rot=0.352941 success_rate=0.0
depth-rot-polish: active_steps=615 first_step=1311 last_step=2599 max_lateral=0.004365 min_axial=0.044687 max_rot=0.526121 rot_step=0.035
tail window: lateral=0.002437 axial=0.052236 rot=0.283574 contact=0.208385 phase_counts={insert:44, depth-rot-polish:6}
limiter: panda_joint4 min_margin=0.100994 at step 2212
diagnosis: tail post-action movement makes little progress along the requested XY command
```

Artifacts:

```text
artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.tar.gz
artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-rotpolish-vm-2026-06-08T04-25-16Z.txt
```

Interpretation: the new state entered and kept XY tightly inside gate, so the latch/hold/preload plumbing worked. It did not solve the actual blocker: rotation during/after depth polish stayed above the `0.18rad` gate and ended worse than the prior soft-gated run (`selected rot 0.3260` vs `0.2876`, final rot `0.3529` vs `0.3319`). The failure is therefore not worth a duplicate paid rerun with the same wrapper. Next local-first change should replace the full-target orientation polish with a less oscillatory late-contact rotation repair: adaptive smaller rotation step, a contact/Z-aware orientation target, or a phase that rotates only while depth/contact remain stable instead of repeatedly cycling polish and insertion.

Adaptive late-contact rotation repair prepared after that result:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh
```

What changed locally:

```text
--depth-rotation-polish-orientation-mode stateful-waypoint
--depth-rotation-polish-exit-contact-min-force 0.30
--depth-rotation-polish-rot-step 0.012
--depth-rotation-polish-preload-step 0.0005
--depth-rotation-polish-exit-xy-tol 0.010
--depth-rotation-polish-exit-z-tol 0.055
```

The new mode seeds a persistent quaternion command at depth-polish entry and advances it toward the orientation target by a bounded step instead of recomputing a fresh full target every frame. It also exits the phase when contact falls below `0.30`, so late rotation only continues while contact/depth remain stable. This is the next non-duplicate paid validation candidate, but it still needs only a short AWS run after confirming Brev is empty; do not run it together with any sweep.

Validation command, only after confirming Brev is empty:

```bash
RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_GUARD_ENV_NAME=rca-reachable-guard-adaptive-rotpolish-vm \
RCA_BREV_GUARD_PROBE_SCRIPT=scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh \
RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES=80 \
RCA_REMOTE_SMOKE_WATCHDOG_SECONDS=300 \
RCA_REMOTE_SMOKE_TIMEOUT_SECONDS=420 \
./scripts/run_brev_reachable_guard_probe.sh
```

Expected improvement criteria: `depth_rotation_polish_orientation_mode=stateful-waypoint`, nonzero `depth_rotation_polish_step_count`, selected lateral under `0.005m`, selected axial under `0.045m`, and selected/final rotation materially below the old rotpolish run (`0.326/0.353`) with a target of `<0.18rad`. If it fails closed, compare contact-exit timing and whether `depth_rotation_polish_command_valid` stayed continuous before changing the step size.

Paid adaptive rotpolish validation on 2026-06-09:

```text
timestamp: 2026-06-09T05:17Z
instance: rca-reachable-guard-adaptive-rotpolish-vm / evzxs5mnd
provider: AWS g6e.xlarge / L40S
probe run: 2026-06-09T05-30-44Z_jointpos-reachable-jointlimit-guard-adaptive-rotpolish-probe
status: fail_closed
cleanup: copied result archive and host diagnostics, deleted instance, final Brev check returned {"workspaces": null}
```

Key result:

```text
selected handoff: step=1415 phase=insert lateral=0.002064 axial=0.044518 rot=0.320708 contact=1.847413 strict_miss=1.407076
final: lateral=0.002561 axial=0.045312 rot=0.366785 success_rate=0.0
depth-rot-polish: active_steps=863 first_step=1311 last_step=2999 max_lateral=0.004139 min_axial=0.044509 max_rot=0.506800 rot_step=0.012 orientation_mode=stateful-waypoint exit_contact_min_force=0.30
insert rotation gate: active_steps=1101 first_step=177 last_step=2997 max_rot=0.518001 descent_scale=0.25
ready counts: strict=0 xy=2865 z=150 contact=919 rot=17
tail window: lateral=0.002107 axial=0.045669 rot=0.337341 contact=0.468937 phase_counts={depth-rot-polish:30, insert:16, insert-rot-recover:4}
limiter: panda_joint4 min_margin=0.104442 at step 2921
diagnosis: tail post-action movement makes little progress along the requested XY command
```

Artifacts:

```text
artifacts/launchable_logs/rca-reachable-guard-results-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.tar.gz
artifacts/launchable_logs/rca-host-diagnostics-rca-reachable-guard-adaptive-rotpolish-vm-2026-06-09T05-17-35Z.txt
```

Interpretation: adaptive stateful waypoint polish was active and protected XY/depth, but it still did not repair rotation. Compared with the 2026-06-08 target-orientation rotpolish run, selected rotation improved only slightly (`0.3207` vs `0.3260`), final rotation worsened (`0.3668` vs `0.3529`), and no strict-ready step was produced. Do not rerun adaptive rotpolish unchanged or as a threshold sweep. The next useful step is local-first trace analysis around the `rot_ready` / `depth-rot-polish` windows and then a controller change to the late-contact orientation target or branch selection; only after that should another short paid validation be considered.

Local trace analysis helper added after the run:

```text
scripts/analyze_rotation_polish_trace.py
```

Running it on the 2026-06-08 rotpolish and 2026-06-09 adaptive rotpolish archives shows the rotation blocker is not a simple missing runtime or threshold issue:

```text
rotpolish: 2600 steps, 80 phase segments, 25 depth-rot-polish segments, mean segment len 24.6, best XY/Z/contact-ready rot 0.3260
adaptive rotpolish: 3000 steps, 983 phase segments, 472 depth-rot-polish segments, mean segment len 1.83, best XY/Z/contact-ready rot 0.3207
rot-ready range for both: only steps 87-103, before contact/depth readiness
```

This supports the controller diagnosis: near the actual handoff depth, the current `axis-align-current`/stateful-polish target keeps XY and depth usable but does not drive the trace toward the strict rotation metric. The next implementation should change the late-contact orientation target/branch behavior, not just lower polish step size or rerun with longer time.

Near-depth rotation-gate candidate prepared after that analysis:

```text
scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
```

This adds default-off near-depth rotation-gate overrides to `scripts/scripted_agent.py` and exposes them through `scripts/run_launchable_phase2_jointpos_nullspace_probe.sh`:

```text
--insert-rotation-gate-near-depth-z-tol
--insert-rotation-gate-near-depth-rot-tol
--insert-rotation-gate-near-depth-descent-scale
--insert-rotation-gate-near-depth-min-descent-step
```

The wrapper inherits the soft-gated run but tightens only once `axial < 0.065m`: `rot_tol=0.22`, `descent_scale=0.10`, `min_descent_step=0.0005`. The intent was to avoid the observed redescend at `rot≈0.24` before the strict `0.18rad` gate is reached, while keeping early insertion permissive.

Paid validation on 2026-06-09:

```text
timestamp: 2026-06-09T06:31Z
instance: rca-neardepth-rotgate-vm / 5x0dmseey
provider/type: AWS g6e.xlarge L40S
smoke/runtime: passed
probe run: 2026-06-09T06-45-39Z_jointpos-reachable-jointlimit-guard-neardepth-rotgate-probe
result: failed closed
success_step: null
selected handoff: step=1763 phase=align lateral=0.001235 axial=0.049536 rot=0.350150 contact=0.500092
strict_miss_score: 2.155097
final: lateral=0.002205 axial=0.060102 rot=0.313013
best_lateral=0.000371@1236
best_axial=0.047266@1760
best_rot=0.171399@98
insert_rotation_gate_step_count=2101
min_arm_joint_limit_margin=0.096164 at panda_joint4 step 1766
tail means: lateral=0.002955 axial=0.061385 rot=0.262909 contact=0.070176
diagnosis: tail post-action movement makes little progress along the requested XY command
artifacts:
  artifacts/launchable_logs/rca-reachable-guard-results-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.tar.gz
  artifacts/launchable_logs/rca-host-diagnostics-rca-neardepth-rotgate-vm-2026-06-09T06-31-56Z.txt
cleanup: results and diagnostics copied; delete issued by wrapper; final wrapper output and independent Brev CLI check returned {"workspaces": null}
```

Interpretation: tightening the rotation gate near depth did not close the strict handoff gap. The run again reached excellent XY and briefly achieved low rotation early, but at useful depth the controller could not satisfy depth/contact/rotation together. It selected a contact-qualified but too-shallow/high-rotation state (`axial=0.0495`, `rot=0.3502`) and the tail lost contact while making little XY progress. This closes the current scripted-controller branch; do not rerun near-depth rotgate unchanged or as a threshold sweep.

Latest local bundle after near-depth rotgate wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-neardepth-rotgate-2026-06-09.tar.gz
```

Latest local bundle after documenting the adaptive rotpolish result:

```text
artifacts/launchable/robot-contact-assembly-launchable-adaptive-rotpolish-result-2026-06-09.tar.gz
```

Latest local bundle after adaptive rotpolish wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-adaptive-rotpolish-2026-06-08.tar.gz
```

Latest local bundle after documenting the paid rotpolish result:

```text
artifacts/launchable/robot-contact-assembly-launchable-rotpolish-result-2026-06-08.tar.gz
```

Latest local bundle after depth-aware rotation polish wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-rotpolish-2026-06-08.tar.gz
```

Previous local bundle after rotation-gated probe wiring and smoke watchdog hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T23-35-06Z.tar.gz
```

Previous local bundle after rotation-gated probe wiring only:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-08T00-20-00Z.tar.gz
```

Previous local bundle after tuned guard result documentation and watchdog hardening:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T22-50-00Z.tar.gz
```

Previous local bundle after tuned guard wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-06-07T22-17-23Z.tar.gz
```

Bundle used for the target-command run:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T15-05-37Z.tar.gz
```

Latest bundle after strengthening the no-wall-collision diagnostic:

```text
artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz
```

Latest bundle after target-offset matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-target-offset-matrix-2026-05-25.tar.gz
```

Latest bundle after IK-method matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-ik-method-matrix-2026-05-25.tar.gz
```

Latest bundle after full-arm posture matrix wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-full-arm-posture-matrix-2026-05-25.tar.gz
```

Latest bundle after JointPos nullspace wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-jointpos-nullspace-2026-05-26.tar.gz
```

Latest bundle after JointPos rotate-descend wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
```

## 2026-06-11 Contact Physics Validity Audit

A geometric audit of all recorded traces found that the Phase 2 task has no
real peg/socket contact physics, which invalidates the physical premise of
the entire scripted-controller and BC campaign.

```text
script: scripts/analyze_contact_physics_validity.py
report: artifacts/analysis/contact_physics_validity_2026-06-11.md
        artifacts/analysis/contact_physics_validity_2026-06-11.json
traces analyzed: 78
traces with free-space contact force: 72
traces with silent wall penetration: 15
verdicts: no_wall_physics=15, contact_signal_not_socket=57, consistent=3 (tiny smokes)
```

Root cause: both the peg and the socket guide walls are spawned with
`kinematic_enabled=True`, and `sync_peg_to_hand` teleports the peg to the
hand pose every step. PhysX does not resolve kinematic-kinematic pairs, so
the guide walls have never exerted any force on the peg. The
`contact_force_magnitude` signal is not socket reaction either; it is
consistent with gripper-finger interaction with the kinematically synced
peg.

Decisive evidence:

```text
softgated trace step 2322:
  peg axis passes 10mm through both left and right walls; contact reads 0.00
softgated trace step 98:
  peg in free space at z=0.745, >0.3m from any wall; contact reads 1.00
softgated trace steps 1399-1403:
  inserting end 52-58mm deep inside the channel at tilt 0.21rad,
  4x the geometric two-point maximum (0.05rad) for that depth
best near-miss trace 2026-05-17T23-32-18Z:
  816 steps with contact>=0.3 while >=2mm clear of every wall (max 3.35)
  298 steps with wall penetration >=2mm while contact < 0.1
  penetration/contact correlation: -0.113
note: the logged physical_tip_pos_w is the gripped upper end of the peg;
  the inserting end is one peg length farther along the peg axis.
  Trace quaternions are XYZW.
```

Implications:

1. Every paid probe optimized against a non-physical gate: `contact>=0.5`
   measured the gripper, not insertion, and the rotation plateau happened
   in a world where walls cannot block anything, so it is a
   controller/kinematics artifact, not contact jamming.
2. The earlier no-wall-collision diagnostic result (parking the walls
   changed nothing) is fully explained: the walls were never interacting.
3. The "shallow true-contact success", the strict near-miss labels, the
   near-contact BC datasets, and the final-contact reset candidates are all
   labeled by a gripper-force artifact and do not represent physical
   insertion contact.
4. Do not spend any further paid compute on any controller, BC, or RL run
   until the environment is fixed and a smoke test demonstrates real
   peg-wall collision response.

Required environment fix before any new run:

```text
- give the task a dynamic peg with real collision response: either a
  dynamic rigid body rigidly attached to the hand (fixed joint) or an
  extra link on the robot articulation
- keep the socket guide walls as colliders against that dynamic peg so
  PhysX generates real contact constraints
- remove sync_peg_to_hand teleportation during contact phases; a
  teleported kinematic body cannot experience reaction forces
- route the success-gate contact signal through a peg-vs-wall filtered
  contact pair, not the peg net-force sensor
- add a contact-physics smoke: command the peg straight into a wall and
  assert nonzero wall reaction and blocked motion before any paid run
```

The environment fix was implemented locally on 2026-06-13:

```text
source/.../peg_in_hole/assets.py (new)
  AttachedPegCylinderCfg / spawn_attached_peg_cylinder: spawns the peg as a
  DYNAMIC rigid body and authors a USD PhysicsFixedJoint from panda_hand to
  the peg inside the env_0 template (before sim start; cloner replicates it
  per env). Joint local pose = PEG_CENTER_BODY_OFFSET_POS/ROT, i.e. the same
  hand-to-peg transform the old kinematic sync enforced (XYZW constants are
  converted explicitly to USD scalar-first quaternions). The initial
  implementation set excludeFromArticulation so the peg stayed a standalone
  RigidObject view; after the 2026-06-20 smoke showed that maximal-coordinate
  model did not constrain the peg, the default changed to
  exclude_from_articulation=False so the peg participates in the Franka
  articulation. The smoke script keeps --exclude_peg_from_articulation only as
  a legacy negative-control/diagnostic switch.
  Gripper hand/finger collisions against the peg are disabled via
  UsdPhysics.FilteredPairsAPI (they interpenetrate by construction and only
  pollute forces/dynamics).

source/.../peg_in_hole/peg_in_hole_env_cfg.py
  peg: kinematic_enabled=False, max_depenetration_velocity=5.0, solver
  iterations 16/1, contact_offset=0.001 / rest_offset=0.0 (clearance is
  1.5mm per side, the offset must stay below it), friction 0.3, attached
  spawner wired with the calibrated joint transform.
  walls: same contact offsets/material, still kinematic colliders (valid
  against a dynamic peg).
  events: sync_peg_each_step REMOVED (a per-step teleport would fight the
  joint and erase contact impulses); sync_peg_on_reset kept as best-effort
  placement so the joint starts near zero error after arm reset.

source/.../peg_in_hole/mdp/observations.py
  peg_contact_force_magnitude / peg_contact_force_socket now read the
  wall-filtered force_matrix_w (summed over the four guide-wall pairs)
  instead of net_forces_w. scripted_agent.py and
  evaluate_contact_bc_policy.py consume these mdp functions directly, so
  every contact gate in the stack switches to the wall-only signal without
  script changes. Observation widths are unchanged.

source/.../peg_in_hole/config/franka/ik_rel_env_cfg.py
  sync_peg_each_step references removed. zero_agent's
  --disable_peg_sync_interval / --peg_sync_interval_seconds flags use
  defensive getattr and now no-op.

scripts/contact_physics_smoke.py (new)
scripts/run_launchable_contact_physics_smoke.sh (new)
  The audit-mandated gate. Runs the Abs IK play task with num_envs=2
  (catches per-env joint wiring failures after cloning), then checks
  markers: attach (peg tracks its own hand through the fixed joint),
  free-space (wall-filtered force ~0 when hovering), press-force
  (sustained reaction >0.5N pressing 20mm into a wall top), press-blocked
  (the peg end stays within 8mm of the wall-top plane instead of passing
  through), press-no-clip (geometric lower-end wall penetration stays within
  tolerance), release, joint-integrity, and the wrapper completion marker
  `[contact-smoke] completed: contact physics is real`. The smoke overrides
  episode_length_s to 60s so the phase sequence cannot be interrupted by
  the play cfg's 240-step timeout.
```

Status: implemented and lint/syntax-checked locally; NOT yet validated on an
Isaac runtime because no local GPU/Isaac is available. The first action on
the next approved GPU session must be
`./scripts/run_launchable_contact_physics_smoke.sh`, before any other
evaluation. Until that smoke passes, treat the contact physics as unproven.

Verified runtime conventions used by the fix (empirically, from the June
Launchable traces): quaternions are XYZW end-to-end in the deployed Isaac
Lab runtimes (tip = hand ⊗ (0,0,0.1034) reproduces logged positions to
<1mm under XYZW and is ~17cm off under WXYZ), and the logged
`physical_tip_pos_w` is the gripped UPPER end of the peg — the inserting
end is one peg length farther along the peg axis. An earlier automated
review claimed a systemic XYZW/WXYZ mismatch against Isaac Lab math utils;
that claim is wrong for the deployed runtimes and was refuted with the
trace check above.

## 2026-06-20 Contact Smoke Follow-up

The official AWS Isaac Launchable smoke was rerun on `isaac-launchable-06320b`
(`kj53qhjld`) with payload
`ea1f96b9ec12bb167ab76e5ab75b37c244115c47007acf5e36372d7baeaee5a1`.
The run used the short contact-smoke path only; no controller sweep, BC, or RL
job was started. The pulled log is:

```text
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_kj53qhjld.log
artifacts/launchable_logs/contact_physics_smoke_failed_kj53qhjld_2026-06-19T23-47Z.log
```

Result: still `BLOCKED`. The smoke reproduced the same semantic failure:

```text
CONTACT-SMOKE attach: FAIL
CONTACT-SMOKE press-force: FAIL
CONTACT-SMOKE press-blocked: FAIL
CONTACT-SMOKE press-no-clip: FAIL
CONTACT-SMOKE joint-integrity: FAIL
PhysicsUSD: CreateJoint - found a joint with disjointed body transforms:
  /World/envs/env_0/Peg/PegHandFixedJoint
```

Interpretation: do not spend on downstream control. The next local fix is the
spawn-time fixed-joint seed, not another controller variant. `assets.py` now
aligns the spawned peg prim to `joint_local_frame * hand_world` before
authoring `PegHandFixedJoint`, and `scripts/check_contact_physics_wiring.py`
requires this ordering. Local verification after this patch:

```bash
./scripts/run_local_quality_checks.sh
python3 scripts/check_phase2_contact_gate.py --run-local-quality  # expected BLOCKED
python3 scripts/project_status_report.py --fail-on-blocked        # expected BLOCKED
```

Current runtime payload after the spawn-time alignment patch:

```text
1f3f93c468830c9543137257039a2d000027d4da011a6f1d237e195ba1ab7227
```

The next allowed paid action, after confirming the old Launchable has fully
disappeared from `brev ls instances --json --all`, is one more contact-smoke
bundle for this payload under the watchdog/deletion plan. If that smoke still
shows the disjointed-joint warning or attach failure, stop and add a diagnostic
that logs the authored USD joint frames and runtime hand/peg poses before any
further paid run.

Follow-up smoke for payload
`1f3f93c468830c9543137257039a2d000027d4da011a6f1d237e195ba1ab7227` ran on
`isaac-launchable-096e3f` (`1ven2jhye`) and also failed. Artifacts:

```text
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_1ven2jhye.log
artifacts/launchable_logs/contact_physics_smoke_failed_1ven2jhye_2026-06-20T00-20Z.log
```

Key markers:

```text
CONTACT-SMOKE attach: FAIL (per-env hand-peg error [0.1499068, 0.2825360] m)
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL (0 N)
CONTACT-SMOKE press-blocked: FAIL
CONTACT-SMOKE press-no-clip: FAIL
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: FAIL
```

Cleanup for `1ven2jhye` is confirmed: the instance was deleted through the Brev
UI after CLI delete/stop left it stuck in `UNHEALTHY`/`DELETING`; the watchdog
ended with `target disappeared; cleanup confirmed`, and
`/Users/Shenghan/bin/brev ls instances --json --all` returned
`{"workspaces": null}`.

Interpretation update: the spawn-time joint-frame seeding patch did not
materially change the failure. The same hand/peg separation and zero wall force
remain, so the most likely fault is that the authored fixed joint is missing,
mis-targeted after cloning, or not enforced by PhysX, rather than a controller
or policy issue. `scripts/contact_physics_smoke.py` now logs runtime
diagnostics for the authored USD joint and hand/peg expected-vs-actual poses.
Do not open another paid run until either the joint implementation is locally
changed or the next single contact-smoke run is explicitly treated as the
diagnostic smoke for those new log fields.

Current runtime payload after adding diagnostics:

```text
785d9c754cc4eb94bdd6010c424cd8a50a5cd1e91b12c4ceb2c3a8e58674099f
```

Third 2026-06-20 diagnostic smoke ran on `isaac-launchable-14ab03`
(`91wizfdos`) with payload
`da587201cc5a1ad1e643b2c0980980b02d75e75295b098aa9e7f3fcedbd5e85e`.
The run again used only the short contact-smoke path. Artifacts:

```text
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_91wizfdos.log
artifacts/launchable_logs/contact_physics_smoke_failed_91wizfdos_2026-06-20T01-02Z.log
```

Key markers:

```text
CONTACT-SMOKE peg-articulation-model exclude_from_articulation=False
CONTACT-SMOKE attach: PASS after reset (per-env error about [0.0, 0.00000007] m)
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL (0 N)
CONTACT-SMOKE press-blocked: FAIL
CONTACT-SMOKE press-no-clip: FAIL
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: FAIL after free-space settle
RigidBodyView contains non-root articulation links whose transforms cannot be set directly
RigidBodyView contains non-root articulation links whose velocities cannot be set directly
```

Cleanup for `91wizfdos` is confirmed: the watchdog ended with
`target disappeared; cleanup confirmed`, the Brev UI returned to the empty
Environments state, and `/Users/Shenghan/bin/brev ls instances --json --all`
returned `{"workspaces": null}`.

Interpretation update: `exclude_from_articulation=False` fixed the immediate
reset-time attachment, but the peg was still registered as an Isaac Lab
`RigidObjectCfg`. Once the peg participates in the Franka articulation, that
separate RigidObject view is invalid because it tries to write transforms and
velocities for a non-root articulation link. This explains the post-settle
separation and zero wall reaction. The current local fix therefore removes the
active peg `RigidObjectCfg` and `sync_peg_on_reset` path:

```text
peg_in_hole_env_cfg.py:
  peg is now AssetBaseCfg with AttachedPegCylinderCfg, not RigidObjectCfg.
  sync_peg_on_reset is no longer an active EventTerm.

observations.py:
  peg root pose is derived from the Franka hand pose and PEG_CENTER_BODY_OFFSET,
  instead of env.scene["peg"].data.

contact_physics_smoke.py:
  peg pose diagnostics use the robot articulation if available, otherwise the
  derived hand offset; the log prints peg_pose_source.

check_contact_physics_wiring.py:
  fails if the active env registers peg as RigidObjectCfg or reintroduces
  sync_peg_on_reset before the contact gate passes.
```

Local verification after this patch:

```bash
./scripts/run_local_quality_checks.sh  # passed
python3 scripts/project_status_report.py --fail-on-blocked  # expected BLOCKED
```

Current runtime payload after removing the invalid peg RigidObject view:

```text
b2f9fd5642fad1b615f5ff1839b37f294efd6bf213c43e243aa8cb8695d212b5
```

The next allowed paid action is one single contact-smoke run for payload
`b2f9fd5642fad1b615f5ff1839b37f294efd6bf213c43e243aa8cb8695d212b5`, after
`./scripts/run_local_quality_checks.sh`, paid preflight, explicit budget/TTL,
watchdog start, exact bundle upload, log pullback, and immediate deletion.
Do not run controller sweeps, BC, RL, or any broader Isaac job until that smoke
passes.

A later 2026-06-20 UI Launchable attempt for the same payload did not reach
the project smoke stage:

```text
prepared bundle:
  artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T01-21-14Z.tar.gz
instance:
  isaac-launchable-b18cd5 / t7f0c8qh0
provider/type:
  AWS g6e.4xlarge L40S
UI price:
  $3.61/hr
status:
  STARTING / BUILDING / NOT READY for about 10 minutes, then deletion requested
smoke:
  not run; no bundle uploaded; no project code executed remotely
cleanup:
  CLI delete, UI delete confirmation, stop, stop --all, and repeated delete
  attempts were issued while the workspace moved through UNHEALTHY/DELETING.
  The watchdog exited with `target disappeared; cleanup confirmed`, and
  `/Users/Shenghan/bin/brev ls instances --json --all` returned
  `{"workspaces": null}`.
```

This attempt should not be interpreted as a robotics result. It only confirms
another Brev/Launchable lifecycle failure before shell access. If retrying,
reuse the guarded one-smoke procedure and do not create a second instance while
any workspace is visible in `brev ls instances --json --all`.

Immediate retry after that also failed before project execution:

```text
instance:
  isaac-launchable-7ccc42 / hqo1aftwz
provider/type:
  AWS g6e.4xlarge L40S
UI price:
  about $3.64-$3.65/hr
status:
  STARTING / BUILDING / NOT READY, then UNHEALTHY before shell access
smoke:
  not run; no bundle uploaded; no project code executed remotely
cleanup:
  CLI delete, stop, delete-by-id, and UI delete confirmation were issued.
  A short heartbeat cleanup monitor was created as
  `cleanup-stuck-brev-launchable-hqo1aftwz` while the workspace remained in
  `DELETING` / `UNHEALTHY`.
```

Do not open another paid Launchable until `brev ls instances --json --all`
returns `{"workspaces": null}` and the cleanup heartbeat has confirmed or been
deleted. Two consecutive AWS Launchable attempts failed before shell access, so
the next useful action after cleanup is likely a support note or waiting for
Brev service recovery, not another immediate retry.

Local hardening after this incident:

```text
docs/brev_launchable_lifecycle_hold.md
  active hold file documenting the repeated Launchable lifecycle failures

scripts/paid_compute_preflight.sh
  blocks all paid creation while the hold file exists unless
  RCA_ACK_BREV_LIFECYCLE_RISK=1 is set deliberately

scripts/project_status_report.py
  reports `Brev lifecycle hold | BLOCKED` and points the next action away from
  paid retry while the hold is active
```

As of the latest local check after the retry cleanup,
`/Users/Shenghan/bin/brev ls instances --json --all` returned
`{"workspaces": null}`. The cleanup heartbeat
`cleanup-stuck-brev-launchable-hqo1aftwz` was deleted after cleanup was
confirmed.

After the user logged back in on 2026-06-20, the read-only Brev CLI check was
run again at `2026-06-20T02:11:09Z` and still returned `{"workspaces": null}`.
`./scripts/check_brev_lifecycle_hold_clearance.sh` and
`./scripts/run_local_quality_checks.sh` both passed. This confirms auth and
cleanup state, but it does not clear the lifecycle hold.

`./scripts/brev_paid_safety_status.sh` was added afterward as a single
read-only Brev safety command. On the same restored login it reported:

```text
healthcheck=pass
org_list=pass
instance_list=pass
visible_instances=0
watchdog_processes=none
manual_delete_alerts=stale_resolved current_visible_instances=0
status=SAFE_NO_VISIBLE_PAID_INSTANCE
```

The stale manual-delete alerts are old watchdog ledgers from June 7 that are
overridden by the current proven empty org state; they are still listed so they
can be inspected before any future paid work.

Local review of the existing failed contact-smoke logs is recorded at:

```text
docs/contact_smoke_failure_review_2026-06-20.md
```

Key conclusion: all existing failed smoke logs reference older runtime payload
hashes, so they cannot prove the current payload either way. Their common
failure signature was hand/peg separation after free-space motion, zero
wall-filtered force during press, and deep penetration. The current payload
has already removed the invalid peg `RigidObjectCfg` view and keeps the peg in
the Franka articulation, but this remains unproven until a fresh Isaac smoke
for payload `b2f9fd5642fad1b615f5ff1839b37f294efd6bf213c43e243aa8cb8695d212b5`
passes.

Downstream post-gate helpers were also made compatible with the new no-
RigidObject peg model:

```text
scripts/scripted_agent.py
scripts/evaluate_contact_bc_policy.py
```

Both now fall back to the calibrated hand-derived action-frame tip pose when
`env.scene["peg"]` has no RigidObject root-pose data. `scripts/check_contact_physics_wiring.py`
guards this fallback.

Post-login check on 2026-06-20: `/Users/Shenghan/bin/brev ls instances --json --all`
returned `{"workspaces": null}` and `./scripts/brev_paid_safety_status.sh`
reported `status=SAFE_NO_VISIBLE_PAID_INSTANCE`. No paid instance was visible.
The wiring guard was also tightened to fail on new unallowlisted direct
`scene["peg"]` / `peg.data.root_*` pose consumers, and
`./scripts/run_local_quality_checks.sh` passed after the change.

A support follow-up draft with the two failed Launchable attempts and cleanup
evidence is prepared at:

```text
docs/brev_support_followup_2026-06-20.md
```

An incident evidence bundle was generated after cleanup:

```text
artifacts/brev_lifecycle_incidents/2026-06-20T02-01-55Z/
artifacts/brev_lifecycle_incidents/2026-06-20T02-01-55Z.tar.gz
sha256: e44c452a90ca309ff36c557508f6aefe9834ee16083b30570057a5141529315f
```

Latest local incident evidence bundle after adding the read-only Brev safety
snapshot:

```text
artifacts/brev_lifecycle_incidents/2026-06-20T02-19-49Z/
artifacts/brev_lifecycle_incidents/2026-06-20T02-19-49Z.tar.gz
sha256: 83f9571d11204b808f30bbf94749f8b4c937c2f41bc8a09c59506f1ab6d7b2a1
new evidence file: brev_paid_safety_status.txt
```

Latest local incident evidence bundle after adding the paid preflight
EUR/hour budget-estimate guard:

```text
artifacts/brev_lifecycle_incidents/2026-06-20T02-39-30Z/
artifacts/brev_lifecycle_incidents/2026-06-20T02-39-30Z.tar.gz
sha256: c2323eb6524ce8220c11e3864082f7b51146fb60c3080138db343a57ecf22e5f
```

Latest local incident evidence bundle after adding the manual Brev UI
credit-verification preflight guard:

```text
artifacts/brev_lifecycle_incidents/2026-06-20T02-57-31Z/
artifacts/brev_lifecycle_incidents/2026-06-20T02-57-31Z.tar.gz
sha256: 2df222e569d1a21b5c6803a0aa040a1b94792739f964f476cf8f7e7364e20329
```

The paid preflight now requires `RCA_PAID_ESTIMATED_EUR_PER_HOUR` and manual
Brev UI credit verification via `RCA_BREV_CREDITS_VERIFIED=1`, and blocks when
`hourly_estimate * TTL / 60` exceeds `RCA_PAID_BUDGET_EUR`. The Brev CLI has no
read-only credit-balance command, so the credit marker is an explicit manual UI
check. The incident bundle's `paid_preflight_hold_block.txt` confirms the
active blocker is still the lifecycle hold, not a missing budget parameter.

`scripts/brev_paid_run_watchdog.sh` now records the same cost boundary in
`watchdog_start.env` (`budget_eur`, `estimated_eur_per_hour`,
`estimated_max_cost_eur`) and logs it at startup. This does not make CLI logout
deletion possible, but it makes every guarded paid run auditable against the
budget and TTL that were accepted before creation.

`scripts/check_launchable_retry_readiness.sh` is a read-only final gate for any
future one-run Launchable retry. Without `RCA_ACK_BREV_LIFECYCLE_RISK=1` it
must fail closed on the lifecycle hold; with the acknowledgement, it still
requires local quality, `SAFE_NO_VISIBLE_PAID_INSTANCE`, `Contact-smoke bundle
| READY`, Phase 2 contact gate still blocked, manual UI credit verification,
budget/hourly estimate/TTL preflight, and empty visible org before printing
`READY_FOR_ONE_CONTACT_SMOKE_RETRY`.

The hold-clearance checker passed only for human review:

```bash
./scripts/check_brev_lifecycle_hold_clearance.sh
```

It confirmed `visible_instances=0` and `paid_preflight_hold_block=confirmed`,
but does not remove the hold. Keep `docs/brev_launchable_lifecycle_hold.md`
active until Brev service recovery is confirmed or a deliberate single retry is
chosen with `RCA_ACK_BREV_LIFECYCLE_RISK=1`.

## 2026-06-20 Short Launchable Retry And Smoke Gate Tightening

A single official AWS Isaac Launchable retry was run after local WXYZ fixes,
using `isaac-launchable-607d2a` / `5lpa3taei` on `g6e.4xlarge` L40S. The run
was deleted immediately after the smoke failed; both the watchdog and direct
CLI verification later reported:

```text
{"workspaces": null}
```

The complete failed log was pulled without overwriting canonical PASS evidence:

```text
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-607d2a_2026-06-20T04-36-06Z_FAIL.log
```

Runtime result:

```text
source_payload_sha256=e3c3df90cee2e2fd33143270b098f17c4b9131dba232db9482a3ab40c7a10a83
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL
CONTACT-SMOKE press-blocked: PASS
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
```

Interpretation: WXYZ fixed the old attach/joint-integrity failure. The peg
tracked the Franka hand to about `1e-7 m` after reset, free-space motion, and
retreat. The remaining failure was not a proven wall-contact sensor failure:
the log also showed large lateral slip (`0.20-0.26 m`), and review found that
`press-blocked` accepted negative `wall_top_z - lower_end_z` values. Negative
values mean the lower peg end is above the wall top, not blocked against it.

Local follow-up changed the contact smoke and gate:

- `scripts/contact_physics_smoke.py` now emits `CONTACT-SMOKE press-tracking`
  and fails if the physical lower peg end is not laterally near the commanded
  wall-contact point.
- `press-blocked` now requires `abs(wall_top_z - lower_end_z)` within the block
  tolerance, so hovering above the wall no longer passes as blocked.
- The smoke no longer adds `PEG_LENGTH_M` to hover/press z targets. The action
  frame is already the calibrated insertion tip, so adding the peg length used
  the stale "upper tip" convention and kept the commanded insertion end above
  the wall.
- `scripts/check_phase2_contact_gate.py`,
  `scripts/run_launchable_contact_physics_smoke.sh`, and
  `scripts/test_local_gates.py` now require the new `press-tracking` marker.

Local verification after the patch:

```text
./scripts/run_local_quality_checks.sh
[local-quality] passed
```

Prepared bundle for that historical reanchor-marker retry:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T06-42-09Z.tar.gz
Runtime source payload SHA256: 9639dff71de0d493878a6d40d5aa95cf1948c308070cf9092c52c66538fd34e0
```

Do not use this older bundle for the next run; it predates the phase-sentinel
instrumentation documented below.

## 2026-06-20 Reanchor-Marker Launchable Retry

A second short official AWS Isaac Launchable retry was run on
`isaac-launchable-ede7f3` / `ewix5zjtj` after the wrapper was tightened to use
per-run logs and require the re-anchor marker. It used:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T06-42-09Z.tar.gz
source_payload_sha256=9639dff71de0d493878a6d40d5aa95cf1948c308070cf9092c52c66538fd34e0
```

Pulled evidence:

```text
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-ede7f3_2026-06-20T06-58-21Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_runs_isaac-launchable-ede7f3_2026-06-20T06-58-21Z.tsv
```

Result:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE contact-setup: local-guide reanchored: missing
CONTACT-SMOKE free-space-reanchored: missing
CONTACT-SMOKE press-force: missing
```

The wrapper failed closed with:

```text
missing marker: CONTACT-SMOKE contact-setup: local-guide reanchored
```

Cleanup was confirmed. `brev delete isaac-launchable-ede7f3 ewix5zjtj` was
issued immediately after pulling the log; after several minutes in `DELETING`,
`brev ls instances --json --all` returned `{"workspaces": null}`, and the
watchdog printed `target disappeared; cleanup confirmed`.

Interpretation: Phase 2 remained BLOCKED. The smoke no longer lost evidence to
fixed-log overwrites, but the Python smoke exited/returned before the
post-free-space re-anchor phase.

## 2026-06-20 Phase-Sentinel Local Follow-up

Local follow-up now adds the missing control-flow evidence. The current prepared
bundle is:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T07-25-33Z.tar.gz
source_payload_sha256=1d19fecb91790e2762426723e2b5e4daaf296c6787929d8c5ab9d9c514c001c6
```

`scripts/contact_physics_smoke.py` now emits explicit phase begin/progress/end
markers for `free-space-settle`, `local-guide-reanchor`, `press-hold`, and
`retreat-hold`. It emits `CONTACT-SMOKE phase-sequence: PASS` only when all
required phases complete; otherwise the Python layer itself emits
`CONTACT-SMOKE phase-sequence: FAIL` and returns nonzero. The wrapper and phase
gate now require those phase sentinels, and `./scripts/run_local_quality_checks.sh`
passes.

The follow-up Launchable run on `isaac-launchable-57032f` / `km6cr6mj0`
confirmed this control-flow instrumentation: after a targeted inference-mode
root-pose write fix, the smoke reached `phase-sequence: PASS`. It still failed
the physical press checks with zero mean wall force, lateral errors
`[0.04027855396270752, 0.36005330085754395] m`, and `press-blocked` /
`press-no-clip` failures. The pulled evidence is under:

```text
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/
```

Cleanup was confirmed with `brev ls instances --json --all` returning
`{"workspaces": null}` and `./scripts/brev_paid_safety_status.sh` returning
`SAFE_NO_VISIBLE_PAID_INSTANCE`.

Phase 2 still has no current remote PASS log. The only useful next step is
local validation of the new lower-end feedback press formulation. Do not run
another paid retry until local quality passes and the current bundle is rebuilt.
Controller sweeps, BC, RL, broad scripted probes, and post-contact paid jobs
remain blocked.

2026-06-20 follow-up: the next current-tip servo Launchable retry
(`isaac-launchable-26bffe` / `s85xtqx1n`) produced real wall force in env0 but
failed env1 with lateral drift:

```text
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-26bffe/contact_physics_smoke_2026-06-20T09-52-29Z-currenttip.log
payload: 14da96a2a87e74c81220b3da09143b075ea933e33ec56a9f98faf54cdc9a34ef
press-force: FAIL [4.317049980163574, 0.0] N
press-tracking: FAIL [0.00972306914627552, 0.5869264602661133] m
cleanup: final `brev ls instances --json --all` returned {"workspaces": null};
         watchdog printed `target disappeared; cleanup confirmed`;
         `./scripts/brev_paid_safety_status.sh` returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

This changes the next local task: freeze reset joint randomization in
`scripts/contact_physics_smoke.py` and require the
`CONTACT-SMOKE reset-joints: deterministic` marker in the wrapper/gate before
any future remote PASS can count. Also, run future fail-closed smoke commands
through `brev exec` with an outer zero exit and a recorded inner smoke exit
code; the 26bffe run showed that `brev exec` can reconnect and repeat a command
after a nonzero smoke failure.

Current prepared bundle:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T10-14-55Z.tar.gz
source_payload_sha256=a9745f5634f5f16bfee813da46bba829794e72e1b1d49fd9e98a913608b7124a
archive_sha256=16d98d08b9fd4935d83de73047bb9b39ded70eeb28a3616510e987a122ee08b9
```

A Gmail draft was created but not sent:

```text
draft_id: r-7545863501805331854
message_id: 19ee2c7896acfa40
thread_id: 19e4e182e6100df1
to: brev-support@nvidia.com
subject: Re: Follow-up: repeated probe-only Brev lifecycle failures in org NCA-57cf-29515
attachment: artifacts/brev_lifecycle_incidents/2026-06-20T02-01-55Z.tar.gz
created_utc: 2026-06-20T02:06:33Z
rechecked_utc: 2026-06-20T02:11:09Z
send_status: draft exists; not sent
note: draft attachment is still the earlier 2026-06-20T02-01-55Z bundle unless updated manually
```

2026-06-20 follow-up: the `guide-wall-sweep` Launchable retry
(`isaac-launchable-wallsweep-9a36` / `eqb76y582`) used payload
`9a36b8041d8440fe7822c9711c8c4aa6047eb9582ec3b3e2d71f2accc009b1e2`.
Pulled evidence:

```text
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-wallsweep/contact_physics_smoke_2026-06-20T11-47-15Z-wallsweep.log
pull_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-wallsweep-eqb76y582.tar.gz
pull_archive_sha256: 974c383d10ba5f30aca292894ceea7bf16f6a695f76fcbe34f539c193e87c331
```

Result:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE press-control: local-wall-sweep
CONTACT-SMOKE press-force: PASS (mean wall force [29.153621673583984, 37.27742004394531] N)
CONTACT-SMOKE press-tracking: PASS (lower-end lateral error [0.005723054055124521, 0.008925105445086956] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.009471744298934937, -0.008838444948196411] m)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
CONTACT-SMOKE phase-sequence: PASS
```

Interpretation: wall contact forces are now real and substantial, so the
previous zero-force blocker is gone. The smoke still does not prove the
intended blocked-contact geometry because the dynamic peg lower end rides
slightly above the wall top while the guide is swept upward into it. Phase 2
therefore remains BLOCKED. Do not run controller sweeps, BC, RL, or more paid
post-contact work until the local smoke fixture/blocked-contact assertion is
fixed and a future short Launchable smoke produces `press-blocked: PASS`.

Cleanup was confirmed after deletion briefly cycled through `DELETING` and
`DEPLOYING`: a retry returned `instance ... not found`, `brev ls instances
--json --all` returned `{"workspaces": null}`, `./scripts/brev_paid_safety_status.sh`
returned `SAFE_NO_VISIBLE_PAID_INSTANCE`, and the watchdog printed
`target disappeared; cleanup confirmed`.

Local follow-up: `scripts/contact_physics_smoke.py` now makes the
`guide-wall-sweep` blocked check radius-aware. The Launchable log showed
`lower_end_z - wall_top_z` around `8.8-9.5 mm`, which matches the
`PEG_RADIUS_M=10 mm` cylindrical centerline offset. The `arm-servo` diagnostic
path still requires the lower end near the wall-top plane, but the default
contact-physics gate now checks the correct cylinder-vs-wall edge relation.
`scripts/check_contact_physics_wiring.py` guards this radius-aware check.

Current prepared bundle after the radius-aware blocked check:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T12-05-01Z.tar.gz
source_payload_sha256=3ac9064fda3bc0c88aee7c3770f3a8f6087e56158fa22beb81ff75fae74e69fb
archive_sha256=641df0fd25f0e50ff3176b9dab917aa4709edfba0f9ce74a85f48948d9eb7456
local_quality: ./scripts/run_local_quality_checks.sh passed
brev_safety: ./scripts/brev_paid_safety_status.sh returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

## Recommended Next Steps

0. The environment contact-physics smoke is now validated on the official AWS
   Isaac Launchable runtime. Do not rerun the smoke just to reconfirm it unless
   runtime source payload changes or the archived evidence becomes stale.
1. Do not run a full Isaac install/evaluation through the current Brev GCP path.
2. Treat the AWS Isaac Launchable as technically validated but expensive; do not create another paid Brev/AWS/GPU environment unless `scripts/paid_compute_preflight.sh` passes with an explicit budget, conservative EUR/hour estimate, TTL, valid Brev CLI auth, empty visible org, and estimated max cost inside the budget.
   Local create scripts now also require `RCA_ALLOW_PAID_BREV_CREATE=1` before they will call `brev create`, and the paid CLI wrappers start `scripts/brev_paid_run_watchdog.sh` before creation. For UI Launchable runs, run `scripts/start_brev_ui_launchable_watchdog.sh` before clicking Create, or start `scripts/brev_paid_run_watchdog.sh` with a target name/id immediately after creation.
3. Do not run another paid sweep on the current scripted handoff / `preload-direction` family; full-quaternion, axis-aware, XY-retention, and joint-step limiter variants all failed closed before a useful post-handoff eval.
4. Keep Brev support focused on the separate `CreateWorkspace unexpected EOF` CLI create failure; that failure happens before SSH/Isaac/ports and is not explained by Launchable runtime behavior.
5. If another AWS Launchable is ever approved for a short validation of a new formulation, use the same smoke/runtime/deletion discipline:

```bash
docs/aws_isaac_launchable_runbook.md
scripts/create_launchable_bundle.sh
scripts/run_launchable_headless_smoke.sh
scripts/run_launchable_rca_diagnostic_matrix.sh
scripts/run_launchable_phase2_fresh_preload_direction.sh
   scripts/run_launchable_phase2_absik_handoff_probe.sh
   scripts/run_launchable_phase2_jointpos_nullspace_probe.sh
   scripts/run_launchable_phase2_jointpos_rotate_descend_probe.sh
   scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh
scripts/run_launchable_phase2_jointpos_reachable_guard_probe.sh
scripts/run_launchable_phase2_jointpos_reachable_guard_adaptive_rotpolish_probe.sh
scripts/run_launchable_phase2_jointpos_reachable_guard_neardepth_rotgate_probe.sh
scripts/analyze_rotation_polish_trace.py
scripts/run_brev_reachable_guard_probe.sh
```

6. If Brev support confirms the create API is healthy, rerun only a tiny probe first. No Isaac install, no evaluation:

```bash
RCA_ALLOW_DIRTY=1 scripts/run_brev_probe_direct_ssh_gate.sh
```

7. Do not rerun root-frame waypoint, orientation-current waypoint, full-target Abs IK, the single-joint `panda_joint4=-2.6` initial-posture diagnostic, no-wall-collision target diagnostics, simple target-offset variants, native IK solver-method variants, the current JointPos nullspace matrix, the current JointPos rotate-descend wrapper, `reachable-approach` unchanged, the strong reachable guard unchanged, the tuned reachable guard unchanged, the rotation-gated reachable guard unchanged, the soft-gated reachable guard unchanged, the depth-aware rotation polish wrapper unchanged, adaptive rotpolish unchanged, near-depth rotgate unchanged, the old scripted/video candidate wrapper unchanged, the final-contact-servo route unchanged, or the socket-insertion-servo route unchanged. The no-wall run was worse than full-target baseline, the contact-force signal is not wall-only, target offsets did not improve true socket XY, `dls/pinv/svd/trans` all failed closed with the same `panda_joint4` signature, the JointPos nullspace probe did not activate its nullspace term while regressing depth, rotate-descend either fell into XY recovery or drifted laterally when recovery was disabled, reachable-approach still failed strict handoff while consuming `panda_joint4` margin, the strong guard preserved too much margin while stalling axial progress, the tuned guard improved depth but still missed z/contact/rotation gates, the rotation gate protected margin by over-freezing descent, the soft gate reached depth/contact but still missed rotation and late XY retention, depth-aware rotation polish preserved XY/Z but worsened rotation, adaptive rotpolish only slightly improved selected rotation while worsening final rotation, near-depth rotgate still missed depth/rotation/contact together, metric-XY plus hold-Z centered laterally but never reached axial readiness, and socket-insertion-servo found a metric/task-frame mismatch while never reaching contact. No prepared scripted-controller trace route is currently approved as an unchanged next paid run.
   The legacy historical-replay script now fails closed unless `RCA_ALLOW_HISTORICAL_PRELOAD_REPLAY=1` is set for a deliberate replay-drift diagnostic.
8. Keep the fresh-preload guards enabled unless there is a specific diagnostic reason:

```text
RCA_LAUNCHABLE_HANDOFF_MAX_STRICT_MISS=1.0
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_LATERAL_DRIFT=0.02
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_AXIAL_DRIFT=0.02
RCA_LAUNCHABLE_HANDOFF_REPLAY_MAX_ROT_DRIFT=0.25
```

9. A viewport video is blocked. The guarded trace-only run
   `artifacts/videos/trace_only/2026-06-21T02-49-00Z/video_trace.json` failed
   `scripts/check_peg_in_hole_video_candidate.py`; Brev cleanup was confirmed
   with `{"workspaces": null}` and `SAFE_NO_VISIBLE_PAID_INSTANCE`. The follow-up
   socket-servo trace
   `artifacts/videos/trace_only/2026-06-21T05-53-23Z/video_trace.json` fixed the
   WXYZ frame-audit issue (`scripts/audit_trace_frame_alignment.py` passed), but
   it still recorded only one step and failed the peg-video candidate check. More
   importantly, `scripts/check_scripted_action_response_trace.py` fails it:
   the commanded action-frame delta was approximately
   `[+0.00014, -0.00012, -0.00149]`, while the actual post-action delta was
   `[-0.01179, +0.00047, +0.00766]` with cosine `-0.622`. The current
   socket-servo/joint-IK route is therefore a rejected control-interface route,
   not a video-ready near success. This motivated the dedicated action-semantics
   probe below; do not keep adding late flags to the existing socket-servo path.
10. The old relative-IK raw-action calibration is not an approved shortcut.
    Running `scripts/check_action_calibration_summary.py` on
    `artifacts/calibration/relative_ik_action/latest_seed_42.json` fails because
    zero-action drift is about `0.0148m`, Z raw action dominantly moves world X
    instead of world Z, and multiple raw axes map dominantly to world X.
    `scripts/run_remote_action_calibration.sh` now validates new calibration
    summaries by default. A future calibration can feed insertion control only
    if it passes this checker and the subsequent trace passes
    `scripts/check_scripted_action_response_trace.py`.
11. The guarded action-semantics probes have now run and failed. The first trace
    `artifacts/videos/trace_only/2026-06-21T06-48-58Z/video_trace.json` used a
    world-frame command delta of `[0, 0, -0.0015]`, but
    `scripts/check_scripted_action_response_trace.py` reported `bad_steps=4/8`,
    `min_cosine=-0.535`, and a worst actual TCP delta of about
    `[-0.01195, +0.00038, +0.00758]`. This proves the current joint-IK wrapper
    is not a trustworthy insertion-control surface. Do not rerun
    `scripts/recreate_brev_and_run_action_semantics_probe_trace.sh` unchanged.
    The follow-up suite after the local XYZW inverse repair also failed at the
    down probe before it could justify an up probe:
    `artifacts/videos/trace_only/2026-06-21T07-31-53Z/video_trace.json`
    reported `bad_steps=6/8`, `min_cosine=-0.559`, and a worst actual TCP delta
    of about `[-0.01120, +0.00071, +0.00756]` for the same `[0,0,-0.0015]`
    command. That closes the XYZW-inverse repair as an approved paid path. Do
    not run a viewport video, another unchanged insertion trace, or the same
    action-semantics suite again. The next work must be local-first control
    interface replacement plus a positive and negative semantic gate before any
    new paid runtime action. The current replacement candidate is empirical
    JointPositionAction response control: `scripts/calibrate_joint_position_action.py`
    measures the 3x7 action-frame response matrix for small absolute joint-target
    offsets, `scripts/joint_response_control.py` converts a requested world-frame
    TCP delta into a bounded minimum-norm joint delta, and
    `scripts/run_remote_joint_response_calibration.sh` can run that calibration
    inside an already-created Isaac runtime. This still needs remote semantic
    validation before any insertion trace or viewport video is allowed.
    The first paid joint-response semantics attempt on 2026-06-21
    (`rca-joint-response-semantics-vm` / `ba96pfju9`) did not reach robot
    semantics. It failed immediately in `scripts/calibrate_joint_position_action.py`
    because IsaacLab 7 no longer exports
    `isaaclab_tasks.utils.add_launcher_args`. The only pulled artifact was:

```text
artifacts/calibration/joint_position_action/2026-06-21T08-19-02Z/seed_42.log
```

    Cleanup was confirmed by the wrapper and an independent safety check:
    Brev returned `{"workspaces": null}`, no watchdog process remained, and
    `scripts/brev_paid_safety_status.sh` reported
    `SAFE_NO_VISIBLE_PAID_INSTANCE`. This is not evidence that joint-response
    control failed; it is only an API-compatibility failure before calibration.
    The local fix now makes `scripts/calibrate_joint_position_action.py` use the
    same `AppLauncher + parse_env_cfg` fallback already used by
    `scripts/scripted_agent.py`, and `PYTHONDONTWRITEBYTECODE=1
    ./scripts/run_local_quality_checks.sh` passes after the fix. If another paid
    retry is approved, it must be one short joint-response calibration plus
    down/up semantic probe only; still do not record video or run an insertion
    trace until those semantic probes pass.
    The second paid joint-response semantics attempt on 2026-06-21
    (`rca-joint-response-semantics-vm` / `gml9m5csj`) also did not reach robot
    semantics. It reused the already-created paid instance and failed during
    calibration startup with Isaac/Kit aborting after warning that `pxr` modules
    were loaded before `SimulationApp`:

```text
artifacts/calibration/joint_position_action/2026-06-21T08-50-32Z/seed_42.log
free(): invalid pointer
[Warning] [simulation_app.simulation_app] Modules: ['pxr', ...] were loaded before SimulationApp was started
/isaac-sim/python.sh: line 73: 2074 Aborted (core dumped)
```

    No `seed_42.json`, down/up semantic trace, insertion trace, or video was
    produced. Artifacts were pulled, deletion was retried until
    `/Users/Shenghan/bin/brev ls instances --json --all` returned
    `{"workspaces": null}`, `scripts/brev_paid_safety_status.sh` reported
    `SAFE_NO_VISIBLE_PAID_INSTANCE`, and the stale local watchdog was stopped.
    The local fix removes the module-scope
    `import robot_contact_assembly_tasks.tasks` from
    `scripts/calibrate_joint_position_action.py` so task registration happens
    only inside the launcher context. `scripts/test_local_gates.py` now has an
    AST static gate to prevent that module-scope import from returning, and
    `PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh` passes.
    This is still launch-order evidence, not evidence that empirical
    joint-response control itself works or fails. The next paid action, if any,
    remains one short calibration + down/up semantic probe after confirming
    `SAFE_NO_VISIBLE_PAID_INSTANCE`; do not record a viewport video first.
    The third paid joint-response semantics attempt on 2026-06-21
    (`rca-joint-response-semantics-vm` / `k8sp0dux8`) reached the real semantic
    gate and failed it. The launch-order fixes worked: calibration produced
    `artifacts/calibration/joint_position_action/2026-06-21T09-20-16Z/seed_42.json`,
    and `scripts/joint_response_control.py` predicted both `[0,0,-0.0015]`
    and `[0,0,+0.0015]` with cosine about `1.0` and negligible residual. The
    real down rollout nevertheless failed:

```text
trace: artifacts/videos/trace_only/2026-06-21T09-21-19Z/video_trace.json
action-response: FAIL
bad_steps: 6/8
bad_fraction: 0.75
min_cosine: -0.5655236741426465
worst command_delta: [0.0, 0.0, -0.0015000104904174805]
worst actual_delta: [-0.011340349912643433, +0.0007162163965404034, +0.007791638374328613]
cleanup: wrapper confirmed {"workspaces": null}; safety reported SAFE_NO_VISIBLE_PAID_INSTANCE
```

    Interpretation: the empirical matrix is not enough because the scripted
    rollout was not running the same experiment as the calibration. Calibration
    resets, reads the current joint positions, holds those positions for
    settling, then applies a fixed joint offset for multiple steps. The scripted
    trace used zero-action warmup, which is a dangerous nonzero command for a
    7D JointPositionAction task, and then measured one-step sequential deltas
    while the arm was still drifting. The immediate local fix changes
    `scripts/scripted_agent.py` so 7D action warmup and demo-reanchor settle use
    hold-current joint targets instead of all-zero joint targets; the same file
    now prints `hold-current-joints` for that warmup mode. `scripts/test_local_gates.py`
    has a static gate for this. `PYTHONDONTWRITEBYTECODE=1
    ./scripts/run_local_quality_checks.sh` passes after the fix.

    Do not rerun the previous joint-response semantic suite unchanged. The next
    remote action, if one is justified, must be a tiny down/up semantic probe of
    the hold-current warmup fix only, still with budget/TTL/watchdog/artifact
    pullback/deletion. Do not run insertion, RL/IL, VLM, ROS, or viewport video
    before this action-semantics gate passes.
    The follow-up hold-current validation on 2026-06-21
    (`rca-joint-response-holdwarmup-vm` / `5iyt1bhxd`) passed the minimal
    down/up action-semantics gate and cleaned up safely. Evidence:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T09-47-57Z/seed_42.json
down trace:  artifacts/videos/trace_only/2026-06-21T09-49-17Z/video_trace.json
up trace:    artifacts/videos/trace_only/2026-06-21T09-49-34Z/video_trace.json
down check:  bad_steps=0/8, min_cosine=0.999734, action-response PASS
up check:    bad_steps=0/8, action-response PASS
cleanup:     wrapper confirmed {"workspaces": null}; safety reported SAFE_NO_VISIBLE_PAID_INSTANCE
```

    This is the first successful post-contact-gate control-interface semantic
    result. It proves that 7D JointPositionAction can produce small commanded
    action-frame down/up motion when the warmup holds current joints instead of
    commanding all-zero joint targets. It does not prove insertion success and
    does not justify a viewport video yet. The task traces still show
    `action_tip_alignment` around `0.049m`, so a normal insertion controller
    that targets the action frame directly at the socket can still be
    structurally wrong for the actual peg-tip/socket success metric.

    Next work: implement and locally gate a metric-tip residual controller that
    converts task-space peg-tip/socket residuals into small joint-response
    commands while preserving the hold-current warmup. The next paid run, if
    any, should be one trace-only insertion attempt with that metric-tip
    controller plus the existing semantic/video-candidate validators. Do not
    start RL/IL/VLM/ROS or viewport video until a trace shows sustained
    peg-tip/socket insertion semantics.
12. Only run temporal residual-current BC after the demonstration labels show sustained post-contact behavior. Use `scripts/analyze_contact_demo_coverage.py` with local traces plus Launchable archives before any paid learned-policy run; the 2026-06-09 combined report still shows zero target-gate passing steps across 38 traces.
13. For the next local implementation, use `scripts/select_final_contact_reset_candidates.py` and `artifacts/reports/final_contact_reset_candidates_2026-06-09.json` as the seed source for a reset-based final-contact stabilizer/evaluator. Do not treat those candidates as success labels unless a future report contains `target_gate_success > 0`.
14. `scripts/evaluate_contact_bc_policy.py` can now consume the candidate manifest directly via `--preload-candidate-json`; use this for future stabilizer baselines so the handoff seed is reproducible.
15. `scripts/extract_final_contact_candidate_dataset.py` generated a candidate-window temporal residual-current dataset from the manifest. Use it only as a stabilization/reset prior unless new data adds strict-success samples.
16. Training `artifacts/policies/phase2_contact_bc_final_contact_candidates/bc_mlp.pt` has not been completed locally because PyTorch is unavailable in the host Python. Run `scripts/train_contact_bc_policy.py` in the Isaac/PyTorch runtime if a local prior checkpoint is needed.
17. Use `scripts/run_remote_train_final_contact_candidate_bc.sh` and `scripts/run_remote_eval_final_contact_candidate_bc.sh` only on an already-running Isaac/PyTorch environment. They do not provision Brev and therefore should be paired with the existing paid-run watchdog only if a new environment has been deliberately created elsewhere.

## 2026-06-21 Joint-Response Socket-Insertion Result

The next structural route moved away from ambiguous IK commands and calibrated
the actual `JointPositionAction` response before running socket-insertion
servo. This is a real improvement over the previous routes: the remote
calibration proves that small requested Z motion maps to the expected physical
tip motion.

Calibration evidence:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T10-21-39Z/seed_42.json
down_check: pass_gate=True cosine=0.9999999999999946 residual_norm=1.7823301472130166e-10
up_check: pass_gate=True cosine=0.9999999999999946 residual_norm=1.7823301472130166e-10
```

The first guarded joint-response socket trace ran on
`rca-joint-response-socket-servo-vm` / `3evn0rn85`:

```text
trace: artifacts/videos/trace_only/2026-06-21T10-22-58Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-21T10-22-58Z/video_summary.json
action_response_check: PASS bad_steps=0/101 min_cosine=0.45986878917803237
trace_frame_alignment_check: PASS
task_gate_pass: False
video_candidate_pass: False
initial_lateral: 0.000158m
best_lateral: 0.000158m
initial_axial: 0.049638m
best_axial: 0.008006m
best_rot: 0.000488rad
max_contact_force_magnitude: 1.626N
```

This reached the contact boundary with good lateral alignment, correct frame
semantics, and real contact force, but it still did not reach sustained task
success. The trace event log records a pop immediately after the near-boundary
state: step `101` moved to lateral `0.031609m`, axial `0.017230m`, and rotation
`0.066278rad`. The current blocker is therefore no longer "does the action
interface move the robot?" but "can the final insertion controller stay stable
through guide contact?"

A second guarded run on `rca-joint-response-socket-soft-vm` / `lkllxgfml` used
smaller Z/preload steps, held orientation when already aligned, and flushed the
trace every step:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T10-49-58Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T10-51-20Z/
result: no video_summary.json
trace_events: control_loop_setup, control_loop_enter, step_begin=0 only
cleanup: brev ls instances --json --all returned {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

This second run is not evidence that the soft controller failed insertion. It
is an execution/runtime failure: Isaac entered the control loop but did not
record a completed first step before timeout cleanup. Do not count it as a
semantic controller result.

Current decision: do not record a viewport video and do not start RL/IL/VLM on
top of this environment yet. The semantic smoke is still blocked at the final
insertion dynamics. The next local-first step is to add a deterministic,
short-horizon final-contact diagnostic around the 8mm axial boundary: hold XY
and orientation fixed, descend/preload in very small increments, log contact
normal/lateral error every step, and include a negative control where socket
walls or contact sensors cannot produce the same success signal. Only if that
diagnostic passes should another paid trace be run.

That local diagnostic and the first controller safety fix are now implemented:

```text
script: scripts/check_final_contact_boundary_diagnostic.py
logic: scripts/socket_insertion_servo_logic.py
gate: scripts/test_local_gates.py
```

The diagnostic automatically merges `trace_events.jsonl` rows when a remote
run did not flush the last step into `video_trace.json`. Against the known
`2026-06-21T10-22-58Z` trace it fails closed with:

```text
unsafe_boundary_descent_count=2
pop_event_count=1
first_unsafe_boundary_descent: step 99, axial 0.008118m, offset_z -0.001500m
first_pop_event: step 100 -> 101, lateral 0.000790m -> 0.031609m, axial 0.008006m -> 0.017230m
```

`SocketInsertionServoConfig` now has a contact-boundary mode: when XY and
rotation are ready, real contact force is present, and axial error is within
`success_z_tolerance + contact_boundary_tolerance`, the controller uses
`contact_boundary_step` rather than the normal `z_step`. The joint-response
remote wrapper sets the first guarded default to:

```text
RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_TOL=0.0010
RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_STEP=0.00005
```

This is still not proof of success. It is the local semantic guard needed before
another paid trace. The next paid trace is justified only after local quality
passes and Brev safety is green, and it must include the boundary diagnostic as
a validator before any viewport video attempt.

A guarded paid trace was attempted after the contact-boundary micro-step change:

```text
instance: rca-joint-response-boundary-vm / o69gah0k8
calibration: artifacts/calibration/joint_position_action/2026-06-21T11-36-56Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T11-38-02Z/
result: no video_summary.json or video_trace.json
trace_events: control_loop_setup, control_loop_enter, step_begin=0 only
```

Do not interpret this as an insertion-controller result. It is the same
runtime/execution failure pattern as `2026-06-21T10-51-20Z`: Isaac entered the
control loop but did not complete the first step. The next paid action should
not be another controller retry. First fix the first-step observability and
runtime diagnosis path.

That diagnostic hardening is now in place locally:

```text
scripts/scripted_agent.py: fine-grained step_phase events for the first N steps
scripts/run_remote_scripted_trace_only.sh: defaults RCA_SCRIPTED_WATCHDOG_SECONDS=120 and RCA_TRACE_PHASE_STEPS=5
```

The next minimal remote trace should be a short diagnostics run, not a full
video or RL run: confirm whether the first-step stall is in pose sampling,
target computation, insertion metrics, contact-force reads, action computation,
or `env.step`. Only after that path returns to producing summaries should the
contact-boundary controller be judged.

The first short step-0 diagnostic trace ran on `rca-step0-diagnostic-vm` /
`8szk4nfe5`:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T12-14-25Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T12-15-37Z/
video_summary.json: missing
video_trace.json: missing
trace_events: setup, enter, step_begin=0, begin, pose sampling, target pose,
  insertion metrics, tip_to_socket_position, pre_contact_force, metrics_ready
cleanup: target disappeared; scripts/brev_paid_safety_status.sh returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

This narrows the missing-trace failure to after `metrics_ready` and before
`before_env_step`. That is inside per-step action/phase computation, not Isaac
startup, pose sampling, insertion metrics, tip-to-socket metrics, or
contact-force reads. The code is now locally hardened again:

```text
scripts/scripted_agent.py:
  - writes partial summary/trace artifacts even when zero trace rows exist
  - records last_step_started and last_trace_phase in partial summaries
  - adds step_phase markers across ready masks, insert state, polish/settle,
    final-contact servo, socket-insertion servo, and control-action solve
./scripts/run_local_quality_checks.sh: passed
./scripts/brev_paid_safety_status.sh: SAFE_NO_VISIBLE_PAID_INSTANCE
```

Project-level decision: the original "language-conditioned contact-rich
assembly system" is still feasible, but the current milestone is lower in the
stack. Do not move to RL/IL/VLM, public claims, or success-video capture until
the semantic peg-in-hole trace passes. A simulator success will still not be a
drop-in controller for arbitrary real arms; it should become a portable system
architecture plus a robot-specific adapter, calibration, safety, and revalidation
workflow.

A second short paid diagnostic trace after the zero-row partial writer narrowed
the stall further:

```text
instance: rca-step0-phase-diagnostic-vm / oliz8h0yt
calibration: artifacts/calibration/joint_position_action/2026-06-21T12-52-12Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T12-53-30Z/
video_summary.json: missing
video_trace.json: missing
trace_events: reached step 0 phase before_socket_insertion_servo_command
cleanup: org cleanup confirmed with {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

This means the failure is no longer the broad `metrics_ready -> before_env_step`
gap. It is inside the socket-insertion-servo command block before the step row
is appended. Because the process still produced no `atexit` summary, the likely
termination path is a signal/timeout or hard Kit/runtime exit rather than a
normal Python exception.

The local diagnostic hardening after this run:

```text
scripts/scripted_agent.py:
  - installs SIGTERM/SIGINT handlers that write partial summary/trace artifacts
  - marks partial artifacts finalized to avoid duplicate atexit writes
  - splits socket-insertion-servo command into sub-phases for config, offset,
    socket-frame rotation, target update, quaternion update, and GPU metric
    reductions
scripts/test_local_gates.py:
  - statically guards the signal handlers and new phase markers
./scripts/run_local_quality_checks.sh: passed
git diff --check: passed
```

The next paid run, if any, should still be short and diagnostic-only. Its job is
to determine whether the command-block failure is in the pure servo offset
calculation, quaternion/target update, or CUDA metric reductions. It should not
attempt viewport video until a fresh trace writes `video_trace.json` and passes
the action-response, frame-alignment, contact-boundary, and video-candidate
checks.

The next diagnostic confirmed the exact command-block sub-phase:

```text
instance: rca-socket-command-diagnostic-vm / iw1712l9s
calibration: artifacts/calibration/joint_position_action/2026-06-21T13-23-02Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T13-24-14Z/
video_summary.json: missing
video_trace.json: missing
last trace event: step 0 phase before_socket_insertion_servo_metric_reductions
cleanup: org cleanup confirmed with {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

The socket-insertion-servo target command itself completed: config, offset
calculation, socket-frame rotation, target update, and quaternion update all
emitted `after_*` phase markers. The remaining stall was the summary-only CUDA
scalar reductions used to update `socket_insertion_servo_max_lateral`,
`socket_insertion_servo_min_axial`, and `socket_insertion_servo_max_xy_offset`.
Those statistics are not needed to generate the control command and can be
derived from full trace rows later.

Local fix after this run:

```text
scripts/scripted_agent.py:
  - removed the socket-servo command-block masked CUDA max/min reductions
  - records skipped_socket_insertion_servo_metric_reductions instead
scripts/test_local_gates.py:
  - guards the skip so this diagnostic-only reduction is not reintroduced
```

The next paid diagnostic should verify that the rollout now reaches
`before_env_step`, `after_env_step`, and `trace_row_appended` for at least step
0. Only after that should the run length be increased back toward a successful
semantic trace and then a viewport video.

That diagnostic has now passed its narrow gate:

```text
instance: rca-joint-response-step5-vm / 3meqf97mn
calibration: artifacts/calibration/joint_position_action/2026-06-21T14-00-29Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T14-01-40Z/
video_summary.json: present
video_trace.json: present
trace rows: 5
last trace events: before_env_step -> after_env_step -> trace_row_appended -> final_artifacts_written
cleanup: org cleanup confirmed with {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

This is not a peg-in-hole success and not a viewport-video candidate. The run was
intentionally limited to 5 steps with peg-video-candidate validation disabled,
so the trace stayed in `settle`:

```text
success_step: null
final_success_rate: 0.0
best_lateral: 0.000147m
best_axial: 0.048662m
first phase: settle
last phase: settle
```

The important result is structural: removing the summary-only CUDA reductions
cleared the previous step-0 stall, and the runner can again produce
`video_summary.json`, `video_trace.json`, and `trace_events.jsonl` under the
official AWS Isaac Launchable runtime.

The run also exposed a cost/latency issue. `RCA_ISAACLAB_RUNTIME_PROFILE=trace-only`
was correctly passed into the remote container and skipped the extra explicit
contrib/RL/rsl-rl/h5py install block, but `./isaaclab.sh --install
assets,physx,tasks` still installed a broad IsaacLab source set including RL and
video-related dependencies because those tokens are not valid narrow install
targets for this IsaacLab version. Before more repeated paid diagnostics, either
use a pre-warmed environment/cache or replace that install step with a truly
narrow task-runtime setup.

The wrapper wording was also fixed locally after this diagnostic: if
peg-video-candidate validation is disabled, it now reports only that the trace
runner completed, not that the trace was a video candidate. Keep this guard,
because diagnostic traces must not be promoted into success evidence.

The next longer semantic trace was stopped early after enough evidence was
collected:

```text
instance: rca-joint-response-semantic-vm / bk3cajkvf
calibration: artifacts/calibration/joint_position_action/2026-06-21T14-30-42Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T14-31-43Z/
steps recorded: 489
success_step: null
final_success_rate: 0.0
best_axial: 0.0080797076m at step 182
final_axial: 0.0087215072m
best_lateral: 0.0001472154m
final_lateral: 0.0005120616m
max_contact_force_magnitude: 1.3475245
last_phase: settle
cleanup: org cleanup confirmed with {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

This is not a success trace and not a video candidate. It is useful because the
failure is no longer gross approach, missing contact, or a step-0 crash: the
best state missed the 8mm axial success threshold by about 0.08mm, then drifted
back out. Trace fields also exposed that `socket_insertion_servo_state=True`
while `socket_insertion_servo_active=False`; code review found
`socket_insertion_servo_rotate_mask = socket_insertion_servo_mask` followed by
in-place `&=` filters, which mutated the main activation mask before trace row
recording and some downstream orientation logic. This was fixed locally by
cloning the rotate mask, and `scripts/test_local_gates.py` now guards against
the alias.

Local follow-up after this trace:

```text
scripts/scripted_agent.py:
  - clone socket_insertion_servo_mask before deriving the rotate-only sub-mask
scripts/socket_insertion_servo_logic.py:
  - raise contact_boundary_step default from 0.00005m to 0.00015m
scripts/run_remote_socket_insertion_servo_trace.sh:
  - default RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_STEP to 0.00015m
scripts/run_remote_joint_response_socket_insertion_servo_trace.sh:
  - default RCA_JOINT_RESPONSE_SOCKET_CONTACT_BOUNDARY_STEP to 0.00015m
scripts/check_final_contact_boundary_diagnostic.py:
  - allow the same 0.00015m boundary micro-step in validation
scripts/test_local_gates.py:
  - guards the mask clone
  - verifies the boundary micro-step is still clipped to metric_z - success_z_tol
./scripts/run_local_quality_checks.sh: passed
git diff --check: passed
```

This keeps the success threshold unchanged. The intent is only to let the
contact-boundary servo correct the observed 0.08mm near-miss in one bounded
micro-step; the pure servo logic still clamps the boundary z offset to the
remaining distance above the success threshold rather than blindly descending by
the full configured step.

A new paid run is now technically justified only as a short, budget-capped
semantic validation of this exact change. Do not record viewport video unless
the validator-enabled trace first proves sustained peg-in-hole success.

That short validation has now been run and failed closed:

```text
instance: rca-boundary-step015-vm / t7ree4ri7
calibration: artifacts/calibration/joint_position_action/2026-06-21T15-11-06Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T15-12-20Z/
steps recorded: 500
success_step: null
final_success_rate: 0.0
best_axial: 0.0080776298m at step 172
final_axial: 0.0087595545m
best_lateral: 0.0001472154m
final_lateral: 0.0005570633m
best_rot: 0.0003452670rad
final_rot: 0.0607439503rad
max_contact_force_magnitude: 1.2441853N
cleanup: org cleanup confirmed with {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

This invalidates the simple "larger contact-boundary micro-step will cross the
last 0.08mm" hypothesis. The trace still never reached sustained success, and
the best axial miss is effectively unchanged from the previous semantic trace.
The controller then drifted back out to about 8.76mm axial error.

The validators identify the next blocker more specifically:

```text
action_response_check: FAIL
  bad_steps: 47 / 309 assessed
  worst step: 426
  worst phase: socket-insertion-servo
  min_cosine: -0.7645606147

final_contact_boundary_check: FAIL
  unsafe_boundary_descent_count: 35
  first unsafe boundary descent: step 158, axial 0.0082480386m, offset_z -0.0005000000m
  fail: no sustained task-success window at the contact boundary
  fail: controller used a normal descent step after contact near the axial boundary

peg_video_candidate_check: FAIL
  task_gate_pass: False
  video_candidate_pass: False
  fail: task gate never reached sustained configured success tolerances
  fail: pose never reached stricter guide-clearance lateral tolerance

trace_frame_alignment_check: PASS
```

Do not rerun the `0.00015m` boundary-step branch unchanged and do not record a
viewport video from it. The next work is local-first: fix the command/response
semantics around socket-insertion-servo at the contact boundary, and make the
near-boundary controller enter the micro-step branch before any normal
`-0.0005m` descent after contact. A future paid run is justified only after a
local diagnostic proves that the contact-boundary phase selection and
action-response checks should change in the expected direction.

Local follow-up after that failure:

```text
scripts/socket_insertion_servo_logic.py:
  - keeps the task success contact threshold at 0.5N
  - adds contact_boundary_min_force, default 0.25N, used only inside the
    near-axial contact-boundary band
  - adds contact_boundary_xy_gain/contact_boundary_xy_clamp, default 0, so
    boundary micro-steps freeze XY instead of scrubbing laterally after contact

scripts/scripted_agent.py:
  - exposes the new contact-boundary force/XY parameters
  - records socket_insertion_servo_boundary_contact_ready in trace rows

scripts/check_final_contact_boundary_diagnostic.py:
  - evaluates boundary rows from decision-time pre_contact_force_magnitude when
    available, instead of judging the controller by post-step contact it could
    not yet observe
  - adds --boundary-contact-min-force, default 0.25N

scripts/run_remote_socket_insertion_servo_trace.sh:
scripts/run_remote_joint_response_socket_insertion_servo_trace.sh:
  - pass the new boundary defaults to the remote trace runner
```

Offline replay of the old `2026-06-21T15-12-20Z` trace through the pure servo
logic is only a directional check, not success evidence. It shows the new local
decision rule addresses the specific failure mode:

```text
old-like logic: near_rows=345, boundary=307, normal_descend=38, unsafe=38, boundary_xy_nonzero=307
new logic:      near_rows=345, boundary=341, normal_descend=4,  unsafe=4,  boundary_xy_nonzero=0
```

The remaining four normal descents are the initial no-pre-contact probe rows
before contact becomes observable to the controller. This is acceptable for a
next short semantic validation, but still not proof of success.

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

git diff --check
  passed
```

Next allowed paid action, if any: one short validator-enabled joint-response
socket-insertion trace with the new boundary-contact/XY-freeze defaults, only
after `./scripts/brev_paid_safety_status.sh` reports
`SAFE_NO_VISIBLE_PAID_INSTANCE`. Do not record viewport video unless that trace
passes action-response, final-contact-boundary, frame-alignment, and
peg-video-candidate validators.

2026-06-21 follow-up trace with the boundary-contact/XY-freeze defaults failed
closed but exposed a more important structural mismatch:

```text
instance: rca-boundary-freezexy-vm / ii96h00e2
trace dir: artifacts/videos/trace_only/2026-06-21T15-59-31Z/
best_axial: 0.008009647950530052m at step 280
final_axial: 0.008044378831982613m
best_lateral: 0.00014721538173034787m
max_contact_force_magnitude: 1.900056004524231N at step 266
success_step: null
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

The run reached the geometric boundary and real contact, but failed the
contact-aware gate:

```text
action_response_check: FAIL, bad_steps=1, worst step=396
final_contact_boundary_check: FAIL, pop_event_count=2
peg_video_candidate_check: FAIL
trace_frame_alignment_check: PASS
```

The key finding is that the Isaac task's built-in
`terminations.insertion_success` is geometry-only: it checks lateral, axial,
and rotation tolerances, but not contact force. Our video/semantic gate
requires contact force as well. Near step 280, the scripted trace was within
about 0.01mm of the axial threshold with contact present; immediately after
that, the arm jumped back toward a reset/default posture. That makes the
internal geometry-only termination/reset a likely source of the observed pop,
and it means scripted validation must not rely on the environment's built-in
success termination.

Local fix after this run:

```text
scripts/scripted_agent.py:
  - adds --disable-insertion-success-termination, default on
  - adds --keep-insertion-success-termination for explicit opt-in to old behavior
  - sets env_cfg.terminations.insertion_success = None before gym.make when disabled
  - records insertion_success_termination_disabled in trace rows and summary

scripts/test_local_gates.py:
  - adds static checks for the termination-disable guard
```

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

git diff --check
  passed
```

Next paid action, if any: one short validator-enabled joint-response
socket-insertion trace with the same boundary-contact/XY-freeze defaults and
the now-default disabled insertion-success termination. The run is justified
only after `./scripts/brev_paid_safety_status.sh` reports
`SAFE_NO_VISIBLE_PAID_INSTANCE`. Do not record viewport video until the
contact-aware validators pass.

2026-06-21 follow-up trace with built-in insertion-success termination disabled
failed closed but substantially narrowed the remaining blocker:

```text
instance: rca-disable-reset-vm / 8us3zypas
trace dir: artifacts/videos/trace_only/2026-06-21T16-45-23Z/
success_step: 166
final_success_rate: 1.0
best_axial: 0.007974937558174133m at step 166
best_lateral: 0.00014721538173034787m at step 0
final_lateral: 0.0009611804271116853m
final_rot: 0.05461684986948967rad
max_contact_force_magnitude: 0.8971468210220337N at step 158
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Validators:

```text
action_response_check: PASS
trace_frame_alignment_check: PASS
peg_video_candidate_check: FAIL
final_contact_boundary_check: FAIL
unsafe_boundary_descent_count: 0
pop_event_count: 0
```

This confirms the geometry-only reset was a real blocker: once disabled, the
trace reached a contact-aware success step without branch pop. The remaining
failure is that `scripts/scripted_agent.py` stopped immediately on the first
success step, while the strict video/boundary validators require a sustained
window of five steps. The trace had only two axial-ready rows near the end
(`165` and `166`), so it could not pass a sustained-window check even though
the last row itself was successful.

Local fix after this run:

```text
scripts/scripted_agent.py:
  - adds --success-hold-steps, default 1 for legacy behavior
  - after first success, values >1 replace actions with hold-current-joints
    (or zero relative action) until the required consecutive success window is
    observed or the rollout ends
  - records success_hold_count, success_hold_steps,
    success_hold_exit_step, and post_success_hold_step_count

scripts/run_remote_joint_response_socket_insertion_servo_trace.sh:
  - passes --success-hold-steps ${RCA_JOINT_RESPONSE_SOCKET_SUCCESS_HOLD_STEPS:-5}

scripts/test_local_gates.py:
  - checks the post-success hold guard and wrapper default
```

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/scripted_agent.py scripts/test_local_gates.py
  passed

git diff --check
  passed

PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed
```

Next paid action, if any: one short validator-enabled joint-response trace with
the post-success hold default. It is technically justified because the previous
run reached first semantic success and failed only because the scripted loop
exited before the sustained window could exist. Still do not record viewport
video until the trace passes action-response, final-contact-boundary,
frame-alignment, and peg-video-candidate validators.

2026-06-21 success-hold trace failed closed and exposed a second control-loop
issue:

```text
instance: rca-success-hold-vm / nv7l10123
trace dir: artifacts/videos/trace_only/2026-06-21T17-16-33Z/
success_step: 166
success_hold: 0/5
final_lateral: 0.007539698854088783m
final_axial: 0.0044609056785702705m
final_rot: 0.049713972955942154rad
max_contact_force_magnitude: 0.8971468210220337N at step 158
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Validators:

```text
peg_video_candidate_check: PASS
trace_frame_alignment_check: PASS
action_response_check: FAIL
  bad_fraction=0.26666666666666666
  worst step=181, cosine=-0.9009444702808566
final_contact_boundary_check: FAIL
  fail: no sustained task-success window at the contact boundary
```

The root cause is not a new cloud/runtime failure. The trace showed that once a
first success was reached, the follow-up hold mode froze joint targets. In the
contact-rich socket, pure joint freezing let contact force decay immediately
(`step 167` fell below the 0.5N success threshold) and the tip then drifted
laterally out of the success window. The action-response failure after success
is also polluted by this freeze, because the trace still recorded servo targets
while the actual action had been overwritten with a hold-current command.

Local follow-up fix:

```text
scripts/socket_insertion_servo_logic.py:
  - adds maintain_contact_preload to keep a tiny axial preload in the success
    window instead of switching to hold_z as soon as contact is above threshold

scripts/scripted_agent.py:
  - adds --socket-insertion-servo-maintain-contact-preload
  - when success-hold is active with socket insertion servo, lets the servo keep
    running in maintain-contact-preload mode instead of overwriting actions with
    hold-current joints
  - records post_success_hold_mode in trace rows/events

scripts/run_remote_joint_response_socket_insertion_servo_trace.sh:
  - defaults RCA_JOINT_RESPONSE_SOCKET_MAINTAIN_CONTACT_PRELOAD to 1

scripts/test_local_gates.py:
  - adds an offline negative/positive control for maintain-contact preload
  - checks the wrapper default and scripted-agent trace fields
```

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

git diff --check
  passed

./scripts/brev_paid_safety_status.sh
  status=SAFE_NO_VISIBLE_PAID_INSTANCE
```

Next paid action, if any: one short trace-only semantic validation with
maintain-contact preload enabled. It should still use the same cleanup/budget
plan and should not attempt viewport recording until the semantic validators
pass.

2026-06-21 maintain-contact-preload validation made semantic progress but still
failed closed:

```text
instance: rca-maintain-preload-vm / o5mt17y59
trace dir: artifacts/videos/trace_only/2026-06-21T18-01-55Z/
success_step: 166
success_hold: 5/5
success_hold_exit_step: 186
final_lateral: 0.0006703325198031962m
final_axial: 0.007980781607329845m
final_rot: 0.05415081977844238rad
max_contact_force_magnitude: 1.1637400388717651N at step 171
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Gate results:

```text
peg_video_candidate_check: PASS
trace_frame_alignment_check: PASS
action_response_check: FAIL
  bad_fraction=0.011235955056179775
  bad_steps=2
  worst step=178, cosine=-0.3543077607795342
final_contact_boundary_check: FAIL
  first_sustained_success_step=182
  unsafe_boundary_descent_count=4
  first unsafe boundary step=169
```

Interpretation: the previous contact-decay issue is fixed. The controller now
reaches semantic success and keeps the success window for five steps. The
remaining blocker is finer: while holding contact near the 8mm axial boundary,
`maintain_contact_preload` still used the normal preload step (`0.0002m`) and
normal XY correction. The boundary validator requires only micro-steps
(`<=0.00015m`) near this contact boundary and rejects the trace when a post-step
metric falls just outside the success axial tolerance.

Local follow-up fix:

```text
scripts/socket_insertion_servo_logic.py:
  - when maintain_contact_preload is active and contact is already ready, use
    boundary XY gain/clamp instead of the normal XY correction
  - cap the maintained preload at contact_boundary_step instead of
    contact_preload_step
  - expose maintained_contact_preload in the pure logic masks

scripts/test_local_gates.py:
  - checks that maintained contact uses a boundary micro-preload
  - checks that maintained contact does not continue applying normal XY
    corrections
```

Local validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

git diff --check
  passed

./scripts/brev_paid_safety_status.sh
  status=SAFE_NO_VISIBLE_PAID_INSTANCE
```

Next paid action, if any: one short trace-only semantic validation with the
maintained-contact micro-preload fix. Do not record a viewport video until all
four trace validators pass.

## 2026-06-21 Micro-Preload Trace Failed Boundary Hold

The follow-up validator-enabled trace ran on `rca-micro-preload-vm / 50vq3fdu3`
and cleanup was confirmed:

```text
trace dir: artifacts/videos/trace_only/2026-06-21T18-36-03Z/
success_step: 166
success_hold: 0/5
success_hold_exit_step: None
final_lateral: 0.0016100112115964293m
final_axial: 0.00805152952671051m
final_rot: 0.06043585017323494rad
max_contact_force_magnitude: 2.071620225906372N
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Gate results:

```text
action_response_check: PASS
peg_video_candidate_check: PASS
trace_frame_alignment_check: PASS
final_contact_boundary_check: FAIL
  first_sustained_success_step=None
  unsafe_boundary_descent_count=12
  first unsafe boundary step=282
```

Interpretation: the previous action-response failure is fixed. The remaining
failure is now narrower: at the axial boundary, measured contact force flickers
between low-but-real contact and task-success contact. Low-but-real contact
frames (`pre_contact_force_magnitude >= 0.25N` but `< 0.5N`) still used the
normal `contact_preload_step` (`0.0002m`), which pushed the post-step axial
metric just outside the 8mm success tolerance.

Local follow-up fix:

```text
scripts/socket_insertion_servo_logic.py:
  - low-but-real contact preload in the success axial window now uses boundary
    XY gain/clamp and contact_boundary_step
  - exposes contact_boundary_preload in the pure logic masks

scripts/scripted_agent.py:
  - records socket_insertion_servo_maintained_contact_preload
  - records socket_insertion_servo_contact_boundary_preload

scripts/test_local_gates.py:
  - covers low-but-real contact using boundary micro-preload
  - checks boundary preload disables normal XY corrections
```

Local validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

./scripts/brev_paid_safety_status.sh
  status=SAFE_NO_VISIBLE_PAID_INSTANCE
```

Next paid action, if any: one short trace-only semantic validation with the
low-contact boundary-preload fix. Still do not record a viewport video until
all four validators pass on the same trace.

## Main Files To Read First

- `README.md`
- `docs/phase2_il_contact_policy_plan.md`
- `docs/gpu_selection_policy.md`
- `docs/aws_isaac_launchable_runbook.md`
- `artifacts/analysis/launchable_probe_archive_summary_2026-05-26.md`
- `experiments/2026-05-18_phase2_contact_bc_smoke.md`
- `experiments/2026-05-19_phase2_contact_demo_coverage.md`
- `experiments/2026-05-20_phase2_bc_eval_trace_audit.md`
- `scripts/summarize_launchable_probe_archives.py`
- `scripts/select_reachable_approach_candidates.py`
- `scripts/run_guarded_phase2_gate.sh`
- `scripts/evaluate_contact_bc_policy.py`
- `scripts/extract_contact_demo_dataset.py`
- `scripts/run_phase2_contact_handoff_preload_direction_gate.sh`
