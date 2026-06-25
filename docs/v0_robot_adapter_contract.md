# V0 Robot Adapter Contract

The V0 language and skill layers are portable only up to the adapter boundary.
They are not a direct drop-in controller for arbitrary robot arms.

## Boundary

```text
language request -> skill target -> robot-specific adapter -> robot driver
```

The adapter is responsible for translating a validated `peg_in_hole` skill
target into the named robot's model, frames, controller interface, speed limits,
timeouts, and abort behavior. A new robot therefore requires a new adapter
manifest plus robot-specific evidence.

## Required Evidence

- `model_sources`: URDF/USD or equivalent model, joint limits, tool geometry,
  TCP transform, and controller interface specification.
- `calibration_evidence`: base-frame alignment, TCP calibration, socket fixture
  frame, and optional perception/contact threshold calibration.
- `ros2_interfaces`: joint trajectory command interface, joint-state feedback,
  and skill status feedback, all explicitly validated.
- `command_contract`: command frame, units, control mode, feedback fields,
  abort conditions, and rate limits.
- `frame_contract`: base, tool, TCP, socket, transform source, and timestamp
  source.
- `runtime_guards`: translation/rotation/joint step limits, command timeout,
  stale-state timeout, abort-on-fault, and low-speed contact mode.
- `safety_evidence`: joint/workspace/collision limits, controller timeout,
  emergency stop path, and low-speed contact validation.
- `revalidation_evidence`: contact-gate equivalent, strict variation batch,
  fail-closed negative control, and low-speed hardware contact trial.

## Non-Claims

Passing the adapter checker for one named robot does not prove readiness for
any other arm. It only means this named adapter has supplied the required
evidence and is ready for low-speed human review. Cross-robot portability is
achieved by repeating the adapter, calibration, safety, and revalidation steps
for each robot.

## Executable Boundary Check

Use `python3 scripts/check_v0_portability_boundary.py` to audit the whole
portability claim. The checker combines V0 skill readiness with the named robot
adapter contract and keeps `universal_drop_in_ready=false` even when a specific
adapter is ready. A passing result means `READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW`,
not arbitrary-arm plug-and-play precision.
