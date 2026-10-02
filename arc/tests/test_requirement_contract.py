import json
import unittest

from requirement_contract import compact_contract, compile_requirement_contract


def tree(*nodes, name="Synthetic App"):
    return {"id": "ROOT", "name": name, "type": "FOLDER", "description": "A reloadable app.",
            "children": list(nodes)}


def node(node_id, description, scenarios):
    return {"id": node_id, "type": "ATOMIC", "name": node_id, "description": description,
            "dependencies": [], "scenarios": scenarios}


class RequirementContractTests(unittest.TestCase):
    def test_compiles_steps_fixtures_and_evidence_without_inventing_locators(self):
        contract = compile_requirement_contract(tree(node(
            "REQ-1", "The current account can reopen the target record after reload.", [{
                "name": "Update record",
                "steps": [
                    {"keyword": "GIVEN", "content": "User is signed in with account `demo@example.com`."},
                    {"keyword": "WHEN", "content": "Click the `Save` button for the selected record."},
                    {"keyword": "THEN", "content": "The record remains saved after reload."},
                ],
            }]
        )))
        item = contract["nodes"][0]
        self.assertEqual(contract["atomic_count"], 1)
        self.assertEqual(contract["scenario_count"], 1)
        self.assertIn("demo@example.com", item["scenarios"][0]["facts"]["exact_values"])
        self.assertIn("Save", item["scenarios"][0]["facts"]["exact_values"])
        self.assertEqual(item["scenarios"][0]["facts"]["actions"], ["Click the `Save` button for the selected record."])
        self.assertTrue(item["scenarios"][0]["facts"]["persistence_hints"])
        self.assertIn("evidence", item["scenarios"][0]["steps"][0])
        self.assertEqual(item["facts"]["paths"], [])
        self.assertIn("refresh_reopen_result", item["acceptance_contract"])
        self.assertTrue(contract["capabilities"])
        self.assertTrue(any(item["kind"] == "refresh_reopen" for item in contract["invariants"]))

    def test_compact_contract_is_valid_json_and_bounded(self):
        contract = compile_requirement_contract(tree(*[
            node(f"REQ-{i}", "x" * 600, [{"name": "s", "steps": [{"keyword": "THEN", "content": "y" * 500}]}])
            for i in range(10)
        ]))
        text = compact_contract(contract, max_chars=900)
        self.assertLessEqual(len(text), 900)
        self.assertTrue(json.loads(text))
        node_text = compact_contract(contract, node_id="REQ-1", max_chars=700)
        self.assertLessEqual(len(node_text), 700)
        self.assertTrue(json.loads(node_text))

    def test_empty_folder_is_not_falsely_counted_as_atomic(self):
        contract = compile_requirement_contract(tree({"id": "FOLDER", "type": "FOLDER", "children": []}))
        self.assertEqual(contract["atomic_count"], 0)

    def test_global_summary_keeps_large_tree_identity_within_prompt_budget(self):
        contract = compile_requirement_contract(tree(*[
            node(f"REQ-{i}", "description", [{"name": "s", "steps": []}])
            for i in range(47)
        ]))
        text = compact_contract(contract, max_chars=7000)
        payload = json.loads(text)
        self.assertEqual(payload["atomic_count"], 47)
        self.assertIn("REQ-0", text)
        self.assertIn("REQ-46", text)

    def test_capability_map_groups_by_first_real_folder(self):
        contract = compile_requirement_contract(tree(
            {"id": "CAP-A", "type": "FOLDER", "children": [node("A-1", "a", []), node("A-2", "a", [])]},
            {"id": "CAP-B", "type": "FOLDER", "children": [node("B-1", "b", [])]},
        ))
        self.assertEqual({item["id"] for item in contract["capabilities"]}, {"CAP-A", "CAP-B"})


if __name__ == "__main__":
    unittest.main()
