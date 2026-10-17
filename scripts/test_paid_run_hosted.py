#!/usr/bin/env python3
"""Only the new hosted wiring: fake provider, real HTTP/files/crypto, no cloud."""
import contextlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import paid_run_hosted as hosted

PLAN = {"target_name": "rca-seated-fixture-01234567", "instance_type": "fixture-gpu"}
ROW = {"id": "fixture-id", "name": PLAN["target_name"], "organizationId": hosted.ORG,
       "instanceType": PLAN["instance_type"]}


class ProviderFixture(http.server.BaseHTTPRequestHandler):
    rows = []
    calls = []
    deletion = "ok"

    def log_message(self, *_):
        pass

    def answer(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_GET(self):
        type(self).calls.append(("GET", self.path))
        if self.path != "/api/organizations/" + hosted.ORG + "/workspaces":
            return self.answer(404, {})
        self.answer(200, type(self).rows)

    def do_DELETE(self):
        type(self).calls.append(("DELETE", self.path))
        if self.path != "/api/workspaces/fixture-id":
            return self.answer(404, {})
        if type(self).deletion == "forbidden":
            return self.answer(403, {"error": "synthetic denial"})
        if type(self).deletion == "redirect":
            self.send_response(307)
            self.send_header("Location", "/never-follow")
            self.end_headers()
            return
        type(self).rows = []
        if type(self).deletion == "eof":
            self.close_connection = True
            return
        self.answer(202, ROW)


class HostedIntegrationTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        ProviderFixture.rows, ProviderFixture.calls, ProviderFixture.deletion = [dict(ROW)], [], "ok"
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ProviderFixture)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = patch.object(hosted, "API", f"http://127.0.0.1:{self.server.server_port}/")
        self.base.start()
        self.addCleanup(self.base.stop)
        self.provider = hosted.Provider("bak-synthetic-never-real")
        self.target = hosted.bind_target(PLAN, ProviderFixture.rows)
        self.remaining = 250

    def left(self):
        return self.remaining

    def sleep(self, seconds):
        self.remaining -= seconds

    def pull(self, seconds):
        self.assertLessEqual(seconds, 150)
        (self.root / "raw.json").write_text(json.dumps({"id": self.target["id"], "synthetic": True}))

    def recover(self, pull=None):
        with patch.object(hosted.time, "sleep", side_effect=self.sleep):
            return hosted.recover_exact(self.provider, PLAN, self.target, self.root,
                                        self.left, pull or self.pull)

    def deletes(self):
        return [c for c in ProviderFixture.calls if c[0] == "DELETE"]

    def test_real_http_pull_then_exact_delete_and_independent_inventory(self):
        def pull(seconds):
            self.assertEqual(self.deletes(), [])
            self.pull(seconds)
        report = self.recover(pull)
        self.assertTrue(report["artifacts_recovered"])
        self.assertTrue(report["target_absent"])
        self.assertTrue(report["organization_empty"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(self.deletes(), [("DELETE", "/api/workspaces/fixture-id")])
        self.assertEqual(ProviderFixture.calls[-1][0], "GET")
        intent = json.loads((self.root / "delete-intent.json").read_text())
        self.assertEqual(intent["target"], self.target)

    def test_eof_after_applied_delete_is_not_replayed_or_labelled_clean_success(self):
        ProviderFixture.deletion = "eof"
        report = self.recover()
        self.assertTrue(report["target_absent"])
        self.assertIn("delete outcome unknown", report["errors"][0])
        self.assertEqual(len(self.deletes()), 1)

    def test_403_and_redirect_never_replay_delete(self):
        for mode in ("forbidden", "redirect"):
            with self.subTest(mode=mode):
                ProviderFixture.deletion = mode
                ProviderFixture.calls = []
                self.remaining = 110
                report = self.recover()
                self.assertFalse(report["target_absent"])
                self.assertEqual(len(self.deletes()), 1)
                self.assertNotIn(("DELETE", "/never-follow"), ProviderFixture.calls)
                (self.root / "delete-intent.json").unlink()

    def test_persisted_intent_refuses_retry_in_new_recovery(self):
        hosted.write_private(self.root / "delete-intent.json", {"target": self.target})
        self.remaining = 110
        report = self.recover()
        self.assertEqual(self.deletes(), [])
        self.assertTrue(any("no replay" in e for e in report["errors"]))

    def test_same_name_replacement_and_renamed_id_refuse_mutation(self):
        for row in (dict(ROW, id="replacement"), dict(ROW, name="someone-else")):
            with self.subTest(row=row):
                ProviderFixture.rows = [row]
                with self.assertRaises(ValueError):
                    self.recover()
                self.assertEqual(self.deletes(), [])

    def test_wrong_org_duplicate_and_ambiguous_rows_rejected(self):
        for rows in ([dict(ROW, organizationId="wrong")], [ROW, ROW],
                     [ROW, dict(ROW, id="another")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                ProviderFixture.rows = rows
                hosted.bind_target(PLAN, self.provider.inventory(), self.target)
        self.assertEqual(self.deletes(), [])

    def test_unrelated_instance_is_retained_and_account_nonempty_is_not_success(self):
        ProviderFixture.rows.append(dict(ROW, id="unrelated", name="unrelated"))
        original = ProviderFixture.do_DELETE
        def delete(handler):
            original(handler)
            ProviderFixture.rows = [dict(ROW, id="unrelated", name="unrelated")]
        with patch.object(ProviderFixture, "do_DELETE", delete):
            report = self.recover()
        self.assertTrue(report["target_absent"])
        self.assertFalse(report["organization_empty"])
        self.assertEqual(self.deletes(), [("DELETE", "/api/workspaces/fixture-id")])

    def test_pull_failure_is_retained_but_does_not_leave_billing_running(self):
        def fail(_):
            raise TimeoutError("fixture")
        report = self.recover(fail)
        self.assertFalse(report["artifacts_recovered"])
        self.assertTrue(report["target_absent"])
        self.assertEqual(len(self.deletes()), 1)
        self.assertEqual(report["errors"], ["pullback:TimeoutError"])

    def test_changed_scope_after_pull_does_not_delete(self):
        def replaced(_):
            ProviderFixture.rows = [dict(ROW, id="replacement")]
        with self.assertRaises(ValueError):
            self.recover(replaced)
        self.assertEqual(self.deletes(), [])

    def test_deadline_has_no_fresh_retry_window(self):
        self.remaining = 30
        with self.assertRaises(TimeoutError):
            self.recover()
        self.assertEqual(self.deletes(), [])

    def test_cms_roundtrip_preserves_private_bytes(self):
        key, cert = self.root / "key.pem", self.root / "cert.pem"
        hosted.bounded(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-subj", "/CN=RCA synthetic fixture", "-days", "1", "-keyout", str(key),
                        "-out", str(cert)], 20)
        private = self.root / "private"
        private.mkdir()
        raw = b"synthetic private raw bytes; no real credentials\n"
        (private / "raw.txt").write_bytes(raw)
        encrypted, decrypted = self.root / "evidence.cms", self.root / "decrypted.tar.gz"
        digest = hosted.seal_evidence(private, cert, encrypted)
        self.assertEqual(digest, hosted.sha(encrypted.read_bytes()))
        self.assertNotIn(raw, encrypted.read_bytes())
        hosted.bounded(["openssl", "cms", "-decrypt", "-binary", "-inform", "DER", "-in", str(encrypted),
                        "-recip", str(cert), "-inkey", str(key), "-out", str(decrypted)], 10)
        with hosted.tarfile.open(decrypted, "r:gz") as archive:
            self.assertEqual(archive.extractfile("evidence/raw.txt").read(), raw)

    def test_live_owner_and_source_checks_cannot_be_replaced_by_marker(self):
        with patch.dict(os.environ, {"RCA_HOSTED_CLEANUP_RUN": "123", "RCA_ALLOW_PAID_BREV_CREATE": "1"}), \
                patch.object(hosted, "plan_read", side_effect=ValueError("missing source binding")), \
                patch.object(hosted, "github") as api, self.assertRaises(ValueError):
            hosted.check_before_create(PLAN["target_name"])
        api.assert_not_called()

    def test_actual_wrapper_has_only_hosted_delete_owner(self):
        source = (hosted.ROOT / "scripts/recreate_brev_and_run_final_contact_servo_trace.sh").read_text()
        body = source.split("delete_instance() {\n", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('paid_run_hosted.py" finish', body)
        self.assertNotIn('"${BREV_BIN}" delete', body)
        create = source.split("CREATED_INSTANCE=1", 1)[1]
        self.assertNotIn("start_billing_watchdog", create)
        self.assertIn('paid_run_hosted.py" probe', create)
        self.assertIn('paid_run_hosted.py" admit --phases', create)

    def test_actual_phase_admission_preserves_original_window_and_rejects_missing_pair(self):
        from paid_run_deadline import Clock, PHASES
        rows = []
        for index, name in enumerate(PHASES):
            for event, offset in (("start", index * 10), ("end", index * 10 + 5)):
                rows.append({"phase": name, "event": event, "lifecycle_pid": 42,
                             "clock": {"utc": 1000 + offset, "monotonic": 500 + offset, "boot_id": "actual-fixture"},
                             "exit_code": 0 if event == "end" else None})
        path = self.root / "phases.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows))
        owner = (PLAN, {"id": 123, "head_sha": "fixture"}, {"origin": 990})
        with patch.dict(os.environ, {"RCA_HOSTED_CLEANUP_RUN": "123"}), \
                patch.object(hosted, "active_owner", return_value=owner), \
                patch.object(hosted.time, "time", return_value=1060), \
                patch.object(hosted, "sample_os_clock", return_value=Clock(1060, 560, "actual-fixture")), \
                patch.object(hosted, "status_read", return_value={"state": "success", "description": "fixture-id"}):
            self.assertTrue(hosted.admit_workload(path)["workload_timing_admissible"])
            path.write_text("\n".join(json.dumps(r) for r in rows[:-1]))
            with self.assertRaises(ValueError):
                hosted.admit_workload(path)
            with patch.object(hosted.time, "time", return_value=2070), self.assertRaises(TimeoutError):
                hosted.admit_workload(path)

    def test_every_changed_production_entry_is_bound_to_hosted_verification(self):
        for path in ("scripts/check_paid_supervision.py", "scripts/prepare_contact_smoke_run.sh",
                     "scripts/run_success_variation_paid_lifecycle.py",
                     "scripts/recreate_brev_and_run_final_contact_servo_trace.sh"):
            self.assertIn(path, hosted.INTEGRATION_FILES)

    def test_hosted_manifest_cannot_admit_dirty_bundle_rejected_by_runtime(self):
        repo = self.root / "dirty-repo"
        scripts = repo / "scripts"
        scripts.mkdir(parents=True)
        script = scripts / "prepare_contact_smoke_run.sh"
        script.write_bytes((hosted.ROOT / "scripts/prepare_contact_smoke_run.sh").read_bytes())
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        result = subprocess.run(["bash", str(script)], cwd=repo, capture_output=True, text=True,
                                env={**os.environ, "RCA_CONTACT_SMOKE_REQUIRE_CLEAN": "1",
                                     "RCA_HOSTED_PLAN_PREPARATION": "even-a-frozen-manifest"}, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires a clean frozen bundle", result.stderr)
        self.assertNotIn("paid preflight", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_formal_lifecycle_waits_for_owner_before_real_wrapper(self):
        import run_success_variation_paid_lifecycle as lifecycle
        calls = []
        commands = {key: [key] for key in ("prepare", "preflight", "run", "disarm", "safety", "recovery", "finalize")}
        with patch.object(lifecycle, "_run", side_effect=lambda label, _: calls.append(label) or 0), \
                patch.object(hosted, "launch_owner", side_effect=lambda: calls.append("owner_ready")), \
                patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(__import__('io').StringIO()):
            self.assertEqual(lifecycle._execute_lifecycle(SimpleNamespace(hosted_cleanup=True), commands), 0)
        self.assertLess(calls.index("preflight"), calls.index("owner_ready"))
        self.assertLess(calls.index("owner_ready"), calls.index("run"))

    def test_owner_readiness_failure_prevents_create(self):
        import run_success_variation_paid_lifecycle as lifecycle
        calls = []
        commands = {key: [key] for key in ("prepare", "preflight", "run", "disarm", "safety", "recovery", "finalize")}
        with patch.object(lifecycle, "_run", side_effect=lambda label, _: calls.append(label) or 0), \
                patch.object(hosted, "launch_owner", side_effect=TimeoutError("fixture")), \
                patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(__import__('io').StringIO()):
            self.assertNotEqual(lifecycle._execute_lifecycle(SimpleNamespace(hosted_cleanup=True), commands), 0)
        self.assertNotIn("run", calls)
        self.assertIn("disarm", calls)

    def test_uploaded_stage_can_use_remaining_deletion_reserve_without_repull(self):
        self.remaining = 65
        calls = []
        result = hosted.recover_exact(self.provider, PLAN, self.target, self.root, self.left,
                                     lambda seconds: calls.append(seconds), pull_seconds=20, post_pull_reserve=35)
        self.assertEqual(calls, [20])
        self.assertTrue(result["artifacts_recovered"])
        self.assertTrue(result["target_absent"])

    def test_workflow_stores_ciphertext_before_delete_and_never_uploads_raw(self):
        source = (hosted.ROOT / hosted.WORKFLOW).read_text().split("  instance-cleanup:", 1)[1].split("  clock-check:", 1)[0]
        self.assertLess(source.index("path: sealed-evidence/recovered.cms"), source.index("delete-uploaded"))
        self.assertIn("RCA_RECOVERED_ARTIFACT_ID: ${{ steps.recovered.outputs.artifact-id }}", source)
        self.assertNotIn("path: /", source)
        self.assertNotIn("path: artifacts/", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
