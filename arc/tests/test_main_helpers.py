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


class RequirementOnlyContextTests(unittest.TestCase):
    def test_outline_is_bounded_and_uses_harness_parsed_nodes(self):
        tree = {"id": "ROOT", "type": "FOLDER", "children": [
            node(f"REQ-{i}", "word " * 30) for i in range(1, 12)
        ]}
        text = m.requirement_outline(tree, max_chars=240)
        self.assertLessEqual(len(text), 240)
        self.assertIn("REQ-1", text)

    def test_requirement_only_prompt_forbids_test_search_and_keeps_shell(self):
        import argparse
        from pathlib import Path
        from types import SimpleNamespace
        flow = m.Flow(argparse.Namespace(web_port=3000), Path("."), Path("."))
        flow.llm_proxy = SimpleNamespace(extra_drop_tools={"shell"})
        text = flow.verify_text(1, has_specs=False).lower()
        self.assertIn("do not search", text)
        self.assertIn("not an official test verdict", text)
        self.assertIn("npm run build", text)
        self.assertEqual(flow.llm_proxy.extra_drop_tools, set())

    def test_requirement_only_execution_writes_before_more_exploration(self):
        text = m.REQUIREMENT_ONLY_EXECUTION_GUIDANCE.lower()
        self.assertIn("tool call 3", text)
        self.assertIn("first product write", text)
        self.assertIn("do not search", text)


class ProductFingerprintTests(unittest.TestCase):
    def test_counts_product_source_but_ignores_build_lock_and_runtime_db(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontend" / "src").mkdir(parents=True)
            (root / "frontend" / "dist").mkdir()
            (root / "backend").mkdir()
            (root / "frontend" / "src" / "app.tsx").write_text("export const x=1")
            (root / "backend" / "server.js").write_text("module.exports={}")
            baseline = m.product_fingerprint(root)
            (root / "frontend" / "dist" / "bundle.js").write_text("generated")
            (root / "frontend" / "package-lock.json").write_text("{}")
            (root / "backend" / "db.json").write_text('{"mutated":true}')
            self.assertEqual(m.product_fingerprint(root), baseline)
            (root / "frontend" / "src" / "app.tsx").write_text("export const x=2")
            self.assertNotEqual(m.product_fingerprint(root), baseline)

    def test_cap_hit_or_missing_write_evidence_never_counts_as_complete(self):
        self.assertEqual(
            m.product_turn_incomplete_reason(wrote=True, budget_exhausted=True),
            "request_budget_exhausted")
        self.assertEqual(
            m.product_turn_incomplete_reason(wrote=False, budget_exhausted=False),
            "untracked_product_write")
        self.assertIsNone(m.product_turn_incomplete_reason(wrote=True, budget_exhausted=False))


class BundledSkillStagingTests(unittest.TestCase):
    def test_stages_context_skill_and_registers_parent_path(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            skill = bundle / "skills" / "arc-project-context"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: arc-project-context\n---\n")
            (skill / "manifest.json").write_text(json.dumps({"name": "arc-project-context"}))
            (skill / "index.js").write_text("process.exit(0)")
            (skill / "main").write_text("#!/bin/sh\n")
            data = root / "data"
            staged = m.stage_bundled_skills(data, bundle)
            self.assertEqual(staged, data / "skills")
            self.assertTrue((data / "skills" / "arc-project-context" / "main").is_file())


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
            limited = inline_spec_text(tests, ["REQ-1.spec.ts", "support/e2e.ts"], 10)
            self.assertIn("OMITTED SPEC RANGES", limited)
            self.assertIn("sha256=", limited)


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

    def test_should_bound_rewrite_requests_on_multi_node_tasks(self):
        import os
        flow = self._flow()
        flow.n_nodes = 32
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        os.environ.pop("OCTOS_ARC_REWRITE_REQUESTS", None)
        self.assertGreater(flow.implement_request_budget(), 0)
        self.assertLessEqual(flow.rewrite_request_budget(), 8)

    def test_should_cap_rewrite_like_implement_on_small_tasks(self):
        import os
        flow = self._flow()
        flow.n_nodes = 1
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        os.environ.pop("OCTOS_ARC_REWRITE_REQUESTS", None)
        self.assertEqual(flow.implement_request_budget(), 22)
        self.assertLessEqual(flow.rewrite_request_budget(), 8)

    def test_should_give_multi_node_implement_enough_requests_to_write_code(self):
        """Platform runs 2b6a1f545c37 (sheet 0/24) and 0564f5955f16 (github
        0/47) hit "request budget 8 hit" on every node — turns were forced to
        finish before code was written (wrote=False verified=False, feature
        0%). A multi-node implement turn needs enough requests to read, write,
        and verify one node, not the starvation cap of 8."""
        import os
        flow = self._flow()
        flow.n_nodes = 32
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        self.assertEqual(flow.implement_request_budget(), 22)
        self.assertEqual(flow.continuation_request_budget(), 12)
        self.assertLessEqual(flow.max_node_request_budget(), 36)

    def test_should_give_large_tree_implement_enough_requests_to_finish_a_node(self):
        """Platform run 3d6713b1 (prestashop, 87 tests / 47 implement nodes)
        scored 13/100: 92 nodes hit "request budget 18 hit" and ended
        wrote=False/verified=False across the whole second half of the tree.
        A feature node must implement + `npm run build` + curl-verify in one
        turn; 18 requests runs out before the node is written and verified on a
        large app, so the multi-node default is raised to give that headroom.
        Env OCTOS_ARC_IMPLEMENT_REQUESTS still overrides for cost control."""
        import os
        flow = self._flow()
        flow.n_nodes = 47
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        self.assertEqual(flow.implement_request_budget(), 22)
        self.assertEqual(flow.continuation_request_budget(), 12)

    def test_should_give_skeleton_room_to_scaffold_both_ends(self):
        """The skeleton turn writes a whole app shell (frontend + backend
        package.json, entrypoints, build/start scripts). On the same two runs
        the very first "request budget 8 hit" fired during "skeleton attempt
        1", so the scaffold could not finish either end. It must get a larger
        budget than a single implement node."""
        import os
        flow = self._flow()
        flow.n_nodes = 32
        os.environ.pop("OCTOS_ARC_SKELETON_REQUESTS", None)
        os.environ.pop("OCTOS_ARC_IMPLEMENT_REQUESTS", None)
        self.assertGreaterEqual(flow.skeleton_request_budget(), flow.implement_request_budget())
        # The skeleton now lays the whole shared foundation (router table, a
        # seeded collection per entity, page shell) in one turn, so it needs
        # more room than a single feature node, not just 20.
        self.assertGreaterEqual(flow.skeleton_request_budget(), 28)


class SharedFoundationTests(unittest.TestCase):
    """Github run arc-agent-...-9ff7e750 (0/47): budget reached code, but 94
    of 98 turns ended verified=False because every node rebuilt shared
    infrastructure from scratch ("does not exist and must be built from
    scratch", "No files were changed this turn"). The skeleton must lay the
    shared router/seed foundation once, and extend turns must be told it
    already exists so they do not re-discover it."""

    def test_skeleton_prompt_asks_for_shared_router_and_seed_foundation(self):
        text = m.SKELETON_PROMPT.format(req_dir="/r", port=3000, smoke=3001, tests="",
                                         requirements_outline="- REQ-1: base", requirement_contract="{}")
        lowered = text.lower()
        self.assertIn("router", lowered)
        self.assertIn("seed", lowered)

    def test_extend_preamble_states_foundation_exists_so_nodes_do_not_rebuild(self):
        text = m.NODE_PREAMBLE_EXTEND.format(node_id="REQ-1")
        lowered = text.lower()
        self.assertIn("exist", lowered)
        # It must steer away from rebuilding, not just say "extend".
        self.assertTrue("do not" in lowered or "don't" in lowered or "reuse" in lowered)

    def test_inline_design_note_does_not_force_a_separate_design_file_write(self):
        """The old note made every implement turn write .arc/design/<id>.json
        to disk before any code — a write_file round trip spent before the
        feature. Planning stays; the mandatory design-file write goes (the note
        may still name the path to tell the model NOT to spend a call on it)."""
        text = m.INLINE_DESIGN_NOTE.format(node_id="REQ-1").lower()
        # No imperative to write/save the design JSON to disk.
        self.assertNotIn("write your design", text)
        self.assertNotIn("write one json object", text)
        # Planning intent is retained.
        self.assertTrue("implement" in text and ("route" in text or "plan" in text or "name the" in text))


class SingleOriginContractTests(unittest.TestCase):
    """Github run arc-agent-...-7fc46206 (0/100 despite 31 verified=True): the
    skeleton built a SPLIT model — API-only backend plus a frontend that calls
    `http://127.0.0.1:3001` through a hardcoded API_BASE. The agent's own curl
    smoke used that port so it self-reported verified=True, but the grader loads
    the page from its own host/port where 3001 has no server, so every API
    request failed and every test failed. The architecture contract and the
    skeleton must forbid absolute origins and mandate same-origin relative
    paths; extend turns must not reintroduce a host:port constant."""

    def test_architecture_contract_forbids_hardcoded_absolute_origin(self):
        text = m.ARCHITECTURE_CONTRACT.format(port=3000).lower()
        self.assertIn("same-origin", text)
        self.assertIn("127.0.0.1", text)  # named as the thing NOT to hardcode
        self.assertTrue("never hardcode" in text or "never" in text and "api_base" in text)

    def test_skeleton_prompt_mandates_single_port_relative_fetch(self):
        text = m.SKELETON_PROMPT.format(req_dir="/r", port=3000, smoke=3001, tests="",
                                         requirements_outline="- REQ-1: base", requirement_contract="{}").lower()
        self.assertIn("same-origin", text)
        self.assertIn("/api/", text)

    def test_extend_preamble_warns_against_absolute_origin(self):
        text = m.NODE_PREAMBLE_EXTEND.format(node_id="REQ-1").lower()
        self.assertTrue("relative" in text or "same-origin" in text)


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
                    smoke=3001, port=3000, execution="")
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


class WorkflowStateContractTests(unittest.TestCase):
    def test_should_share_conditional_workflow_contract_across_agent_turns(self):
        import argparse
        from pathlib import Path

        flow = m.Flow(argparse.Namespace(web_port=3000), Path("."), Path("."))
        flow.classify_tree({"description": "Open an existing parent record, create a draft, edit it, then filter the list"})
        prompts = {
            "design": m.DESIGN_PROMPT.format(node_id="record", node_spec="Edit a record",
                                             ancestors="", tests=""),
            "codegen": m.CODEGEN_PROMPT.format(node_id="record", description="Edit a record",
                                               spec="", port=3000, ports="", size_rule=""),
            "implementation": m.NODE_PROMPT.format(
                preamble="", node_spec="Edit a record", design="", ancestors="", tests="",
                ui=flow.ui_contract(), performance="", verify="", smoke=3001, port=3000,
                execution=""),
            "repair": m.REPAIR_PROMPT.format(node_id="record", passed=0, total=1,
                                             failures="missing action", corrections="", slow="",
                                             sources="", smoke=3001, port=3000),
        }
        for name, prompt in prompts.items():
            with self.subTest(prompt=name):
                self.assertEqual(prompt.count(m.WORKFLOW_STATE_CONTRACT), 1)
        for phrase in ("existing named record or parent/context", "draft-save distinct",
                       "editor's accessible scope", "preserve unsaved content",
                       "preserve the selected filter", "one navigation owner"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, m.WORKFLOW_STATE_CONTRACT)
        self.assertNotIn("bookstack", m.WORKFLOW_STATE_CONTRACT.lower())
        self.assertNotIn("arc-bench-lite--keep", m.WORKFLOW_STATE_CONTRACT.lower())
        self.assertNotIn("req-", m.WORKFLOW_STATE_CONTRACT.lower())

    def test_should_enable_seed_contract_for_existing_parent_context_language(self):
        import argparse
        from pathlib import Path

        flow = m.Flow(argparse.Namespace(web_port=3000), Path("."), Path("."))
        flow.classify_tree({"description": "Start from an existing parent context before creating a record"})
        self.assertTrue(flow.needs_data)
        self.assertIn("seed that required starting record once", flow.ui_contract())
        self.assertIn("Do not pre-create an entity", flow.ui_contract())

    def test_should_match_frozen_label_locators_to_editor_scope_contract(self):
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        tests = (repo / "workstreams/arc-bench/official-snapshots/20260917-150121Z/competitions/"
                 "arc-bench-lite/tasks/arc-bench-lite--keep/public-tests")
        helper = (tests / "helpers.ts").read_text(encoding="utf-8")
        locator = "noteEditor(page).getByRole('checkbox'"
        self.assertIn(locator, helper)
        for name in ("REQ-2.7.1.spec.ts", "REQ-2.7.2.spec.ts", "REQ-2.7.4.spec.ts"):
            with self.subTest(spec=name):
                self.assertIn("setLabel(page", (tests / name).read_text(encoding="utf-8"))
        self.assertIn("in that editor's accessible scope", m.WORKFLOW_STATE_CONTRACT)
        self.assertIn("prefer a fieldset, region, or disclosure panel over a second dialog",
                      m.WORKFLOW_STATE_CONTRACT)

    def test_should_preserve_frozen_context_and_draft_authoring_sequences(self):
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        tests = (repo / "workstreams/arc-bench/official-snapshots/20260917-150121Z/competitions/"
                 "arc-bench-lite/tasks/arc-bench-lite--bookstack/public-tests")
        helper = (tests / "helpers.ts").read_text(encoding="utf-8")
        shelf_create = (tests / "REQ-4.3.1.spec.ts").read_text(encoding="utf-8")
        shelf_cancel = (tests / "REQ-4.3.2.spec.ts").read_text(encoding="utf-8")
        draft_save = (tests / "REQ-6.1.2.spec.ts").read_text(encoding="utf-8")
        draft_delete = (tests / "REQ-6.1.3.spec.ts").read_text(encoding="utf-8")

        self.assertIn("h.openShelfDetails(page, h.FIXTURES.shelves.create.contextName)", shelf_create)
        self.assertIn("h.openShelfDetails(page, h.FIXTURES.shelves.cancelCreate.contextName)", shelf_cancel)
        self.assertIn("await clickNamed(page, /^New Page$/i)", helper)
        self.assertIn("await clickNamed(page, /^Edit$/i)", helper)
        self.assertIn("/^Save Draft$/i", draft_save)
        self.assertIn("/^Delete Draft$/i", draft_delete)
        self.assertIn("draft-save distinct from the existing publish/save action", m.WORKFLOW_STATE_CONTRACT)
        self.assertIn("available from the editor the flow enters", m.WORKFLOW_STATE_CONTRACT)
        self.assertIn("enter edit mode only when invoked", m.WORKFLOW_STATE_CONTRACT)


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

    def test_scaffold_gate_rejects_manifests_without_real_entries(self):
        import argparse
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontend").mkdir()
            (root / "backend").mkdir()
            manifest = {"scripts": {"build": "node build.js"}}
            (root / "frontend/package.json").write_text(json.dumps(manifest))
            (root / "backend/package.json").write_text(json.dumps({"scripts": {"start": "node server.js"}}))
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root / "requirements")
            self.assertFalse(flow.has_app())


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


class RecoveryScaffoldTests(unittest.TestCase):
    def _flow(self, root):
        import argparse
        return m.Flow(argparse.Namespace(web_port=3000), root, root / "requirements")

    def test_quota_checkpoint_keeps_provider_reason_without_argument_collision(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = self._flow(root)
            flow.enter_quota_gate("HTTP 402: billing quota exhausted")
            self.assertTrue(flow.quota_gated)
            checkpoints = list((root / ".arc" / "checkpoints").glob("cp-*.json"))
            self.assertTrue(checkpoints)
            payload = json.loads(checkpoints[-1].read_text(encoding="utf-8"))
            self.assertEqual(payload["reason"], "quota_gated")
            self.assertEqual(payload["quota_reason"], "HTTP 402: billing quota exhausted")

    def test_node_state_reason_is_diagnostic_and_does_not_replace_event(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = self._flow(root)
            flow.set_node_state("REQ-1", "inconclusive", reason="implement_timeout")
            checkpoints = list((root / ".arc" / "checkpoints").glob("cp-*.json"))
            self.assertTrue(checkpoints)
            payload = json.loads(checkpoints[-1].read_text(encoding="utf-8"))
            self.assertEqual(payload["reason"], "node_state")
            self.assertEqual(payload["state_reason"], "implement_timeout")

    def test_fallback_fills_missing_scaffold_and_is_buildable(self):
        import json
        import os
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "frontend/src/components"
            nested.mkdir(parents=True)
            (nested / "placeholder.txt").write_text("nested", encoding="utf-8")
            flow = self._flow(root)
            self.assertTrue(flow.ensure_minimal_scaffold())
            self.assertTrue(flow.has_app())
            frontend = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
            backend = json.loads((root / "backend/package.json").read_text(encoding="utf-8"))
            self.assertEqual(frontend["scripts"]["build"], "node copy.js")
            self.assertEqual(backend["scripts"]["start"], "node server.js")
            self.assertTrue((root / "frontend/src/index.html").is_file())
            self.assertTrue((root / "backend/server.js").is_file())
            node = shutil.which("node")
            if not node:
                self.skipTest("node is required for scaffold build/start smoke")
            subprocess.run([node, "copy.js"], cwd=root / "frontend", check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertTrue((root / "frontend/dist/index.html").is_file())
            self.assertEqual((root / "frontend/dist/components/placeholder.txt").read_text(encoding="utf-8"), "nested")
            import socket
            import time
            import urllib.request
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, PORT=str(port))
            server = subprocess.Popen([node, "server.js"], cwd=root / "backend", env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(30):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2) as response:
                            self.assertEqual(response.status, 200)
                            break
                    except Exception:
                        time.sleep(0.05)
                else:
                    self.fail("minimal backend did not become ready")
            finally:
                server.terminate()
                server.wait(timeout=5)

    def test_fallback_never_overwrites_nonempty_business_files(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontend").mkdir(parents=True)
            (root / "backend").mkdir(parents=True)
            frontend_manifest = root / "frontend/package.json"
            backend_server = root / "backend/server.js"
            frontend_manifest.write_text('{"custom":"business"}', encoding="utf-8")
            backend_server.write_text("// business implementation", encoding="utf-8")
            flow = self._flow(root)
            self.assertFalse(flow.ensure_minimal_scaffold())
            self.assertEqual(frontend_manifest.read_text(encoding="utf-8"), '{"custom":"business"}')
            self.assertEqual(backend_server.read_text(encoding="utf-8"), "// business implementation")


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
