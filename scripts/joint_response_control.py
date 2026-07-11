#!/usr/bin/env python3
"""Empirical joint-response controller helpers.

This module intentionally has no Isaac dependency. A remote Isaac calibration
can measure how small absolute joint-position target offsets move the action
frame, then these helpers turn a desired Cartesian delta into a bounded joint
delta using the measured response matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
import math
from pathlib import Path
from typing import Any, Sequence


Vector = list[float]
Matrix = list[list[float]]


@dataclass(frozen=True)
class JointResponseCommand:
    joint_delta: Vector
    predicted_delta: Vector
    desired_delta: Vector
    cosine: float | None
    residual_norm: float
    clamped: bool
    pass_gate: bool


def _vec(value: Sequence[float], *, length: int, label: str) -> Vector:
    if len(value) != length:
        raise ValueError(f"{label} must have length {length}, got {len(value)}")
    return [float(part) for part in value]


def _norm(value: Sequence[float]) -> float:
    return math.sqrt(sum(float(part) * float(part) for part in value))


def _dot(lhs: Sequence[float], rhs: Sequence[float]) -> float:
    return sum(float(lhs[idx]) * float(rhs[idx]) for idx in range(len(lhs)))


def _mat_vec(matrix: Matrix, vector: Sequence[float]) -> Vector:
    return [_dot(row, vector) for row in matrix]


def _mat_transpose_vec(matrix: Matrix, vector: Sequence[float]) -> Vector:
    cols = len(matrix[0])
    return [sum(matrix[row][col] * float(vector[row]) for row in range(len(matrix))) for col in range(cols)]


def _response_gram3(matrix: Matrix, damping: float) -> Matrix:
    gram = [[0.0 for _ in range(3)] for _ in range(3)]
    for row in range(3):
        for col in range(3):
            gram[row][col] = _dot(matrix[row], matrix[col])
        gram[row][row] += damping * damping
    return gram


def _solve_3x3(matrix: Matrix, rhs: Sequence[float]) -> Vector:
    """Solve a 3x3 system with partial pivoting."""

    aug = [list(matrix[row]) + [float(rhs[row])] for row in range(3)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1.0e-12:
            raise ValueError("response matrix is singular; increase damping or recalibrate")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_value = aug[col][col]
        for item in range(col, 4):
            aug[col][item] /= pivot_value
        for row in range(3):
            if row == col:
                continue
            factor = aug[row][col]
            for item in range(col, 4):
                aug[row][item] -= factor * aug[col][item]
    return [aug[row][3] for row in range(3)]


def validate_response_matrix(matrix: Sequence[Sequence[float]]) -> Matrix:
    if len(matrix) != 3:
        raise ValueError(f"response matrix must have 3 rows, got {len(matrix)}")
    rows = [_vec(row, length=len(matrix[0]), label=f"response row {idx}") for idx, row in enumerate(matrix)]
    if not rows or len(rows[0]) == 0:
        raise ValueError("response matrix must have at least one joint column")
    width = len(rows[0])
    for idx, row in enumerate(rows):
        if len(row) != width:
            raise ValueError(f"response row {idx} width {len(row)} does not match {width}")
    return rows


def compute_joint_response_command(
    response_matrix: Sequence[Sequence[float]],
    desired_delta: Sequence[float],
    *,
    damping: float = 1.0e-4,
    max_joint_delta: float = 0.04,
    min_predicted_norm: float = 1.0e-5,
    min_cosine: float = 0.50,
    max_residual_ratio: float = 0.75,
) -> JointResponseCommand:
    matrix = validate_response_matrix(response_matrix)
    desired = _vec(desired_delta, length=3, label="desired_delta")
    desired_norm = _norm(desired)
    if desired_norm <= 0.0:
        zero = [0.0 for _ in range(len(matrix[0]))]
        return JointResponseCommand(zero, [0.0, 0.0, 0.0], desired, None, 0.0, False, False)

    if damping <= 0.0:
        raise ValueError("damping must be positive")
    gram = _response_gram3(matrix, damping)
    dual = _solve_3x3(gram, desired)
    joint_delta = _mat_transpose_vec(matrix, dual)

    clamped = False
    max_abs = max((abs(part) for part in joint_delta), default=0.0)
    if max_joint_delta > 0.0 and max_abs > max_joint_delta:
        scale = max_joint_delta / max_abs
        joint_delta = [part * scale for part in joint_delta]
        clamped = True

    predicted = _mat_vec(matrix, joint_delta)
    predicted_norm = _norm(predicted)
    residual = [desired[idx] - predicted[idx] for idx in range(3)]
    residual_norm = _norm(residual)
    cosine = None
    if predicted_norm >= min_predicted_norm:
        cosine = _dot(desired, predicted) / max(desired_norm * predicted_norm, 1.0e-12)
    pass_gate = (
        cosine is not None
        and cosine >= min_cosine
        and residual_norm <= max_residual_ratio * desired_norm
    )
    return JointResponseCommand(joint_delta, predicted, desired, cosine, residual_norm, clamped, pass_gate)


def load_response_matrix(path: Path) -> Matrix:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    matrix = payload.get("response_matrix_world_delta_per_joint_rad")
    if matrix is None:
        matrix = payload.get("response_matrix_world_delta_per_raw_action")
    if matrix is None:
        raise ValueError(f"{path} has no response matrix")
    if not isinstance(matrix, list):
        raise ValueError(f"{path} response matrix must be a list")
    return validate_response_matrix(matrix)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("--desired-delta", required=True, help="Comma-separated world delta, e.g. 0,0,-0.0015")
    parser.add_argument("--damping", type=float, default=1.0e-4)
    parser.add_argument("--max-joint-delta", type=float, default=0.04)
    parser.add_argument("--min-cosine", type=float, default=0.50)
    parser.add_argument("--max-residual-ratio", type=float, default=0.75)
    args = parser.parse_args()

    desired = [float(part) for part in args.desired_delta.split(",")]
    command = compute_joint_response_command(
        load_response_matrix(args.summary_json),
        desired,
        damping=args.damping,
        max_joint_delta=args.max_joint_delta,
        min_cosine=args.min_cosine,
        max_residual_ratio=args.max_residual_ratio,
    )
    print(json.dumps(command.__dict__, indent=2, sort_keys=True))
    return 0 if command.pass_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
