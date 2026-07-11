# Peg-In-Hole Success Video Audit - 2026-06-20

## Target

The requested deliverable is not just a viewport mp4. The target is a real
Isaac viewport video that shows a successful peg-in-hole insertion, backed by a
trace that proves the physical task succeeded.

Completion requires all of the following:

- `scripts/check_phase2_contact_gate.py` passes against the current archived
  Isaac contact-smoke log.
- A fresh trace from the same runtime/task reaches sustained insertion success:
  lateral, axial, rotation, and wall-filtered contact-force gates all true.
- `scripts/check_peg_in_hole_video_candidate.py <video_trace.json>` passes.
- The mp4 is real Isaac viewport/camera footage from the same successful
  semantic setup, not a log replay and not a failed motion recording.
- The paid instance is deleted and `brev ls instances --json --all` returns
  `{"workspaces": null}`.

## Current Evidence

The contact-smoke gate is no longer the blocker:

```text
canonical_log: artifacts/launchable_logs/contact_physics_smoke.log
source_payload_sha256: 5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f
python3 scripts/check_phase2_contact_gate.py
  PASS: validated contact-physics smoke evidence
```

This proves the physical shell is credible under Isaac: dynamic peg attached
through physics, wall-filtered contact force, blocked-motion response, no-clip
check, release check, and joint-integrity check.

The fresh video-candidate traces do not prove peg insertion. The best current
post-smoke trace is:

```text
trace: artifacts/videos/trace_only/2026-06-20T20-04-09Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-20T20-04-09Z/video_summary.json
checker: artifacts/videos/trace_only/2026-06-20T20-04-09Z/peg_video_candidate_check.log
```

Key metrics:

```text
success_step: null
final_success_rate: 0.0
best_lateral: 0.005550m
best_axial: 0.030969m
best_rot: 0.013093rad
max_contact_force_magnitude: 1.211N
```

The video-candidate checker rejects it:

```text
task_gate_pass=False
video_candidate_pass=False
fail: task gate never reached sustained configured success tolerances
fail: pose never reached stricter guide-clearance lateral tolerance
fail: trace does not show enough visible insertion descent from above the socket
```

The per-condition audit of the same trace shows:

```text
success thresholds: xy<=0.005m, axial<=0.045m for this scripted run,
rotation<=0.18rad, contact>=0.5N
xy_task_ready_steps: 0
xy_clearance_ready_steps: 0
axial_ready_steps: 1169
rot_ready_steps: 1200
contact_ready_steps: 4
task_success_steps: 0
video_pose_steps: 0
```

`scripts/analyze_contact_physics_validity.py` also reports no true engagement
for the three fresh traces:

```text
traces_analyzed: 3
traces_with_true_engagement: 0
verdict_counts:
  consistent: 2
  contact_signal_not_socket: 1
```

## Metric Sources

The metric sources are now explicit:

- Contact-smoke evidence comes from
  `artifacts/launchable_logs/contact_physics_smoke.log` and is validated by
  `scripts/check_phase2_contact_gate.py`.
- Task insertion success comes from
  `source/robot_contact_assembly_tasks/.../mdp/terminations.py`, using
  `tip_to_socket_position()` and `tip_to_socket_axis_error()` against the
  physical socket frame.
- Wall contact force comes from
  `peg_contact_force_magnitude()`, which reads wall-filtered
  `ContactSensor.data.force_matrix_w`.
- Video deliverable success is deliberately stricter than the task gate and is
  evaluated by `scripts/check_peg_in_hole_video_candidate.py`.

## What This Rules Out

Do not spend another paid run on these as the primary route:

- recording a viewport video before the trace passes the semantic checker;
- re-running `scripts/recreate_brev_and_record_peg_video_candidate.sh` with the
  same scripted controller family;
- treating the 2026-06-20 real viewport mp4 as insertion evidence;
- relaxing the checker so that contact or rotation alone counts as success.

The current failure is not a contact-smoke failure and not a video encoder
failure. It is a controller/task-formulation failure: the trace maintains
rotation and reaches shallow depth, but it never maintains the XY condition and
does not achieve true guide engagement.

## Next Structural Route

The next work should be local-first and structural:

1. Build or select a controller route that directly closes the physical
   socket-frame error near contact, rather than adding more flags to the old
   staged scripted/video wrapper.
2. Keep viewport recording disabled until the trace checker passes.
3. Use a short trace-only paid run only after the route has a clear budget,
   timeout, artifact plan, watchdog, and deletion plan.
4. If a trace passes, then run one viewport recording from the same semantic
   setup and validate the mp4 plus `video_trace.json`.

That route is now implemented as an explicit trace-only candidate:

```bash
scripts/run_remote_final_contact_servo_trace.sh <env-name> /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose
```

It enables `--final-contact-servo` in `scripts/scripted_agent.py` and switches
cached insertion back to live IK during polish with `--joint-cache-live-polish`.
The intent is to avoid replaying the same cached joint descent after the trace
has already reached the near-contact polish region.

The final-contact controller branch:

- start above the socket with the contact-smoke-validated physical task;
- servo in the socket frame on the measured physical tip error;
- keep orientation fixed once axis error is within tolerance;
- descend only while XY stays below the task threshold;
- use wall-filtered force only as a correction/contact condition, not as a
  substitute for geometric engagement;
- stop immediately if XY leaves the task gate or contact appears without true
  engagement.

Required negative control before calling the route trustworthy:

- the same trace checker must fail when the guide walls are parked/disabled, or
  the contact metric must materially change. If contact stays meaningful when
  the guide walls are not present, the metric is not proving peg/socket contact.

## Final-Contact Trace Result

The first short validation of this route ran on the official AWS Isaac
Launchable environment and failed closed:

```text
trace: artifacts/videos/trace_only/2026-06-20T20-56-43Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-20T20-56-43Z/video_summary.json
best_lateral: 0.006714m
best_axial: 0.030362m
best_rot: 0.006569rad
max_contact_force_magnitude: 1.352N
task_gate_pass: False
video_candidate_pass: False
```

The important result is not another generic near miss. The summary recorded:

```text
final_contact_servo: true
final_contact_servo_step_count: 0
final_contact_servo_first_step: null
final_contact_servo_entry_count: 0
```

The trace shows `polish_state=True` throughout but `insert_mask=False`
throughout, so the original final-contact entry condition
`insert_mask & polish_state & thresholds` could never become true. The local
controller has been patched to let the final-contact phase operate from
`insert_mask | polish_state` while keeping the measured XY/Z/rotation entry and
exit gates.

The patched branch was then validated once:

```text
trace: artifacts/videos/trace_only/2026-06-20T21-34-52Z/video_trace.json
best_lateral: 0.001174m
best_axial: 0.000013m
best_rot: 0.010770rad
max_contact_force_magnitude: 8.715N
final_contact_servo_step_count: 701
task_gate_pass: False
video_candidate_pass: False
```

This is the first strong near-success after the contact-smoke gate. The branch
now enters final-contact-servo and can hit each individual condition, but the
strict simultaneous gate is still not sustained. The nearest simultaneous
window was:

```text
step: 787
phase: final-contact-servo
lateral: 0.0057m
axial: 0.0080m
rotation: 0.0190rad
contact: 1.242N
```

That miss is approximately `0.7mm` outside the task XY tolerance. After this
window, XY keeps improving, but axial error grows again. Trace inspection shows
the legacy final-contact controller still mixes a debug physical-tip transform
for XY with a world-Z descent. A follow-up local change added
`--final-contact-servo-metric-error`, which drives XYZ corrections from
`mdp.tip_to_socket_position()`, the same signed socket-frame metric used by the
success checker. That full metric-error hypothesis was then tested once and
rejected:

```text
trace: artifacts/videos/trace_only/2026-06-20T22-10-50Z/video_trace.json
best_lateral: 0.007921m
best_axial: 0.031092m
best_rot: 0.008429rad
max_contact_force_magnitude: 1.066N
final_contact_servo_step_count: 26
task_gate_pass: False
video_candidate_pass: False
```

The regression is diagnostic: full metric-error XY made the controller leave
the final-contact servo almost immediately, with `success_xy_ready=0` and
`success_axial_ready=0`. A narrower metric-Z-only diagnostic was then tried and
also failed before the controller/source mismatch was found. The remote
final-contact trace wrapper now keeps metric-Z off by default; set
`RCA_FINAL_CONTACT_SERVO_METRIC_Z=1` only for an explicit one-shot diagnostic.

After the scripted physical-tip source was corrected to prefer the articulated
`Peg` body, the canonical-tip/no-metric-Z route was rerun:

```text
trace: artifacts/videos/trace_only/2026-06-21T00-34-31Z/video_trace.json
best_lateral: 0.001173m
best_axial: 0.000015m
best_rot: 0.010770rad
max_contact_force_magnitude: 8.714N
task_gate_pass: False
video_candidate_pass: False
```

The closest simultaneous step remained about `0.7mm` outside the XY gate; later
steps moved XY inside the gate while axial error moved back out. This closes
the no-metric-Z canonical-tip route as a success-video candidate.

## Current Decision

The project has moved past "is the contact shell real?" and is now blocked on
"can the controller produce a physically valid insertion trajectory?"

The goal remains active, but the success video is not available yet. The next
paid action should not be a video run. The hold-Z trace-only validation
(`artifacts/videos/trace_only/2026-06-21T01-17-49Z/video_trace.json`) failed the
semantic checker: axial stayed inside the success window late in the run, but
`success_xy_ready` never became true and the final task lateral error remained
about `9.7mm`. That diagnosed a controller-source mismatch, so the next
local-first candidate was `--final-contact-servo-metric-xy` plus hold-Z.

That candidate also failed:

```text
artifact: artifacts/videos/trace_only/2026-06-21T01-56-21Z/video_trace.json
result: peg-video-candidate FAIL
best_lateral: 0.000550m
best_axial: 0.029598m
best_rot: 0.009174rad
max_contact_force_magnitude: 11.841N
success_xy_ready: 409 steps
success_axial_ready: 0 steps
success_contact_ready: 173 steps, first 603, last 785
success: 0 steps
```

Metric-XY solved the lateral-source mismatch, but it did not solve insertion:
axial depth never reached the task gate, contact readiness disappeared before
the late lateral success window, and orientation drifted past the success gate.
Do not record a viewport video from this route, and do not keep spending on
near-duplicate final-contact-servo traces. The next project step should change
the insertion/control formulation itself and include a semantic smoke plus a
negative control before any further paid run.

## Local Next Candidate

The next local candidate is now implemented as `--socket-insertion-servo`. It is
not a video route yet. Its command rule is intentionally staged:

- task-metric socket-frame XY is corrected on every active step,
- socket-axis descent is allowed only after XY and rotation are ready,
- orientation moves by a stateful quaternion waypoint toward the socket target,
- a small preload is used only when axial depth is ready but contact evidence is
  missing.

The pure command rule is in `scripts/socket_insertion_servo_logic.py` and the
negative controls are part of `scripts/test_local_gates.py`; local quality
passes. The prepared trace-only wrapper is
`scripts/recreate_brev_and_run_socket_insertion_servo_trace.sh`. Use it only for
one guarded paid trace after Brev safety is green. A viewport video remains
blocked until that trace passes the semantic checker.

## 2026-06-21 Socket-Insertion Servo Result

The guarded AWS trace-only validation was run once:

```text
env: rca-socket-insertion-servo-vm
instance_id: 4kek9u5dj
trace: artifacts/videos/trace_only/2026-06-21T02-49-00Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-21T02-49-00Z/video_summary.json
checker: artifacts/videos/trace_only/2026-06-21T02-49-00Z/peg_video_candidate_check.log
result: peg-video-candidate FAIL
best_lateral: 0.010245m
best_axial: 0.046755m
best_rot: 0.001505rad
max_contact_force_magnitude: 0.0N
success_xy_ready: 0 steps
success_axial_ready: 0 steps
success_contact_ready: 0 steps
socket_insertion_servo_active: 26 steps, first 0, last 80
```

This closes `--socket-insertion-servo` as a video route in its current form. It
did not reach contact, did not descend far enough, and did not satisfy the task
XY gate. The trace shows a deeper structural mismatch: the servo's own
socket-frame metric considered XY ready at step 0, while the task gate still
reported about `10mm` lateral error. After that, the servo's XY correction moved
the task lateral/rotation farther from the gate; it exited around step 81 and
the old polish phase continued drifting away.

The cleanup completed successfully after artifact pullback:

```text
brev ls instances --json --all: {"workspaces": null}
scripts/brev_paid_safety_status.sh: SAFE_NO_VISIBLE_PAID_INSTANCE
watchdog_processes: none
```

Do not record a viewport video from this trace, and do not run another paid
socket-servo attempt unchanged. The next useful work is local-first and
structural: audit/reconcile the task gate frame, physical peg tip frame, and
servo socket-frame correction source, then replace the final insertion phase
ownership so one controller owns XY, Z, orientation, and contact together.

## 2026-06-21 Frame/Metric Audit

The latest trace was audited with `scripts/audit_trace_frame_alignment.py`:

```text
trace: artifacts/videos/trace_only/2026-06-21T02-49-00Z/video_trace.json
same_step_metric_lateral_gap_max: 0.0102446635
next_step_metric_lateral_gap_max: 0.0000000032
metric_world_to_physical_proxy_gap_mean: 0.0790807574m
socket_offset_rows: 26
socket_offset_wxyz_closer: 0
socket_offset_legacy_closer: 26
result: FAIL
```

This explains why the route should not be retried unchanged. The trace mixed
pre-step control fields with post-step outcome metrics, so apparent same-row
contradictions were a time-base artifact. More importantly, socket-frame servo
offsets matched the legacy XYZW quaternion rotation helper, while the task MDP
and success gate use Isaac Lab WXYZ quaternions. The recorded action-frame
physical-tip proxy was also about `8cm` from the task metric tip, so it is not a
valid substitute for task success evidence. The local fix is to keep
socket-frame command rotations on the WXYZ path and require the frame audit to
pass before considering any new paid trace.

## 2026-06-21 Joint-Response Socket-Insertion Follow-Up

After the frame fix, the next guarded route calibrated the empirical
`JointPositionAction` response and used that response matrix for socket
insertion. This closed the previous action-interface ambiguity:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T10-21-39Z/seed_42.json
down_check: pass_gate=True cosine=0.9999999999999946
up_check: pass_gate=True cosine=0.9999999999999946
```

The guarded trace on `rca-joint-response-socket-servo-vm` / `3evn0rn85`
produced the strongest socket-servo evidence so far:

```text
trace: artifacts/videos/trace_only/2026-06-21T10-22-58Z/video_trace.json
summary: artifacts/videos/trace_only/2026-06-21T10-22-58Z/video_summary.json
action_response_check: PASS bad_steps=0/101
trace_frame_alignment_check: PASS
peg_video_candidate_check: FAIL
initial_lateral: 0.000158m
best_lateral: 0.000158m
initial_axial: 0.049638m
best_axial: 0.008006m
best_rot: 0.000488rad
max_contact_force_magnitude: 1.626N
```

This is a meaningful improvement, but still not success. It reached the
near-boundary region with good lateral alignment and real contact force, then
lost stability just after the boundary. The event trace records the pop at
step `101`: lateral `0.031609m`, axial `0.017230m`, rotation `0.066278rad`.

A follow-up softened run on `rca-joint-response-socket-soft-vm` / `lkllxgfml`
reduced Z/preload steps and held rotation when already aligned, but did not
produce a semantic trace:

```text
trace dir: artifacts/videos/trace_only/2026-06-21T10-51-20Z/
trace_events: control_loop_setup, control_loop_enter, step_begin=0 only
video_summary.json: missing
cleanup: brev ls instances --json --all returned {"workspaces": null}
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

Do not interpret this second run as an insertion-controller failure; it is a
runtime/execution failure before the first completed step. The next paid action
should remain blocked until a local deterministic final-contact diagnostic
exists around the 8mm axial boundary, including a negative control for socket
contact. A viewport video is still blocked until
`scripts/check_peg_in_hole_video_candidate.py` passes on a fresh trace.

## 2026-06-21 Contact-Boundary Diagnostic

The local final-contact boundary diagnostic now exists:

```bash
python3 scripts/check_final_contact_boundary_diagnostic.py <video_trace.json>
```

It is a pre-video safety gate. It fails traces where the controller reaches the
near-boundary region with XY/rotation/contact ready but continues using a normal
descent step, or where the next recorded row pops laterally/axially away from
the socket. It also supports a negative trace via `--negative-trace-json`.

The known joint-response trace is rejected for the exact failure mode we need
to eliminate:

```text
trace: artifacts/videos/trace_only/2026-06-21T10-22-58Z/video_trace.json
unsafe_boundary_descent_count: 2
pop_event_count: 1
first_unsafe_boundary_descent: step 99, axial 0.008118m, offset_z -0.001500m
first_pop_event: step 100 -> 101, lateral 0.000790m -> 0.031609m, axial 0.008006m -> 0.017230m
```

`scripts/socket_insertion_servo_logic.py` now has a near-contact mode that
switches from normal descent to a micro-step when contact is already present
within the axial boundary band:

```text
contact_boundary_tolerance: 0.0010m
contact_boundary_step: 0.00005m
```

This is not a success claim. It is the next structural attempt to prevent the
observed boundary pop. The next remote trace, if run, must still pass the
boundary diagnostic, the action-response checker, the frame-alignment checker,
and finally `scripts/check_peg_in_hole_video_candidate.py` before any video
recording is worth spending on.

## 2026-06-21 Boundary Trace Attempt

A follow-up paid trace using the boundary micro-step controller did not reach
the semantic validators:

```text
instance: rca-joint-response-boundary-vm / o69gah0k8
calibration: artifacts/calibration/joint_position_action/2026-06-21T11-36-56Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T11-38-02Z/
video_summary.json: missing
video_trace.json: missing
trace_events: control_loop_setup, control_loop_enter, step_begin=0 only
```

This is not evidence for or against the boundary micro-step controller. The run
entered the scripted loop but did not complete step 0, so it is a runtime
observability failure. The code has been hardened so future trace-only runs
default to Python traceback watchdogs and write fine-grained `step_phase` JSONL
events for the first few steps. The next remote action should be a short
diagnostic trace to locate the first-step stall, not a viewport video.

## 2026-06-21 Step-0 Diagnostic Result

The short diagnostic trace ran on `rca-step0-diagnostic-vm` / `8szk4nfe5` and
was cleaned up successfully:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T12-14-25Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T12-15-37Z/
trace_events: reached metrics_ready on step 0
video_summary.json: missing
video_trace.json: missing
cleanup: target disappeared
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

The last event was:

```text
{"event": "step_phase", "phase": "metrics_ready", "step": 0}
```

This narrows the missing-artifact failure to the action/phase computation block
between `metrics_ready` and `before_env_step`. It is not a failure of Isaac
startup, pose sampling, target-pose construction, insertion metrics,
`tip_to_socket_position`, or pre-step contact-force reads.

The local diagnostic fix after this run:

```text
scripts/scripted_agent.py
  partial zero-row summary/trace writer
  last_step_started / last_trace_phase in partial summaries
  fine-grained phase markers through ready masks, approach/insert state,
  depth-rotation polish, insert target updates, polish/settle, final-contact
  servo, socket-insertion servo, and control-action solve

./scripts/run_local_quality_checks.sh
  passed
```

Next action should stay diagnostic-first. A new paid trace is only useful if it
uses the new zero-row partial artifacts and phase markers; it should be short
and should stop after locating or clearing the `metrics_ready -> before_env_step`
gap. Do not record a viewport video or begin RL/IL/VLM work until the semantic
trace path is stable again and `scripts/check_peg_in_hole_video_candidate.py`
passes.

## 2026-06-21 Socket-Servo Command Diagnostic Result

The next short diagnostic trace ran on `rca-step0-phase-diagnostic-vm` /
`oliz8h0yt`, calibrated joint-response successfully, and cleaned up with no
visible Brev instance left:

```text
calibration: artifacts/calibration/joint_position_action/2026-06-21T12-52-12Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T12-53-30Z/
trace_events: reached step 0 phase before_socket_insertion_servo_command
video_summary.json: missing
video_trace.json: missing
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

The last event was:

```text
{"event": "step_phase", "phase": "before_socket_insertion_servo_command", "step": 0}
```

This run proves the previous stall is inside the socket-insertion-servo command
block, before the first trace row is appended. It does not prove the controller
is physically failing or succeeding.

The local diagnostic fix after this run:

```text
scripts/scripted_agent.py
  SIGTERM/SIGINT partial-artifact handler
  finalized partial artifacts to avoid duplicate atexit writes
  sub-phase markers inside socket-insertion-servo command computation

scripts/test_local_gates.py
  static guards for the signal handlers and sub-phase markers

./scripts/run_local_quality_checks.sh
  passed
```

The next paid trace should remain diagnostic-only and short. The expected
evidence is either a signal-safe partial `video_summary.json` naming the exact
last phase, or a real `video_trace.json` that can be checked by the existing
semantic validators. A viewport video is still blocked until the trace writes
success evidence and passes `scripts/check_peg_in_hole_video_candidate.py`.

## 2026-06-21 Socket-Servo Metric-Reduction Diagnostic

The follow-up diagnostic used the sub-phase markers above and narrowed the
missing-artifact failure to a summary-only CUDA reduction:

```text
instance: rca-socket-command-diagnostic-vm / iw1712l9s
calibration: artifacts/calibration/joint_position_action/2026-06-21T13-23-02Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T13-24-14Z/
last event: {"event": "step_phase", "phase": "before_socket_insertion_servo_metric_reductions", "step": 0}
video_summary.json: missing
video_trace.json: missing
brev safety: SAFE_NO_VISIBLE_PAID_INSTANCE
```

This is useful evidence: socket-insertion-servo config, offset computation,
socket-frame offset rotation, target update, and quaternion update all completed
for step 0. The stall is in the diagnostic stats update that computed masked
CUDA `max/min` scalar reductions for summary fields, before the first `env.step`.

Local fix:

```text
scripts/scripted_agent.py
  skip socket-insertion-servo command-block metric reductions
  keep the control command path unchanged
  emit skipped_socket_insertion_servo_metric_reductions

scripts/test_local_gates.py
  require the skip marker and trace-row rationale
```

The next remote check should be another short trace whose only required success
is reaching `before_env_step`, `after_env_step`, and at least one
`trace_row_appended` event. A longer semantic attempt or viewport video is still
premature until that happens.

## 2026-06-21 Step-Through Trace Recovery Diagnostic

The follow-up short paid diagnostic used `RCA_ISAACLAB_RUNTIME_PROFILE=trace-only`
and a 5-step joint-response socket wrapper run. It completed the narrow
step-through gate:

```text
instance: rca-joint-response-step5-vm / 3meqf97mn
calibration: artifacts/calibration/joint_position_action/2026-06-21T14-00-29Z/seed_42.json
trace dir: artifacts/videos/trace_only/2026-06-21T14-01-40Z/
trace rows: 5
last events: before_env_step, after_env_step, trace_row_appended, final_artifacts_written
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

This proves the earlier `before_socket_insertion_servo_metric_reductions` stall
has been cleared. It does not prove insertion success: the run was deliberately
only 5 steps, peg-video-candidate validation was disabled, and all trace rows
remained in `settle` with `success_step=null`.

The run also showed that the current runtime install is still too broad for
cheap repeated diagnostics. The trace-only profile was propagated correctly and
skipped the explicit optional install block, but the IsaacLab install command
still installed many broad source packages, including RL/video dependencies,
before the trace could run. Do not treat trace-only profile as a complete
cold-start cost fix.

Next technical step: after local gates pass and Brev safety is green, run one
longer semantic trace with the same joint-response socket route and validators
enabled. Only if that trace passes `scripts/check_peg_in_hole_video_candidate.py`
should a viewport video be recorded.

## 2026-06-21 Long Semantic Trace: Near-Miss, Not Video Candidate

The longer semantic trace was intentionally interrupted after it produced enough
evidence that it was not trending toward a success video:

```text
instance: rca-joint-response-semantic-vm / bk3cajkvf
trace dir: artifacts/videos/trace_only/2026-06-21T14-31-43Z/
steps recorded: 489 / 1200 requested
success_step: null
final_success_rate: 0.0
best_axial: 0.0080797076m at step 182
final_axial: 0.0087215072m
best_lateral: 0.0001472154m
final_lateral: 0.0005120616m
max_contact_force_magnitude: 1.3475245
last_phase: settle
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

This run must not be promoted to a peg-in-hole video candidate. It shows contact
and very small lateral error, but it never crossed the axial success threshold
of 0.008m. The best point missed by roughly 0.08mm, then the trace regressed to
about 8.72mm axial error.

The trace exposed one concrete implementation issue: the socket insertion
servo's rotation sub-mask aliased the main activation mask and was then modified
in-place. That made `socket_insertion_servo_state=True` coexist with
`socket_insertion_servo_active=False` in trace rows and made downstream
servo-state evidence unreliable. The local fix changes the rotation sub-mask to
`socket_insertion_servo_mask.clone()` and adds a local gate in
`scripts/test_local_gates.py`.

The remaining hypothesis is near-contact boundary behavior, not missing
approach or missing contact. The run used
`--socket-insertion-servo-contact-boundary-step 0.00005`; at this scale the
controller was too conservative to reliably cross the final 0.08mm while
contact force flickered.

Local follow-up changed the boundary micro-step default to 0.00015m, fixed the
socket-servo mask alias, and kept the safety property that boundary z is clipped
to the remaining `metric_z - success_z_tol` rather than blindly applying the
full step. `./scripts/run_local_quality_checks.sh` and `git diff --check` both
passed after the change. The next paid action should be a short
validator-enabled semantic trace only; viewport recording is still blocked until
that trace proves sustained peg-in-hole success.

## 2026-06-21 Boundary-Step Validation Failed Closed

The validator-enabled trace for the mask-clone fix plus `0.00015m`
contact-boundary micro-step ran on the official AWS Isaac Launchable runtime and
failed closed:

```text
instance: rca-boundary-step015-vm / t7ree4ri7
trace dir: artifacts/videos/trace_only/2026-06-21T15-12-20Z/
steps recorded: 500
success_step: null
final_success_rate: 0.0
best_axial: 0.0080776298m at step 172
final_axial: 0.0087595545m
best_lateral: 0.0001472154m
best_rot: 0.0003452670rad
max_contact_force_magnitude: 1.2441853N
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

The near-miss did not improve relative to the previous semantic trace. Contact
is real and frame alignment still passes, but the controller did not produce a
valid insertion candidate:

```text
action_response_check: FAIL, bad_steps=47, worst cosine=-0.7645606147
final_contact_boundary_check: FAIL, unsafe_boundary_descent_count=35
peg_video_candidate_check: FAIL, task_gate_pass=False, video_candidate_pass=False
trace_frame_alignment_check: PASS
```

This rules out the simple hypothesis that the remaining problem is just an
undersized boundary step. The next blocker is the contact-boundary control
semantics: after contact near the axial threshold, the controller can still use
normal `-0.0005m` descent rows and later command/response directions become
unreliable in socket-insertion-servo. Do not rerun this branch unchanged and do
not record viewport video from it. The next work should be local-first command
semantics and boundary-phase selection diagnostics; another paid trace should
wait until those local checks predict a different validator outcome.

## 2026-06-21 Local Boundary-Control Fix

The local controller has now been changed in the direction suggested by the
failed trace:

- keep the task success contact gate unchanged at `0.5N`;
- use a separate decision-time `contact_boundary_min_force=0.25N` only inside
  the near-axial contact-boundary band, so force flicker does not repeatedly
  drop the controller back into normal descent;
- freeze XY during contact-boundary micro-steps by default
  (`contact_boundary_xy_gain=0`, `contact_boundary_xy_clamp=0`), because the
  latest trace already had sub-millimeter lateral error and the lateral scrub
  dominated the command vector after contact;
- make the boundary diagnostic prefer `pre_contact_force_magnitude` when it is
  present, because that is the contact value available when the controller
  chooses the next action.

Offline replay of the latest failed trace through the pure servo rule confirms
the intended local effect, without claiming task success:

```text
old-like logic: near_rows=345, boundary=307, normal_descend=38, unsafe=38, boundary_xy_nonzero=307
new logic:      near_rows=345, boundary=341, normal_descend=4,  unsafe=4,  boundary_xy_nonzero=0
```

Local validation passed:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

git diff --check
  passed
```

This is still not a peg-in-hole success and not a video candidate. It only makes
one short follow-up semantic trace technically defensible after Brev safety is
green. Viewport video remains blocked until the trace passes
`scripts/check_peg_in_hole_video_candidate.py`.

## 2026-06-21 Boundary-Freeze Trace Exposed Geometry-Only Reset

The follow-up validator trace ran with the local boundary-contact/XY-freeze
defaults on the official AWS Isaac Launchable runtime and failed closed:

```text
instance: rca-boundary-freezexy-vm / ii96h00e2
trace dir: artifacts/videos/trace_only/2026-06-21T15-59-31Z/
success_step: null
final_success_rate: 0.0
best_axial: 0.008009647950530052m at step 280
final_axial: 0.008044378831982613m
best_lateral: 0.00014721538173034787m
best_rot: 0.0003452669770922512rad
max_contact_force_magnitude: 1.900056004524231N at step 266
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Validators:

```text
action_response_check: FAIL, bad_steps=1, worst step=396
final_contact_boundary_check: FAIL, unsafe_boundary_descent_count=1, pop_event_count=2
peg_video_candidate_check: FAIL
trace_frame_alignment_check: PASS
```

The important new evidence is the step 280 to 281 transition. At step 280 the
trace was only about 0.01mm outside the axial tolerance and had real contact,
but by step 281 the arm had jumped toward a reset/default posture. The raw
joint target for step 281 was tiny, while `post_arm_joint_pos` changed
dramatically, so this is not explained by the socket-servo offset itself.

The likely structural cause is that the task's built-in
`terminations.insertion_success` is geometry-only. It does not require contact
force, while the video/semantic gate does. This means the environment can reset
near the geometric threshold before the contact-aware validator has a sustained
success window.

Local fix:

```text
scripts/scripted_agent.py:
  - disables env_cfg.terminations.insertion_success by default for scripted validation
  - provides --keep-insertion-success-termination to opt back into old behavior
  - records insertion_success_termination_disabled in trace rows and summary

scripts/test_local_gates.py:
  - checks that this guard remains present
```

Validation after the fix:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
  [gate-tests] passed

PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
  [local-quality] passed

git diff --check
  passed
```

This still does not authorize viewport recording. The next paid run should be
another short semantic trace only, with internal insertion-success termination
disabled and contact-aware validators as the source of truth.

## 2026-06-21 Disabled-Reset Trace Reached First Semantic Success

The next validator-enabled trace ran with `env_cfg.terminations.insertion_success`
disabled by default and failed closed:

```text
instance: rca-disable-reset-vm / 8us3zypas
trace dir: artifacts/videos/trace_only/2026-06-21T16-45-23Z/
success_step: 166
final_success_rate: 1.0
best_axial: 0.007974937558174133m at step 166
best_lateral: 0.00014721538173034787m
final_lateral: 0.0009611804271116853m
final_rot: 0.05461684986948967rad
max_contact_force_magnitude: 0.8971468210220337N
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Good evidence:

```text
action_response_check: PASS
trace_frame_alignment_check: PASS
unsafe_boundary_descent_count: 0
pop_event_count: 0
```

Remaining failure:

```text
peg_video_candidate_check: FAIL
  fail: pose never reached stricter guide-clearance lateral tolerance

final_contact_boundary_check: FAIL
  fail: no sustained task-success window at the contact boundary
```

This is not a viewport-video success. The trace reached a first contact-aware
success row, but `scripts/scripted_agent.py` exited immediately on that row.
Because the strict video and boundary validators require a sustained five-step
window, the run had no chance to satisfy the final gate.

Local follow-up fix:

```text
scripts/scripted_agent.py:
  - adds --success-hold-steps
  - after first success, holds current joint targets for the requested
    consecutive success window instead of breaking immediately
  - records success_hold_count, success_hold_exit_step, and
    post_success_hold_step_count

scripts/run_remote_joint_response_socket_insertion_servo_trace.sh:
  - defaults RCA_JOINT_RESPONSE_SOCKET_SUCCESS_HOLD_STEPS to 5
```

Local validation passed:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/scripted_agent.py scripts/test_local_gates.py
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
```

Next action remains a short trace-only semantic validation. Do not record a
viewport video until the sustained-window validators pass.

## 2026-06-21 Success-Hold Trace Exposed Contact Decay Under Joint Freeze

The short follow-up trace with `--success-hold-steps 5` ran on
`rca-success-hold-vm / nv7l10123` and cleaned up successfully:

```text
trace dir: artifacts/videos/trace_only/2026-06-21T17-16-33Z/
success_step: 166
success_hold: 0/5
final_lateral: 0.007539698854088783m
final_axial: 0.0044609056785702705m
final_rot: 0.049713972955942154rad
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

Gate results:

```text
peg_video_candidate_check: PASS
trace_frame_alignment_check: PASS
action_response_check: FAIL
final_contact_boundary_check: FAIL
```

The important trace pattern is that step 166 reached the semantic success gate,
but step 167 already lost the required contact force. Pure post-success
joint-target freezing does not keep the peg loaded against the socket; contact
force decays and the tip later drifts laterally outside the success window.

Local fix after this trace:

```text
scripts/socket_insertion_servo_logic.py:
  - adds maintain_contact_preload so the socket-frame servo can keep a small
    preload inside the axial success window

scripts/scripted_agent.py:
  - adds --socket-insertion-servo-maintain-contact-preload
  - success-hold no longer overwrites socket-servo actions with hold-current
    joints when maintain-contact preload is enabled
  - records post_success_hold_mode

scripts/run_remote_joint_response_socket_insertion_servo_trace.sh:
  - enables RCA_JOINT_RESPONSE_SOCKET_MAINTAIN_CONTACT_PRELOAD by default
```

Local validation passed:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
git diff --check
./scripts/brev_paid_safety_status.sh
```

Next action remains trace-only semantic validation, not viewport recording.

## 2026-06-21 Maintain-Preload Trace Reached Sustained Success

The next validator-enabled trace ran on `rca-maintain-preload-vm / o5mt17y59`
and cleaned up successfully:

```text
trace dir: artifacts/videos/trace_only/2026-06-21T18-01-55Z/
success_step: 166
success_hold: 5/5
success_hold_exit_step: 186
final_lateral: 0.0006703325198031962m
final_axial: 0.007980781607329845m
final_rot: 0.05415081977844238rad
max_contact_force_magnitude: 1.1637400388717651N
cleanup: workspaces null; SAFE_NO_VISIBLE_PAID_INSTANCE
```

This is real progress over the previous success-hold run: the trace now reaches
the semantic insertion gate and sustains it for the requested five-step hold.
The video-candidate checker and frame-alignment audit passed:

```text
peg_video_candidate_check: PASS
trace_frame_alignment_check: PASS
```

The run still failed closed because the stricter control-quality validators
caught residual contact-boundary behavior:

```text
action_response_check: FAIL
  bad_fraction=0.011235955056179775
  bad_steps=2

final_contact_boundary_check: FAIL
  first_sustained_success_step=182
  unsafe_boundary_descent_count=4
  fail: controller used a normal descent step after contact near the axial boundary
```

Interpretation: the project is no longer blocked at "cannot reach insertion
success" for this trace seed. The current blocker is now the contact-boundary
hold policy. While maintaining contact, the controller still issued a
`0.0002m` preload and normal XY correction; the boundary validator requires
micro-step behavior (`<=0.00015m`) once contact is present near the axial
success threshold.

Local follow-up fix:

```text
scripts/socket_insertion_servo_logic.py:
  - maintained contact preload now uses contact-boundary XY gain/clamp
  - maintained contact preload is capped at contact_boundary_step
  - exposes maintained_contact_preload in logic masks

scripts/test_local_gates.py:
  - covers boundary micro-preload during maintained contact
  - covers disabling normal XY correction during maintained contact
```

Local validation passed:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
git diff --check
./scripts/brev_paid_safety_status.sh
```

Next action remains a short trace-only semantic validation. A real viewport
recording should wait until action-response, final-contact-boundary,
peg-video-candidate, and frame-alignment validators all pass on the same trace.

## 2026-06-21 Micro-Preload Trace Update

The follow-up trace ran on `rca-micro-preload-vm / 50vq3fdu3` and cleaned up
successfully:

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

Validator result:

```text
action_response_check: PASS
peg_video_candidate_check: PASS
trace_frame_alignment_check: PASS
final_contact_boundary_check: FAIL
  first_sustained_success_step=None
  unsafe_boundary_descent_count=12
  first unsafe boundary step=282
```

This means the trace is not yet valid evidence for a successful peg-in-hole
video. It gets close and has real contact, but it does not sustain the strict
task-success window at the axial boundary. The remaining bug is low-but-real
contact preload: when `pre_contact_force_magnitude` is above the boundary
threshold but below the task-success threshold, the controller still used the
normal preload step instead of the micro boundary step.

Local fix after this trace:

```text
scripts/socket_insertion_servo_logic.py:
  - low-but-real contact preload now uses contact-boundary XY gain/clamp
  - low-but-real contact preload is capped at contact_boundary_step
  - exposes contact_boundary_preload in pure logic masks

scripts/scripted_agent.py:
  - logs socket_insertion_servo_maintained_contact_preload
  - logs socket_insertion_servo_contact_boundary_preload

scripts/test_local_gates.py:
  - covers low-but-real contact in the axial success window
  - checks boundary preload does not keep normal XY correction
```

Local validation passed:

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_local_gates.py
PYTHONDONTWRITEBYTECODE=1 ./scripts/run_local_quality_checks.sh
./scripts/brev_paid_safety_status.sh
```

The next remote step should remain trace-only. Do not spend on viewport
recording until the same trace passes action-response, final-contact-boundary,
peg-video-candidate, and frame-alignment together.
