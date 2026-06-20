#!/usr/bin/env python3
"""Local behavior tests for project gate scripts.

These tests are intentionally offline: they do not call Brev, Isaac, Docker, or
the network. A tiny fake Brev CLI is used to exercise paid preflight behavior.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import hashlib


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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rca-gate-tests-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        fake_brev = tmp_dir / "fake-brev"
        fake_rsync = tmp_dir / "fake-rsync"
        fake_isaac = tmp_dir / "fake-isaac-python"
        fake_launchable_repo = tmp_dir / "fake-launchable-repo"
        write_fake_brev(fake_brev)
        write_fake_rsync(fake_rsync)
        write_fake_isaac_python(fake_isaac)
        write_fake_launchable_repo(fake_launchable_repo)

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
        ):
            if needle not in watchdog_meta_text:
                print(f"[gate-tests] FAIL watchdog metadata missing {needle!r}", file=sys.stderr)
                print(watchdog_meta_text, file=sys.stderr)
                raise SystemExit(1)

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
        result = run(
            ["scripts/check_brev_lifecycle_hold_clearance.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_BREV_SUPPORT_DRAFT=str(lifecycle_support_draft),
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
        assert_status(result, 2, "Launchable retry readiness blocks duplicate smoke after contact gate PASS")
        assert_contains(result, "Phase 2 contact gate already passes", "Launchable retry readiness duplicate-smoke detail")

        result = run(
            ["scripts/check_launchable_retry_readiness.sh"],
            env=paid_env(
                fake_brev,
                RCA_BREV_LIFECYCLE_HOLD_FILE=str(lifecycle_hold),
                RCA_ACK_BREV_LIFECYCLE_RISK="1",
                RCA_RETRY_READINESS_SKIP_LOCAL_QUALITY="1",
            ),
        )
        assert_status(result, 2, "Launchable retry readiness still blocks duplicate smoke with risk ack")
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
            result = run(["scripts/create_launchable_bundle.sh", str(bundle_path)])
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

        stale_scope_bundle = REPO_ROOT / "artifacts" / "launchable" / "robot-contact-assembly-contact-smoke-manual-preauth-9998-stale-scope-test.tar.gz"
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
            result = run(["python3", "scripts/project_status_report.py", "--fail-on-blocked"])
            assert_status(result, 2, "status report fails when latest bundle has stale scope")
            assert_contains(result, "Contact-smoke bundle | STALE", "status report stale scope bundle detail")
            assert_contains(result, "Latest bundle scope runtime-v0", "status report stale scope detail")
        finally:
            stale_scope_bundle.unlink(missing_ok=True)

        stale_bundle = REPO_ROOT / "artifacts" / "launchable" / "robot-contact-assembly-contact-smoke-manual-preauth-9999-stale-test.tar.gz"
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
            result = run(["python3", "scripts/project_status_report.py", "--fail-on-blocked"])
            assert_status(result, 2, "status report fails when latest bundle is stale")
            assert_contains(result, "Contact-smoke bundle | STALE", "status report stale bundle detail")
        finally:
            stale_bundle.unlink(missing_ok=True)

    print("[gate-tests] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
