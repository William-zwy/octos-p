import unittest

from main import OctosDriver, describe_node, folder_descendants, inline_sources, inline_spec_text, unchanged_node_ids
import main as m


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


class AcceptanceSuiteIdentityTests(unittest.TestCase):
    def _tree(self, task_id, title, marker):
        return {
            "id": task_id,
            "name": title,
            "type": "FOLDER",
            "description": marker,
            "dependencies": [],
            "children": [node("REQ-1", marker)],
        }

    def _bundle(self, root, manifest, suite_ids):
        import json
        bundled = root / "public-tests"
        bundled.mkdir()
        (bundled / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for suite_id in suite_ids:
            suite = bundled / suite_id
            suite.mkdir()
            (suite / "REQ-1.spec.ts").write_text("test('identity', () => {})", encoding="utf-8")
        return bundled

    def _v2(self, *entries):
        return {"version": 2, "fingerprint": "sha256-canonical-json-v1", "suites": list(entries)}

    def _entry(self, suite_id, tree):
        return {
            "id": suite_id,
            "title": tree["name"],
            "requirement_tree_sha256": m.requirement_tree_fingerprint(tree),
        }

    def test_should_select_lite_bookstack_by_exact_tree_identity(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        lite = self._tree("ROOT", "BookStack Knowledge Base System", "lite")
        web = self._tree("ROOT", "BookStack Knowledge Base System", "web")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(m.os.environ, {"ARCBENCH_TESTS_DIR": ""}):
            root = Path(tmp)
            self._bundle(root, self._v2(
                self._entry("arc-bench-web--bookstack", web),
                self._entry("arc-bench-lite--bookstack", lite),
            ), ["arc-bench-web--bookstack", "arc-bench-lite--bookstack"])
            self.assertEqual(m.locate_acceptance_tests(lite, root).name, "arc-bench-lite--bookstack")

    def test_should_select_web_bookstack_by_exact_tree_identity(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        lite = self._tree("ROOT", "BookStack Knowledge Base System", "lite")
        web = self._tree("ROOT", "BookStack Knowledge Base System", "web")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(m.os.environ, {"ARCBENCH_TESTS_DIR": ""}):
            root = Path(tmp)
            self._bundle(root, self._v2(
                self._entry("arc-bench-web--bookstack", web),
                self._entry("arc-bench-lite--bookstack", lite),
            ), ["arc-bench-web--bookstack", "arc-bench-lite--bookstack"])
            self.assertEqual(m.locate_acceptance_tests(web, root).name, "arc-bench-web--bookstack")

    def test_should_disable_bundled_tests_when_same_title_has_no_exact_identity(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        lite = self._tree("ROOT", "BookStack Knowledge Base System", "lite")
        web = self._tree("ROOT", "BookStack Knowledge Base System", "web")
        unknown = self._tree("ROOT", "BookStack Knowledge Base System", "unknown")
        messages = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(m.os.environ, {"ARCBENCH_TESTS_DIR": ""}), mock.patch.object(m, "log", messages.append):
            root = Path(tmp)
            self._bundle(root, self._v2(
                self._entry("arc-bench-web--bookstack", web),
                self._entry("arc-bench-lite--bookstack", lite),
            ), ["arc-bench-web--bookstack", "arc-bench-lite--bookstack"])
            self.assertIsNone(m.locate_acceptance_tests(unknown, root))
        self.assertTrue(any("identity ambiguity" in line and "disabled" in line for line in messages))

    def test_should_keep_unique_title_compatibility_for_legacy_manifest(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        tree = self._tree("ROOT", "Legacy Task", "legacy")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(m.os.environ, {"ARCBENCH_TESTS_DIR": ""}):
            root = Path(tmp)
            self._bundle(root, {"legacy--task": "Legacy Task"}, ["legacy--task"])
            self.assertEqual(m.locate_acceptance_tests(tree, root).name, "legacy--task")


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


class CoreRegressionTests(unittest.TestCase):
    """Cross-node breakage travels along shared UI/data surface, not the
    declared dependency edges. keep-0927 REQ-2.4 (Update Note) passed alone
    (4/4) but a later editor-touching node (2.5.x/2.7.x) rewrote the note card
    and broke the 'Note content' textbox; dep-regression never re-ran 2.4
    because 2.4 was not a *declared* ancestor. acceptance_specs_for() must
    backfill the remaining regression budget with the earliest already-passed
    node specs so a foundational spec is protected on every later node."""

    def _flow(self):
        import argparse
        from pathlib import Path
        flow = m.Flow(argparse.Namespace(web_port=3000), Path("."), Path("."))
        # 3 nodes: A (base), B (editor CRUD, NOT declared as C's dependency), C.
        flow.ordered_nodes = [
            {"id": "A", "dependencies": []},
            {"id": "B", "dependencies": ["A"]},
            {"id": "C", "dependencies": ["A"]},  # C depends on A only, NOT B
        ]
        flow.spec_map = {None: [], "A": ["A.spec.ts"], "B": ["B.spec.ts"], "C": ["C.spec.ts"]}
        return flow

    def test_should_regress_passed_nonancestor_spec_when_budget_allows(self):
        import os
        flow = self._flow()
        flow.test_verdict = {"A": True, "B": True}  # both built and passed
        os.environ.pop("OCTOS_ARC_CORE_REGRESSION", None)
        os.environ.pop("OCTOS_ARC_CORE_REGRESSION_SPECS", None)
        specs = flow.acceptance_specs_for("C")
        # B is not a declared ancestor of C, but it passed earlier and the
        # budget has room, so it must be regressed to catch shared-UI breakage.
        self.assertIn("B.spec.ts", specs)
        self.assertIn("C.spec.ts", specs)  # own spec always first
        self.assertIn("A.spec.ts", specs)  # declared ancestor

    def test_should_not_add_core_regression_when_disabled(self):
        import os
        flow = self._flow()
        flow.test_verdict = {"A": True, "B": True}
        os.environ["OCTOS_ARC_CORE_REGRESSION"] = "0"
        try:
            specs = flow.acceptance_specs_for("C")
        finally:
            os.environ.pop("OCTOS_ARC_CORE_REGRESSION", None)
        self.assertNotIn("B.spec.ts", specs)  # B is not a declared ancestor
        self.assertIn("A.spec.ts", specs)      # A still comes in as ancestor


class RewriteBudgetTests(unittest.TestCase):
    """A full rewrite re-implements the whole node; it must get the same
    request budget as the implement turn, not the hardcoded 20 that starved
    REQ-2.5.1's rewrite (keep-0927-v2_1-f: 900s implement timeout -> rewrite
    forced to finish at 20 requests -> 0/4)."""

    def _flow(self):
        import argparse
        from pathlib import Path
        return m.Flow(argparse.Namespace(web_port=3000), Path("."), Path("."))

    def test_should_give_rewrite_unlimited_requests_on_multi_node_tasks(self):
        import os
        flow = self._flow()
        flow.n_nodes = 32
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        os.environ.pop("OCTOS_ARC_REWRITE_REQUESTS", None)
        # 0 == uncapped, matching the implement turn on a 32-node task.
        self.assertEqual(flow.implement_request_budget(), 0)

    def test_should_cap_rewrite_like_implement_on_small_tasks(self):
        import os
        flow = self._flow()
        flow.n_nodes = 1
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        os.environ.pop("OCTOS_ARC_REWRITE_REQUESTS", None)
        self.assertEqual(flow.implement_request_budget(), 20)


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

    def test_should_share_urgent_ui_contract_across_design_codegen_and_repair(self):
        phrases = (
            "after a successful login",
            "every declared UI action has an explicit reachable handler",
            "not unconditional toggle inversion",
            "Detail and draft pages",
            "Authenticated dashboard",
            "aria-pressed=\"true\"|\"false\"",
        )
        prompts = {
            "design": m.DESIGN_PROMPT.format(node_id="item", node_spec="Edit an item",
                                             ancestors="", tests=""),
            "codegen": m.CODEGEN_PROMPT.format(node_id="item", description="Edit an item",
                                                spec="", port=3000, ports="", size_rule=""),
            "repair": m.REPAIR_PROMPT.format(node_id="item", passed=0, total=1,
                                              failures="missing action", corrections="",
                                              slow="", sources="", smoke=3001, port=3000),
        }
        for prompt_name, prompt in prompts.items():
            for phrase in phrases:
                with self.subTest(prompt=prompt_name, phrase=phrase):
                    self.assertIn(phrase, prompt)


class StructuralSelfCheckTests(unittest.TestCase):
    def test_should_report_high_confidence_ui_and_route_contract_breaks(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontend/src").mkdir(parents=True)
            (root / "backend").mkdir()
            (root / "frontend/package.json").write_text(
                json.dumps({"scripts": {"build": "node build.js"}}))
            (root / "backend/package.json").write_text(
                json.dumps({"scripts": {"start": "node server.js"}}))
            (root / "backend/server.js").write_text(
                "const http=require('http'); http.createServer((req,res)=>res.end()).listen(3000);")
            (root / "frontend/src/index.html").write_text(
                '<h1>Dashboard</h1><h2>Dashboard</h2>'
                '<input id="nickname"><button id="edit-item">Edit</button>'
                '<button data-edit-shelf>Edit shelf</button>'
                '<button>Favorite</button>')
            findings = m.structural_self_check(
                root,
                design={
                    "routes": [{"method": "PUT", "path": "/api/items/:id"}],
                    "pages": [{"path": "/items/:id", "elements": [
                        {"role": "button", "name": "Confirm Delete"}]}],
                },
                requirement_text="Users can favorite an item",
            )
            text = "\n".join(findings)
            self.assertIn("control #nickname has 0 explicit labels", text)
            self.assertIn("renders heading 'dashboard' 2 times", text)
            self.assertIn("button #edit-item", text)
            self.assertIn("button [data-edit-shelf]", text)
            self.assertIn("declared route PUT /api/items/:id", text)
            self.assertIn("declared button 'Confirm Delete'", text)
            self.assertIn("Favorite/Unfavorite button lacks aria-pressed", text)

    def test_should_accept_minimal_well_wired_generated_app(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontend/src").mkdir(parents=True)
            (root / "backend").mkdir()
            (root / "frontend/package.json").write_text(
                json.dumps({"scripts": {"build": "node build.js"}}))
            (root / "backend/package.json").write_text(
                json.dumps({"scripts": {"start": "node server.js"}}))
            (root / "frontend/src/index.html").write_text(
                '<h1>Profile</h1><label for="nickname">Nickname</label>'
                '<input id="nickname"><button id="save" type="submit">Save</button>')
            (root / "backend/server.js").write_text(
                "const http=require('http'); http.createServer((req,res)=>res.end()).listen(3000);")
            self.assertEqual(m.structural_self_check(root), [])


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


class ApplicationContractTests(unittest.TestCase):
    def test_should_include_shared_contract_and_bounded_dependency_specs(self):
        import argparse
        import json
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            flow = m.Flow(argparse.Namespace(web_port=1), out, Path(tmp) / "req")
            ordered = [
                node("REQ-1", "base"),
                node("REQ-2", "middle", ["REQ-1"]),
                node("REQ-3", "leaf", ["REQ-2"]),
            ]
            flow.spec_map = {
                "REQ-1": ["REQ-1.spec.ts"],
                "REQ-2": ["REQ-2.spec.ts"],
                "REQ-3": ["REQ-3.spec.ts"],
                None: [],
            }
            flow.designs["REQ-1"] = {
                "routes": [{"method": "GET", "path": "/api/items"}],
                "pages": [{"path": "/", "elements": [{"role": "heading", "name": "Items"}]}],
                "data_model": {"items": {"name": "string"}},
            }
            flow.initialize_application_contract({"id": "ROOT"}, ordered)
            self.assertEqual(flow.acceptance_specs_for("REQ-3"), [
                "REQ-3.spec.ts", "REQ-1.spec.ts", "REQ-2.spec.ts"])
            os.environ["OCTOS_ARC_DEP_REGRESSION_MAX_SPECS"] = "1"
            try:
                self.assertEqual(flow.acceptance_specs_for("REQ-3"), [
                    "REQ-3.spec.ts", "REQ-1.spec.ts"])
            finally:
                os.environ.pop("OCTOS_ARC_DEP_REGRESSION_MAX_SPECS", None)
            payload = json.loads((out / ".arc" / "application-contract.json").read_text())
            self.assertIn("REQ-1", payload["requirements"][0]["id"])
            self.assertEqual(payload["routes"]["GET /api/items"], ["REQ-1"])
            self.assertEqual(payload["acceptance_ownership"]["REQ-3.spec.ts"], "REQ-3")
            self.assertIn("invariants", payload)

    def test_should_inject_only_own_spec_while_running_ancestor_regression(self):
        import argparse
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            tests = Path(tmp) / "tests"
            tests.mkdir()
            (tests / "REQ-1.spec.ts").write_text("test('base', () => { /* BASE_BODY */ });")
            (tests / "REQ-2.spec.ts").write_text("test('leaf', () => { /* LEAF_BODY */ });")
            flow = m.Flow(argparse.Namespace(web_port=3000), out, Path(tmp) / "req")
            flow.tests_dir = tests
            flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"], "REQ-2": ["REQ-2.spec.ts"], None: []}
            ordered = [node("REQ-1", "base"), node("REQ-2", "leaf", ["REQ-1"])]
            flow.initialize_application_contract({"id": "ROOT"}, ordered)
            # Acceptance still runs the ancestor spec to catch regressions.
            self.assertEqual(flow.acceptance_specs_for("REQ-2"), ["REQ-2.spec.ts", "REQ-1.spec.ts"])
            # But the implement/design prompts see only the node's own spec, so
            # the model stays focused and is not tempted to edit ancestor tests.
            self.assertIn("LEAF_BODY", flow.spec_bodies("REQ-2"))
            self.assertNotIn("BASE_BODY", flow.spec_bodies("REQ-2"))
            prompt = flow.tests_prompt_for("REQ-2")
            self.assertIn("REQ-2.spec.ts", prompt)
            self.assertNotIn("REQ-1.spec.ts", prompt)

    def test_should_skip_context_injection_when_no_cross_node_state_exists(self):
        import argparse
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            flow = m.Flow(argparse.Namespace(web_port=1), out, Path(tmp) / "req")
            flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"], None: []}
            flow.initialize_application_contract({"id": "ROOT"}, [node("REQ-1", "base")])
            # skeleton / first node: nothing implemented, passed, or designed yet.
            self.assertEqual(flow.application_context_text(None), "")

    def test_should_omit_invariants_until_a_node_is_implemented(self):
        import argparse
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            flow = m.Flow(argparse.Namespace(web_port=1), out, Path(tmp) / "req")
            flow.spec_map = {"REQ-1": ["REQ-1.spec.ts"], "REQ-2": ["REQ-2.spec.ts"], None: []}
            ordered = [node("REQ-1", "base"), node("REQ-2", "leaf", ["REQ-1"])]
            flow.designs["REQ-1"] = {"routes": [{"method": "GET", "path": "/api/items"}]}
            flow.initialize_application_contract({"id": "ROOT"}, ordered)
            # a design exists but nothing implemented: context flows, invariants do not.
            text = flow.application_context_text("REQ-2")
            self.assertIn("APPLICATION CONTRACT", text)
            self.assertNotIn("invariants", text)
            # once a node is implemented, the protect-existing-work invariants apply.
            flow.implemented_nodes.add("REQ-1")
            flow.update_application_contract()
            self.assertIn("invariants", flow.application_context_text("REQ-2"))


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
