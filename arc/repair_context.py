"""Structured evidence passed from acceptance runs into repair turns."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


DOMAIN_PROFILES = {
    "github": {
        "business_flow": "session_to_repository_permission_and_pull_request_workflow",
        "state_owner": ["session_store", "organization_store", "repository_store", "branch_store",
                         "issue_store", "pull_request_store", "review_store"],
        "read_path": ["account", "organization", "repository", "branch", "issue", "pull_request", "review"],
        "write_path": ["auth_handler", "repository_handler", "issue_handler", "pull_request_handler",
                       "review_handler", "merge_handler"],
        "persistence_path": ["server_store", "reload", "direct_resource_url"],
        "permission_boundary": ["current_session", "organization_role", "repository_role", "resource_owner"],
        "derived_state": ["visible_resources", "effective_permission", "compare_commit", "merge_eligibility",
                          "review_status", "branch_protection"],
        "workflow_transition": "draft_or_open -> reviewed_or_merged",
        "invariants_to_preserve": [
            "unauthorized_write_is_rejected",
            "review_targets_the_current_compare_commit",
            "failed_merge_keeps_pull_request_and_target_branch_unchanged",
            "list_and_detail_use_the_same_persisted_resource",
        ],
    },
    "sheet": {
        "business_flow": "workbook_worksheet_cell_edit_and_derived_state_workflow",
        "state_owner": ["workbook_store", "worksheet_store", "cell_store", "formula_store",
                        "filter_store", "validation_store", "pivot_store"],
        "read_path": ["workbook_home", "worksheet_tabs", "grid", "formula_bar", "filter_view", "pivot_view"],
        "write_path": ["workbook_handler", "cell_commit", "paste_handler", "row_column_handler",
                       "filter_handler", "validation_handler", "pivot_handler"],
        "persistence_path": ["server_store", "refresh", "reopen", "direct_workbook_url"],
        "permission_boundary": ["active_workbook", "active_worksheet", "selected_range"],
        "derived_state": ["formula_results", "dependency_graph", "validation_state", "filter_result",
                          "pivot_result"],
        "workflow_transition": "source_cell_change -> dependent_recalculation_and_persistence",
        "invariants_to_preserve": [
            "formula_bar_keeps_the_original_formula",
            "grid_shows_the_current_calculated_result",
            "failed_batch_operation_keeps_the_last_successful_state",
            "unrelated_cells_and_worksheets_are_unchanged",
            "refresh_reopens_the_same_workbook_state",
        ],
    },
}


def infer_product_domain(text: str) -> str:
    """Infer only the two known real-task domains; avoid guessing for generic tasks."""
    value = (text or "").lower()
    github_score = sum(value.count(term) for term in (
        "github", "repository", "pull request", "branch protection", "organization", "merge",
    ))
    sheet_score = sum(value.count(term) for term in (
        "workbook", "worksheet", "spreadsheet", "formula", "pivot", "gridcell", "cell",
    ))
    if github_score >= 2 and github_score > sheet_score:
        return "github"
    if sheet_score >= 2 and sheet_score > github_score:
        return "sheet"
    return "generic"


def infer_failure_reason(text: str, domain: str = "generic") -> str:
    """Map common cross-layer evidence to a repair order without overclaiming."""
    value = (text or "").lower()
    if any(term in value for term in ("permission", "unauthorized", "forbidden", "not allowed", "access")):
        return "permission_boundary_mismatch"
    if any(term in value for term in ("refresh", "reopen", "persist", "after reload", "direct url")):
        return "state_persistence_mismatch"
    if domain == "github" and any(term in value for term in ("merge", "review", "branch protection", "compare commit")):
        return "workflow_transition_invalid"
    if domain == "sheet" and any(term in value for term in ("formula", "recalculate", "dependency", "pivot", "derived")):
        return "formula_dependency_stale"
    if any(term in value for term in ("validation", "invalid input", "paste")):
        return "validation_bypass"
    if any(term in value for term in ("aria-", "accessible name", "role=", "gridcell", "tab")):
        return "accessibility_contract_mismatch"
    return ""


def domain_context(text: str, failure_text: str = "") -> dict:
    """Return a compact, prompt-ready domain contract for a repair turn."""
    domain = infer_product_domain(text)
    profile = DOMAIN_PROFILES.get(domain)
    if not profile:
        return {
            "product_domain": "generic",
            "business_flow": "unknown",
            "state_owner": [],
            "read_path": [],
            "write_path": [],
            "persistence_path": [],
            "permission_boundary": [],
            "derived_state": [],
            "workflow_transition": "",
            "invariants_to_preserve": [],
            "failure_reason_hint": infer_failure_reason(failure_text, domain),
        }
    return {
        "product_domain": domain,
        **profile,
        "failure_reason_hint": infer_failure_reason(failure_text, domain),
    }


@dataclass
class RepairContext:
    node_id: str
    repair_round: int
    failure_kind: str
    failure_reason: str = ""
    current_failures: list[str] = field(default_factory=list)
    best_failures: list[str] = field(default_factory=list)
    fixed_failures: list[str] = field(default_factory=list)
    new_failures: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    missing_checks: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    likely_files: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    no_progress_count: int = 0
    product_domain: str = "generic"
    business_flow: str = "unknown"
    state_owner: list[str] = field(default_factory=list)
    read_path: list[str] = field(default_factory=list)
    write_path: list[str] = field(default_factory=list)
    persistence_path: list[str] = field(default_factory=list)
    permission_boundary: list[str] = field(default_factory=list)
    derived_state: list[str] = field(default_factory=list)
    workflow_transition: str = ""
    invariants_to_preserve: list[str] = field(default_factory=list)
    files_to_change: list[str] = field(default_factory=list)
    seed_entities: list[str] = field(default_factory=list)
    session_context: list[str] = field(default_factory=list)
    failure_reason_hint: str = ""

    def as_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "repair_round": self.repair_round,
            "failure_kind": self.failure_kind,
            "failure_reason": self.failure_reason,
            "current_failures": self.current_failures,
            "best_failures": self.best_failures,
            "fixed_failures": self.fixed_failures,
            "new_failures": self.new_failures,
            "known_failures": self.known_failures,
            "missing_checks": self.missing_checks,
            "changed_files": self.changed_files,
            "likely_files": self.likely_files,
            "evidence": self.evidence,
            "no_progress_count": self.no_progress_count,
            "product_domain": self.product_domain,
            "business_flow": self.business_flow,
            "state_owner": self.state_owner,
            "read_path": self.read_path,
            "write_path": self.write_path,
            "persistence_path": self.persistence_path,
            "permission_boundary": self.permission_boundary,
            "derived_state": self.derived_state,
            "workflow_transition": self.workflow_transition,
            "invariants_to_preserve": self.invariants_to_preserve,
            "files_to_change": self.files_to_change,
            "seed_entities": self.seed_entities,
            "session_context": self.session_context,
            "failure_reason_hint": self.failure_reason_hint,
        }

    def prompt_text(self) -> str:
        """Compact, deterministic context; keep repair prompts readable."""
        payload = json.dumps(self.as_dict(), ensure_ascii=False, indent=2)
        return (
            "STRUCTURED REPAIR CONTEXT (acceptance evidence is authoritative; "
            "do not claim success from the model response alone):\n"
            "```json\n" + payload[:12000] + "\n```\n"
            "Repair rules: inspect the likely files first, preserve passing behavior, "
            "and stop repeating the same approach when no_progress_count is non-zero.\n"
            "For a non-generic product domain, trace the failure through state_owner -> write_path "
            "-> persistence_path -> read_path before changing presentation code. Preserve every "
            "listed invariant and do not invent domain rules for generic tasks.\n"
        )
