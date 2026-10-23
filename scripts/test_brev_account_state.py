#!/usr/bin/env python3
"""Offline regressions for scoped-key organization checks and empty inventories."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch

sys.dont_write_bytecode = True
import diagnose_brev_credit_blocker as diagnosis
import wait_brev_instance_ready as ready_gate

ROOT = Path(__file__).resolve().parents[1]
ORG = diagnosis.credit_gate.EXPECTED_ORG_ID
TABLE = f"Your organizations:\n NAME ID\n * NCA-57cf-29515 {ORG}\n"
UNSUPPORTED = "api key auth cannot list organizations"


def response(*, code=0, stdout="", stderr="", payload=None):
    return {"exit_code": code, "stdout": stdout, "stderr_tail": stderr,
            "json": payload, "command": ["fake-brev"]}


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(diagnosis.subprocess, "run", side_effect=AssertionError("Unmocked CLI call"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_json_user_login_keeps_existing_path(self):
        organizations = [{"id": ORG, "is_active": True}]
        with patch.object(diagnosis, "_run_brev", return_value=response(payload=organizations)) as run:
            result = diagnosis._query_organizations(timeout_seconds=2)
        self.assertEqual(diagnosis._active_org(result)["id"], ORG)
        self.assertEqual(result["source"], "cli_organizations_json")
        run.assert_called_once_with(["ls", "orgs", "--json"], timeout_seconds=2)

    def test_scoped_api_key_uses_one_read_only_fallback(self):
        with patch.object(diagnosis, "_run_brev", side_effect=[
            response(code=1, stderr=UNSUPPORTED), response(stdout=TABLE)
        ]) as run:
            result = diagnosis._query_organizations(timeout_seconds=2)
        self.assertEqual(diagnosis._active_org(result)["id"], ORG)
        self.assertEqual(result["source"], "cli_scoped_organization_table")
        self.assertEqual(run.call_args_list, [
            call(["ls", "orgs", "--json"], timeout_seconds=2),
            call(["org", "ls"], timeout_seconds=2)])

    def test_auth_network_and_malformed_json_do_not_trigger_fallback(self):
        results = [response(code=1, stderr="login expired"), response(code=None, stderr="timeout"),
                   response(code=1, stderr=UNSUPPORTED + "\nnetwork failure"),
                   response(stdout=UNSUPPORTED), response(stdout="malformed JSON")]
        for original in results:
            with self.subTest(original=original), patch.object(diagnosis, "_run_brev", return_value=original) as run:
                result = diagnosis._query_organizations(timeout_seconds=2)
                self.assertEqual(diagnosis._active_org(result), {})
                run.assert_called_once()

    def test_only_complete_single_active_org_table_is_accepted(self):
        bad = ["", f"* NCA-57cf-29515 {ORG}", TABLE.replace("* ", ""),
               TABLE + f" * Other {ORG}\n", TABLE + "unexpected extra text\n",
               TABLE.replace("NAME ID", "NAME"), TABLE.replace(ORG, "not-an-id"),
               TABLE.replace("* ", "** "), TABLE.replace("NCA-57cf-29515", "NCA\x00bad")]
        for table in bad:
            with self.subTest(table=table):
                self.assertIsNone(diagnosis._scoped_org_table(table))
        colored = TABLE.replace("* NCA", "\x1b[32m* NCA").replace(ORG, ORG + "\x1b[0m")
        self.assertEqual(diagnosis._scoped_org_table(colored)[0]["id"], ORG)

    def test_failed_or_partial_fallback_cannot_establish_active_org(self):
        for fallback in (response(code=1, stdout=TABLE), response(stdout="Your organizations:")):
            with self.subTest(fallback=fallback), patch.object(diagnosis, "_run_brev", side_effect=[
                response(code=1, stderr=UNSUPPORTED), fallback
            ]):
                result = diagnosis._query_organizations(timeout_seconds=2)
                self.assertEqual(diagnosis._active_org(result), {})

    def test_wrong_org_is_not_replaced_with_expected_org(self):
        active = diagnosis._scoped_org_table(TABLE.replace(ORG, "org-wrong"))[0]
        status, _ = diagnosis._status(review={}, active_org=active, visible_instances=0)
        self.assertEqual(status, "WRONG_ACTIVE_ORG")

    def test_cli_is_bounded_and_noninteractive(self):
        with patch.object(diagnosis.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run:
            diagnosis._run_brev(["org", "ls"], timeout_seconds=3)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_build_report_uses_scoped_query_without_authorizing_spend(self):
        review = {"status": "NEEDS_BREV_UI_CREDIT_EVIDENCE",
                  "api_credit_balance": {"status": "PASS", "balance_usd": 7.11},
                  "credit_consistency": {"paid_prepare_allowed": False, "next_action": "review"}}
        with patch.object(diagnosis, "_run_brev", side_effect=[
            response(code=1, stderr=UNSUPPORTED), response(stdout=TABLE),
            response(payload={"workspaces": None}), response(stdout="0.6.335")
        ]), patch.object(diagnosis.credit_review, "build_packet", return_value=review):
            report = diagnosis.build_report(config_path=Path("unused"), manifest_path=Path("unused"),
                run_packet_path=Path("unused"), balance_eur=None, api_credit_output=None,
                command_timeout_seconds=2)
        self.assertEqual(report["active_organization"]["id"], ORG)
        self.assertEqual(report["visible_instances"], 0)
        self.assertEqual(report["org_query_source"], "cli_scoped_organization_table")
        self.assertFalse(report["paid_prepare_allowed"])
        self.assertFalse(report["side_effects"]["creates_paid_instance"])


class SafetyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rca-account-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        fake = self.folder / "brev"
        fake.write_text("#!/bin/sh\ncase \"$*\" in\n"
                        "healthcheck) printf 'Healthy!\\n' ;;\n"
                        f"'org ls') printf 'Your organizations:\\n NAME ID\\n * Test {ORG}\\n' ;;\n"
                        "'ls instances --json --all') printf '%s\\n' \"$FAKE_INSTANCE_OUTPUT\"; exit \"${FAKE_INSTANCE_EXIT:-0}\" ;;\n"
                        "*) exit 97 ;;\nesac\n")
        fake.chmod(0o755)
        hold = self.folder / "hold.md"
        hold.write_text("Test-only active hold\n")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("RCA_", "FAKE_", "BREV_"))}
        self.env.update(RCA_BREV_CLI=str(fake), RCA_BREV_SAFETY_QUERY_TIMEOUT_SECONDS="3",
                        RCA_BREV_WATCHDOG_LEDGER_ROOT=str(self.folder / "ledgers"),
                        RCA_BREV_LIFECYCLE_HOLD_FILE=str(hold),
                        PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))

    def run_safety(self, output, code=0):
        return subprocess.run(["bash", str(ROOT / "scripts/brev_paid_safety_status.sh")],
            cwd=ROOT, env={**self.env, "FAKE_INSTANCE_OUTPUT": output, "FAKE_INSTANCE_EXIT": str(code)},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)

    def test_explicit_null_and_empty_list_are_valid_empty_inventories(self):
        for workspaces in (None, []):
            with self.subTest(workspaces=workspaces):
                result = self.run_safety(json.dumps({"workspaces": workspaces}))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("status=SAFE_NO_VISIBLE_PAID_INSTANCE", result.stdout)

    def test_malformed_or_wrong_schema_never_means_empty(self):
        for value in ({}, [], None, False, {"instances": []}, {"workspaces": ""},
                      {"workspaces": {}}, {"workspaces": False}, {"workspaces": [None]}):
            with self.subTest(value=value):
                result = self.run_safety(json.dumps(value))
                self.assertEqual(result.returncode, 2)
                self.assertIn("visible_instances=unknown", result.stderr)
                self.assertNotIn("status=SAFE_NO_VISIBLE_PAID_INSTANCE", result.stdout)

    def test_failed_query_cannot_establish_empty_inventory(self):
        result = self.run_safety('{"workspaces":null}', code=1)
        self.assertEqual(result.returncode, 2)
        self.assertIn("instance_list=fail", result.stderr)

    def test_visible_instance_still_blocks(self):
        result = self.run_safety('{"workspaces":[{"id":"test-instance"}]}')
        self.assertEqual(result.returncode, 2)
        self.assertIn("visible_instances=1", result.stderr)


class InstanceReadinessTests(unittest.TestCase):
    def row(self, **changes):
        return {"workspaces": [{"name": "offline-target", "id": "offline-id", "instance_type": "offline-l4",
                "status": "RUNNING", "build_status": "COMPLETED", "shell_status": "READY",
                "health_status": "HEALTHY", **changes}]}

    def test_running_is_not_software_ready(self):
        for changes in ({"build_status": "BUILDING", "shell_status": "NOT READY"},
                        {"shell_status": "NOT READY"}, {"health_status": "UNAVAILABLE"}):
            self.assertFalse(ready_gate.readiness(self.row(**changes), "offline-target", "offline-l4")[0])
        self.assertTrue(ready_gate.readiness(self.row(), "offline-target", "offline-l4")[0])

    def test_bootstrap_health_alias_is_wait_only_not_ready(self):
        payload = self.row(status="UNHEALTHY", health_status="UNHEALTHY",
                           build_status="BUILDING", shell_status="NOT READY")
        self.assertFalse(ready_gate.readiness(payload, "offline-target", "offline-l4")[0])
        replies = [subprocess.CompletedProcess([], 0, json.dumps(payload)),
                   subprocess.CompletedProcess([], 0, json.dumps(self.row()))]
        with patch.object(ready_gate.subprocess, "run", side_effect=replies) as run, \
             patch.object(ready_gate.time, "sleep"), patch.object(ready_gate.time, "monotonic", return_value=0):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 900)
        self.assertEqual(run.call_count, 2)
        for call_ in run.call_args_list:
            self.assertEqual(call_.args[0][1:], ["ls", "instances", "--json", "--all"])
        for changes in ({"build_status": "COMPLETED"}, {"shell_status": "READY"},
                        {"health_status": "UNKNOWN"}, {"name": "other"}):
            invalid = {"workspaces": [{**payload["workspaces"][0], **changes}]}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ready_gate.readiness(invalid, "offline-target", "offline-l4")

    def test_wrong_missing_or_failed_instance_is_blocked(self):
        cases = [{}, {"workspaces": None}, {"workspaces": []}, {"workspaces": [None]},
                 self.row(name="different"), self.row(instance_type="different"), self.row(id=True),
                 self.row(status="STOPPING"), self.row(build_status="CREATE_FAILED"),
                 self.row(health_status="UNHEALTHY"), self.row(shell_status=None)]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                ready_gate.readiness(payload, "offline-target", "offline-l4")

    def test_wait_is_read_only_bounded_and_tracks_build_transition(self):
        replies = [subprocess.CompletedProcess([], 0, json.dumps(self.row(build_status="BUILDING", shell_status="NOT READY"))),
                   subprocess.CompletedProcess([], 0, json.dumps(self.row()))]
        with patch.object(ready_gate.subprocess, "run", side_effect=replies) as run, \
             patch.object(ready_gate.time, "sleep"), patch.object(ready_gate.time, "monotonic", return_value=0):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 30)
        self.assertEqual(run.call_count, 2)
        for call_ in run.call_args_list:
            self.assertEqual(call_.args[0], ["offline-brev", "ls", "instances", "--json", "--all"])
            self.assertEqual(call_.kwargs["stdin"], subprocess.DEVNULL)
            self.assertLessEqual(call_.kwargs["timeout"], 30)

    def test_single_read_timeout_does_not_advance_or_recreate(self):
        replies = [subprocess.TimeoutExpired(["offline-brev"], 45),
                   subprocess.CompletedProcess([], 0, json.dumps(self.row(build_status="BUILDING", shell_status="NOT READY"))),
                   subprocess.TimeoutExpired(["offline-brev"], 45),
                   subprocess.TimeoutExpired(["offline-brev"], 45),
                   subprocess.CompletedProcess([], 0, json.dumps(self.row()))]
        with patch.object(ready_gate.subprocess, "run", side_effect=replies) as run, \
             patch.object(ready_gate.time, "sleep"), patch.object(ready_gate.time, "monotonic", return_value=0):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 900)
        self.assertEqual(run.call_count, 5)
        for call_ in run.call_args_list:
            self.assertEqual(call_.args[0], ["offline-brev", "ls", "instances", "--json", "--all"])
            self.assertEqual(call_.kwargs["timeout"], 45)

    def test_repeated_read_timeouts_are_bounded(self):
        with patch.object(ready_gate.subprocess, "run", side_effect=subprocess.TimeoutExpired(["offline-brev"], 45)) as run, \
             patch.object(ready_gate.time, "sleep"), patch.object(ready_gate.time, "monotonic", return_value=0), \
             self.assertRaisesRegex(TimeoutError, "consecutive read-only"):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 900)
        self.assertEqual(run.call_count, 3)

    def test_transient_timeout_never_extends_total_deadline(self):
        with patch.object(ready_gate.subprocess, "run", side_effect=subprocess.TimeoutExpired(["offline-brev"], 5)) as run, \
             patch.object(ready_gate.time, "sleep") as sleep, \
             patch.object(ready_gate.time, "monotonic", side_effect=[0, 895, 900, 901]), \
             self.assertRaisesRegex(TimeoutError, "deadline expired"):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 900)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        run.assert_called_once()
        sleep.assert_called_once_with(0)

    def test_deadline_and_query_error_do_not_allow_bootstrap(self):
        with patch.object(ready_gate.time, "monotonic", side_effect=[0, 31]), \
             patch.object(ready_gate.subprocess, "run") as run, self.assertRaises(TimeoutError):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 30)
        run.assert_not_called()
        with patch.object(ready_gate.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["offline"])) as run, \
             self.assertRaises(subprocess.CalledProcessError):
            ready_gate.wait_ready("offline-brev", "offline-target", "offline-l4", 30)
        run.assert_called_once()

    def test_wait_refresh_bootstrap_order_and_no_uninitialized_pull(self):
        source = (ROOT / "scripts/recreate_brev_and_run_final_contact_servo_trace.sh").read_text()
        wait = source.index('python3 "${SCRIPT_DIR}/wait_brev_instance_ready.py"')
        refresh = source.index('--refresh-ssh', wait)
        bootstrap = source.index('"${SCRIPT_DIR}/bootstrap_brev_workspace.sh"', refresh)
        self.assertLess(wait, refresh)
        self.assertLess(refresh, bootstrap)
        self.assertLess(bootstrap, source.index("REMOTE_INITIALIZED=1"))
        self.assertIn('if [[ "${REMOTE_INITIALIZED}" != "1" ]]', source)
        pull = (ROOT / "scripts/pull_artifacts.sh").read_text()
        for bound in ("--timeout=60", "BatchMode=yes", "ConnectTimeout=15", "ServerAliveCountMax=2"):
            self.assertIn(bound, pull)

    def test_pending_poll_is_slow_and_bounded(self):
        replies = [subprocess.CompletedProcess([], 0, json.dumps(self.row(build_status="BUILDING"))),
                   subprocess.CompletedProcess([], 0, json.dumps(self.row()))]
        with patch.object(ready_gate.subprocess, "run", side_effect=replies), \
             patch.object(ready_gate.time, "sleep") as sleep, \
             patch.object(ready_gate.time, "monotonic", return_value=0):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900)
        sleep.assert_called_once_with(60)

    def test_inventory_rate_limit_cools_down_but_does_not_mean_ready(self):
        limited = subprocess.CalledProcessError(1, ["offline"], output="rate limit exceeded\n")
        replies = [limited, subprocess.CompletedProcess([], 0, json.dumps(self.row()))]
        with patch.object(ready_gate.subprocess, "run", side_effect=replies) as run, \
             patch.object(ready_gate.time, "sleep") as sleep, \
             patch.object(ready_gate.time, "monotonic", return_value=0):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900)
        sleep.assert_called_once_with(60)
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all(c.args[0][1:] == ["ls", "instances", "--json", "--all"]
                            for c in run.call_args_list))

    def test_repeated_inventory_rate_limit_stops_after_three(self):
        limited = subprocess.CalledProcessError(1, ["offline"], stderr="rate limit exceeded")
        with patch.object(ready_gate.subprocess, "run", side_effect=limited) as run, \
             patch.object(ready_gate.time, "sleep") as sleep, \
             patch.object(ready_gate.time, "monotonic", return_value=0), \
             self.assertRaises(subprocess.CalledProcessError):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_refresh_rate_limit_rechecks_inventory_then_retries_once(self):
        ready = subprocess.CompletedProcess([], 0, json.dumps(self.row()))
        limited = subprocess.CalledProcessError(1, ["offline", "refresh"],
                    output="refreshing brev...\n", stderr="rate limit exceeded\n")
        for second in (subprocess.CompletedProcess([], 0, "refreshed\n"), limited):
            with self.subTest(second=second), \
                 patch.object(ready_gate.subprocess, "run", side_effect=[ready, limited, ready, second]) as run, \
                 patch.object(ready_gate.time, "sleep") as sleep, \
                 patch.object(ready_gate.time, "monotonic", return_value=0):
                if isinstance(second, Exception):
                    with self.assertRaises(subprocess.CalledProcessError):
                        ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900, refresh_ssh=True)
                else:
                    ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900, refresh_ssh=True)
                self.assertEqual([c.args[0][1:] for c in run.call_args_list],
                                 [["ls", "instances", "--json", "--all"], ["refresh"],
                                  ["ls", "instances", "--json", "--all"], ["refresh"]])
                sleep.assert_called_once_with(60)
                self.assertTrue(all(c.kwargs["timeout"] <= 45 for c in run.call_args_list))

    def test_refresh_rate_limit_then_changed_instance_never_retries_refresh(self):
        replies = [subprocess.CompletedProcess([], 0, json.dumps(self.row())),
                   subprocess.CalledProcessError(1, ["offline"], stderr="rate limit exceeded"),
                   subprocess.CompletedProcess([], 0, json.dumps(self.row(name="different")))]
        with patch.object(ready_gate.subprocess, "run", side_effect=replies) as run, \
             patch.object(ready_gate.time, "sleep"), \
             patch.object(ready_gate.time, "monotonic", return_value=0), self.assertRaises(ValueError):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900, refresh_ssh=True)
        self.assertEqual(run.call_count, 3)

    def test_unknown_refresh_errors_and_timeouts_are_not_retried(self):
        for error in ("unauthorized", "unexpected EOF", "rate limit exceeded\nunauthorized", ""):
            exc = subprocess.CalledProcessError(1, ["offline"], stderr=error)
            with self.subTest(error=error), \
                 patch.object(ready_gate.subprocess, "run", side_effect=[
                     subprocess.CompletedProcess([], 0, json.dumps(self.row())), exc]) as run, \
                 patch.object(ready_gate.time, "sleep") as sleep, \
                 patch.object(ready_gate.time, "monotonic", return_value=0), \
                 self.assertRaises(subprocess.CalledProcessError):
                ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900, refresh_ssh=True)
            self.assertEqual(run.call_count, 2)
            sleep.assert_not_called()
        with patch.object(ready_gate.subprocess, "run", side_effect=[
                 subprocess.CompletedProcess([], 0, json.dumps(self.row())),
                 subprocess.TimeoutExpired(["offline"], 45)]) as run, \
             patch.object(ready_gate.time, "monotonic", return_value=0), \
             self.assertRaises(subprocess.TimeoutExpired):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 900, refresh_ssh=True)
        self.assertEqual(run.call_count, 2)

    def test_refresh_cooldown_cannot_extend_total_deadline(self):
        clock = [0.0]

        def query(*args, **kwargs):
            if args[0][1] == "refresh":
                clock[0] = 29.0
                raise subprocess.CalledProcessError(1, args[0], stderr="rate limit exceeded")
            return subprocess.CompletedProcess(args[0], 0, json.dumps(self.row()))

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(ready_gate.subprocess, "run", side_effect=query) as run, \
             patch.object(ready_gate.time, "sleep", side_effect=sleep) as pause, \
             patch.object(ready_gate.time, "monotonic", side_effect=lambda: clock[0]), \
             self.assertRaises(TimeoutError):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 30, refresh_ssh=True)
        pause.assert_called_once_with(1)
        self.assertEqual(run.call_count, 2)

    def test_late_ready_reply_is_not_accepted(self):
        with patch.object(ready_gate.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 0, json.dumps(self.row()))) as run, \
             patch.object(ready_gate.time, "monotonic", side_effect=[0, 0, 31]), \
             self.assertRaises(TimeoutError):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 30, refresh_ssh=True)
        run.assert_called_once()

    def test_late_refresh_success_does_not_escape_deadline(self):
        with patch.object(ready_gate.subprocess, "run", side_effect=[
                 subprocess.CompletedProcess([], 0, json.dumps(self.row())),
                 subprocess.CompletedProcess([], 0, "refreshed")]) as run, \
             patch.object(ready_gate.time, "monotonic", side_effect=[0, 0, 0, 29, 31]), \
             self.assertRaisesRegex(TimeoutError, "SSH refresh deadline"):
            ready_gate.wait_ready("offline", "offline-target", "offline-l4", 30, refresh_ssh=True)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.kwargs["timeout"], 1)


class CleanupInventoryTests(unittest.TestCase):
    """Execute the real shell functions with an in-process fake CLI only."""

    def run_function(self, name, raw, code=0, **overrides):
        wrapper = (ROOT / "scripts/recreate_brev_and_run_final_contact_servo_trace.sh").read_text()
        watchdog = (ROOT / "scripts/brev_paid_run_watchdog.sh").read_text()

        def extract(source, function):
            return function + "() {\n" + source.split(function + "() {\n", 1)[1].split("\n}\n", 1)[0] + "\n}\n"

        script = 'set -euo pipefail\nrun_with_timeout() { printf "%s\\n" "$TEST_RAW"; return "$TEST_CODE"; }\nsleep() { :; }\n'
        for function in ("matching_instance_tokens", "delete_instance", "confirm_org_empty", "pull_remote_artifacts", "selected_instance_spec"):
            script += extract(wrapper, function)
        script += extract(watchdog, "filter_instances")
        script += name + (' "$TEST_RAW"' if name == "filter_instances" else "") + "\n"
        env = {key: value for key, value in os.environ.items() if not key.startswith(("RCA_", "BREV_", "FAKE_"))}
        env.update(TEST_RAW=raw, TEST_CODE=str(code), ENV_NAME="offline-target", SCOPE="org",
                   INSTANCE_NAME="offline-target", INSTANCE_ID="", DELETE_ATTEMPTS="1",
                   DELETE_RETRY_INTERVAL_SECONDS="0", BREV_QUERY_TIMEOUT_SECONDS="1",
                   BREV_MUTATION_TIMEOUT_SECONDS="1", BREV_BIN="/not/a/real/cli",
                   REMOTE_INITIALIZED="0", INSTANCE_TYPE="offline-l4", MIN_DISK="500",
                   PATH=str(Path(sys.executable).parent) + ":/usr/bin:/bin")
        env.update(overrides)
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=5)

    def test_creation_spec_preserves_exact_type_and_disk(self):
        result = self.run_function("selected_instance_spec", "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"type": "offline-l4", "target_disk_gb": 500}])
        source = (ROOT / "scripts/recreate_brev_and_run_final_contact_servo_trace.sh").read_text()
        create = source.split('"${BREV_BIN}" create "${ENV_NAME}"', 1)[1].split('\n\n', 1)[0]
        self.assertIn('--count 1 --parallel 1', create)
        self.assertIn('run_preparation create env CREATE_SPEC="${CREATE_SPEC}"', source)
        self.assertIn('bash -c \'exec "$@" <<<"${CREATE_SPEC}"\'', source)
        self.assertNotIn('--type', create)

    def test_creation_spec_rejects_fallback_and_invalid_disk(self):
        for overrides in ({"INSTANCE_TYPE": ""}, {"INSTANCE_TYPE": "one,two"},
                          {"MIN_DISK": "0"}, {"MIN_DISK": "-1"}, {"MIN_DISK": "nan"}):
            with self.subTest(overrides=overrides):
                result = self.run_function("selected_instance_spec", "", **overrides)
                self.assertNotEqual(result.returncode, 0)

    def test_headless_creation_disables_notebook_without_changing_scope_or_failure(self):
        source = (ROOT / "scripts/recreate_brev_and_run_final_contact_servo_trace.sh").read_text()
        create = 'run_preparation create ' + source.split('run_preparation create ', 1)[1].split('\n\n', 1)[0]
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("RCA_", "BREV_", "FAKE_"))}
        env.update(ENV_NAME="offline-target", CREATE_TIMEOUT="600",
                   CREATE_SPEC='[{"type":"offline-l4","target_disk_gb":500}]')
        temporary_root = ROOT / "artifacts" / "local_tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root, prefix="headless-create-") as temp:
            cli = Path(temp) / "fake brev"
            cli.write_text('#!' + sys.executable + '\nimport json, os, sys\n'
                           'print(json.dumps({"args": sys.argv[1:], "stdin": sys.stdin.read()}))\n'
                           'raise SystemExit(int(os.environ["FAKE_EXIT"]))\n')
            cli.chmod(0o700)
            env["BREV_BIN"] = str(cli)
            # Execute only the real creation dispatch, never the paid wrapper or CLI.
            script = ('set -euo pipefail\nrun_preparation() { '
                      'test "$1" = create; shift; "$@"; }\n' + create)
            for code in (0, 7):
                with self.subTest(exit_code=code):
                    env["FAKE_EXIT"] = str(code)
                    result = subprocess.run(["bash", "-c", script], env=env,
                                            capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, code, result.stderr)
                    rows = result.stdout.splitlines()
                    self.assertEqual(len(rows), 1, "creation must not be retried")
                    observed = json.loads(rows[0])
                    self.assertEqual(observed["args"], ["create", "offline-target", "--count", "1",
                                     "--parallel", "1", "--jupyter=false", "--stoppable", "--timeout", "600"])
                    self.assertEqual(json.loads(observed["stdin"]),
                                     [{"type": "offline-l4", "target_disk_gb": 500}])

    def test_unknown_inventory_never_confirms_cleanup_or_watchdog_absence(self):
        for function in ("matching_instance_tokens", "confirm_org_empty", "filter_instances"):
            for raw in ("", "malformed", "{}", "null", "[]", '{"instances":[]}',
                        '{"workspaces":false}', '{"workspaces":{}}', '{"workspaces":[null]}'):
                with self.subTest(function=function, raw=raw):
                    result = self.run_function(function, raw)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertNotIn("cleanup confirmed", result.stdout)

    def test_failed_query_is_not_an_empty_inventory(self):
        for function in ("matching_instance_tokens", "confirm_org_empty"):
            with self.subTest(function=function):
                result = self.run_function(function, '{"workspaces":null}', code=1)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("cleanup confirmed", result.stdout)

    def test_no_pull_if_remote_initialization_never_completed(self):
        result = self.run_function("pull_remote_artifacts", "")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no task artifacts to pull", result.stdout)
        self.assertNotIn("pulling remote artifacts", result.stdout)

    def test_explicit_empty_inventory_is_accepted(self):
        for function in ("matching_instance_tokens", "confirm_org_empty", "filter_instances"):
            for raw in ('{"workspaces":null}', '{"workspaces":[]}'):
                with self.subTest(function=function, raw=raw):
                    result = self.run_function(function, raw)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_visible_target_survives_filtering_and_blocks_cleanup(self):
        raw = '{"workspaces":[{"name":"offline-target","id":"offline-id"}]}'
        for function in ("matching_instance_tokens", "filter_instances"):
            result = self.run_function(function, raw)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("offline-target", result.stdout)
            self.assertIn("offline-id", result.stdout)
        for function in ("confirm_org_empty",):
            result = self.run_function(function, raw)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("cleanup confirmed", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
