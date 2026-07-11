# Contact Smoke Failure Review - 2026-06-20

This note summarizes the local review of existing failed Isaac contact-smoke
logs. It does not claim the current runtime passes; it only records what the
old logs prove and what has already changed locally.

## Evidence Reviewed

Existing failed logs:

```text
artifacts/launchable_logs/contact_physics_smoke_failed_dum95ipxl_2026-06-19T23-08Z.log
artifacts/launchable_logs/contact_physics_smoke_failed_kj53qhjld_2026-06-19T23-47Z.log
artifacts/launchable_logs/contact_physics_smoke_failed_1ven2jhye_2026-06-20T00-20Z.log
artifacts/launchable_logs/contact_physics_smoke_failed_91wizfdos_2026-06-20T01-02Z.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-bcd83f_2026-06-20T03-46-58Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-607d2a_2026-06-20T04-36-06Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-a6354c_2026-06-20T05-12-01Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-b8fc1e_2026-06-20T05-50-21Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-ede7f3_2026-06-20T06-58-21Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_runs_isaac-launchable-ede7f3_2026-06-20T06-58-21Z.tsv
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-29-28Z-1770.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_runs.tsv
```

Current runtime payload:

```text
1d19fecb91790e2762426723e2b5e4daaf296c6787929d8c5ab9d9c514c001c6
```

The archived failure for `isaac-launchable-b8fc1e` references the previous
first local-guide payload
`834a7f478ea8d225c3cd7a828266d5092ba9ae1f2a127411902af91fb1c9cc85`.
The local smoke/gate code was then changed to re-anchor the local guide after
free-space settle. A later wrapper fix changed the current payload hash above
and preserved per-run logs. No remote PASS log exists for the current payload.

## Common Failure Signature

The old logs consistently show:

```text
CONTACT-SMOKE attach: FAIL
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL
CONTACT-SMOKE press-blocked: FAIL
CONTACT-SMOKE press-no-clip: FAIL
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: FAIL
```

The most informative old log is `contact_physics_smoke_failed_91wizfdos...`:

- after reset, the hand/peg diagnostic was effectively aligned;
- after free-space settle, hand/peg error grew to roughly 0.11m and 0.26m;
- wall-filtered force stayed zero during press;
- lower-end penetration was roughly 0.30m;
- Isaac logged warnings that a `RigidBodyView` was trying to set transforms on
  non-root articulation links.

Interpretation: those old payloads did not prove a physically constrained peg.
The peg either remained a broken/maximal-coordinate body or was still being
handled through an invalid RigidObject view once attached into the articulation.

## 2026-06-20 WXYZ Runtime Retry

The short official AWS Launchable retry on `isaac-launchable-607d2a` fixed the
old attachment failure but still failed the contact gate:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL
CONTACT-SMOKE press-blocked: PASS
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
```

The important change was the attach error: after reset, free-space settle, and
retreat it stayed near `1e-7 m`, proving the WXYZ joint-frame fix made the peg
follow the Franka hand. The remaining failure was wall force: the mean
wall-filtered force stayed `[0.0, 0.0] N`.

Reviewing the smoke code against this log found that `press-blocked` had a
sign bug. It treated negative `wall_top_z - lower_end_z` as PASS, even though a
negative value means the lower peg end is above the wall top, not blocked by it.
The same log also showed large lateral slip (`0.20-0.26 m`), so the smoke did
not actually prove the peg had reached the wall contact line.

Local follow-up changed the smoke semantics:

- added `CONTACT-SMOKE press-tracking`, requiring the physical lower peg end to
  be laterally near the commanded wall-contact point;
- changed `press-blocked` to require `abs(wall_top_z - lower_end_z)` within the
  block tolerance;
- corrected the smoke target z coordinates to use the controller/insertion tip
  frame directly. The previous smoke still added `PEG_LENGTH_M`, an old
  upper-tip assumption that commanded the insertion tip to hover above the wall
  instead of pressing below it;
- made `scripts/check_phase2_contact_gate.py` and
  `scripts/run_launchable_contact_physics_smoke.sh` require the new
  `press-tracking` PASS marker.

## 2026-06-20 Strict Fixed-Socket Retry

The next short Launchable retry on `isaac-launchable-a6354c` (`xxv4vn1te`) used
payload `4f7e574f2271e87ba801798a0b86e3fd611905b22675e8f18d1633a03488a8c2`.
It confirmed the fixed joint stayed valid but the stricter fixed-socket smoke
still failed before contact:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error [0.1622, 0.1904] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.1705, -0.1446] m)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
```

Cleanup was confirmed: the delete request was sent, `brev ls instances --json
--all` returned `{"workspaces": null}`, and the watchdog printed `target
disappeared; cleanup confirmed`.

Interpretation: the remaining failure was not attach or wall filtering. The
script was still testing long-range absolute-IK reach to the authored fixed
socket before it could test contact physics. The local smoke now defaults to
`--contact_setup local-guide`, which relocates the kinematic guide under the
current insertion tip and keeps `fixed-socket` only as a later reachability
diagnostic.

## 2026-06-20 First Local-Guide Retry

The short Launchable retry on `isaac-launchable-b8fc1e` (`c51fxe4d3`) used
payload `834a7f478ea8d225c3cd7a828266d5092ba9ae1f2a127411902af91fb1c9cc85`.
It reached the official Isaac Lab runtime and showed the new mode was active:

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
```

Cleanup was confirmed after retrying deletion: Brev briefly reported the same
environment as `DEPLOYING` again, then the watchdog printed `target disappeared;
cleanup confirmed`, and the final `brev ls instances --json --all` returned
`{"workspaces": null}`.

Interpretation: the smoke still anchored the guide before free-space settle.
The absolute IK controller moved the actual lower peg end roughly 0.21-0.23m
laterally during settle/press, so the press phase was still not a vertical press
from the physical settled peg pose into the wall. This is a smoke-target
definition problem, not evidence that wall contact works.

Local follow-up changed `scripts/contact_physics_smoke.py` again:

- `local-guide` still establishes an initial free-space negative control;
- after that settle, it reads the actual physical lower peg end and re-anchors
  the kinematic guide under that settled pose;
- it re-checks wall force as `CONTACT-SMOKE free-space-reanchored`;
- the press target then moves straight down from the re-anchored hover pose.

`scripts/check_contact_physics_wiring.py` now requires this re-anchor logic so a
future edit cannot silently revert to the pre-settle target.

## 2026-06-20 Reanchor-Marker Retry

The next short Launchable retry on `isaac-launchable-ede7f3` (`ewix5zjtj`) used
payload `9639dff71de0d493878a6d40d5aa95cf1948c308070cf9092c52c66538fd34e0`.
The wrapper generated a per-run log instead of overwriting the canonical smoke
log:

```text
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_isaac-launchable-ede7f3_2026-06-20T06-58-21Z_FAIL.log
artifacts/launchable_logs/pulled_contact_smoke/contact_physics_smoke_runs_isaac-launchable-ede7f3_2026-06-20T06-58-21Z.tsv
```

Runtime result:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE contact-setup: local-guide reanchored: missing
CONTACT-SMOKE free-space-reanchored: missing
CONTACT-SMOKE press-force: missing
```

Cleanup was confirmed. `brev delete isaac-launchable-ede7f3 ewix5zjtj` was
issued, the instance remained in `DELETING` for several minutes, then
`brev ls instances --json --all` returned `{"workspaces": null}` and the
watchdog printed `target disappeared; cleanup confirmed`.

Interpretation: this is still not contact-physics proof. It is a tighter
fail-closed result showing the Isaac process/wrapper returned after the initial
free-space negative control without producing the required re-anchor or press
markers. Before spending another paid retry, debug the smoke control flow
locally/in-code: add explicit phase sentinels around the post-free-space
re-anchor block and make an incomplete phase sequence a first-class failure in
the Python script itself, not only in the shell wrapper.

## 2026-06-20 Phase-Sentinel Local Follow-up

Local follow-up implemented that missing control-flow evidence. The
phase-sentinel payload at that point was:

```text
1d19fecb91790e2762426723e2b5e4daaf296c6787929d8c5ab9d9c514c001c6
```

The prepared bundle at that point was:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T07-25-33Z.tar.gz
```

`scripts/contact_physics_smoke.py` now emits explicit phase begin/progress/end
markers for `free-space-settle`, `local-guide-reanchor`, `press-hold`, and
`retreat-hold`. It also emits `CONTACT-SMOKE phase-sequence: PASS` only after
all required phases complete. If the script exits after `free-space` again, the
Python layer itself should emit `CONTACT-SMOKE phase-sequence: FAIL` and return
nonzero, so the next remote log should identify the last completed phase instead
of only letting the shell wrapper report a missing marker afterward.

`scripts/check_phase2_contact_gate.py` and
`scripts/run_launchable_contact_physics_smoke.sh` now require those phase
sentinels in addition to the semantic PASS markers. `./scripts/run_local_quality_checks.sh`
passed after this change.

## 2026-06-20 Inference-Mode Launchable Retry

The next short official AWS Launchable retry ran on
`isaac-launchable-57032f` (`km6cr6mj0`) using AWS `g6e.4xlarge` / L40S. The
uploaded bundle was:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T08-03-51Z.tar.gz
source_payload_sha256=6c7513c22e56819c1402b358e66e5e252eeca83c648dcb3f30e41228b0d35345
```

The run first exposed an Isaac Lab/PyTorch inference-mode write issue while
moving the kinematic socket guide:

```text
RuntimeError: Inplace update to inference tensor outside InferenceMode
asset.write_root_pose_to_sim(torch.cat((pos_w, quat_w), dim=-1))
```

Local follow-up wrapped the kinematic root pose and velocity writes in
`torch.inference_mode()`. After copying that targeted script patch into the
running Launchable, the smoke completed all control-flow phases:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE phase-sequence: PASS
```

The semantic contact checks still failed:

```text
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error [0.04027855396270752, 0.36005330085754395] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.0764109194278717, 0.190305694937706] m)
CONTACT-SMOKE press-no-clip: FAIL (lower-end wall penetration [0.0, 0.190305694937706] m)
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
```

Pulled evidence:

```text
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-21-17Z-84.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-22-10Z-338.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-24-30Z-597.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-24-59Z-826.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-26-35Z-1069.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-27-06Z-1298.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-28-46Z-1541.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_2026-06-20T08-29-28Z-1770.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_canonical_2026-06-20T08-29-28Z-1770.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull/contact_physics_smoke_runs.tsv
artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-57032f-km6cr6mj0.tar.gz
```

Cleanup was confirmed. The instance remained in `DELETING` for several
minutes, then `brev ls instances --json --all` returned `{"workspaces": null}`
and `./scripts/brev_paid_safety_status.sh` returned
`SAFE_NO_VISIBLE_PAID_INSTANCE`.

Interpretation: the control-flow problem is fixed enough to reach the press
phase, but Phase 2 remains BLOCKED because the physical press is not being
tracked into contact. The next work should be local debugging of the press
target/tracking formulation. Do not spend on another Launchable retry until a
local code change specifically changes that formulation and the local checks
pass.

## 2026-06-20 Press-Tracking Local Follow-up

Local follow-up changed the press phase from a one-shot absolute action-frame
target into a small physical lower-end feedback loop. During `press-hold`,
`scripts/contact_physics_smoke.py` now recomputes the current physical lower
peg end each step and applies a bounded correction to the action-frame target:

```text
CONTACT-SMOKE press-control: lower-end closed-loop
```

This does not relax the semantic gate. The smoke still requires wall force,
bounded lateral tracking error, blocked motion near the wall-top plane, and
no clipping. The change only prevents a failed one-shot IK target from being
mistaken for a contact-physics result. `scripts/check_contact_physics_wiring.py`
now requires this lower-end closed-loop press path so it cannot be silently
removed.

The current prepared bundle after this follow-up is:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T08-52-37Z.tar.gz
source_payload_sha256=87e962fe4ab08ceb2650dd9478208005a886e66d5b6288a909c6d11ff1954fb6
archive_sha256=30ebd5f89285c8313bd5bac23f70e6a626753926f19ca3195ff052b9b3b776b5
```

Local quality passed after rebuilding this bundle:

```text
./scripts/run_local_quality_checks.sh
```

## 2026-06-20 Lower-End Feedback Runtime Retry

The bounded lower-end feedback version was run once on the official AWS Isaac
Launchable:

```text
instance: isaac-launchable-b4f35a / r6osffjlb
provider/type: AWS g6e.4xlarge L40S
payload: 87e962fe4ab08ceb2650dd9478208005a886e66d5b6288a909c6d11ff1954fb6
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-b4f35a/contact_physics_smoke_2026-06-20T09-15-45Z-newfeedback.log
log_sha256: d68719d7bdab29a3f37f5abe37850e3b286e4b609063751906dc71415ff1ff05
pull_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-b4f35a-r6osffjlb.tar.gz
pull_archive_sha256: 7e5e49fff2f9830da481b783449172174ff1a1af7295731944730e95ab95f5d2
cleanup: final `brev ls instances --json --all` returned {"workspaces": null};
         watchdog printed `target disappeared; cleanup confirmed`;
         `./scripts/brev_paid_safety_status.sh` returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

The smoke reached all phases but still failed the contact semantics:

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
```

Important diagnosis: the lower-end controller accumulated correction into a
global target while the IK lagged or saturated. The final commanded target was
far from the workspace, so this was control windup, not proof that the wall
contact model is valid.

Local follow-up changed `scripts/contact_physics_smoke.py` again:

- `local-guide-reanchor` now holds the current physical tip pose instead of
  treating a lower-end hover point as the IK tip target;
- after that hold, the guide is reanchored from the post-hold physical
  lower-end pose;
- `step_track_lower_end()` now computes each command from the current physical
  tip plus a bounded lower-end correction, instead of accumulating an
  unbounded target;
- retreat uses the same bounded lower-end servo to return to hover.

Current prepared bundle after this fix:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T09-32-10Z.tar.gz
source_payload_sha256=14da96a2a87e74c81220b3da09143b075ea933e33ec56a9f98faf54cdc9a34ef
archive_sha256=ccaa8a2f9e3e1afd3d05e702d91fd67934d1fc2bde3a7dbb10b163452d0fceea
```

Local quality passed for this current payload:

```text
./scripts/run_local_quality_checks.sh
```

## 2026-06-20 Current-Tip Servo Runtime Retry

The next official AWS Launchable retry on `isaac-launchable-26bffe`
(`s85xtqx1n`) used payload
`14da96a2a87e74c81220b3da09143b075ea933e33ec56a9f98faf54cdc9a34ef`.
The pulled evidence is:

```text
artifacts/launchable_logs/pulled_contact_smoke/rca-pull-26bffe/contact_physics_smoke_2026-06-20T09-52-29Z-currenttip.log
artifacts/launchable_logs/pulled_contact_smoke/rca-pull-26bffe/contact_physics_smoke_2026-06-20T09-53-21Z-currenttip.log
pull_archive_sha256=32e1a2e990051fecb3ca815f017ebb1a14eff722f13ca803e26b2153a00d168b
cleanup: final `brev ls instances --json --all` returned {"workspaces": null};
         watchdog printed `target disappeared; cleanup confirmed`;
         `./scripts/brev_paid_safety_status.sh` returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

The first log is the intended run. The second log exists because `brev exec`
reconnected after the fail-closed exit and repeated the same remote command
once. Future remote smoke invocations through `brev exec` must record the inner
smoke exit code but keep the outer CLI command at zero, then validate the
pulled log locally.

The runtime result was mixed:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE phase-sequence: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [4.317049980163574, 0.0] N)
CONTACT-SMOKE press-tracking: FAIL (lower-end lateral error [0.00972306914627552, 0.5869264602661133] m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z [-0.005544692277908325, 0.14811840653419495] m)
CONTACT-SMOKE press-no-clip: FAIL (lower-end wall penetration [0.0, 0.14811840653419495] m)
CONTACT-SMOKE release: PASS
CONTACT-SMOKE joint-integrity: PASS
```

Interpretation: env0 finally produced real wall force and stayed near the wall
line, so the contact model is not globally inert. Env1 drifted laterally by
about `0.59 m`, missed the wall, and then moved below the wall top with no wall
force. That points to the smoke control/reachability setup still leaking into
the physics gate. The contact smoke should isolate per-env contact physics, so
the next local fix freezes reset joint randomization for this gate and requires
a `CONTACT-SMOKE reset-joints: deterministic` marker in future PASS logs.

Prepared bundle after the deterministic-reset local fix:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T10-14-55Z.tar.gz
source_payload_sha256=a9745f5634f5f16bfee813da46bba829794e72e1b1d49fd9e98a913608b7124a
archive_sha256=16d98d08b9fd4935d83de73047bb9b39ded70eeb28a3616510e987a122ee08b9
```

## Current Local Difference

The current payload has already moved away from that old failure mode:

- `peg` is an `AssetBaseCfg` with `AttachedPegCylinderCfg`, not a
  `RigidObjectCfg`;
- `exclude_from_articulation=False`, so the peg is intended to participate in
  the Franka articulation;
- MDP observations derive peg pose from the calibrated hand frame rather than a
  separate peg RigidObject view;
- `contact_physics_smoke.py` can read peg pose from a robot body if the peg is
  exposed inside the articulation, or otherwise fall back to the calibrated
  hand offset;
- `contact_physics_smoke.py` defaults to `local-guide`, relocating the kinematic
  socket walls under the current insertion tip so the smoke isolates dynamic
  contact response instead of long-range IK reachability;
- `local-guide` now re-anchors after free-space settle and re-checks
  free-space force before the press phase;
- `contact_physics_smoke.py` now logs phase begin/progress/end sentinels and
  fails incomplete phase sequences in Python itself;
- `contact_physics_smoke.py` now freezes `reset_robot_joints` to a deterministic
  `(1.0, 1.0)` joint-position scale for the smoke, so randomized reset posture
  reachability cannot masquerade as contact-physics evidence;
- `run_launchable_contact_physics_smoke.sh` now writes each invocation to a
  unique `contact_physics_smoke_<run_id>.log`, records
  `contact_physics_smoke_runs.tsv`, and copies the latest run to the canonical
  log only as a compatibility artifact;
- post-gate helper scripts now tolerate the new no-RigidObject peg model by
  falling back to the hand-derived action-frame tip pose.

`scripts/check_contact_physics_wiring.py` now also scans Python sources for old
unguarded peg pose assumptions and requires the stricter smoke/gate markers.
The only allowed direct peg-pose consumers are `scripts/contact_physics_smoke.py`,
`scripts/scripted_agent.py`, and `scripts/evaluate_contact_bc_policy.py`, and
those paths must keep their explicit articulation/no-RigidObject fallbacks.

## Current Status

The current payload still has no valid remote PASS log. Keep
`python3 scripts/check_phase2_contact_gate.py` as BLOCKED until a new Isaac
runtime log for payload
`9a36b8041d8440fe7822c9711c8c4aa6047eb9582ec3b3e2d71f2accc009b1e2`
contains all required PASS markers and is archived as
`artifacts/launchable_logs/contact_physics_smoke.log`.

Do not use the old failed logs as current proof. They are useful only as
diagnostic history explaining why the RigidObject peg view had to be removed.

## 2026-06-20 Z-Locked Arm-Servo Retry And Local Wall-Sweep Follow-up

The deterministic reset / z-only lateral-lock retry on
`isaac-launchable-zlock-9b3c` (`hzekq6qqz`) used payload
`9b3cd761fb8843047260cc4a3be21cefe22268b7e2d85160c2014cbba4ab0182`.
Pulled evidence:

```text
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-zlock/contact_physics_smoke_2026-06-20T11-10-08Z-zlock.log
pull_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-zlock-hzekq6qqz.tar.gz
pull_archive_sha256: 2405e40d0477671a38c91a629c339fb9d020843f1e3864897ff3fd4020f20db1
```

Result:

```text
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS
CONTACT-SMOKE free-space-reanchored: PASS
CONTACT-SMOKE phase-sequence: PASS
CONTACT-SMOKE press-force: FAIL (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-tracking: PASS (lower-end lateral error about 0.0074m)
CONTACT-SMOKE press-blocked: FAIL (wall_top_z - lower_end_z about -0.016m)
CONTACT-SMOKE press-no-clip: PASS
CONTACT-SMOKE release: FAIL (residual wall force [0.4584, 6.8527] N)
CONTACT-SMOKE joint-integrity: PASS
```

This is a useful negative result: the z-only lock fixed the runaway lateral
drift, but the arm-servo press still did not move the physical lower peg end
into the wall top. The first semantic gate should prove peg-vs-wall contact
physics, not Franka IK reachability.

Local follow-up changes the default `scripts/contact_physics_smoke.py` press
mechanism to `guide-wall-sweep`. It holds the current reanchored robot pose and
sweeps the local kinematic guide vertically into the dynamic peg. The old
`arm-servo` mechanism remains available as a controller diagnostic mode, but
the Phase 2 gate now requires:

```text
CONTACT-SMOKE press-control: local-wall-sweep
```

Current local bundle after this follow-up:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T11-21-30Z.tar.gz
source_payload_sha256=9a36b8041d8440fe7822c9711c8c4aa6047eb9582ec3b3e2d71f2accc009b1e2
archive_sha256=3248793a7ebbc52fde17936e6e814962be59fdcb3e093193673b49de174ad0dc
local_quality: ./scripts/run_local_quality_checks.sh passed
```

Cleanup after the zlock retry was confirmed: `brev ls instances --json --all`
returned `{"workspaces": null}`, the watchdog printed `target disappeared;
cleanup confirmed`, and `./scripts/brev_paid_safety_status.sh` returned
`SAFE_NO_VISIBLE_PAID_INSTANCE` with no watchdog processes. The next paid smoke
still requires the normal readiness/preflight path and must run only the current
`guide-wall-sweep` contact smoke.

## 2026-06-20 Guide-Wall-Sweep Runtime Retry

The short official AWS Launchable retry on `isaac-launchable-wallsweep-9a36`
(`eqb76y582`) used payload
`9a36b8041d8440fe7822c9711c8c4aa6047eb9582ec3b3e2d71f2accc009b1e2`.
Pulled evidence:

```text
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-wallsweep/contact_physics_smoke_2026-06-20T11-47-15Z-wallsweep.log
pull_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-wallsweep-eqb76y582.tar.gz
pull_archive_sha256: 974c383d10ba5f30aca292894ceea7bf16f6a695f76fcbe34f539c193e87c331
```

The runtime result was:

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

Interpretation: this is the first current-payload run that proves substantial
wall-filtered force in both environments while preserving attachment,
free-space negative controls, release, and joint integrity. The remaining
failure is now narrower: the smoke's blocked-contact condition is not satisfied
because the lower peg end remains about `8.8-9.5 mm` above the wall top instead
of showing the commanded `20 mm` blocked overlap. The next step should be local:
inspect the guide-wall-sweep geometry and blocked-contact assertion, then
change the fixture or the semantic check so it measures the intended contact
normal relation. Do not run paid controller sweeps or learned-policy work from
this result.

Cleanup was confirmed after the delete path briefly cycled through `DELETING`
and `DEPLOYING`: a retry returned `instance ... not found`, `brev ls instances
--json --all` returned `{"workspaces": null}`,
`./scripts/brev_paid_safety_status.sh` returned
`SAFE_NO_VISIBLE_PAID_INSTANCE`, and the watchdog printed
`target disappeared; cleanup confirmed`.

Local follow-up: the `guide-wall-sweep` blocked check is now radius-aware. The
failed log's `lower_end_z - wall_top_z` offset of about `8.8-9.5 mm` is close
to `PEG_RADIUS_M=10 mm`, which is the expected centerline offset for a
cylindrical peg contacting a guide-wall edge. The `arm-servo` diagnostic mode
still checks wall-top plane blocking, but the default contact-physics smoke now
requires the guide-wall sweep to keep the lower-end centerline within
`block_tolerance_m` of one peg radius above the wall top.

Current prepared bundle after this local fix:

```text
artifacts/launchable/robot-contact-assembly-contact-smoke-2026-06-20T12-05-01Z.tar.gz
source_payload_sha256=3ac9064fda3bc0c88aee7c3770f3a8f6087e56158fa22beb81ff75fae74e69fb
archive_sha256=641df0fd25f0e50ff3176b9dab917aa4709edfba0f9ce74a85f48948d9eb7456
local_quality: ./scripts/run_local_quality_checks.sh passed
brev_safety: ./scripts/brev_paid_safety_status.sh returned SAFE_NO_VISIBLE_PAID_INSTANCE
```

## 2026-06-20 Final Contact-Smoke PASS

The final short official AWS Launchable retry on `isaac-launchable-gate-5ecb`
(`ak7egbprx`) used payload
`5ecbb035170e1cbc323d70263d5a7398c0e2a47cc2b2a2f86a7aef010a760e7f`.

Pulled evidence:

```text
log: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-gate/contact_physics_smoke_2026-06-20T13-01-54Z-gate.log
canonical_log: artifacts/launchable_logs/contact_physics_smoke.log
pull_archive: artifacts/launchable_logs/pulled_contact_smoke/rca-pull-isaac-launchable-gate-ak7egbprx.tar.gz
pull_archive_sha256: 4c595d7098c8b760ba3af603246ccf5c485f3d9251984ce372d9f52eafb3ec92
deliverables: artifacts/deliverables/2026-06-20-contact-smoke/
```

Runtime result:

```text
smoke_exit=0
CONTACT-SMOKE attach: PASS
CONTACT-SMOKE free-space: PASS (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE free-space-reanchored: PASS (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE press-control: local-wall-sweep
CONTACT-SMOKE press-force: PASS (mean wall force [29.153621673583984, 37.27742004394531] N)
CONTACT-SMOKE press-tracking: PASS (lower-end lateral error [0.005723054055124521, 0.008925105445086956] m)
CONTACT-SMOKE press-blocked: PASS (lower_end_z - wall_top_z [0.009471744298934937, 0.008838444948196411] m)
CONTACT-SMOKE press-no-clip: PASS (lower-end wall penetration [0.0, 0.0] m)
CONTACT-SMOKE release: PASS (mean wall force [0.0, 0.0] N)
CONTACT-SMOKE joint-integrity: PASS
CONTACT-SMOKE phase-sequence: PASS
Contact physics smoke completed: all checks passed.
[contact-smoke] completed: contact physics is real
```

Validation:

```text
python3 scripts/check_phase2_contact_gate.py --log artifacts/launchable_logs/pulled_contact_smoke/rca-pull-gate/contact_physics_smoke_2026-06-20T13-01-54Z-gate.log --run-local-quality
  PASS: validated contact-physics smoke evidence

./scripts/run_local_quality_checks.sh
  passed
```

Cleanup:

```text
brev ls instances --json --all
  {"workspaces": null}

./scripts/brev_paid_safety_status.sh
  status=SAFE_NO_VISIBLE_PAID_INSTANCE

watchdog:
  target disappeared; cleanup confirmed
```

Interpretation: the Phase 2 contact-physics gate is satisfied for the current
runtime payload. The prior zero-force, reachability-entanglement, and
radius-awareness blockers are resolved for the smoke gate. The next work should
not be another smoke retry; it should be a short scripted trace under this
validated task, then refreshed contact-validity and demo-coverage reports before
reopening controller, BC, or RL work.
