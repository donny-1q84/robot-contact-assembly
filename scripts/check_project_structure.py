#!/usr/bin/env python3
"""Static project-structure checks for package and runtime entrypoints.

The repo intentionally has two Python package layers:

- ``src/robot_contact_assembly``: lightweight planning-side notes/utilities.
- ``source/robot_contact_assembly_tasks``: Isaac Lab runtime extension.

This guard prevents future work from accidentally treating the planning package
as the runtime task package or installing the repo root inside Isaac runtimes.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
PLANNING_SPEC = REPO_ROOT / "src/robot_contact_assembly/tasks/peg_in_hole/spec.py"
RUNTIME_ROOT = REPO_ROOT / "source/robot_contact_assembly_tasks"
RUNTIME_PYPROJECT = RUNTIME_ROOT / "pyproject.toml"
RUNTIME_SETUP = RUNTIME_ROOT / "setup.py"
RUNTIME_EXTENSION = RUNTIME_ROOT / "config/extension.toml"
RUNTIME_TASK_ROOT = (
    RUNTIME_ROOT
    / "robot_contact_assembly_tasks/tasks/manager_based/manipulation/peg_in_hole"
)

BAD_RUNTIME_ROOT_INSTALL_RE = re.compile(
    r"""(?mx)
    pip\s+install\s+
    (?:
      -e|--editable
    )
    \s+
    (?:
      ["']?\$\{REPO_DIR\}["']?
      |
      ["']?/workspace/robot-contact-assembly["']?
      |
      ["']?\.
    )
    (?!/source/robot_contact_assembly_tasks)
    """
)


def fail(message: str) -> None:
    print(f"[project-structure] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    if not path.is_file():
        fail(f"missing required file: {path.relative_to(REPO_ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def check_package_boundaries() -> None:
    root_meta = tomllib.loads(read_text(ROOT_PYPROJECT))
    package_dir = root_meta.get("tool", {}).get("setuptools", {}).get("package-dir", {})
    if package_dir.get("") != "src":
        fail("root pyproject must keep package-dir = {'': 'src'} for planning-side package")

    planning_text = read_text(PLANNING_SPEC)
    for marker in ("not the runtime source of truth", "source/robot_contact_assembly_tasks"):
        if marker not in planning_text:
            fail(f"planning spec missing runtime-boundary marker: {marker}")
    if "isaaclab" in planning_text.lower():
        fail("planning-side spec must not import or depend on Isaac Lab")

    for path in (RUNTIME_PYPROJECT, RUNTIME_SETUP, RUNTIME_EXTENSION):
        if not path.is_file():
            fail(f"missing runtime extension file: {path.relative_to(REPO_ROOT)}")

    extension = tomllib.loads(read_text(RUNTIME_EXTENSION))
    modules = extension.get("python", {}).get("module", [])
    module_names = {item.get("name") for item in modules if isinstance(item, dict)}
    if "robot_contact_assembly_tasks" not in module_names:
        fail("runtime extension.toml must expose python module robot_contact_assembly_tasks")

    setup_text = read_text(RUNTIME_SETUP)
    if 'name="robot_contact_assembly_tasks"' not in setup_text:
        fail("runtime setup.py must install robot_contact_assembly_tasks")

    for rel_path in (
        "__init__.py",
        "assets.py",
        "constants.py",
        "peg_in_hole_env_cfg.py",
        "config/franka/__init__.py",
        "mdp/observations.py",
        "mdp/events.py",
    ):
        path = RUNTIME_TASK_ROOT / rel_path
        if not path.is_file():
            fail(f"missing runtime task file: {path.relative_to(REPO_ROOT)}")


def check_runtime_install_targets() -> None:
    bad_scripts: list[str] = []
    for path in sorted((REPO_ROOT / "scripts").glob("*.sh")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if BAD_RUNTIME_ROOT_INSTALL_RE.search(text):
            bad_scripts.append(str(path.relative_to(REPO_ROOT)))
    if bad_scripts:
        fail(
            "runtime script installs the repo root instead of source/robot_contact_assembly_tasks: "
            + ", ".join(bad_scripts)
        )

    install_scripts = [
        "scripts/run_launchable_contact_physics_smoke.sh",
        "scripts/run_launchable_headless_smoke.sh",
        "scripts/run_launchable_rca_diagnostic_matrix.sh",
        "scripts/install_remote_isaaclab_runtime.sh",
    ]
    for rel_path in install_scripts:
        text = read_text(REPO_ROOT / rel_path)
        if "source/robot_contact_assembly_tasks" not in text:
            fail(f"{rel_path} must install the runtime extension from source/robot_contact_assembly_tasks")


def check_required_local_guard_scripts() -> None:
    required_scripts = [
        "scripts/refresh_brev_login.sh",
        "scripts/paid_compute_preflight.sh",
        "scripts/prepare_contact_smoke_run.sh",
        "scripts/start_brev_ui_launchable_watchdog.sh",
        "scripts/brev_paid_safety_status.sh",
        "scripts/pull_contact_smoke_log.sh",
        "scripts/archive_contact_smoke_log.sh",
        "scripts/create_brev_lifecycle_incident_bundle.sh",
        "scripts/check_brev_support_evidence.py",
        "scripts/check_brev_lifecycle_hold_clearance.sh",
        "scripts/check_launchable_retry_readiness.sh",
    ]
    for rel_path in required_scripts:
        if not (REPO_ROOT / rel_path).is_file():
            fail(f"missing required local guard script: {rel_path}")


def check_docs_name_the_two_layers() -> None:
    readme = read_text(REPO_ROOT / "README.md")
    for marker in (
        "`src/robot_contact_assembly/`: planning-side specs",
        "`source/robot_contact_assembly_tasks/`: Isaac Lab external task package",
    ):
        if marker not in readme:
            fail(f"README missing package-boundary marker: {marker}")


def main() -> int:
    check_package_boundaries()
    check_runtime_install_targets()
    check_required_local_guard_scripts()
    check_docs_name_the_two_layers()
    print("[project-structure] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
