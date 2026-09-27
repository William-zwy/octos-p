import unittest

from main import (
    OctosDriver, describe_node, folder_descendants, implementation_timeout, inline_sources,
    inline_spec_text, repair_timeout, should_use_full_rewrite, skeleton_timeout,
    early_stop_eligible, fast_pass_eligible, is_complex_node_text,
    turn_was_early_stopped, turn_was_timed_out, unchanged_node_ids,
)
import main as m
from repair_context import domain_context, infer_product_domain


def node(node_id, description, deps=()):
    return {"id": node_id, "type": "ATOMIC", "name": node_id, "description": description,
            "dependencies": list(deps), "scenarios": [{"name": "s", "steps": [{"keyword": "GIVEN", "content": "x"}]}]}


class EvolutionDiffTests(unittest.TestCase):
    def test_should_keep_nodes_whose_content_matches_previous_requirement_table(self):
        current = [node("REQ-1", "same"), node("REQ-2", "changed"), node("REQ-3", "new", ["REQ-1"])]
        previous = {
            "REQ-1": {"req_id": "REQ-1", "id": "REQ-1", "name": "REQ-1", "description": "same", "dependencies": [],
                      "scenarios": [{"name": "s", "steps": [{"keyword": "GIVEN", "content": "x"}]}]},
            "REQ-2": {"req_id": "REQ-2", "id": "REQ-2", "name": "REQ-2", "description": "old", "dependencies": [],
                      "scenarios": [{"name": "s", "steps": [{"keyword": "GIVEN", "content": "x"}]}]},
        }
        self.assertEqual(unchanged_node_ids(current, previous), {"REQ-1"})

    def test_should_treat_everything_as_changed_without_previous_table(self):
        self.assertEqual(unchanged_node_ids([node("REQ-1", "a")], {}), set())


class DescribeNodeTests(unittest.TestCase):
    def test_should_render_scenarios_and_dependencies(self):
        text = describe_node(node("REQ-2", "desc", ["REQ-1"]))
        self.assertIn("ID: REQ-2", text)
        self.assertIn("GIVEN x", text)
        self.assertIn("Depends on: REQ-1", text)


class AdaptiveTimeoutTests(unittest.TestCase):
    def test_simple_node_gets_a_shorter_first_turn(self):
        timeout = implementation_timeout(1500, 1200, "Create a settings page with a save button.")
        self.assertEqual(timeout, 630)

    def test_real_github_node_keeps_the_long_budget(self):
        text = (
            "GitHub repository pull request review merge branch protection. "
            "The current session must preserve permissions and persistence."
        )
        timeout = implementation_timeout(1500, 1200, text)
        self.assertEqual(timeout, 900)

    def test_reliability_override_gives_simple_nodes_the_shared_budget(self):
        timeout = implementation_timeout(
            1500, 1200, "Display a static settings heading.", force_complex=True
        )
        self.assertEqual(timeout, 900)

    def test_rewrite_has_an_independent_cap(self):
        self.assertEqual(repair_timeout(580, 1200, rewrite=True), 420)
        self.assertEqual(repair_timeout(580, 1200), 480)

    def test_timed_out_implementation_uses_targeted_repair(self):
        self.assertFalse(should_use_full_rewrite(0, False, True))
        self.assertTrue(should_use_full_rewrite(0, False, False))

    def test_skeleton_timeout_reserves_time_for_nudges(self):
        self.assertEqual(skeleton_timeout(1800, 1200), 600)
        self.assertEqual(skeleton_timeout(600, 1200), 570)

    def test_timeout_text_is_detected_for_session_cleanup(self):
        self.assertTrue(turn_was_timed_out("octos turn timed out"))
        self.assertTrue(turn_was_timed_out("octos timed out after 1200s"))
        self.assertFalse(turn_was_timed_out("provider returned 502"))

    def test_early_stop_text_is_detected(self):
        self.assertTrue(turn_was_early_stopped("octos turn stopped after local verification"))
        self.assertFalse(turn_was_early_stopped("octos turn timed out"))

    def test_fast_pass_is_limited_to_simple_generic_nodes(self):
        self.assertTrue(fast_pass_eligible("Create a settings page with a save button."))
        self.assertTrue(is_complex_node_text(
            "GitHub repository pull request review merge branch protection"
        ))
        self.assertFalse(fast_pass_eligible(
            "GitHub repository pull request review merge branch protection"
        ))

    def test_interactive_note_workflow_is_not_simple_or_early_stoppable(self):
        text = (
            "Create a note from the Take a note button. Open exactly one dialog "
            "named Note editor with uniquely labelled textboxes Title and Note content. "
            "Fill the form and close it; autosave the note article."
        )
        self.assertTrue(is_complex_node_text(text))
        self.assertFalse(fast_pass_eligible(text))
        self.assertFalse(early_stop_eligible(text))

    def test_early_stop_stays_available_for_a_small_shell_task(self):
        self.assertTrue(early_stop_eligible("Display a static settings heading."))

class DomainContextTests(unittest.TestCase):
    def test_github_context_contains_permission_and_merge_invariants(self):
        context = domain_context(
            "GitHub repository pull request review and branch protection",
            "merge forbidden",
        )
        self.assertEqual(context["product_domain"], "github")
        self.assertIn("repository_store", context["state_owner"])
        self.assertEqual(context["failure_reason_hint"], "permission_boundary_mismatch")
        self.assertIn("failed_merge_keeps_pull_request_and_target_branch_unchanged",
                      context["invariants_to_preserve"])

    def test_sheet_context_contains_formula_and_refresh_invariants(self):
        context = domain_context(
            "Workbook worksheet grid formula dependency and pivot refresh",
            "formula dependency is stale after refresh",
        )
        self.assertEqual(context["product_domain"], "sheet")
        self.assertIn("cell_store", context["state_owner"])
        self.assertEqual(context["failure_reason_hint"], "state_persistence_mismatch")
        self.assertIn("formula_bar_keeps_the_original_formula",
                      context["invariants_to_preserve"])

    def test_generic_context_does_not_invent_a_business_domain(self):
        self.assertEqual(infer_product_domain("Create a profile page with a button"), "generic")
        context = domain_context("Create a profile page with a button")
        self.assertEqual(context["product_domain"], "generic")
        self.assertEqual(context["state_owner"], [])


if __name__ == "__main__":
    unittest.main()


class TransientTests(unittest.TestCase):
    def test_should_not_retry_own_turn_timeouts(self):
        self.assertFalse(OctosDriver._transient("octos turn timed out"))
        self.assertFalse(OctosDriver._transient("octos timed out after 900s"))

    def test_should_retry_provider_errors(self):
        self.assertTrue(OctosDriver._transient("HTTP 503 Service Temporarily Unavailable"))
        self.assertTrue(OctosDriver._transient("failed to send streaming request"))


class FolderDescendantTests(unittest.TestCase):
    def test_should_map_every_folder_to_its_atomic_leaves(self):
        tree = {"id": "ROOT", "type": "FOLDER", "children": [
            {"id": "F-1", "type": "FOLDER", "children": [node("REQ-1", "a"), node("REQ-2", "b")]},
            node("REQ-3", "c")]}
        self.assertEqual(folder_descendants(tree), {"F-1": ["REQ-1", "REQ-2"], "ROOT": ["REQ-1", "REQ-2", "REQ-3"]})


class SetupPlaywrightTests(unittest.TestCase):
    """Regression for cloud run d116ad5e3aa0: the private-install branch of
    setup_playwright must unpack (root, env_extra) and expose cleanup."""

    def test_should_use_private_install_tuple_and_clean_it_up(self):
        import argparse, tempfile
        from pathlib import Path
        import main as m
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "tests"; tests.mkdir(); (tests / "REQ-1.spec.ts").write_text("x")
            fake_root = Path(tmp) / "pw"; (fake_root / "node_modules" / "@playwright" / "test").mkdir(parents=True)
            flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp) / "out", Path(tmp) / "req")
            flow.tests_dir = tests
            calls = {}
            def fake_ensure(install_root, log, timeout=540, version="1.63.0"):
                calls["version"] = version
                return fake_root, {"PLAYWRIGHT_BROWSERS_PATH": str(install_root / "browsers")}
            saved = (m.find_playwright_root, m.find_playwright_by_search, m.ensure_playwright)
            m.find_playwright_root = lambda cands: fake_root if cands == [fake_root] else None
            m.find_playwright_by_search = lambda log: None
            m.ensure_playwright = fake_ensure
            try:
                flow.setup_playwright()
            finally:
                m.find_playwright_root, m.find_playwright_by_search, m.ensure_playwright = saved
            self.assertEqual(calls["version"], "1.63.0")
            self.assertIsNotNone(flow.runner)
            self.assertEqual(flow.runner.root, fake_root)
            self.assertIn("PLAYWRIGHT_BROWSERS_PATH", flow.runner.env_extra)
            private = flow.private_playwright
            self.assertTrue(private.exists())
            flow.cleanup_playwright()
            self.assertFalse(private.exists())


class InlineSpecTests(unittest.TestCase):
    def test_should_quote_files_within_budget_and_bail_when_too_big(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp); (tests / "support").mkdir()
            (tests / "REQ-1.spec.ts").write_text("spec body"); (tests / "support" / "e2e.ts").write_text("helper")
            text = inline_spec_text(tests, ["REQ-1.spec.ts", "support/e2e.ts"], 1000)
            self.assertIn("--- REQ-1.spec.ts ---\nspec body", text)
            self.assertIn("--- support/e2e.ts ---\nhelper", text)
            self.assertEqual(inline_spec_text(tests, ["REQ-1.spec.ts", "support/e2e.ts"], 10), "")


class InlineSourcesTests(unittest.TestCase):
    def test_should_quote_small_files_and_omit_those_over_budget(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "backend").mkdir(); (root / "frontend" / "src").mkdir(parents=True)
            (root / "backend" / "server.js").write_text("x" * 100); (root / "frontend" / "src" / "index.html").write_text("<p>hi</p>")
            (root / "frontend" / "node_modules").mkdir(); (root / "frontend" / "node_modules" / "a.js").write_text("no")
            text = inline_sources(root, max_chars=50)
            self.assertIn("--- frontend/src/index.html ---\n<p>hi</p>", text)
            self.assertIn("backend/server.js --- (omitted, 100 chars", text)
            self.assertNotIn("node_modules", text)


class FailureNormalizationTests(unittest.TestCase):
    def test_should_treat_digests_differing_only_in_numbers_as_identical(self):
        import re
        a = "Observation: TIMED OUT after 4136 ms ... Expected: \"2\" Received: \"\""
        b = "Observation: TIMED OUT after 4144 ms ... Expected: \"2\" Received: \"\""
        self.assertEqual(re.sub(r"\d+", "#", a), re.sub(r"\d+", "#", b))


class CodegenPromptTests(unittest.TestCase):
    def test_should_format_without_placeholder_errors_and_keep_build_command(self):
        import main as m
        text = m.CODEGEN_PROMPT.format(node_id="REQ-1", description="S", spec="T", port=3000, ports=" P", size_rule="R")
        self.assertIn("do not output them", text)
        self.assertIn("REQ-1", text)


class CreateResultContractTests(unittest.TestCase):
    def test_should_share_one_contract_across_generation_and_repair_prompts(self):
        contract = m.CREATE_RESULT_CONTRACT
        prompts = {
            "ui_core": m.UI_CONTRACT_CORE,
            "ui_full": m.UI_CONTRACT,
            "design": m.DESIGN_PROMPT.format(node_id="item", node_spec="Create an item",
                                           ancestors="", tests=""),
            "codegen": m.CODEGEN_PROMPT.format(node_id="item", description="Create an item",
                                              spec="", port=3000, ports="", size_rule=""),
            "repair": m.REPAIR_PROMPT.format(node_id="item", passed=0, total=1,
                                            failures="missing result", corrections="",
                                            slow="", sources="", smoke=3001, port=3000),
        }
        for name, prompt in prompts.items():
            with self.subTest(prompt=name):
                self.assertEqual(prompt.count(contract), 1)

    def test_should_include_contract_once_in_implementation_with_inline_design(self):
        import argparse
        from pathlib import Path
        flow = m.Flow(argparse.Namespace(web_port=3000), Path("."), Path("."))
        for description in ("Create a named item", "A counter initially zero"):
            with self.subTest(description=description):
                flow.classify_tree({"description": description})
                prompt = m.NODE_PROMPT.format(
                    preamble="", node_spec=description,
                    design=m.INLINE_DESIGN_NOTE.format(node_id="item"), ancestors="",
                    tests="", ui=flow.ui_contract(), performance="", verify="",
                    smoke=3001, port=3000)
                self.assertEqual(prompt.count(m.CREATE_RESULT_CONTRACT), 1)

    def test_should_require_persisted_success_and_preserve_navigation_without_duplicate_text(self):
        contract = m.CREATE_RESULT_CONTRACT
        for phrase in ("Only for create/save flows with a named entity", "successful 2xx response",
                       "persistence", "stable destination", "exact entity name",
                       "one visible semantic heading", '<h2><a href="...">name</a></h2>',
                       "existing destination", "Do not duplicate", "On failure", "no success heading"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)

    def test_should_keep_contract_generic_and_bounded(self):
        contract = m.CREATE_RESULT_CONTRACT
        self.assertLessEqual(len(contract.split()), 100)
        for literal in ("bookstack", "shelf", "favorite", "req-", "timeout", "retry"):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, contract.lower())

    def test_should_allow_heading_in_separate_design_schema(self):
        self.assertIn("heading", m.DESIGN_PROMPT.split('"role": "', 1)[1].split('"', 1)[0])


class AlreadyPassingProbeTests(unittest.TestCase):
    def test_should_mark_only_fully_passing_nodes_as_unchanged(self):
        import argparse
        from pathlib import Path
        from types import SimpleNamespace
        flow = m.Flow(argparse.Namespace(web_port=1), Path("."), Path("."))
        flow.spec_map = {"REQ-1": ["a.spec.ts"], "REQ-2": ["b.spec.ts"], "REQ-3": [], None: []}
        results = {"a.spec.ts": SimpleNamespace(error=None, total=2, passed=2, all_passed=True),
                   "b.spec.ts": SimpleNamespace(error=None, total=2, passed=1, all_passed=False)}
        flow.run_specs = lambda specs, **kw: results[specs[0]]
        self.assertEqual(flow.already_passing_nodes(["REQ-1", "REQ-2", "REQ-3"]), {"REQ-1"})


class CodegenManifestTests(unittest.TestCase):
    def test_should_write_missing_manifests_once(self):
        import json, tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        self.assertEqual(m.write_codegen_manifests(root), ["frontend/package.json", "backend/package.json"])
        self.assertEqual(m.write_codegen_manifests(root), [])
        fe = json.loads((root / "frontend/package.json").read_text())
        self.assertIn("mkdirSync('dist',{recursive:true})", fe["scripts"]["build"])
        # the build script must run and emit both register.html and extensionless register
        import shutil, subprocess
        node = shutil.which("node") or "/opt/homebrew/opt/node@24/bin/node"
        (root / "frontend/src").mkdir(parents=True)
        (root / "frontend/src/index.html").write_text("i"); (root / "frontend/src/register.html").write_text("r")
        cmd = fe["scripts"]["build"][len("node -e "):].strip('"').replace('\\"', '"')
        subprocess.run([node, "-e", cmd], cwd=root / "frontend", check=True)
        self.assertEqual((root / "frontend/dist/register").read_text(), "r")
        self.assertTrue((root / "frontend/dist/register.html").is_file())
        self.assertFalse((root / "frontend/dist/index").exists())
        be = json.loads((root / "backend/package.json").read_text())
        self.assertEqual(be["scripts"]["start"], "node server.js")
        self.assertEqual(be["type"], "commonjs")


class ExtraPortsBoundTests(unittest.TestCase):
    def test_should_report_unbound_spec_ports_in_grader_like_mode(self):
        import tempfile
        from pathlib import Path
        from acceptance import AppServer
        srv = AppServer(Path(tempfile.mkdtemp()), 3100, lambda s: None, grader_like=True, extra_ports=[3301])
        srv.port = 3100
        err = srv.extra_ports_bound(wait_seconds=0.3)
        self.assertIn("3301", err)
        self.assertIn("ERR_CONNECTION_REFUSED", err)
        srv.extra_ports = []
        self.assertIsNone(srv.extra_ports_bound(wait_seconds=0.1))


class SnapshotSourcesTests(unittest.TestCase):
    def test_should_copy_sources_but_not_node_modules(self):
        import argparse, tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        (root / "frontend/src").mkdir(parents=True); (root / "backend/node_modules/x").mkdir(parents=True)
        (root / "frontend/src/index.html").write_text("<p>")
        (root / "backend/server.js").write_text("x")
        (root / "backend/node_modules/x/i.js").write_text("y")
        flow = m.Flow(argparse.Namespace(web_port=1), root, root)
        dest = flow.snapshot_sources("REQ-1", 0)
        self.assertTrue((dest / "frontend/src/index.html").is_file())
        self.assertTrue((dest / "backend/server.js").is_file())
        self.assertFalse((dest / "backend/node_modules").exists())
