#!/usr/bin/env python3
"""Local behavior tests for project gate scripts.

These tests are intentionally offline: they do not call Brev, Isaac, Docker, or
the network. A tiny fake Brev CLI is used to exercise paid preflight behavior.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import hashlib
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]


def scrub_gate_env(env: dict[str, str]) -> dict[str, str]:
    """Keep tests independent from paid-run variables in the parent shell."""
    return {
        key: value
        for key, value in env.items()
        if not key.startswith(("RCA_", "FAKE_BREV_")) and key != "BREV_BIN"
    }


def run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = scrub_gate_env(os.environ.copy())
    if env:
        merged_env.update(env)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def assert_status(result: subprocess.CompletedProcess[str], expected: int, label: str) -> None:
    if result.returncode != expected:
        print(f"[gate-tests] FAIL {label}: expected exit {expected}, got {result.returncode}", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        raise SystemExit(1)


def assert_contains(result: subprocess.CompletedProcess[str], needle: str, label: str) -> None:
    if needle not in result.stdout:
        print(f"[gate-tests] FAIL {label}: missing output {needle!r}", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        raise SystemExit(1)


def current_git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def current_payload_sha256() -> str:
    result = subprocess.run(
        ["python3", "scripts/source_payload_fingerprint.py"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def current_payload_scope() -> str:
    result = subprocess.run(
        ["python3", "scripts/source_payload_fingerprint.py", "--scope"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def fingerprint_for(root: Path) -> str:
    result = subprocess.run(
        ["python3", "scripts/source_payload_fingerprint.py", str(root)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def write_fake_brev(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${FAKE_BREV_EXIT:-0}" != "0" ]]; then
  echo "fake brev failure" >&2
  exit "${FAKE_BREV_EXIT}"
fi
if [[ -n "${FAKE_BREV_JSON:-}" ]]; then
  printf '%s\n' "${FAKE_BREV_JSON}"
else
  printf '%s\n' '{"workspaces": null}'
fi
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def write_fake_rsync(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${FAKE_RSYNC_SOURCE:-}" ]]; then
  echo "FAKE_RSYNC_SOURCE is required" >&2
  exit 9
fi
dest="${@: -1}"
cp "${FAKE_RSYNC_SOURCE}" "${dest}"
echo "fake rsync copied ${FAKE_RSYNC_SOURCE} to ${dest}"
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def write_fake_isaac_python(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-m" && "${2:-}" == "pip" ]]; then
  echo "fake pip install $*" >&2
  exit "${FAKE_PIP_EXIT:-0}"
fi
if [[ "${FAKE_ISAAC_EXIT:-0}" != "0" ]]; then
  echo "fake isaac failure" >&2
  exit "${FAKE_ISAAC_EXIT}"
fi
cat <<'EOF'
[INFO]: CONTACT-SMOKE reset-joints: deterministic (synthetic)
[INFO]: CONTACT-SMOKE phase free-space-settle: begin (steps=50, collect_last=10)
[INFO]: CONTACT-SMOKE phase free-space-settle: progress 50/50
[INFO]: CONTACT-SMOKE phase free-space-settle: end
[INFO]: CONTACT-SMOKE attach: PASS
[INFO]: CONTACT-SMOKE free-space: PASS
[INFO]: CONTACT-SMOKE phase local-guide-reanchor: begin (steps=10, collect_last=10)
[INFO]: CONTACT-SMOKE phase local-guide-reanchor: progress 10/10
[INFO]: CONTACT-SMOKE phase local-guide-reanchor: end
[INFO]: CONTACT-SMOKE contact-setup: local-guide reanchored (synthetic)
[INFO]: CONTACT-SMOKE free-space-reanchored: PASS
[INFO]: CONTACT-SMOKE press-control: local-wall-sweep (synthetic)
[INFO]: CONTACT-SMOKE phase press-hold: begin (steps=220, collect_last=30)
[INFO]: CONTACT-SMOKE phase press-hold: progress 220/220
[INFO]: CONTACT-SMOKE phase press-hold: end
[INFO]: CONTACT-SMOKE press-force: PASS
[INFO]: CONTACT-SMOKE press-tracking: PASS
[INFO]: CONTACT-SMOKE press-blocked: PASS
[INFO]: CONTACT-SMOKE press-no-clip: PASS
[INFO]: CONTACT-SMOKE phase retreat-hold: begin (steps=80, collect_last=10)
[INFO]: CONTACT-SMOKE phase retreat-hold: progress 80/80
[INFO]: CONTACT-SMOKE phase retreat-hold: end
[INFO]: CONTACT-SMOKE release: PASS
[INFO]: CONTACT-SMOKE joint-integrity: PASS
[INFO]: CONTACT-SMOKE phase-sequence: PASS (completed=['free-space-settle', 'local-guide-reanchor', 'press-hold', 'retreat-hold'])
[INFO]: Contact physics smoke completed: all checks passed.
EOF
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def write_fake_launchable_repo(path: Path) -> None:
    (path / "source" / "robot_contact_assembly_tasks").mkdir(parents=True)
    (path / "scripts").mkdir()
    for script_name in (
        "check_phase2_contact_gate.py",
        "run_launchable_contact_physics_smoke.sh",
        "source_payload_fingerprint.py",
    ):
        source = REPO_ROOT / "scripts" / script_name
        dest = path / "scripts" / script_name
        dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        dest.chmod(source.stat().st_mode)
    (path / ".rca_launchable_source_manifest.txt").write_text(
        "\n".join(
            [
                "created_utc=2026-06-18T00-00-00Z",
                f"source_repo={REPO_ROOT}",
                f"git_head={current_git_head()}",
                "git_branch=master",
                "git_dirty=1",
                f"source_payload_scope={current_payload_scope()}",
                f"source_payload_sha256={current_payload_sha256()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_contact_log(
    path: Path,
    *,
    fail_marker: bool = False,
    omit_release: bool = False,
    unknown_git_head: bool = False,
    include_source_manifest: bool = False,
    git_head: str | None = None,
    payload_sha256: str | None = None,
    payload_scope: str | None = None,
    omit_payload_scope: bool = False,
    omit_payload_sha256: bool = False,
) -> None:
    source_head = git_head or current_git_head()
    source_payload = payload_sha256 or current_payload_sha256()
    source_scope = payload_scope or current_payload_scope()
    markers = [
        "[contact-smoke] git_head=unknown" if unknown_git_head else f"[contact-smoke] git_head={source_head}",
        "[INFO]: CONTACT-SMOKE reset-joints: deterministic (synthetic)",
        "[INFO]: CONTACT-SMOKE phase free-space-settle: end",
        "[INFO]: CONTACT-SMOKE attach: PASS",
        "[INFO]: CONTACT-SMOKE free-space: PASS",
        "[INFO]: CONTACT-SMOKE phase local-guide-reanchor: end",
        "[INFO]: CONTACT-SMOKE contact-setup: local-guide reanchored (synthetic)",
        "[INFO]: CONTACT-SMOKE free-space-reanchored: PASS",
        "[INFO]: CONTACT-SMOKE press-control: local-wall-sweep (synthetic)",
        "[INFO]: CONTACT-SMOKE phase press-hold: end",
        "[INFO]: CONTACT-SMOKE press-force: PASS",
        "[INFO]: CONTACT-SMOKE press-tracking: PASS",
        "[INFO]: CONTACT-SMOKE press-blocked: PASS",
        "[INFO]: CONTACT-SMOKE press-no-clip: PASS",
        "[INFO]: CONTACT-SMOKE phase retreat-hold: end",
        "[INFO]: CONTACT-SMOKE release: PASS",
        "[INFO]: CONTACT-SMOKE joint-integrity: PASS",
        "[INFO]: CONTACT-SMOKE phase-sequence: PASS (completed=['free-space-settle', 'local-guide-reanchor', 'press-hold', 'retreat-hold'])",
        "[INFO]: Contact physics smoke completed: all checks passed.",
        "[contact-smoke] completed: contact physics is real",
    ]
    if omit_release:
        markers = [line for line in markers if "release: PASS" not in line]
    if include_source_manifest:
        markers[1:1] = [
            "[contact-smoke] source_manifest_begin",
            "[contact-smoke] source_manifest: created_utc=2026-06-18T00-00-00Z",
            f"[contact-smoke] source_manifest: git_head={source_head}",
            "[contact-smoke] source_manifest: git_dirty=1",
        ]
        if not omit_payload_scope:
            markers.insert(-1, f"[contact-smoke] source_manifest: source_payload_scope={source_scope}")
        if not omit_payload_sha256:
            markers.insert(-1, f"[contact-smoke] source_manifest: source_payload_sha256={source_payload}")
        markers.append("[contact-smoke] source_manifest_end")
    if fail_marker:
        markers.append("[ERROR]: CONTACT-SMOKE press-force: FAIL (synthetic)")
    path.write_text("\n".join(markers) + "\n", encoding="utf-8")


def paid_env(fake_brev: Path, **overrides: str) -> dict[str, str]:
    env = {
        "RCA_BREV_CLI": str(fake_brev),
        "RCA_ALLOW_PAID_BREV_CREATE": "1",
        "RCA_BREV_CREDITS_VERIFIED": "1",
        "RCA_PAID_BUDGET_EUR": "1",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR": "10",
        "RCA_PAID_MAX_MINUTES": "5",
        "RCA_PAID_RUN_PURPOSE": "contact_physics_smoke",
        "RCA_PAID_PREFLIGHT_QUERY_TIMEOUT_SECONDS": "5",
        "RCA_BREV_LIFECYCLE_HOLD_FILE": str(REPO_ROOT / ".rca-test-no-brev-lifecycle-hold"),
    }
    env.update(overrides)
    return env


def prepare_env(fake_brev: Path, **overrides: str) -> dict[str, str]:
    env = paid_env(
        fake_brev,
        RCA_CONTACT_SMOKE_TEST_SKIP_LOCAL_QUALITY="1",
        RCA_CONTACT_SMOKE_MAX_MINUTES="5",
    )
    env.pop("RCA_ALLOW_PAID_BREV_CREATE", None)
    env.pop("RCA_PAID_MAX_MINUTES", None)
    env.pop("RCA_PAID_RUN_PURPOSE", None)
    env.update(overrides)
    return env


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_tar_gz(source_dir: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)


def write_video_candidate_trace(path: Path, *, final_lateral: float, success: bool = True) -> None:
    steps = []
    for idx, axial in enumerate((0.060, 0.045, 0.030, 0.006, 0.006, 0.006)):
        steps.append(
            {
                "step": idx,
                "lateral": final_lateral if idx >= 3 else 0.010,
                "axial": axial,
                "rot": 0.020,
                "contact_force_magnitude": 1.2 if idx >= 3 else 0.0,
                "success": bool(success and idx >= 3),
            }
        )
    path.write_text(
        json.dumps(
            {
                "steps": steps,
                "summary": {
                    "initial_axial": 0.060,
                    "best_axial": 0.006,
                    "success_step": 3 if success else None,
                },
            }
        ),
        encoding="utf-8",
    )


def run_socket_insertion_servo_logic_tests() -> None:
    scripts_path = str(REPO_ROOT / "scripts")
    sys.path.insert(0, scripts_path)
    try:
        from socket_insertion_servo_logic import (
            SocketInsertionServoConfig,
            compute_socket_insertion_servo_offset_scalar,
        )
    finally:
        try:
            sys.path.remove(scripts_path)
        except ValueError:
            pass

    config = SocketInsertionServoConfig(
        xy_gain=1.0,
        xy_clamp=0.002,
        z_gain=1.0,
        z_step=0.0015,
        descend_xy_tolerance=0.005,
        descend_rot_tolerance=0.18,
        success_z_tolerance=0.008,
        contact_preload_step=0.0007,
        success_min_contact_force=0.5,
        contact_boundary_min_force=0.25,
        contact_boundary_tolerance=0.001,
        contact_boundary_step=0.00015,
        contact_boundary_xy_gain=0.0,
        contact_boundary_xy_clamp=0.0,
    )
    cases = [
        ((0.010, -0.010, 0.030), 0.010, 0.030, 0.020, 1.0, True),
        ((0.003, 0.004, 0.030), 0.003, 0.030, 0.050, 1.0, True),
        ((0.003, 0.004, 0.030), 0.003, 0.030, 0.250, 1.0, True),
        ((0.002, -0.001, 0.004), 0.002, 0.004, 0.050, 0.0, True),
        ((0.0002, 0.0003, 0.00798), 0.0004, 0.00798, 0.050, 0.30, True),
        ((0.0002, 0.0003, 0.00812), 0.0004, 0.00812, 0.050, 1.0, True),
        ((0.0002, 0.0003, 0.00812), 0.0004, 0.00812, 0.050, 0.30, True),
        ((0.003, 0.004, 0.030), 0.003, 0.030, 0.050, 1.0, False),
    ]
    results = [
        compute_socket_insertion_servo_offset_scalar(*case, config)
        for case in cases
    ]
    maintain_config = SocketInsertionServoConfig(
        xy_gain=1.0,
        xy_clamp=0.002,
        z_gain=1.0,
        z_step=0.0015,
        descend_xy_tolerance=0.005,
        descend_rot_tolerance=0.18,
        success_z_tolerance=0.008,
        contact_preload_step=0.0007,
        success_min_contact_force=0.5,
        contact_boundary_min_force=0.25,
        contact_boundary_tolerance=0.001,
        contact_boundary_step=0.00015,
        contact_boundary_xy_gain=0.0,
        contact_boundary_xy_clamp=0.0,
        maintain_contact_preload=True,
    )
    maintained_offset, maintained_masks = compute_socket_insertion_servo_offset_scalar(
        (0.002, -0.001, 0.004),
        0.002,
        0.004,
        0.050,
        1.0,
        True,
        maintain_config,
    )
    boundary_xy_config = SocketInsertionServoConfig(
        xy_gain=1.0,
        xy_clamp=0.002,
        z_gain=1.0,
        z_step=0.0015,
        descend_xy_tolerance=0.005,
        descend_rot_tolerance=0.18,
        success_z_tolerance=0.008,
        contact_preload_step=0.0007,
        success_min_contact_force=0.5,
        contact_boundary_min_force=0.25,
        contact_boundary_tolerance=0.001,
        contact_boundary_step=0.00015,
        contact_boundary_xy_gain=0.15,
        contact_boundary_xy_clamp=0.00035,
        maintain_contact_preload=True,
    )
    boundary_xy_offset, boundary_xy_masks = compute_socket_insertion_servo_offset_scalar(
        (0.002, -0.003, 0.004),
        0.0036,
        0.004,
        0.050,
        1.0,
        True,
        boundary_xy_config,
    )
    offsets = [result[0] for result in results]
    masks = [result[1] for result in results]
    expected_xy = (
        (-0.002, 0.002),
        (-0.002, -0.002),
        (-0.002, -0.002),
        (-0.002, 0.001),
        (0.000, 0.000),
        (0.000, 0.000),
        (0.000, 0.000),
        (0.000, 0.000),
    )
    for idx, (offset, expected) in enumerate(zip(offsets, expected_xy, strict=True)):
        if any(abs(offset[axis] - expected[axis]) > 1.0e-7 for axis in (0, 1)):
            raise AssertionError(f"socket servo XY offsets wrong at case {idx}: {offset}")
    if offsets[0][2] != 0.0 or not masks[0]["hold_z"]:
        raise AssertionError("socket servo negative control failed: lateral miss should hold Z")
    if offsets[1][2] >= 0.0 or not masks[1]["descend_ready"]:
        raise AssertionError("socket servo should descend when XY and rotation are ready")
    if offsets[2][2] != 0.0 or masks[2]["descend_ready"]:
        raise AssertionError("socket servo negative control failed: rotation miss should hold Z")
    if abs(offsets[3][2] + 0.0007) > 1.0e-8 or not masks[3]["contact_preload"]:
        raise AssertionError("socket servo should preload only when axial-ready but contact is missing")
    if offsets[3][2] != 0.0 and masks[3]["hold_z"]:
        raise AssertionError("contact-preload and hold-z masks must be exclusive")
    if abs(offsets[4][2] + 0.00015) > 1.0e-8 or not masks[4]["contact_boundary_preload"]:
        raise AssertionError("low-but-real contact in the success window should use boundary micro-preload")
    if any(abs(offsets[4][axis]) > 1.0e-8 for axis in (0, 1)):
        raise AssertionError("boundary preload should not keep applying normal XY corrections")
    if abs(maintained_offset[2] + 0.00015) > 1.0e-8 or not maintained_masks["contact_preload"]:
        raise AssertionError("maintain-contact preload should keep only a boundary micro-preload in the success window")
    if any(abs(maintained_offset[axis]) > 1.0e-8 for axis in (0, 1)):
        raise AssertionError("maintain-contact preload should not keep applying normal XY corrections after contact")
    if not maintained_masks["maintained_contact_preload"]:
        raise AssertionError("maintain-contact preload should expose a dedicated maintained-contact mask")
    if not maintained_masks["contact_boundary_preload"]:
        raise AssertionError("maintain-contact preload should also be marked as boundary preload")
    if not maintained_masks["contact_ready"] or maintained_masks["hold_z"]:
        raise AssertionError("maintain-contact preload must preserve contact evidence while disabling hold-z")
    if abs(boundary_xy_offset[0] + 0.0003) > 1.0e-8:
        raise AssertionError(f"boundary XY gain should apply a small X correction: {boundary_xy_offset}")
    if abs(boundary_xy_offset[1] - 0.00035) > 1.0e-8:
        raise AssertionError(f"boundary XY clamp should cap the Y correction: {boundary_xy_offset}")
    if abs(boundary_xy_offset[2] + 0.00015) > 1.0e-8:
        raise AssertionError("boundary XY correction must retain only the micro preload Z step")
    if not boundary_xy_masks["maintained_contact_preload"] or not boundary_xy_masks["contact_boundary_preload"]:
        raise AssertionError("boundary XY correction should stay in maintained boundary-preload mode")
    if abs(offsets[5][2] + 0.00012) > 1.0e-8 or not masks[5]["contact_boundary"]:
        raise AssertionError("socket servo should step only to the axial boundary, not normal-descend past it")
    if abs(offsets[6][2] + 0.00012) > 1.0e-8 or not masks[6]["contact_boundary"]:
        raise AssertionError("socket servo boundary should tolerate low-but-real contact force flicker")
    if masks[6]["contact_ready"] or not masks[6]["boundary_contact_ready"]:
        raise AssertionError("boundary contact threshold must not relax the task success contact threshold")
    if masks[5]["descend_ready"]:
        raise AssertionError("socket servo near-contact boundary must not use the normal descent path")
    if any(abs(value) > 1.0e-8 for value in offsets[7]):
        raise AssertionError("socket servo inactive rows must produce zero offset")


def _write_boundary_trace(path: Path, *, success: bool, unsafe: bool, contact: bool = True) -> None:
    steps: list[dict[str, object]] = []
    for idx in range(8):
        in_success_window = success and idx >= 3
        near_boundary = idx >= 2
        axial = 0.0075 if in_success_window else (0.00812 if near_boundary else 0.020)
        lateral = 0.0007 if near_boundary else 0.002
        if unsafe and idx == 4:
            lateral = 0.031
            axial = 0.017
        offset_z = -0.0015 if unsafe and idx == 3 else (-0.00004 if near_boundary else -0.0005)
        steps.append(
            {
                "step": idx,
                "phase": "socket-insertion-servo",
                "lateral": lateral,
                "axial": axial,
                "rot": 0.04,
                "contact_force_magnitude": 1.2 if contact and near_boundary else 0.0,
                "socket_insertion_servo_contact_boundary": near_boundary and contact and not in_success_window and not unsafe,
                "socket_insertion_servo_offset_socket": [0.0, 0.0, offset_z],
                "success": in_success_window and contact,
            }
        )
    path.write_text(json.dumps({"steps": steps, "summary": {"success_step": 3 if success and contact else None}}))


def run_final_contact_boundary_diagnostic_tests() -> None:
    scripts_path = str(REPO_ROOT / "scripts")
    sys.path.insert(0, scripts_path)
    try:
        from check_final_contact_boundary_diagnostic import evaluate_trace
    finally:
        try:
            sys.path.remove(scripts_path)
        except ValueError:
            pass

    with tempfile.TemporaryDirectory(prefix="rca-boundary-diagnostic-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        positive_path = tmp_dir / "positive.json"
        negative_path = tmp_dir / "negative.json"
        unsafe_path = tmp_dir / "unsafe.json"
        _write_boundary_trace(positive_path, success=True, unsafe=False)
        _write_boundary_trace(negative_path, success=True, unsafe=False, contact=False)
        _write_boundary_trace(unsafe_path, success=False, unsafe=True)

        kwargs = {
            "xy_tol": 0.005,
            "axial_tol": 0.008,
            "rot_tol": 0.18,
            "contact_min_force": 0.5,
            "boundary_contact_min_force": 0.25,
            "boundary_axial_band": 0.001,
            "max_boundary_step": 0.00015,
            "pop_lateral_jump": 0.010,
            "pop_lateral_abs": 0.020,
            "pop_axial_regress": 0.004,
            "sustained_steps": 3,
        }
        positive = evaluate_trace(json.loads(positive_path.read_text()), **kwargs)
        negative = evaluate_trace(json.loads(negative_path.read_text()), **kwargs)
        unsafe = evaluate_trace(json.loads(unsafe_path.read_text()), **kwargs)
        if not positive["pass_gate"]:
            raise AssertionError(f"final-contact boundary diagnostic should pass stable synthetic trace: {positive}")
        if negative["pass_gate"]:
            raise AssertionError(f"final-contact boundary diagnostic negative control must fail: {negative}")
        if unsafe["pass_gate"]:
            raise AssertionError(f"final-contact boundary diagnostic must fail unsafe pop trace: {unsafe}")
        if unsafe["unsafe_boundary_descent_count"] < 1 or unsafe["pop_event_count"] < 1:
            raise AssertionError(f"unsafe synthetic trace should report both normal descent and pop: {unsafe}")

    known_failure = REPO_ROOT / "artifacts/videos/trace_only/2026-06-21T10-22-58Z/video_trace.json"
    if known_failure.exists():
        result = run(["python3", "scripts/check_final_contact_boundary_diagnostic.py", str(known_failure)])
        assert_status(result, 1, "final-contact boundary diagnostic rejects known 8mm pop trace")
        assert_contains(
            result,
            "controller used a normal descent step after contact near the axial boundary",
            "known boundary failure unsafe descent detail",
        )
        assert_contains(
            result,
            "trace popped laterally or axially after reaching the contact boundary",
            "known boundary failure pop detail",
        )


def run_joint_response_control_tests() -> None:
    scripts_path = str(REPO_ROOT / "scripts")
    sys.path.insert(0, scripts_path)
    try:
        from joint_response_control import compute_joint_response_command, load_response_matrix
    finally:
        try:
            sys.path.remove(scripts_path)
        except ValueError:
            pass

    # Synthetic 3x7 measured Jacobian with nontrivial off-axis coupling. The
    # controller should still find a small minimum-norm joint command whose
    # predicted action-frame motion points in the requested direction.
    usable_matrix = [
        [0.020, 0.002, 0.000, 0.004, 0.001, 0.000, 0.000],
        [0.001, 0.018, 0.003, 0.000, 0.002, 0.000, 0.000],
        [0.000, 0.002, 0.022, -0.004, 0.000, 0.012, 0.003],
    ]
    down = compute_joint_response_command(
        usable_matrix,
        (0.0, 0.0, -0.0015),
        max_joint_delta=0.04,
        min_cosine=0.85,
        max_residual_ratio=0.25,
    )
    up = compute_joint_response_command(
        usable_matrix,
        (0.0, 0.0, 0.0015),
        max_joint_delta=0.04,
        min_cosine=0.85,
        max_residual_ratio=0.25,
    )
    if not down.pass_gate or down.cosine is None or down.cosine < 0.85:
        raise AssertionError(f"joint-response controller should pass down command: {down}")
    if not up.pass_gate or up.cosine is None or up.cosine < 0.85:
        raise AssertionError(f"joint-response controller should pass up command: {up}")
    if down.predicted_delta[2] >= 0.0 or up.predicted_delta[2] <= 0.0:
        raise AssertionError(f"joint-response controller got Z signs wrong: down={down} up={up}")

    no_z_matrix = [
        [0.020, 0.002, 0.000, 0.004, 0.001, 0.000, 0.000],
        [0.001, 0.018, 0.003, 0.000, 0.002, 0.000, 0.000],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ]
    blocked = compute_joint_response_command(
        no_z_matrix,
        (0.0, 0.0, -0.0015),
        max_joint_delta=0.04,
        min_cosine=0.50,
        max_residual_ratio=0.25,
    )
    if blocked.pass_gate:
        raise AssertionError(f"joint-response controller must fail closed without Z authority: {blocked}")

    known_good = REPO_ROOT / "artifacts/calibration/joint_position_action/2026-06-21T10-21-39Z/seed_42.json"
    if known_good.exists():
        good_down = compute_joint_response_command(
            load_response_matrix(known_good),
            (0.0, 0.0, -0.0015),
            max_joint_delta=0.04,
            min_cosine=0.85,
            max_residual_ratio=0.25,
        )
        if not good_down.pass_gate:
            raise AssertionError(f"known 8-step joint-response calibration should pass: {good_down}")

    known_underconverged = REPO_ROOT / "artifacts/calibration/joint_position_action/2026-06-23T00-40-06Z/seed_42.json"
    if known_underconverged.exists():
        underconverged_down = compute_joint_response_command(
            load_response_matrix(known_underconverged),
            (0.0, 0.0, -0.0015),
            max_joint_delta=0.04,
            min_cosine=0.85,
            max_residual_ratio=0.25,
        )
        if underconverged_down.pass_gate:
            raise AssertionError(
                "under-converged 4-step joint-response calibration should fail closed: "
                f"{underconverged_down}"
            )


def run_scripted_agent_quaternion_static_tests() -> None:
    scripted_agent = (REPO_ROOT / "scripts" / "scripted_agent.py").read_text(encoding="utf-8")
    forbidden = "legacy `(x, y, z, w)`"
    if forbidden in scripted_agent:
        raise AssertionError("scripted_agent.py still documents the default quaternion helper as legacy XYZW")
    forbidden_socket_mask_alias = "socket_insertion_servo_rotate_mask = socket_insertion_servo_mask\n"
    if forbidden_socket_mask_alias in scripted_agent:
        raise AssertionError("socket servo rotate mask must clone the activation mask before in-place filtering")
    required_snippets = [
        '"""Hamilton product for Isaac Lab WXYZ quaternions."""',
        "w1, x1, y1, z1 = lhs.unbind(dim=-1)",
        "vec_quat = torch.cat((zeros, vec), dim=-1)",
        "return rotated[..., 1:]",
        "def _child_pose_to_parent_pose_xyzw(",
        '"""Invert `child = parent * offset` for IsaacLab transform quats stored as XYZW.',
        "x1, y1, z1, w1 = lhs.unbind(dim=-1)",
        "vec_quat = torch.cat((vec, zeros), dim=-1)",
        "parent_pos_w = child_pos_w + _quat_rotate_xyzw(child_quat_w, inv_offset_pos)",
        "parent_quat_w = _normalize_quat(_quat_multiply_xyzw(child_quat_w, inv_offset_quat))",
        "hand_target_pos_w, hand_target_quat_w = _child_pose_to_parent_pose_xyzw(",
        "quat = torch.cat((1.0 + dot, axis), dim=-1)",
        "quat = torch.cat((torch.cos(half_angle), axis * torch.sin(half_angle)), dim=-1)",
        "quat[small_angle] = axis_angle.new_tensor((1.0, 0.0, 0.0, 0.0))",
        "peg_tip_pos_w, peg_tip_quat_w = _metric_peg_tip_pose_w(env_unwrapped, SceneEntityCfg(\"peg\"))",
        "return peg_tip_pos_w.detach().clone(), peg_tip_quat_w.detach().clone()",
        "socket_insertion_servo_soft_exit_mask",
        "socket_insertion_servo_recovery_mask",
        "socket_insertion_servo_strict_exit",
        "phase = \"socket-insertion-servo-recover\"",
        "socket_insertion_servo_rotate_while_xy_misaligned",
        "socket_insertion_servo_rotate_only_when_rot_misaligned",
        "socket_insertion_servo_rotate_mask = socket_insertion_servo_mask.clone()",
        "socket_insertion_servo_rotate_mask &= ~socket_insertion_servo_rot_ready_mask",
        "socket_insertion_servo_contact_boundary_mask",
        "socket_insertion_servo_contact_boundary_count",
        "socket_insertion_servo_contact_boundary_min_force",
        "socket_insertion_servo_contact_boundary_tolerance",
        "socket_insertion_servo_contact_boundary_step",
        "socket_insertion_servo_contact_boundary_xy_gain",
        "socket_insertion_servo_contact_boundary_xy_clamp",
        "socket_insertion_servo_maintain_contact_preload",
        "socket_insertion_servo_boundary_contact_ready_mask",
        "socket_insertion_servo_orientation_hold_mask",
        "socket_insertion_servo_orientation_hold_count",
        "_write_json_atomic",
        "os.replace(tmp_path, abs_path)",
        "--trace-autoflush-every",
        "atexit.register(_write_unexpected_exit_trace_artifacts)",
        "trace_artifacts_finalized",
        "last_partial_summary",
        "_append_jsonl",
        "signal.signal(signal.SIGTERM, _handle_termination_signal)",
        "signal.signal(signal.SIGINT, _handle_termination_signal)",
        "trace_artifacts_finalized[\"value\"] = True",
        "\"event\": \"step_begin\"",
        "\"event\": \"after_env_step\"",
        "\"event\": \"trace_row_appended\"",
        "\"event\": \"control_loop_exit\"",
        "\"artifact_label\": \"atexit-without-summary\"",
        "\"artifact_status\": \"partial\"",
        "\"artifact_status\": \"complete\"",
        "before_socket_insertion_servo_offset",
        "after_socket_insertion_servo_offset",
        "skipped_socket_insertion_servo_metric_reductions",
        "detailed metrics are still preserved in trace rows",
        "--action-semantics-probe-delta",
        "phase = \"action-semantics-probe\"",
        "\"action_semantics_probe_delta_w\"",
        "def _hold_current_or_zero_actions()",
        "warmup_mode = \"hold-current-joints\" if action_dim == 7 else \"zero-relative-action\"",
        "--joint-response-json",
        "def _load_joint_response_matrix(",
        "choices=(\"auto\", \"mdp\", \"joint-ik\", \"joint-response\")",
        "scripted_control_mode == \"joint-response\"",
        "joint_response_matrix @ joint_response_matrix.transpose(0, 1)",
        "\"joint_response_predicted_delta\"",
        "--disable-insertion-success-termination",
        "terminations_cfg.insertion_success = None",
        "\"insertion_success_termination_disabled\"",
        "--success-hold-steps",
        "--socket-insertion-servo-maintain-contact-preload",
        "--reset-joint-noise-rad",
        "reset_joints_by_offset",
        "\"reset_joint_noise_rad\": reset_joint_noise_rad",
        "\"variation_case_id\": os.environ.get(\"RCA_TRACE_VARIATION_CASE_ID\")",
        "\"variation_socket_delta_m\": os.environ.get(\"RCA_TRACE_VARIATION_SOCKET_DELTA_M\")",
        "\"event\": \"post_success_hold_action\"",
        "\"mode\": post_success_hold_mode",
        "\"event\": \"success_hold_break\"",
        "\"success_hold_steps\"",
        "\"post_success_hold_mode\"",
        "post_success_hold_step_count",
        "socket-servo-maintain-contact-preload",
        "def _make_debug_camera(",
        "from isaaclab.sensors.camera import Camera, CameraCfg",
        "choices=(\"viewport\", \"camera\")",
        "args_cli.video_backend in (\"viewport\", \"camera\")",
        "video_camera = _make_debug_camera(",
        "video_writer.append_data(_frame_to_uint8(video_camera.data.output[\"rgb\"][0]))",
        "\"video_frames_written\": video_frames_written if args_cli.video else 0",
        "closed camera video writer",
    ]
    for snippet in required_snippets:
        if snippet not in scripted_agent:
            raise AssertionError(f"scripted_agent.py is missing quaternion/action-frame safety snippet: {snippet}")


def run_isaac_launcher_import_order_static_tests() -> None:
    """Keep Isaac task registration out of module scope before SimulationApp starts."""

    script_path = REPO_ROOT / "scripts" / "calibrate_joint_position_action.py"
    tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
    forbidden_modules = {
        "gymnasium",
        "isaaclab_tasks.utils",
        "robot_contact_assembly_tasks.tasks",
        "torch",
        "warp",
    }
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_modules:
                    raise AssertionError(
                        "calibrate_joint_position_action.py imports Isaac runtime-dependent modules "
                        f"at module scope ({alias.name}); import them only after SimulationApp starts"
                    )
        if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
            raise AssertionError(
                "calibrate_joint_position_action.py imports Isaac runtime-dependent modules "
                f"at module scope ({node.module}); import them only after SimulationApp starts"
            )


def run_joint_response_socket_wrapper_static_tests() -> None:
    """Guard the metric-tip insertion retry against falling back to the failed joint-IK path."""

    run_script = (
        REPO_ROOT / "scripts" / "run_remote_joint_response_socket_insertion_servo_trace.sh"
    ).read_text(encoding="utf-8")
    recreate_script = (
        REPO_ROOT / "scripts" / "recreate_brev_and_run_joint_response_socket_insertion_servo_trace.sh"
    ).read_text(encoding="utf-8")

    required_run_snippets = [
        "run_remote_joint_response_calibration.sh",
        'SUMMARY_PATH="/workspace/artifacts/calibration/joint_position_action/latest_seed_${SEED}.json"',
        '--joint-response-json "${SUMMARY_PATH}"',
        'REUSE_CALIBRATION="${RCA_JOINT_RESPONSE_SOCKET_REUSE_CALIBRATION:-0}"',
        'rca_remote_container_exec "test -s',
        "reusing existing calibration",
        "--socket-insertion-servo-rotate-only-when-rot-misaligned",
        'RCA_JOINT_RESPONSE_SOCKET_SUCCESS_HOLD_STEPS:-5',
        "--trace-autoflush-every",
        'RCA_VALIDATE_FINAL_CONTACT_BOUNDARY="${RCA_JOINT_RESPONSE_SOCKET_VALIDATE_FINAL_CONTACT_BOUNDARY:-1}"',
        "RCA_SOCKET_INSERTION_SERVO_CONTROL_MODE=joint-response",
        'RCA_SOCKET_INSERTION_SERVO_Z_STEP="${RCA_JOINT_RESPONSE_SOCKET_Z_STEP:-0.0005}"',
        'RCA_SOCKET_INSERTION_SERVO_CONTACT_PRELOAD_STEP="${RCA_JOINT_RESPONSE_SOCKET_CONTACT_PRELOAD_STEP:-0.0002}"',
        'RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_TOL="${RCA_JOINT_RESPONSE_SOCKET_CONTACT_BOUNDARY_TOL:-0.0010}"',
        'RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_STEP="${RCA_JOINT_RESPONSE_SOCKET_CONTACT_BOUNDARY_STEP:-0.00015}"',
        'RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_XY_GAIN="${RCA_JOINT_RESPONSE_SOCKET_CONTACT_BOUNDARY_XY_GAIN:-0.15}"',
        'RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_XY_CLAMP="${RCA_JOINT_RESPONSE_SOCKET_CONTACT_BOUNDARY_XY_CLAMP:-0.00035}"',
        'RCA_SOCKET_INSERTION_SERVO_MAINTAIN_CONTACT_PRELOAD="${RCA_JOINT_RESPONSE_SOCKET_MAINTAIN_CONTACT_PRELOAD:-1}"',
        'RCA_ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_JOINT_RESPONSE_SOCKET_ACTION_RESPONSE_MIN_COMMAND_NORM:-0.0002}"',
        'RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS="${JOINT_RESPONSE_ARGS[*]}"',
        "run_remote_socket_insertion_servo_trace.sh",
        'RCA_VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE:-1}"',
    ]
    for snippet in required_run_snippets:
        if snippet not in run_script:
            raise AssertionError(
                "run_remote_joint_response_socket_insertion_servo_trace.sh is missing "
                f"required joint-response socket snippet: {snippet}"
            )

    if "--scripted-control-mode joint-response" in run_script:
        raise AssertionError(
            "joint-response socket wrapper should select joint-response through "
            "RCA_SOCKET_INSERTION_SERVO_CONTROL_MODE, not by appending a duplicate control-mode CLI flag"
        )

    required_recreate_snippets = [
        'RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE:-1}"',
        'RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_joint_response_socket_insertion_servo_trace.sh"',
        "recreate_brev_and_run_final_contact_servo_trace.sh",
        'STEPS="${5:-1200}"',
        'SEED="${6:-42}"',
    ]
    for snippet in required_recreate_snippets:
        if snippet not in recreate_script:
            raise AssertionError(
                "recreate_brev_and_run_joint_response_socket_insertion_servo_trace.sh is missing "
                f"required delegation snippet: {snippet}"
            )


def run_trace_only_runtime_profile_static_tests() -> None:
    """Keep trace-only paid diagnostics from reinstalling optional training dependencies."""

    install_script = (REPO_ROOT / "scripts" / "install_remote_isaaclab_runtime.sh").read_text(
        encoding="utf-8"
    )
    record_script = (REPO_ROOT / "scripts" / "run_remote_record_scripted_video.sh").read_text(
        encoding="utf-8"
    )
    trace_recreate_script = (
        REPO_ROOT / "scripts" / "recreate_brev_and_run_final_contact_servo_trace.sh"
    ).read_text(encoding="utf-8")
    trace_only_script = (
        REPO_ROOT / "scripts" / "run_remote_scripted_trace_only.sh"
    ).read_text(encoding="utf-8")

    required_install_snippets = [
        'RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-full}"',
        'ISAACLAB_GIT_REF="${RCA_ISAACLAB_GIT_REF:-develop}"',
        "RCA_ISAACLAB_GIT_REF=${ISAACLAB_GIT_REF_Q} bash -s",
        '-e RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE}"',
        '-e RCA_ISAACLAB_GIT_REF="${RCA_ISAACLAB_GIT_REF}"',
        'RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-full}"',
        'RCA_ISAACLAB_GIT_REF="${RCA_ISAACLAB_GIT_REF:-develop}"',
        'git clone --depth 1 --branch "${RCA_ISAACLAB_GIT_REF}" https://github.com/isaac-sim/IsaacLab.git',
        'git ls-remote --exit-code --tags origin "${RCA_ISAACLAB_GIT_REF}"',
        "[runtime] installing IsaacLab ref ${RCA_ISAACLAB_GIT_REF} with profile ${RCA_ISAACLAB_RUNTIME_PROFILE}",
        "set +e",
        'if [ "${status}" -eq 0 ]; then',
        "install_editable_package()",
        "install_isaaclab_core_runtime()",
        "validate_runtime_imports()",
        'if os.environ.get("RCA_ISAACLAB_RUNTIME_PROFILE") in {"camera", "viewport"}:',
        "rendering profile requires a warp package with warp.context",
        "rendering profile requires a warp package with warp.types.array",
        "[runtime-import] OK rendering warp compatibility",
        'export TERM="${TERM:-xterm-256color}"',
        '/isaac-sim/python.sh -m pip install "setuptools<80"',
        "/isaac-sim/python.sh -m pip install --no-build-isolation flatdict==4.0.1",
        "/isaac-sim/python.sh -m pip install --no-build-isolation --editable",
        'if [ "${RCA_ISAACLAB_RUNTIME_PROFILE}" = "trace-only" ]; then',
        "[runtime] trace-only profile: installing required IsaacLab runtime submodules only",
        "/workspace/IsaacLab/source/isaaclab_tasks",
        "/workspace/IsaacLab/source/isaaclab_rl",
        "/isaac-sim/python.sh -m pip install warp-lang==1.12.1 pillow==12.1.1",
        "[runtime] trace-only profile: skipping optional IsaacLab contrib/newton/visualizer/rsl-rl explicit installs",
        'elif [ "${RCA_ISAACLAB_RUNTIME_PROFILE}" = "camera" ]; then',
        "[runtime] camera profile: installing headless IsaacLab runtime plus video writer dependencies",
        "/isaac-sim/python.sh -m pip install warp-lang==1.12.1 pillow==12.1.1 imageio imageio-ffmpeg",
        "[runtime] camera profile: skipping optional IsaacLab contrib/newton/visualizer/rsl-rl explicit installs",
        'elif [ "${RCA_ISAACLAB_RUNTIME_PROFILE}" = "viewport" ]; then',
        "[runtime] viewport profile: installing IsaacLab runtime plus screen/video dependencies",
        "/isaac-sim/python.sh -m pip install warp-lang==1.12.1 imageio imageio-ffmpeg",
        "[runtime] viewport profile: skipping optional training extras",
        'install_editable_package /workspace/IsaacLab/source/isaaclab_contrib optional',
        "importlib.util.find_spec(module_name)",
        "robot_contact_assembly_tasks",
    ]
    for snippet in required_install_snippets:
        if snippet not in install_script:
            raise AssertionError(
                "install_remote_isaaclab_runtime.sh is missing trace-only runtime profile "
                f"snippet: {snippet}"
            )
    if "./isaaclab.sh --install assets,physx,tasks" in install_script:
        raise AssertionError(
            "trace-only runtime must not use invalid IsaacLab install tokens that fall back to broad installs"
        )

    required_camera_record_snippets = [
        'FORCE_APP_LAUNCHER="${RCA_RECORD_SCRIPTED_FORCE_APP_LAUNCHER:-${RCA_FORCE_APP_LAUNCHER:-0}}"',
        'SCRIPTED_VIS_ARGS="${RCA_RECORD_SCRIPTED_VIS_ARGS:-}"',
        'if [[ "${VIDEO_BACKEND}" == "camera" ]]; then',
        'FORCE_APP_LAUNCHER="${RCA_RECORD_SCRIPTED_FORCE_APP_LAUNCHER:-${RCA_FORCE_APP_LAUNCHER:-1}}"',
        'SCRIPTED_VIS_ARGS="${RCA_RECORD_SCRIPTED_VIS_ARGS:---viz none}"',
        'echo "[record-scripted] force_app_launcher=${FORCE_APP_LAUNCHER}"',
        "export RCA_FORCE_APP_LAUNCHER='${FORCE_APP_LAUNCHER}'",
        "scripts/scripted_agent.py ${SCRIPTED_VIS_ARGS} --task",
    ]
    for snippet in required_camera_record_snippets:
        if snippet not in record_script:
            raise AssertionError(
                "run_remote_record_scripted_video.sh is missing camera launcher protection "
                f"snippet: {snippet}"
            )

    required_trace_recreate_snippets = [
        'RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-trace-only}"',
        'RCA_SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-1}"',
        "install_remote_isaaclab_runtime.sh",
        "running trace-only final-contact servo validation",
        'VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE:-${RCA_VALIDATE_PEG_VIDEO_CANDIDATE:-1}}"',
        'RCA_VALIDATE_PEG_VIDEO_CANDIDATE="${VALIDATE_PEG_VIDEO_CANDIDATE}"',
        "peg video candidate validation was disabled",
    ]
    for snippet in required_trace_recreate_snippets:
        if snippet not in trace_recreate_script:
            raise AssertionError(
                "recreate_brev_and_run_final_contact_servo_trace.sh is missing trace-only "
                f"runtime profile snippet: {snippet}"
            )

    required_trace_only_snippets = [
        'TRACE_DIR_NAME="${RCA_TRACE_ONLY_DIR_NAME:-}"',
        'TRACE_REMOTE_DIR_OVERRIDE="${RCA_TRACE_ONLY_REMOTE_DIR:-}"',
        'REMOTE_TRACE_DIR="${TRACE_REMOTE_DIR_OVERRIDE:-/workspace/artifacts/videos/trace_only/${TRACE_DIR_NAME}}"',
        'TRACE_VARIATION_CASE_ID="${RCA_TRACE_VARIATION_CASE_ID:-}"',
        "export RCA_TRACE_VARIATION_CASE_ID='${TRACE_VARIATION_CASE_ID}'",
        "export RCA_TRACE_VARIATION_SOCKET_DELTA_M='${TRACE_VARIATION_SOCKET_DELTA_M}'",
        "export RCA_TRACE_VARIATION_RESET_JOINT_NOISE_RAD='${TRACE_VARIATION_RESET_JOINT_NOISE_RAD}'",
    ]
    for snippet in required_trace_only_snippets:
        if snippet not in trace_only_script:
            raise AssertionError(
                "run_remote_scripted_trace_only.sh is missing variation trace directory/metadata "
                f"snippet: {snippet}"
            )


def run_video_candidate_xvfb_static_tests() -> None:
    """Keep paid video attempts from losing display-startup diagnostics."""

    video_recreate_script = (
        REPO_ROOT / "scripts" / "recreate_brev_and_record_peg_video_candidate.sh"
    ).read_text(encoding="utf-8")

    required_snippets = [
        "start_container_xvfb()",
        "copy_xvfb_logs()",
        "/workspace/artifacts/runtime/rca-xvfb.log",
        "Xvfb :99 -screen 0 1280x720x24 -ac -nolisten tcp -extension GLX",
        "for _ in $(seq 1 20); do",
        'RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99"',
    ]
    for snippet in required_snippets:
        if snippet not in video_recreate_script:
            raise AssertionError(
                "recreate_brev_and_record_peg_video_candidate.sh is missing robust Xvfb "
                f"startup snippet: {snippet}"
            )
    brittle_snippet = "nohup Xvfb :99 -screen 0 1280x720x24 -ac >/tmp/rca-xvfb.log 2>&1 & sleep 2"
    if brittle_snippet in video_recreate_script:
        raise AssertionError("video candidate wrapper still has brittle Xvfb startup")


def run_video_candidate_screen_recording_static_tests() -> None:
    """Keep paid video attempts on the screen-capture path with semantic validators."""

    video_recreate_script = (
        REPO_ROOT / "scripts" / "recreate_brev_and_record_peg_video_candidate.sh"
    ).read_text(encoding="utf-8")
    screen_script = (
        REPO_ROOT / "scripts" / "run_remote_record_scripted_screen_video.sh"
    ).read_text(encoding="utf-8")

    required_recreate_snippets = [
        'RECORDING_MODE="${RCA_VIDEO_CANDIDATE_RECORDING_MODE:-screen}"',
        'CALIBRATION_STEPS_PER_PROBE="${RCA_VIDEO_CANDIDATE_CALIBRATION_STEPS_PER_PROBE:-8}"',
        'CALIBRATION_TIMEOUT_SECONDS="${RCA_VIDEO_CANDIDATE_CALIBRATION_TIMEOUT_SECONDS:-900}"',
        'CALIBRATION_DOWN_DELTA="${RCA_VIDEO_CANDIDATE_CALIBRATION_DOWN_DELTA:-0,0,-0.0002}"',
        'CALIBRATION_UP_DELTA="${RCA_VIDEO_CANDIDATE_CALIBRATION_UP_DELTA:-0,0,0.0002}"',
        'RCA_JOINT_RESPONSE_CALIBRATION_DOWN_DELTA="${CALIBRATION_DOWN_DELTA}"',
        'RCA_JOINT_RESPONSE_CALIBRATION_UP_DELTA="${CALIBRATION_UP_DELTA}"',
        '--socket-insertion-servo-z-step "${RCA_VIDEO_CANDIDATE_SOCKET_Z_STEP:-0.0002}"',
        'echo "[peg-video-candidate] recording_mode=${RECORDING_MODE}"',
        'case "${RECORDING_MODE}" in',
        'refusing ${RECORDING_MODE} recording with RCA_ISAACLAB_RUNTIME_PROFILE=trace-only',
        "scripts/render_trace_video.py",
        'run_remote_record_scripted_screen_video.sh',
        'RCA_VIDEO_BACKEND=camera',
        'RCA_AUTO_VIEWPORT_KIT_ARGS="${RCA_AUTO_VIEWPORT_KIT_ARGS:-1}"',
        'RCA_VALIDATE_ACTION_RESPONSE=1',
        'RCA_VALIDATE_FINAL_CONTACT_BOUNDARY=1',
        'RCA_VALIDATE_TRACE_FRAME_ALIGNMENT=1',
        'unsupported RCA_VIDEO_CANDIDATE_RECORDING_MODE',
    ]
    for snippet in required_recreate_snippets:
        if snippet not in video_recreate_script:
            raise AssertionError(
                "recreate_brev_and_record_peg_video_candidate.sh is missing screen recording "
                f"snippet: {snippet}"
            )

    required_screen_snippets = [
        "rca_remote_container_write_file()",
        "base64 | tr -d '\\n'",
        "rca_remote_container_write_file \"${REMOTE_RUN_PATH}\" 0755",
        'SCRIPTED_VIS_ARGS="${RCA_SCREEN_SCRIPTED_VIS_ARGS:---visualizer kit}"',
        'FORCE_APP_LAUNCHER="${RCA_SCREEN_FORCE_APP_LAUNCHER:-1}"',
        "export RCA_FORCE_APP_LAUNCHER='${FORCE_APP_LAUNCHER}'",
        "scripts/scripted_agent.py ${SCRIPTED_VIS_ARGS} --task",
        "x11grab",
        ">/tmp/rca-ffmpeg-path.txt",
        "read -r FFMPEG </tmp/rca-ffmpeg-path.txt",
        "imageio_ffmpeg.get_ffmpeg_exe()",
        '"\\${FFMPEG}" -y -f x11grab',
        "screen_capture.mp4",
        "check_scripted_action_response_trace.py",
        "check_peg_in_hole_video_candidate.py",
        "check_final_contact_boundary_diagnostic.py",
        "audit_trace_frame_alignment.py",
        "action_response_check.log",
        "final_contact_boundary_check.log",
        "trace_frame_alignment_check.log",
    ]
    for snippet in required_screen_snippets:
        if snippet not in screen_script:
            raise AssertionError(
                "run_remote_record_scripted_screen_video.sh is missing validated screen recording "
                f"snippet: {snippet}"
            )
    forbidden_screen_snippets = [
        "cat > '${REMOTE_RUN_PATH}' <<'EOF'",
        "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'",
    ]
    for snippet in forbidden_screen_snippets:
        if snippet in screen_script:
            raise AssertionError(
                "run_remote_record_scripted_screen_video.sh must not write remote scripts through "
                f"nested heredocs: {snippet}"
            )


def run_isaac_trace_replay_video_static_tests() -> None:
    """Keep trace replay honest: semantic proof from trace, pixels from Isaac."""

    replay_script = (REPO_ROOT / "scripts" / "replay_trace_in_isaac_video.py").read_text(
        encoding="utf-8"
    )
    remote_runner = (REPO_ROOT / "scripts" / "run_remote_replay_trace_video.sh").read_text(
        encoding="utf-8"
    )
    video_recreate_script = (
        REPO_ROOT / "scripts" / "recreate_brev_and_record_peg_video_candidate.sh"
    ).read_text(encoding="utf-8")

    required_replay_snippets = [
        "Render a validated scripted trace inside Isaac Sim.",
        "real Isaac Lab scene",
        "The source trace remains the",
        "semantic proof",
        "render_mode=\"rgb_array\"",
        "write_root_pose_to_sim",
        "write_joint_state_to_sim",
        "set_joint_position_target",
        "articulation-link peg is",
        "imageio.get_writer",
        "isaac_trace_replay.mp4",
        "--require-source-success",
        "--write-peg-root-from-trace",
        "\"source_success_step\"",
        "\"frames_written\"",
    ]
    for snippet in required_replay_snippets:
        if snippet not in replay_script:
            raise AssertionError(f"replay_trace_in_isaac_video.py missing snippet: {snippet}")

    required_runner_snippets = [
        "remote_common.sh",
        "rca_init_remote_vars",
        "RCA_REPLAY_TRACE_JSON",
        "trace_replay_inputs",
        "rsync -az",
        "scripts/replay_trace_in_isaac_video.py",
        "--require-source-success",
        "--write-peg-root-from-trace",
        "isaac_trace_replay.mp4",
        "replay_summary.json",
        "frames_written must be positive",
        "source_success_step must be present",
    ]
    for snippet in required_runner_snippets:
        if snippet not in remote_runner:
            raise AssertionError(f"run_remote_replay_trace_video.sh missing snippet: {snippet}")

    required_recreate_snippets = [
        'RECORDING_MODE="${RCA_VIDEO_CANDIDATE_RECORDING_MODE:-screen}"',
        '"${RECORDING_MODE}" != "trace-replay"',
        "trace-replay)",
        "run_remote_replay_trace_video.sh",
        'RCA_REPLAY_VIDEO_TIMEOUT_SECONDS="${VIDEO_TIMEOUT_SECONDS}"',
        'RCA_REPLAY_TRACE_SEED="${SEED}"',
    ]
    for snippet in required_recreate_snippets:
        if snippet not in video_recreate_script:
            raise AssertionError(
                "recreate_brev_and_record_peg_video_candidate.sh is missing trace-replay "
                f"snippet: {snippet}"
            )


def run_trace_video_renderer_static_tests() -> None:
    """Keep local trace rendering dependency-light and clearly labeled."""

    renderer = (REPO_ROOT / "scripts" / "render_trace_video.py").read_text(encoding="utf-8")
    required_snippets = [
        "trace-rendered diagnostic, not Isaac viewport footage",
        "TRACE-RENDERED PEG-IN-HOLE DIAGNOSTIC",
        "SOURCE TRACE - NOT ISAAC VIEWPORT",
        "-f",
        "rawvideo",
        "rgb24",
        "libx264",
        "post_metric_tip_rel_socket_pos",
        "metric_tip_rel_socket_pos",
    ]
    for snippet in required_snippets:
        if snippet not in renderer:
            raise AssertionError(f"render_trace_video.py is missing required snippet: {snippet}")

    forbidden_snippets = [
        "import numpy",
        "import matplotlib",
        "import imageio",
        "import cv2",
        "from PIL",
    ]
    for snippet in forbidden_snippets:
        if snippet in renderer:
            raise AssertionError(f"render_trace_video.py must stay dependency-light; found: {snippet}")


def run_trace_frame_alignment_tests() -> None:
    scripts_path = str(REPO_ROOT / "scripts")
    sys.path.insert(0, scripts_path)
    try:
        from audit_trace_frame_alignment import audit_trace, rotate_legacy_xyzw, rotate_wxyz
    finally:
        try:
            sys.path.remove(scripts_path)
        except ValueError:
            pass

    with tempfile.TemporaryDirectory(prefix="rca-frame-audit-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        socket_pos = (0.10, -0.20, 0.30)
        socket_quat_wxyz = (0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        metric_tip_rel_socket = (0.004, 0.0, 0.030)
        offset_socket = (0.001, 0.002, 0.0)

        def add3(lhs: tuple[float, float, float], rhs: tuple[float, float, float]) -> list[float]:
            return [lhs[0] + rhs[0], lhs[1] + rhs[1], lhs[2] + rhs[2]]

        def write_trace(path: Path, *, legacy_offset: bool, proxy_gap: float) -> None:
            offset_w = (
                rotate_legacy_xyzw(socket_quat_wxyz, offset_socket)
                if legacy_offset
                else rotate_wxyz(socket_quat_wxyz, offset_socket)
            )
            metric_tip_world = add3(socket_pos, rotate_wxyz(socket_quat_wxyz, metric_tip_rel_socket))
            metric_tip_world[0] += proxy_gap
            steps = [
                {
                    "step": 0,
                    "metric_tip_rel_socket_pos": list(metric_tip_rel_socket),
                    "post_metric_tip_rel_socket_pos": list(metric_tip_rel_socket),
                    "lateral": 0.004,
                    "socket_pos_w": list(socket_pos),
                    "socket_quat_w": list(socket_quat_wxyz),
                    "physical_tip_pos_w": metric_tip_world,
                    "post_socket_pos_w": list(socket_pos),
                    "post_socket_quat_w": list(socket_quat_wxyz),
                    "post_physical_tip_pos_w": metric_tip_world,
                    "socket_insertion_servo_active": True,
                    "socket_insertion_servo_offset_socket": list(offset_socket),
                    "socket_insertion_servo_offset_w": list(offset_w),
                }
            ]
            path.write_text(json.dumps({"steps": steps}), encoding="utf-8")

        passing_trace = tmp_dir / "passing-frame-trace.json"
        write_trace(passing_trace, legacy_offset=False, proxy_gap=0.0)
        report, failures = audit_trace(passing_trace)
        if failures:
            raise AssertionError(f"frame audit should pass WXYZ-aligned synthetic trace: {failures}")
        if report["socket_offset_wxyz_closer"] != 1 or report["socket_offset_legacy_closer"] != 0:
            raise AssertionError(f"frame audit did not classify WXYZ offset correctly: {report}")

        failing_trace = tmp_dir / "legacy-frame-trace.json"
        write_trace(failing_trace, legacy_offset=True, proxy_gap=0.050)
        report, failures = audit_trace(failing_trace)
        if not failures:
            raise AssertionError(f"frame audit should reject legacy/proxy-mismatched trace: {report}")
        if "socket-frame offsets match legacy XYZW rotation more often than task WXYZ rotation" not in failures:
            raise AssertionError(f"frame audit missed legacy rotation failure: {failures}")
        if "physical-tip proxy is more than 2cm from the task metric tip on average" not in failures:
            raise AssertionError(f"frame audit missed physical proxy failure: {failures}")


def run_success_deliverable_bundle_tests() -> None:
    success_trace_bundle = REPO_ROOT / "artifacts/deliverables/2026-06-21-peg-in-hole-success-trace"
    isaac_replay_bundle = REPO_ROOT / "artifacts/deliverables/2026-06-23-isaac-trace-replay-video"
    source_trace = success_trace_bundle / "video_trace.json"
    source_video = isaac_replay_bundle / "isaac_trace_replay_trimmed.mp4"

    result = run(["python3", "scripts/check_success_deliverable_bundle.py", str(isaac_replay_bundle)])
    assert_status(result, 0, "success bundle validator accepts Isaac replay deliverable")
    assert_contains(result, "[success-bundle] PASS", "success bundle replay PASS detail")
    assert_contains(result, "gate: peg-video-candidate PASS", "success bundle semantic gate detail")

    result = run(["python3", "scripts/check_success_deliverable_bundle.py", str(success_trace_bundle)])
    assert_status(result, 0, "success bundle validator accepts source trace deliverable")
    assert_contains(result, "gate: trace-frame-alignment PASS", "success bundle frame audit detail")

    def write_bundle_sha256(bundle: Path) -> None:
        rows = []
        for path in sorted(child for child in bundle.iterdir() if child.is_file() and child.name != "SHA256SUMS.txt"):
            rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{path.name}")
        (bundle / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="rca-success-bundle-tests-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)

        video_only_bundle = tmp_dir / "video-only-bundle"
        video_only_bundle.mkdir()
        shutil.copy2(source_video, video_only_bundle / source_video.name)
        (video_only_bundle / "brev_paid_safety_status.txt").write_text(
            "\n".join(
                [
                    "[brev-safety] visible_instances=0",
                    "[brev-safety] status=SAFE_NO_VISIBLE_PAID_INSTANCE",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        write_bundle_sha256(video_only_bundle)
        result = run(["python3", "scripts/check_success_deliverable_bundle.py", str(video_only_bundle)])
        assert_status(result, 1, "success bundle validator rejects video-only bundle")
        assert_contains(result, "could not locate source trace", "video-only bundle failure detail")

        bad_trace = tmp_dir / "bad_video_trace.json"
        payload = json.loads(source_trace.read_text(encoding="utf-8"))
        if isinstance(payload.get("summary"), dict):
            payload["summary"]["success_step"] = None
            payload["summary"]["final_success_rate"] = 0.0
            payload["summary"]["best_lateral"] = 0.050
        for step in payload.get("steps", []):
            if isinstance(step, dict):
                step["success"] = False
                step["lateral"] = 0.050
        bad_trace.write_text(json.dumps(payload), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/check_success_deliverable_bundle.py",
                str(isaac_replay_bundle),
                "--trace-json",
                str(bad_trace),
            ]
        )
        assert_status(result, 1, "success bundle validator rejects semantically failed trace")
        assert_contains(result, "peg-video-candidate failed", "failed trace bundle detail")

        corrupt_bundle = tmp_dir / "corrupt-checksum-bundle"
        shutil.copytree(isaac_replay_bundle, corrupt_bundle)
        readme = corrupt_bundle / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nchecksum corruption test\n", encoding="utf-8")
        result = run(["python3", "scripts/check_success_deliverable_bundle.py", str(corrupt_bundle)])
        assert_status(result, 1, "success bundle validator rejects checksum mismatch")
        assert_contains(result, "checksum mismatch", "checksum mismatch failure detail")


def run_v0_skill_api_contract_tests() -> None:
    contract_path = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
    checker_path = REPO_ROOT / "scripts" / "check_v0_skill_api_contract.py"
    request_path = REPO_ROOT / "configs" / "v0_skill_request.example.json"
    request_checker_path = REPO_ROOT / "scripts" / "validate_v0_skill_request.py"
    planner_path = REPO_ROOT / "scripts" / "plan_v0_skill_request.py"
    language_suite_path = REPO_ROOT / "configs" / "v0_language_instruction_suite.json"
    language_suite_checker_path = REPO_ROOT / "scripts" / "check_v0_language_instruction_suite.py"
    readiness_checker_path = REPO_ROOT / "scripts" / "check_v0_skill_readiness.py"
    execution_planner_path = REPO_ROOT / "scripts" / "plan_v0_skill_execution.py"
    language_dry_run_path = REPO_ROOT / "scripts" / "run_v0_language_skill_dry_run.py"
    policy_api_review_path = REPO_ROOT / "scripts" / "prepare_v0_policy_api_review.py"
    policy_dataset_audit_path = REPO_ROOT / "scripts" / "audit_v0_policy_dataset.py"
    policy_experiment_path = REPO_ROOT / "scripts" / "plan_v0_policy_experiment.py"
    policy_feature_dry_run_path = REPO_ROOT / "scripts" / "plan_v0_policy_feature_dry_run.py"
    policy_label_source_audit_path = REPO_ROOT / "scripts" / "audit_v0_policy_label_sources.py"
    policy_label_dry_run_path = REPO_ROOT / "scripts" / "plan_v0_policy_label_dry_run.py"
    policy_label_dataset_path = REPO_ROOT / "scripts" / "extract_v0_policy_label_dataset.py"
    policy_training_preflight_path = REPO_ROOT / "scripts" / "check_v0_policy_training_preflight.py"
    policy_training_script_path = REPO_ROOT / "scripts" / "train_v0_residual_policy.py"
    policy_eval_script_path = REPO_ROOT / "scripts" / "evaluate_v0_residual_policy.py"
    policy_promotion_gate_path = REPO_ROOT / "scripts" / "check_v0_policy_promotion_gate.py"
    policy_readiness_pipeline_path = REPO_ROOT / "scripts" / "run_v0_offline_policy_readiness_pipeline.py"
    robot_adapter_path = REPO_ROOT / "configs" / "v0_external_robot_adapter.template.json"
    robot_adapter_checker_path = REPO_ROOT / "scripts" / "check_v0_robot_adapter_contract.py"
    robot_adapter_planner_path = REPO_ROOT / "scripts" / "plan_v0_robot_adapter_manifest.py"
    portability_checker_path = REPO_ROOT / "scripts" / "check_v0_portability_boundary.py"
    portability_review_path = REPO_ROOT / "scripts" / "prepare_v0_portability_review.py"

    result = run(["python3", str(checker_path), str(contract_path)])
    assert_status(result, 0, "V0 skill API contract validator accepts committed contract")
    assert_contains(result, "[v0-skill-api-contract] PASS", "V0 skill API contract PASS detail")
    result = run(["python3", str(request_checker_path), str(request_path)])
    assert_status(result, 0, "V0 skill request validator accepts committed example request")
    assert_contains(result, "[v0-skill-request] PASS", "V0 skill request PASS detail")
    result = run(["python3", str(language_suite_checker_path), str(language_suite_path), "--no-output"])
    assert_status(result, 0, "V0 language instruction suite accepts committed cases")
    assert_contains(result, "[v0-language-suite] status=PASS", "V0 language suite PASS detail")
    assert_contains(result, "insert_center_socket", "V0 language suite includes center socket case")
    assert_contains(result, "reject_low_level_joint_command", "V0 language suite includes low-level rejection")
    language_suite_report, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-language-suite] facts=", 1)[1].lstrip()
    )
    language_suite_effects = language_suite_report["side_effects"]
    for key in (
        "writes_suite_report",
        "creates_paid_instance",
        "runs_remote_code",
        "starts_isaac",
        "calls_llm_or_vlm",
        "calls_ros_or_robot",
    ):
        if language_suite_effects[key] is not False:
            raise AssertionError(f"language suite --no-output side effect must be false for {key}: {language_suite_report}")
    result = run(["python3", str(robot_adapter_checker_path), str(robot_adapter_path)])
    assert_status(result, 0, "V0 external robot adapter template is a safe blocked contract")
    assert_contains(result, "[v0-robot-adapter] BLOCKED", "V0 robot adapter template BLOCKED detail")
    adapter_report, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-robot-adapter] facts=", 1)[1].lstrip()
    )
    if adapter_report["ready_for_hardware_execution"] is not False:
        raise AssertionError(f"adapter checker must never approve direct hardware execution: {adapter_report}")
    if adapter_report["manual_hardware_approval_required"] is not True:
        raise AssertionError(f"adapter checker must require manual hardware approval: {adapter_report}")
    if adapter_report["review_scope"] != "named_robot_low_speed_review_only":
        raise AssertionError(f"adapter checker must scope readiness to named low-speed review: {adapter_report}")
    adapter_effects = adapter_report["side_effects"]
    for key in (
        "writes_adapter_report",
        "writes_adapter_manifest",
        "creates_paid_instance",
        "runs_remote_code",
        "starts_isaac",
        "calls_ros_or_robot",
    ):
        if adapter_effects[key] is not False:
            raise AssertionError(f"adapter checker side effect must be false for {key}: {adapter_report}")
    assert_contains(
        result,
        "next_action=fill_robot_specific_model_calibration_safety_ros2_and_revalidation_evidence",
        "V0 robot adapter next action detail",
    )
    result = run(["python3", str(portability_checker_path), "--skip-phase2-contact-gate"])
    assert_status(result, 0, "V0 portability boundary reports current safe blocked state")
    assert_contains(result, "BLOCKED_NOT_DROP_IN", "V0 portability boundary blocked detail")
    assert_contains(result, "universal_drop_in_ready=false", "V0 portability boundary universal non-claim")
    portability_boundary, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-portability-boundary] facts=", 1)[1].lstrip()
    )
    if portability_boundary["ready_for_hardware_execution"] is not False:
        raise AssertionError(f"portability boundary must never approve direct hardware execution: {portability_boundary}")
    boundary_effects = portability_boundary["side_effects"]
    for key in (
        "writes_boundary_report",
        "writes_adapter_manifest",
        "creates_paid_instance",
        "runs_remote_code",
        "starts_isaac",
        "calls_ros_or_robot",
    ):
        if boundary_effects[key] is not False:
            raise AssertionError(f"portability boundary side effect must be false for {key}: {portability_boundary}")
    result = run(["python3", str(portability_checker_path), "--skip-phase2-contact-gate", "--fail-on-blocked"])
    assert_status(result, 1, "V0 portability boundary can fail closed while blocked")
    result = run(["python3", str(portability_review_path), "--skip-phase2-contact-gate", "--no-output"])
    assert_status(result, 0, "V0 portability review reports current safe blocked state")
    assert_contains(result, "[v0-portability-review] status=BLOCKED", "V0 portability review blocked detail")
    assert_contains(result, "NO_DIRECT_DROP_IN", "V0 portability review direct drop-in answer")
    assert_contains(result, "universal_drop_in_ready=false", "V0 portability review universal non-claim")
    assert_contains(
        result,
        "target_adapter_preview_status=NOT_PROVIDED",
        "V0 portability review default target-preview detail",
    )
    assert_contains(result, "adapter_workplan", "V0 portability review workplan detail")
    assert_contains(result, "minimum_ordered_steps", "V0 portability review ordered adapter steps detail")
    assert_contains(result, "required_evidence_groups", "V0 portability review evidence groups detail")
    portability_review_default, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-portability-review] facts=", 1)[1].lstrip()
    )
    default_workplan = portability_review_default["adapter_workplan"]
    if portability_review_default["ready_for_hardware_execution"] is not False:
        raise AssertionError(f"portability review must never approve direct hardware execution: {portability_review_default}")
    if default_workplan["ready_for_hardware_execution"] is not False:
        raise AssertionError(f"portability workplan must keep direct hardware execution false: {default_workplan}")
    if default_workplan["direct_drop_in_answer"] != "NO_DIRECT_DROP_IN":
        raise AssertionError(f"portability workplan must reject direct drop-in: {default_workplan}")
    if "model_sources" not in default_workplan["required_evidence_groups"]:
        raise AssertionError(f"portability workplan must expose model-source evidence: {default_workplan}")
    if "low_speed_contact_validation" not in default_workplan["required_evidence_groups"]["safety_evidence"]:
        raise AssertionError(f"portability workplan must expose low-speed safety evidence: {default_workplan}")
    if "ee_pose_feedback" not in default_workplan["required_evidence_groups"]["ros2_interfaces"]:
        raise AssertionError(f"portability workplan must expose EE pose feedback evidence: {default_workplan}")
    if "force_torque_or_contact_feedback" not in default_workplan["required_evidence_groups"]["ros2_interfaces"]:
        raise AssertionError(f"portability workplan must expose force/contact feedback evidence: {default_workplan}")
    if "calibration_error_bounds" not in default_workplan["required_evidence_groups"]["frame_contract"]:
        raise AssertionError(f"portability workplan must expose frame calibration bounds: {default_workplan}")
    if "low_speed_no_contact_dry_run" not in default_workplan["required_evidence_groups"]["revalidation_evidence"]:
        raise AssertionError(f"portability workplan must expose low-speed no-contact dry-run evidence: {default_workplan}")
    if default_workplan["minimum_ordered_steps"][-1] != "perform_manual_low_speed_named_robot_review_only_after_all_gates_are_ready":
        raise AssertionError(f"portability workplan final review step changed: {default_workplan}")
    review_effects = portability_review_default["side_effects"]
    for key in ("writes_review_artifacts", "writes_target_adapter_manifest", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
        if review_effects[key] is not False:
            raise AssertionError(f"portability review --no-output side effect must be false for {key}: {portability_review_default}")
    result = run(
        [
            "python3",
            str(portability_review_path),
            "--skip-phase2-contact-gate",
            "--target-robot-id",
            "demo_arm_v0",
            "--target-robot-family",
            "demo_6dof_arm",
            "--end-effector",
            "parallel_gripper",
            "--no-output",
        ]
    )
    assert_status(result, 0, "V0 portability review previews a named adapter without writing it")
    assert_contains(
        result,
        "target_adapter_preview_status=PASS_SAFE_BLOCKED",
        "V0 portability review named adapter preview detail",
    )
    assert_contains(result, "demo_arm_v0", "V0 portability review named adapter robot id detail")
    assert_contains(
        result,
        "command_contract.command_frame",
        "V0 portability review named adapter blocker detail",
    )
    named_portability_review, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-portability-review] facts=", 1)[1].lstrip()
    )
    named_workplan = named_portability_review["adapter_workplan"]
    if named_workplan["target_robot"]["robot_id"] != "demo_arm_v0":
        raise AssertionError(f"named portability workplan should preserve target robot: {named_workplan}")
    if named_workplan["current_adapter_blocker_count"] <= 0:
        raise AssertionError(f"named portability workplan should remain blocked on adapter evidence: {named_workplan}")
    if any("replace_with_robot_id" in blocker for blocker in named_workplan["top_adapter_blockers"]):
        raise AssertionError(f"named portability workplan should use preview blockers, not template blockers: {named_workplan}")
    result = run(["python3", str(portability_review_path), "--skip-phase2-contact-gate", "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 portability review can fail closed while blocked")
    result = run(["python3", str(execution_planner_path), "--skip-phase2-contact-gate", "--no-output"])
    assert_status(result, 0, "V0 skill execution planner writes blocked plan without failing by default")
    assert_contains(result, "[v0-skill-execution-plan] status=BLOCKED", "V0 execution planner blocked detail")
    assert_contains(result, "ready_for_execution", "V0 execution planner readiness field")
    blocked_execution_plan, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-skill-execution-plan] facts=", 1)[1].lstrip()
    )
    blocked_execution_effects = blocked_execution_plan["side_effects"]
    for key in ("writes_execution_plan", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
        if blocked_execution_effects[key] is not False:
            raise AssertionError(f"execution planner --no-output side effect must be false for {key}: {blocked_execution_plan}")
    result = run(
        [
            "python3",
            str(language_dry_run_path),
            "insert the peg into the right socket",
            "--skip-phase2-contact-gate",
            "--no-output",
        ]
    )
    assert_status(result, 0, "V0 language skill dry-run reports blocked current state without failing by default")
    assert_contains(result, "[v0-language-skill-dry-run] status=BLOCKED", "V0 language dry-run blocked marker")
    assert_contains(result, "request_planner_status", "V0 language dry-run request-planner field")
    assert_contains(result, "allowed_command_boundary", "V0 language dry-run execution-surface field")
    blocked_language_report, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-language-skill-dry-run] facts=", 1)[1].lstrip()
    )
    blocked_language_effects = blocked_language_report["side_effects"]
    for key in (
        "writes_request_artifact",
        "writes_dry_run_report",
        "creates_paid_instance",
        "runs_remote_code",
        "starts_isaac",
        "calls_llm_or_vlm",
        "calls_ros_or_robot",
    ):
        if blocked_language_effects[key] is not False:
            raise AssertionError(f"language dry-run --no-output side effect must be false for {key}: {blocked_language_report}")
    result = run(
        [
            "python3",
            str(language_dry_run_path),
            "insert the peg into the right socket",
            "--skip-phase2-contact-gate",
            "--no-output",
            "--fail-on-blocked",
        ]
    )
    assert_status(result, 1, "V0 language skill dry-run can fail closed while V0 readiness is blocked")
    result = run(["python3", str(language_dry_run_path), "move joint 4 down by 2 degrees", "--no-output"])
    assert_status(result, 1, "V0 language skill dry-run rejects low-level joint commands")
    assert_contains(result, "fix_language_instruction", "V0 language dry-run low-level rejection detail")
    result = run(
        [
            "python3",
            str(execution_planner_path),
            "--skip-phase2-contact-gate",
            "--no-output",
            "--fail-on-blocked",
        ]
    )
    assert_status(result, 1, "V0 skill execution planner can fail closed on blocked readiness")
    result = run(["python3", str(policy_experiment_path), "--no-output"])
    assert_status(result, 0, "V0 policy experiment planner reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-experiment-plan] status=BLOCKED", "V0 policy experiment blocked detail")
    result = run(["python3", str(policy_experiment_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy experiment planner can fail closed before review packet exists")
    result = run(["python3", str(policy_dataset_audit_path), "--no-output"])
    assert_status(result, 0, "V0 policy dataset audit reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-dataset-audit] status=BLOCKED", "V0 policy dataset audit blocked detail")
    result = run(["python3", str(policy_dataset_audit_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy dataset audit can fail closed before dataset exists")
    result = run(["python3", str(policy_feature_dry_run_path), "--no-output"])
    assert_status(result, 0, "V0 policy feature dry-run reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-feature-dry-run] status=BLOCKED", "V0 policy feature dry-run blocked detail")
    result = run(["python3", str(policy_feature_dry_run_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy feature dry-run can fail closed before dataset audit and experiment plan exist")
    result = run(["python3", str(policy_label_source_audit_path), "--no-output"])
    assert_status(result, 0, "V0 policy label-source audit reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-label-source-audit] status=BLOCKED", "V0 policy label-source blocked detail")
    result = run(["python3", str(policy_label_source_audit_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy label-source audit can fail closed before feature dry-run exists")
    result = run(["python3", str(policy_label_dry_run_path), "--no-output"])
    assert_status(result, 0, "V0 policy label dry-run reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-label-dry-run] status=BLOCKED", "V0 policy label dry-run blocked detail")
    result = run(["python3", str(policy_label_dry_run_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy label dry-run can fail closed before label-source audit exists")
    result = run(["python3", str(policy_label_dataset_path), "--no-output"])
    assert_status(result, 0, "V0 policy label dataset extractor reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-label-dataset] status=BLOCKED", "V0 policy label dataset blocked detail")
    result = run(["python3", str(policy_label_dataset_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy label dataset extractor can fail closed before label dry-run exists")
    result = run(["python3", str(policy_training_preflight_path), "--no-output"])
    assert_status(result, 0, "V0 policy training preflight reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-training-preflight] status=BLOCKED", "V0 policy training preflight blocked detail")
    result = run(["python3", str(policy_training_preflight_path), "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 policy training preflight can fail closed before label dataset exists")
    result = run(["python3", str(policy_training_script_path), "--dry-run", "--no-output"])
    assert_status(result, 1, "V0 residual policy trainer dry-run blocks before label dataset exists")
    assert_contains(result, "[v0-residual-policy-train] facts=", "V0 residual trainer blocked facts marker")
    assert_contains(result, "[v0-residual-policy-train] BLOCKED", "V0 residual trainer blocked detail")
    blocked_training_report, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-residual-policy-train] facts=", 1)[1].lstrip()
    )
    if blocked_training_report["status"] != "BLOCKED":
        raise AssertionError(f"blocked trainer should expose BLOCKED facts: {blocked_training_report}")
    blocked_training_effects = blocked_training_report["side_effects"]
    for key in ("writes_training_plan", "writes_checkpoint", "writes_metadata", "creates_paid_instance", "starts_isaac", "calls_ros_or_robot"):
        if blocked_training_effects[key] is not False:
            raise AssertionError(f"blocked trainer side effect must be false for {key}: {blocked_training_report}")
    result = run(["python3", str(policy_readiness_pipeline_path), "--dry-run", "--no-summary"])
    assert_status(result, 0, "V0 offline policy-readiness pipeline dry-run prints its local sequence")
    assert_contains(result, "[v0-offline-policy-readiness] facts=", "V0 offline pipeline dry-run facts marker")
    assert_contains(result, "[v0-offline-policy-readiness] status=DRY_RUN", "V0 offline pipeline dry-run marker")
    assert_contains(result, "policy_training_dry_run", "V0 offline pipeline includes training dry-run step")
    result = run(
        [
            "python3",
            str(policy_readiness_pipeline_path),
            "--skip-phase2-contact-gate",
            "--no-summary",
            "--no-output",
        ]
    )
    assert_status(result, 0, "V0 offline policy-readiness pipeline reports blocked current state by default")
    assert_contains(result, "[v0-offline-policy-readiness] facts=", "V0 offline pipeline blocked facts marker")
    assert_contains(result, "[v0-offline-policy-readiness] status=BLOCKED", "V0 offline pipeline blocked marker")
    assert_contains(result, "blocked_step=policy_api_review", "V0 offline pipeline blocked step detail")
    assert_contains(result, '"no_output": true', "V0 offline pipeline no-output detail")
    assert_contains(
        result,
        '"writes_review_dataset_plan_or_training_artifacts": false',
        "V0 offline pipeline no-artifact-write detail",
    )
    result = run(
        [
            "python3",
            str(policy_readiness_pipeline_path),
            "--skip-phase2-contact-gate",
            "--no-summary",
            "--fail-on-blocked",
        ]
    )
    assert_status(result, 1, "V0 offline policy-readiness pipeline can fail closed while blocked")
    result = run(["python3", str(policy_eval_script_path), "--dry-run", "--no-output"])
    assert_status(result, 0, "V0 residual policy eval reports blocked current state without failing by default")
    assert_contains(result, "[v0-residual-policy-eval] facts=", "V0 residual eval blocked facts marker")
    assert_contains(result, "[v0-residual-policy-eval] BLOCKED", "V0 residual eval blocked detail")
    blocked_eval_report, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-residual-policy-eval] facts=", 1)[1].lstrip()
    )
    if blocked_eval_report["status"] != "BLOCKED":
        raise AssertionError(f"blocked evaluator should expose BLOCKED facts: {blocked_eval_report}")
    blocked_eval_effects = blocked_eval_report["side_effects"]
    for key in (
        "writes_eval_summary",
        "writes_checkpoint",
        "writes_training_metadata",
        "imports_torch",
        "runs_supervised_eval",
        "creates_paid_instance",
        "starts_isaac",
        "calls_ros_or_robot",
    ):
        if blocked_eval_effects[key] is not False:
            raise AssertionError(f"blocked evaluator side effect must be false for {key}: {blocked_eval_report}")
    result = run(["python3", str(policy_eval_script_path), "--dry-run", "--no-output", "--fail-on-blocked"])
    assert_status(result, 1, "V0 residual policy eval can fail closed before checkpoint metadata exists")
    result = run(["python3", str(policy_promotion_gate_path), "--skip-phase2-contact-gate", "--no-output"])
    assert_status(result, 0, "V0 policy promotion gate reports blocked current state without failing by default")
    assert_contains(result, "[v0-policy-promotion-gate] BLOCKED", "V0 policy promotion gate blocked detail")
    blocked_promotion_report, _ = json.JSONDecoder().raw_decode(
        result.stdout.split("[v0-policy-promotion-gate] facts=", 1)[1].lstrip()
    )
    if blocked_promotion_report["status"] != "BLOCKED":
        raise AssertionError(f"blocked promotion gate should expose BLOCKED facts: {blocked_promotion_report}")
    for key in (
        "writes_promotion_report",
        "writes_checkpoint",
        "trains_policy",
        "creates_paid_instance",
        "runs_remote_code",
        "starts_isaac",
        "calls_ros_or_robot",
    ):
        if blocked_promotion_report["side_effects"][key] is not False:
            raise AssertionError(f"blocked promotion gate side effect must be false for {key}: {blocked_promotion_report}")
    result = run(
        [
            "python3",
            str(policy_promotion_gate_path),
            "--skip-phase2-contact-gate",
            "--no-output",
            "--fail-on-blocked",
        ]
    )
    assert_status(result, 1, "V0 policy promotion gate can fail closed before closed-loop policy evidence exists")

    checker = checker_path.read_text(encoding="utf-8")
    request_checker = request_checker_path.read_text(encoding="utf-8")
    planner = planner_path.read_text(encoding="utf-8")
    language_suite = language_suite_path.read_text(encoding="utf-8")
    language_suite_checker = language_suite_checker_path.read_text(encoding="utf-8")
    readiness_checker = readiness_checker_path.read_text(encoding="utf-8")
    execution_planner = execution_planner_path.read_text(encoding="utf-8")
    language_dry_run = language_dry_run_path.read_text(encoding="utf-8")
    policy_api_review = policy_api_review_path.read_text(encoding="utf-8")
    policy_dataset_audit = policy_dataset_audit_path.read_text(encoding="utf-8")
    policy_experiment = policy_experiment_path.read_text(encoding="utf-8")
    policy_feature_dry_run = policy_feature_dry_run_path.read_text(encoding="utf-8")
    policy_label_source_audit = policy_label_source_audit_path.read_text(encoding="utf-8")
    policy_label_dry_run = policy_label_dry_run_path.read_text(encoding="utf-8")
    policy_label_dataset = policy_label_dataset_path.read_text(encoding="utf-8")
    policy_training_preflight = policy_training_preflight_path.read_text(encoding="utf-8")
    policy_training_script = policy_training_script_path.read_text(encoding="utf-8")
    policy_eval_script = policy_eval_script_path.read_text(encoding="utf-8")
    policy_promotion_gate = policy_promotion_gate_path.read_text(encoding="utf-8")
    policy_readiness_pipeline = policy_readiness_pipeline_path.read_text(encoding="utf-8")
    robot_adapter_checker = robot_adapter_checker_path.read_text(encoding="utf-8")
    robot_adapter_planner = robot_adapter_planner_path.read_text(encoding="utf-8")
    portability_checker = portability_checker_path.read_text(encoding="utf-8")
    portability_review = portability_review_path.read_text(encoding="utf-8")
    for expected_snippet in (
        "raw_joint_targets",
        "not direct drop-in precision on another robot arm",
        "new_robot_requires_adapter_calibration_and_revalidation",
        "joint_trajectory_action",
        "low_speed_contact_validation",
        "required_command_contract",
        "required_frame_contract",
        "required_runtime_guards",
        "requires_min_strict_success_traces must be an integer >= 5",
    ):
        if expected_snippet not in checker:
            raise AssertionError(f"V0 skill API contract checker missing snippet: {expected_snippet}")
    if "brev create" in checker or '"${BREV_BIN}" create' in checker:
        raise AssertionError("V0 skill API contract checker must be offline and must not create Brev instances")
    for expected_snippet in (
        "DIRECT_COMMAND_KEYS",
        "raw_joint_targets",
        "direct_force_commands",
        "contract must require success-variation result gate before policy/API promotion",
        "new_robot_requires_adapter_calibration_and_revalidation",
    ):
        if expected_snippet not in request_checker:
            raise AssertionError(f"V0 skill request validator missing snippet: {expected_snippet}")
    if "brev create" in request_checker or '"${BREV_BIN}" create' in request_checker:
        raise AssertionError("V0 skill request validator must be offline and must not create Brev instances")
    for expected_snippet in (
        "deterministic_v0_language_to_skill_shim",
        "Unsupported or ambiguous",
        "instructions fail closed instead of guessing low-level behavior",
        "not an LLM/VLM and does not command joints",
        "blocked: request JSON was not written",
    ):
        if expected_snippet not in planner:
            raise AssertionError(f"V0 skill request planner missing snippet: {expected_snippet}")
    if "brev create" in planner or '"${BREV_BIN}" create' in planner:
        raise AssertionError("V0 skill request planner must be offline and must not create Brev instances")
    for expected_snippet in (
        "insert_left_socket",
        "insert_right_socket",
        "insert_center_socket",
        "reject_low_level_joint_command",
        "reject_substring_socket_alias",
        "reject_force_command_without_socket",
        "raw_joint_targets",
        "direct_cartesian_servo_commands",
        "direct_force_commands",
        "not an LLM or VLM evaluation",
    ):
        if expected_snippet not in language_suite:
            raise AssertionError(f"V0 language instruction suite missing snippet: {expected_snippet}")
    for expected_snippet in (
        "Check the offline V0 language instruction suite",
        "deterministic V0 language-to-skill planner",
        "low-level joint commands fail closed",
        "plan_v0_skill_request",
        "not call Brev, Isaac, ROS, hardware, an LLM, or a VLM",
        "raw joint",
        "Cartesian servo",
        "direct force commands",
    ):
        if expected_snippet not in language_suite_checker:
            raise AssertionError(f"V0 language suite checker missing snippet: {expected_snippet}")
    if "brev create" in language_suite_checker or '"${BREV_BIN}" create' in language_suite_checker:
        raise AssertionError("V0 language suite checker must be offline and must not create Brev instances")
    for expected_snippet in (
        "v0_skill_request_readiness",
        "run_fixed_budget_success_variation_batch_after_paid_ack",
        "run_success_variation_finalizer_to_prepare_dataset",
        "It does not call Brev, Isaac, ROS, or any robot",
        "success variation:",
        "dataset:",
    ):
        if expected_snippet not in readiness_checker:
            raise AssertionError(f"V0 skill readiness checker missing snippet: {expected_snippet}")
    if "brev create" in readiness_checker or '"${BREV_BIN}" create' in readiness_checker:
        raise AssertionError("V0 skill readiness checker must be offline and must not create Brev instances")
    for expected_snippet in (
        "offline bridge between the language/request layer",
        "ready_for_execution",
        "allowed_command_boundary",
        "forbidden_command_boundary",
        "raw_joint_targets",
        "direct_force_commands",
        "not a Brev or Isaac launcher",
        "does not call Brev, Isaac, ROS, or any robot",
    ):
        if expected_snippet not in execution_planner:
            raise AssertionError(f"V0 skill execution planner missing snippet: {expected_snippet}")
    if "brev create" in execution_planner or '"${BREV_BIN}" create' in execution_planner:
        raise AssertionError("V0 skill execution planner must be offline and must not create Brev instances")
    for expected_snippet in (
        "Run the V0 language-to-skill dry-run",
        "deterministic language request planner",
        "plan_v0_skill_request",
        "plan_v0_skill_execution",
        "not an LLM or VLM call",
        "not a Brev or Isaac launcher",
        "not ROS or hardware execution",
        "raw joint",
        "Cartesian servo",
        "force commands",
    ):
        if expected_snippet not in language_dry_run:
            raise AssertionError(f"V0 language skill dry-run missing snippet: {expected_snippet}")
    if "brev create" in language_dry_run or '"${BREV_BIN}" create' in language_dry_run:
        raise AssertionError("V0 language skill dry-run must be offline and must not create Brev instances")
    for expected_snippet in (
        "READY_FOR_POLICY_API_REVIEW",
        "manual_review_checklist",
        "not a direct low-level VLM controller",
        "It does not train a policy, call Brev, start Isaac",
        "[v0-policy-api-review] BLOCKED",
    ):
        if expected_snippet not in policy_api_review:
            raise AssertionError(f"V0 policy/API review prep missing snippet: {expected_snippet}")
    if "brev create" in policy_api_review or '"${BREV_BIN}" create' in policy_api_review:
        raise AssertionError("V0 policy/API review prep must be offline and must not create Brev instances")
    for expected_snippet in (
        "Audit the V0 policy dataset",
        "v0_policy_dataset_audit",
        "coverage_groups",
        "dataset source_manifest_sha256",
        "negative-control case",
        "not trained policy",
        "does not train a policy, call Brev, start Isaac",
    ):
        if expected_snippet not in policy_dataset_audit:
            raise AssertionError(f"V0 policy dataset audit missing snippet: {expected_snippet}")
    if "brev create" in policy_dataset_audit or '"${BREV_BIN}" create' in policy_dataset_audit:
        raise AssertionError("V0 policy dataset audit must be offline and must not create Brev instances")
    for expected_snippet in (
        "Plan the first V0 residual-policy experiment",
        "READY_FOR_LOCAL_POLICY_EXPERIMENT_DESIGN",
        "ready_for_training",
        "residual_policy_over_scripted_baseline",
        "negative-control case must not be included",
        "does not train a policy, call Brev, start Isaac",
        "not a Brev or Isaac launcher",
    ):
        if expected_snippet not in policy_experiment:
            raise AssertionError(f"V0 policy experiment planner missing snippet: {expected_snippet}")
    if "brev create" in policy_experiment or '"${BREV_BIN}" create' in policy_experiment:
        raise AssertionError("V0 policy experiment planner must be offline and must not create Brev instances")
    for expected_snippet in (
        "Dry-run V0 residual-policy feature extraction",
        "READY_FOR_FEATURE_EXTRACTION_REVIEW",
        "target_status",
        "NOT_GENERATED",
        "raw_joint_targets",
        "does not train a policy, call Brev, start Isaac",
        "not direct drop-in precision on another robot arm",
    ):
        if expected_snippet not in policy_feature_dry_run:
            raise AssertionError(f"V0 policy feature dry-run missing snippet: {expected_snippet}")
    if "brev create" in policy_feature_dry_run or '"${BREV_BIN}" create' in policy_feature_dry_run:
        raise AssertionError("V0 policy feature dry-run must be offline and must not create Brev instances")
    for expected_snippet in (
        "Audit V0 residual-policy label sources",
        "READY_FOR_LABEL_SOURCE_REVIEW",
        "target_generation_status",
        "DESIGN_ONLY",
        "socket_insertion_servo_offset_socket",
        "prove the label generator ignores raw_action and joint_pos_des",
        "not generated labels",
        "does not train a policy, generate",
    ):
        if expected_snippet not in policy_label_source_audit:
            raise AssertionError(f"V0 policy label-source audit missing snippet: {expected_snippet}")
    if "brev create" in policy_label_source_audit or '"${BREV_BIN}" create' in policy_label_source_audit:
        raise AssertionError("V0 policy label-source audit must be offline and must not create Brev instances")
    for expected_snippet in (
        "Dry-run V0 residual-policy label generation",
        "READY_FOR_LABEL_DRY_RUN_REVIEW",
        "DRY_RUN_PREVIEW_ONLY",
        "not full label dataset",
        "socket_insertion_servo_offset_socket",
        "recording raw joint/action fields as excluded evidence",
        "does not train a policy",
    ):
        if expected_snippet not in policy_label_dry_run:
            raise AssertionError(f"V0 policy label dry-run missing snippet: {expected_snippet}")
    if "brev create" in policy_label_dry_run or '"${BREV_BIN}" create' in policy_label_dry_run:
        raise AssertionError("V0 policy label dry-run must be offline and must not create Brev instances")
    for expected_snippet in (
        "Extract a V0 residual-policy label dataset",
        "READY_FOR_LOCAL_POLICY_DATASET_REVIEW",
        "jsonl_sha256",
        "not trained policy",
        "socket_insertion_servo_offset_socket",
        "skill_controller_task_parameter_residual",
        "It does not train a policy",
    ):
        if expected_snippet not in policy_label_dataset:
            raise AssertionError(f"V0 policy label dataset extractor missing snippet: {expected_snippet}")
    if "brev create" in policy_label_dataset or '"${BREV_BIN}" create' in policy_label_dataset:
        raise AssertionError("V0 policy label dataset extractor must be offline and must not create Brev instances")
    for expected_snippet in (
        "Check V0 residual-policy training preflight",
        "READY_FOR_LOCAL_RESIDUAL_POLICY_TRAINING",
        "jsonl_sha256",
        "raw_action",
        "training_script_status",
        "It does not train a policy",
        "do not use Brev or paid GPU",
    ):
        if expected_snippet not in policy_training_preflight:
            raise AssertionError(f"V0 policy training preflight missing snippet: {expected_snippet}")
    if "brev create" in policy_training_preflight or '"${BREV_BIN}" create' in policy_training_preflight:
        raise AssertionError("V0 policy training preflight must be offline and must not create Brev instances")
    for expected_snippet in (
        "Train the V0 residual policy",
        "READY_FOR_LOCAL_TRAINING_DRY_RUN",
        "TRAINED_NEEDS_EVALUATION",
        "check_v0_policy_training_preflight",
        "not direct drop-in precision on another robot arm",
        "It does not call Brev, Isaac, ROS, a",
    ):
        if expected_snippet not in policy_training_script:
            raise AssertionError(f"V0 residual policy trainer missing snippet: {expected_snippet}")
    if "brev create" in policy_training_script or '"${BREV_BIN}" create' in policy_training_script:
        raise AssertionError("V0 residual policy trainer must be offline and must not create Brev instances")
    for expected_snippet in (
        "Evaluate or preflight a trained V0 residual policy checkpoint",
        "READY_FOR_LOCAL_SUPERVISED_EVAL_DRY_RUN",
        "SUPERVISED_EVAL_NEEDS_ISAAC_POLICY_GATE",
        "checkpoint_sha256",
        "not Isaac closed-loop evaluation",
        "It does not call Brev, Isaac, ROS, a",
    ):
        if expected_snippet not in policy_eval_script:
            raise AssertionError(f"V0 residual policy evaluator missing snippet: {expected_snippet}")
    if "brev create" in policy_eval_script or '"${BREV_BIN}" create' in policy_eval_script:
        raise AssertionError("V0 residual policy evaluator must be offline and must not create Brev instances")
    for expected_snippet in (
        "Check whether a V0 residual policy may move to promotion review",
        "READY_FOR_POLICY_PROMOTION_REVIEW",
        "v0_residual_policy_promotion_gate",
        "Isaac closed-loop policy evaluation",
        "same checkpoint checksum",
        "scripted-baseline comparison",
        "not direct drop-in precision on another robot arm",
        "It does not call Brev, start Isaac, ROS",
    ):
        if expected_snippet not in policy_promotion_gate:
            raise AssertionError(f"V0 policy promotion gate missing snippet: {expected_snippet}")
    if "brev create" in policy_promotion_gate or '"${BREV_BIN}" create' in policy_promotion_gate:
        raise AssertionError("V0 policy promotion gate must be offline and must not create Brev instances")
    for expected_snippet in (
        "Run the offline V0 policy-readiness pipeline",
        "v0_offline_policy_readiness_pipeline",
        "prepare_v0_policy_api_review.py",
        "audit_v0_policy_dataset.py",
        "plan_v0_policy_feature_dry_run.py",
        "audit_v0_policy_label_sources.py",
        "extract_v0_policy_label_dataset.py",
        "check_v0_policy_training_preflight.py",
        "train_v0_residual_policy.py",
        "not a paid run",
        "not a Brev or Isaac launcher",
        "not direct drop-in precision on another robot arm",
        "does not create, start, stop, delete, copy to, or execute on Brev",
    ):
        if expected_snippet not in policy_readiness_pipeline:
            raise AssertionError(f"V0 offline policy-readiness pipeline missing snippet: {expected_snippet}")
    if "brev create" in policy_readiness_pipeline or '"${BREV_BIN}" create' in policy_readiness_pipeline:
        raise AssertionError("V0 offline policy-readiness pipeline must not create Brev instances")
    for expected_snippet in (
        "external-arm portability",
        "ready_for_external_robot cannot be true while adapter evidence blockers remain",
        "ready_for_hardware_execution",
        "low_speed_hardware_contact_trial",
        "ee_pose_feedback",
        "cartesian_command_or_ik",
        "force_torque_or_contact_feedback",
        "low_speed_no_contact_dry_run",
        "adapter_frame_round_trip_check",
        "command_contract",
        "frame_contract",
        "runtime_guards",
        "abort_on_fault",
        "not direct drop-in precision on another robot arm",
        "It does not call Brev, Isaac, ROS, a",
    ):
        if expected_snippet not in robot_adapter_checker:
            raise AssertionError(f"V0 robot adapter checker missing snippet: {expected_snippet}")
    if "brev create" in robot_adapter_checker or '"${BREV_BIN}" create' in robot_adapter_checker:
        raise AssertionError("V0 robot adapter checker must be offline and must not create Brev instances")
    for expected_snippet in (
        "PASS_SAFE_BLOCKED",
        "ee_pose_feedback",
        "cartesian_command_or_ik",
        "force_torque_or_contact_feedback",
        "placeholders are not accepted",
        "not ready for hardware execution",
        "not autonomous hardware execution approval",
        "not direct drop-in precision on another robot arm",
        "It does not call Brev, Isaac, ROS, a",
    ):
        if expected_snippet not in robot_adapter_planner:
            raise AssertionError(f"V0 robot adapter planner missing snippet: {expected_snippet}")
    if "brev create" in robot_adapter_planner or '"${BREV_BIN}" create' in robot_adapter_planner:
        raise AssertionError("V0 robot adapter planner must be offline and must not create Brev instances")
    for expected_snippet in (
        "v0_cross_robot_portability_boundary",
        "universal_drop_in_ready",
        "READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW",
        "ready_for_hardware_execution",
        "BLOCKED_NOT_DROP_IN",
        "joint_cartesian_tool_and_feedback_interfaces",
        "force_torque_or_contact_feedback_thresholds",
        "not direct drop-in precision on another robot arm",
        "It does not call Brev, Isaac, ROS, a",
    ):
        if expected_snippet not in portability_checker:
            raise AssertionError(f"V0 portability boundary checker missing snippet: {expected_snippet}")
    if "brev create" in portability_checker or '"${BREV_BIN}" create' in portability_checker:
        raise AssertionError("V0 portability boundary checker must be offline and must not create Brev instances")
    for expected_snippet in (
        "v0_cross_robot_portability_review",
        "NO_DIRECT_DROP_IN",
        "universal_drop_in_ready",
        "target_adapter_preview",
        "adapter_workplan",
        "required_evidence_groups",
        "minimum_ordered_steps",
        "validate_joint_cartesian_tool_state_and_force_feedback_interfaces",
        "run_low_speed_no_contact_dry_run_before_any_contact_trial",
        "not a universal robot-arm policy",
        "not autonomous hardware execution approval",
        "ready_for_hardware_execution",
        "PASS_SAFE_BLOCKED",
        "writes_target_adapter_manifest",
        "named external-robot adapter contract",
        "language/request and skill-target layers are reusable",
        "not evidence that arbitrary robot arms can be used without adaptation",
        "It does not call Brev, start Isaac, call ROS",
    ):
        if expected_snippet not in portability_review:
            raise AssertionError(f"V0 portability review missing snippet: {expected_snippet}")
    if "brev create" in portability_review or '"${BREV_BIN}" create' in portability_review:
        raise AssertionError("V0 portability review must be offline and must not create Brev instances")

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if "raw_joint_targets" not in contract["language_layer"]["forbidden_outputs"]:
        raise AssertionError("V0 skill contract must forbid language-to-raw-joint outputs")
    if "not cross-robot-ready" not in contract["not_claims"]:
        raise AssertionError("V0 skill contract must preserve cross-robot non-claim")
    if contract["robot_adapter_contract"]["portability_rule"] != "new_robot_requires_adapter_calibration_and_revalidation":
        raise AssertionError("V0 skill contract must require revalidation for new robots")
    for required_section in ("required_command_contract", "required_frame_contract", "required_runtime_guards"):
        if required_section not in contract["robot_adapter_contract"]:
            raise AssertionError(f"V0 skill contract missing adapter section: {required_section}")

    with tempfile.TemporaryDirectory(prefix="rca-v0-skill-contract-tests-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        bad_contract = json.loads(contract_path.read_text(encoding="utf-8"))
        bad_contract["language_layer"]["forbidden_outputs"].remove("raw_joint_targets")
        bad_contract["promotion_gates"]["requires_min_strict_success_traces"] = 1
        bad_contract["not_claims"].remove("not direct drop-in precision on another robot arm")
        bad_path = tmp_dir / "bad_v0_skill_api_contract.json"
        bad_path.write_text(json.dumps(bad_contract), encoding="utf-8")
        result = run(["python3", str(checker_path), str(bad_path)])
        assert_status(result, 1, "V0 skill API contract validator rejects unsafe contract")
        assert_contains(result, "raw_joint_targets", "unsafe V0 skill contract raw joint detail")
        assert_contains(result, "requires_min_strict_success_traces", "unsafe V0 skill contract trace-count detail")
        assert_contains(result, "not direct drop-in precision", "unsafe V0 skill contract non-claim detail")

        bad_request = json.loads(request_path.read_text(encoding="utf-8"))
        bad_request["raw_joint_targets"] = [0.0, 0.1, 0.2, 0.0, 0.0, 0.0, 0.0]
        bad_request["skill_selection"]["controller_mode"] = "vlm_to_raw_joint_control"
        bad_request_path = tmp_dir / "bad_v0_skill_request.json"
        bad_request_path.write_text(json.dumps(bad_request), encoding="utf-8")
        result = run(["python3", str(request_checker_path), str(bad_request_path)])
        assert_status(result, 1, "V0 skill request validator rejects direct low-level control")
        assert_contains(result, "forbidden direct control keys", "unsafe V0 request direct-command detail")
        assert_contains(result, "controller_mode must be one of", "unsafe V0 request controller detail")

        premature_adapter = json.loads(robot_adapter_path.read_text(encoding="utf-8"))
        premature_adapter["ready_for_external_robot"] = True
        premature_adapter["ready_for_hardware_execution"] = True
        premature_adapter["target_robot"]["robot_id"] = "demo_arm"
        premature_adapter["not_claims"].remove("not direct drop-in precision on another robot arm")
        premature_adapter_path = tmp_dir / "premature_external_robot_adapter.json"
        premature_adapter_path.write_text(json.dumps(premature_adapter), encoding="utf-8")
        result = run(["python3", str(robot_adapter_checker_path), str(premature_adapter_path)])
        assert_status(result, 1, "V0 robot adapter checker rejects premature ready claim")
        assert_contains(result, "ready_for_external_robot cannot be true", "premature adapter ready failure detail")
        assert_contains(result, "ready_for_hardware_execution must remain false", "premature adapter hardware execution failure detail")
        assert_contains(result, "not direct drop-in precision", "premature adapter non-claim failure detail")

        planned_adapter_preview_path = tmp_dir / "planned_external_robot_adapter_preview.json"
        result = run(
            [
                "python3",
                str(robot_adapter_planner_path),
                "--robot-id",
                "demo_arm_v0",
                "--robot-family",
                "demo_6dof_arm",
                "--control-stack",
                "ros2_control_joint_trajectory",
                "--end-effector",
                "parallel_gripper_with_peg_fixture",
                "--joint-trajectory-action",
                "/demo_arm/joint_trajectory_controller/follow_joint_trajectory",
                "--joint-state-feedback",
                "/joint_states",
                "--skill-status",
                "/rca/skill_status",
                "--output-json",
                str(planned_adapter_preview_path),
                "--no-output",
            ]
        )
        assert_status(result, 0, "V0 robot adapter planner previews safe blocked manifest")
        assert_contains(result, "PASS_SAFE_BLOCKED", "V0 robot adapter planner preview safe-blocked detail")
        assert_contains(result, '"adapter_contract_status": "BLOCKED"', "V0 planner preview checker status detail")
        assert_contains(result, "command_contract.command_frame", "V0 planner preview blocker detail")
        preview_report, _ = json.JSONDecoder().raw_decode(
            result.stdout.split("[v0-robot-adapter-planner] facts=", 1)[1].lstrip()
        )
        if preview_report["adapter_contract_status"] != "BLOCKED":
            raise AssertionError(f"planned adapter preview should run contract checker: {preview_report}")
        if preview_report["status"] != "PASS_SAFE_BLOCKED":
            raise AssertionError(f"planned adapter preview status should be safe-blocked: {preview_report}")
        if not preview_report["adapter_contract_blockers"]:
            raise AssertionError(f"planned adapter preview should expose blockers: {preview_report}")
        if preview_report["output_json"] is not None:
            raise AssertionError(f"planned adapter preview must not report an output path: {preview_report}")
        if preview_report["side_effects"]["writes_adapter_manifest"] is not False:
            raise AssertionError(f"planned adapter preview must not write a manifest: {preview_report}")
        for key in ("creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if preview_report["side_effects"][key] is not False:
                raise AssertionError(f"planned adapter preview side effect must be false for {key}: {preview_report}")
        if planned_adapter_preview_path.exists():
            raise AssertionError("V0 adapter planner --no-output must not write a manifest")

        planned_adapter_path = tmp_dir / "planned_external_robot_adapter.json"
        result = run(
            [
                "python3",
                str(robot_adapter_planner_path),
                "--robot-id",
                "demo_arm_v0",
                "--robot-family",
                "demo_6dof_arm",
                "--control-stack",
                "ros2_control_joint_trajectory",
                "--end-effector",
                "parallel_gripper_with_peg_fixture",
                "--joint-trajectory-action",
                "/demo_arm/joint_trajectory_controller/follow_joint_trajectory",
                "--joint-state-feedback",
                "/joint_states",
                "--skill-status",
                "/rca/skill_status",
                "--output-json",
                str(planned_adapter_path),
            ]
        )
        assert_status(result, 0, "V0 robot adapter planner writes safe blocked manifest")
        assert_contains(result, "PASS_SAFE_BLOCKED", "V0 robot adapter planner safe-blocked detail")
        if "adapter manifest was not written" in (result.stderr or ""):
            raise AssertionError(f"V0 adapter planner must not claim no write after writing: {result.stderr}")
        planned_adapter = json.loads(planned_adapter_path.read_text(encoding="utf-8"))
        if planned_adapter["target_robot"]["robot_id"] != "demo_arm_v0":
            raise AssertionError(f"planned adapter has wrong robot id: {planned_adapter['target_robot']}")
        if planned_adapter["ready_for_external_robot"] is not False:
            raise AssertionError("planned adapter must not claim hardware readiness")
        if planned_adapter["ready_for_hardware_execution"] is not False:
            raise AssertionError("planned adapter must not claim direct hardware execution")
        if planned_adapter["direct_use_ready"] is not False:
            raise AssertionError("planned adapter must not claim direct external-robot use")
        if planned_adapter["transfer_readiness_level"] != "L1_NAMED_ADAPTER_DRAFT_BLOCKED":
            raise AssertionError(f"planned adapter should be a blocked named-adapter draft: {planned_adapter}")
        if planned_adapter["manual_hardware_approval_required"] is not True:
            raise AssertionError("planned adapter must require manual hardware approval")
        if planned_adapter["ros2_interfaces"]["joint_trajectory_action"]["validated"] is not False:
            raise AssertionError("planned adapter must leave ROS 2 interface validation blocked")
        for interface_name in (
            "cartesian_command_or_ik",
            "ee_pose_feedback",
            "end_effector_command",
            "force_torque_or_contact_feedback",
        ):
            if interface_name not in planned_adapter["ros2_interfaces"]:
                raise AssertionError(f"planned adapter missing robot interface: {interface_name}")
            if planned_adapter["ros2_interfaces"][interface_name]["validated"] is not False:
                raise AssertionError(f"planned adapter must leave {interface_name} validation blocked")
        for section in ("command_contract", "frame_contract", "runtime_guards"):
            if section not in planned_adapter:
                raise AssertionError(f"planned adapter missing section: {section}")
        if planned_adapter["runtime_guards"]["abort_on_fault"] is not True:
            raise AssertionError("planned adapter must preserve abort_on_fault guard")
        planned_report, _ = json.JSONDecoder().raw_decode(
            result.stdout.split("[v0-robot-adapter-planner] facts=", 1)[1].lstrip()
        )
        if planned_report["status"] != "PASS_SAFE_BLOCKED":
            raise AssertionError(f"planned adapter writer status should be safe-blocked: {planned_report}")
        if planned_report["adapter_contract_status"] != "BLOCKED":
            raise AssertionError(f"planned adapter writer should surface blocked checker status: {planned_report}")
        if planned_report["side_effects"]["writes_adapter_manifest"] is not True:
            raise AssertionError(f"planned adapter writer should disclose manifest write: {planned_report}")
        for key in ("creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if planned_report["side_effects"][key] is not False:
                raise AssertionError(f"planned adapter writer side effect must be false for {key}: {planned_report}")
        result = run(["python3", str(robot_adapter_checker_path), str(planned_adapter_path)])
        assert_status(result, 0, "V0 robot adapter checker accepts planned manifest as blocked")
        assert_contains(result, "[v0-robot-adapter] BLOCKED", "planned V0 robot adapter blocked detail")
        assert_contains(result, '"direct_use_ready": false', "planned adapter direct-use non-claim detail")
        assert_contains(result, "L1_NAMED_ADAPTER_DRAFT_BLOCKED", "planned adapter transfer readiness detail")
        assert_contains(result, "command_contract.command_frame", "planned adapter command-contract blocker detail")
        assert_contains(result, "runtime_guards.command_timeout_s", "planned adapter runtime guard blocker detail")
        assert_contains(result, "low_speed_hardware_contact_trial", "planned adapter revalidation blocker detail")

        placeholder_adapter_path = tmp_dir / "placeholder_external_robot_adapter.json"
        result = run(
            [
                "python3",
                str(robot_adapter_planner_path),
                "--robot-id",
                "replace_with_robot_id",
                "--robot-family",
                "demo_6dof_arm",
                "--end-effector",
                "parallel_gripper",
                "--output-json",
                str(placeholder_adapter_path),
            ]
        )
        assert_status(result, 1, "V0 robot adapter planner rejects placeholder robot id")
        assert_contains(result, "placeholders are not accepted", "V0 adapter planner placeholder detail")
        if placeholder_adapter_path.exists():
            raise AssertionError("V0 adapter planner must not write a manifest for placeholder robot id")

        planned_request_path = tmp_dir / "planned_v0_skill_request.json"
        result = run(
            [
                "python3",
                str(planner_path),
                "insert the peg into the right socket",
                "--output-json",
                str(planned_request_path),
            ]
        )
        assert_status(result, 0, "V0 skill request planner writes supported insert request")
        assert_contains(result, "[v0-skill-planner] PASS", "V0 planner PASS detail")
        planned_request = json.loads(planned_request_path.read_text(encoding="utf-8"))
        if planned_request["task_parameters"]["socket_id"] != "right_socket":
            raise AssertionError(f"V0 planner should normalize right socket target: {planned_request}")
        result = run(["python3", str(request_checker_path), str(planned_request_path)])
        assert_status(result, 0, "V0 skill request validator accepts planned request")

        blocked_request_path = tmp_dir / "blocked_v0_skill_request.json"
        result = run(
            [
                "python3",
                str(planner_path),
                "move joint 4 down by 2 degrees",
                "--output-json",
                str(blocked_request_path),
            ]
        )
        assert_status(result, 1, "V0 skill request planner rejects low-level joint instruction")
        assert_contains(result, "must request the high-level insert skill", "V0 planner low-level rejection detail")
        if blocked_request_path.exists():
            raise AssertionError("V0 planner must not write a request artifact after a rejected instruction")

        substring_request_path = tmp_dir / "substring_v0_skill_request.json"
        result = run(
            [
                "python3",
                str(planner_path),
                "insert the peg into the bright socket",
                "--output-json",
                str(substring_request_path),
            ]
        )
        assert_status(result, 1, "V0 skill request planner rejects substring socket aliases")
        assert_contains(
            result,
            "must specify a supported socket target",
            "V0 planner substring socket rejection detail",
        )
        if substring_request_path.exists():
            raise AssertionError("V0 planner must not write a request artifact for substring socket aliases")

        bad_language_suite = json.loads(language_suite_path.read_text(encoding="utf-8"))
        bad_language_suite["cases"][0]["expected_socket_id"] = "right_socket"
        bad_language_suite_path = tmp_dir / "bad_v0_language_instruction_suite.json"
        bad_language_suite_path.write_text(json.dumps(bad_language_suite), encoding="utf-8")
        result = run(["python3", str(language_suite_checker_path), str(bad_language_suite_path), "--no-output"])
        assert_status(result, 1, "V0 language instruction suite rejects wrong expected socket")
        assert_contains(result, "expected socket_id right_socket", "V0 language suite wrong-socket detail")

        current_readiness_json = tmp_dir / "current_v0_skill_readiness.json"
        result = run(
            [
                "python3",
                str(readiness_checker_path),
                str(request_path),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(current_readiness_json),
            ]
        )
        assert_status(result, 0, "V0 skill readiness checker reports current blocked state without failing by default")
        assert_contains(result, "[v0-skill-readiness] BLOCKED", "current V0 readiness blocked detail")
        assert_contains(
            result,
            "next_action=run_fixed_budget_success_variation_batch_after_paid_ack",
            "current V0 readiness next action detail",
        )
        current_readiness = json.loads(current_readiness_json.read_text(encoding="utf-8"))
        if current_readiness["status"] != "BLOCKED":
            raise AssertionError(f"current V0 readiness should be blocked before variation batch: {current_readiness}")
        if current_readiness["next_action"] != "run_fixed_budget_success_variation_batch_after_paid_ack":
            raise AssertionError(f"current V0 readiness should point to variation batch: {current_readiness}")
        if current_readiness["side_effects"]["writes_readiness_report"] is not True:
            raise AssertionError(f"current V0 readiness should disclose local report write: {current_readiness}")
        for key in ("writes_dataset_artifacts", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if current_readiness["side_effects"][key] is not False:
                raise AssertionError(f"current V0 readiness side effect must be false for {key}: {current_readiness}")
        blocked_review_json = tmp_dir / "blocked_v0_policy_api_review.json"
        blocked_review_md = tmp_dir / "blocked_v0_policy_api_review.md"
        result = run(
            [
                "python3",
                str(policy_api_review_path),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(blocked_review_json),
                "--output-md",
                str(blocked_review_md),
            ]
        )
        assert_status(result, 1, "V0 policy/API review prep blocks current incomplete state")
        assert_contains(result, "[v0-policy-api-review] BLOCKED", "blocked V0 policy/API review detail")
        blocked_policy_review, _ = json.JSONDecoder().raw_decode(
            result.stdout.split("[v0-policy-api-review] facts=", 1)[1].lstrip()
        )
        if blocked_policy_review["status"] != "BLOCKED":
            raise AssertionError(f"blocked V0 policy/API review should expose BLOCKED facts: {blocked_policy_review}")
        for key in (
            "writes_review_artifacts",
            "writes_dataset_artifacts",
            "writes_policy_artifacts",
            "writes_checkpoint",
            "trains_policy",
            "creates_paid_instance",
            "runs_remote_code",
            "starts_isaac",
            "calls_ros_or_robot",
        ):
            if blocked_policy_review["side_effects"][key] is not False:
                raise AssertionError(f"blocked V0 policy/API review side effect must be false for {key}: {blocked_policy_review}")
        if blocked_review_json.exists() or blocked_review_md.exists():
            raise AssertionError("blocked V0 policy/API review must not write artifacts")


def run_success_variation_manifest_tests() -> None:
    language_dry_run_path = REPO_ROOT / "scripts" / "run_v0_language_skill_dry_run.py"
    policy_readiness_pipeline_path = REPO_ROOT / "scripts" / "run_v0_offline_policy_readiness_pipeline.py"
    source_trace = (
        REPO_ROOT
        / "artifacts"
        / "deliverables"
        / "2026-06-21-peg-in-hole-success-trace"
        / "video_trace.json"
    )
    with tempfile.TemporaryDirectory(prefix="rca-success-variation-tests-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        manifest_path = tmp_dir / "success_variations.json"
        results_root = tmp_dir / "results"
        report_json = tmp_dir / "classification.json"
        report_md = tmp_dir / "classification.md"

        result = run(
            [
                "python3",
                "scripts/create_success_variation_manifest.py",
                "--output",
                str(manifest_path),
                "--output-trace-root",
                "artifacts/videos/success_variations/2026-06-25",
            ]
        )
        assert_status(result, 0, "success variation manifest generator exits cleanly")
        assert_contains(result, "[success-variations] wrote manifest", "success variation manifest output")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = {case["case_id"]: case for case in manifest["cases"]}
        if len(cases) != 9:
            raise AssertionError(f"expected 9 variation cases, got {len(cases)}")
        if cases["baseline_replay"]["status"] != "available":
            raise AssertionError("baseline replay must be available as the positive control")
        if cases["socket_x_pos_25mm_negative_control"]["expected"] != "fail_closed":
            raise AssertionError("large socket perturbation must be marked as a fail-closed negative control")
        if manifest["remote_run_policy"]["paid_compute_allowed"] is not False:
            raise AssertionError("variation manifest must not allow paid compute by default")

        result = run(
            [
                "python3",
                "scripts/classify_success_variation_results.py",
                str(manifest_path),
                "--output-json",
                str(report_json),
                "--output-md",
                str(report_md),
            ]
        )
        assert_status(result, 0, "success variation classifier handles baseline-only manifest")
        assert_contains(result, "strict_success=1", "baseline-only classifier strict success count")
        assert_contains(result, "missing=8", "baseline-only classifier missing count")
        report = json.loads(report_json.read_text(encoding="utf-8"))
        counts = report["summary"]["classification_counts"]
        if counts != {"missing": 8, "strict_success": 1}:
            raise AssertionError(f"unexpected baseline-only classification counts: {counts}")
        if "baseline_replay" not in report_md.read_text(encoding="utf-8"):
            raise AssertionError("classification markdown should include the baseline case row")

        bad_trace = tmp_dir / "bad_video_trace.json"
        payload = json.loads(source_trace.read_text(encoding="utf-8"))
        if isinstance(payload.get("summary"), dict):
            payload["summary"]["success_step"] = None
            payload["summary"]["final_success_rate"] = 0.0
            payload["summary"]["best_lateral"] = 0.050
        for step in payload.get("steps", []):
            if isinstance(step, dict):
                step["success"] = False
                step["lateral"] = 0.050
        bad_trace.write_text(json.dumps(payload), encoding="utf-8")

        cases["seed_43_nominal"]["trace_json"] = str(bad_trace)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/classify_success_variation_results.py",
                str(manifest_path),
                "--output-json",
                str(report_json),
            ]
        )
        assert_status(result, 0, "success variation classifier handles a bad trace")
        assert_contains(result, "fail_closed=1", "bad-trace classifier fail-closed count")
        report = json.loads(report_json.read_text(encoding="utf-8"))
        by_case = {case["case_id"]: case for case in report["results"]}
        if by_case["seed_43_nominal"]["classification"] != "fail_closed":
            raise AssertionError(f"bad trace should fail closed: {by_case['seed_43_nominal']}")

        plan_json = tmp_dir / "batch_plan.json"
        plan_sh = tmp_dir / "batch_plan.sh"
        result = run(
            [
                "python3",
                "scripts/plan_success_variation_batch.py",
                str(manifest_path),
                "--output-json",
                str(plan_json),
                "--output-sh",
                str(plan_sh),
            ]
        )
        assert_status(result, 0, "success variation batch planner handles manifest")
        assert_contains(result, "cases=8", "success variation planner excludes available baseline by default")
        plan = json.loads(plan_json.read_text(encoding="utf-8"))
        by_plan_case = {case["case_id"]: case for case in plan["cases"]}
        if "baseline_replay" in by_plan_case:
            raise AssertionError("batch planner should not rerun the available baseline unless explicitly requested")
        if by_plan_case["socket_x_pos_1mm"]["socket_pos_m"] != [0.521, 0.0, 0.19]:
            raise AssertionError(f"socket X +1mm plan has wrong absolute socket position: {by_plan_case['socket_x_pos_1mm']}")
        if "--socket-pos 0.521000,0.000000,0.190000" not in by_plan_case["socket_x_pos_1mm"]["env"].get(
            "RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS", ""
        ):
            raise AssertionError("socket X +1mm plan must pass --socket-pos through the runner env")
        if "--reset-joint-noise-rad 0.010000" not in by_plan_case["seed_44_reset_noise"]["env"].get(
            "RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS", ""
        ):
            raise AssertionError("reset-noise variation must pass explicit reset noise through the runner env")
        if by_plan_case["socket_x_pos_25mm_negative_control"]["remote_trace_dir"] != (
            "/workspace/artifacts/videos/success_variations/2026-06-25/socket_x_pos_25mm_negative_control"
        ):
            raise AssertionError("negative-control remote trace dir must match the manifest planned artifact path")
        rendered_plan = plan_sh.read_text(encoding="utf-8")
        for expected_snippet in (
            "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE=0",
            "RCA_TRACE_VARIATION_CASE_ID=socket_x_pos_25mm_negative_control",
            "scripts/run_remote_joint_response_socket_insertion_servo_trace.sh",
        ):
            if expected_snippet not in rendered_plan:
                raise AssertionError(f"rendered batch plan missing snippet: {expected_snippet}")

        plan_gate_json = tmp_dir / "batch_plan_gate.json"
        result = run(
            [
                "python3",
                "scripts/check_success_variation_batch_plan.py",
                str(manifest_path),
                "--output-json",
                str(plan_gate_json),
            ]
        )
        assert_status(result, 0, "success variation batch plan gate accepts generated plan")
        assert_contains(result, "[success-variation-plan-gate] PASS", "success variation batch plan-gate PASS detail")
        plan_gate = json.loads(plan_gate_json.read_text(encoding="utf-8"))
        if plan_gate["summary"]["planned_case_count"] != 8:
            raise AssertionError(f"plan gate should audit the 8 planned cases: {plan_gate['summary']}")
        if plan_gate["summary"]["negative_control_in_plan"] is not True:
            raise AssertionError(f"plan gate must include the negative control: {plan_gate['summary']}")

        bad_plan_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for case in bad_plan_manifest["cases"]:
            if case["case_id"] == "socket_x_pos_1mm":
                case["planned_trace_json"] = "/tmp/bad/video_trace.json"
        bad_plan_manifest_path = tmp_dir / "success_variations_bad_plan.json"
        bad_plan_manifest_path.write_text(json.dumps(bad_plan_manifest), encoding="utf-8")
        result = run(["python3", "scripts/check_success_variation_batch_plan.py", str(bad_plan_manifest_path)])
        assert_status(result, 1, "success variation batch plan gate rejects artifact path escapes")
        assert_contains(result, "[success-variation-plan-gate] BLOCKED", "bad plan-gate blocked detail")
        assert_contains(result, "planned trace", "bad plan-gate failure reason")

        result = run(["python3", "scripts/check_success_variation_batch_results.py", str(manifest_path)])
        assert_status(result, 1, "success variation result gate rejects incomplete batch")
        assert_contains(result, "missing planned trace artifacts", "incomplete variation batch result-gate detail")
        recovery_json = tmp_dir / "recovery_plan.json"
        recovery_sh = tmp_dir / "recovery_plan.sh"
        result = run(
            [
                "python3",
                "scripts/plan_success_variation_recovery_batch.py",
                str(manifest_path),
                "--output-json",
                str(recovery_json),
                "--output-sh",
                str(recovery_sh),
            ]
        )
        assert_status(result, 0, "success variation recovery planner handles incomplete batch")
        assert_contains(result, "[success-variation-recovery] facts=", "recovery planner facts detail")
        assert_contains(result, "[success-variation-recovery] status=READY", "recovery planner ready detail")
        recovery = json.loads(recovery_json.read_text(encoding="utf-8"))
        if recovery["rerun_case_count"] != 8:
            raise AssertionError(f"baseline-only recovery should rerun 8 planned cases: {recovery}")
        if "baseline_replay" in recovery["rerun_case_ids"]:
            raise AssertionError("recovery planner must not rerun the baseline positive control")
        if "socket_x_pos_25mm_negative_control" not in recovery_sh.read_text(encoding="utf-8"):
            raise AssertionError("recovery shell should include the missing negative-control rerun")
        recovery_no_output_json = tmp_dir / "recovery_no_output.json"
        recovery_no_output_sh = tmp_dir / "recovery_no_output.sh"
        result = run(
            [
                "python3",
                "scripts/plan_success_variation_recovery_batch.py",
                str(manifest_path),
                "--output-json",
                str(recovery_no_output_json),
                "--output-sh",
                str(recovery_no_output_sh),
                "--no-output",
            ]
        )
        assert_status(result, 0, "success variation recovery planner supports no-output status mode")
        assert_contains(result, '"writes_recovery_artifacts": false', "recovery planner no-output side-effect detail")
        if recovery_no_output_json.exists() or recovery_no_output_sh.exists():
            raise AssertionError("no-output recovery planner must not write recovery artifacts")

        blocked_dataset_json = tmp_dir / "blocked_dataset" / "manifest.json"
        blocked_dataset_md = tmp_dir / "blocked_dataset" / "README.md"
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_dataset.py",
                str(manifest_path),
                "--output-json",
                str(blocked_dataset_json),
                "--output-md",
                str(blocked_dataset_md),
            ]
        )
        assert_status(result, 1, "success variation dataset prep rejects incomplete batch")
        assert_contains(result, "[success-variation-dataset] BLOCKED", "blocked dataset prep detail")
        if blocked_dataset_json.exists() or blocked_dataset_md.exists():
            raise AssertionError("blocked dataset prep must not write dataset artifacts")
        blocked_dry_run_json = tmp_dir / "blocked_dataset_dry_run" / "manifest.json"
        blocked_dry_run_md = tmp_dir / "blocked_dataset_dry_run" / "README.md"
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_dataset.py",
                str(manifest_path),
                "--output-json",
                str(blocked_dry_run_json),
                "--output-md",
                str(blocked_dry_run_md),
                "--no-output",
            ]
        )
        assert_status(result, 1, "success variation dataset dry-run rejects incomplete batch")
        assert_contains(result, "[success-variation-dataset] facts=", "blocked dataset dry-run facts detail")
        assert_contains(result, '"writes_dataset_artifacts": false', "blocked dataset dry-run no-write detail")
        if blocked_dry_run_json.exists() or blocked_dry_run_md.exists():
            raise AssertionError("blocked dataset dry-run must not write dataset artifacts")

        review_json = tmp_dir / "success_variation_review.json"
        review_md = tmp_dir / "success_variation_review.md"
        result = run(
            [
                "python3",
                "scripts/review_success_variation_batch.py",
                str(manifest_path),
                "--skip-brev-safety",
                "--output-json",
                str(review_json),
                "--output-md",
                str(review_md),
            ]
        )
        assert_status(result, 0, "success variation review summarizes incomplete batch")
        assert_contains(result, "decision=continue_variation_batch_or_debug", "incomplete review decision detail")
        review = json.loads(review_json.read_text(encoding="utf-8"))
        if review["decision"] != "continue_variation_batch_or_debug":
            raise AssertionError(f"incomplete batch review has wrong decision: {review['decision']}")
        if "missing planned trace artifacts" not in review_md.read_text(encoding="utf-8"):
            raise AssertionError("review markdown should include missing-artifact failure detail")

        finalize_dry_run_dir = tmp_dir / "finalize_dry_run"
        result = run(
            [
                "scripts/finalize_success_variation_batch.sh",
                str(manifest_path),
                "--dry-run",
            ],
            env={
                "RCA_SUCCESS_VARIATION_FINALIZE_SKIP_BREV_SAFETY": "1",
                "RCA_SUCCESS_VARIATION_RESULTS_ROOT": str(finalize_dry_run_dir / "pulled_results"),
                "RCA_SUCCESS_VARIATION_REVIEW_JSON": str(finalize_dry_run_dir / "review.json"),
                "RCA_SUCCESS_VARIATION_REVIEW_MD": str(finalize_dry_run_dir / "review.md"),
                "RCA_SUCCESS_VARIATION_RESULT_GATE_JSON": str(finalize_dry_run_dir / "result_gate.json"),
                "RCA_SUCCESS_VARIATION_DATASET_JSON": str(finalize_dry_run_dir / "dataset" / "manifest.json"),
                "RCA_SUCCESS_VARIATION_DATASET_MD": str(finalize_dry_run_dir / "dataset" / "README.md"),
            },
        )
        assert_status(result, 0, "success variation finalizer dry-run previews handoff")
        assert_contains(result, "[success-variation-finalize] DRY_RUN", "finalizer dry-run marker")
        assert_contains(result, '"writes_review_record": false', "finalizer dry-run no review write detail")
        assert_contains(result, '"writes_dataset_artifacts": false', "finalizer dry-run no dataset write detail")
        assert_contains(result, '"results_root":', "finalizer dry-run results-root detail")
        assert_contains(result, "--results-root", "finalizer dry-run results-root command detail")
        assert_contains(result, "review_success_variation_batch.py", "finalizer dry-run review command detail")
        assert_contains(result, "prepare_success_variation_dataset.py", "finalizer dry-run dataset command detail")
        if finalize_dry_run_dir.exists():
            raise AssertionError("finalizer dry-run must not write review/result/dataset artifacts")

        finalize_blocked_dir = tmp_dir / "finalize_blocked"
        result = run(
            [
                "scripts/finalize_success_variation_batch.sh",
                str(manifest_path),
            ],
            env={
                "RCA_SUCCESS_VARIATION_FINALIZE_SKIP_BREV_SAFETY": "1",
                "RCA_SUCCESS_VARIATION_REVIEW_JSON": str(finalize_blocked_dir / "review.json"),
                "RCA_SUCCESS_VARIATION_REVIEW_MD": str(finalize_blocked_dir / "review.md"),
                "RCA_SUCCESS_VARIATION_RESULT_GATE_JSON": str(finalize_blocked_dir / "result_gate.json"),
                "RCA_SUCCESS_VARIATION_DATASET_JSON": str(finalize_blocked_dir / "dataset" / "manifest.json"),
                "RCA_SUCCESS_VARIATION_DATASET_MD": str(finalize_blocked_dir / "dataset" / "README.md"),
            },
        )
        assert_status(result, 1, "success variation finalizer blocks incomplete batch")
        assert_contains(result, "[success-variation-finalize] BLOCKED", "blocked finalizer detail")
        if not (finalize_blocked_dir / "review.json").is_file():
            raise AssertionError("blocked finalizer should still write the review record")
        if (finalize_blocked_dir / "dataset" / "manifest.json").exists():
            raise AssertionError("blocked finalizer must not write dataset manifest")

        pass_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for case in pass_manifest["cases"]:
            case_id = case["case_id"]
            if case_id == "baseline_replay":
                continue
            if case_id == "socket_x_pos_25mm_negative_control":
                case["trace_json"] = str(bad_trace)
            else:
                case["trace_json"] = str(source_trace)
        pass_manifest_path = tmp_dir / "success_variations_pass.json"
        pass_manifest_path.write_text(json.dumps(pass_manifest), encoding="utf-8")

        sparse_coverage_manifest = json.loads(pass_manifest_path.read_text(encoding="utf-8"))
        for case in sparse_coverage_manifest["cases"]:
            if case["case_id"] in {"socket_y_neg_1mm", "socket_z_pos_1mm"}:
                case["trace_json"] = str(bad_trace)
        sparse_coverage_manifest_path = tmp_dir / "success_variations_sparse_coverage.json"
        sparse_coverage_manifest_path.write_text(json.dumps(sparse_coverage_manifest), encoding="utf-8")
        result = run(
            ["python3", "scripts/check_success_variation_batch_results.py", str(sparse_coverage_manifest_path)]
        )
        assert_status(result, 1, "success variation result gate rejects sparse variation coverage")
        assert_contains(result, "missing required strict-success variation coverage groups", "sparse coverage failure detail")
        assert_contains(result, "socket_z", "sparse coverage missing group detail")

        result = run(["python3", "scripts/check_success_variation_batch_results.py", str(pass_manifest_path)])
        assert_status(result, 0, "success variation result gate accepts strict successes plus fail-closed negative")
        assert_contains(result, "[success-variation-result-gate] PASS", "success variation result-gate PASS detail")
        result = run(
            [
                "python3",
                "scripts/plan_success_variation_recovery_batch.py",
                str(pass_manifest_path),
                "--output-json",
                str(recovery_json),
                "--output-sh",
                str(recovery_sh),
            ]
        )
        assert_status(result, 0, "success variation recovery planner skips fully promotable batch")
        assert_contains(result, "status=NOTHING_TO_RERUN", "recovery planner no-rerun detail")
        recovery = json.loads(recovery_json.read_text(encoding="utf-8"))
        if recovery["rerun_case_count"] != 0 or recovery["blocked_case_count"] != 0:
            raise AssertionError(f"promotable batch should have no recovery reruns: {recovery}")
        dataset_json = tmp_dir / "dataset" / "manifest.json"
        dataset_md = tmp_dir / "dataset" / "README.md"
        dataset_dry_run_json = tmp_dir / "dataset_dry_run" / "manifest.json"
        dataset_dry_run_md = tmp_dir / "dataset_dry_run" / "README.md"
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_dataset.py",
                str(pass_manifest_path),
                "--output-json",
                str(dataset_dry_run_json),
                "--output-md",
                str(dataset_dry_run_md),
                "--dry-run",
            ]
        )
        assert_status(result, 0, "success variation dataset dry-run accepts promotable batch")
        assert_contains(result, "[success-variation-dataset] DRY_RUN", "dataset dry-run marker")
        assert_contains(result, '"status": "READY_FOR_POLICY_API_REVIEW"', "dataset dry-run ready facts detail")
        assert_contains(result, '"writes_dataset_artifacts": false', "dataset dry-run no-write detail")
        if dataset_dry_run_json.exists() or dataset_dry_run_md.exists():
            raise AssertionError("dataset dry-run must not write dataset artifacts")
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_dataset.py",
                str(pass_manifest_path),
                "--output-json",
                str(dataset_json),
                "--output-md",
                str(dataset_md),
            ]
        )
        assert_status(result, 0, "success variation dataset prep accepts promotable batch")
        assert_contains(result, "READY_FOR_POLICY_API_REVIEW", "dataset prep ready detail")
        dataset = json.loads(dataset_json.read_text(encoding="utf-8"))
        if dataset["dataset_name"] != "v0_scripted_skill_success_variations":
            raise AssertionError(f"dataset prep wrote wrong dataset name: {dataset['dataset_name']}")
        if dataset.get("skill_api_contract") != "configs/v0_skill_api_contract.json":
            raise AssertionError(f"dataset prep must reference the V0 skill API contract: {dataset.get('skill_api_contract')}")
        if len(dataset["cases"]) < 6:
            raise AssertionError(f"dataset prep should include baseline plus strict variations: {len(dataset['cases'])}")
        dataset_case_ids = {case["case_id"] for case in dataset["cases"]}
        if "socket_x_pos_25mm_negative_control" in dataset_case_ids:
            raise AssertionError("dataset prep must exclude the negative-control case")
        if dataset["selection_policy"].get("requires_negative_control_fail_closed_evidence") is not True:
            raise AssertionError(f"dataset prep must require negative-control evidence: {dataset['selection_policy']}")
        excluded_by_id = {case["case_id"]: case for case in dataset["excluded_cases"]}
        excluded_negative = excluded_by_id.get("socket_x_pos_25mm_negative_control")
        if not excluded_negative:
            raise AssertionError(f"dataset prep must record excluded negative-control case: {dataset['excluded_cases']}")
        if excluded_negative["classification"] != "fail_closed" or excluded_negative["reason"] != "fail_closed_negative_control":
            raise AssertionError(f"dataset prep must preserve fail-closed negative exclusion: {excluded_negative}")
        negative_evidence = dataset.get("negative_control_evidence")
        if not isinstance(negative_evidence, dict):
            raise AssertionError(f"dataset prep must expose negative_control_evidence: {dataset}")
        if negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"negative_control_evidence should name the negative case: {negative_evidence}")
        if negative_evidence.get("classification") != "fail_closed" or negative_evidence.get("expected") != "fail_closed":
            raise AssertionError(f"negative_control_evidence must prove fail_closed behavior: {negative_evidence}")
        if negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"negative_control_evidence must stay outside training cases: {negative_evidence}")
        if negative_evidence.get("trace_sha256") != sha256_path(bad_trace):
            raise AssertionError(f"negative_control_evidence should checksum the negative trace: {negative_evidence}")
        if "not learned policy" not in dataset["not_claims"] or "not sim-to-real" not in dataset["not_claims"]:
            raise AssertionError(f"dataset prep must carry explicit non-claims: {dataset['not_claims']}")
        if "V0 Scripted Skill Success Variations Dataset" not in dataset_md.read_text(encoding="utf-8"):
            raise AssertionError("dataset prep README should include a clear title")
        ready_skill_json = tmp_dir / "ready_v0_skill_readiness.json"
        result = run(
            [
                "python3",
                "scripts/check_v0_skill_readiness.py",
                "configs/v0_skill_request.example.json",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(ready_skill_json),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 skill readiness checker accepts promotable manifest plus dataset")
        assert_contains(result, "[v0-skill-readiness] READY", "ready V0 skill readiness detail")
        ready_skill = json.loads(ready_skill_json.read_text(encoding="utf-8"))
        if ready_skill["next_action"] != "ready_for_policy_api_review":
            raise AssertionError(f"ready V0 skill should point to policy/API review: {ready_skill}")
        if ready_skill["side_effects"]["writes_readiness_report"] is not True:
            raise AssertionError(f"ready V0 skill should disclose local report write: {ready_skill}")
        for key in ("writes_dataset_artifacts", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if ready_skill["side_effects"][key] is not False:
                raise AssertionError(f"ready V0 skill side effect must be false for {key}: {ready_skill}")
        ready_adapter = json.loads((REPO_ROOT / "configs" / "v0_external_robot_adapter.template.json").read_text(encoding="utf-8"))
        evidence_dir = tmp_dir / "adapter_evidence"
        evidence_dir.mkdir()
        evidence_files: dict[str, str] = {}
        for name in (
            "robot_model.usd",
            "joint_limits.json",
            "tool_geometry.json",
            "tcp_transform.json",
            "controller_interface.md",
            "base_frame_alignment.json",
            "tool_center_point.json",
            "socket_fixture_frame.json",
            "calibration_error_bounds.json",
            "joint_limit_check.json",
            "workspace_limit_check.json",
            "collision_clearance_check.json",
            "controller_timeout.json",
            "emergency_stop_path.md",
            "force_torque_limit_check.json",
            "low_speed_no_contact_dry_run.json",
            "low_speed_contact_validation.json",
            "adapter_frame_round_trip_check.json",
            "phase2_contact_gate_equivalent.json",
            "strict_success_variation_batch.json",
            "negative_control_fail_closed.json",
            "low_speed_hardware_contact_trial.json",
        ):
            path = evidence_dir / name
            path.write_text('{"status":"pass"}\n', encoding="utf-8")
            evidence_files[name] = str(path)
        ready_adapter["adapter_name"] = "v0_external_robot_adapter_demo_arm_ready_fixture"
        ready_adapter["ready_for_external_robot"] = True
        ready_adapter["target_robot"] = {
            "robot_id": "demo_arm_ready_fixture",
            "robot_family": "demo_6dof_arm",
            "control_stack": "ros2_control_joint_trajectory",
            "end_effector": "parallel_gripper_with_peg_fixture",
        }
        ready_adapter["model_sources"] = {
            "robot_urdf_or_usd": evidence_files["robot_model.usd"],
            "joint_limits": evidence_files["joint_limits.json"],
            "tool_geometry": evidence_files["tool_geometry.json"],
            "tcp_transform": evidence_files["tcp_transform.json"],
            "controller_interface_spec": evidence_files["controller_interface.md"],
        }
        ready_adapter["calibration_evidence"] = {
            "base_frame_alignment": evidence_files["base_frame_alignment.json"],
            "tool_center_point": evidence_files["tool_center_point.json"],
            "socket_fixture_frame": evidence_files["socket_fixture_frame.json"],
            "calibration_error_bounds": evidence_files["calibration_error_bounds.json"],
            "camera_or_perception_frame_if_used": None,
            "force_or_contact_thresholds_if_used": None,
        }
        ready_adapter["safety_evidence"] = {
            "joint_limit_check": evidence_files["joint_limit_check.json"],
            "workspace_limit_check": evidence_files["workspace_limit_check.json"],
            "collision_or_clearance_check": evidence_files["collision_clearance_check.json"],
            "controller_timeout": evidence_files["controller_timeout.json"],
            "emergency_stop_path": evidence_files["emergency_stop_path.md"],
            "force_torque_limit_check": evidence_files["force_torque_limit_check.json"],
            "low_speed_no_contact_dry_run": evidence_files["low_speed_no_contact_dry_run.json"],
            "low_speed_contact_validation": evidence_files["low_speed_contact_validation.json"],
        }
        ready_adapter["ros2_interfaces"] = {
            "cartesian_command_or_ik": {
                "interface": "/demo_arm/cartesian_servo_or_ik",
                "validated": True,
            },
            "ee_pose_feedback": {"interface": "/demo_arm/tcp_pose", "validated": True},
            "end_effector_command": {"interface": "/demo_arm/gripper/command", "validated": True},
            "force_torque_or_contact_feedback": {"interface": "/demo_arm/wrench", "validated": True},
            "joint_trajectory_action": {
                "interface": "/demo_arm/joint_trajectory_controller/follow_joint_trajectory",
                "validated": True,
            },
            "joint_state_feedback": {"interface": "/joint_states", "validated": True},
            "skill_status": {"interface": "/rca/skill_status", "validated": True},
        }
        ready_adapter["command_contract"] = {
            "skill_target_schema": "configs/v0_skill_api_contract.json#skill_request_schema",
            "command_acknowledgement": "action_result_or_vendor_ack",
            "command_frame": "socket_frame",
            "command_units": "meters_radians_seconds",
            "control_mode": "joint_trajectory_low_speed_contact",
            "feedback_fields": ["joint_state", "ee_pose", "wrench", "tool_state", "skill_status", "fault_state"],
            "abort_conditions": ["stale_state", "controller_fault", "workspace_limit"],
            "rate_limits": "max_hz=20,max_translation_step_m=0.001",
        }
        ready_adapter["frame_contract"] = {
            "base_frame": "demo_arm_base",
            "tool_frame": "demo_tool0",
            "tcp_frame": "demo_tcp",
            "socket_frame": "demo_socket_fixture",
            "calibration_error_bounds": "tcp<=0.001m,rot<=0.01rad",
            "transform_source": "calibrated_static_tf",
            "timestamp_source": "ros_clock",
        }
        ready_adapter["runtime_guards"] = {
            "max_contact_force_n": 15.0,
            "max_translation_step_m": 0.001,
            "max_tcp_speed_mps": 0.005,
            "max_rotation_step_rad": 0.01,
            "max_joint_delta_rad": 0.02,
            "command_timeout_s": 0.5,
            "stale_state_timeout_s": 0.25,
            "abort_on_fault": True,
            "low_speed_mode_required": True,
        }
        ready_adapter["revalidation_evidence"] = {
            "adapter_frame_round_trip_check": evidence_files["adapter_frame_round_trip_check.json"],
            "phase2_contact_gate_equivalent": evidence_files["phase2_contact_gate_equivalent.json"],
            "strict_success_variation_batch": evidence_files["strict_success_variation_batch.json"],
            "negative_control_fail_closed": evidence_files["negative_control_fail_closed.json"],
            "low_speed_no_contact_dry_run": evidence_files["low_speed_no_contact_dry_run.json"],
            "low_speed_hardware_contact_trial": evidence_files["low_speed_hardware_contact_trial.json"],
        }
        ready_adapter_path = tmp_dir / "ready_external_robot_adapter.json"
        ready_adapter_path.write_text(json.dumps(ready_adapter), encoding="utf-8")
        result = run(["python3", "scripts/check_v0_robot_adapter_contract.py", str(ready_adapter_path), "--fail-on-blocked"])
        assert_status(result, 0, "V0 robot adapter checker accepts complete named-robot evidence fixture")
        assert_contains(result, "[v0-robot-adapter] READY", "ready V0 robot adapter detail")
        assert_contains(result, '"direct_use_ready": false', "ready V0 adapter still rejects direct use")
        assert_contains(
            result,
            '"transfer_readiness_level": "L2_NAMED_ROBOT_LOW_SPEED_REVIEW_READY"',
            "ready V0 adapter transfer level detail",
        )
        portability_json = tmp_dir / "portability" / "boundary.json"
        result = run(
            [
                "python3",
                "scripts/check_v0_portability_boundary.py",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--adapter",
                str(ready_adapter_path),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(portability_json),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 portability boundary accepts ready V0 skill plus named adapter")
        assert_contains(
            result,
            "READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW",
            "ready V0 portability boundary detail",
        )
        assert_contains(result, "universal_drop_in_ready=false", "ready portability boundary keeps universal non-claim")
        portability = json.loads(portability_json.read_text(encoding="utf-8"))
        if portability["universal_drop_in_ready"] is not False:
            raise AssertionError(f"portability gate must never claim arbitrary-arm drop-in readiness: {portability}")
        if portability["direct_use_ready"] is not False:
            raise AssertionError(f"portability gate must never claim direct external-robot use: {portability}")
        if portability["transfer_readiness_level"] != "L2_NAMED_ROBOT_LOW_SPEED_REVIEW_READY":
            raise AssertionError(f"ready portability should only reach named low-speed review L2: {portability}")
        if portability["ready_for_hardware_execution"] is not False:
            raise AssertionError(f"portability gate must never claim direct hardware execution readiness: {portability}")
        if portability["ready_for_named_robot_low_speed_review"] is not True:
            raise AssertionError(f"portability gate should only allow named low-speed review readiness: {portability}")
        if portability["target_robot_id"] != "demo_arm_ready_fixture":
            raise AssertionError(f"portability gate should name the ready adapter robot: {portability}")
        if portability["side_effects"]["writes_boundary_report"] is not True:
            raise AssertionError(f"portability gate should disclose boundary report write: {portability}")
        for key in ("writes_adapter_manifest", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if portability["side_effects"][key] is not False:
                raise AssertionError(f"ready portability boundary side effect must be false for {key}: {portability}")
        portability_review_json = tmp_dir / "portability_review" / "review_packet.json"
        portability_review_md = tmp_dir / "portability_review" / "README.md"
        result = run(
            [
                "python3",
                "scripts/prepare_v0_portability_review.py",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--adapter",
                str(ready_adapter_path),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(portability_review_json),
                "--output-md",
                str(portability_review_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 portability review accepts ready V0 skill plus named adapter")
        assert_contains(
            result,
            "READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW",
            "ready V0 portability review detail",
        )
        assert_contains(result, "universal_drop_in_ready=false", "ready portability review keeps universal non-claim")
        portability_review_packet = json.loads(portability_review_json.read_text(encoding="utf-8"))
        if portability_review_packet["direct_drop_in_answer"] != "NO_DIRECT_DROP_IN":
            raise AssertionError(f"portability review must reject drop-in claims: {portability_review_packet}")
        if portability_review_packet["universal_drop_in_ready"] is not False:
            raise AssertionError(f"portability review must never claim arbitrary-arm readiness: {portability_review_packet}")
        if portability_review_packet["direct_use_ready"] is not False:
            raise AssertionError(f"portability review must never claim direct external-robot use: {portability_review_packet}")
        if portability_review_packet["transfer_readiness_level"] != "L2_NAMED_ROBOT_LOW_SPEED_REVIEW_READY":
            raise AssertionError(f"portability review should surface named low-speed review L2 only: {portability_review_packet}")
        if portability_review_packet["ready_for_hardware_execution"] is not False:
            raise AssertionError(f"portability review must never claim direct hardware execution readiness: {portability_review_packet}")
        if portability_review_packet["ready_for_named_robot_low_speed_review"] is not True:
            raise AssertionError(f"portability review should only allow named low-speed review readiness: {portability_review_packet}")
        if portability_review_packet["named_robot_ready"] is not True:
            raise AssertionError(f"portability review should allow named ready adapter review: {portability_review_packet}")
        if portability_review_packet["adapter_workplan"]["status"] != "READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW":
            raise AssertionError(f"ready portability workplan should be ready only for named low-speed review: {portability_review_packet}")
        if portability_review_packet["adapter_workplan"]["direct_drop_in_answer"] != "NO_DIRECT_DROP_IN":
            raise AssertionError(f"ready portability workplan must still reject direct drop-in: {portability_review_packet}")
        if portability_review_packet["adapter_workplan"]["direct_use_ready"] is not False:
            raise AssertionError(f"ready portability workplan must still reject direct use: {portability_review_packet}")
        if portability_review_packet["adapter_workplan"]["transfer_readiness_level"] != "L2_NAMED_ROBOT_LOW_SPEED_REVIEW_READY":
            raise AssertionError(f"ready portability workplan should surface L2 named review only: {portability_review_packet}")
        if portability_review_packet["adapter_workplan"]["ready_for_hardware_execution"] is not False:
            raise AssertionError(f"ready portability workplan must still reject direct hardware execution: {portability_review_packet}")
        if portability_review_packet["side_effects"]["writes_review_artifacts"] is not True:
            raise AssertionError(f"portability review should disclose review artifact writes: {portability_review_packet}")
        for key in ("writes_target_adapter_manifest", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if portability_review_packet["side_effects"][key] is not False:
                raise AssertionError(f"ready portability review side effect must be false for {key}: {portability_review_packet}")
        if "V0 Cross-Robot Portability Review" not in portability_review_md.read_text(encoding="utf-8"):
            raise AssertionError("portability review README should include a clear title")
        if "Adapter Workplan" not in portability_review_md.read_text(encoding="utf-8"):
            raise AssertionError("portability review README should include adapter workplan")
        if "transfer_readiness_level" not in portability_review_md.read_text(encoding="utf-8"):
            raise AssertionError("portability review README should include transfer readiness level")
        execution_plan_json = tmp_dir / "v0_skill_execution" / "plan.json"
        result = run(
            [
                "python3",
                "scripts/plan_v0_skill_execution.py",
                "configs/v0_skill_request.example.json",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(execution_plan_json),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 skill execution planner accepts promotable manifest plus dataset")
        assert_contains(result, "[v0-skill-execution-plan] status=READY", "ready V0 skill execution detail")
        execution_plan = json.loads(execution_plan_json.read_text(encoding="utf-8"))
        if execution_plan["ready_for_execution"] is not True:
            raise AssertionError(f"execution planner should be ready after V0 readiness gate: {execution_plan}")
        if execution_plan["execution_surface"]["allowed_command_boundary"] != "task_parameters_to_skill_controller":
            raise AssertionError(f"execution planner should preserve skill boundary: {execution_plan['execution_surface']}")
        if "raw_joint_targets" not in execution_plan["execution_surface"]["forbidden_command_boundary"]:
            raise AssertionError("execution planner must preserve raw joint command ban")
        if execution_plan["side_effects"]["writes_execution_plan"] is not True:
            raise AssertionError(f"execution planner should disclose local plan write: {execution_plan}")
        for key in ("creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if execution_plan["side_effects"][key] is not False:
                raise AssertionError(f"ready execution planner side effect must be false for {key}: {execution_plan}")
        language_dry_run_json = tmp_dir / "v0_language_skill_dry_run" / "report.json"
        language_dry_run_md = tmp_dir / "v0_language_skill_dry_run" / "README.md"
        language_request_json = tmp_dir / "v0_language_skill_dry_run" / "request.json"
        result = run(
            [
                "python3",
                str(language_dry_run_path),
                "insert the peg into the right socket",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--skip-phase2-contact-gate",
                "--request-json",
                str(language_request_json),
                "--output-json",
                str(language_dry_run_json),
                "--output-md",
                str(language_dry_run_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 language skill dry-run reaches ready execution review on ready fixture")
        assert_contains(
            result,
            "READY_FOR_SKILL_EXECUTION_REVIEW",
            "V0 language skill dry-run ready detail",
        )
        language_report = json.loads(language_dry_run_json.read_text(encoding="utf-8"))
        if language_report["ready_for_execution"] is not True:
            raise AssertionError(f"language dry-run should be ready with ready fixture: {language_report}")
        if language_report["request_preview"]["task_parameters"]["socket_id"] != "right_socket":
            raise AssertionError(f"language dry-run should normalize right socket: {language_report}")
        if language_report["execution_surface"]["allowed_command_boundary"] != "task_parameters_to_skill_controller":
            raise AssertionError(f"language dry-run should preserve skill boundary: {language_report}")
        if "raw_joint_targets" not in language_report["execution_surface"]["forbidden_command_boundary"]:
            raise AssertionError("language dry-run must preserve raw-joint command ban")
        if language_report["side_effects"]["writes_request_artifact"] is not True:
            raise AssertionError(f"language dry-run should disclose request artifact write: {language_report}")
        if language_report["side_effects"]["writes_dry_run_report"] is not True:
            raise AssertionError(f"language dry-run should disclose report writes: {language_report}")
        for key in ("creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_llm_or_vlm", "calls_ros_or_robot"):
            if language_report["side_effects"][key] is not False:
                raise AssertionError(f"ready language dry-run side effect must be false for {key}: {language_report}")
        if not language_request_json.is_file():
            raise AssertionError("language dry-run should write the planned request artifact when ready")
        if "V0 Language Skill Dry Run" not in language_dry_run_md.read_text(encoding="utf-8"):
            raise AssertionError("language dry-run README should include a clear title")
        policy_review_json = tmp_dir / "policy_api_review" / "review_packet.json"
        policy_review_md = tmp_dir / "policy_api_review" / "README.md"
        result = run(
            [
                "python3",
                "scripts/prepare_v0_policy_api_review.py",
                "configs/v0_skill_request.example.json",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(policy_review_json),
                "--output-md",
                str(policy_review_md),
            ]
        )
        assert_status(result, 0, "V0 policy/API review prep accepts promotable manifest plus dataset")
        assert_contains(result, "READY_FOR_POLICY_API_REVIEW", "V0 policy/API review ready detail")
        policy_review = json.loads(policy_review_json.read_text(encoding="utf-8"))
        if policy_review["status"] != "READY_FOR_POLICY_API_REVIEW":
            raise AssertionError(f"policy/API review packet should be ready: {policy_review}")
        if policy_review["dataset"]["case_count"] != len(dataset["cases"]):
            raise AssertionError(f"policy/API review should summarize dataset cases: {policy_review['dataset']}")
        review_negative_evidence = policy_review["dataset"].get("negative_control_evidence")
        if not isinstance(review_negative_evidence, dict):
            raise AssertionError(f"policy/API review should preserve negative-control evidence: {policy_review['dataset']}")
        if review_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"policy/API review should name the negative-control case: {review_negative_evidence}")
        if review_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"policy/API review should preserve fail-closed classification: {review_negative_evidence}")
        if review_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"policy/API review should preserve training exclusion: {review_negative_evidence}")
        if "direct_force_commands" not in policy_review["proposed_api_boundary"]["forbidden_outputs"]:
            raise AssertionError("policy/API review must preserve direct force-command ban")
        if "not sim-to-real" not in policy_review["not_claims"]:
            raise AssertionError("policy/API review must preserve sim-to-real non-claim")
        if policy_review["side_effects"]["writes_review_artifacts"] is not True:
            raise AssertionError(f"policy/API review should disclose local review artifact writes: {policy_review}")
        for key in (
            "writes_dataset_artifacts",
            "writes_policy_artifacts",
            "writes_checkpoint",
            "trains_policy",
            "creates_paid_instance",
            "runs_remote_code",
            "starts_isaac",
            "calls_ros_or_robot",
        ):
            if policy_review["side_effects"][key] is not False:
                raise AssertionError(f"policy/API review side effect must be false for {key}: {policy_review}")
        if "V0 Policy/API Review Packet" not in policy_review_md.read_text(encoding="utf-8"):
            raise AssertionError("policy/API review README should include a clear title")
        if "Negative Control Evidence" not in policy_review_md.read_text(encoding="utf-8"):
            raise AssertionError("policy/API review README should surface negative-control evidence")
        dataset_audit_json = tmp_dir / "policy_dataset_audit" / "audit.json"
        dataset_audit_md = tmp_dir / "policy_dataset_audit" / "README.md"
        result = run(
            [
                "python3",
                "scripts/audit_v0_policy_dataset.py",
                "--review-packet",
                str(policy_review_json),
                "--dataset",
                str(dataset_json),
                "--output-json",
                str(dataset_audit_json),
                "--output-md",
                str(dataset_audit_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy dataset audit accepts review packet plus dataset")
        assert_contains(result, "[v0-policy-dataset-audit] status=PASS", "V0 policy dataset audit PASS detail")
        dataset_audit = json.loads(dataset_audit_json.read_text(encoding="utf-8"))
        if dataset_audit["ready_for_training"] is not False:
            raise AssertionError(f"dataset audit should not mark training ready: {dataset_audit}")
        for group in ("seed_or_reset", "socket_x", "socket_y", "socket_z"):
            if group not in dataset_audit["coverage_groups"]:
                raise AssertionError(f"dataset audit missing coverage group {group}: {dataset_audit}")
        if "socket_x_pos_25mm_negative_control" in dataset_audit["dataset_case_ids"]:
            raise AssertionError("dataset audit must confirm negative-control exclusion")
        broken_review = json.loads(policy_review_json.read_text(encoding="utf-8"))
        broken_review["dataset"].pop("negative_control_evidence", None)
        broken_review_json = tmp_dir / "policy_dataset_audit" / "broken_review_missing_negative_evidence.json"
        broken_review_json.write_text(json.dumps(broken_review), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/audit_v0_policy_dataset.py",
                "--review-packet",
                str(broken_review_json),
                "--dataset",
                str(dataset_json),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy dataset audit rejects review packet missing negative-control evidence")
        assert_contains(
            result,
            "policy/API review must preserve negative_control_evidence",
            "missing review negative evidence failure detail",
        )
        broken_dataset = json.loads(dataset_json.read_text(encoding="utf-8"))
        broken_dataset.pop("negative_control_evidence", None)
        broken_dataset_json = tmp_dir / "policy_dataset_audit" / "broken_missing_negative_evidence.json"
        broken_dataset_json.write_text(json.dumps(broken_dataset), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/audit_v0_policy_dataset.py",
                "--review-packet",
                str(policy_review_json),
                "--dataset",
                str(broken_dataset_json),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy dataset audit rejects missing negative-control evidence")
        assert_contains(result, "dataset must record negative_control_evidence", "missing negative evidence failure detail")
        if "V0 Policy Dataset Audit" not in dataset_audit_md.read_text(encoding="utf-8"):
            raise AssertionError("dataset audit README should include a clear title")
        result = run(
            [
                "python3",
                "scripts/plan_v0_policy_experiment.py",
                "--review-packet",
                str(broken_review_json),
                "--dataset",
                str(dataset_json),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy experiment plan rejects review packet missing negative-control evidence")
        assert_contains(
            result,
            "policy/API review must preserve negative_control_evidence",
            "experiment plan missing negative review evidence detail",
        )
        policy_experiment_json = tmp_dir / "policy_experiment" / "plan.json"
        policy_experiment_md = tmp_dir / "policy_experiment" / "README.md"
        result = run(
            [
                "python3",
                "scripts/plan_v0_policy_experiment.py",
                "--review-packet",
                str(policy_review_json),
                "--dataset",
                str(dataset_json),
                "--output-json",
                str(policy_experiment_json),
                "--output-md",
                str(policy_experiment_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy experiment planner accepts review packet plus dataset")
        assert_contains(
            result,
            "READY_FOR_LOCAL_POLICY_EXPERIMENT_DESIGN",
            "V0 policy experiment ready detail",
        )
        policy_experiment_plan = json.loads(policy_experiment_json.read_text(encoding="utf-8"))
        if policy_experiment_plan["ready_for_training"] is not False:
            raise AssertionError(f"policy experiment plan should still require review before training: {policy_experiment_plan}")
        if policy_experiment_plan["experiment"]["policy_family"] != "residual_policy_over_scripted_baseline":
            raise AssertionError(f"policy experiment should be residual over scripted baseline: {policy_experiment_plan}")
        experiment_negative_evidence = policy_experiment_plan.get("negative_control_evidence")
        if not isinstance(experiment_negative_evidence, dict):
            raise AssertionError(f"policy experiment should carry negative-control evidence: {policy_experiment_plan}")
        if experiment_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"policy experiment should name the negative-control case: {experiment_negative_evidence}")
        if experiment_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"policy experiment should preserve fail-closed evidence: {experiment_negative_evidence}")
        if experiment_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"policy experiment should preserve training exclusion: {experiment_negative_evidence}")
        if "raw_joint_targets" not in policy_experiment_plan["experiment"]["forbidden_outputs"]:
            raise AssertionError("policy experiment plan must preserve raw joint command ban")
        if "V0 Residual Policy Experiment Plan" not in policy_experiment_md.read_text(encoding="utf-8"):
            raise AssertionError("policy experiment plan README should include a clear title")
        if "Negative Control Evidence" not in policy_experiment_md.read_text(encoding="utf-8"):
            raise AssertionError("policy experiment plan README should surface negative-control evidence")
        policy_feature_json = tmp_dir / "policy_feature_dry_run" / "features.json"
        policy_feature_md = tmp_dir / "policy_feature_dry_run" / "README.md"
        result = run(
            [
                "python3",
                "scripts/plan_v0_policy_feature_dry_run.py",
                "--dataset",
                str(dataset_json),
                "--dataset-audit",
                str(dataset_audit_json),
                "--policy-experiment-plan",
                str(policy_experiment_json),
                "--output-json",
                str(policy_feature_json),
                "--output-md",
                str(policy_feature_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy feature dry-run accepts audited dataset and experiment plan")
        assert_contains(
            result,
            "READY_FOR_FEATURE_EXTRACTION_REVIEW",
            "V0 policy feature dry-run ready detail",
        )
        policy_feature_dry_run = json.loads(policy_feature_json.read_text(encoding="utf-8"))
        if policy_feature_dry_run["ready_for_training"] is not False:
            raise AssertionError(f"feature dry-run must not mark training ready: {policy_feature_dry_run}")
        if policy_feature_dry_run["sample_count"] != len(dataset["cases"]):
            raise AssertionError(f"feature dry-run should preview every dataset case: {policy_feature_dry_run}")
        if "socket_delta_x_m" not in policy_feature_dry_run["feature_names"]:
            raise AssertionError(f"feature dry-run missing socket_delta_x_m: {policy_feature_dry_run}")
        if policy_feature_dry_run["target_schema"]["target_status"] != "NOT_GENERATED":
            raise AssertionError(f"feature dry-run must not generate residual targets: {policy_feature_dry_run}")
        feature_negative_evidence = policy_feature_dry_run.get("negative_control_evidence")
        if not isinstance(feature_negative_evidence, dict):
            raise AssertionError(f"feature dry-run should carry negative-control evidence: {policy_feature_dry_run}")
        if feature_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"feature dry-run should name the negative-control case: {feature_negative_evidence}")
        if feature_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"feature dry-run should preserve fail-closed evidence: {feature_negative_evidence}")
        if feature_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"feature dry-run should preserve training exclusion: {feature_negative_evidence}")
        feature_payload = json.dumps(
            {
                "feature_names": policy_feature_dry_run["feature_names"],
                "sample_preview": policy_feature_dry_run["sample_preview"],
            },
            sort_keys=True,
        )
        if "raw_joint_targets" in feature_payload:
            raise AssertionError("feature dry-run must not expose raw joint targets as features or samples")
        if "raw_joint_targets" not in policy_feature_dry_run["target_schema"]["forbidden_targets"]:
            raise AssertionError("feature dry-run must keep raw joint targets forbidden")
        if "V0 Policy Feature Dry Run" not in policy_feature_md.read_text(encoding="utf-8"):
            raise AssertionError("feature dry-run README should include a clear title")
        if "Negative Control Evidence" not in policy_feature_md.read_text(encoding="utf-8"):
            raise AssertionError("feature dry-run README should surface negative-control evidence")
        missing_negative_feature_json = tmp_dir / "policy_feature_dry_run" / "missing_negative_evidence.json"
        missing_negative_feature = json.loads(policy_feature_json.read_text(encoding="utf-8"))
        missing_negative_feature.pop("negative_control_evidence", None)
        missing_negative_feature_json.write_text(json.dumps(missing_negative_feature), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/audit_v0_policy_label_sources.py",
                "--dataset",
                str(dataset_json),
                "--policy-feature-dry-run",
                str(missing_negative_feature_json),
                "--policy-experiment-plan",
                str(policy_experiment_json),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 label-source audit rejects feature dry-run missing negative-control evidence")
        assert_contains(
            result,
            "policy feature dry-run must preserve negative_control_evidence",
            "missing feature negative evidence failure detail",
        )
        policy_label_source_json = tmp_dir / "policy_label_source_audit" / "audit.json"
        policy_label_source_md = tmp_dir / "policy_label_source_audit" / "README.md"
        result = run(
            [
                "python3",
                "scripts/audit_v0_policy_label_sources.py",
                "--dataset",
                str(dataset_json),
                "--policy-feature-dry-run",
                str(policy_feature_json),
                "--policy-experiment-plan",
                str(policy_experiment_json),
                "--output-json",
                str(policy_label_source_json),
                "--output-md",
                str(policy_label_source_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy label-source audit accepts ready feature dry-run and traces")
        assert_contains(
            result,
            "READY_FOR_LABEL_SOURCE_REVIEW",
            "V0 policy label-source ready detail",
        )
        policy_label_source_audit = json.loads(policy_label_source_json.read_text(encoding="utf-8"))
        if policy_label_source_audit["ready_for_training"] is not False:
            raise AssertionError(f"label-source audit must not mark training ready: {policy_label_source_audit}")
        if policy_label_source_audit["ready_for_label_generation"] is not False:
            raise AssertionError(f"label-source audit must not mark label generation ready: {policy_label_source_audit}")
        if policy_label_source_audit["target_generation_status"] != "DESIGN_ONLY":
            raise AssertionError(f"label-source audit must remain design-only: {policy_label_source_audit}")
        if "residual_socket_offset_x_m" not in policy_label_source_audit["target_channel_names"]:
            raise AssertionError(f"label-source audit missing socket offset target: {policy_label_source_audit}")
        label_source_negative_evidence = policy_label_source_audit.get("negative_control_evidence")
        if not isinstance(label_source_negative_evidence, dict):
            raise AssertionError(f"label-source audit should carry negative-control evidence: {policy_label_source_audit}")
        if label_source_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"label-source audit should name negative-control case: {label_source_negative_evidence}")
        if label_source_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"label-source audit should preserve fail-closed evidence: {label_source_negative_evidence}")
        if label_source_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"label-source audit should preserve training exclusion: {label_source_negative_evidence}")
        target_payload = json.dumps(policy_label_source_audit["target_channel_schema"], sort_keys=True)
        if "raw_joint" in target_payload or "joint_pos" in target_payload:
            raise AssertionError("label-source target schema must not expose raw joint labels")
        if not any(
            "raw_action" in case_report["forbidden_trace_fields_present_but_excluded"]
            for case_report in policy_label_source_audit["case_reports"]
        ):
            raise AssertionError("label-source audit should record raw_action as present but excluded")
        if "V0 Policy Label Source Audit" not in policy_label_source_md.read_text(encoding="utf-8"):
            raise AssertionError("label-source audit README should include a clear title")
        if "Negative Control Evidence" not in policy_label_source_md.read_text(encoding="utf-8"):
            raise AssertionError("label-source audit README should surface negative-control evidence")
        policy_label_json = tmp_dir / "policy_label_dry_run" / "labels.json"
        policy_label_md = tmp_dir / "policy_label_dry_run" / "README.md"
        result = run(
            [
                "python3",
                "scripts/plan_v0_policy_label_dry_run.py",
                "--dataset",
                str(dataset_json),
                "--policy-feature-dry-run",
                str(policy_feature_json),
                "--policy-label-source-audit",
                str(policy_label_source_json),
                "--output-json",
                str(policy_label_json),
                "--output-md",
                str(policy_label_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy label dry-run accepts ready label-source audit and traces")
        assert_contains(
            result,
            "READY_FOR_LABEL_DRY_RUN_REVIEW",
            "V0 policy label dry-run ready detail",
        )
        policy_label_dry_run = json.loads(policy_label_json.read_text(encoding="utf-8"))
        if policy_label_dry_run["ready_for_training"] is not False:
            raise AssertionError(f"label dry-run must not mark training ready: {policy_label_dry_run}")
        if policy_label_dry_run["label_generation_status"] != "DRY_RUN_PREVIEW_ONLY":
            raise AssertionError(f"label dry-run must remain preview-only: {policy_label_dry_run}")
        if policy_label_dry_run["candidate_label_window_count"] <= 0:
            raise AssertionError(f"label dry-run should find candidate label windows: {policy_label_dry_run}")
        if "residual_socket_offset_x_m" not in policy_label_dry_run["label_names"]:
            raise AssertionError(f"label dry-run missing socket offset label: {policy_label_dry_run}")
        label_negative_evidence = policy_label_dry_run.get("negative_control_evidence")
        if not isinstance(label_negative_evidence, dict):
            raise AssertionError(f"label dry-run should carry negative-control evidence: {policy_label_dry_run}")
        if label_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"label dry-run should name negative-control case: {label_negative_evidence}")
        if label_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"label dry-run should preserve fail-closed evidence: {label_negative_evidence}")
        if label_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"label dry-run should preserve training exclusion: {label_negative_evidence}")
        label_schema_payload = json.dumps(policy_label_dry_run["label_schema"], sort_keys=True)
        if "raw_joint" in label_schema_payload or "joint_pos" in label_schema_payload:
            raise AssertionError("label dry-run schema must not expose raw joint labels")
        label_values_payload = json.dumps(
            [sample["labels"] for sample in policy_label_dry_run["sample_preview"]],
            sort_keys=True,
        )
        if "raw_action" in label_values_payload or "joint_pos" in label_values_payload:
            raise AssertionError("label dry-run samples must not contain raw action or joint labels")
        if not any(
            "raw_action" in case_report["forbidden_trace_fields_present_but_excluded"]
            for case_report in policy_label_dry_run["case_reports"]
        ):
            raise AssertionError("label dry-run should record raw_action as present but excluded")
        if "V0 Policy Label Dry Run" not in policy_label_md.read_text(encoding="utf-8"):
            raise AssertionError("label dry-run README should include a clear title")
        if "Negative Control Evidence" not in policy_label_md.read_text(encoding="utf-8"):
            raise AssertionError("label dry-run README should surface negative-control evidence")
        missing_negative_label_source = tmp_dir / "policy_label_source_audit" / "missing_negative.json"
        broken_label_source = json.loads(policy_label_source_json.read_text(encoding="utf-8"))
        broken_label_source.pop("negative_control_evidence", None)
        missing_negative_label_source.write_text(json.dumps(broken_label_source, indent=2, sort_keys=True), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/plan_v0_policy_label_dry_run.py",
                "--dataset",
                str(dataset_json),
                "--policy-feature-dry-run",
                str(policy_feature_json),
                "--policy-label-source-audit",
                str(missing_negative_label_source),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy label dry-run rejects missing negative-control evidence")
        assert_contains(
            result,
            "policy label-source audit must preserve negative_control_evidence",
            "missing label-source negative evidence failure detail",
        )
        policy_label_dataset_dir = tmp_dir / "policy_label_dataset"
        policy_label_dataset_jsonl = policy_label_dataset_dir / "labels.jsonl"
        policy_label_dataset_manifest = policy_label_dataset_dir / "manifest.json"
        policy_label_dataset_md = policy_label_dataset_dir / "README.md"
        result = run(
            [
                "python3",
                "scripts/extract_v0_policy_label_dataset.py",
                "--dataset",
                str(dataset_json),
                "--policy-label-dry-run",
                str(policy_label_json),
                "--max-samples-per-case",
                "3",
                "--output-jsonl",
                str(policy_label_dataset_jsonl),
                "--output-manifest",
                str(policy_label_dataset_manifest),
                "--output-md",
                str(policy_label_dataset_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy label dataset extractor accepts ready label dry-run and traces")
        assert_contains(
            result,
            "READY_FOR_LOCAL_POLICY_DATASET_REVIEW",
            "V0 policy label dataset ready detail",
        )
        policy_label_dataset = json.loads(policy_label_dataset_manifest.read_text(encoding="utf-8"))
        if policy_label_dataset["ready_for_training"] is not False:
            raise AssertionError(f"label dataset must not mark training ready: {policy_label_dataset}")
        if policy_label_dataset["sample_count"] <= 0:
            raise AssertionError(f"label dataset should contain samples: {policy_label_dataset}")
        dataset_label_negative_evidence = policy_label_dataset.get("negative_control_evidence")
        if not isinstance(dataset_label_negative_evidence, dict):
            raise AssertionError(f"label dataset should carry negative-control evidence: {policy_label_dataset}")
        if dataset_label_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"label dataset should name negative-control case: {dataset_label_negative_evidence}")
        if dataset_label_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"label dataset should preserve fail-closed evidence: {dataset_label_negative_evidence}")
        if dataset_label_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"label dataset should preserve training exclusion: {dataset_label_negative_evidence}")
        if not policy_label_dataset_jsonl.is_file():
            raise AssertionError("label dataset JSONL should be written on ready extraction")
        if "jsonl_sha256" not in policy_label_dataset:
            raise AssertionError(f"label dataset manifest should include JSONL checksum: {policy_label_dataset}")
        sample_lines = [json.loads(line) for line in policy_label_dataset_jsonl.read_text(encoding="utf-8").splitlines()]
        if len(sample_lines) != policy_label_dataset["sample_count"]:
            raise AssertionError(f"label dataset sample_count mismatch: {policy_label_dataset}")
        if "residual_socket_offset_x_m" not in sample_lines[0]["labels"]:
            raise AssertionError(f"label dataset sample missing residual offset label: {sample_lines[0]}")
        sample_payload = json.dumps(sample_lines, sort_keys=True)
        if "raw_action" in sample_payload or "joint_pos_des" in sample_payload:
            raise AssertionError("label dataset samples must not contain raw action or joint target fields")
        if "V0 Residual Policy Label Dataset" not in policy_label_dataset_md.read_text(encoding="utf-8"):
            raise AssertionError("label dataset README should include a clear title")
        if "Negative Control Evidence" not in policy_label_dataset_md.read_text(encoding="utf-8"):
            raise AssertionError("label dataset README should surface negative-control evidence")
        missing_negative_label_dry_run = tmp_dir / "policy_label_dry_run" / "missing_negative.json"
        broken_label_dry_run = json.loads(policy_label_json.read_text(encoding="utf-8"))
        broken_label_dry_run.pop("negative_control_evidence", None)
        missing_negative_label_dry_run.write_text(
            json.dumps(broken_label_dry_run, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        result = run(
            [
                "python3",
                "scripts/extract_v0_policy_label_dataset.py",
                "--dataset",
                str(dataset_json),
                "--policy-label-dry-run",
                str(missing_negative_label_dry_run),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy label dataset rejects missing negative-control evidence")
        assert_contains(
            result,
            "policy label dry-run must preserve negative_control_evidence",
            "missing label dry-run negative evidence failure detail",
        )
        policy_training_preflight_json = tmp_dir / "policy_training_preflight" / "preflight.json"
        policy_training_preflight_md = tmp_dir / "policy_training_preflight" / "README.md"
        result = run(
            [
                "python3",
                "scripts/check_v0_policy_training_preflight.py",
                "--label-dataset-manifest",
                str(policy_label_dataset_manifest),
                "--output-json",
                str(policy_training_preflight_json),
                "--output-md",
                str(policy_training_preflight_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy training preflight accepts checked label dataset")
        assert_contains(
            result,
            "READY_FOR_LOCAL_RESIDUAL_POLICY_TRAINING",
            "V0 policy training preflight ready detail",
        )
        policy_training_preflight = json.loads(policy_training_preflight_json.read_text(encoding="utf-8"))
        if policy_training_preflight["ready_for_training"] is not True:
            raise AssertionError(f"training preflight should mark local training ready: {policy_training_preflight}")
        if policy_training_preflight["training_script_status"] != "IMPLEMENTED":
            raise AssertionError(f"training preflight should see implemented script: {policy_training_preflight}")
        if policy_training_preflight["sample_count"] != policy_label_dataset["sample_count"]:
            raise AssertionError(f"training preflight sample_count mismatch: {policy_training_preflight}")
        preflight_negative_evidence = policy_training_preflight.get("negative_control_evidence")
        if not isinstance(preflight_negative_evidence, dict):
            raise AssertionError(f"training preflight should carry negative-control evidence: {policy_training_preflight}")
        if preflight_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"training preflight should name negative-control case: {preflight_negative_evidence}")
        if preflight_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"training preflight should preserve fail-closed evidence: {preflight_negative_evidence}")
        if preflight_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"training preflight should preserve training exclusion: {preflight_negative_evidence}")
        expected_jsonl_sha = hashlib.sha256(policy_label_dataset_jsonl.read_bytes()).hexdigest()
        if policy_training_preflight["jsonl_sha256"] != expected_jsonl_sha:
            raise AssertionError(f"training preflight checksum mismatch: {policy_training_preflight}")
        if "raw_action" not in policy_training_preflight["forbidden_sample_tokens"]:
            raise AssertionError("training preflight should preserve raw_action forbidden-token check")
        if "V0 Policy Training Preflight" not in policy_training_preflight_md.read_text(encoding="utf-8"):
            raise AssertionError("training preflight README should include a clear title")
        if "Negative Control Evidence" not in policy_training_preflight_md.read_text(encoding="utf-8"):
            raise AssertionError("training preflight README should surface negative-control evidence")
        missing_negative_label_dataset = policy_label_dataset_dir / "missing_negative_manifest.json"
        broken_label_dataset = json.loads(policy_label_dataset_manifest.read_text(encoding="utf-8"))
        broken_label_dataset.pop("negative_control_evidence", None)
        missing_negative_label_dataset.write_text(
            json.dumps(broken_label_dataset, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        result = run(
            [
                "python3",
                "scripts/check_v0_policy_training_preflight.py",
                "--label-dataset-manifest",
                str(missing_negative_label_dataset),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy training preflight rejects missing negative-control evidence")
        assert_contains(
            result,
            "label dataset manifest must preserve negative_control_evidence",
            "missing label dataset negative evidence failure detail",
        )
        training_dry_run_plan = tmp_dir / "policy_training" / "dry_run_plan.json"
        training_checkpoint = tmp_dir / "policy_training" / "model.pt"
        result = run(
            [
                "python3",
                "scripts/train_v0_residual_policy.py",
                "--label-dataset-manifest",
                str(policy_label_dataset_manifest),
                "--output-checkpoint",
                str(training_checkpoint),
                "--output-plan",
                str(training_dry_run_plan),
                "--dry-run",
            ]
        )
        assert_status(result, 0, "V0 residual policy trainer dry-run accepts checked label dataset")
        assert_contains(
            result,
            "READY_FOR_LOCAL_TRAINING_DRY_RUN",
            "V0 residual policy dry-run ready detail",
        )
        if training_checkpoint.exists():
            raise AssertionError("V0 residual policy dry-run must not write a checkpoint")
        training_plan = json.loads(training_dry_run_plan.read_text(encoding="utf-8"))
        if training_plan["sample_count"] != policy_label_dataset["sample_count"]:
            raise AssertionError(f"training dry-run should preserve sample count: {training_plan}")
        if "residual_socket_offset_x_m" not in training_plan["label_names"]:
            raise AssertionError(f"training dry-run should preserve residual labels: {training_plan}")
        training_plan_negative_evidence = training_plan.get("negative_control_evidence")
        if not isinstance(training_plan_negative_evidence, dict):
            raise AssertionError(f"training dry-run should carry negative-control evidence: {training_plan}")
        if training_plan_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"training dry-run should name negative-control case: {training_plan_negative_evidence}")
        if training_plan_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"training dry-run should preserve fail-closed evidence: {training_plan_negative_evidence}")
        if training_plan_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"training dry-run should preserve training exclusion: {training_plan_negative_evidence}")
        if "not trained policy" not in training_plan["not_claims"]:
            raise AssertionError(f"training dry-run must preserve not-trained non-claim: {training_plan}")
        if training_plan["side_effects"]["writes_checkpoint"] is not False:
            raise AssertionError(f"training dry-run must not write checkpoints: {training_plan}")
        if training_plan["side_effects"]["writes_metadata"] is not False:
            raise AssertionError(f"training dry-run must not write metadata: {training_plan}")
        pipeline_dir = tmp_dir / "offline_policy_readiness_pipeline"
        pipeline_checkpoint = pipeline_dir / "policy_training" / "model.pt"
        pipeline_summary_json = pipeline_dir / "summary.json"
        result = run(
            [
                "python3",
                str(policy_readiness_pipeline_path),
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--skip-phase2-contact-gate",
                "--review-json",
                str(pipeline_dir / "policy_api_review" / "review_packet.json"),
                "--review-md",
                str(pipeline_dir / "policy_api_review" / "README.md"),
                "--dataset-audit-json",
                str(pipeline_dir / "policy_dataset_audit" / "audit.json"),
                "--dataset-audit-md",
                str(pipeline_dir / "policy_dataset_audit" / "README.md"),
                "--experiment-json",
                str(pipeline_dir / "policy_experiment" / "plan.json"),
                "--experiment-md",
                str(pipeline_dir / "policy_experiment" / "README.md"),
                "--feature-json",
                str(pipeline_dir / "policy_feature_dry_run" / "features.json"),
                "--feature-md",
                str(pipeline_dir / "policy_feature_dry_run" / "README.md"),
                "--label-source-json",
                str(pipeline_dir / "policy_label_source_audit" / "audit.json"),
                "--label-source-md",
                str(pipeline_dir / "policy_label_source_audit" / "README.md"),
                "--label-dry-run-json",
                str(pipeline_dir / "policy_label_dry_run" / "labels.json"),
                "--label-dry-run-md",
                str(pipeline_dir / "policy_label_dry_run" / "README.md"),
                "--label-jsonl",
                str(pipeline_dir / "policy_label_dataset" / "labels.jsonl"),
                "--label-manifest",
                str(pipeline_dir / "policy_label_dataset" / "manifest.json"),
                "--label-md",
                str(pipeline_dir / "policy_label_dataset" / "README.md"),
                "--training-preflight-json",
                str(pipeline_dir / "policy_training_preflight" / "preflight.json"),
                "--training-preflight-md",
                str(pipeline_dir / "policy_training_preflight" / "README.md"),
                "--training-plan-json",
                str(pipeline_dir / "policy_training" / "dry_run_plan.json"),
                "--output-checkpoint",
                str(pipeline_checkpoint),
                "--summary-json",
                str(pipeline_summary_json),
                "--summary-md",
                str(pipeline_dir / "summary.md"),
                "--max-samples-per-case",
                "3",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 offline policy-readiness pipeline reaches dry-run training on ready fixture")
        assert_contains(
            result,
            "[v0-offline-policy-readiness] status=READY_FOR_LOCAL_TRAINING_DRY_RUN",
            "V0 offline policy-readiness ready detail",
        )
        if pipeline_checkpoint.exists():
            raise AssertionError("V0 offline policy-readiness pipeline must not write a checkpoint in dry-run mode")
        pipeline_summary = json.loads(pipeline_summary_json.read_text(encoding="utf-8"))
        if pipeline_summary["status"] != "READY_FOR_LOCAL_TRAINING_DRY_RUN":
            raise AssertionError(f"offline policy-readiness summary should be ready: {pipeline_summary}")
        if pipeline_summary["ready_for_local_training_dry_run"] is not True:
            raise AssertionError(f"offline policy-readiness should mark dry-run training ready: {pipeline_summary}")
        if "not a paid run" not in pipeline_summary["not_claims"]:
            raise AssertionError(f"offline policy-readiness must preserve paid-run non-claim: {pipeline_summary}")
        step_statuses = {step["step_id"]: step["status"] for step in pipeline_summary["steps"]}
        if step_statuses.get("policy_training_dry_run") != "PASS":
            raise AssertionError(f"offline policy-readiness should run training dry-run: {step_statuses}")
        fake_checkpoint = tmp_dir / "policy_training" / "fake_model.pt"
        fake_checkpoint.write_bytes(b"fake checkpoint bytes for dry-run integrity gate\n")
        fake_metadata = tmp_dir / "policy_training" / "metadata.json"
        fake_metadata_payload = {
            "status": "TRAINED_NEEDS_EVALUATION",
            "checkpoint": str(fake_checkpoint),
            "checkpoint_sha256": hashlib.sha256(fake_checkpoint.read_bytes()).hexdigest(),
            "label_dataset_manifest": str(policy_label_dataset_manifest),
            "label_dataset_manifest_sha256": hashlib.sha256(policy_label_dataset_manifest.read_bytes()).hexdigest(),
            "jsonl": str(policy_label_dataset_jsonl),
            "jsonl_sha256": hashlib.sha256(policy_label_dataset_jsonl.read_bytes()).hexdigest(),
            "negative_control_evidence": policy_label_dataset["negative_control_evidence"],
            "sample_count": policy_label_dataset["sample_count"],
            "feature_schema": policy_label_dataset["feature_schema"],
            "label_names": policy_label_dataset["label_names"],
            "not_claims": [
                "not evaluated policy",
                "not sim-to-real",
                "not cross-robot-ready",
                "not direct drop-in precision on another robot arm",
                "not a Brev or Isaac launcher",
            ],
        }
        fake_metadata.write_text(json.dumps(fake_metadata_payload), encoding="utf-8")
        eval_dry_run_json = tmp_dir / "policy_eval" / "summary.json"
        result = run(
            [
                "python3",
                "scripts/evaluate_v0_residual_policy.py",
                "--metadata",
                str(fake_metadata),
                "--output-json",
                str(eval_dry_run_json),
                "--dry-run",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 residual policy evaluator dry-run accepts consistent checkpoint metadata")
        assert_contains(
            result,
            "READY_FOR_LOCAL_SUPERVISED_EVAL_DRY_RUN",
            "V0 residual policy eval dry-run ready detail",
        )
        eval_dry_run = json.loads(eval_dry_run_json.read_text(encoding="utf-8"))
        if eval_dry_run["ready_for_supervised_eval"] is not True:
            raise AssertionError(f"eval dry-run should be ready for supervised eval: {eval_dry_run}")
        if eval_dry_run["sample_count"] != policy_label_dataset["sample_count"]:
            raise AssertionError(f"eval dry-run should preserve sample count: {eval_dry_run}")
        eval_negative_evidence = eval_dry_run.get("negative_control_evidence")
        if not isinstance(eval_negative_evidence, dict):
            raise AssertionError(f"eval dry-run should carry negative-control evidence: {eval_dry_run}")
        if eval_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"eval dry-run should name negative-control case: {eval_negative_evidence}")
        if eval_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"eval dry-run should preserve fail-closed evidence: {eval_negative_evidence}")
        if eval_negative_evidence.get("excluded_from_training_cases") is not True:
            raise AssertionError(f"eval dry-run should preserve training exclusion: {eval_negative_evidence}")
        if "not Isaac closed-loop evaluation" not in eval_dry_run["not_claims"]:
            raise AssertionError(f"eval dry-run must preserve Isaac non-claim: {eval_dry_run}")
        if eval_dry_run["side_effects"]["writes_eval_summary"] is not True:
            raise AssertionError(f"eval dry-run should disclose summary writes: {eval_dry_run}")
        for key in (
            "writes_checkpoint",
            "writes_training_metadata",
            "imports_torch",
            "runs_supervised_eval",
            "creates_paid_instance",
            "starts_isaac",
            "calls_ros_or_robot",
        ):
            if eval_dry_run["side_effects"][key] is not False:
                raise AssertionError(f"eval dry-run side effect must be false for {key}: {eval_dry_run}")
        missing_negative_metadata = tmp_dir / "policy_training" / "missing_negative_metadata.json"
        broken_metadata_payload = dict(fake_metadata_payload)
        broken_metadata_payload.pop("negative_control_evidence", None)
        missing_negative_metadata.write_text(json.dumps(broken_metadata_payload, indent=2, sort_keys=True), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/evaluate_v0_residual_policy.py",
                "--metadata",
                str(missing_negative_metadata),
                "--dry-run",
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 residual policy evaluator rejects metadata missing negative-control evidence")
        assert_contains(
            result,
            "training metadata must preserve negative_control_evidence",
            "missing training metadata negative evidence failure detail",
        )
        supervised_eval_json = tmp_dir / "policy_eval" / "supervised_summary.json"
        fake_checkpoint_sha = hashlib.sha256(fake_checkpoint.read_bytes()).hexdigest()
        supervised_eval_payload = {
            "eval_name": "v0_residual_policy_supervised_eval",
            "status": "SUPERVISED_EVAL_NEEDS_ISAAC_POLICY_GATE",
            "metadata": str(fake_metadata),
            "checkpoint": str(fake_checkpoint),
            "label_dataset_manifest": str(policy_label_dataset_manifest),
            "jsonl": str(policy_label_dataset_jsonl),
            "sample_count": policy_label_dataset["sample_count"],
            "negative_control_evidence": policy_label_dataset["negative_control_evidence"],
            "mse": 0.0001,
            "max_abs_error": 0.001,
            "required_before_policy_promotion": [
                "run an Isaac closed-loop policy gate with the same checkpoint checksum",
                "compare against scripted baseline and negative controls",
            ],
            "not_claims": [
                "not Isaac closed-loop evaluation",
                "not sim-to-real",
                "not cross-robot-ready",
                "not direct drop-in precision on another robot arm",
                "not a Brev or Isaac launcher",
            ],
        }
        supervised_eval_json.write_text(json.dumps(supervised_eval_payload), encoding="utf-8")
        isaac_policy_eval_json = tmp_dir / "policy_eval" / "isaac_closed_loop_summary.json"
        isaac_policy_eval_payload = {
            "eval_name": "v0_residual_policy_isaac_closed_loop",
            "status": "PASS",
            "policy_checkpoint_sha256": fake_checkpoint_sha,
            "supervised_eval": str(supervised_eval_json),
            "strict_trials": 5,
            "strict_successes": 5,
            "strict_success_rate": 1.0,
            "negative_control": {
                "id": "socket_x_pos_25mm_negative_control",
                "result": "fail_closed",
                "strict_success": False,
            },
            "scripted_baseline_comparison": {
                "policy_not_worse_than_scripted_baseline": True,
                "regression": False,
                "scripted_baseline_strict_success_rate": 1.0,
                "policy_strict_success_rate": 1.0,
            },
            "not_claims": [
                "not sim-to-real",
                "not cross-robot-ready",
                "not external robot ready",
                "not direct drop-in precision on another robot arm",
                "not a Brev or Isaac launcher",
            ],
        }
        isaac_policy_eval_json.write_text(json.dumps(isaac_policy_eval_payload), encoding="utf-8")
        policy_promotion_json = tmp_dir / "policy_eval" / "promotion_gate.json"
        result = run(
            [
                "python3",
                "scripts/check_v0_policy_promotion_gate.py",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--supervised-eval",
                str(supervised_eval_json),
                "--isaac-eval",
                str(isaac_policy_eval_json),
                "--skip-phase2-contact-gate",
                "--output-json",
                str(policy_promotion_json),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "V0 policy promotion gate accepts supervised plus Isaac closed-loop evidence")
        assert_contains(
            result,
            "READY_FOR_POLICY_PROMOTION_REVIEW",
            "V0 policy promotion gate ready detail",
        )
        policy_promotion = json.loads(policy_promotion_json.read_text(encoding="utf-8"))
        if policy_promotion["ready_for_policy_promotion_review"] is not True:
            raise AssertionError(f"promotion gate should be ready for review: {policy_promotion}")
        if policy_promotion["ready_for_external_robot"] is not False:
            raise AssertionError(f"promotion gate must not imply external robot readiness: {policy_promotion}")
        if policy_promotion["isaac_closed_loop_eval"]["checkpoint_sha256"] != fake_checkpoint_sha:
            raise AssertionError(f"promotion gate should preserve checkpoint checksum: {policy_promotion}")
        promotion_negative_evidence = policy_promotion["supervised_eval"].get("negative_control_evidence")
        if not isinstance(promotion_negative_evidence, dict):
            raise AssertionError(f"promotion gate should carry supervised negative-control evidence: {policy_promotion}")
        if promotion_negative_evidence.get("case_id") != "socket_x_pos_25mm_negative_control":
            raise AssertionError(f"promotion gate should name negative-control case: {promotion_negative_evidence}")
        if promotion_negative_evidence.get("classification") != "fail_closed":
            raise AssertionError(f"promotion gate should preserve fail-closed evidence: {promotion_negative_evidence}")
        if policy_promotion["side_effects"]["writes_promotion_report"] is not True:
            raise AssertionError(f"promotion gate should disclose local report write: {policy_promotion}")
        for key in ("writes_checkpoint", "trains_policy", "creates_paid_instance", "runs_remote_code", "starts_isaac", "calls_ros_or_robot"):
            if policy_promotion["side_effects"][key] is not False:
                raise AssertionError(f"ready promotion gate side effect must be false for {key}: {policy_promotion}")
        missing_negative_supervised_eval = tmp_dir / "policy_eval" / "missing_negative_supervised_summary.json"
        broken_supervised_eval = dict(supervised_eval_payload)
        broken_supervised_eval.pop("negative_control_evidence", None)
        missing_negative_supervised_eval.write_text(
            json.dumps(broken_supervised_eval, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        result = run(
            [
                "python3",
                "scripts/check_v0_policy_promotion_gate.py",
                "--manifest",
                str(pass_manifest_path),
                "--dataset",
                str(dataset_json),
                "--supervised-eval",
                str(missing_negative_supervised_eval),
                "--isaac-eval",
                str(isaac_policy_eval_json),
                "--skip-phase2-contact-gate",
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "V0 policy promotion gate rejects supervised eval missing negative evidence")
        assert_contains(
            result,
            "supervised eval must preserve negative_control_evidence",
            "missing supervised negative evidence failure detail",
        )
        result = run(
            [
                "python3",
                "scripts/review_success_variation_batch.py",
                str(pass_manifest_path),
                "--skip-brev-safety",
                "--output-json",
                str(review_json),
            ]
        )
        assert_status(result, 0, "success variation review accepts promotable batch")
        assert_contains(
            result,
            "decision=ready_for_dataset_policy_preparation",
            "promotable review decision detail",
        )

        finalize_pass_dir = tmp_dir / "finalize_pass"
        result = run(
            [
                "scripts/finalize_success_variation_batch.sh",
                str(pass_manifest_path),
            ],
            env={
                "RCA_SUCCESS_VARIATION_FINALIZE_SKIP_BREV_SAFETY": "1",
                "RCA_SUCCESS_VARIATION_REVIEW_JSON": str(finalize_pass_dir / "review.json"),
                "RCA_SUCCESS_VARIATION_REVIEW_MD": str(finalize_pass_dir / "review.md"),
                "RCA_SUCCESS_VARIATION_RESULT_GATE_JSON": str(finalize_pass_dir / "result_gate.json"),
                "RCA_SUCCESS_VARIATION_DATASET_JSON": str(finalize_pass_dir / "dataset" / "manifest.json"),
                "RCA_SUCCESS_VARIATION_DATASET_MD": str(finalize_pass_dir / "dataset" / "README.md"),
            },
        )
        assert_status(result, 0, "success variation finalizer accepts promotable batch")
        assert_contains(result, "[success-variation-finalize] PASS", "promotable finalizer detail")
        finalized_dataset = json.loads((finalize_pass_dir / "dataset" / "manifest.json").read_text(encoding="utf-8"))
        if finalized_dataset["dataset_name"] != "v0_scripted_skill_success_variations":
            raise AssertionError(f"finalizer wrote wrong dataset: {finalized_dataset['dataset_name']}")
        finalized_result_gate = json.loads((finalize_pass_dir / "result_gate.json").read_text(encoding="utf-8"))
        if not finalized_result_gate["gate"]["pass"]:
            raise AssertionError(f"finalizer result gate should pass: {finalized_result_gate['gate']}")

        negative_success_manifest = json.loads(pass_manifest_path.read_text(encoding="utf-8"))
        for case in negative_success_manifest["cases"]:
            if case["case_id"] == "socket_x_pos_25mm_negative_control":
                case["trace_json"] = str(source_trace)
        negative_success_manifest_path = tmp_dir / "success_variations_negative_success.json"
        negative_success_manifest_path.write_text(json.dumps(negative_success_manifest), encoding="utf-8")
        result = run(
            ["python3", "scripts/check_success_variation_batch_results.py", str(negative_success_manifest_path)]
        )
        assert_status(result, 1, "success variation result gate rejects successful negative control")
        assert_contains(result, "must be fail_closed", "negative-control success result-gate detail")
        result = run(
            [
                "python3",
                "scripts/plan_success_variation_recovery_batch.py",
                str(negative_success_manifest_path),
                "--output-json",
                str(recovery_json),
                "--output-sh",
                str(recovery_sh),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "success variation recovery planner blocks successful negative control")
        assert_contains(result, "status=BLOCKED", "negative-control recovery blocked detail")
        assert_contains(result, "blocked_case_count=1", "negative-control recovery blocked count")

        negative_expected_manifest = json.loads(pass_manifest_path.read_text(encoding="utf-8"))
        for case in negative_expected_manifest["cases"]:
            if case["case_id"] == "socket_x_pos_25mm_negative_control":
                case["expected"] = "strict_success"
        negative_expected_manifest_path = tmp_dir / "success_variations_negative_expected_wrong.json"
        negative_expected_manifest_path.write_text(json.dumps(negative_expected_manifest), encoding="utf-8")
        result = run(
            ["python3", "scripts/check_success_variation_batch_results.py", str(negative_expected_manifest_path)]
        )
        assert_status(result, 1, "success variation result gate rejects a mislabeled negative control")
        assert_contains(result, "expected=fail_closed", "negative-control expected result-gate detail")

        batch_runner = (REPO_ROOT / "scripts" / "run_remote_success_variation_batch.sh").read_text(
            encoding="utf-8"
        )
        adapter_runner = (
            REPO_ROOT / "scripts" / "run_remote_success_variation_batch_as_trace_runner.sh"
        ).read_text(encoding="utf-8")
        paid_wrapper = (
            REPO_ROOT / "scripts" / "recreate_brev_and_run_success_variation_batch.sh"
        ).read_text(encoding="utf-8")
        config_runner = (
            REPO_ROOT / "scripts" / "run_success_variation_batch_from_config.sh"
        ).read_text(encoding="utf-8")
        config_example = (
            REPO_ROOT / "configs" / "success_variation_batch_run.env.example"
        ).read_text(encoding="utf-8")
        readiness_gate = (
            REPO_ROOT / "scripts" / "check_success_variation_batch_readiness.py"
        ).read_text(encoding="utf-8")
        plan_gate_script = (
            REPO_ROOT / "scripts" / "check_success_variation_batch_plan.py"
        ).read_text(encoding="utf-8")
        result_gate = (
            REPO_ROOT / "scripts" / "check_success_variation_batch_results.py"
        ).read_text(encoding="utf-8")
        recovery_script = (
            REPO_ROOT / "scripts" / "plan_success_variation_recovery_batch.py"
        ).read_text(encoding="utf-8")
        review_script = (
            REPO_ROOT / "scripts" / "review_success_variation_batch.py"
        ).read_text(encoding="utf-8")
        dataset_script = (
            REPO_ROOT / "scripts" / "prepare_success_variation_dataset.py"
        ).read_text(encoding="utf-8")
        finalizer_script = (
            REPO_ROOT / "scripts" / "finalize_success_variation_batch.sh"
        ).read_text(encoding="utf-8")
        audit_script = (
            REPO_ROOT / "scripts" / "audit_success_variation_assumptions.py"
        ).read_text(encoding="utf-8")
        run_packet_script = (
            REPO_ROOT / "scripts" / "write_success_variation_run_packet.py"
        ).read_text(encoding="utf-8")
        prepare_paid_script = (
            REPO_ROOT / "scripts" / "prepare_success_variation_paid_batch.py"
        ).read_text(encoding="utf-8")
        credit_review_path = REPO_ROOT / "scripts" / "prepare_brev_credit_review.py"
        credit_review_script = credit_review_path.read_text(encoding="utf-8")
        credit_diagnosis_path = REPO_ROOT / "scripts" / "diagnose_brev_credit_blocker.py"
        credit_diagnosis_script = credit_diagnosis_path.read_text(encoding="utf-8")
        paid_preflight_path = REPO_ROOT / "scripts" / "check_success_variation_paid_lifecycle_preflight.py"
        paid_preflight_script = paid_preflight_path.read_text(encoding="utf-8")
        lifecycle_script = (
            REPO_ROOT / "scripts" / "run_success_variation_paid_lifecycle.py"
        ).read_text(encoding="utf-8")
        local_env_script = (
            REPO_ROOT / "scripts" / "prepare_success_variation_local_env.py"
        ).read_text(encoding="utf-8")
        arm_env_script = (
            REPO_ROOT / "scripts" / "arm_success_variation_paid_env.py"
        ).read_text(encoding="utf-8")
        credit_template_path = REPO_ROOT / "configs" / "brev_credit_verification.template.json"
        credit_checker_path = REPO_ROOT / "scripts" / "check_brev_credit_evidence.py"
        credit_checker = credit_checker_path.read_text(encoding="utf-8")
        credit_writer_path = REPO_ROOT / "scripts" / "write_brev_credit_evidence.py"
        credit_writer = credit_writer_path.read_text(encoding="utf-8")
        api_credit_path = REPO_ROOT / "scripts" / "read_brev_credit_balance.py"
        api_credit_script = api_credit_path.read_text(encoding="utf-8")
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        for expected_snippet in (
            'TASK_NAME="${RCA_SUCCESS_VARIATION_TASK:-}"',
            'PLANNER_ARGS+=(--task "${TASK_NAME}")',
            'plan_success_variation_batch.py" "${PLANNER_ARGS[@]}"',
            "this script uses an existing remote environment; it does not create or delete Brev instances",
            'CASE_CALIBRATION_TIMEOUT_SECONDS="${RCA_SUCCESS_VARIATION_CASE_CALIBRATION_TIMEOUT_SECONDS:-300}"',
            'CASE_TRACE_TIMEOUT_SECONDS="${RCA_SUCCESS_VARIATION_CASE_TRACE_TIMEOUT_SECONDS:-300}"',
            'REUSE_CALIBRATION="${RCA_SUCCESS_VARIATION_REUSE_CALIBRATION:-1}"',
            "RCA_JOINT_RESPONSE_SOCKET_CALIBRATION_TIMEOUT_SECONDS",
            "RCA_JOINT_RESPONSE_SOCKET_TRACE_TIMEOUT_SECONDS",
            "RCA_JOINT_RESPONSE_SOCKET_REUSE_CALIBRATION",
            "plan_status=$?",
            "artifact pull failed status=",
            "classification failed status=",
            "returning generated plan status=",
            "[success-variation-batch] PASS",
        ):
            if expected_snippet not in batch_runner:
                raise AssertionError(f"success variation batch runner missing snippet: {expected_snippet}")

        for expected_snippet in (
            'MANIFEST="${RCA_SUCCESS_VARIATION_MANIFEST:-',
            'RCA_SUCCESS_VARIATION_TASK="${TASK_NAME}"',
            'RCA_SUCCESS_VARIATION_STEPS="${STEPS}"',
            "run_remote_success_variation_batch.sh",
            "manifest case seeds are authoritative",
        ):
            if expected_snippet not in adapter_runner:
                raise AssertionError(f"success variation trace-runner adapter missing snippet: {expected_snippet}")

        for expected_snippet in (
            "recreate_brev_and_run_final_contact_servo_trace.sh",
            "check_success_variation_batch_readiness.py",
            'RCA_FINAL_CONTACT_TRACE_RUNNER="${SCRIPT_DIR}/run_remote_success_variation_batch_as_trace_runner.sh"',
            "RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE=0",
            'RCA_SUCCESS_VARIATION_MANIFEST="${MANIFEST}"',
            'RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES="${RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES:-',
            "set an explicit TTL with RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES",
            "delegates create, preflight, watchdog, artifact pull",
        ):
            if expected_snippet not in paid_wrapper:
                raise AssertionError(f"success variation paid wrapper missing snippet: {expected_snippet}")
        if "brev create" in paid_wrapper or '"${BREV_BIN}" create' in paid_wrapper:
            raise AssertionError("success variation paid wrapper must not duplicate Brev create logic")

        for expected_snippet in (
            "configs/success_variation_batch_run.local.env",
            "configs/success_variation_batch_run.env.example",
            "check_success_variation_batch_readiness.py",
            "write_success_variation_run_packet.py",
            "audit_success_variation_assumptions.py",
            "recreate_brev_and_run_success_variation_batch.sh",
            'if [[ "${CONFIG_PATH}" == "--check-only" || "${CONFIG_PATH}" == "--run" ]]',
            "--check-only",
            "RCA_SUCCESS_VARIATION_RUN_PACKET_JSON",
            "writing read-only run packet",
            "writing read-only pre-batch assumption audit",
            "--phase pre-batch",
            "auto-disarming paid local env",
            "trap disarm_on_exit EXIT",
            "RCA_SUCCESS_VARIATION_AUTO_DISARM",
            "Real acknowledgement values should live in the ignored *.local.env file",
            "disallowed config key",
            "RCA_*|BREV_BIN",
        ):
            if expected_snippet not in config_runner:
                raise AssertionError(f"success variation config runner missing snippet: {expected_snippet}")
        if "brev create" in config_runner or '"${BREV_BIN}" create' in config_runner:
            raise AssertionError("success variation config runner must delegate paid creation to the guarded wrapper")

        for expected_snippet in (
            "RCA_SUCCESS_VARIATION_MANIFEST=artifacts/manifests/success_trace_variations_2026-06-25.json",
            "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES=75",
            "RCA_SUCCESS_VARIATION_SETUP_RESERVE_SECONDS=900",
            "RCA_SUCCESS_VARIATION_TIMEOUT_MARGIN_SECONDS=300",
            "RCA_SUCCESS_VARIATION_CASE_CALIBRATION_TIMEOUT_SECONDS=300",
            "RCA_SUCCESS_VARIATION_CASE_TRACE_TIMEOUT_SECONDS=300",
            "RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_KILL_SECONDS=60",
            "RCA_SUCCESS_VARIATION_REUSE_CALIBRATION=1",
            "RCA_SUCCESS_VARIATION_AUTO_DISARM=1",
            "RCA_PAID_BUDGET_EUR=6.00",
            "RCA_PAID_ESTIMATED_EUR_PER_HOUR=4.50",
            "RCA_BREV_CREDIT_EVIDENCE_JSON=configs/brev_credit_verification.local.json",
            "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES=60",
            "RCA_PAID_ARMED_AT_UTC=",
            "RCA_PAID_ARMING_MAX_AGE_MINUTES=15",
            "RCA_ALLOW_PAID_BREV_CREATE=0",
            "RCA_BREV_CREDITS_VERIFIED=0",
            "RCA_ACK_BREV_LIFECYCLE_RISK=0",
        ):
            if expected_snippet not in config_example:
                raise AssertionError(f"success variation config example missing snippet: {expected_snippet}")
        if "configs/*.local.env" not in gitignore:
            raise AssertionError(".gitignore must exclude private success-variation local env configs")
        if "configs/brev_credit_verification.local.json" not in gitignore:
            raise AssertionError(".gitignore must exclude private Brev credit verification evidence")

        for expected_snippet in (
            "brev_credit_balance_verification",
            "Brev UI organization credits page",
            "org-3BaYGdtoRGmgc77Z7NHHhPSD254",
        ):
            if expected_snippet not in credit_template_path.read_text(encoding="utf-8"):
                raise AssertionError(f"Brev credit evidence template missing snippet: {expected_snippet}")

        for expected_snippet in (
            "Brev CLI does not expose a read-only credit-balance command",
            "configs/brev_credit_verification.local.json",
            "Brev credit evidence is too old",
            "Brev credit balance",
            "source must explicitly mention Brev UI",
            "[brev-credit-evidence] PASS",
            "[brev-credit-evidence] BLOCKED",
        ):
            if expected_snippet not in credit_checker:
                raise AssertionError(f"Brev credit evidence checker missing snippet: {expected_snippet}")
        if "brev create" in credit_checker or '"${BREV_BIN}" create' in credit_checker:
            raise AssertionError("Brev credit evidence checker must not create Brev instances")
        for expected_snippet in (
            "write configs/brev_credit_verification.local.json",
            "--balance-eur",
            "balance",
            "is below budget",
            "use --force after re-checking the current Brev UI balance",
            "Generated from manually checked Brev UI balance",
            "[brev-credit-evidence-write] PASS",
        ):
            if expected_snippet not in credit_writer:
                raise AssertionError(f"Brev credit evidence writer missing snippet: {expected_snippet}")
        if "brev create" in credit_writer or '"${BREV_BIN}" create' in credit_writer:
            raise AssertionError("Brev credit evidence writer must not create Brev instances")

        for expected_snippet in (
            "Read the current Brev organization credit balance through the Brev API",
            "refreshes_brev_credentials_with_cli",
            "prints_token",
            "balance_usd",
            "add_brev_credits_or_reduce_budget_before_paid_run",
            "[brev-api-credit] PASS",
            "[brev-api-credit] BLOCKED",
            "[brev-api-credit] UNAVAILABLE",
        ):
            if expected_snippet not in api_credit_script:
                raise AssertionError(f"Brev API credit helper missing snippet: {expected_snippet}")
        if "brev create" in api_credit_script or '"${BREV_BIN}" create' in api_credit_script:
            raise AssertionError("Brev API credit helper must not create Brev instances")
        missing_api_credentials = tmp_dir / "missing-brev-credentials.json"
        result = run(
            [
                "python3",
                str(api_credit_path),
                "--credentials",
                str(missing_api_credentials),
                "--brev-bin",
                str(tmp_dir / "missing-brev-bin"),
                "--required-budget-eur",
                "6.00",
            ]
        )
        assert_status(result, 0, "Brev API credit helper reports unavailable without credentials")
        assert_contains(result, "[brev-api-credit] UNAVAILABLE", "Brev API credit helper unavailable marker")
        assert_contains(result, "creates_paid_instance", "Brev API credit helper side-effect detail")
        assert_contains(result, '"prints_token": false', "Brev API credit helper token safety detail")
        assert_contains(result, "fall_back_to_current_brev_ui_balance_review", "Brev API credit helper fallback detail")
        result = run(
            [
                "python3",
                str(api_credit_path),
                "--credentials",
                str(missing_api_credentials),
                "--brev-bin",
                str(tmp_dir / "missing-brev-bin"),
                "--required-budget-eur",
                "6.00",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "Brev API credit helper can fail closed when unavailable")

        credit_dry_run_output = tmp_dir / "brev_credit_verification.local.json"
        result = run(
            [
                "python3",
                "scripts/write_brev_credit_evidence.py",
                "--balance-eur",
                "20.00",
                "--budget-eur",
                "6.00",
                "--output",
                str(credit_dry_run_output),
                "--dry-run",
            ]
        )
        assert_status(result, 0, "Brev credit evidence writer dry-run succeeds")
        assert_contains(result, "[brev-credit-evidence-write] DRY_RUN", "Brev credit writer dry-run marker")
        assert_contains(result, "[brev-credit-evidence-write] facts=", "Brev credit writer dry-run facts marker")
        if credit_dry_run_output.exists():
            raise AssertionError("Brev credit evidence writer dry-run must not write the evidence file")
        credit_dry_run_facts, _ = json.JSONDecoder().raw_decode(
            result.stdout.split("[brev-credit-evidence-write] facts=", 1)[1].lstrip()
        )
        if credit_dry_run_facts["status"] != "DRY_RUN_READY":
            raise AssertionError(f"Brev credit writer dry-run should be ready: {credit_dry_run_facts}")
        if credit_dry_run_facts["side_effects"]["writes_credit_evidence"] is not False:
            raise AssertionError(f"Brev credit writer dry-run must not write evidence: {credit_dry_run_facts}")
        if credit_dry_run_facts["side_effects"]["creates_paid_instance"] is not False:
            raise AssertionError(f"Brev credit writer dry-run must not create paid instances: {credit_dry_run_facts}")
        if credit_dry_run_facts["payload_preview"]["balance_eur"] != 20.0:
            raise AssertionError(f"Brev credit writer dry-run should preview provided balance: {credit_dry_run_facts}")

        blocked_api_fixture = tmp_dir / "blocked_brev_api_credit.json"
        blocked_api_fixture.write_text(
            json.dumps(
                {
                    "check_name": "brev_api_credit_balance",
                    "status": "BLOCKED",
                    "balance_usd": 0.0,
                    "required_budget_eur": 6.0,
                    "blockers": ["Brev API credit balance 0 USD is below required budget 6.00"],
                    "next_action": "add_brev_credits_or_reduce_budget_before_paid_run",
                }
            ),
            encoding="utf-8",
        )

        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_paid_batch.py",
                "--balance-eur",
                "20.00",
                "--i-understand-this-arms-paid-run",
                "--dry-run",
            ]
        )
        assert_status(result, 0, "success variation paid prepare dry-run succeeds")
        assert_contains(result, "DRY_RUN", "paid prepare dry-run marker")
        assert_contains(result, "would not create a paid instance", "paid prepare dry-run safety detail")
        assert_contains(result, "api_credit_check", "paid prepare API credit dry-run step detail")
        assert_contains(result, "aggregate_preflight", "paid prepare aggregate preflight label")
        assert_contains(
            result,
            "check_success_variation_paid_lifecycle_preflight.py",
            "paid prepare aggregate preflight command",
        )
        paid_prepare_marker = "[success-variation-paid-prepare] facts="
        assert_contains(result, paid_prepare_marker, "paid prepare dry-run facts marker")
        paid_prepare_facts, _ = json.JSONDecoder().raw_decode(
            result.stdout.split(paid_prepare_marker, 1)[1].lstrip()
        )
        if paid_prepare_facts["status"] != "DRY_RUN":
            raise AssertionError(f"paid prepare dry-run facts should report DRY_RUN: {paid_prepare_facts}")
        if paid_prepare_facts["side_effects"]["creates_paid_instance"] is not False:
            raise AssertionError(f"paid prepare dry-run must not create paid instances: {paid_prepare_facts}")
        if paid_prepare_facts["side_effects"]["reads_brev_api"] is not False:
            raise AssertionError(f"paid prepare dry-run must not read Brev API: {paid_prepare_facts}")
        if paid_prepare_facts["side_effects"]["writes_credit_evidence"] is not False:
            raise AssertionError(f"paid prepare dry-run must not write credit evidence: {paid_prepare_facts}")
        if paid_prepare_facts["side_effects"]["arms_local_env"] is not False:
            raise AssertionError(f"paid prepare dry-run must not arm local env: {paid_prepare_facts}")
        if [step["step"] for step in paid_prepare_facts["steps"]] != [
            "api_credit_check",
            "write_credit_evidence",
            "arm_local_env",
            "check_only",
            "aggregate_preflight",
        ]:
            raise AssertionError(f"paid prepare dry-run step order changed: {paid_prepare_facts}")
        cleanup_guards = "\n".join(paid_prepare_facts["cleanup_guards"])
        for expected_snippet in (
            "Brev API credit BLOCKED or UNAVAILABLE stops before writing credit evidence or arming the local env",
            "check-only failure after arming disarms the local env",
            "aggregate preflight failure after arming disarms the local env",
            "KeyboardInterrupt after arming disarms the local env",
            "unexpected exception after arming disarms the local env",
        ):
            if expected_snippet not in cleanup_guards:
                raise AssertionError(f"paid prepare dry-run missing cleanup guard {expected_snippet}: {paid_prepare_facts}")
        blocked_prepare_credit = tmp_dir / "blocked_prepare_credit.local.json"
        blocked_prepare_config = tmp_dir / "blocked_prepare_success_variation.local.env"
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_paid_batch.py",
                "--balance-eur",
                "20.00",
                "--budget-eur",
                "6.00",
                "--config",
                str(blocked_prepare_config),
                "--credit-output",
                str(blocked_prepare_credit),
                "--api-credit-output",
                str(blocked_api_fixture),
                "--force-credit",
                "--i-understand-this-arms-paid-run",
            ]
        )
        assert_status(result, 1, "success variation paid prepare blocks before writing when API credit is low")
        assert_contains(result, "api_credit_status=BLOCKED", "paid prepare blocked API status detail")
        assert_contains(result, "no credit evidence was written", "paid prepare blocked no-write detail")
        assert_contains(result, "local env was not armed", "paid prepare blocked no-arm detail")
        if blocked_prepare_credit.exists():
            raise AssertionError("paid prepare must not write credit evidence when API credit is blocked")
        if blocked_prepare_config.exists():
            raise AssertionError("paid prepare must not create or arm local env when API credit is blocked")
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_paid_batch.py",
                "--balance-eur",
                "20.00",
                "--dry-run",
            ]
        )
        assert_status(result, 1, "success variation paid prepare requires explicit arming acknowledgement")
        assert_contains(result, "--i-understand-this-arms-paid-run", "paid prepare acknowledgement guidance")

        for expected_snippet in (
            "Prepare, but do not run, one success-variation paid batch",
            "write_brev_credit_evidence.py",
            "arm_success_variation_paid_env.py",
            "run_success_variation_batch_from_config.sh",
            "check_success_variation_paid_lifecycle_preflight.py",
            "--check-only",
            "api_credit_check",
            "read_brev_credit_balance.py",
            "--api-credit-output",
            "Brev API credit BLOCKED or UNAVAILABLE stops before writing credit evidence or arming the local env",
            "aggregate_preflight",
            "READY_FOR_SINGLE_PAID_RUN",
            "would not create a paid instance",
            "disarms the local env",
            "except KeyboardInterrupt",
            "[success-variation-paid-prepare] INTERRUPTED",
            "return 130",
            "except Exception as exc",
            "[success-variation-paid-prepare] FAILED_AFTER_ARM",
            "return 1",
            "does not create, start, stop, delete, copy to, or execute on Brev instances",
        ):
            if expected_snippet not in prepare_paid_script:
                raise AssertionError(f"success variation paid prepare helper missing snippet: {expected_snippet}")
        if "brev create" in prepare_paid_script or '"${BREV_BIN}" create' in prepare_paid_script:
            raise AssertionError("success variation paid prepare helper must not create Brev instances")

        result = run(["python3", str(credit_review_path), "--no-output"])
        assert_status(result, 0, "Brev credit review packet reports current blocked state")
        assert_contains(result, "[brev-credit-review] status=", "Brev credit review status detail")
        assert_contains(result, "api_credit_status=", "Brev credit review API credit status detail")
        assert_contains(result, "api_credit_balance_usd=", "Brev credit review API credit balance detail")
        assert_contains(result, "credit_consistency_status=NO_UI_BALANCE_PROVIDED", "Brev credit review default consistency detail")
        assert_contains(result, "paid_prepare_allowed=False", "Brev credit review default paid-prepare guard detail")
        assert_contains(result, "balance_preview_status=NOT_PROVIDED", "Brev credit review default balance preview detail")
        assert_contains(result, "dashboard_url=https://brev.nvidia.com/org/", "Brev credit review dashboard detail")
        assert_contains(result, "preview_credit_evidence=", "Brev credit review preview evidence command detail")
        assert_contains(result, "write_credit_evidence=", "Brev credit review follow-up command detail")
        assert_contains(result, "preview_prepare_paid_batch=", "Brev credit review preview prepare command detail")
        assert_contains(result, "prepare_success_variation_paid_batch.py", "Brev credit review prepare helper command")
        assert_contains(result, "paid_lifecycle_unblock_plan", "Brev credit review paid unblock-plan detail")
        assert_contains(result, "paid_lifecycle_blocked_subchecks", "Brev credit review paid blocked-subchecks detail")
        assert_contains(result, "BLOCKED_REFRESH_CREDIT_AND_ACKS", "Brev credit review blocked unblock-plan status detail")
        result = run(["python3", str(credit_review_path), "--api-credit-output", str(blocked_api_fixture), "--no-output"])
        assert_status(result, 0, "Brev credit review consumes saved blocked API credit output")
        assert_contains(result, "NEEDS_BREV_CREDIT_TOPUP", "Brev credit review top-up status detail")
        assert_contains(result, "api_credit_status=BLOCKED", "Brev credit review blocked API detail")
        assert_contains(result, "api_credit_balance_usd=0.0", "Brev credit review blocked API balance detail")
        result = run(
            [
                "python3",
                str(credit_review_path),
                "--api-credit-output",
                str(blocked_api_fixture),
                "--balance-eur",
                "20.00",
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "Brev credit review blocks paid readiness when API balance is too low")
        assert_contains(result, "NEEDS_BREV_CREDIT_TOPUP", "Brev credit review API blocker overrides UI preview")
        assert_contains(
            result,
            "credit_consistency_status=UI_API_MISMATCH_API_BLOCKED",
            "Brev credit review detects UI/API credit mismatch",
        )
        assert_contains(result, "paid_prepare_allowed=False", "Brev credit review blocks prepare on UI/API mismatch")
        result = run(["python3", str(credit_review_path), "--balance-eur", "20.00", "--no-output"])
        assert_status(result, 0, "Brev credit review accepts concrete UI balance for preview commands")
        assert_contains(result, "balance_preview_status=PASS", "Brev credit review concrete balance preview detail")
        assert_contains(
            result,
            "preview_credit_evidence=python3 scripts/write_brev_credit_evidence.py --balance-eur 20.00",
            "Brev credit review concrete preview evidence command detail",
        )
        assert_contains(
            result,
            "preview_prepare_paid_batch=python3 scripts/prepare_success_variation_paid_batch.py --balance-eur 20.00",
            "Brev credit review concrete preview prepare command detail",
        )
        result = run(["python3", str(credit_review_path), "--no-output", "--fail-on-blocked"])
        assert_status(result, 1, "Brev credit review can fail closed while UI evidence is missing")

        result = run(["python3", str(credit_diagnosis_path), "--api-credit-output", str(blocked_api_fixture), "--no-output"])
        assert_status(result, 0, "Brev credit diagnosis reports saved blocked API state")
        assert_contains(result, "status=API_CREDIT_BLOCKED", "Brev credit diagnosis API blocked detail")
        assert_contains(result, "active_org_id=org-3BaYGdtoRGmgc77Z7NHHhPSD254", "Brev credit diagnosis active org detail")
        assert_contains(result, "api_credit_status=BLOCKED", "Brev credit diagnosis API status detail")
        assert_contains(result, "credit_consistency_status=NO_UI_BALANCE_PROVIDED", "Brev credit diagnosis default consistency detail")
        assert_contains(result, "paid_prepare_allowed=False", "Brev credit diagnosis prepare guard detail")
        assert_contains(result, "visible_instances=0", "Brev credit diagnosis instance safety detail")
        result = run(
            [
                "python3",
                str(credit_diagnosis_path),
                "--api-credit-output",
                str(blocked_api_fixture),
                "--balance-eur",
                "20.00",
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "Brev credit diagnosis fails closed on UI/API mismatch")
        assert_contains(result, "status=UI_API_MISMATCH_BLOCKED", "Brev credit diagnosis UI/API mismatch detail")
        assert_contains(
            result,
            "credit_consistency_status=UI_API_MISMATCH_API_BLOCKED",
            "Brev credit diagnosis consistency mismatch detail",
        )
        assert_contains(result, "paid_prepare_allowed=False", "Brev credit diagnosis mismatch guard detail")

        fake_open_log = tmp_dir / "brev_credit_review_open.log"
        fake_open_bin = tmp_dir / "fake-open-brev-credit-review.sh"
        fake_open_bin.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$RCA_FAKE_OPEN_LOG\"\n",
            encoding="utf-8",
        )
        fake_open_bin.chmod(0o755)
        result = run(
            ["python3", str(credit_review_path), "--open-dashboard", "--no-output"],
            env={"RCA_OPEN_BIN": str(fake_open_bin), "RCA_FAKE_OPEN_LOG": str(fake_open_log)},
        )
        assert_status(result, 0, "Brev credit review can open dashboard without creating paid resources")
        if "https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments" not in fake_open_log.read_text(
            encoding="utf-8"
        ):
            raise AssertionError("Brev credit review should open the organization dashboard URL")

        for expected_snippet in (
            "Prepare the Brev UI credit review before a paid success-variation run",
            "NEEDS_BREV_UI_CREDIT_EVIDENCE",
            "NEEDS_BREV_CREDIT_TOPUP",
            "READY_FOR_PAID_LIFECYCLE",
            "api_credit_balance",
            "--api-credit-output",
            "--skip-api-credit",
            "--source-status-output",
            "balance_eur_for_preview",
            "preview_credit_evidence",
            "write_brev_credit_evidence.py",
            "preview_prepare_paid_batch",
            "prepare_success_variation_paid_batch.py",
            "prepare_paid_batch",
            "paid_lifecycle_unblock_plan",
            "paid_lifecycle_blocked_subchecks",
            "check_success_variation_paid_lifecycle_preflight.py",
            "run_success_variation_paid_lifecycle.py",
            "opens_dashboard",
            "creates_paid_instance",
            "By default it does not open a browser, write credit evidence",
        ):
            if expected_snippet not in credit_review_script:
                raise AssertionError(f"Brev credit review helper missing snippet: {expected_snippet}")
        if "brev create" in credit_review_script or '"${BREV_BIN}" create' in credit_review_script:
            raise AssertionError("Brev credit review helper must not create Brev instances")

        for expected_snippet in (
            "Diagnose why the fixed-budget Brev paid run is still credit-blocked",
            "UI_API_MISMATCH_BLOCKED",
            "API_CREDIT_BLOCKED",
            "paid_prepare_allowed",
            "creates_paid_instance",
            "writes_local_env",
            "does not open a browser, write credit evidence, arm local env state",
        ):
            if expected_snippet not in credit_diagnosis_script:
                raise AssertionError(f"Brev credit diagnosis helper missing snippet: {expected_snippet}")
        if "brev create" in credit_diagnosis_script or '"${BREV_BIN}" create' in credit_diagnosis_script:
            raise AssertionError("Brev credit diagnosis helper must not create Brev instances")

        result = run(["python3", str(paid_preflight_path), "--no-output"])
        assert_status(result, 0, "success variation paid lifecycle preflight reports blocked current state")
        assert_contains(result, "[success-variation-paid-preflight] status=BLOCKED", "paid lifecycle preflight blocked marker")
        assert_contains(result, "Brev credit evidence file is missing", "paid lifecycle preflight credit blocker detail")
        assert_contains(result, "watchdog_max_minutes", "paid lifecycle preflight watchdog plan detail")
        assert_contains(result, "estimated_max_cost_eur", "paid lifecycle preflight cost-envelope detail")
        assert_contains(result, "api_credit_balance", "paid lifecycle preflight API credit facts detail")
        assert_contains(result, "api_credit_blockers", "paid lifecycle preflight API blocker detail")
        assert_contains(result, "required_cleanup_guards", "paid lifecycle preflight cleanup guard detail")
        assert_contains(result, "blocked_subchecks", "paid lifecycle preflight blocked-subchecks detail")
        assert_contains(result, "unblock_plan", "paid lifecycle preflight unblock-plan detail")
        assert_contains(result, "preview_credit_evidence", "paid lifecycle preflight credit preview command detail")
        assert_contains(result, "arm_one_run_paid_local_env", "paid lifecycle preflight arm command detail")
        assert_contains(
            result,
            "success-variation pre-batch assumption audit must pass before the paid lifecycle",
            "paid lifecycle preflight assumption-audit blocker detail",
        )
        assert_contains(result, "no paid instance was created", "paid lifecycle preflight safety detail")
        result = run(["python3", str(paid_preflight_path), "--no-output", "--fail-on-blocked"])
        assert_status(result, 1, "success variation paid lifecycle preflight can fail closed")

        ready_credit_path = tmp_dir / "paid_lifecycle_preflight_ready" / "brev_credit_verification.local.json"
        result = run(
            [
                "python3",
                "scripts/write_brev_credit_evidence.py",
                "--balance-eur",
                "20.00",
                "--budget-eur",
                "6.00",
                "--output",
                str(ready_credit_path),
            ]
        )
        assert_status(result, 0, "test fixture writes valid Brev credit evidence")
        ready_config_path = tmp_dir / "paid_lifecycle_preflight_ready" / "success_variation_batch_run.local.env"
        ready_config_text = (REPO_ROOT / "configs" / "success_variation_batch_run.local.env").read_text(
            encoding="utf-8"
        )
        ready_config_text = ready_config_text.replace(
            "RCA_BREV_CREDIT_EVIDENCE_JSON=configs/brev_credit_verification.local.json",
            f"RCA_BREV_CREDIT_EVIDENCE_JSON={ready_credit_path}",
        )
        ready_config_path.write_text(ready_config_text, encoding="utf-8")
        fake_safe_brev = tmp_dir / "paid_lifecycle_preflight_ready" / "brev_safety_safe.txt"
        fake_safe_brev.write_text(
            "\n".join(
                [
                    "[brev-safety] healthcheck=pass",
                    "[brev-safety] org_list=pass",
                    "[brev-safety] instance_list=pass",
                    "[brev-safety] visible_instances=0",
                    "[brev-safety] watchdog_processes=none",
                    "[brev-safety] manual_delete_alerts=none",
                    "[brev-safety] status=SAFE_NO_VISIBLE_PAID_INSTANCE",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fake_clean_source = tmp_dir / "paid_lifecycle_preflight_ready" / "project_status_clean.txt"
        fake_clean_source.write_text(
            "\n".join(
                [
                    "| Check | Status | Detail |",
                    "| --- | --- | --- |",
                    "| Git worktree | CLEAN | No uncommitted changes. |",
                    "| Contact-smoke bundle | READY | Latest bundle matches current runtime payload scope/hash. |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fake_dirty_source = tmp_dir / "paid_lifecycle_preflight_ready" / "project_status_dirty.txt"
        fake_dirty_source.write_text(
            "\n".join(
                [
                    "| Check | Status | Detail |",
                    "| --- | --- | --- |",
                    "| Git worktree | DIRTY | synthetic dirty source state |",
                    "| Contact-smoke bundle | READY | Latest bundle matches current runtime payload scope/hash. |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        ready_run_packet_path = tmp_dir / "paid_lifecycle_preflight_ready" / "run_packet_ready.json"
        ready_run_packet_path.write_text(
            json.dumps(
                {
                    "readiness": {
                        "status": "READY",
                        "blockers": [],
                        "facts": {"brev_safety_status": "SAFE_NO_VISIBLE_PAID_INSTANCE"},
                    },
                    "estimated_cost": {"budget_eur": 6.0, "estimated_max_cost_eur": 5.625},
                }
            ),
            encoding="utf-8",
        )
        ready_preflight_json = tmp_dir / "paid_lifecycle_preflight_ready" / "preflight.json"
        ready_preflight_md = tmp_dir / "paid_lifecycle_preflight_ready" / "README.md"
        ready_api_fixture = tmp_dir / "paid_lifecycle_preflight_ready" / "passing_brev_api_credit.json"
        ready_api_fixture.write_text(
            json.dumps(
                {
                    "check_name": "brev_api_credit_balance",
                    "status": "PASS",
                    "balance_usd": 20.0,
                    "required_budget_eur": 6.0,
                    "blockers": [],
                    "failures": [],
                    "next_action": "write_fresh_credit_evidence_from_current_balance",
                }
            ),
            encoding="utf-8",
        )
        result = run(
            [
                "python3",
                str(paid_preflight_path),
                "--config",
                str(ready_config_path),
                "--brev-safety-output",
                str(fake_safe_brev),
                "--source-status-output",
                str(fake_clean_source),
                "--run-packet",
                str(ready_run_packet_path),
                "--api-credit-output",
                str(ready_api_fixture),
                "--output-json",
                str(ready_preflight_json),
                "--output-md",
                str(ready_preflight_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "success variation paid lifecycle preflight has a READY offline path")
        assert_contains(
            result,
            "READY_FOR_SINGLE_PAID_LIFECYCLE",
            "paid lifecycle preflight READY detail",
        )
        ready_preflight = json.loads(ready_preflight_json.read_text(encoding="utf-8"))
        if ready_preflight["status"] != "READY_FOR_SINGLE_PAID_LIFECYCLE":
            raise AssertionError(f"paid lifecycle preflight should be ready with valid offline evidence: {ready_preflight}")
        if ready_preflight["credit_evidence"]["status"] != "PASS":
            raise AssertionError(f"paid lifecycle preflight should accept valid credit evidence: {ready_preflight}")
        if ready_preflight["api_credit_balance"]["status"] != "PASS":
            raise AssertionError(f"paid lifecycle preflight should require passing API credit evidence: {ready_preflight}")
        if ready_preflight["api_credit_balance"]["balance_usd"] != 20.0:
            raise AssertionError(f"paid lifecycle preflight should expose API credit balance: {ready_preflight}")
        if ready_preflight["armability"]["status"] != "PASS":
            raise AssertionError(f"paid lifecycle preflight should accept safe armability fixture: {ready_preflight}")
        current_arming = ready_preflight["armability"].get("current_arming")
        if not isinstance(current_arming, dict):
            raise AssertionError(f"paid lifecycle preflight should expose current arming state: {ready_preflight}")
        if current_arming["armed"] is not False:
            raise AssertionError(f"ready preflight fixture should start disarmed before arming: {ready_preflight}")
        brev_safety = ready_preflight["armability"]["brev_safety"]
        if brev_safety["visible_instances"] != "0":
            raise AssertionError(f"paid lifecycle preflight should expose visible instance count: {ready_preflight}")
        if brev_safety["watchdog_processes"] != "none":
            raise AssertionError(f"paid lifecycle preflight should expose watchdog process state: {ready_preflight}")
        if brev_safety["manual_delete_alerts"] != "none":
            raise AssertionError(f"paid lifecycle preflight should expose manual-delete alert state: {ready_preflight}")
        if ready_preflight["source_state"]["git_worktree"]["status"] != "CLEAN":
            raise AssertionError(f"paid lifecycle preflight should record clean source state: {ready_preflight}")
        if ready_preflight["source_state"]["contact_smoke_bundle"]["status"] != "READY":
            raise AssertionError(f"paid lifecycle preflight should record READY contact bundle: {ready_preflight}")
        if ready_preflight["pre_batch_assumption_audit"]["audit_status"] != "PASS":
            raise AssertionError(f"paid lifecycle preflight should enforce a passing pre-batch audit: {ready_preflight}")
        if ready_preflight["unblock_plan"]["status"] != "READY_TO_RUN_SINGLE_PAID_LIFECYCLE":
            raise AssertionError(f"paid lifecycle preflight should expose ready unblock-plan status: {ready_preflight}")
        if ready_preflight["blocked_subchecks"]["credit_evidence_blockers"]:
            raise AssertionError(f"ready preflight should have no credit blockers: {ready_preflight}")
        if ready_preflight["blocked_subchecks"]["api_credit_blockers"]:
            raise AssertionError(f"ready preflight should have no API credit blockers: {ready_preflight}")
        if ready_preflight["blocked_subchecks"]["required_acknowledgement_blockers"]:
            raise AssertionError(f"ready preflight should have no ack blockers: {ready_preflight}")
        lifecycle_plan = ready_preflight["lifecycle_plan"]
        if lifecycle_plan["budget"]["watchdog_max_minutes"] != 75:
            raise AssertionError(f"paid lifecycle preflight should expose watchdog TTL: {ready_preflight}")
        if lifecycle_plan["budget"]["estimated_max_cost_eur"] != 5.625:
            raise AssertionError(f"paid lifecycle preflight should expose estimated max cost: {ready_preflight}")
        if lifecycle_plan["timeouts"]["auto_disarm"] is not True:
            raise AssertionError(f"paid lifecycle preflight should expose auto-disarm: {ready_preflight}")
        if "manual_disarm_fallback" not in lifecycle_plan["commands"]:
            raise AssertionError(f"paid lifecycle preflight should expose manual disarm fallback: {ready_preflight}")
        if "SAFE_NO_VISIBLE_PAID_INSTANCE" not in " ".join(lifecycle_plan["required_cleanup_guards"]):
            raise AssertionError(f"paid lifecycle preflight should expose cleanup confirmation guard: {ready_preflight}")
        if any(lifecycle_plan["side_effects"].values()):
            raise AssertionError(f"paid lifecycle plan must remain side-effect free: {ready_preflight}")
        if any(ready_preflight["side_effects"].values()):
            raise AssertionError(f"paid lifecycle preflight must remain side-effect free: {ready_preflight}")
        ready_preflight_md_text = ready_preflight_md.read_text(encoding="utf-8")
        for expected_snippet in (
            "brev_safety_status: SAFE_NO_VISIBLE_PAID_INSTANCE",
            "brev_visible_instances: 0",
            "brev_watchdog_processes: none",
            "brev_manual_delete_alerts: none",
            "api_credit_status: PASS",
            "api_credit_balance_usd: 20.0",
            "current_paid_arming: False",
            "Unblock Sequence",
            "READY_TO_RUN_SINGLE_PAID_LIFECYCLE",
        ):
            if expected_snippet not in ready_preflight_md_text:
                raise AssertionError(f"paid lifecycle preflight markdown missing safety snippet {expected_snippet}")
        if "Success Variation Paid Lifecycle Preflight" not in ready_preflight_md_text:
            raise AssertionError("paid lifecycle preflight README should include a clear title")
        if "Cleanup Guards" not in ready_preflight_md_text:
            raise AssertionError("paid lifecycle preflight README should include cleanup guards")
        stale_armed_config_path = tmp_dir / "paid_lifecycle_preflight_ready" / "stale_armed_success_variation.env"
        stale_armed_text = ready_config_text
        stale_armed_text = stale_armed_text.replace(
            "RCA_BREV_CREDIT_EVIDENCE_JSON=configs/brev_credit_verification.local.json",
            f"RCA_BREV_CREDIT_EVIDENCE_JSON={ready_credit_path}",
        )
        stale_armed_text = stale_armed_text.replace(
            "RCA_PAID_ARMED_AT_UTC=",
            "RCA_PAID_ARMED_AT_UTC=2000-01-01T00:00:00Z",
        )
        stale_armed_text = stale_armed_text.replace("RCA_ALLOW_PAID_BREV_CREATE=0", "RCA_ALLOW_PAID_BREV_CREATE=1")
        stale_armed_text = stale_armed_text.replace("RCA_BREV_CREDITS_VERIFIED=0", "RCA_BREV_CREDITS_VERIFIED=1")
        stale_armed_text = stale_armed_text.replace("RCA_ACK_BREV_LIFECYCLE_RISK=0", "RCA_ACK_BREV_LIFECYCLE_RISK=1")
        stale_armed_config_path.write_text(stale_armed_text, encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/arm_success_variation_paid_env.py",
                "--config",
                str(stale_armed_config_path),
                "--brev-safety-output",
                str(fake_safe_brev),
                "--dry-run",
                "--i-understand-this-arms-paid-run",
            ]
        )
        assert_status(result, 1, "success variation arm gate rejects stale already-armed env")
        assert_contains(result, "existing paid arming is too old", "stale arming direct guard detail")
        result = run(
            [
                "python3",
                str(paid_preflight_path),
                "--config",
                str(stale_armed_config_path),
                "--brev-safety-output",
                str(fake_safe_brev),
                "--source-status-output",
                str(fake_clean_source),
                "--run-packet",
                str(ready_run_packet_path),
                "--api-credit-output",
                str(ready_api_fixture),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "success variation paid lifecycle preflight rejects stale armed env")
        assert_contains(result, "existing paid arming is too old", "paid lifecycle preflight stale arming detail")
        result = run(
            [
                "python3",
                str(paid_preflight_path),
                "--config",
                str(ready_config_path),
                "--brev-safety-output",
                str(fake_safe_brev),
                "--source-status-output",
                str(fake_dirty_source),
                "--run-packet",
                str(ready_run_packet_path),
                "--api-credit-output",
                str(ready_api_fixture),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "success variation paid lifecycle preflight rejects dirty source state")
        assert_contains(result, "Git worktree must be CLEAN", "paid lifecycle preflight dirty source detail")
        result = run(
            [
                "python3",
                str(paid_preflight_path),
                "--config",
                str(ready_config_path),
                "--brev-safety-output",
                str(fake_safe_brev),
                "--source-status-output",
                str(fake_clean_source),
                "--run-packet",
                str(ready_run_packet_path),
                "--api-credit-output",
                str(blocked_api_fixture),
                "--no-output",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "success variation paid lifecycle preflight rejects low API credit balance")
        assert_contains(
            result,
            "Brev API credit balance must be readable and cover the paid lifecycle budget",
            "paid lifecycle preflight API credit blocker detail",
        )
        assert_contains(result, "api_credit_blockers", "paid lifecycle preflight API blocked-subcheck detail")
        ready_credit_review_json = tmp_dir / "paid_lifecycle_preflight_ready" / "credit_review.json"
        ready_credit_review_md = tmp_dir / "paid_lifecycle_preflight_ready" / "credit_review.md"
        result = run(
            [
                "python3",
                str(credit_review_path),
                "--config",
                str(ready_config_path),
                "--brev-safety-output",
                str(fake_safe_brev),
                "--source-status-output",
                str(fake_clean_source),
                "--run-packet",
                str(ready_run_packet_path),
                "--api-credit-output",
                str(ready_api_fixture),
                "--output-json",
                str(ready_credit_review_json),
                "--output-md",
                str(ready_credit_review_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "Brev credit review packet has a READY offline path")
        assert_contains(result, "READY_FOR_PAID_LIFECYCLE", "Brev credit review READY detail")
        ready_credit_review = json.loads(ready_credit_review_json.read_text(encoding="utf-8"))
        if ready_credit_review["status"] != "READY_FOR_PAID_LIFECYCLE":
            raise AssertionError(f"Brev credit review should be ready with valid evidence: {ready_credit_review}")
        if ready_credit_review["credit_consistency"]["status"] != "LOCAL_EVIDENCE_API_CONSISTENT_PASS":
            raise AssertionError(f"Brev credit review should confirm UI/API consistency when ready: {ready_credit_review}")
        if ready_credit_review["credit_consistency"]["paid_prepare_allowed"] is not True:
            raise AssertionError(f"Brev credit review should allow prepare only after consistent pass: {ready_credit_review}")
        if ready_credit_review["side_effects"]["creates_paid_instance"] is not False:
            raise AssertionError(f"Brev credit review must not create paid instances: {ready_credit_review}")
        if ready_credit_review["paid_lifecycle_preflight"]["pre_batch_assumption_audit"]["audit_status"] != "PASS":
            raise AssertionError(f"Brev credit review should preserve passing pre-batch audit: {ready_credit_review}")
        if ready_credit_review["paid_lifecycle_unblock_plan"]["status"] != "READY_TO_RUN_SINGLE_PAID_LIFECYCLE":
            raise AssertionError(f"Brev credit review should preserve ready paid unblock-plan: {ready_credit_review}")
        if ready_credit_review["paid_lifecycle_blocked_subchecks"]["required_acknowledgement_blockers"]:
            raise AssertionError(f"READY Brev credit review should not have ack blockers: {ready_credit_review}")
        ready_credit_md_text = ready_credit_review_md.read_text(encoding="utf-8")
        if "Brev Credit Review Packet" not in ready_credit_md_text:
            raise AssertionError("Brev credit review README should include a clear title")
        if "Paid Lifecycle Unblock Plan" not in ready_credit_md_text:
            raise AssertionError("Brev credit review README should include the paid lifecycle unblock plan")

        for expected_snippet in (
            "success_variation_paid_lifecycle_preflight",
            "clean source state, current contact-smoke bundle, credit evidence",
            "--brev-safety-output",
            "--source-status-output",
            "source_state",
            "Git worktree must be CLEAN",
            "current contact-smoke bundle must be READY",
            "check_success_variation_batch_plan.py",
            "audit_success_variation_assumptions",
            "pre_batch_assumption_audit",
            "lifecycle_plan",
            "blocked_subchecks",
            "unblock_plan",
            "required_acknowledgement_blockers",
            "api_credit_balance",
            "api_credit_blockers",
            "--api-credit-output",
            "preview_credit_evidence",
            "arm_one_run_paid_local_env",
            "required_cleanup_guards",
            "estimated_max_cost_eur",
            "manual_disarm_fallback",
            "success-variation pre-batch assumption audit must pass before the paid lifecycle",
            "arm_success_variation_paid_env",
            "READY_FOR_SINGLE_PAID_LIFECYCLE",
            "current_paid_arming",
            "not a paid run",
            "not armed local env",
            "writes_local_env",
            "creates_paid_instance",
            "no paid instance was created",
        ):
            if expected_snippet not in paid_preflight_script:
                raise AssertionError(f"success variation paid lifecycle preflight missing snippet: {expected_snippet}")
        if "brev create" in paid_preflight_script or '"${BREV_BIN}" create' in paid_preflight_script:
            raise AssertionError("success variation paid lifecycle preflight must not create Brev instances")

        result = run(
            [
                "python3",
                "scripts/run_success_variation_paid_lifecycle.py",
                "--balance-eur",
                "20.00",
                "--i-understand-this-can-create-paid-instance",
                "--dry-run",
            ]
        )
        assert_status(result, 0, "success variation paid lifecycle dry-run succeeds")
        assert_contains(result, "DRY_RUN", "paid lifecycle dry-run marker")
        assert_contains(result, "would not create a paid instance", "paid lifecycle dry-run safety detail")
        assert_contains(result, "[success-variation-lifecycle] facts=", "paid lifecycle dry-run facts marker")
        assert_contains(
            result,
            "check_success_variation_paid_lifecycle_preflight.py",
            "paid lifecycle aggregate preflight detail",
        )
        assert_contains(result, "finalize_success_variation_batch.sh", "paid lifecycle finalizer detail")
        assert_contains(
            result,
            "run_v0_offline_policy_readiness_pipeline.py",
            "paid lifecycle offline policy-readiness detail",
        )
        assert_contains(result, "plan_success_variation_recovery_batch.py", "paid lifecycle recovery detail")
        paid_lifecycle_facts, _ = json.JSONDecoder().raw_decode(
            result.stdout.split("[success-variation-lifecycle] facts=", 1)[1].lstrip()
        )
        if paid_lifecycle_facts["status"] != "DRY_RUN":
            raise AssertionError(f"paid lifecycle dry-run facts should report DRY_RUN: {paid_lifecycle_facts}")
        if paid_lifecycle_facts["balance_eur"] != 20.0:
            raise AssertionError(f"paid lifecycle dry-run should preserve provided balance: {paid_lifecycle_facts}")
        if paid_lifecycle_facts["side_effects"]["creates_paid_instance"] is not False:
            raise AssertionError(f"paid lifecycle dry-run must not create paid instances: {paid_lifecycle_facts}")
        if paid_lifecycle_facts["side_effects"]["arms_local_env"] is not False:
            raise AssertionError(f"paid lifecycle dry-run must not arm local env: {paid_lifecycle_facts}")
        if paid_lifecycle_facts["side_effects"]["writes_recovery_plan"] is not False:
            raise AssertionError(f"paid lifecycle dry-run must not write a recovery plan: {paid_lifecycle_facts}")
        if "KeyboardInterrupt disarms local paid env" not in " ".join(paid_lifecycle_facts["cleanup_guards"]):
            raise AssertionError(f"paid lifecycle dry-run should expose interrupt cleanup: {paid_lifecycle_facts}")
        if paid_lifecycle_facts["execution_order"][:3] != ["prepare", "preflight", "run"]:
            raise AssertionError(f"paid lifecycle dry-run execution order changed: {paid_lifecycle_facts}")
        custom_lifecycle_config = tmp_dir / "custom_success_variation_batch_run.local.env"
        custom_lifecycle_credit = tmp_dir / "custom_brev_credit_verification.local.json"
        custom_lifecycle_config.write_text(
            (REPO_ROOT / "configs" / "success_variation_batch_run.local.env")
            .read_text(encoding="utf-8")
            .replace(
                "RCA_BREV_CREDIT_EVIDENCE_JSON=configs/brev_credit_verification.local.json",
                f"RCA_BREV_CREDIT_EVIDENCE_JSON={custom_lifecycle_credit}",
            ),
            encoding="utf-8",
        )
        result = run(
            [
                "python3",
                "scripts/run_success_variation_paid_lifecycle.py",
                "--balance-eur",
                "20.00",
                "--config",
                str(custom_lifecycle_config),
                "--dry-run",
            ]
        )
        assert_status(result, 0, "success variation paid lifecycle dry-run preserves custom config")
        custom_lifecycle_facts, _ = json.JSONDecoder().raw_decode(
            result.stdout.split("[success-variation-lifecycle] facts=", 1)[1].lstrip()
        )
        if custom_lifecycle_facts["commands"]["prepare"][
            custom_lifecycle_facts["commands"]["prepare"].index("--config") + 1
        ] != str(custom_lifecycle_config):
            raise AssertionError(
                f"paid lifecycle custom config should be preserved in prepare command: {custom_lifecycle_facts}"
            )
        assert_contains(
            result,
            "success_trace_variations_2026-06-25.json",
            "paid lifecycle custom manifest preflight detail",
        )
        if custom_lifecycle_facts["commands"]["prepare"][
            custom_lifecycle_facts["commands"]["prepare"].index("--credit-output") + 1
        ] != str(custom_lifecycle_credit):
            raise AssertionError(
                f"paid lifecycle custom credit evidence should be preserved in prepare command: {custom_lifecycle_facts}"
            )
        result = run(["python3", "scripts/run_success_variation_paid_lifecycle.py"])
        assert_status(result, 1, "success variation paid lifecycle blocks without explicit run inputs")
        assert_contains(result, "BLOCKED", "paid lifecycle blocked marker")
        assert_contains(result, "--balance-eur", "paid lifecycle balance guidance")
        assert_contains(result, "no paid instance was created", "paid lifecycle blocked safety detail")

        lifecycle_module_spec = importlib.util.spec_from_file_location(
            "rca_success_variation_paid_lifecycle_test_module",
            REPO_ROOT / "scripts" / "run_success_variation_paid_lifecycle.py",
        )
        if lifecycle_module_spec is None or lifecycle_module_spec.loader is None:
            raise AssertionError("could not import success variation paid lifecycle module for cleanup tests")
        lifecycle_module = importlib.util.module_from_spec(lifecycle_module_spec)
        lifecycle_module_spec.loader.exec_module(lifecycle_module)
        lifecycle_commands = {
            "prepare": ["prepare"],
            "preflight": ["preflight"],
            "run": ["run"],
            "disarm": ["disarm"],
            "safety": ["safety"],
            "finalize": ["finalize"],
            "policy_readiness": ["policy_readiness"],
            "recovery": ["recovery"],
        }

        def exercise_lifecycle(status_by_label: dict[str, int], interrupt_label: str | None = None) -> tuple[int, list[str]]:
            calls: list[str] = []
            original_run = lifecycle_module._run

            def fake_run(label: str, command: list[str]) -> int:
                del command
                calls.append(label)
                if label == interrupt_label:
                    raise KeyboardInterrupt
                return status_by_label.get(label, 0)

            lifecycle_module._run = fake_run
            try:
                status = lifecycle_module._execute_lifecycle(SimpleNamespace(), lifecycle_commands)
            finally:
                lifecycle_module._run = original_run
            return status, calls

        status, calls = exercise_lifecycle({"prepare": 5})
        if status != 5 or calls != ["prepare", "disarm", "safety"]:
            raise AssertionError(f"paid lifecycle prepare failure should disarm and safety-check: {status=} {calls=}")
        status, calls = exercise_lifecycle({"prepare": 5, "disarm": 11})
        if status != 11 or calls != ["prepare", "disarm", "safety"]:
            raise AssertionError(f"paid lifecycle prepare cleanup failure should fail closed: {status=} {calls=}")
        status, calls = exercise_lifecycle({"preflight": 6})
        if status != 6 or calls != ["prepare", "preflight", "disarm", "safety"]:
            raise AssertionError(f"paid lifecycle preflight failure should disarm and safety-check: {status=} {calls=}")
        status, calls = exercise_lifecycle({"preflight": 6, "safety": 12})
        if status != 12 or calls != ["prepare", "preflight", "disarm", "safety"]:
            raise AssertionError(f"paid lifecycle preflight safety failure should fail closed: {status=} {calls=}")
        status, calls = exercise_lifecycle({}, interrupt_label="preflight")
        if status != 130 or calls != ["prepare", "preflight", "disarm", "safety", "recovery"]:
            raise AssertionError(f"paid lifecycle preflight interrupt should disarm, safety-check, and recover: {status=} {calls=}")
        status, calls = exercise_lifecycle({"run": 7})
        if status != 7 or calls != ["prepare", "preflight", "run", "disarm", "safety", "recovery"]:
            raise AssertionError(f"paid lifecycle run failure should disarm, safety-check, and recover: {status=} {calls=}")
        status, calls = exercise_lifecycle({"safety": 13})
        if status != 13 or calls != ["prepare", "preflight", "run", "disarm", "safety", "recovery"]:
            raise AssertionError(f"paid lifecycle post-run safety failure should recover and fail closed: {status=} {calls=}")
        status, calls = exercise_lifecycle({"finalize": 9})
        if status != 9 or calls != ["prepare", "preflight", "run", "disarm", "safety", "finalize", "recovery"]:
            raise AssertionError(f"paid lifecycle finalize failure should recover after cleanup: {status=} {calls=}")
        status, calls = exercise_lifecycle({"safety_final": 14})
        if status != 14 or calls != [
            "prepare",
            "preflight",
            "run",
            "disarm",
            "safety",
            "finalize",
            "policy_readiness",
            "safety_final",
            "recovery",
        ]:
            raise AssertionError(f"paid lifecycle final safety failure should recover and fail closed: {status=} {calls=}")
        status, calls = exercise_lifecycle({}, interrupt_label="run")
        if status != 130 or calls != ["prepare", "preflight", "run", "disarm", "safety", "recovery"]:
            raise AssertionError(f"paid lifecycle interrupt should disarm, safety-check, and recover: {status=} {calls=}")
        status, calls = exercise_lifecycle({})
        if status != 0 or calls != [
            "prepare",
            "preflight",
            "run",
            "disarm",
            "safety",
            "finalize",
            "policy_readiness",
            "safety_final",
        ]:
            raise AssertionError(f"paid lifecycle success should run final safety after policy readiness: {status=} {calls=}")

        for expected_snippet in (
            "highest-level paid entrypoint",
            "--i-understand-this-can-create-paid-instance",
            "prepare_success_variation_paid_batch.py",
            "check_success_variation_paid_lifecycle_preflight.py",
            "--fail-on-blocked",
            "RCA_BREV_CREDIT_EVIDENCE_JSON",
            "run_success_variation_batch_from_config.sh",
            "arm_success_variation_paid_env.py",
            "brev_paid_safety_status.sh",
            "[success-variation-lifecycle] facts=",
            "cleanup_guards",
            "prepare failure disarms local paid env",
            "cleanup or Brev safety failure blocks finalize/policy readiness",
            "KeyboardInterrupt disarms local paid env",
            "writes_recovery_plan",
            "finalize_success_variation_batch.sh",
            "run_v0_offline_policy_readiness_pipeline.py",
            "plan_success_variation_recovery_batch.py",
            "would not create a paid instance",
            "no paid instance was created",
            "disarms the local env",
            "checks Brev safety",
            "cleanup_required",
            "_post_run_cleanup",
            "_execute_lifecycle",
            "except KeyboardInterrupt",
            "[success-variation-lifecycle] INTERRUPTED",
        ):
            if expected_snippet not in lifecycle_script:
                raise AssertionError(f"success variation paid lifecycle missing snippet: {expected_snippet}")
        if "brev create" in lifecycle_script or '"${BREV_BIN}" create' in lifecycle_script:
            raise AssertionError("success variation paid lifecycle must delegate paid creation to the guarded wrapper")

        for expected_snippet in (
            "classify_success_variation_results",
            "scripts/check_phase2_contact_gate.py",
            "./scripts/brev_paid_safety_status.sh",
            "SAFE_NO_VISIBLE_PAID_INSTANCE",
            "RCA_ALLOW_PAID_BREV_CREATE",
            "RCA_BREV_CREDITS_VERIFIED",
            "RCA_ACK_BREV_LIFECYCLE_RISK",
            "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES",
            "RCA_SUCCESS_VARIATION_CASE_CALIBRATION_TIMEOUT_SECONDS",
            "RCA_SUCCESS_VARIATION_CASE_TRACE_TIMEOUT_SECONDS",
            "RCA_SUCCESS_VARIATION_REUSE_CALIBRATION",
            "RCA_PAID_BUDGET_EUR",
            "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
            "RCA_BREV_CREDIT_EVIDENCE_JSON",
            "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES",
            "RCA_PAID_ARMED_AT_UTC",
            "paid arming is too old",
            "check_brev_credit_evidence",
            "RCA_BREV_CREDITS_VERIFIED=1 requires passing current Brev UI credit evidence",
            "Brev instance price search",
            "instance_price",
            "check_success_variation_batch_plan",
            "success variation batch plan is invalid",
            "batch_plan",
            "time_budget",
            "estimated_batch_timeout_seconds",
            "success variation timeout envelope exceeds TTL",
            "selected instance type is not currently visible",
            "live Brev price_per_hour",
            "selected instance type is not stoppable",
            "baseline_replay must remain a strict_success positive control",
            "negative control is already strict_success",
            "estimated max cost",
            "[success-variation-readiness] BLOCKED",
            "[success-variation-readiness] READY",
        ):
            if expected_snippet not in readiness_gate:
                raise AssertionError(f"success variation readiness gate missing snippet: {expected_snippet}")
        if "brev create" in readiness_gate or '"${BREV_BIN}" create' in readiness_gate:
            raise AssertionError("success variation readiness gate must be read-only and must not create Brev instances")

        for expected_snippet in (
            "Validate the generated success-variation batch plan before paid compute",
            "plan_success_variation_batch",
            "does not create, delete, copy to, or execute on Brev instances",
            "RCA_TRACE_ONLY_REMOTE_DIR",
            "RCA_TRACE_VARIATION_CASE_ID",
            "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE",
            "scripts/run_remote_joint_response_socket_insertion_servo_trace.sh",
            "socket_x_pos_25mm_negative_control",
            "negative_control_in_plan",
            "planned_unique_seed_count",
            "[success-variation-plan-gate] PASS",
            "[success-variation-plan-gate] BLOCKED",
        ):
            if expected_snippet not in plan_gate_script:
                raise AssertionError(f"success variation plan gate missing snippet: {expected_snippet}")
        if "brev create" in plan_gate_script or '"${BREV_BIN}" create' in plan_gate_script:
            raise AssertionError("success variation plan gate must not create Brev instances")

        for expected_snippet in (
            "baseline positive control remains strict_success",
            "planned non-negative variations have trace artifacts",
            "at least N non-baseline, non-negative variations are strict_success",
            "the deliberate negative control is fail_closed",
            "strict non-baseline, non-negative variation successes",
            "missing planned trace artifacts",
            "negative_control_classification",
            "[success-variation-result-gate] FAIL",
            "[success-variation-result-gate] PASS",
        ):
            if expected_snippet not in result_gate:
                raise AssertionError(f"success variation result gate missing snippet: {expected_snippet}")
        if "brev create" in result_gate or '"${BREV_BIN}" create' in result_gate:
            raise AssertionError("success variation result gate must be offline and must not create Brev instances")

        for expected_snippet in (
            "partial paid runs",
            "skip cases that already satisfy the promotion contract",
            "NOTHING_TO_RERUN",
            "negative control classified",
            "not a paid-run launcher",
            "[success-variation-recovery] status=",
        ):
            if expected_snippet not in recovery_script:
                raise AssertionError(f"success variation recovery planner missing snippet: {expected_snippet}")
        if "brev create" in recovery_script or '"${BREV_BIN}" create' in recovery_script:
            raise AssertionError("success variation recovery planner must be offline and must not create Brev instances")

        for expected_snippet in (
            "classify_success_variation_results",
            "check_success_variation_batch_results",
            "brev_paid_safety_status.sh",
            "continue_variation_batch_or_debug",
            "ready_for_dataset_policy_preparation",
            "cleanup_required",
            "Do not start learned policy, VLM, ROS, or sim-to-real work yet.",
            "[success-variation-review] decision=",
        ):
            if expected_snippet not in review_script:
                raise AssertionError(f"success variation review script missing snippet: {expected_snippet}")
        if "brev create" in review_script or '"${BREV_BIN}" create' in review_script:
            raise AssertionError("success variation review script must be read-only and must not create Brev instances")

        for expected_snippet in (
            "v0_scripted_skill_success_variations",
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "check_success_variation_batch_results",
            "classify_success_variation_results",
            "result_gate_pass",
            "[success-variation-dataset] facts=",
            "[success-variation-dataset] BLOCKED",
            "[success-variation-dataset] DRY_RUN",
            "writes_dataset_artifacts",
            "READY_FOR_POLICY_API_REVIEW",
        ):
            if expected_snippet not in dataset_script:
                raise AssertionError(f"success variation dataset prep script missing snippet: {expected_snippet}")
        if "brev create" in dataset_script or '"${BREV_BIN}" create' in dataset_script:
            raise AssertionError("success variation dataset prep must be offline and must not create Brev instances")

        for expected_snippet in (
            "review_success_variation_batch.py",
            "check_success_variation_batch_results.py",
            "prepare_success_variation_dataset.py",
            "--fail-on-blocked",
            "RCA_SUCCESS_VARIATION_FINALIZE_SKIP_BREV_SAFETY",
            "--dry-run",
            "[success-variation-finalize] DRY_RUN",
            "[success-variation-finalize] facts=",
            "writes_review_record",
            "writes_result_gate",
            "writes_dataset_artifacts",
            "[success-variation-finalize] BLOCKED",
            "[success-variation-finalize] PASS",
            "does not create or delete Brev instances",
        ):
            if expected_snippet not in finalizer_script:
                raise AssertionError(f"success variation finalizer missing snippet: {expected_snippet}")
        if "brev create" in finalizer_script or '"${BREV_BIN}" create' in finalizer_script:
            raise AssertionError("success variation finalizer must not create Brev instances")

        for expected_snippet in (
            "strict_success",
            "negative_control_fail_closed",
            "planned_variation_coverage",
            "paid_run_budget_and_cleanup",
            "promotion_to_dataset_policy",
            "not learned policy",
            "not sim-to-real",
            "does not create, delete, copy to, or execute on Brev instances",
            "Metric Sources",
            "pre-batch",
            "post-batch",
            "run packet is required for pre-batch paid-run audit",
            "post-batch result gate is not expected to pass before generating planned variation traces",
            "--fail-on-blocked",
        ):
            if expected_snippet not in audit_script:
                raise AssertionError(f"success variation assumption audit missing snippet: {expected_snippet}")
        if "brev create" in audit_script or '"${BREV_BIN}" create' in audit_script:
            raise AssertionError("success variation assumption audit must be read-only and must not create Brev instances")

        fake_readiness_output = tmp_dir / "fake_readiness_output.txt"
        fake_readiness_output.write_text(
            "\n".join(
                [
                    '[success-variation-readiness] facts={',
                    '  "brev_safety_status": "SAFE_NO_VISIBLE_PAID_INSTANCE",',
                    '  "phase2_contact_gate": "PASS",',
                    '  "ttl_minutes": 75,',
                    '  "budget_eur": 6.0,',
                    '  "estimated_eur_per_hour": 4.5,',
                    '  "estimated_max_cost_eur": 5.625,',
                    '  "instance_price": {"type": "g6e.xlarge", "price_per_hour": 2.2332},',
                    '  "time_budget": {"estimated_batch_timeout_seconds": 4500, "ttl_seconds": 4500}',
                    '}',
                    "[success-variation-readiness] BLOCKED",
                    "- set RCA_ALLOW_PAID_BREV_CREATE=1 only for the deliberate paid batch run",
                    "- set RCA_BREV_CREDITS_VERIFIED=1 only after the current Brev UI/org credit balance covers this budget",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        run_packet_json = tmp_dir / "run_packet.json"
        run_packet_md = tmp_dir / "run_packet.md"
        result = run(
            [
                "python3",
                "scripts/write_success_variation_run_packet.py",
                "--config",
                "configs/success_variation_batch_run.env.example",
                "--manifest",
                str(manifest_path),
                "--readiness-output",
                str(fake_readiness_output),
                "--output-json",
                str(run_packet_json),
                "--output-md",
                str(run_packet_md),
            ]
        )
        assert_status(result, 0, "success variation run packet writes from saved readiness output")
        assert_contains(result, "status=BLOCKED", "run packet blocked status detail")
        run_packet = json.loads(run_packet_json.read_text(encoding="utf-8"))
        if run_packet["readiness"]["status"] != "BLOCKED":
            raise AssertionError(f"run packet should preserve BLOCKED status: {run_packet['readiness']}")
        if "RCA_BREV_CREDITS_VERIFIED=0" not in run_packet["one_run_local_env_template"]:
            raise AssertionError("run packet template must keep credit acknowledgement fail-closed")
        if "finalize_success_variation_batch.sh" not in run_packet["commands"]["finalize"]:
            raise AssertionError(f"run packet should include finalizer command: {run_packet['commands']}")
        if "check_success_variation_batch_plan.py" not in run_packet["commands"]["plan_gate"]:
            raise AssertionError(f"run packet should include plan gate command: {run_packet['commands']}")
        if "audit_success_variation_assumptions.py" not in run_packet["commands"]["pre_batch_audit"]:
            raise AssertionError(f"run packet should include pre-batch audit command: {run_packet['commands']}")
        run_packet_md_text = run_packet_md.read_text(encoding="utf-8")
        if "Current Blockers" not in run_packet_md_text or "Brev UI/org credit balance" not in run_packet_md_text:
            raise AssertionError("run packet markdown should include blocker details")
        if "time_budget_seconds: 4500 / 4500" not in run_packet_md_text:
            raise AssertionError("run packet markdown should include the success-variation time budget")

        post_batch_audit_json = tmp_dir / "post_batch_assumption_audit.json"
        post_batch_audit_md = tmp_dir / "post_batch_assumption_audit.md"
        result = run(
            [
                "python3",
                "scripts/audit_success_variation_assumptions.py",
                str(manifest_path),
                "--run-packet",
                str(run_packet_json),
                "--output-json",
                str(post_batch_audit_json),
                "--output-md",
                str(post_batch_audit_md),
            ]
        )
        assert_status(result, 0, "post-batch assumption audit writes blocked report")
        assert_contains(result, "status=BLOCKED", "post-batch assumption audit blocked status detail")
        post_batch_audit = json.loads(post_batch_audit_json.read_text(encoding="utf-8"))
        if post_batch_audit["phase"] != "post-batch" or post_batch_audit["audit_status"] != "BLOCKED":
            raise AssertionError(f"post-batch audit should be blocked: {post_batch_audit}")
        if post_batch_audit["source_trace"]["status"] != "pass":
            raise AssertionError(
                f"post-batch audit should verify source trace checksum: {post_batch_audit['source_trace']}"
            )
        post_batch_blockers = "\n".join(post_batch_audit["blockers"])
        if "missing planned trace artifacts" not in post_batch_blockers:
            raise AssertionError(
                f"post-batch audit should include missing planned artifacts: {post_batch_audit['blockers']}"
            )
        metric_names = {item["metric"] for item in post_batch_audit["metric_sources"]}
        expected_metrics = {
            "strict_success",
            "negative_control_fail_closed",
            "planned_variation_coverage",
            "paid_run_budget_and_cleanup",
            "promotion_to_dataset_policy",
        }
        if metric_names != expected_metrics:
            raise AssertionError(f"assumption audit metric set changed: {metric_names}")
        post_batch_md_text = post_batch_audit_md.read_text(encoding="utf-8")
        if "Metric Sources" not in post_batch_md_text or "not sim-to-real" not in post_batch_md_text:
            raise AssertionError("post-batch audit markdown should include sources and non-claims")
        result = run(
            [
                "python3",
                "scripts/audit_success_variation_assumptions.py",
                str(manifest_path),
                "--run-packet",
                str(run_packet_json),
                "--output-json",
                str(tmp_dir / "assumption_audit_fail.json"),
                "--output-md",
                str(tmp_dir / "assumption_audit_fail.md"),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "post-batch assumption audit fail-on-blocked rejects incomplete batch")

        no_output_json = tmp_dir / "assumption_audit_no_output.json"
        no_output_md = tmp_dir / "assumption_audit_no_output.md"
        result = run(
            [
                "python3",
                "scripts/audit_success_variation_assumptions.py",
                str(manifest_path),
                "--run-packet",
                str(run_packet_json),
                "--output-json",
                str(no_output_json),
                "--output-md",
                str(no_output_md),
                "--no-output",
            ]
        )
        assert_status(result, 0, "assumption audit no-output remains a read-only report")
        assert_contains(result, "[success-variation-assumption-audit] facts=", "assumption audit no-output facts")
        if no_output_json.exists() or no_output_md.exists():
            raise AssertionError("assumption audit --no-output must not write JSON/Markdown artifacts")

        pre_batch_blocked_json = tmp_dir / "pre_batch_assumption_audit_blocked.json"
        pre_batch_blocked_md = tmp_dir / "pre_batch_assumption_audit_blocked.md"
        result = run(
            [
                "python3",
                "scripts/audit_success_variation_assumptions.py",
                str(manifest_path),
                "--phase",
                "pre-batch",
                "--run-packet",
                str(run_packet_json),
                "--output-json",
                str(pre_batch_blocked_json),
                "--output-md",
                str(pre_batch_blocked_md),
            ]
        )
        assert_status(result, 0, "pre-batch assumption audit writes blocked report")
        pre_batch_blocked = json.loads(pre_batch_blocked_json.read_text(encoding="utf-8"))
        if pre_batch_blocked["phase"] != "pre-batch" or pre_batch_blocked["audit_status"] != "BLOCKED":
            raise AssertionError(f"pre-batch audit should block on paid readiness: {pre_batch_blocked}")
        pre_batch_blockers = "\n".join(pre_batch_blocked["blockers"])
        if "RCA_BREV_CREDITS_VERIFIED" not in pre_batch_blockers:
            raise AssertionError(f"pre-batch audit should include paid-run credit blocker: {pre_batch_blocked['blockers']}")
        if "missing planned trace artifacts" in pre_batch_blockers:
            raise AssertionError(f"pre-batch audit must not block on planned traces it is about to run: {pre_batch_blockers}")

        ready_run_packet = json.loads(run_packet_json.read_text(encoding="utf-8"))
        ready_run_packet["readiness"]["status"] = "READY"
        ready_run_packet["readiness"]["blockers"] = []
        ready_run_packet_json = tmp_dir / "run_packet_ready.json"
        ready_run_packet_json.write_text(json.dumps(ready_run_packet), encoding="utf-8")
        pre_batch_ready_json = tmp_dir / "pre_batch_assumption_audit_ready.json"
        pre_batch_ready_md = tmp_dir / "pre_batch_assumption_audit_ready.md"
        result = run(
            [
                "python3",
                "scripts/audit_success_variation_assumptions.py",
                str(manifest_path),
                "--phase",
                "pre-batch",
                "--run-packet",
                str(ready_run_packet_json),
                "--output-json",
                str(pre_batch_ready_json),
                "--output-md",
                str(pre_batch_ready_md),
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 0, "pre-batch assumption audit allows ready packet with missing planned traces")
        pre_batch_ready = json.loads(pre_batch_ready_json.read_text(encoding="utf-8"))
        if pre_batch_ready["audit_status"] != "PASS":
            raise AssertionError(f"pre-batch ready audit should pass before generating traces: {pre_batch_ready}")
        if pre_batch_ready["classification_summary"]["missing_count"] < 1:
            raise AssertionError(f"pre-batch audit should preserve missing planned count: {pre_batch_ready}")
        if not pre_batch_ready["warnings"]:
            raise AssertionError("pre-batch ready audit should warn that post-batch promotion is not proven yet")

        for expected_snippet in (
            "check_success_variation_batch_readiness.py",
            "check_success_variation_batch_plan.py",
            "run_success_variation_batch_from_config.sh",
            "finalize_success_variation_batch.sh",
            "write_brev_credit_evidence.py",
            "prepare_success_variation_paid_batch.py",
            "arm_success_variation_paid_env.py",
            "--disarm",
            "audit_success_variation_assumptions.py",
            "--phase pre-batch",
            "RCA_BREV_CREDITS_VERIFIED",
            "Brev UI credit evidence JSON",
            "does not create or delete Brev instances",
            "--readiness-output",
            "Current Blockers",
            "time_budget_seconds",
        ):
            if expected_snippet not in run_packet_script:
                raise AssertionError(f"success variation run packet script missing snippet: {expected_snippet}")
        if "brev create" in run_packet_script or '"${BREV_BIN}" create' in run_packet_script:
            raise AssertionError("success variation run packet must not create Brev instances")

        for expected_snippet in (
            "Arm the ignored success-variation local env for one paid batch",
            "SAFE_NO_VISIBLE_PAID_INSTANCE",
            "RCA_ALLOW_PAID_BREV_CREATE",
            "RCA_BREV_CREDITS_VERIFIED",
            "RCA_ACK_BREV_LIFECYCLE_RISK",
            "RCA_PAID_ARMED_AT_UTC",
            "current_arming",
            "existing paid arming is too old",
            "RCA_SUCCESS_VARIATION_CASE_CALIBRATION_TIMEOUT_SECONDS",
            "RCA_SUCCESS_VARIATION_CASE_TRACE_TIMEOUT_SECONDS",
            "RCA_SUCCESS_VARIATION_REUSE_CALIBRATION",
            "--disarm",
            "--i-understand-this-arms-paid-run",
            "--brev-safety-output",
            "does not create, start, stop, delete, copy to, or execute on Brev instances",
        ):
            if expected_snippet not in arm_env_script:
                raise AssertionError(f"success variation arm helper missing snippet: {expected_snippet}")
        if "brev create" in arm_env_script or '"${BREV_BIN}" create' in arm_env_script:
            raise AssertionError("success variation arm helper must not create Brev instances")

        written_credit_path = tmp_dir / "written_brev_credit.local.json"
        result = run(
            [
                "python3",
                "scripts/write_brev_credit_evidence.py",
                "--balance-eur",
                "20.00",
                "--budget-eur",
                "6.00",
                "--output",
                str(written_credit_path),
            ]
        )
        assert_status(result, 0, "Brev credit evidence writer writes sufficient UI evidence")
        assert_contains(result, "[brev-credit-evidence-write] PASS", "Brev credit evidence writer PASS detail")
        written_credit = json.loads(written_credit_path.read_text(encoding="utf-8"))
        if written_credit["organization_id"] != "org-3BaYGdtoRGmgc77Z7NHHhPSD254":
            raise AssertionError(f"credit writer used wrong org: {written_credit}")
        if written_credit["balance_eur"] != 20.0 or written_credit["budget_eur"] != 6.0:
            raise AssertionError(f"credit writer wrote wrong amounts: {written_credit}")
        result = run(
            [
                "python3",
                "scripts/write_brev_credit_evidence.py",
                "--balance-eur",
                "20.00",
                "--budget-eur",
                "6.00",
                "--output",
                str(written_credit_path),
            ]
        )
        assert_status(result, 2, "Brev credit evidence writer refuses overwrite without force")
        assert_contains(result, "use --force", "Brev credit evidence writer overwrite detail")
        low_written_credit_path = tmp_dir / "low_written_brev_credit.local.json"
        result = run(
            [
                "python3",
                "scripts/write_brev_credit_evidence.py",
                "--balance-eur",
                "1.00",
                "--budget-eur",
                "6.00",
                "--output",
                str(low_written_credit_path),
            ]
        )
        assert_status(result, 1, "Brev credit evidence writer refuses insufficient balance")
        assert_contains(result, "below budget", "Brev credit evidence writer insufficient balance detail")
        if low_written_credit_path.exists():
            raise AssertionError("credit writer must not write insufficient-balance evidence")

        credit_evidence_path = tmp_dir / "brev_credit_verification.local.json"
        fresh_credit_evidence = {
            "evidence_name": "brev_credit_balance_verification",
            "verified_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Brev UI organization credits page",
            "organization_name": "NCA-57cf-29515",
            "organization_id": "org-3BaYGdtoRGmgc77Z7NHHhPSD254",
            "balance_eur": 20.0,
            "budget_eur": 6.0,
            "checked_instance_type": "g6e.xlarge",
            "checked_by": "test",
        }
        credit_evidence_path.write_text(json.dumps(fresh_credit_evidence), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/check_brev_credit_evidence.py",
                "--evidence",
                str(credit_evidence_path),
                "--required-budget-eur",
                "6.0",
                "--max-age-minutes",
                "60",
            ]
        )
        assert_status(result, 0, "Brev credit evidence checker accepts fresh sufficient UI evidence")
        assert_contains(result, "[brev-credit-evidence] PASS", "fresh Brev credit evidence detail")

        low_credit_evidence = dict(fresh_credit_evidence)
        low_credit_evidence["balance_eur"] = 1.0
        low_credit_path = tmp_dir / "brev_credit_low.local.json"
        low_credit_path.write_text(json.dumps(low_credit_evidence), encoding="utf-8")
        result = run(
            [
                "python3",
                "scripts/check_brev_credit_evidence.py",
                "--evidence",
                str(low_credit_path),
                "--required-budget-eur",
                "6.0",
                "--fail-on-blocked",
            ]
        )
        assert_status(result, 1, "Brev credit evidence checker rejects insufficient balance")
        assert_contains(result, "below required budget", "insufficient Brev credit evidence detail")

        local_env_path = tmp_dir / "success_variation_batch_run.local.env"
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_local_env.py",
                "--packet",
                str(run_packet_json),
                "--output",
                str(local_env_path),
            ]
        )
        assert_status(result, 0, "success variation local env generator writes fail-closed env")
        assert_contains(result, "acknowledgements remain fail-closed", "local env fail-closed detail")
        local_env_text = local_env_path.read_text(encoding="utf-8")
        for expected_snippet in (
            "RCA_ALLOW_PAID_BREV_CREATE=0",
            "RCA_BREV_CREDITS_VERIFIED=0",
            "RCA_ACK_BREV_LIFECYCLE_RISK=0",
            "RCA_SUCCESS_VARIATION_AUTO_DISARM=1",
            "RCA_PAID_ARMED_AT_UTC=",
            "RCA_PAID_ARMING_MAX_AGE_MINUTES=15",
        ):
            if expected_snippet not in local_env_text:
                raise AssertionError(f"local env generator missing fail-closed marker: {expected_snippet}")
        for forbidden_snippet in (
            "RCA_ALLOW_PAID_BREV_CREATE=1",
            "RCA_BREV_CREDITS_VERIFIED=1",
            "RCA_ACK_BREV_LIFECYCLE_RISK=1",
        ):
            if forbidden_snippet in local_env_text:
                raise AssertionError(f"local env generator must not grant acknowledgement: {forbidden_snippet}")
        armable_env_text = local_env_text.replace(
            "RCA_BREV_CREDIT_EVIDENCE_JSON=configs/brev_credit_verification.local.json",
            f"RCA_BREV_CREDIT_EVIDENCE_JSON={credit_evidence_path}",
        )
        local_env_path.write_text(armable_env_text, encoding="utf-8")
        fake_brev_safety = tmp_dir / "brev_safety_safe.txt"
        fake_brev_safety.write_text("[brev-safety] status=SAFE_NO_VISIBLE_PAID_INSTANCE\n", encoding="utf-8")
        armed_env_path = tmp_dir / "success_variation_batch_run.armed.env"
        result = run(
            [
                "python3",
                "scripts/arm_success_variation_paid_env.py",
                "--config",
                str(local_env_path),
                "--output",
                str(armed_env_path),
                "--brev-safety-output",
                str(fake_brev_safety),
            ]
        )
        assert_status(result, 1, "success variation arm helper requires explicit paid-run flag")
        assert_contains(result, "--i-understand-this-arms-paid-run", "arm helper explicit flag detail")
        if armed_env_path.exists():
            raise AssertionError("arm helper must not write without explicit paid-run flag")
        result = run(
            [
                "python3",
                "scripts/arm_success_variation_paid_env.py",
                "--config",
                str(local_env_path),
                "--output",
                str(armed_env_path),
                "--brev-safety-output",
                str(fake_brev_safety),
                "--i-understand-this-arms-paid-run",
                "--dry-run",
            ]
        )
        assert_status(result, 0, "success variation arm helper dry-run accepts passing evidence")
        assert_contains(result, "DRY_RUN_READY", "arm helper dry-run detail")
        if armed_env_path.exists():
            raise AssertionError("arm helper dry-run must not write armed env")
        result = run(
            [
                "python3",
                "scripts/arm_success_variation_paid_env.py",
                "--config",
                str(local_env_path),
                "--output",
                str(armed_env_path),
                "--brev-safety-output",
                str(fake_brev_safety),
                "--i-understand-this-arms-paid-run",
            ]
        )
        assert_status(result, 0, "success variation arm helper writes armed env after checked evidence")
        assert_contains(result, "wrote armed env", "arm helper write detail")
        armed_env_text = armed_env_path.read_text(encoding="utf-8")
        for expected_snippet in (
            "RCA_ALLOW_PAID_BREV_CREATE=1",
            "RCA_BREV_CREDITS_VERIFIED=1",
            "RCA_ACK_BREV_LIFECYCLE_RISK=1",
        ):
            if expected_snippet not in armed_env_text:
                raise AssertionError(f"armed env missing acknowledgement: {expected_snippet}")
        if "RCA_PAID_ARMED_AT_UTC=" not in armed_env_text or "RCA_PAID_ARMING_MAX_AGE_MINUTES=15" not in armed_env_text:
            raise AssertionError(f"armed env missing arming timestamp or max age: {armed_env_text}")
        result = run(
            [
                "python3",
                "scripts/arm_success_variation_paid_env.py",
                "--config",
                str(armed_env_path),
                "--output",
                str(armed_env_path),
                "--disarm",
            ]
        )
        assert_status(result, 0, "success variation arm helper can disarm env")
        assert_contains(result, "disarmed env", "arm helper disarm detail")
        disarmed_env_text = armed_env_path.read_text(encoding="utf-8")
        for expected_snippet in (
            "RCA_ALLOW_PAID_BREV_CREATE=0",
            "RCA_BREV_CREDITS_VERIFIED=0",
            "RCA_ACK_BREV_LIFECYCLE_RISK=0",
            "RCA_PAID_ARMED_AT_UTC=",
        ):
            if expected_snippet not in disarmed_env_text:
                raise AssertionError(f"disarmed env missing fail-closed marker: {expected_snippet}")
        result = run(
            [
                "python3",
                "scripts/prepare_success_variation_local_env.py",
                "--packet",
                str(run_packet_json),
                "--output",
                str(local_env_path),
            ]
        )
        assert_status(result, 2, "success variation local env generator refuses overwrite")
        assert_contains(result, "use --force", "local env overwrite guidance")

        for expected_snippet in (
            "success_variation_batch_run.local.env",
            "RCA_ALLOW_PAID_BREV_CREATE=0",
            "RCA_BREV_CREDITS_VERIFIED=0",
            "RCA_ACK_BREV_LIFECYCLE_RISK=0",
            "does not create, delete, copy to, or execute on Brev instances",
            "use --force",
        ):
            if expected_snippet not in local_env_script:
                raise AssertionError(f"success variation local env generator missing snippet: {expected_snippet}")
        if "brev create" in local_env_script or '"${BREV_BIN}" create' in local_env_script:
            raise AssertionError("success variation local env generator must not create Brev instances")


def write_action_response_trace(
    path: Path,
    *,
    command_delta: tuple[float, float, float],
    actual_delta: tuple[float, float, float],
) -> None:
    action_pos = (0.30, -0.01, 0.80)
    command_pos = tuple(action_pos[i] + command_delta[i] for i in range(3))
    post_action_pos = tuple(action_pos[i] + actual_delta[i] for i in range(3))
    path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "step": 0,
                        "phase": "synthetic-action-response",
                        "action_pos_w": list(action_pos),
                        "command_pos_w": list(command_pos),
                        "post_action_pos_w": list(post_action_pos),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def write_mixed_micro_action_response_trace(path: Path) -> None:
    action_pos = (0.30, -0.01, 0.80)
    rows = []
    for step, command_delta, actual_delta in [
        (0, (0.0, 0.0, -0.0020), (0.0, 0.0, -0.0015)),
        (1, (0.0, 0.0, -0.00015), (0.0, 0.0, 0.00012)),
    ]:
        rows.append(
            {
                "step": step,
                "phase": "synthetic-action-response",
                "action_pos_w": list(action_pos),
                "command_pos_w": [action_pos[i] + command_delta[i] for i in range(3)],
                "post_action_pos_w": [action_pos[i] + actual_delta[i] for i in range(3)],
            }
        )
    path.write_text(json.dumps({"steps": rows}), encoding="utf-8")


def write_post_success_contact_action_response_trace(path: Path) -> None:
    action_pos = (0.30, -0.01, 0.80)
    rows = []
    for step, success, command_delta, actual_delta in [
        (0, False, (0.0, 0.0, -0.0020), (0.0, 0.0, -0.0015)),
        (1, True, (0.0, 0.0, -0.0010), (0.0, 0.0, -0.0008)),
        (2, True, (0.0, -0.0004, 0.0001), (0.0, 0.00008, -0.00002)),
    ]:
        rows.append(
            {
                "step": step,
                "phase": "synthetic-contact-response",
                "success": success,
                "action_pos_w": list(action_pos),
                "command_pos_w": [action_pos[i] + command_delta[i] for i in range(3)],
                "post_action_pos_w": [action_pos[i] + actual_delta[i] for i in range(3)],
            }
        )
    path.write_text(json.dumps({"steps": rows}), encoding="utf-8")


def write_action_calibration_summary(path: Path, *, z_maps_to_x: bool) -> None:
    action_magnitude = 0.10
    columns = {
        "x": (0.030, 0.002, 0.001),
        "y": (0.001, 0.028, -0.001),
        "z": (0.026, 0.001, 0.006) if z_maps_to_x else (0.001, -0.001, 0.030),
    }
    probes = {
        "zero": {"delta_action_pos": [0.0, 0.0, 0.0]},
    }
    for axis, column in columns.items():
        delta = tuple(action_magnitude * value for value in column)
        probes[f"{axis}_pos"] = {
            "action_xyz": [
                action_magnitude if axis == "x" else 0.0,
                action_magnitude if axis == "y" else 0.0,
                action_magnitude if axis == "z" else 0.0,
            ],
            "delta_action_pos": list(delta),
        }
        probes[f"{axis}_neg"] = {
            "action_xyz": [
                -action_magnitude if axis == "x" else 0.0,
                -action_magnitude if axis == "y" else 0.0,
                -action_magnitude if axis == "z" else 0.0,
            ],
            "delta_action_pos": [-value for value in delta],
        }
    path.write_text(
        json.dumps(
            {
                "task": "synthetic-action-calibration",
                "action_magnitude": action_magnitude,
                "probes": probes,
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    run_socket_insertion_servo_logic_tests()
    run_final_contact_boundary_diagnostic_tests()
    run_joint_response_control_tests()
    run_scripted_agent_quaternion_static_tests()
    run_isaac_launcher_import_order_static_tests()
    run_joint_response_socket_wrapper_static_tests()
    run_trace_only_runtime_profile_static_tests()
    run_video_candidate_xvfb_static_tests()
    run_video_candidate_screen_recording_static_tests()
    run_isaac_trace_replay_video_static_tests()
    run_trace_video_renderer_static_tests()
    run_trace_frame_alignment_tests()
    run_success_deliverable_bundle_tests()
    run_v0_skill_api_contract_tests()
    run_success_variation_manifest_tests()

    with tempfile.TemporaryDirectory(prefix="rca-gate-tests-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        launchable_bundle_dir = tmp_dir / "launchable"
        fake_brev = tmp_dir / "fake-brev"
        fake_rsync = tmp_dir / "fake-rsync"
        fake_isaac = tmp_dir / "fake-isaac-python"
        fake_launchable_repo = tmp_dir / "fake-launchable-repo"
        write_fake_brev(fake_brev)
        write_fake_rsync(fake_rsync)
        write_fake_isaac_python(fake_isaac)
        write_fake_launchable_repo(fake_launchable_repo)

        good_video_trace = tmp_dir / "good-video-trace.json"
        lip_contact_trace = tmp_dir / "lip-contact-trace.json"
        write_video_candidate_trace(good_video_trace, final_lateral=0.0010)
        write_video_candidate_trace(lip_contact_trace, final_lateral=0.0040)
        result = run(
            [
                "python3",
                "scripts/check_peg_in_hole_video_candidate.py",
                str(good_video_trace),
                "--sustained-steps",
                "3",
            ]
        )
        assert_status(result, 0, "peg video candidate accepts strict successful trace")
        assert_contains(result, "video_candidate_pass=True", "strict successful trace detail")
        result = run(
            [
                "python3",
                "scripts/check_peg_in_hole_video_candidate.py",
                str(lip_contact_trace),
                "--sustained-steps",
                "3",
            ]
        )
        assert_status(result, 1, "peg video candidate rejects lip-contact trace")
        assert_contains(
            result,
            "pose never reached stricter guide-clearance lateral tolerance",
            "lip-contact rejection detail",
        )

        good_action_response_trace = tmp_dir / "good-action-response-trace.json"
        reversed_action_response_trace = tmp_dir / "reversed-action-response-trace.json"
        mixed_micro_action_response_trace = tmp_dir / "mixed-micro-action-response-trace.json"
        post_success_contact_action_response_trace = (
            tmp_dir / "post-success-contact-action-response-trace.json"
        )
        write_action_response_trace(
            good_action_response_trace,
            command_delta=(0.0, 0.0, -0.0020),
            actual_delta=(0.0, 0.0, -0.0015),
        )
        write_action_response_trace(
            reversed_action_response_trace,
            command_delta=(0.0, 0.0, -0.0020),
            actual_delta=(0.0, 0.0, 0.0015),
        )
        write_mixed_micro_action_response_trace(mixed_micro_action_response_trace)
        write_post_success_contact_action_response_trace(
            post_success_contact_action_response_trace
        )
        result = run(
            [
                "python3",
                "scripts/check_scripted_action_response_trace.py",
                str(good_action_response_trace),
            ]
        )
        assert_status(result, 0, "action-response checker accepts aligned motion")
        assert_contains(result, "[action-response] PASS", "aligned action-response detail")
        result = run(
            [
                "python3",
                "scripts/check_scripted_action_response_trace.py",
                str(reversed_action_response_trace),
            ]
        )
        assert_status(result, 1, "action-response checker rejects reversed motion")
        assert_contains(result, '"bad_fraction": 1.0', "reversed action-response detail")
        result = run(
            [
                "python3",
                "scripts/check_scripted_action_response_trace.py",
                str(mixed_micro_action_response_trace),
                "--min-command-norm",
                "0.0002",
            ]
        )
        assert_status(result, 0, "action-response checker can skip contact micro-bounce rows")
        assert_contains(result, '"steps_assessed": 1', "micro-bounce skip detail")
        result = run(
            [
                "python3",
                "scripts/check_scripted_action_response_trace.py",
                str(post_success_contact_action_response_trace),
            ]
        )
        assert_status(result, 1, "action-response checker rejects post-success reverse by default")
        result = run(
            [
                "python3",
                "scripts/check_scripted_action_response_trace.py",
                str(post_success_contact_action_response_trace),
                "--stop-after-first-success",
            ]
        )
        assert_status(result, 0, "action-response checker can stop at first contact success")
        assert_contains(result, '"first_success_step": 1', "first-success stop detail")

        good_action_calibration = tmp_dir / "good-action-calibration.json"
        bad_action_calibration = tmp_dir / "bad-action-calibration.json"
        write_action_calibration_summary(good_action_calibration, z_maps_to_x=False)
        write_action_calibration_summary(bad_action_calibration, z_maps_to_x=True)
        result = run(
            [
                "python3",
                "scripts/check_action_calibration_summary.py",
                str(good_action_calibration),
            ]
        )
        assert_status(result, 0, "action calibration checker accepts axis-aligned response")
        assert_contains(result, "[action-calibration-check] PASS", "axis-aligned calibration detail")
        result = run(
            [
                "python3",
                "scripts/check_action_calibration_summary.py",
                str(bad_action_calibration),
            ]
        )
        assert_status(result, 1, "action calibration checker rejects wrong dominant axis")
        assert_contains(
            result,
            "z raw action dominantly moves world x",
            "wrong-dominant-axis calibration detail",
        )

        fingerprint_root = tmp_dir / "fingerprint-root"
        (fingerprint_root / "source" / "robot_contact_assembly_tasks").mkdir(parents=True)
        (fingerprint_root / "scripts").mkdir()
        (fingerprint_root / "source" / "robot_contact_assembly_tasks" / "runtime.py").write_text(
            "runtime-v1\n",
            encoding="utf-8",
        )
        (fingerprint_root / "scripts" / "contact_physics_smoke.py").write_text(
            "smoke-v1\n",
            encoding="utf-8",
        )
        (fingerprint_root / "scripts" / "run_launchable_contact_physics_smoke.sh").write_text(
            "wrapper-v1\n",
            encoding="utf-8",
        )
        (fingerprint_root / "README.md").write_text("docs-v1\n", encoding="utf-8")
        fingerprint_a = fingerprint_for(fingerprint_root)
        (fingerprint_root / "README.md").write_text("docs-v2\n", encoding="utf-8")
        fingerprint_b = fingerprint_for(fingerprint_root)
        if fingerprint_b != fingerprint_a:
            print("[gate-tests] FAIL runtime fingerprint changed after documentation-only edit", file=sys.stderr)
            raise SystemExit(1)
        (fingerprint_root / "source" / "robot_contact_assembly_tasks" / "runtime.py").write_text(
            "runtime-v2\n",
            encoding="utf-8",
        )
        fingerprint_c = fingerprint_for(fingerprint_root)
        if fingerprint_c == fingerprint_a:
            print("[gate-tests] FAIL runtime fingerprint did not change after runtime source edit", file=sys.stderr)
            raise SystemExit(1)

        pass_log = tmp_dir / "contact_pass.log"
        fail_log = tmp_dir / "contact_fail.log"
        incomplete_log = tmp_dir / "contact_incomplete.log"
        unknown_source_log = tmp_dir / "contact_unknown_source.log"
        manifest_source_log = tmp_dir / "contact_manifest_source.log"
        stale_head_matching_payload_log = tmp_dir / "contact_stale_head_matching_payload.log"
        stale_source_log = tmp_dir / "contact_stale_source.log"
        missing_payload_log = tmp_dir / "contact_missing_payload.log"
        missing_payload_scope_log = tmp_dir / "contact_missing_payload_scope.log"
        stale_payload_scope_log = tmp_dir / "contact_stale_payload_scope.log"
        stale_payload_log = tmp_dir / "contact_stale_payload.log"
        write_contact_log(pass_log, include_source_manifest=True)
        write_contact_log(fail_log, fail_marker=True)
        write_contact_log(incomplete_log, omit_release=True)
        write_contact_log(unknown_source_log, unknown_git_head=True)
        write_contact_log(manifest_source_log, unknown_git_head=True, include_source_manifest=True)
        write_contact_log(
            missing_payload_log,
            unknown_git_head=True,
            include_source_manifest=True,
            omit_payload_sha256=True,
        )
        write_contact_log(
            missing_payload_scope_log,
            unknown_git_head=True,
            include_source_manifest=True,
            omit_payload_scope=True,
        )
        write_contact_log(
            stale_payload_scope_log,
            unknown_git_head=True,
            include_source_manifest=True,
            payload_scope="runtime-v0",
        )
        write_contact_log(
            stale_head_matching_payload_log,
            unknown_git_head=True,
            include_source_manifest=True,
            git_head="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        )
        write_contact_log(stale_source_log, git_head="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        write_contact_log(
            stale_payload_log,
            include_source_manifest=True,
            payload_sha256="0" * 64,
        )

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(pass_log)])
        assert_status(result, 0, "contact gate accepts complete PASS log")
        assert_contains(result, "PASS: validated", "contact gate PASS output")

        archived_log = tmp_dir / "canonical-artifacts" / "launchable_logs" / "contact_physics_smoke.log"
        result = run(["scripts/archive_contact_smoke_log.sh", str(pass_log), str(archived_log)])
        assert_status(result, 0, "contact smoke archive accepts complete PASS log")
        assert_contains(result, "canonical contact-smoke evidence is archived and valid", "contact archive PASS detail")
        if not archived_log.is_file():
            print("[gate-tests] FAIL contact smoke archive did not write canonical log", file=sys.stderr)
            raise SystemExit(1)
        if archived_log.read_text(encoding="utf-8") != pass_log.read_text(encoding="utf-8"):
            print("[gate-tests] FAIL contact smoke archive changed log content", file=sys.stderr)
            raise SystemExit(1)

        preserved_log = tmp_dir / "canonical-artifacts" / "launchable_logs" / "preserved_contact_smoke.log"
        preserved_log.write_text("keep-existing-log\n", encoding="utf-8")
        result = run(["scripts/archive_contact_smoke_log.sh", str(fail_log), str(preserved_log)])
        assert_status(result, 2, "contact smoke archive rejects FAIL log before overwrite")
        assert_contains(result, "FAIL marker present", "contact archive invalid-source detail")
        if preserved_log.read_text(encoding="utf-8") != "keep-existing-log\n":
            print("[gate-tests] FAIL contact smoke archive overwrote destination with invalid log", file=sys.stderr)
            raise SystemExit(1)

        pulled_archived_log = tmp_dir / "pulled-artifacts" / "launchable_logs" / "contact_physics_smoke.log"
        result = run(
            [
                "scripts/pull_contact_smoke_log.sh",
                "fake-env",
                "/workspace/robot-contact-assembly",
                str(tmp_dir / "pulled-contact-smoke-stage"),
            ],
            env={
                "RCA_RSYNC_BIN": str(fake_rsync),
                "FAKE_RSYNC_SOURCE": str(pass_log),
                "RCA_CONTACT_SMOKE_ARCHIVE_PATH": str(pulled_archived_log),
            },
        )
        assert_status(result, 0, "contact smoke pull archives complete PASS log")
        assert_contains(result, "contact_physics_smoke_fake-env_", "contact smoke pull names staged log")
        assert_contains(result, "pulled, archived, and validated", "contact smoke pull PASS detail")
        if not pulled_archived_log.is_file():
            print("[gate-tests] FAIL contact smoke pull did not archive canonical log", file=sys.stderr)
            raise SystemExit(1)
        if pulled_archived_log.read_text(encoding="utf-8") != pass_log.read_text(encoding="utf-8"):
            print("[gate-tests] FAIL contact smoke pull changed log content", file=sys.stderr)
            raise SystemExit(1)

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(fail_log)])
        assert_status(result, 2, "contact gate rejects FAIL marker")
        assert_contains(result, "FAIL marker present", "contact gate FAIL marker detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(incomplete_log)])
        assert_status(result, 2, "contact gate rejects incomplete PASS log")
        assert_contains(result, "missing required marker", "contact gate missing marker detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(unknown_source_log)])
        assert_status(result, 2, "contact gate rejects unknown source log")
        assert_contains(result, "missing source evidence", "contact gate source evidence detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(manifest_source_log)])
        assert_status(result, 0, "contact gate accepts bundle source manifest evidence")
        assert_contains(result, "PASS: validated", "contact gate manifest-source PASS output")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(stale_head_matching_payload_log)])
        assert_status(result, 0, "contact gate accepts stale HEAD when runtime payload matches")
        assert_contains(result, "PASS: validated", "contact gate stale-HEAD matching-payload PASS output")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(stale_source_log)])
        assert_status(result, 2, "contact gate rejects stale source HEAD")
        assert_contains(result, "source HEAD mismatch", "contact gate stale source detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(missing_payload_log)])
        assert_status(result, 2, "contact gate rejects missing source payload fingerprint")
        assert_contains(result, "missing source payload fingerprint", "contact gate missing payload detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(missing_payload_scope_log)])
        assert_status(result, 2, "contact gate rejects missing source payload scope")
        assert_contains(result, "missing or unsupported source payload scope", "contact gate missing payload scope detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(stale_payload_scope_log)])
        assert_status(result, 2, "contact gate rejects stale source payload scope")
        assert_contains(result, "missing or unsupported source payload scope", "contact gate stale payload scope detail")

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(stale_payload_log)])
        assert_status(result, 2, "contact gate rejects stale source payload fingerprint")
        assert_contains(result, "source payload mismatch", "contact gate stale payload detail")

        result = run(
            ["scripts/run_launchable_headless_smoke.sh"],
            env={
                "RCA_LAUNCHABLE_REPO_DIR": str(fake_launchable_repo),
                "RCA_LAUNCHABLE_ARTIFACT_ROOT": str(tmp_dir / "blocked-launchable-artifacts"),
                "RCA_ISAAC_PYTHON": str(fake_isaac),
            },
        )
        assert_status(result, 2, "launchable workload blocks before contact gate PASS")
        assert_contains(result, "run_launchable_contact_physics_smoke.sh first", "launchable direct workload gate detail")

        result = run(
            ["scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh"],
            env={
                "RCA_LAUNCHABLE_REPO_DIR": str(fake_launchable_repo),
                "RCA_LAUNCHABLE_ARTIFACT_ROOT": str(tmp_dir / "blocked-launchable-wrapper-artifacts"),
                "RCA_ISAAC_PYTHON": str(fake_isaac),
            },
        )
        assert_status(result, 2, "launchable wrapper blocks through guarded base script")
        assert_contains(result, "run_launchable_contact_physics_smoke.sh first", "launchable wrapper gate detail")

        blocked_gate_env = {"RCA_CONTACT_GATE_REPO_ROOT": str(fake_launchable_repo)}

        result = run(["scripts/remote_operation_preflight.sh"], env=blocked_gate_env)
        assert_status(result, 2, "remote operation preflight blocks while contact gate is blocked")

        result = run(
            ["scripts/remote_operation_preflight.sh"],
            env={"RCA_REMOTE_OPERATION_PURPOSE": "contact_physics_smoke"},
        )
        assert_status(result, 0, "remote operation preflight allows contact smoke purpose")
        assert_contains(result, "PASS purpose=contact_physics_smoke", "remote operation contact-smoke detail")

        result = run(
            ["scripts/remote_operation_preflight.sh"],
            env={"RCA_REMOTE_OPERATION_PURPOSE": "unknown"},
        )
        assert_status(result, 2, "remote operation preflight rejects unknown purpose")
        assert_contains(result, "unknown RCA_REMOTE_OPERATION_PURPOSE", "remote operation unknown-purpose detail")

        result = run(
            ["bash", "-c", "source scripts/remote_common.sh; rca_init_remote_vars fake-env /tmp/remote /tmp/compose"],
            env=blocked_gate_env,
        )
        assert_status(result, 2, "remote_common blocks existing-env operations while contact gate is blocked")
        assert_contains(result, "Phase 2 contact gate", "remote_common blocked-gate detail")

        result = run(
            ["bash", "-c", "source scripts/remote_common.sh; rca_init_remote_vars fake-env /tmp/remote /tmp/compose"],
            env={
                **blocked_gate_env,
                "RCA_REMOTE_OPERATION_PREFLIGHT_DONE": "1",
            },
        )
        assert_status(result, 2, "remote_common ignores external preflight-done bypass")
        assert_contains(result, "Phase 2 contact gate", "remote_common bypass blocked-gate detail")

        result = run(["scripts/sync_to_brev.sh", "fake-env", str(tmp_dir / "remote-sync")], env=blocked_gate_env)
        assert_status(result, 2, "sync_to_brev blocks before ssh while contact gate is blocked")
        assert_contains(result, "Phase 2 contact gate", "sync_to_brev blocked-gate detail")

        result = run(
            [
                "scripts/install_remote_isaaclab_runtime.sh",
                "fake-env",
                str(tmp_dir / "remote-runtime"),
                str(tmp_dir / "remote-compose"),
            ],
            env=blocked_gate_env,
        )
        assert_status(result, 2, "install_remote_isaaclab_runtime blocks before ssh while contact gate is blocked")
        assert_contains(result, "Phase 2 contact gate", "runtime install blocked-gate detail")

        result = run(
            ["scripts/pull_artifacts.sh", "fake-env", str(tmp_dir / "remote-pull"), str(tmp_dir / "local-artifacts")],
            env=blocked_gate_env,
        )
        assert_status(result, 2, "pull_artifacts blocks before rsync while contact gate is blocked")
        assert_contains(result, "Phase 2 contact gate", "pull_artifacts blocked-gate detail")

        result = run(["scripts/paid_compute_preflight.sh"], env={"RCA_BREV_CLI": str(fake_brev)})
        assert_status(result, 2, "paid preflight requires explicit paid acknowledgement")
        assert_contains(result, "RCA_ALLOW_PAID_BREV_CREATE", "paid preflight ack detail")

        result = run(["scripts/paid_compute_preflight.sh"], env=paid_env(fake_brev))
        assert_status(result, 0, "paid preflight allows contact smoke with empty fake org")
        assert_contains(result, "[paid-preflight] PASS", "paid preflight PASS output")
        assert_contains(result, "estimated_max_cost_eur=0.8333", "paid preflight estimated cost detail")

        no_credit_env = paid_env(fake_brev)
        no_credit_env.pop("RCA_BREV_CREDITS_VERIFIED", None)
        result = run(["scripts/paid_compute_preflight.sh"], env=no_credit_env)
        assert_status(result, 2, "paid preflight requires manual Brev credit verification")
        assert_contains(result, "RCA_BREV_CREDITS_VERIFIED", "paid preflight credit verification detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(fake_brev, RCA_PAID_BUDGET_EUR="0.5"),
        )
        assert_status(result, 2, "paid preflight blocks estimated cost above budget")
        assert_contains(result, "estimated max cost", "paid preflight cost cap detail")

        watchdog_ledger = tmp_dir / "watchdog-ledger"
        result = run(
            ["scripts/brev_paid_run_watchdog.sh"],
            env={
                "RCA_BREV_CLI": str(fake_brev),
                "RCA_BREV_WATCHDOG_SCOPE": "org",
                "RCA_BREV_WATCHDOG_DELETE_SCOPE_ACK": "delete-all-visible-brev-instances",
                "RCA_BREV_WATCHDOG_MAX_MINUTES": "5",
                "RCA_BREV_WATCHDOG_ONCE": "1",
                "RCA_BREV_WATCHDOG_LEDGER_DIR": str(watchdog_ledger),
                "RCA_PAID_BUDGET_EUR": "1",
                "RCA_PAID_ESTIMATED_EUR_PER_HOUR": "10",
                "FAKE_BREV_JSON": '{"workspaces": [{"name": "watchdog-test", "id": "wd1"}]}',
            },
        )
        assert_status(result, 0, "Brev watchdog records cost metadata offline")
        watchdog_meta = watchdog_ledger / "watchdog_start.env"
        if not watchdog_meta.is_file():
            print("[gate-tests] FAIL watchdog metadata missing", file=sys.stderr)
            raise SystemExit(1)
        watchdog_meta_text = watchdog_meta.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "budget_eur=1",
            "estimated_eur_per_hour=10",
            "estimated_max_cost_eur=0.8333",
            "open_dashboard_on_manual=1",
        ):
            if needle not in watchdog_meta_text:
                print(f"[gate-tests] FAIL watchdog metadata missing {needle!r}", file=sys.stderr)
                print(watchdog_meta_text, file=sys.stderr)
                raise SystemExit(1)

        fake_bin_dir = tmp_dir / "fake-bin"
        fake_bin_dir.mkdir()
        fake_open_log = tmp_dir / "fake-open.log"
        fake_open = fake_bin_dir / "open"
        fake_open.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' \"$*\" >> \"${FAKE_OPEN_LOG}\"\n",
            encoding="utf-8",
        )
        fake_open.chmod(fake_open.stat().st_mode | stat.S_IXUSR)
        manual_ledger = tmp_dir / "watchdog-manual-ledger"
        result = run(
            ["scripts/brev_paid_run_watchdog.sh"],
            env={
                "PATH": f"{fake_bin_dir}:{os.environ.get('PATH', '')}",
                "FAKE_OPEN_LOG": str(fake_open_log),
                "RCA_BREV_CLI": str(fake_brev),
                "RCA_BREV_WATCHDOG_SCOPE": "target",
                "RCA_BREV_WATCHDOG_INSTANCE_NAME": "watchdog-login-drop",
                "RCA_BREV_WATCHDOG_MAX_MINUTES": "5",
                "RCA_BREV_WATCHDOG_POLL_SECONDS": "5",
                "RCA_BREV_WATCHDOG_QUERY_FAILURE_LIMIT": "1",
                "RCA_BREV_WATCHDOG_NOTIFY": "0",
                "RCA_BREV_WATCHDOG_SOUND": "0",
                "RCA_BREV_WATCHDOG_LEDGER_DIR": str(manual_ledger),
                "RCA_BREV_WATCHDOG_DASHBOARD_URL": "https://brev.nvidia.com/org/test/environments",
                "FAKE_BREV_EXIT": "1",
            },
        )
        assert_status(result, 86, "Brev watchdog opens dashboard when CLI query/login fails")
        assert_contains(result, "MANUAL DELETE REQUIRED", "watchdog manual delete alert detail")
        if not (manual_ledger / "manual_delete_required.txt").is_file():
            raise AssertionError("watchdog must write manual_delete_required.txt on query/login failure")
        if not fake_open_log.is_file() or "https://brev.nvidia.com/org/test/environments" not in fake_open_log.read_text(
            encoding="utf-8"
        ):
            raise AssertionError("watchdog must open the Brev dashboard on manual cleanup risk")
        events_text = (manual_ledger / "events.tsv").read_text(encoding="utf-8")
        if "dashboard_open_requested" not in events_text:
            raise AssertionError("watchdog events should record dashboard_open_requested")

        lifecycle_hold = tmp_dir / "brev-lifecycle-hold.md"
        lifecycle_hold.write_text("synthetic lifecycle hold\n", encoding="utf-8")
        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(fake_brev, RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold)),
        )
        assert_status(result, 2, "paid preflight blocks active Brev lifecycle hold")
        assert_contains(result, "Brev/Launchable lifecycle hold is active", "paid preflight lifecycle hold detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_ACK_BREV_LIFECYCLE_RISK="1",
            ),
        )
        assert_status(result, 0, "paid preflight allows explicit lifecycle-risk acknowledgement")
        assert_contains(result, "[paid-preflight] PASS", "paid preflight lifecycle risk ack PASS output")

        lifecycle_support_draft = tmp_dir / "brev-support-draft.md"
        lifecycle_support_draft.write_text("synthetic support draft\n", encoding="utf-8")
        lifecycle_bundle_path = launchable_bundle_dir / "robot-contact-assembly-contact-smoke-gate-test.tar.gz"
        result = run(
            ["scripts/create_launchable_bundle.sh", str(lifecycle_bundle_path)],
            env={
                "RCA_LAUNCHABLE_BUNDLE_DIR": str(launchable_bundle_dir),
                "RCA_LAUNCHABLE_TMPDIR": str(tmp_dir / "launchable-lifecycle-bundle-tmp"),
            },
        )
        assert_status(result, 0, "launchable bundle creation succeeds before lifecycle clearance")
        assert_contains(result, "[launchable-bundle] wrote", "lifecycle clearance bundle output detail")
        result = run(
            ["scripts/check_brev_lifecycle_hold_clearance.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_BREV_SUPPORT_DRAFT=str(lifecycle_support_draft),
                RCA_LAUNCHABLE_BUNDLE_DIR=str(launchable_bundle_dir),
            ),
        )
        assert_status(result, 0, "Brev lifecycle clearance check passes with empty fake org and active hold")
        assert_contains(result, "READY_FOR_HUMAN_REVIEW", "Brev lifecycle clearance ready detail")

        result = run(
            ["scripts/check_brev_lifecycle_hold_clearance.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_BREV_SUPPORT_DRAFT=str(lifecycle_support_draft),
                FAKE_BREV_JSON='{"workspaces": [{"name": "still-live"}]}',
            ),
        )
        assert_status(result, 2, "Brev lifecycle clearance blocks nonempty fake org")
        assert_contains(result, "visible Brev instance list is not empty", "Brev lifecycle clearance nonempty detail")

        result = run(
            ["scripts/check_launchable_retry_readiness.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_RETRY_READINESS_SKIP_LOCAL_QUALITY="1",
            ),
        )
        assert_status(result, 2, "Launchable retry readiness blocks unsafe contact-smoke retry")
        if "Phase 2 contact gate already passes" not in result.stdout:
            assert_contains(result, "lifecycle risk has not been acknowledged", "Launchable retry readiness lifecycle-risk detail")

        result = run(
            ["scripts/check_launchable_retry_readiness.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_ACK_BREV_LIFECYCLE_RISK="1",
                RCA_RETRY_READINESS_SKIP_LOCAL_QUALITY="1",
            ),
        )
        if result.returncode == 0:
            assert_contains(result, "READY_FOR_ONE_CONTACT_SMOKE_RETRY", "Launchable retry readiness acknowledged detail")
        else:
            assert_status(result, 2, "Launchable retry readiness blocks duplicate smoke with risk ack")
            assert_contains(result, "Phase 2 contact gate already passes", "Launchable retry readiness post-PASS detail")

        incident_dir = tmp_dir / "brev-incident"
        result = run(
            ["scripts/create_brev_lifecycle_incident_bundle.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_BREV_SUPPORT_DRAFT=str(lifecycle_support_draft),
                RCA_BREV_INCIDENT_OUTPUT_DIR=str(incident_dir),
                RCA_INCIDENT_SKIP_LOCAL_QUALITY="1",
            ),
        )
        assert_status(result, 0, "Brev lifecycle incident bundle generation succeeds offline")
        assert_contains(result, "[brev-incident] READY", "Brev lifecycle incident ready detail")
        assert_contains(result, "archive_sha256=", "Brev lifecycle incident archive sha detail")
        for rel_name in (
            "brev_ls_instances_json.txt",
            "project_status_report.txt",
            "paid_preflight_hold_block.txt",
            "support_followup_draft.md",
            "brev_launchable_lifecycle_hold.md",
            "SHA256SUMS.txt",
        ):
            if not (incident_dir / rel_name).is_file():
                print(f"[gate-tests] FAIL Brev incident bundle missing {rel_name}", file=sys.stderr)
                raise SystemExit(1)
        if not Path(f"{incident_dir}.tar.gz").is_file():
            print("[gate-tests] FAIL Brev incident bundle archive missing", file=sys.stderr)
            raise SystemExit(1)
        if not Path(f"{incident_dir}.tar.gz.sha256").is_file():
            print("[gate-tests] FAIL Brev incident bundle archive sha missing", file=sys.stderr)
            raise SystemExit(1)
        assert_contains(
            subprocess.CompletedProcess(args=[], returncode=0, stdout=(incident_dir / "paid_preflight_hold_block.txt").read_text(encoding="utf-8")),
            "Brev/Launchable lifecycle hold is active",
            "Brev incident paid preflight hold evidence",
        )
        (incident_dir / "local_quality_checks.txt").write_text(
            "[local-quality] passed\n\n[exit_status] 0\n",
            encoding="utf-8",
        )
        write_tar_gz(incident_dir, Path(f"{incident_dir}.tar.gz"))
        incident_sha = sha256_path(Path(f"{incident_dir}.tar.gz"))
        Path(f"{incident_dir}.tar.gz.sha256").write_text(
            f"{incident_sha}  {incident_dir}.tar.gz\n",
            encoding="utf-8",
        )
        evidence_draft = tmp_dir / "brev-support-evidence.md"
        evidence_draft.write_text(
            "\n".join(
                [
                    "Latest local evidence bundle:",
                    "",
                    "```text",
                    f"archive: {incident_dir}.tar.gz",
                    f"sha256: {incident_sha}",
                    "```",
                    "",
                    "- Local incident evidence bundle:",
                    f"  `{incident_dir}.tar.gz`",
                    f"  (`sha256={incident_sha}`).",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        result = run(["python3", "scripts/check_brev_support_evidence.py", str(evidence_draft)])
        assert_status(result, 0, "Brev support evidence check passes on synthetic evidence")
        assert_contains(result, "[brev-support-evidence] passed", "Brev support evidence pass detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(fake_brev, FAKE_BREV_JSON='{"workspaces": [{"name": "live"}]}'),
        )
        assert_status(result, 2, "paid preflight blocks nonempty fake org")
        assert_contains(result, "Brev org is not empty", "paid preflight nonempty detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(
                fake_brev,
                FAKE_BREV_JSON='{"workspaces": [{"name": "live"}]}',
                RCA_PAID_PREFLIGHT_ALLOW_NONEMPTY_ORG="1",
            ),
        )
        assert_status(result, 2, "paid preflight ignores nonempty-org bypass")
        assert_contains(result, "Brev org is not empty", "paid preflight nonempty bypass detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(fake_brev, FAKE_BREV_EXIT="1"),
        )
        assert_status(result, 2, "paid preflight blocks failed fake Brev query")
        assert_contains(result, "Brev CLI query failed", "paid preflight auth/query detail")

        canonical_smoke_log = REPO_ROOT / "artifacts" / "launchable_logs" / "contact_physics_smoke.log"
        result = run(["scripts/archive_contact_smoke_log.sh", str(pass_log), str(canonical_smoke_log)])
        assert_status(result, 0, "contact smoke archive installs canonical PASS log")
        assert_contains(result, "canonical contact-smoke evidence is archived and valid", "canonical smoke archive detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(fake_brev, RCA_PAID_RUN_PURPOSE="post_contact_gate"),
        )
        assert_status(result, 0, "post-contact paid preflight passes after contact gate PASS")
        assert_contains(result, "[paid-preflight] PASS", "post-contact paid preflight PASS detail")

        result = run(
            ["scripts/paid_compute_preflight.sh"],
            env=paid_env(
                fake_brev,
                RCA_PAID_RUN_PURPOSE="post_contact_gate",
                RCA_PAID_PREFLIGHT_SKIP_PHASE_GATE="1",
            ),
        )
        assert_status(result, 0, "post-contact paid preflight ignores obsolete phase-gate skip bypass after PASS")
        assert_contains(result, "[paid-preflight] PASS", "post-contact skip bypass PASS detail")

        result = run(
            ["scripts/prepare_contact_smoke_run.sh"],
            env=prepare_env(fake_brev, RCA_PAID_BUDGET_EUR=""),
        )
        assert_status(result, 2, "contact smoke prepare requires explicit budget")
        assert_contains(result, "RCA_PAID_BUDGET_EUR", "contact smoke prepare budget detail")

        result = run(
            ["scripts/prepare_contact_smoke_run.sh"],
            env=prepare_env(fake_brev, RCA_PAID_ESTIMATED_EUR_PER_HOUR=""),
        )
        assert_status(result, 2, "contact smoke prepare requires hourly cost estimate")
        assert_contains(result, "RCA_PAID_ESTIMATED_EUR_PER_HOUR", "contact smoke prepare hourly estimate detail")

        prepare_bundle_path = tmp_dir / "prepare-contact-smoke.tar.gz"
        result = run(
            ["scripts/prepare_contact_smoke_run.sh"],
            env=prepare_env(fake_brev, RCA_CONTACT_SMOKE_BUNDLE_PATH=str(prepare_bundle_path)),
        )
        assert_status(result, 0, "contact smoke prepare no-ops after contact gate PASS")
        assert_contains(
            result,
            "contact gate already passes; do not spend paid compute on another smoke",
            "contact smoke prepare duplicate-smoke detail",
        )
        if prepare_bundle_path.exists():
            print("[gate-tests] FAIL contact smoke prepare created bundle after gate PASS", file=sys.stderr)
            raise SystemExit(1)

        result = run(
            ["scripts/prepare_contact_smoke_run.sh"],
            env=prepare_env(fake_brev, FAKE_BREV_EXIT="1"),
        )
        assert_status(result, 0, "contact smoke prepare does not query Brev after contact gate PASS")
        assert_contains(
            result,
            "contact gate already passes; do not spend paid compute on another smoke",
            "contact smoke prepare post-PASS Brev-skip detail",
        )

        bundle_path = tmp_dir / "launchable-test.tar.gz"
        sensitive_fixture_paths = [
            REPO_ROOT / ".env",
            REPO_ROOT / ".env.local",
            REPO_ROOT / "dummy_private.key",
            REPO_ROOT / "fake_credential.txt",
        ]
        for fixture_path in sensitive_fixture_paths:
            fixture_path.write_text("synthetic-test-secret\n", encoding="utf-8")
        try:
            result = run(
                ["scripts/create_launchable_bundle.sh", str(bundle_path)],
                env={"RCA_LAUNCHABLE_TMPDIR": str(tmp_dir / "launchable-bundle-tmp")},
            )
            assert_status(result, 0, "launchable bundle creation succeeds offline")
            assert_contains(result, "[launchable-bundle] wrote", "launchable bundle output detail")
        finally:
            for fixture_path in sensitive_fixture_paths:
                fixture_path.unlink(missing_ok=True)
        if not bundle_path.is_file():
            print("[gate-tests] FAIL launchable bundle file missing", file=sys.stderr)
            raise SystemExit(1)
        with tarfile.open(bundle_path, "r:gz") as archive:
            names = archive.getnames()
            generated_members = [
                name
                for name in names
                if "egg-info" in name
                or "__pycache__" in name
                or name.endswith(".pyc")
                or name.endswith(".DS_Store")
                or "/.claude/" in name
                or name.endswith("/.env")
                or "/.env." in name
                or "credential" in name.lower()
                or "secret" in name.lower()
                or "private" in name.lower()
            ]
            if generated_members:
                print("[gate-tests] FAIL launchable bundle includes generated/local-sensitive files", file=sys.stderr)
                print("\n".join(generated_members[:20]), file=sys.stderr)
                raise SystemExit(1)
            manifest_member = archive.extractfile("robot-contact-assembly/.rca_launchable_source_manifest.txt")
            if manifest_member is None:
                print("[gate-tests] FAIL launchable bundle source manifest missing", file=sys.stderr)
                raise SystemExit(1)
            manifest_text = manifest_member.read().decode("utf-8", errors="replace")
        if (
            "git_head=" not in manifest_text
            or "git_dirty=" not in manifest_text
            or "source_payload_scope=" not in manifest_text
            or "source_payload_sha256=" not in manifest_text
        ):
            print("[gate-tests] FAIL launchable bundle source manifest incomplete", file=sys.stderr)
            print(manifest_text, file=sys.stderr)
            raise SystemExit(1)

        smoke_log = tmp_dir / "contact_physics_smoke.log"
        result = run(
            ["scripts/run_launchable_contact_physics_smoke.sh"],
            env={
                "RCA_LAUNCHABLE_REPO_DIR": str(fake_launchable_repo),
                "RCA_LAUNCHABLE_ARTIFACT_ROOT": str(tmp_dir / "fake-artifacts"),
                "RCA_CONTACT_SMOKE_LOG_PATH": str(smoke_log),
                "RCA_ISAAC_PYTHON": str(fake_isaac),
            },
        )
        assert_status(result, 0, "contact smoke wrapper writes fake Isaac PASS log")
        if not smoke_log.is_file():
            print("[gate-tests] FAIL contact smoke wrapper log missing", file=sys.stderr)
            raise SystemExit(1)
        smoke_text = smoke_log.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "[contact-smoke] git_head=unknown",
            "[contact-smoke] source_manifest_begin",
            f"[contact-smoke] source_manifest: git_head={current_git_head()}",
            f"[contact-smoke] source_manifest: source_payload_scope={current_payload_scope()}",
            f"[contact-smoke] source_manifest: source_payload_sha256={current_payload_sha256()}",
            "[contact-smoke] run_id=",
            "[contact-smoke] log_path=",
            "[contact-smoke] task extension install completed",
            "CONTACT-SMOKE phase free-space-settle: end",
            "CONTACT-SMOKE contact-setup: local-guide reanchored",
            "CONTACT-SMOKE free-space-reanchored: PASS",
            "CONTACT-SMOKE phase local-guide-reanchor: end",
            "CONTACT-SMOKE press-control: local-wall-sweep",
            "CONTACT-SMOKE phase press-hold: end",
            "CONTACT-SMOKE press-tracking: PASS",
            "CONTACT-SMOKE press-no-clip: PASS",
            "CONTACT-SMOKE phase retreat-hold: end",
            "CONTACT-SMOKE joint-integrity: PASS",
            "CONTACT-SMOKE phase-sequence: PASS",
            "[contact-smoke] completed: contact physics is real",
        ):
            if needle not in smoke_text:
                print(f"[gate-tests] FAIL contact smoke wrapper log missing {needle!r}", file=sys.stderr)
                print(smoke_text, file=sys.stderr)
                raise SystemExit(1)

        result = run(["python3", "scripts/check_phase2_contact_gate.py", "--log", str(smoke_log)])
        assert_status(result, 0, "contact gate accepts wrapper-generated fake smoke log")
        assert_contains(result, "PASS: validated", "wrapper-generated smoke log gate detail")

        install_fail_log = tmp_dir / "contact_physics_smoke_install_fail.log"
        result = run(
            ["scripts/run_launchable_contact_physics_smoke.sh"],
            env={
                "RCA_LAUNCHABLE_REPO_DIR": str(fake_launchable_repo),
                "RCA_LAUNCHABLE_ARTIFACT_ROOT": str(tmp_dir / "fake-artifacts-install-fail"),
                "RCA_CONTACT_SMOKE_LOG_PATH": str(install_fail_log),
                "RCA_ISAAC_PYTHON": str(fake_isaac),
                "FAKE_PIP_EXIT": "7",
            },
        )
        assert_status(result, 7, "contact smoke wrapper propagates pip install failure")
        if not install_fail_log.is_file():
            print("[gate-tests] FAIL contact smoke install-failure log missing", file=sys.stderr)
            raise SystemExit(1)
        install_fail_text = install_fail_log.read_text(encoding="utf-8", errors="replace")
        for needle in ("fake pip install", "[contact-smoke] pip install failed status=7"):
            if needle not in install_fail_text:
                print(f"[gate-tests] FAIL contact smoke install-failure log missing {needle!r}", file=sys.stderr)
                print(install_fail_text, file=sys.stderr)
                raise SystemExit(1)

        missing_isaac_log = tmp_dir / "contact_physics_smoke_missing_isaac.log"
        result = run(
            ["scripts/run_launchable_contact_physics_smoke.sh"],
            env={
                "RCA_LAUNCHABLE_REPO_DIR": str(fake_launchable_repo),
                "RCA_LAUNCHABLE_ARTIFACT_ROOT": str(tmp_dir / "fake-artifacts-missing-isaac"),
                "RCA_CONTACT_SMOKE_LOG_PATH": str(missing_isaac_log),
                "RCA_ISAAC_PYTHON": str(tmp_dir / "missing-isaac-python"),
            },
        )
        assert_status(result, 2, "contact smoke wrapper logs missing Isaac Python")
        if not missing_isaac_log.is_file():
            print("[gate-tests] FAIL missing-Isaac log missing", file=sys.stderr)
            raise SystemExit(1)
        assert_contains(result, "missing Isaac Python", "missing-Isaac stdout detail")
        if "missing Isaac Python" not in missing_isaac_log.read_text(encoding="utf-8", errors="replace"):
            print("[gate-tests] FAIL missing-Isaac detail absent from log", file=sys.stderr)
            raise SystemExit(1)

        missing_repo_log = tmp_dir / "contact_physics_smoke_missing_repo.log"
        missing_repo = tmp_dir / "missing-launchable-repo"
        result = run(
            ["scripts/run_launchable_contact_physics_smoke.sh"],
            env={
                "RCA_LAUNCHABLE_REPO_DIR": str(missing_repo),
                "RCA_LAUNCHABLE_ARTIFACT_ROOT": str(tmp_dir / "fake-artifacts-missing-repo"),
                "RCA_CONTACT_SMOKE_LOG_PATH": str(missing_repo_log),
                "RCA_ISAAC_PYTHON": str(fake_isaac),
            },
        )
        assert_status(result, 2, "contact smoke wrapper logs missing repo")
        if not missing_repo_log.is_file():
            print("[gate-tests] FAIL missing-repo log missing", file=sys.stderr)
            raise SystemExit(1)
        assert_contains(result, "missing project repo", "missing-repo stdout detail")
        if "missing project repo" not in missing_repo_log.read_text(encoding="utf-8", errors="replace"):
            print("[gate-tests] FAIL missing-repo detail absent from log", file=sys.stderr)
            raise SystemExit(1)

        policy_test_prefix = f"__policy_test_{os.getpid()}"
        unsafe_create_variants = {
            f"{policy_test_prefix}_unsafe_paid_create_brev.sh": "brev create unsafe-paid-test\n",
            f"{policy_test_prefix}_unsafe_paid_create_bin.sh": "/Users/Shenghan/bin/brev create unsafe-paid-test\n",
            f"{policy_test_prefix}_unsafe_paid_create_var.sh": (
                'BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"\n'
                '"${BREV_BIN}" create unsafe-paid-test\n'
            ),
        }
        for filename, body in unsafe_create_variants.items():
            unsafe_paid_script = REPO_ROOT / "scripts" / filename
            try:
                unsafe_paid_script.write_text(
                    "#!/usr/bin/env bash\nset -euo pipefail\n" + body,
                    encoding="utf-8",
                )
                unsafe_paid_script.chmod(0o755)
                result = run(["python3", "scripts/check_project_policy_compliance.py"])
                assert_status(result, 1, f"policy check rejects unguarded Brev create script {filename}")
                assert_contains(
                    result,
                    "does not call paid_compute_preflight",
                    f"unguarded Brev create policy detail {filename}",
                )
            finally:
                unsafe_paid_script.unlink(missing_ok=True)

        unsafe_unverified_watchdog = REPO_ROOT / "scripts" / f"{policy_test_prefix}_unverified_watchdog_create.sh"
        try:
            unsafe_unverified_watchdog.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                'BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"\n'
                "RCA_ALLOW_PAID_BREV_CREATE=1 RCA_BREV_CREDITS_VERIFIED=1 RCA_PAID_MAX_MINUTES=1 ./scripts/paid_compute_preflight.sh\n"
                "./scripts/brev_paid_run_watchdog.sh &\n"
                '"${BREV_BIN}" create unsafe-paid-test\n',
                encoding="utf-8",
            )
            unsafe_unverified_watchdog.chmod(0o755)
            result = run(["python3", "scripts/check_project_policy_compliance.py"])
            assert_status(result, 1, "policy check rejects paid create without watchdog-start verification")
            assert_contains(
                result,
                "does not verify the watchdog started",
                "unverified watchdog create policy detail",
            )
        finally:
            unsafe_unverified_watchdog.unlink(missing_ok=True)

        unsafe_remote_variants = {
            f"{policy_test_prefix}_unsafe_remote_ssh.sh": (
                "#!/usr/bin/env bash\nset -euo pipefail\nssh fake-env 'true'\n"
            ),
            f"{policy_test_prefix}_unsafe_remote_rsync.sh": (
                "#!/usr/bin/env bash\nset -euo pipefail\nrsync -az ./ fake-env:/tmp/rca\n"
            ),
            f"{policy_test_prefix}_unsafe_remote_brev_exec.py": (
                "#!/usr/bin/env python3\n"
                "import subprocess\n"
                "subprocess.run(['/Users/Shenghan/bin/brev', 'exec', 'fake-env', 'true'], check=False)\n"
            ),
        }
        for filename, body in unsafe_remote_variants.items():
            unsafe_remote_script = REPO_ROOT / "scripts" / filename
            try:
                unsafe_remote_script.write_text(body, encoding="utf-8")
                unsafe_remote_script.chmod(0o755)
                result = run(["python3", "scripts/check_project_policy_compliance.py"])
                assert_status(result, 1, f"policy check rejects unguarded remote operation script {filename}")
                assert_contains(
                    result,
                    "performs direct remote operations",
                    f"unguarded remote operation policy detail {filename}",
                )
            finally:
                unsafe_remote_script.unlink(missing_ok=True)

        unsafe_bypass_markers = (
            "RCA_BREV_UI_WATCHDOG_SKIP_PREFLIGHT",
            "RCA_GATE_WATCHDOG_ENABLED",
            "RCA_RECREATE_WATCHDOG_ENABLED",
            "RCA_GATE_DELETE_ON_EXIT",
            "RCA_GATE_KEEP_ON_FAILURE",
            "RCA_RECREATE_DELETE_ON_EXIT",
            "RCA_RECREATE_KEEP_ON_FAILURE",
            "RCA_BREV_GUARD_DELETE_ON_EXIT",
            "RCA_BREV_GUARD_KEEP_ON_FAILURE",
        )
        for marker in unsafe_bypass_markers:
            unsafe_bypass_script = REPO_ROOT / "scripts" / f"{policy_test_prefix}_unsafe_{marker.lower()}.sh"
            try:
                unsafe_bypass_script.write_text(
                    "#!/usr/bin/env bash\nset -euo pipefail\n"
                    f'{marker}="${{{marker}:-0}}"\n',
                    encoding="utf-8",
                )
                unsafe_bypass_script.chmod(0o755)
                result = run(["python3", "scripts/check_project_policy_compliance.py"])
                assert_status(result, 1, f"policy check rejects guard-bypass marker {marker}")
                assert_contains(
                    result,
                    "forbidden guard-bypass marker",
                    f"guard-bypass marker policy detail {marker}",
                )
            finally:
                unsafe_bypass_script.unlink(missing_ok=True)

        result = run(["python3", "scripts/project_status_report.py", "--fail-on-blocked"])
        assert_status(result, 2, "status report fails while lifecycle hold is blocked")
        assert_contains(result, "Brev lifecycle hold | BLOCKED", "status report lifecycle-hold detail")
        assert_contains(result, "Phase 2 contact gate | PASS", "status report contact gate PASS detail")
        assert_contains(result, "Runtime source payload scope", "status report payload scope detail")
        assert_contains(result, "Runtime source payload SHA256", "status report payload detail")
        assert_contains(result, "Contact-smoke bundle", "status report contact-smoke bundle detail")
        assert_contains(
            result,
            "Success variation paid lifecycle preflight | BLOCKED",
            "status report paid lifecycle preflight detail",
        )
        assert_contains(
            result,
            "brev_safety=",
            "status report Brev safety status detail",
        )
        assert_contains(result, "credit_blockers=", "status report paid lifecycle credit blocker count detail")
        assert_contains(result, "api_credit_status=", "status report paid lifecycle API credit status detail")
        assert_contains(result, "api_credit_balance_usd=", "status report paid lifecycle API credit balance detail")
        assert_contains(result, "api_credit_next_action=", "status report paid lifecycle API credit next-action detail")
        assert_contains(result, "api_credit_blockers=", "status report paid lifecycle API credit blocker count detail")
        assert_contains(result, "armability_blockers=", "status report paid lifecycle armability blocker count detail")
        assert_contains(result, "pre_batch_blockers=", "status report paid lifecycle pre-batch blocker count detail")
        assert_contains(result, "ack_blockers=", "status report paid lifecycle acknowledgement blocker count detail")
        assert_contains(result, "unblock_plan=", "status report paid lifecycle unblock-plan detail")
        assert_contains(result, "visible_instances=", "status report visible instance detail")
        assert_contains(result, "watchdog_processes=", "status report watchdog process detail")
        assert_contains(result, "manual_delete_alerts=", "status report manual-delete alert detail")
        assert_contains(
            result,
            "Success variation pre-batch assumption audit | BLOCKED",
            "status report pre-batch assumption audit detail",
        )
        assert_contains(
            result,
            "Success variation post-batch assumption audit | BLOCKED",
            "status report post-batch assumption audit detail",
        )
        assert_contains(
            result,
            "result_gate_pass=False",
            "status report post-batch result-gate detail",
        )
        assert_contains(
            result,
            "negative_control=missing",
            "status report post-batch negative-control detail",
        )
        assert_contains(
            result,
            "V0 scripted-skill dataset prep | BLOCKED",
            "status report dataset prep detail",
        )
        assert_contains(
            result,
            "Success variation recovery plan | READY",
            "status report recovery plan detail",
        )
        assert_contains(result, "rerun_case_count=8", "status report recovery rerun count detail")
        assert_contains(
            result,
            "negative_control_in_rerun=True",
            "status report recovery negative-control detail",
        )
        assert_contains(
            result,
            "writes_recovery_artifacts=False",
            "status report recovery no-write detail",
        )
        assert_contains(
            result,
            "result_gate_pass=False",
            "status report dataset prep result-gate detail",
        )
        assert_contains(
            result,
            "writes_dataset_artifacts=False",
            "status report dataset prep no-write detail",
        )
        assert_contains(result, "audit_status=BLOCKED; phase=pre-batch", "status report audit status detail")
        assert_contains(result, "Brev UI credit review | BLOCKED", "status report Brev credit review detail")
        assert_contains(
            result,
            "packet_status=",
            "status report Brev credit review packet detail",
        )
        assert_contains(
            result,
            "dashboard_url=https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments",
            "status report Brev dashboard URL detail",
        )
        assert_contains(
            result,
            "preview_credit_command=python3 scripts/write_brev_credit_evidence.py",
            "status report preview credit command detail",
        )
        assert_contains(result, "balance_preview_status=NOT_PROVIDED", "status report balance preview detail")
        assert_contains(result, "api_credit_status=", "status report API credit status detail")
        assert_contains(result, "api_credit_balance_usd=", "status report API credit balance detail")
        assert_contains(result, "api_credit_next_action=", "status report API credit next-action detail")
        assert_contains(result, "credit_consistency=", "status report credit consistency detail")
        assert_contains(result, "paid_prepare_allowed=", "status report paid-prepare guard detail")
        assert_contains(result, "Brev credit blocker diagnosis | BLOCKED", "status report Brev credit diagnosis detail")
        assert_contains(result, "diagnosis_status=", "status report Brev credit diagnosis status detail")
        assert_contains(result, "active_org_id=", "status report Brev credit diagnosis active org detail")
        assert_contains(result, "workspaces_null=", "status report Brev credit diagnosis workspace detail")
        assert_contains(result, "paid_unblock_plan=", "status report Brev credit unblock-plan detail")
        assert_contains(result, "ack_blockers=", "status report Brev credit ack blocker detail")
        assert_contains(
            result,
            "--dry-run",
            "status report includes paid preview dry-run commands",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_success_variation_dataset.py artifacts/manifests/success_trace_variations_2026-06-25.json --dry-run",
            "status report dataset prep dry-run command detail",
        )
        assert_contains(
            result,
            "write_command=python3 scripts/write_brev_credit_evidence.py",
            "status report write credit command detail",
        )
        assert_contains(
            result,
            "preview_prepare_command=python3 scripts/prepare_success_variation_paid_batch.py",
            "status report preview prepare command detail",
        )
        assert_contains(
            result,
            "prepare_command=python3 scripts/prepare_success_variation_paid_batch.py",
            "status report prepare helper detail",
        )
        assert_contains(result, "V0 language instruction suite | PASS", "status report V0 language suite detail")
        assert_contains(result, "cases=6/6", "status report V0 language suite case count detail")
        assert_contains(
            result,
            "writes_suite_report=False",
            "status report V0 language suite no-write detail",
        )
        assert_contains(
            result,
            "calls_llm_or_vlm=False",
            "status report V0 language suite no-LLM detail",
        )
        assert_contains(
            result,
            "not_cross_robot_ready=True",
            "status report V0 language suite portability non-claim detail",
        )
        assert_contains(result, "V0 language skill dry-run | BLOCKED", "status report V0 language dry-run detail")
        assert_contains(result, "request_planner=PASS", "status report V0 language dry-run planner detail")
        assert_contains(result, "request_validation=PASS", "status report V0 language dry-run validation detail")
        assert_contains(result, "execution_plan=BLOCKED", "status report V0 language dry-run execution detail")
        assert_contains(
            result,
            "allowed_command_boundary=task_parameters_to_skill_controller",
            "status report V0 language dry-run command-boundary detail",
        )
        assert_contains(
            result,
            "writes_request_artifact=False",
            "status report V0 language dry-run no-request-write detail",
        )
        assert_contains(
            result,
            "writes_dry_run_report=False",
            "status report V0 language dry-run no-report-write detail",
        )
        assert_contains(
            result,
            "creates_paid_instance=False",
            "status report V0 language dry-run no-paid-instance detail",
        )
        assert_contains(result, "V0 skill readiness | BLOCKED", "status report V0 readiness detail")
        assert_contains(
            result,
            "writes_readiness_report=False",
            "status report V0 readiness no-write detail",
        )
        assert_contains(result, "V0 policy/API review packet | BLOCKED", "status report V0 policy/API review detail")
        assert_contains(
            result,
            "writes_review_artifacts=False",
            "status report V0 policy/API review no-write detail",
        )
        assert_contains(
            result,
            "trains_policy=False",
            "status report V0 policy/API review no-training detail",
        )
        assert_contains(
            result,
            "V0 offline policy-readiness pipeline | BLOCKED",
            "status report V0 offline policy-readiness detail",
        )
        assert_contains(
            result,
            "blocked_step=policy_api_review",
            "status report V0 offline policy-readiness blocked step detail",
        )
        assert_contains(
            result,
            "writes_policy_artifacts=False",
            "status report V0 offline policy-readiness no-write detail",
        )
        assert_contains(result, "V0 policy training preflight | BLOCKED", "status report V0 training preflight detail")
        assert_contains(result, "training_script_status=IMPLEMENTED", "status report V0 training script detail")
        assert_contains(result, "V0 residual policy eval | BLOCKED", "status report V0 residual eval detail")
        assert_contains(result, "V0 policy promotion gate | BLOCKED", "status report V0 policy promotion detail")
        assert_contains(
            result,
            "writes_promotion_report=False",
            "status report V0 policy promotion no-write detail",
        )
        assert_contains(result, "External robot adapter | BLOCKED", "status report external adapter detail")
        assert_contains(
            result,
            "writes_adapter_report=False",
            "status report external adapter no-write detail",
        )
        assert_contains(
            result,
            "calls_ros_or_robot=False",
            "status report external adapter no-robot-call detail",
        )
        assert_contains(result, "Cross-robot portability | BLOCKED", "status report portability boundary detail")
        assert_contains(
            result,
            "writes_boundary_report=False",
            "status report portability boundary no-write detail",
        )
        assert_contains(result, "V0 portability review packet | BLOCKED", "status report portability review detail")
        assert_contains(
            result,
            "writes_review_artifacts=False",
            "status report portability review no-write detail",
        )
        assert_contains(result, "direct_drop_in_answer=NO_DIRECT_DROP_IN", "status report portability review non-drop-in detail")
        assert_contains(result, "universal_drop_in_ready=False", "status report portability non-claim detail")
        assert_contains(result, "direct_use_ready=False", "status report portability direct-use non-claim detail")
        assert_contains(result, "transfer_readiness_level=", "status report portability transfer-level detail")
        assert_contains(result, "ready_for_hardware_execution=False", "status report portability hardware-execution non-claim detail")
        assert_contains(
            result,
            "target_adapter_preview=NOT_PROVIDED",
            "status report portability target adapter preview detail",
        )
        assert_contains(
            result,
            "workplan_status=BLOCKED_NOT_DROP_IN",
            "status report portability workplan status detail",
        )
        assert_contains(
            result,
            "workplan_direct_drop_in=NO_DIRECT_DROP_IN",
            "status report portability workplan non-drop-in detail",
        )
        assert_contains(
            result,
            "workplan_transfer_level=",
            "status report portability workplan transfer-level detail",
        )
        assert_contains(
            result,
            "workplan_skill_blockers=5",
            "status report portability workplan skill blocker detail",
        )
        assert_contains(
            result,
            "workplan_adapter_blockers=",
            "status report portability workplan adapter blocker detail",
        )
        assert_contains(
            result,
            "workplan_evidence_groups=8",
            "status report portability workplan evidence-group detail",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_v0_policy_api_review.py --skip-phase2-contact-gate",
            "status report V0 policy/API review command detail",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_brev_credit_review.py --no-output",
            "status report Brev credit review command detail",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_brev_credit_review.py --balance-eur <current-brev-ui-balance> --no-output",
            "status report concrete-balance Brev credit review command detail",
        )
        assert_contains(
            result,
            "python3 scripts/diagnose_brev_credit_blocker.py --no-output",
            "status report Brev credit diagnosis command detail",
        )
        assert_contains(
            result,
            "python3 scripts/diagnose_brev_credit_blocker.py --balance-eur <current-brev-ui-balance> --no-output",
            "status report concrete-balance Brev credit diagnosis command detail",
        )
        assert_contains(
            result,
            "python3 scripts/write_brev_credit_evidence.py --balance-eur <current-brev-ui-balance> --budget-eur 6.00 --dry-run",
            "status report credit dry-run command detail",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_success_variation_paid_batch.py --balance-eur <current-brev-ui-balance> --force-credit --i-understand-this-arms-paid-run --dry-run",
            "status report paid prepare dry-run command detail",
        )
        assert_contains(
            result,
            "python3 scripts/run_success_variation_paid_lifecycle.py --balance-eur <current-brev-ui-balance> --dry-run",
            "status report paid lifecycle dry-run command detail",
        )
        assert_contains(
            result,
            "Single paid entrypoint after fresh UI balance evidence; do not also run the raw config --run",
            "status report single paid entrypoint warning detail",
        )
        raw_run_line = "scripts/run_success_variation_batch_from_config.sh configs/success_variation_batch_run.local.env --run"
        for output_line in result.stdout.splitlines():
            if output_line.strip() == raw_run_line:
                raise AssertionError("status report must not expose raw success-variation --run as an executable command")
        assert_contains(
            result,
            "# " + raw_run_line,
            "status report raw runner fallback comment detail",
        )
        assert_contains(
            result,
            "python3 scripts/plan_success_variation_recovery_batch.py artifacts/manifests/success_trace_variations_2026-06-25.json --no-output",
            "status report recovery no-output command detail",
        )
        assert_contains(
            result,
            "python3 scripts/audit_success_variation_assumptions.py artifacts/manifests/success_trace_variations_2026-06-25.json --phase pre-batch --run-packet artifacts/analysis/success_variation_run_packet_2026-06-25.json --no-output",
            "status report pre-batch assumption audit command detail",
        )
        assert_contains(
            result,
            "python3 scripts/audit_success_variation_assumptions.py artifacts/manifests/success_trace_variations_2026-06-25.json --phase post-batch --no-output",
            "status report post-batch assumption audit command detail",
        )
        assert_contains(
            result,
            "python3 scripts/check_v0_language_instruction_suite.py --no-output",
            "status report V0 language suite command detail",
        )
        assert_contains(
            result,
            "python3 scripts/plan_v0_robot_adapter_manifest.py --robot-id <target_robot_id>",
            "status report adapter planner command detail",
        )
        assert_contains(
            result,
            "--ee-pose-feedback <ee_pose_feedback_topic>",
            "status report adapter planner EE pose command detail",
        )
        assert_contains(
            result,
            "--force-torque-or-contact-feedback <force_torque_or_contact_feedback>",
            "status report adapter planner force/contact command detail",
        )
        assert_contains(
            result,
            "python3 scripts/check_v0_portability_boundary.py --skip-phase2-contact-gate",
            "status report portability command detail",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_v0_portability_review.py --skip-phase2-contact-gate --no-output",
            "status report portability review command detail",
        )
        assert_contains(
            result,
            "python3 scripts/prepare_v0_portability_review.py --target-robot-id <target_robot_id>",
            "status report target portability review command detail",
        )
        assert_contains(
            result,
            "python3 scripts/train_v0_residual_policy.py --dry-run --no-output",
            "status report V0 training dry-run command detail",
        )
        assert_contains(
            result,
            "python3 scripts/run_v0_offline_policy_readiness_pipeline.py --skip-phase2-contact-gate --no-summary --no-output",
            "status report V0 offline policy-readiness read-only command detail",
        )
        assert_contains(
            result,
            "python3 scripts/evaluate_v0_residual_policy.py --dry-run --no-output",
            "status report V0 residual eval dry-run command detail",
        )
        assert_contains(
            result,
            "python3 scripts/check_v0_policy_promotion_gate.py --skip-phase2-contact-gate --no-output",
            "status report V0 policy promotion command detail",
        )

        stale_scope_bundle = launchable_bundle_dir / "robot-contact-assembly-contact-smoke-manual-preauth-9998-stale-scope-test.tar.gz"
        stale_scope_bundle.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(stale_scope_bundle, "w:gz") as archive:
                manifest = tmp_dir / "stale_scope_manifest.txt"
                manifest.write_text(
                    "\n".join(
                        [
                            "created_utc=9998-stale-scope-test",
                            f"source_repo={REPO_ROOT}",
                            f"git_head={current_git_head()}",
                            "git_branch=master",
                            "git_dirty=1",
                            "source_payload_scope=runtime-v0",
                            f"source_payload_sha256={current_payload_sha256()}",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                archive.add(manifest, arcname="robot-contact-assembly/.rca_launchable_source_manifest.txt")
            result = run(
                ["python3", "scripts/project_status_report.py", "--fail-on-blocked"],
                env={"RCA_LAUNCHABLE_BUNDLE_DIR": str(launchable_bundle_dir)},
            )
            assert_status(result, 2, "status report fails when latest bundle has stale scope")
            assert_contains(result, "Contact-smoke bundle | STALE", "status report stale scope bundle detail")
            assert_contains(result, "Latest bundle scope runtime-v0", "status report stale scope detail")
        finally:
            stale_scope_bundle.unlink(missing_ok=True)

        stale_bundle = launchable_bundle_dir / "robot-contact-assembly-contact-smoke-manual-preauth-9999-stale-test.tar.gz"
        stale_bundle.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(stale_bundle, "w:gz") as archive:
                manifest = tmp_dir / "stale_manifest.txt"
                manifest.write_text(
                    "\n".join(
                        [
                            "created_utc=9999-stale-test",
                            f"source_repo={REPO_ROOT}",
                            f"git_head={current_git_head()}",
                            "git_branch=master",
                            "git_dirty=1",
                            f"source_payload_scope={current_payload_scope()}",
                            f"source_payload_sha256={'0' * 64}",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                archive.add(manifest, arcname="robot-contact-assembly/.rca_launchable_source_manifest.txt")
            result = run(
                ["python3", "scripts/project_status_report.py", "--fail-on-blocked"],
                env={"RCA_LAUNCHABLE_BUNDLE_DIR": str(launchable_bundle_dir)},
            )
            assert_status(result, 2, "status report fails when latest bundle is stale")
            assert_contains(result, "Contact-smoke bundle | STALE", "status report stale bundle detail")
        finally:
            stale_bundle.unlink(missing_ok=True)

    print("[gate-tests] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
