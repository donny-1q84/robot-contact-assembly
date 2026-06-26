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
  frame, calibration error bounds, and optional perception/contact threshold
  calibration.
- `ros2_interfaces`: ROS 2 or vendor-bridge interfaces for joint trajectory or
  equivalent command, joint-state feedback, EE pose feedback, Cartesian command
  or IK, end-effector/tool command, force/torque or contact feedback, and skill
  status feedback, all explicitly validated.
- `command_contract`: skill-target schema, command acknowledgement, command
  frame, units, control mode, feedback fields, abort conditions, and rate
  limits.
- `frame_contract`: base, tool, TCP, socket, transform source, and timestamp
  source, plus calibration error bounds for the named robot.
- `runtime_guards`: contact-force, translation, TCP-speed, rotation, and joint
  step limits, command timeout, stale-state timeout, abort-on-fault, and
  low-speed contact mode.
- `safety_evidence`: joint/workspace/collision limits, controller timeout,
  emergency stop path, force/torque limits, low-speed no-contact dry-run, and
  low-speed contact validation.
- `revalidation_evidence`: adapter frame round-trip check, contact-gate
  equivalent, strict variation batch, fail-closed negative control, low-speed
  no-contact dry-run, and low-speed hardware contact trial.

The adapter checker intentionally requires both command and feedback surfaces.
For a contact-rich insertion task, command-only portability is not meaningful:
the adapter must prove it can read joint state, EE pose, tool state, and
force/torque or contact feedback before any low-speed hardware review.

## Non-Claims

Passing the adapter checker for one named robot does not prove readiness for
any other arm. It only means this named adapter has supplied the required
evidence and is ready for low-speed human review. Cross-robot portability is
achieved by repeating the adapter, calibration, safety, and revalidation steps
for each robot.

Even a named-robot `READY` result is not hardware execution approval. It is a
review gate for a calibrated adapter; actual robot motion still requires a
separate human approval and a low-speed no-contact dry-run before contact.

## Executable Boundary Check

Use `python3 scripts/check_v0_portability_boundary.py` to audit the whole
portability claim. The checker combines V0 skill readiness with the named robot
adapter contract and keeps `universal_drop_in_ready=false` even when a specific
adapter is ready. A passing result means `READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW`,
not arbitrary-arm plug-and-play precision.
