#!/usr/bin/env python3
"""Static source-level checks for contact-physics wiring.

This is a no-Isaac, no-Brev guard. It cannot prove PhysX behavior; the remote
contact smoke remains the hard semantic gate. It does catch local regressions
that would obviously invalidate the smoke before spending paid runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = (
    REPO_ROOT
    / "source/robot_contact_assembly_tasks/robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole"
)
ENV_CFG = TASK_ROOT / "peg_in_hole_env_cfg.py"
ASSETS = TASK_ROOT / "assets.py"
OBSERVATIONS = TASK_ROOT / "mdp/observations.py"
EVENTS = TASK_ROOT / "mdp/events.py"

WALL_PRIMS = (
    "SocketWallLeft",
    "SocketWallRight",
    "SocketWallFront",
    "SocketWallBack",
)


@dataclass(frozen=True)
class RequiredPattern:
    path: Path
    pattern: str
    description: str
    flags: int = re.DOTALL


def read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"missing file: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def require(pattern: RequiredPattern) -> None:
    text = read(pattern.path)
    if not re.search(pattern.pattern, text, flags=pattern.flags):
        raise AssertionError(f"{pattern.description} not found in {pattern.path.relative_to(REPO_ROOT)}")


def check_required_patterns() -> None:
    checks = (
        RequiredPattern(
            ENV_CFG,
            r"peg\s*=\s*AssetBaseCfg\(.*?spawn\s*=\s*AttachedPegCylinderCfg\(.*?kinematic_enabled\s*=\s*False",
            "dynamic peg collider spawn without RigidObject view",
        ),
        RequiredPattern(
            ENV_CFG,
            r"peg_contact\s*=\s*ContactSensorCfg\(.*?filter_prim_paths_expr\s*=\s*\[",
            "wall-filtered peg contact sensor",
        ),
        RequiredPattern(
            ASSETS,
            r"UsdPhysics\.FixedJoint\.Define",
            "USD fixed joint authoring",
        ),
        RequiredPattern(
            ASSETS,
            r"_align_peg_prim_to_joint_frame\(peg_prim,\s*hand_prim,\s*cfg\).*?UsdPhysics\.FixedJoint\.Define",
            "spawn-time peg/joint-frame alignment before fixed joint authoring",
        ),
        RequiredPattern(
            ASSETS,
            r"peg_world\s*=\s*joint_local\s*\*\s*hand_world",
            "OpenUSD row-vector local-to-world joint composition",
        ),
        RequiredPattern(
            ASSETS,
            r"exclude_from_articulation\s*:\s*bool\s*=\s*False",
            "peg participates in the articulation by default",
        ),
        RequiredPattern(
            ASSETS,
            r"CreateExcludeFromArticulationAttr\(\)\.Set\(bool\(cfg\.exclude_from_articulation\)\)",
            "configurable excludeFromArticulation authoring",
        ),
        RequiredPattern(
            ENV_CFG,
            r"exclude_from_articulation\s*=\s*False",
            "env config keeps peg in articulation by default",
        ),
        RequiredPattern(
            REPO_ROOT / "scripts/contact_physics_smoke.py",
            r"--exclude_peg_from_articulation",
            "contact smoke legacy articulation-exclusion diagnostic flag",
            flags=0,
        ),
        RequiredPattern(
            REPO_ROOT / "scripts/contact_physics_smoke.py",
            r"peg_pose_source",
            "contact smoke logs peg pose source",
            flags=0,
        ),
        RequiredPattern(
            ASSETS,
            r"FilteredPairsAPI\.Apply",
            "gripper/peg filtered-pairs setup",
        ),
        RequiredPattern(
            OBSERVATIONS,
            r"force_matrix\s*=\s*getattr\(sensor\.data,\s*\"force_matrix_w\"",
            "force_matrix_w wall-filter lookup",
        ),
        RequiredPattern(
            OBSERVATIONS,
            r"body_name_candidates\s*=.*?Peg.*?if body_name in robot\.body_names",
            "peg pose prefers actual robot Peg body when available",
        ),
        RequiredPattern(
            OBSERVATIONS,
            r"PEG_CENTER_BODY_OFFSET_POS",
            "peg pose keeps calibrated hand-offset fallback",
            flags=0,
        ),
        RequiredPattern(
            OBSERVATIONS,
            r"def peg_contact_force_magnitude\(.*?_peg_wall_contact_forces_w\(sensor\)",
            "contact magnitude uses wall-filtered forces",
        ),
        RequiredPattern(
            OBSERVATIONS,
            r"def peg_contact_force_socket\(.*?_peg_wall_contact_forces_w\(sensor\)",
            "contact socket vector uses wall-filtered forces",
        ),
    )
    for item in checks:
        require(item)


def check_wall_filters() -> None:
    env_text = read(ENV_CFG)
    missing = [wall for wall in WALL_PRIMS if wall not in env_text]
    if missing:
        raise AssertionError("missing socket wall filter prim(s): " + ", ".join(missing))


def check_no_active_peg_rigidobject_or_sync_event() -> None:
    env_text = read(ENV_CFG)
    if re.search(r"peg\s*=\s*RigidObjectCfg\(", env_text):
        raise AssertionError("peg must not be registered as RigidObjectCfg while it is an articulation link")
    task_text = "\n".join(read(path) for path in TASK_ROOT.rglob("*.py"))
    if "sync_peg_on_reset" in task_text:
        raise AssertionError("sync_peg_on_reset must stay removed for articulation-link peg")
    sync_event_blocks = re.findall(r"\w+\s*=\s*EventTerm\((?:(?!\n\s*\w+\s*=\s*EventTerm\().)*sync_peg_to_hand.*?\)", env_text, flags=re.DOTALL)
    if sync_event_blocks:
        raise AssertionError("sync_peg_to_hand must not be active in the scene EventCfg")


def check_contact_smoke_uses_force_matrix() -> None:
    smoke = REPO_ROOT / "scripts/contact_physics_smoke.py"
    text = read(smoke)
    if "sensor.data.force_matrix_w" not in text:
        raise AssertionError("contact_physics_smoke.py must read wall-filtered sensor.data.force_matrix_w")
    if "peg_contact sensor has no force_matrix_w" not in text:
        raise AssertionError("contact_physics_smoke.py must fail when force_matrix_w is unavailable")
    if "press-tracking" not in text:
        raise AssertionError("contact_physics_smoke.py must fail when the lower peg end does not reach the wall line")
    if "--contact_setup" not in text or "local-guide" not in text:
        raise AssertionError("contact_physics_smoke.py must support the local-guide contact-physics setup")
    if "write_root_pose_to_sim" not in text:
        raise AssertionError("contact_physics_smoke.py must be able to relocate kinematic socket walls for local contact")
    if "local-guide reanchored" not in text or "free-space-reanchored" not in text:
        raise AssertionError("local-guide smoke must re-anchor after hover settle and re-check free-space force")
    if "phase-sequence" not in text or "phase_label=" not in text:
        raise AssertionError("contact smoke must emit explicit phase sentinels and fail incomplete phase sequences")
    if "CONTACT-SMOKE reset-joints: deterministic" not in text or "reset_joint_position_scale" not in text:
        raise AssertionError("contact smoke must freeze reset joint randomization for the physics gate")
    if "press-control: local-wall-sweep" not in text or "step_sweep_socket_z" not in text:
        raise AssertionError("contact smoke press phase must isolate contact physics with a local wall sweep")
    if "PEG_RADIUS_M" not in text or "lower_end_z - wall_top_z" not in text:
        raise AssertionError("local wall-sweep blocked check must account for cylindrical peg radius")
    if "arm-servo" not in text or "step_track_lower_end" not in text:
        raise AssertionError("contact smoke must preserve the arm-servo path as a controller diagnostic")
    if re.search(r"hover_target\[:,\s*2\]\s*=.*\+\s*PEG_LENGTH_M", text):
        raise AssertionError("contact smoke hover target must use the insertion action frame directly")
    if re.search(r"press_target\[:,\s*2\]\s*=.*\+\s*PEG_LENGTH_M", text):
        raise AssertionError("contact smoke press target must use the insertion action frame directly")
    wrapper = read(REPO_ROOT / "scripts/run_launchable_contact_physics_smoke.sh")
    if "contact_physics_smoke_${RUN_ID}.log" not in wrapper or "contact_physics_smoke_runs.tsv" not in wrapper:
        raise AssertionError("contact smoke wrapper must preserve per-run logs before updating the canonical log")
    if "CONTACT-SMOKE reset-joints: deterministic" not in wrapper:
        raise AssertionError("contact smoke wrapper must require deterministic reset evidence")
    if "CONTACT-SMOKE free-space-reanchored: PASS" not in wrapper:
        raise AssertionError("contact smoke wrapper must require the re-anchored free-space negative control")
    if "CONTACT-SMOKE press-control: local-wall-sweep" not in wrapper:
        raise AssertionError("contact smoke wrapper must require the local wall-sweep press marker")
    if "CONTACT-SMOKE phase-sequence: PASS" not in wrapper:
        raise AssertionError("contact smoke wrapper must require the Python phase-sequence sentinel")


def check_downstream_scripts_support_articulation_peg() -> None:
    for rel_path in ("scripts/scripted_agent.py", "scripts/evaluate_contact_bc_policy.py"):
        text = read(REPO_ROOT / rel_path)
        if "scene peg has no RigidObject root pose data" not in text:
            raise AssertionError(f"{rel_path} must tolerate peg without a RigidObject data view")
        if "return _action_frame_pose_w(env_unwrapped, robot.body_names.index(\"panda_hand\"))" not in text:
            raise AssertionError(f"{rel_path} must fall back to hand-derived physical tip pose")


def check_no_unguarded_peg_pose_consumers() -> None:
    """Fail closed on old separate-RigidObject peg pose assumptions.

    The current task welds the peg into the Franka articulation. The smoke
    script may still inspect a separate peg RigidObject for legacy diagnostics,
    but every consumer must have an explicit fallback when that view is absent.
    """

    risky_pattern = re.compile(
        r"env(?:_unwrapped)?\.scene\[[\"']peg[\"']\]"
        r"|scene\[[\"']peg[\"']\]"
        r"|peg(?:_data)?\.root_(?:pos|quat)_w"
        r"|peg\.data\.root_(?:pos|quat)_w"
    )
    allowlist = {
        Path("scripts/contact_physics_smoke.py"): (
            "_peg_pose_w_for_smoke",
            "_scene_entity_or_none",
            "derived-hand-offset",
            "peg_pose_source",
        ),
        Path("scripts/scripted_agent.py"): (
            "scene peg has no RigidObject root pose data",
            "return _action_frame_pose_w(env_unwrapped, robot.body_names.index(\"panda_hand\"))",
        ),
        Path("scripts/evaluate_contact_bc_policy.py"): (
            "scene peg has no RigidObject root pose data",
            "return _action_frame_pose_w(env_unwrapped, robot.body_names.index(\"panda_hand\"))",
        ),
    }

    search_roots = (REPO_ROOT / "scripts", REPO_ROOT / "source" / "robot_contact_assembly_tasks")
    violations: list[str] = []
    for root in search_roots:
        for path in sorted(root.rglob("*.py")):
            rel_path = path.relative_to(REPO_ROOT)
            text = read(path)
            matches = [
                f"{line_no}:{line.strip()}"
                for line_no, line in enumerate(text.splitlines(), start=1)
                if risky_pattern.search(line)
            ]
            if not matches:
                continue

            required_markers = allowlist.get(rel_path)
            if required_markers is None:
                violations.append(f"{rel_path} has unallowlisted peg pose access: {'; '.join(matches[:3])}")
                continue

            missing_markers = [marker for marker in required_markers if marker not in text]
            if missing_markers:
                violations.append(
                    f"{rel_path} has peg pose access but is missing fallback marker(s): "
                    + ", ".join(missing_markers)
                )

    if violations:
        raise AssertionError("; ".join(violations))


def check_wxyz_quaternion_transform_helpers() -> None:
    """Keep contact-shell pose math on the Isaac Lab 2.x WXYZ convention."""

    for path in (EVENTS, OBSERVATIONS):
        text = read(path)
        relative = path.relative_to(REPO_ROOT)
        if re.search(r"from\s+isaaclab\.utils\.math\s+import.*frame_transforms", text):
            raise AssertionError(
                f"{relative} must not import frame-transform helpers without an explicit convention audit"
            )
        if re.search(r"(?<!_)combine_frame_transforms\(", text) or re.search(
            r"(?<!_)subtract_frame_transforms\(", text
        ):
            raise AssertionError(
                f"{relative} must not mix generic frame-transform helpers into the WXYZ contact shell"
            )
        if "_combine_frame_transforms_wxyz" not in text:
            raise AssertionError(f"{relative} must define/use _combine_frame_transforms_wxyz")
        if path == OBSERVATIONS and "_subtract_frame_transforms_wxyz" not in text:
            raise AssertionError(f"{relative} must define/use _subtract_frame_transforms_wxyz")


def main() -> int:
    try:
        check_required_patterns()
        check_wall_filters()
        check_no_active_peg_rigidobject_or_sync_event()
        check_contact_smoke_uses_force_matrix()
        check_downstream_scripts_support_articulation_peg()
        check_no_unguarded_peg_pose_consumers()
        check_wxyz_quaternion_transform_helpers()
    except AssertionError as exc:
        print(f"[contact-wiring] FAIL: {exc}", file=sys.stderr)
        return 1

    print("[contact-wiring] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
