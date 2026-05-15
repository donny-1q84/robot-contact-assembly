"""Check contact-task geometry constants without launching Isaac Sim."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_PATH = (
    ROOT
    / "source"
    / "robot_contact_assembly_tasks"
    / "robot_contact_assembly_tasks"
    / "tasks"
    / "manager_based"
    / "manipulation"
    / "peg_in_hole"
    / "constants.py"
)


def _load_constants():
    spec = importlib.util.spec_from_file_location("rca_constants", CONSTANTS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load constants from {CONSTANTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _quat_rotate_wxyz(quat: tuple[float, float, float, float], vec: tuple[float, float, float]) -> tuple[float, float, float]:
    w, x, y, z = quat
    vx, vy, vz = vec
    # Rotation matrix for unit quaternions in Isaac Lab's `(w, x, y, z)` convention.
    return (
        (1.0 - 2.0 * (y * y + z * z)) * vx + 2.0 * (x * y - z * w) * vy + 2.0 * (x * z + y * w) * vz,
        2.0 * (x * y + z * w) * vx + (1.0 - 2.0 * (x * x + z * z)) * vy + 2.0 * (y * z - x * w) * vz,
        2.0 * (x * z - y * w) * vx + 2.0 * (y * z + x * w) * vy + (1.0 - 2.0 * (x * x + y * y)) * vz,
    )


def _assert_close(name: str, actual: tuple[float, ...], expected: tuple[float, ...], tol: float = 1.0e-9) -> None:
    max_error = max(abs(a - b) for a, b in zip(actual, expected, strict=True))
    if max_error > tol:
        raise AssertionError(f"{name}: max_error={max_error:.3e}, actual={actual}, expected={expected}")


def main() -> int:
    c = _load_constants()

    yaw = c.PEG_TIP_YAW_OFFSET_RAD
    expected_tip_rot = (math.cos(0.5 * yaw), 0.0, 0.0, math.sin(0.5 * yaw))
    _assert_close("PEG_TIP_BODY_OFFSET_ROT", c.PEG_TIP_BODY_OFFSET_ROT, expected_tip_rot)

    quat_norm = math.sqrt(sum(value * value for value in c.PEG_TIP_BODY_OFFSET_ROT))
    if abs(quat_norm - 1.0) > 1.0e-9:
        raise AssertionError(f"PEG_TIP_BODY_OFFSET_ROT is not unit length: norm={quat_norm:.12f}")

    local_tip = c.PEG_TIP_FROM_CENTER_POS
    rotated_local_tip = _quat_rotate_wxyz(c.PEG_CENTER_BODY_OFFSET_ROT, local_tip)
    physical_tip_offset = tuple(
        c.PEG_CENTER_BODY_OFFSET_POS[index] + rotated_local_tip[index] for index in range(3)
    )
    _assert_close("physical peg tip offset", physical_tip_offset, c.PEG_TIP_BODY_OFFSET_POS)
    _assert_close("PEG_TIP_FROM_CENTER_POS", c.PEG_TIP_FROM_CENTER_POS, (0.0, 0.0, -0.5 * c.PEG_LENGTH_M))
    _assert_close("PEG_ROOT_FROM_TIP_POS", c.PEG_ROOT_FROM_TIP_POS, tuple(-value for value in local_tip))
    _assert_close("PEG_ROOT_FROM_TIP_ROT", c.PEG_ROOT_FROM_TIP_ROT, (1.0, 0.0, 0.0, 0.0))

    print("[geometry-check] contact geometry constants are self-consistent")
    print(f"[geometry-check] tip_rot_wxyz={c.PEG_TIP_BODY_OFFSET_ROT}")
    print(f"[geometry-check] physical_tip_offset={physical_tip_offset}")
    print(f"[geometry-check] peg_root_from_tip_pos={c.PEG_ROOT_FROM_TIP_POS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
