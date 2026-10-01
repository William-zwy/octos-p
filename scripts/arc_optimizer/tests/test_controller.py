"""Synthetic safety tests; no ARC calls, Codex calls, or benchmark execution."""
import copy
import importlib.util
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "controller.py"
spec = importlib.util.spec_from_file_location("arc_optimizer_controller", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeController(mod.Controller):
    def __init__(self, root):
        self.repo = root / "repo"
        self.repo.mkdir()
        self.store = root / "private"
        self.store.mkdir()
        self.journal = self.store / "controller.json"
        self.c = {"max_log_pages": 20, "enabled": True, "budget_cny": 100,
                  "estimated_run_cny": 20, "reserve_fraction": .25, "max_rounds": 2,
                  "max_no_improvement": 1, "deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                  "competition": "fixture", "official_evaluation": True, "suite_key": "platform-suite",
                  "suite_provenance": "platform response", "requirements_file": "input.zip",
                  "execution_policy": "agent_edit",
                  "requirements_sha256": "", "worker_timeout_seconds": 60,
                  "allowed_paths": [mod.PLAN, mod.LOG, mod.REGISTER, mod.PROJECT_LOG, "arc/main.py"],
                  "context": [], "codex": "fake-codex", "model": "fixture", "task": "fixture--task"}
        requirements = self.repo / "input.zip"
        requirements.write_bytes(b"synthetic requirements")
        self.c["requirements_sha256"] = mod.sha256(requirements)
        self.state = {"phase": "ready", "round": 0, "rounds": [], "no_improvement": 0,
                      "spent_cny": 0, "last_run": None}
        self.secrets = ["fixture-secret"]
        self.github_token = None
        self.calls = []
        self.remaining = 100
        self.status = {"id": "run-fixture", "status": "FAILED", "score": 50,
                       "token_cost_usd": 7, "token_cost_currency": "CNY",
                       "submission_id": "submission-fixture", "requirement_id": "fixture--task"}
        self.pages = {0: {"console": "\n".join(f"line {n}" for n in range(100)), "log_offset": 100},
                      100: {"stderr": "all second page", "log_offset": 200},
                      200: {"console": "", "log_offset": 200}}
        self.fail_offset = None
        self.fail_mutation = False
        self.paths = set()
        self.head = "a" * 40

    def arc(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == "registration":
            return {"registered": True, "remaining_budget_cny": self.remaining}
        if args[0] == "status":
            self.assert_status_allowed = kwargs.get("allowed_codes")
            return copy.deepcopy(self.status)
        if args[0] == "logs":
            offset = int(args[args.index("--offset") + 1])
            folder = Path(args[args.index("--out") + 1])
            mod.atomic_json_write(folder / "run-fixture-logs.json", self.pages[offset])
            if offset == self.fail_offset:
                raise mod.GateError("simulated crash after durable payload before cursor")
            return {"console": "truncated tail", "next_offset": self.pages[offset]["log_offset"]}
        if args[0] in ("download", "archive"):
            Path(args[args.index("--output") + 1]).write_bytes(b"synthetic zip")
            return {"saved": True}
        if args[0] in ("upload", "run"):
            if self.fail_mutation:
                raise mod.GateError("simulated transport uncertainty")
            return [{}]
        raise AssertionError(args)

    def preflight(self, **kwargs):
        return self.head

    def verify_sync(self, expected):
        return {"local": expected, "tracking": expected, "github": expected}

    def changed_paths(self):
        return self.paths

    def git(self, *args):
        if args == ("rev-parse", "HEAD"):
            return self.head
        raise AssertionError(args)

    def command(self, argv, **kwargs):
        output = Path(self.state["worker_dir"]) / "decision.json"
        mod.atomic_json_write(output, {"decision": "candidate", "changed_files": sorted(self.paths),
                                      "hypothesis": "fixture", "evidence": [], "risks": []})
        return 0, "fixture events", ""


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arc-controller-tests-")
        self.addCleanup(self.temp.cleanup)
        self.ctl = FakeController(Path(self.temp.name))

    def test_full_log_payload_not_tail_and_no_overwrite(self):
        result = self.ctl.collect("run-fixture")
        self.assertEqual(result["log_pages"], 2)
        self.assertEqual(result["log_next_offset"], 200)
        self.assertTrue(result["logs_drained"])
        root = self.ctl.store / "runs/run-fixture"
        full = mod.read_json(root / "log-pages/000000000000/run-fixture-logs.json")
        self.assertEqual(len(full["console"].splitlines()), 100)
        self.assertEqual(self.ctl.assert_status_allowed, (0, 1))
        self.assertEqual(result["cost"], {"amount": 7, "currency": "CNY"})

    def test_resume_after_payload_written_before_cursor(self):
        self.ctl.fail_offset = 100
        with self.assertRaises(mod.GateError):
            self.ctl.collect("run-fixture")
        self.ctl.fail_offset = None
        self.ctl.calls.clear()
        result = self.ctl.collect("run-fixture")
        self.assertTrue(result["logs_drained"])
        self.assertFalse(any(call[0] == "logs" and call[3] == "100" for call in self.ctl.calls))
        self.assertEqual(result["log_pages"], 2)

    def test_collect_again_refreshes_end_cursor_for_new_logs(self):
        self.ctl.status["status"] = "RUNNING"
        self.ctl.collect("run-fixture")
        self.ctl.pages[200] = {"console": "late logs", "log_offset": 300}
        self.ctl.pages[300] = {"log_offset": 300}
        result = self.ctl.collect("run-fixture")
        self.assertEqual(result["log_pages"], 3)
        self.assertEqual(result["log_next_offset"], 300)

    def test_collect_writes_analysis_for_implementation_worker(self):
        self.ctl.status["score"] = 0
        result = self.ctl.collect("run-fixture")
        analysis_path = self.ctl.store / "runs/run-fixture/analysis.json"
        self.assertTrue(analysis_path.is_file())
        self.assertEqual(result["analysis"]["decision"], "modify")
        self.assertEqual(result["analysis"]["next_slice"]["scope"], "one vertical slice only")
        codes = {item["code"] for item in result["analysis"]["findings"]}
        self.assertIn("official-details-missing", codes)
        self.assertIn("identity-not-closed", codes)
        self.assertIn("official pass from internal verified", " ".join(result["analysis"]["next_slice"]["must_not_claim"]))
        self.assertIn("forensics", result)

    def test_worker_context_filters_raw_summary_to_actionable_evidence(self):
        self.ctl.status["score"] = 0
        result = self.ctl.collect("run-fixture")
        context = mod.worker_context(result)
        self.assertEqual(context["analysis"]["decision"], "modify")
        self.assertIn("missing_platform_evidence", context["evidence"])
        self.assertTrue(context["raw_evidence_is_external"])
        self.assertNotIn("files", context)
        self.assertNotIn("failed_tests", context)

    def test_evidence_index_is_metadata_only_and_skips_secret_like_names(self):
        source = Path(self.temp.name) / "external-evidence"
        source.mkdir()
        (source / "summary.json").write_text("{}", encoding="utf-8")
        (source / "session-token.txt").write_text("do-not-read", encoding="utf-8")
        index = mod.build_evidence_index("run-fixture", source)
        self.assertTrue(index["raw_not_copied"])
        self.assertEqual(index["files"][0]["path"], "summary.json")
        self.assertEqual(index["skipped"][0]["reason"], "secret_like_filename")

    def test_optimization_plan_stays_plan_only(self):
        facts = {"run": {"run_id": "run-fixture", "url": "https://arc-bench.com/runs/run-fixture"}}
        plan = mod.build_optimization_plan("run-fixture", {
            "decision": "modify",
            "source": "fixture",
            "findings": [{"code": "budget-cap", "severity": "P0", "conclusion": "cap",
                          "action": "split budget", "confidence": "high", "evidence": ["x"]}],
            "next_slice": {"scope": "one vertical slice", "must_prove": ["probe"],
                           "must_not_claim": ["official pass"]},
        }, facts)
        self.assertEqual(plan["mode"], "plan_only")
        self.assertTrue(plan["authorization_required"])
        self.assertFalse(plan["authorization"]["agent_edit"])
        self.assertEqual(plan["budget_policy"]["max_requests_per_slice"], 36)

    def test_analyze_rebuilds_legacy_run_state_without_arc_call(self):
        root = self.ctl.store / "runs/run-fixture"
        root.mkdir(parents=True, exist_ok=True)
        (root / "status.json").write_text(json.dumps(self.ctl.status), encoding="utf-8")
        (root / "collection.json").write_text(json.dumps({"offset": 0, "pages": [], "errors": {},
                                                            "logs_drained": True}), encoding="utf-8")
        result = self.ctl.analyze("run-fixture")
        self.assertEqual(result["run_id"], "run-fixture")
        self.assertEqual(result["optimization_plan"]["mode"], "plan_only")
        self.assertTrue((root / "analysis.json").is_file())
        self.assertTrue((root / "optimization-plan.json").is_file())

    def test_context_snapshot_records_branch_identity_without_merge(self):
        self.ctl.c["context"] = ["HKT/PLAN.md"]
        self.ctl.c["git"] = "git"
        with patch.object(self.ctl, "git", return_value="a" * 40):
            with patch.object(self.ctl, "command", return_value=(0, "100644 blob " + "b" * 40 + "\tHKT/PLAN.md\n", "")):
                snapshot = self.ctl.context_snapshot("codex/hkt-round345-integration")
        self.assertEqual(snapshot["commit"], "a" * 40)
        self.assertFalse(snapshot["merged"])
        self.assertEqual(snapshot["files"][0]["blob"], "b" * 40)

    def test_analysis_marks_budget_and_comparison_without_causal_claim(self):
        facts = {
            "run": {"run_id": "new", "task_key": "fixture--task", "status": "FAILED",
                    "score": 0, "feature_passed": 0},
            "suite": {"suite_key": None, "task_snapshot_id": None},
            "submission": {"binding_closed": False},
            "generation": {"implement_ok": 2, "wrote_verified": 2, "verified_false": 0,
                           "request_budget_hits": 3},
            "deployment": {},
            "evaluation": {"details_available": False, "tests": None, "test_ids": None},
            "errors": {"request_budget_hits": 3},
            "artifacts": {"missing_platform_evidence": ["per_test_details"]},
            "local_manifest": {"present": True},
        }
        analysis = mod.analyze_forensics(facts, {"run_id": "old", "task_key": "fixture--task",
                                                "score": 1, "strict_ab": False})
        codes = {item["code"] for item in analysis["findings"]}
        self.assertIn("budget-cap", codes)
        self.assertIn("comparison-not-causal", codes)
        self.assertEqual(analysis["comparison"]["score_delta"], -1)
        self.assertFalse(analysis["comparison"]["strict_ab"])

    def test_forensics_reads_archive_build_and_local_manifest(self):
        state = self.ctl.store / "runs/run-fixture"
        state.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(state / "submission.zip", "w") as archive:
            archive.writestr("agent-build.json", json.dumps({
                "build_id": "build-fixture", "commit_sha": "c" * 40,
                "payload_tree_sha256": "d" * 64}))
            archive.writestr("requirements.yaml", "fixture: true\n")
            archive.writestr("binding.json", "{}")
        manifest_dir = self.ctl.repo / "evidence/arc-bench/runs/run-fixture"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "manifest.json").write_text(json.dumps({
            "verification_regime": {"mode": "requirement-text-only"},
            "evidence": [{"filename": "summary.md"}],
            "submission": {"runtime_reported_identity": {"suite_key": "runtime-suite"}},
            "traceability": {"final_interface_records": 0},
            "evidence_provenance": {"storage": "local_only"},
        }), encoding="utf-8")
        facts = mod.build_forensics(self.ctl.status, {"pages": [], "errors": {}}, [], {}, state, self.ctl.repo)
        self.assertEqual(facts["submission"]["build_id"], "build-fixture")
        self.assertEqual(facts["submission"]["archive_agent_commit"], "c" * 40)
        self.assertEqual(facts["suite"]["suite_key"], "runtime-suite")
        self.assertTrue(facts["local_manifest"]["present"])
        self.assertEqual(facts["local_manifest"]["traceability"]["final_interface_records"], 0)
        self.assertEqual(facts["local_manifest"]["evidence_provenance"]["storage"], "local_only")

    def test_log_forensics_does_not_count_zero_oom_counters(self):
        log_dir = self.ctl.store / "runs/run-fixture/log-pages/000000000000"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "run-fixture-logs.json").write_text(json.dumps({
            "stdout": "memory.events: oom 0 oom_kill 0; no OOM occurred",
            "stderr": "",
        }), encoding="utf-8")
        result = mod._log_forensics(self.ctl.store / "runs/run-fixture", self.ctl.status)
        self.assertEqual(result["oom_count"], 0)

    def test_missing_or_regressing_cursor_is_not_complete(self):
        for value in (None, -1):
            self.ctl.pages[0] = {"console": "fixture", "log_offset": value}
            path = self.ctl.store / "runs/run-fixture/log-pages/000000000000/run-fixture-logs.json"
            if path.exists():
                path.unlink()
            with self.assertRaises(mod.GateError):
                self.ctl.collect("run-fixture")

    def test_page_limit_marks_incomplete(self):
        self.ctl.c["max_log_pages"] = 1
        result = self.ctl.collect("run-fixture")
        self.assertFalse(result["logs_drained"])
        self.assertIn("complete_log_pagination", result["missing_evidence"])

    def test_wrong_run_response_rejected(self):
        self.ctl.status["id"] = "another-run"
        with self.assertRaises(mod.GateError):
            self.ctl.collect("run-fixture")

    def test_unknown_identities_stay_unknown(self):
        result = self.ctl.collect("run-fixture")
        self.assertIsNone(result["source_commit"])
        self.assertIsNone(result["hidden_suite_identity"])
        self.assertFalse(result["candidate_identity_closed"])
        self.assertFalse(result["strict_ab"])
        self.assertIn("per_test_details", result["missing_evidence"])

    def test_downloaded_submission_hash_closes_only_candidate(self):
        self.ctl.state["candidate"] = {"package_sha256": __import__('hashlib').sha256(b"synthetic zip").hexdigest(),
                                       "source_commit": "a" * 40}
        result = self.ctl.collect("run-fixture")
        self.assertTrue(result["candidate_identity_closed"])
        self.assertEqual(result["platform_identity"], "platform_identity_inconclusive")

    def test_download_failure_is_explicit(self):
        actual = self.ctl.arc
        def unavailable(*args, **kwargs):
            if args[0] == "download":
                raise mod.GateError("download unavailable")
            return actual(*args, **kwargs)
        self.ctl.arc = unavailable
        result = self.ctl.collect("run-fixture")
        self.assertIn("workspace.zip", result["missing_evidence"])
        self.assertIn("workspace", result["collection_errors"])

    def test_mutation_timeout_is_journaled_and_never_repeated(self):
        self.ctl.state["worker_dir"] = str(self.ctl.store)
        self.ctl.fail_mutation = True
        with self.assertRaises(mod.GateError):
            self.ctl.mutate_once("upload", ["upload", "fixture.zip"])
        self.assertEqual(mod.read_json(self.ctl.journal)["phase"], "upload_pending")
        before = len(self.ctl.calls)
        with self.assertRaises(mod.GateError):
            self.ctl.step()
        self.assertEqual(len(self.ctl.calls), before)

    def test_only_read_transport_failures_get_one_retry(self):
        self.ctl.env_file = self.ctl.store / "arc.env"
        self.ctl.c["python"] = "synthetic-python"
        failure = (1, "", json.dumps({"transport_failure": True, "http_status": None}))
        success = (0, json.dumps({"logged_in": True}), "")
        with patch.object(self.ctl, "command", side_effect=[failure, success]) as command:
            self.assertTrue(mod.Controller.arc(self.ctl, "whoami")["logged_in"])
            self.assertEqual(command.call_count, 2)
        with patch.object(self.ctl, "command", return_value=failure) as command:
            with self.assertRaises(mod.GateError):
                mod.Controller.arc(self.ctl, "logs", "run-fixture")
            self.assertEqual(command.call_count, 2)
        with patch.object(self.ctl, "command", return_value=failure) as command:
            with self.assertRaises(mod.GateError):
                mod.Controller.arc(self.ctl, "upload", "fixture.zip")
            self.assertEqual(command.call_count, 1)

    def test_failed_run_exit_one_is_result_not_retry(self):
        self.ctl.env_file = self.ctl.store / "arc.env"
        self.ctl.c["python"] = "synthetic-python"
        failed_run = (1, json.dumps(self.ctl.status), "")
        with patch.object(self.ctl, "command", return_value=failed_run) as command:
            result = mod.Controller.arc(self.ctl, "status", "run-fixture", allowed_codes=(0, 1))
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(command.call_count, 1)

    def test_run_response_without_id_blocks_recreation(self):
        self.ctl.state.update(phase="uploaded", candidate={"submission_id": "submission-fixture"},
                              worker_dir=str(self.ctl.store))
        with self.assertRaises(mod.GateError):
            self.ctl.step()
        self.assertEqual(self.ctl.state["phase"], "run_pending")
        self.ctl.calls.clear()
        with self.assertRaises(mod.GateError):
            self.ctl.step()
        self.assertEqual(self.ctl.calls, [])

    def test_paid_gates_fail_before_worker(self):
        for key, value in (("enabled", False), ("budget_cny", None), ("deadline", None),
                           ("reserve_fraction", .1), ("suite_key", None), ("suite_provenance", None)):
            original = self.ctl.c[key]
            self.ctl.c[key] = value
            with self.assertRaises(mod.GateError, msg=key):
                self.ctl.step()
            self.assertEqual(self.ctl.state["phase"], "ready")
            self.ctl.c[key] = original

    def test_limits_do_not_block_existing_run_collection(self):
        self.ctl.c["enabled"] = False
        self.ctl.state.update(phase="running", candidate={"run_id": "run-fixture"})
        self.ctl.status["status"] = "RUNNING"
        self.ctl.step()
        self.assertEqual(self.ctl.state["phase"], "running")
        self.assertTrue(any(call[0] == "status" for call in self.ctl.calls))

    def test_reserve_protected_from_account_or_local_spend(self):
        self.ctl.remaining = 40  # 25 reserve + 20 estimate needed.
        with self.assertRaises(mod.GateError):
            self.ctl.guard()
        self.ctl.remaining = 100
        self.ctl.state["spent_cny"] = 56
        with self.assertRaises(mod.GateError):
            self.ctl.guard()

    def test_worker_unexpected_path_rejected(self):
        self.ctl.paths = {mod.PLAN, mod.LOG, mod.REGISTER, "arc/main.py", "arc/public-tests/official.spec.ts"}
        with self.assertRaises(mod.GateError):
            self.ctl.worker()
        self.assertEqual(self.ctl.state["phase"], "worker_pending")

    def test_worker_missing_progress_records_rejected(self):
        self.ctl.paths = {"arc/main.py"}
        with self.assertRaises(mod.GateError):
            self.ctl.worker()

    def test_secrets_redacted(self):
        self.assertNotIn("fixture-secret", self.ctl.safe({"data": "fixture-secret"}))

    def test_run_path_injection_rejected(self):
        with self.assertRaises(mod.GateError):
            self.ctl.collect("../secrets")

    def test_lock_rejects_second_writer_and_releases(self):
        directory = self.ctl.store / "locks"
        with mod.writer_lock(directory):
            with self.assertRaises(mod.GateError):
                with mod.writer_lock(directory):
                    pass
        with mod.writer_lock(directory):
            pass

    def test_deadline_requires_timezone(self):
        with self.assertRaises(mod.GateError):
            mod.parse_date("2026-10-01T12:00:00")

    def test_coordination_preserves_historical_formatting(self):
        path = self.ctl.store / "coordination.json"
        historical = '{\n  "roles": {"owner": "original"},\n  "runs": ["one", "two"]\n}\n'
        path.write_text(historical, encoding="utf-8")
        for count in (1, 2):
            mod.write_coordination(path, {"count": count})
            self.assertIn('"roles": {"owner": "original"}', path.read_text())
            self.assertIn('"runs": ["one", "two"]', path.read_text())
            self.assertEqual(mod.read_json(path)["arc_optimizer_deployment"], {"count": count})

    def test_private_github_api_uses_existing_manager_in_memory(self):
        self.ctl.c.update(git="selected-git", github_repo="fixture/repo")
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"commit":{"sha":"fixture"}}'
        with patch.object(self.ctl, "command", return_value=(0, "password=fixture-token\n", "")) as command:
            with patch.object(mod.urllib.request, "urlopen", return_value=Response()) as urlopen:
                self.ctl.api("branches/fixture")
                self.ctl.api("branches/fixture")
                self.assertEqual(command.call_count, 1)
                request = urlopen.call_args.args[0]
                self.assertEqual(request.get_header("Authorization"), "Bearer fixture-token")
                self.assertEqual(command.call_args.kwargs["env"]["GCM_INTERACTIVE"], "Never")
                self.assertNotIn("fixture-token", self.ctl.safe("fixture-token"))


if __name__ == "__main__":
    unittest.main()
