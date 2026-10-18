#!/usr/bin/env python3
"""Connect the existing paid lifecycle to one independently hosted cleanup owner.

No create command lives here. The only provider mutation is one exact-ID DELETE
after a fresh, scoped inventory and bounded evidence pull. GitHub statuses carry
non-secret coordination; raw evidence is uploaded only as CMS ciphertext.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
from paid_run_os_clock import sample_os_clock
from paid_run_deadline import Contract, elapsed, offsets

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "donny-1q84/robot-contact-assembly"
WORKFLOW = ".github/workflows/rca-hosted-cleanup-check.yml"
PLAN = "configs/hosted_cleanup_plan.json"
API = "https://brevapi2.us-west-2-prod.control-plane.brev.dev/"
ORG = "org-3BaYGdtoRGmgc77Z7NHHhPSD254"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
INTEGRATION_FILES = ("scripts/paid_run_hosted.py", "scripts/test_paid_run_hosted.py",
                     "scripts/check_paid_supervision.py", "scripts/run_success_variation_paid_lifecycle.py",
                     "scripts/prepare_contact_smoke_run.sh",
                     "scripts/recreate_brev_and_run_final_contact_servo_trace.sh", WORKFLOW)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded(command, seconds, *, output=None, data=None):
    """Own/reap the complete helper group; never print command output/secrets."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise TimeoutError("no helper time remains")
    stream = output.open("xb") if output else subprocess.PIPE
    process = subprocess.Popen(command, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                               stdout=stream, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, _ = process.communicate(input=data, timeout=seconds)
        if process.returncode:
            raise RuntimeError(f"helper exit {process.returncode}")
        return stdout
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)
        if output:
            stream.close()


def github(path, body=None, *, method=None):
    command = ["gh", "api", "repos/" + REPOSITORY + path]
    if body is not None:
        command += ["--method", method or "POST", "--input", "-"]
    result = bounded(command, 20, data=json.dumps(body).encode() if body is not None else None)
    return json.loads(result) if result.strip() else None


def published(path, commit):
    data = github("/contents/" + path + "?ref=" + commit)
    if data.get("encoding") != "base64":
        raise ValueError("unexpected published file encoding")
    return base64.b64decode(data["content"], validate=False)


def plan_read(root=ROOT, *, owner_only=False, fresh_session=True):
    raw = (root / PLAN).read_bytes()
    plan = json.loads(raw)
    if (plan["schema"] != "rca-hosted-cleanup-v1" or plan["organization_id"] != ORG
            or plan["budget_eur"] != 2 or plan["ttl_seconds"] != 2700
            or not re.fullmatch(r"rca-seated-[a-z0-9-]{8,45}", plan["target_name"])
            or plan["remote_root"] != "/home/ubuntu/projects/robot-contact-assembly"
            or not ID.fullmatch(plan["validation_run_id"])):
        raise ValueError("unreviewed hosted cleanup plan")
    if not owner_only and time.time() + (3000 if fresh_session else 0) >= plan["credential_not_after_utc"]:
        raise ValueError("credential does not cover original run and cleanup")
    required = {"scripts/paid_run_hosted.py", "scripts/check_paid_supervision.py",
                "scripts/run_success_variation_paid_lifecycle.py",
                "scripts/recreate_brev_and_run_final_contact_servo_trace.sh"}
    if not required <= set(plan["source_sha256"]):
        raise ValueError("incomplete frozen source manifest")
    if plan["recipient_certificate"] != "configs/hosted_evidence_recipient.pem":
        raise ValueError("unexpected evidence recipient path")
    owner_files = {"scripts/paid_run_hosted.py", "scripts/paid_run_os_clock.py",
                   "scripts/paid_run_deadline.py", "scripts/seated_time_budget.py", WORKFLOW}
    for name, digest in plan["source_sha256"].items():
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError("unsafe source manifest")
        if owner_only and name not in owner_files:
            continue
        if sha((root / name).read_bytes()) != digest:
            raise ValueError("frozen source changed: " + name)
    if sha((root / plan["recipient_certificate"]).read_bytes()) != plan["recipient_sha256"]:
        raise ValueError("evidence recipient changed")
    if not owner_only:
        from source_payload_fingerprint import source_payload_fingerprint
        if source_payload_fingerprint(root) != plan["runtime_sha256"]:
            raise ValueError("frozen physical runtime source changed")
    return plan, raw


def validate_integration(plan):
    run = github("/actions/runs/" + plan["validation_run_id"])
    if (run["status"] != "completed" or run["conclusion"] != "success"
            or run["run_attempt"] != 1 or run["event"] != "workflow_dispatch"
            or run["path"] != WORKFLOW or "integration-check" not in run["display_title"]):
        raise ValueError("hosted integration verification is not successful")
    for name in INTEGRATION_FILES:
        if sha(published(name, run["head_sha"])) != sha((ROOT / name).read_bytes()):
            raise ValueError("integration-tested source differs: " + name)


def status_write(commit, run_id, phase, description, state="pending"):
    if len(description) > 140:
        raise ValueError("public coordination record too long")
    return github("/statuses/" + commit, {"state": state,
                  "context": f"rca/cleanup/{run_id}/{phase}", "description": description,
                  "target_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"})


def status_read(commit, run_id, phase):
    context = f"rca/cleanup/{run_id}/{phase}"
    rows = github("/commits/" + commit + "/statuses?per_page=100")
    found = [row for row in rows if row["context"] == context]
    if len(found) > 1:
        raise ValueError("duplicate coordination record: " + phase)
    return found[0] if found else None


def active_owner(run_id, *, allow_completed=False):
    if not str(run_id).isdigit():
        raise ValueError("exact cleanup workflow run ID required")
    plan, raw = plan_read(fresh_session=False)
    run = github("/actions/runs/" + str(run_id))
    if (run["run_attempt"] != 1 or run["event"] != "workflow_dispatch" or run["path"] != WORKFLOW
            or "instance-cleanup" not in run["display_title"]
            or run["status"] not in ({"in_progress", "completed"} if allow_completed else {"in_progress"})):
        raise ValueError("independent cleanup owner unavailable or wrong run")
    if published(PLAN, run["head_sha"]) != raw:
        raise ValueError("cleanup owner has a different frozen plan")
    ready = status_read(run["head_sha"], run_id, "ready")
    if not ready or ready["state"] != "pending" or ready["creator"]["login"] != "github-actions[bot]":
        raise ValueError("independent ready-before-create receipt missing")
    state = json.loads(ready["description"])
    if set(state) != {"origin", "plan"} or state["plan"] != sha(raw):
        raise ValueError("readiness is not bound to this plan")
    # Continuation retains the original window; it must not require a fresh TTL.
    if state["origin"] + 3000 >= plan["credential_not_after_utc"]:
        raise ValueError("credential did not cover the original owner window")
    if not 0 <= time.time() - state["origin"] < 2700:
        raise ValueError("original deadline closed or clock uncertain")
    return plan, run, state


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Provider:
    def __init__(self, key):
        if not key.startswith("bak-") or any(c.isspace() for c in key):
            raise ValueError("scoped API key required")
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, timeout=15):
        if path.startswith("/") or ".." in path:
            raise ValueError("invalid provider path")
        request = urllib.request.Request(API + path, method=method, headers={
            "Authorization": "Bearer " + self.key, "Accept": "application/json"})
        # No redirects, retry handler, CLI name resolution, or 403 replay.
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError("provider response exceeds bounded size")
                if not 200 <= response.status < 300:
                    raise ValueError("provider response not successful")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise RuntimeError(f"provider HTTP {status}; not retried") from None

    def inventory(self):
        rows = self.request("GET", "api/organizations/" + ORG + "/workspaces")
        if rows is None:
            rows = []  # Official Go API serializes nil workspace slice as null.
        if not isinstance(rows, list):
            raise ValueError("organization inventory unknown")
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or not ID.fullmatch(row["id"]) or row["id"] in seen
                    or row.get("organizationId") != ORG or not isinstance(row.get("name"), str)):
                raise ValueError("invalid scoped inventory")
            seen.add(row["id"])
        return rows


def bind_target(plan, rows, bound=None):
    matches = [r for r in rows if r["name"] == plan["target_name"]]
    if len(matches) > 1:
        raise ValueError("ambiguous instance identity")
    if bound and any(r["id"] == bound["id"] and r["name"] != bound["name"] for r in rows):
        raise ValueError("bound ID renamed")
    if not matches:
        return bound
    row = matches[0]
    if row.get("organizationId") != ORG or row.get("instanceType") != plan["instance_type"]:
        raise ValueError("wrong instance organization/type")
    if bound and row["id"] != bound["id"]:
        raise ValueError("same-name replacement is not the original target")
    return {"id": row["id"], "name": row["name"], "organizationId": ORG,
            "instanceType": row["instanceType"]}


def exact_present(provider, plan, target):
    rows = provider.inventory()
    bind_target(plan, rows, target)
    return any(r["id"] == target["id"] for r in rows), not rows


def write_private(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def recover_exact(provider, plan, target, root, remaining, pull, *, pull_seconds=150, post_pull_reserve=90):
    """One owner, one mutation; an existing intent forbids every replay."""
    report = {"instance_id": target["id"], "artifacts_recovered": False,
              "delete_calls": 0, "target_absent": False, "organization_empty": False, "errors": []}
    intent = root / "delete-intent.json"
    present, empty = exact_present(provider, plan, target)
    if not present:
        return dict(report, target_absent=True, organization_empty=empty,
                    errors=["already absent; artifact recovery unverified"])
    try:
        if remaining() < post_pull_reserve + 1:
            raise TimeoutError("insufficient pullback reserve")
        pull(min(pull_seconds, remaining() - post_pull_reserve))
        report["artifacts_recovered"] = True
    except Exception as exc:
        report["errors"].append("pullback:" + type(exc).__name__)
    present, empty = exact_present(provider, plan, target)
    if present:
        if intent.exists():
            report["errors"].append("prior delete intent; outcome unknown; no replay")
        else:
            if remaining() < 35:
                raise TimeoutError("insufficient deletion reserve")
            write_private(intent, {"target": target, "utc": time.time(), "operation": "DELETE"})
            report["delete_calls"] = 1
            try:
                provider.request("DELETE", "api/workspaces/" + target["id"], min(25, remaining() - 10))
            except Exception as exc:
                report["errors"].append("delete outcome unknown:" + type(exc).__name__)
        while remaining() > 17:
            try:
                present, empty = exact_present(provider, plan, target)
            except Exception:
                report["errors"].append("reconciliation query unavailable")
                time.sleep(min(5, max(0, remaining() - 16)))
                continue
            if not present:
                break
            time.sleep(min(5, max(0, remaining() - 16)))
    report.update(target_absent=not present, organization_empty=empty)
    return report


def seal_evidence(root, certificate, output):
    archive = root.parent / "private-evidence.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname="evidence")
    bounded(["openssl", "cms", "-encrypt", "-binary", "-aes-256-cbc", "-outform", "DER",
             "-in", str(archive), "-out", str(output), str(certificate)], 20)
    if not output.is_file() or not output.stat().st_size:
        raise ValueError("encrypted evidence missing")
    return sha(output.read_bytes())


def watch():
    plan, raw = plan_read(owner_only=True)
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or sys.platform != "linux"):
        raise ValueError("only the one fresh hosted Linux owner may run")
    run_id, commit = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_SHA"]
    provider = Provider(os.environ["BREV_API_KEY"])
    if provider.inventory():
        raise ValueError("account not empty before readiness")
    root = Path(os.environ["RUNNER_TEMP"]) / "rca-private"
    root.mkdir(mode=0o700)
    contract = Contract(run_id, ORG, plan["target_name"], sample_os_clock())
    write_private(root / "contract.json", contract.payload())
    write_private(root / "plan.json", plan)
    status_write(commit, run_id, "ready", json.dumps({"origin": contract.anchor.utc, "plan": sha(raw)}, separators=(",", ":")))
    target, access_checked, report = None, False, None
    cli = os.environ["RCA_BREV_CLI"]
    def age():
        return elapsed(contract, sample_os_clock())
    def remaining():
        return max(0, offsets()["cleanup_end"] - age())
    def pull(seconds):
        bounded([cli, "refresh"], min(30, seconds / 3))
        name = target["name"]
        present, _ = exact_present(provider, plan, target)
        if not present:
            raise ValueError("target disappeared before pull")
        destination = root / "remote"
        destination.mkdir()
        bounded(["rsync", "-a", "--timeout=30", "-e",
                 "ssh -T -o BatchMode=yes -o ConnectTimeout=10 -o ForwardAgent=no -o ServerAliveInterval=10 -o ServerAliveCountMax=2",
                 name + ":" + plan["remote_root"] + "/artifacts/", str(destination) + "/"],
                max(1, min(seconds - 35, remaining() - 90)))
        files = [p for p in destination.rglob("*") if p.is_file() and not p.is_symlink()]
        if not files:
            raise ValueError("no recovered raw files")
        write_private(root / "recovered-hashes.json", {str(p.relative_to(destination)): sha(p.read_bytes()) for p in files})
    try:
        while age() < offsets()["cleanup_start"]:
            rows = provider.inventory()
            observed = bind_target(plan, rows, target)
            if observed and target is None:
                target = observed
                write_private(root / "target.json", target)
                status_write(commit, run_id, "bound", target["id"])
            if status_read(commit, run_id, "finish"):
                break
            # Admission closes after 120s, but a submitted create may appear
            # later. Continue observation without resetting the original TTL.
            if target and not access_checked and status_read(commit, run_id, "probe"):
                access_checked = True
                bounded([cli, "refresh"], 30)
                present, _ = exact_present(provider, plan, target)
                if not present:
                    raise ValueError("target disappeared before access check")
                canary = bounded(["ssh", "-T", "-o", "BatchMode=yes", "-o", "ForwardAgent=no",
                                  "-o", "ConnectTimeout=10", target["name"],
                                  "cat " + plan["remote_root"] + "/artifacts/cleanup-canary.txt"], 25)
                if canary != (plan["target_name"] + "\n").encode():
                    raise ValueError("independent target canary mismatch")
                (root / "canary.txt").write_bytes(canary)
                status_write(commit, run_id, "access", target["id"], "success")
            time.sleep(5)
    except Exception as exc:
        write_private(root / "watch-error.json", {"error": type(exc).__name__})
    finally:
        try:
            if target is not None:
                present, _ = exact_present(provider, plan, target)
                if not present:
                    raise ValueError("target absent before recovery")
                pull(min(150, remaining() - 130))
                report = {"artifacts_recovered": True}
            else:
                report = {"artifacts_recovered": False, "error": "creation not observed"}
        except Exception as exc:
            report = {"artifacts_recovered": False, "error": type(exc).__name__}
        finally:
            write_private(root / "pullback-report.json", report)
            output = ROOT / "sealed-evidence"
            output.mkdir(exist_ok=False)
            checksum = seal_evidence(root, ROOT / plan["recipient_certificate"], output / "recovered.cms")
            status_write(commit, run_id, "recovered", checksum,
                         "success" if report["artifacts_recovered"] else "failure")
    return 0 if report["artifacts_recovered"] else 2


def delete_uploaded():
    """Runs only AFTER upload-artifact: raw evidence is off this VM first."""
    from paid_run_deadline import Clock
    plan, _ = plan_read(owner_only=True)
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1" or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("wrong hosted cleanup execution")
    root = Path(os.environ["RUNNER_TEMP"]) / "rca-private"
    saved = json.loads((root / "contract.json").read_text())
    contract = Contract(saved["run_id"], saved["organization_id"], saved["target_name"], Clock(**saved["anchor"]))
    if saved != contract.payload() or contract.run_id != os.environ["GITHUB_RUN_ID"]:
        raise ValueError("original cleanup contract changed")
    provider = Provider(os.environ["BREV_API_KEY"])
    report = None
    def remaining():
        return max(0, offsets()["cleanup_end"] - elapsed(contract, sample_os_clock()))
    def uploaded(_):
        staged = json.loads((root / "pullback-report.json").read_text())
        ident = os.environ.get("RCA_RECOVERED_ARTIFACT_ID", "")
        if not staged["artifacts_recovered"] or not ident.isdigit():
            raise ValueError("private raw upload unconfirmed")
        artifact = github("/actions/artifacts/" + ident)
        if (artifact["workflow_run"]["id"] != int(contract.run_id)
                or artifact["name"] != "rca-private-" + contract.run_id
                or artifact["expired"] or artifact["size_in_bytes"] <= 0):
            raise ValueError("wrong uploaded private artifact")
    try:
        target_path = root / "target.json"
        if target_path.is_file():
            report = recover_exact(provider, plan, json.loads(target_path.read_text()), root, remaining, uploaded,
                                   pull_seconds=20, post_pull_reserve=35)
        else:
            report = {"artifacts_recovered": False, "target_absent": not provider.inventory(),
                      "errors": ["creation unknown; no exact target deletion"]}
    finally:
        write_private(root / "cleanup-report.json", report)
        output = ROOT / "sealed-evidence" / "cleanup.cms"
        checksum = seal_evidence(root, ROOT / plan["recipient_certificate"], output)
        ok = bool(report and report.get("target_absent") and report.get("organization_empty")
                  and report.get("artifacts_recovered") and not report.get("errors"))
        status_write(os.environ["GITHUB_SHA"], contract.run_id, "result", checksum, "success" if ok else "failure")
    return 0 if ok else 2


def launch_owner():
    plan, raw = plan_read()
    validate_integration(plan)
    head = github("/commits/master")["sha"]
    if published(PLAN, head) != raw:
        raise ValueError("published plan is not the frozen local plan")
    previous = github("/actions/workflows/" + WORKFLOW.rsplit("/", 1)[1] + "/runs?per_page=20")["workflow_runs"]
    for run in previous:
        if "instance-cleanup" in run["display_title"] and run["head_sha"] == head:
            raise ValueError("this frozen plan already has an owner; no duplicate dispatch")
    github("/actions/workflows/" + WORKFLOW.rsplit("/", 1)[1] + "/dispatches",
           {"ref": "master", "inputs": {"mode": "instance-cleanup", "fault": "group-kill", "source_run_id": "0"}})
    end = time.monotonic() + 150
    while time.monotonic() < end:
        rows = github("/actions/workflows/" + WORKFLOW.rsplit("/", 1)[1] + "/runs?per_page=20")["workflow_runs"]
        matches = [r for r in rows if r["head_sha"] == head and "instance-cleanup" in r["display_title"]]
        if len(matches) > 1:
            raise ValueError("duplicate owner runs; refuse creation")
        if matches:
            run_id = str(matches[0]["id"])
            os.environ["RCA_HOSTED_CLEANUP_RUN"] = run_id
            try:
                _, _, state = active_owner(run_id)
                if time.time() - state["origin"] > 60:
                    raise ValueError("late owner readiness")
                os.environ["RCA_HOSTED_ORIGIN_UTC"] = str(state["origin"])
                return run_id
            except ValueError:
                if matches[0]["status"] == "completed":
                    raise
        time.sleep(3)
    raise TimeoutError("cleanup dispatch readiness unknown; no instance created")


def request_phase(phase):
    run_id = os.environ["RCA_HOSTED_CLEANUP_RUN"]
    _, run, _ = active_owner(run_id)
    old = status_read(run["head_sha"], run_id, phase)
    if not old:
        status_write(run["head_sha"], run_id, phase, "requested by the formal lifecycle")
    return run_id


def check_before_create(name):
    plan, run, state = active_owner(os.environ["RCA_HOSTED_CLEANUP_RUN"])
    if name != plan["target_name"] or time.time() - state["origin"] > 120:
        raise ValueError("wrong target or creation window closed")
    if float(os.environ.get("RCA_HOSTED_ORIGIN_UTC", "nan")) != state["origin"]:
        raise ValueError("local origin differs from independent receipt")
    if status_read(run["head_sha"], str(run["id"]), "bound") or status_read(run["head_sha"], str(run["id"]), "finish"):
        raise ValueError("create was already observed or cleanup requested")
    return state


def admit_workload(path):
    from paid_run_deadline import Clock, PHASES, preparation_admission
    plan, run, state = active_owner(os.environ["RCA_HOSTED_CLEANUP_RUN"])
    if time.time() >= state["origin"] + offsets()["preparation"]:
        raise TimeoutError("original preparation budget exhausted")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if len(rows) != 12:
        raise ValueError("all six actual preparation pairs required")
    phases = []
    for index, name in enumerate(PHASES):
        start, end = rows[index * 2:index * 2 + 2]
        if (start["phase"] != name or end["phase"] != name or start["event"] != "start"
                or end["event"] != "end" or start["lifecycle_pid"] != end["lifecycle_pid"]
                or start["lifecycle_pid"] != rows[0]["lifecycle_pid"]):
            raise ValueError("preparation receipts not from one actual lifecycle")
        phases.append({"name": name, "start": start["clock"], "end": end["clock"], "exit_code": end["exit_code"]})
    # Actual Mac clock anchors validate local ordering only. The independent
    # Linux origin above remains the earlier absolute billing deadline.
    contract = Contract(str(run["id"]), ORG, plan["target_name"], Clock(**rows[0]["clock"]))
    result = preparation_admission(contract, sample_os_clock(), phases)
    if not result["workload_timing_admissible"]:
        raise ValueError("actual preparation phase audit failed")
    access = status_read(run["head_sha"], str(run["id"]), "access")
    bound = status_read(run["head_sha"], str(run["id"]), "bound")
    if (not access or access["state"] != "success" or not bound
            or access["description"] != bound["description"]):
        raise ValueError("independent exact-target data access not acknowledged")
    write_private(path.parent / "preparation-admission.json", result)
    return result


def finish_owner():
    run_id = os.environ["RCA_HOSTED_CLEANUP_RUN"]
    plan, run, state = active_owner(run_id, allow_completed=True)
    if run["status"] != "completed":
        request_phase("finish")
    end = state["origin"] + 2700
    while time.time() < end:
        current = github("/actions/runs/" + run_id)
        if current["status"] == "completed":
            result = status_read(run["head_sha"], run_id, "result")
            if current["conclusion"] != "success" or not result or result["state"] != "success":
                raise RuntimeError("hosted cleanup or encrypted upload not confirmed")
            return
        time.sleep(5)
    raise TimeoutError("original cleanup deadline expired")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("watch", "delete-uploaded", "finish", "probe", "remaining", "admit"))
    parser.add_argument("--phases", type=Path)
    args = parser.parse_args()
    if args.operation == "watch":
        return watch()
    if args.operation == "delete-uploaded":
        return delete_uploaded()
    if args.operation == "finish":
        finish_owner()
    elif args.operation == "admit":
        admit_workload(args.phases)
    elif args.operation == "probe":
        run_id = request_phase("probe")
        _, run, state = active_owner(run_id)
        end = min(time.time() + 75, state["origin"] + 1080)
        while time.time() < end:
            result = status_read(run["head_sha"], run_id, "access")
            if result and result["state"] == "success":
                return 0
            time.sleep(3)
        raise TimeoutError("independent data recovery path not confirmed")
    else:
        _, _, state = active_owner(os.environ["RCA_HOSTED_CLEANUP_RUN"])
        print(max(0, int(state["origin"] + 1080 - time.time())))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Provider/CLI error bodies may contain private fields. Keep them private.
        print("[hosted-cleanup] " + type(exc).__name__ + "; action unconfirmed", file=sys.stderr)
        raise SystemExit(2)
