import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "campaign.py"
spec = importlib.util.spec_from_file_location("arc_optimizer_campaign", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.campaign = json.loads((MODULE.parent / "campaign.example.json").read_text(encoding="utf-8"))

    def test_campaign_has_ordered_task_graph_and_isolated_namespaces(self):
        value = mod.validate_campaign(self.campaign)
        self.assertEqual([item["stage"] for item in value["tasks"]], ["E2", "E3", "E4", "E5", "E6"])
        self.assertEqual(mod.eligible_stages(value, {}), ["E2"])
        self.assertNotEqual(
            mod.task_state_dir("D:/state", "hackathon--sheet"),
            mod.task_state_dir("D:/state", "hackathon--github-stage-1"),
        )

    def test_campaign_rejects_duplicate_task_or_wrong_dependency(self):
        duplicate = copy.deepcopy(self.campaign)
        duplicate["tasks"].append(copy.deepcopy(duplicate["tasks"][0]))
        with self.assertRaises(mod.CampaignError):
            mod.validate_campaign(duplicate)
        wrong = copy.deepcopy(self.campaign)
        wrong["tasks"][1]["depends_on"] = ["E4"]
        with self.assertRaises(mod.CampaignError):
            mod.validate_campaign(wrong)

    def test_campaign_identity_is_task_specific(self):
        tasks = mod.task_map(self.campaign)
        sheet = mod.task_identity(tasks["hackathon--sheet"], run_id="r1")
        stage1 = mod.task_identity(tasks["hackathon--github-stage-1"], run_id="r1")
        self.assertNotEqual(sheet["requirements_sha256"], stage1["requirements_sha256"])
        self.assertNotEqual(sheet["identity_sha256"], stage1["identity_sha256"])

    def test_campaign_requires_explicit_suite_unavailable_provenance(self):
        broken = copy.deepcopy(self.campaign)
        broken["tasks"][0]["suite_provenance"] = "unknown"
        with self.assertRaises(mod.CampaignError):
            mod.validate_campaign(broken)

    def test_budget_summary_reports_insufficient_plan_when_estimates_are_known(self):
        campaign = copy.deepcopy(self.campaign)
        campaign["budget_cny"] = 300
        for item in campaign["tasks"]:
            item["estimated_run_cny"] = 90
        summary = mod.budget_summary(campaign)
        self.assertEqual(summary["planned_estimate_cny"], 450)
        self.assertFalse(summary["sufficient_for_plan"])

    def test_budget_decision_preserves_reserve_and_stops_after_two_runs(self):
        decision = mod.budget_decision(self.campaign, spent_cny=90, estimate_cny=90)
        self.assertTrue(decision["allowed"])
        blocked = mod.budget_decision(self.campaign, spent_cny=225, estimate_cny=90)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["remaining_spendable_cny"], 0)

    def test_campaign_status_uses_task_namespaces_and_dependencies(self):
        with tempfile.TemporaryDirectory() as root:
            task_dir = mod.task_state_dir(root, "hackathon--sheet")
            task_dir.mkdir(parents=True)
            (task_dir / "controller.json").write_text(json.dumps({
                "phase": "round_complete", "round": 1, "spent_cny": 90,
                "last_run": "sheet-run"
            }), encoding="utf-8")
            status = mod.campaign_status(self.campaign, root)
            self.assertEqual(status["eligible_stages"], ["E3"])
            sheet = next(item for item in status["tasks"] if item["stage"] == "E2")
            self.assertEqual(sheet["status"], "completed")
            self.assertEqual(sheet["state_dir"], str(task_dir))


if __name__ == "__main__":
    unittest.main()
