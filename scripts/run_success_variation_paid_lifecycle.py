#!/usr/bin/env python3
"""Run one success-variation paid batch lifecycle after fresh UI balance evidence.

This is the highest-level paid entrypoint for the current success-variation
milestone. It is deliberately fail-closed: it only reaches the paid runner when
--run, --balance-eur, and --i-understand-this-can-create-paid-instance are all
provided. It first delegates to the prepare helper, then forces the aggregate
paid lifecycle preflight, then runs the guarded config runner, disarms the local env,
checks Brev safety, and finally either finalizes the dataset gate plus V0 offline
policy-readiness pipeline or writes a recovery rerun plan.

The explicit baseline-validation stage uses the same paid guards and cleanup,
but validates two fixed geometry controls, installs only a passing baseline,
and never invokes dataset finalization or the policy-readiness pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
from success_variation_stage import STAGES
import write_brev_credit_evidence as credit_writer
import seated_time_budget
import check_paid_supervision

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_RECOVERY_JSON = REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_recovery_plan_2026-06-25.json"
DEFAULT_RECOVERY_SH = REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_recovery_plan_2026-06-25.sh"
DEFAULT_CREDIT_EVIDENCE = REPO_ROOT / "configs" / "brev_credit_verification.local.json"


def _resolve(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be numeric, got {value!r}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {value!r}")
    return parsed


def _fmt(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def _read_config_value(config: Path, key: str) -> str | None:
    if not config.is_file():
        return None
    for raw_line in config.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key == key:
            return value.strip()
    return None


def _run(label: str, args: list[str]) -> int:
    print(f"[success-variation-lifecycle] {label}: {_fmt(args)}", flush=True)
    result = subprocess.run(args, cwd=REPO_ROOT, check=False)
    print(f"[success-variation-lifecycle] {label}_exit={result.returncode}", flush=True)
    return int(result.returncode)


def _build_commands(args: argparse.Namespace) -> dict[str, list[str]]:
    if getattr(args, "stage", None) == "contact-smoke":
        return _build_contact_smoke_commands(args)
    config = _resolve(args.config)
    manifest = _resolve(args.manifest)
    recovery_json = _resolve(args.recovery_json)
    recovery_sh = _resolve(args.recovery_sh)
    credit_output_raw = _read_config_value(config, "RCA_BREV_CREDIT_EVIDENCE_JSON")
    credit_output = _resolve(Path(credit_output_raw)) if credit_output_raw else DEFAULT_CREDIT_EVIDENCE
    packet_raw = _read_config_value(config, "RCA_SUCCESS_VARIATION_RUN_PACKET_JSON")
    _, _, currency_flags = credit_writer.currency_arguments(args)
    commands = {
        "prepare": [
            "python3",
            "scripts/prepare_success_variation_paid_batch.py",
            *currency_flags,
            "--budget-eur",
            f"{args.budget_eur:.2f}",
            "--config",
            str(config),
            "--credit-output",
            str(credit_output),
            "--force-credit",
            "--i-understand-this-arms-paid-run",
        ],
        "preflight": [
            "python3",
            "scripts/check_success_variation_paid_lifecycle_preflight.py",
            "--config",
            str(config),
            "--manifest",
            str(manifest),
            "--no-output",
            "--fail-on-blocked",
        ],
        "run": [
            "scripts/run_success_variation_batch_from_config.sh",
            str(config),
            "--run",
        ],
        "disarm": [
            "python3",
            "scripts/arm_success_variation_paid_env.py",
            "--config",
            str(config),
            "--output",
            str(config),
            "--disarm",
        ],
        "safety": ["./scripts/brev_paid_safety_status.sh"],
        "finalize": ["scripts/finalize_success_variation_batch.sh", str(manifest)],
        "policy_readiness": [
            "python3",
            "scripts/run_v0_offline_policy_readiness_pipeline.py",
            "--manifest",
            str(manifest),
        ],
        "recovery": [
            "python3",
            "scripts/plan_success_variation_recovery_batch.py",
            str(manifest),
            "--output-json",
            str(recovery_json),
            "--output-sh",
            str(recovery_sh),
        ],
    }
    stage = getattr(args, "stage", "variation-batch")
    commands["prepare"].extend(["--stage", stage, "--manifest", str(manifest)])
    commands["preflight"].extend(["--stage", stage])
    if packet_raw:
        commands["preflight"].extend(["--run-packet", str(_resolve(Path(packet_raw)))])
    commands["run"].append(stage)
    if stage == "baseline-validation":
        checker = ["python3", "scripts/check_corrected_geometry_baseline.py", str(manifest)]
        commands["finalize"] = [*checker, "--promote-baseline"]
        commands["recovery"] = checker
        del commands["policy_readiness"]
    return commands


def _build_contact_smoke_commands(args: argparse.Namespace) -> dict[str, list[str]]:
    """Revalidate changed physics only; never use the post-contact skill runner."""
    config = _resolve(args.config)
    def value(key):
        result = _read_config_value(config, key)
        if not result:
            raise ValueError(f"contact-smoke requires {key} in {config}")
        return result
    name = value("RCA_SUCCESS_VARIATION_ENV_NAME")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", name):
        raise ValueError("unsafe or missing contact-smoke instance name")
    instance = value("RCA_SUCCESS_VARIATION_INSTANCE_TYPE")
    ttl = int(value("RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES"))
    disk = int(value("RCA_SUCCESS_VARIATION_MIN_DISK"))
    rate = float(value("RCA_PAID_ESTIMATED_EUR_PER_HOUR"))
    suite = getattr(args, "contact_suite", "wall")
    if suite not in ("wall", "seated"):
        raise ValueError("unreviewed contact suite")
    # 900s setup + 600s smoke (including startup) + 60s kill + 300s cleanup.
    if not 31 <= ttl <= 60 or disk < 500 or not math.isfinite(rate) or rate <= 0:
        raise ValueError("contact-smoke requires 31..60 min TTL, >=500GB disk, and positive hourly estimate")
    if not 0 < args.budget_eur or rate * ttl / 60 > args.budget_eur:
        raise ValueError("contact-smoke timeout envelope exceeds explicit budget")
    # Reallocate slack to preparation without shortening either case or cleanup.
    seated_time_budget.validate()
    if suite == "seated" and (ttl != 45 or args.budget_eur > 2):
        raise ValueError("seated smoke requires exactly 45min TTL and at most EUR2")
    root = value("RCA_SUCCESS_VARIATION_REMOTE_ROOT")
    compose = value("RCA_SUCCESS_VARIATION_COMPOSE_ROOT")
    for path in (root, compose):
        if not re.fullmatch(r"/[a-zA-Z0-9_./-]+", path) or ".." in path:
            raise ValueError("unsafe remote path")
    bundle = REPO_ROOT / "artifacts/launchable" / f"robot-contact-assembly-contact-smoke-{name}.tar.gz"
    log = REPO_ROOT / "artifacts/contact_revalidation" / name / "launchable_logs/contact_physics_smoke.log"
    if log.parent.parent.exists():
        raise ValueError("contact-smoke output already exists; review it and use a new run name")
    evidence = DEFAULT_CREDIT_EVIDENCE
    _, _, currency_flags = credit_writer.currency_arguments(args)
    environment = ["env", f"RCA_CONTACT_SMOKE_SUITE={suite}", "RCA_ALLOW_PAID_BREV_CREATE=1", "RCA_BREV_CREDITS_VERIFIED=1",
                   "RCA_ACK_BREV_LIFECYCLE_RISK=1", "RCA_PAID_RUN_PURPOSE=contact_physics_smoke",
                   f"RCA_PAID_BUDGET_EUR={args.budget_eur}", f"RCA_PAID_ESTIMATED_EUR_PER_HOUR={rate}",
                   f"RCA_PAID_MAX_MINUTES={ttl}", f"RCA_CONTACT_SMOKE_MAX_MINUTES={ttl}",
                   f"RCA_CONTACT_SMOKE_BUNDLE_PATH={bundle}", "RCA_CONTACT_SMOKE_START_WATCHDOG=0",
                   "RCA_CONTACT_SMOKE_TEST_SKIP_LOCAL_QUALITY=0"]
    commands = {
        "prepare": ["python3", "scripts/write_brev_credit_evidence.py", *currency_flags,
                    "--budget-eur", str(args.budget_eur), "--output", str(evidence), "--force",
                    "--checked-instance-type", instance],
        "credit_check": ["python3", "scripts/read_brev_credit_balance.py", "--required-budget-eur",
                         str(args.budget_eur), "--credit-evidence", str(evidence), "--fail-on-blocked"],
        "safety_before": ["bash", "scripts/brev_paid_safety_status.sh"],
        "preflight": [*environment, "RCA_CONTACT_SMOKE_REQUIRE_CLEAN=1", "bash", "scripts/prepare_contact_smoke_run.sh"],
        "run": [*environment, f"RCA_FINAL_CONTACT_INSTANCE_TYPE={instance}",
                f"RCA_FINAL_CONTACT_MIN_DISK={disk}", f"RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES={ttl}",
                f"RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS={seated_time_budget.WORKLOAD_SECONDS if suite == 'seated' else 600}",
                "RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS=60",
                f"RCA_FINAL_CONTACT_TRACE_RUNNER={REPO_ROOT}/scripts/run_remote_contact_revalidation.sh",
                "RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE=0", "bash",
                "scripts/recreate_brev_and_run_final_contact_servo_trace.sh", name, root, compose,
                "RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0", "220", "42"],
        "disarm": ["python3", "scripts/arm_success_variation_paid_env.py", "--config", str(config),
                   "--output", str(config), "--disarm"],
        "safety": ["bash", "scripts/brev_paid_safety_status.sh"],
        "finalize": ["bash", "scripts/archive_contact_smoke_log.sh", str(log)],
        "recovery": ["python3", "scripts/check_phase2_contact_gate.py", "--log", str(log)],
    }
    if suite == "seated":
        checker = ["python3", "scripts/finalize_seated_contact_smoke.py", str(log.parent.parent)]
        commands["finalize"] = [*checker, "--archive-wall"]
        commands["recovery"] = checker
    return commands


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _dry_run_report(args: argparse.Namespace, commands: dict[str, list[str]]) -> dict:
    config = _resolve(args.config)
    manifest = _resolve(args.manifest)
    return {
        "status": "DRY_RUN",
        "stage": getattr(args, "stage", "variation-batch"),
        "run_requested": bool(args.run),
        "balance_eur": None if args.balance_eur is None else round(args.balance_eur, 2),
        "balance_usd": getattr(args, "balance_usd", None),
        "budget_eur": round(args.budget_eur, 2),
        "config": _rel(config),
        "manifest": _rel(manifest),
        "execution_order": [
            "prepare",
        ] + [key for key in ("credit_check", "safety_before") if key in commands] + [
            "preflight",
            "run",
            "disarm",
            "safety",
            "finalize",
        ] + (["policy_readiness"] if "policy_readiness" in commands else []) + ["safety_final"],
        "failure_order": [
            "prepare",
            "preflight",
            "run",
            "disarm",
            "safety",
            "recovery",
        ],
        "commands": commands,
        "cleanup_guards": [
            "prepare failure disarms local paid env and reruns Brev safety",
            "preflight failure disarms local paid env and reruns Brev safety",
            "cleanup or Brev safety failure blocks finalize/policy readiness",
            "run failure disarms local paid env, reruns Brev safety, and writes a recovery plan",
            "KeyboardInterrupt disarms local paid env, reruns Brev safety, and writes a recovery plan",
            "success path requires final Brev safety to pass after policy-readiness handoff",
        ],
        "side_effects": {
            "writes_credit_evidence": False,
            "arms_local_env": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "copies_artifacts": False,
            "deletes_instances": False,
            "writes_recovery_plan": False,
        },
        "not_claims": [
            "not fresh Brev UI credit evidence",
            "not an armed local env",
            "not a paid run",
            "not success-variation result evidence",
            "not cleanup evidence",
        ],
    }


def _print_dry_run(args: argparse.Namespace, commands: dict[str, list[str]]) -> None:
    report = _dry_run_report(args, commands)
    report["operational_hold"] = check_paid_supervision.report()
    print("[success-variation-lifecycle] DRY_RUN")
    print("[success-variation-lifecycle] would not create a paid instance")
    for label in ("prepare", "credit_check", "safety_before", "preflight", "run", "disarm", "safety", "finalize", "policy_readiness", "recovery"):
        if label in commands:
            print(f"- {label}: {_fmt(commands[label])}")
    print("[success-variation-lifecycle] facts=" + json.dumps(report, indent=2, sort_keys=True))


def _post_run_cleanup(commands: dict[str, list[str]]) -> int:
    """Disarm local paid acknowledgements and re-check Brev after arming or a paid run attempt."""

    hosted_status = 0
    if os.environ.get("RCA_HOSTED_CLEANUP_RUN"):
        try:
            import paid_run_hosted as hosted
            hosted.finish_owner()
        except Exception as exc:
            print("[success-variation-lifecycle] hosted cleanup unconfirmed: " + type(exc).__name__)
            hosted_status = 2
    disarm_status = _run("disarm", commands["disarm"])
    safety_status = _run("safety", commands["safety"])
    if disarm_status != 0:
        return disarm_status
    return hosted_status or safety_status


def _execute_lifecycle(args: argparse.Namespace, commands: dict[str, list[str]]) -> int:
    """Execute the paid lifecycle with fail-closed cleanup after local arming."""

    cleanup_required = True
    cleanup_done = False
    try:
        prepare_status = _run("prepare", commands["prepare"])
        if prepare_status != 0:
            cleanup_status = _post_run_cleanup(commands)
            cleanup_done = True
            if cleanup_status != 0:
                return cleanup_status
            return prepare_status

        preflight_status = 0
        for label in ("credit_check", "safety_before", "preflight"):
            if label in commands:
                preflight_status = _run(label, commands[label])
                if preflight_status != 0:
                    break
        if preflight_status != 0:
            cleanup_status = _post_run_cleanup(commands)
            cleanup_done = True
            if cleanup_status != 0:
                return cleanup_status
            return preflight_status

        if getattr(args, "hosted_cleanup", False):
            import paid_run_hosted as hosted
            hosted.launch_owner()
        run_status = _run("run", commands["run"])
        cleanup_status = _post_run_cleanup(commands)
        cleanup_done = True
        if cleanup_status != 0:
            _run("recovery", commands["recovery"])
            return cleanup_status

        if run_status != 0:
            _run("recovery", commands["recovery"])
            return run_status

        finalize_status = _run("finalize", commands["finalize"])
        if finalize_status != 0:
            _run("recovery", commands["recovery"])
            return finalize_status

        if "policy_readiness" in commands:
            policy_readiness_status = _run("policy_readiness", commands["policy_readiness"])
            if policy_readiness_status != 0:
                return policy_readiness_status

        final_safety_status = _run("safety_final", commands["safety"])
        if final_safety_status != 0:
            _run("recovery", commands["recovery"])
            return final_safety_status
        print("[success-variation-lifecycle] PASS")
        return 0
    except KeyboardInterrupt:
        print("[success-variation-lifecycle] INTERRUPTED")
        if cleanup_required and not cleanup_done:
            _post_run_cleanup(commands)
            cleanup_done = True
        _run("recovery", commands["recovery"])
        return 130
    except Exception as exc:
        print(f"[success-variation-lifecycle] FAILED: {exc}")
        return 1
    finally:
        if cleanup_required and not cleanup_done:
            _post_run_cleanup(commands)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    credit_writer.add_currency_arguments(parser, required=False)
    parser.add_argument("--budget-eur", type=_positive_float, default=6.0)
    parser.add_argument("--stage", choices=(*STAGES, "contact-smoke"), default="variation-batch")
    parser.add_argument("--contact-suite", choices=("wall", "seated"), default="wall")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--recovery-json", type=Path, default=DEFAULT_RECOVERY_JSON)
    parser.add_argument("--recovery-sh", type=Path, default=DEFAULT_RECOVERY_SH)
    parser.add_argument("--run", action="store_true", help="Actually run the paid lifecycle after all gates pass.")
    parser.add_argument("--dry-run", action="store_true", help="Print the lifecycle commands without side effects.")
    parser.add_argument("--hosted-cleanup", action="store_true",
                        help="Use the frozen one-run hosted plan; never a hold override.")
    parser.add_argument(
        "--i-understand-this-can-create-paid-instance",
        action="store_true",
        help="Required with --run because the lifecycle can create one paid Brev instance.",
    )
    args = parser.parse_args()
    if args.contact_suite != "wall" and args.stage != "contact-smoke":
        parser.error("--contact-suite seated is only valid for --stage contact-smoke")

    try:
        args.balance_eur, _, _ = credit_writer.currency_arguments(args)
        commands = _build_commands(args)
    except (ValueError, ArithmeticError) as exc:
        print(f"[success-variation-lifecycle] BLOCKED: {exc}")
        return 1
    if args.dry_run:
        _print_dry_run(args, commands)
        return 0

    blockers: list[str] = []
    if not args.run:
        blockers.append("pass --run only after checking the current Brev UI balance and budget")
    if args.balance_eur is None:
        blockers.append("pass --balance-usd with verified FX evidence, or --balance-eur only for an explicitly EUR-denominated UI balance")
    if args.stage in ("baseline-validation", "contact-smoke") and "--budget-eur" not in sys.argv[1:] and not any(
        value.startswith("--budget-eur=") for value in sys.argv[1:]
    ):
        blockers.append(f"{args.stage} requires an explicit --budget-eur; no inferred budget")
    if not args.i_understand_this_can_create_paid_instance:
        blockers.append("pass --i-understand-this-can-create-paid-instance for this one deliberate paid batch")
    if blockers:
        print("[success-variation-lifecycle] BLOCKED")
        for blocker in blockers:
            print(f"- {blocker}")
        print("[success-variation-lifecycle] no paid instance was created")
        return 1

    # Before credit writes, arming or cloud queries. Recovery is deliberately separate.
    if args.hosted_cleanup:
        try:
            import paid_run_hosted as hosted
            if args.stage != "contact-smoke" or args.contact_suite != "seated" or args.budget_eur != 2:
                raise ValueError("hosted route is restricted to this EUR2 seated diagnostic")
            plan, _ = hosted.plan_read()
            hosted.validate_integration(plan)
            if (_read_config_value(_resolve(args.config), "RCA_SUCCESS_VARIATION_ENV_NAME") != plan["target_name"]
                    or _read_config_value(_resolve(args.config), "RCA_SUCCESS_VARIATION_INSTANCE_TYPE") != plan["instance_type"]):
                raise ValueError("config differs from hosted target plan")
            # Preflight is non-creating. The owner is launched only after it passes;
            # the actual create wrapper still requires live ready-before-create.
            os.environ["RCA_HOSTED_PLAN_PREPARATION"] = hosted.sha((REPO_ROOT / hosted.PLAN).read_bytes())
        except Exception as exc:
            print("[paid-supervision] BLOCKED: hosted plan/integration invalid (" + type(exc).__name__ + ")")
            return 2
    else:
        supervision_status = check_paid_supervision.main()
        if supervision_status != 0:
            return supervision_status
    return _execute_lifecycle(args, commands)


if __name__ == "__main__":
    raise SystemExit(main())
