"""Task-aware campaign planning for ARC optimizer runs.

This module is intentionally side-effect free. It validates a campaign registry,
computes task-isolated state paths and budget summaries, and decides which stage
is eligible to start. Remote runs and code generation remain in controller.py.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

STAGES = (
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
)
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_TASK_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")


class CampaignError(ValueError):
    """Raised when a campaign registry is unsafe or internally inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CampaignError(message)


def _sha(value: object, label: str) -> str:
    text = str(value or "")
    _require(bool(_SHA256.fullmatch(text)), f"{label} must be a 64-character SHA-256")
    return text.lower()


def _task_key(value: object) -> str:
    text = str(value or "")
    _require(bool(_TASK_KEY.fullmatch(text)), "task_key is invalid")
    return text


def probe_policy(task: dict) -> dict:
    """Normalize the short-probe gate for one task without touching external state."""
    raw = task.get("short_probe") or {}
    _require(isinstance(raw, dict), f"short_probe must be an object for {task.get('task_key')}")
    minimum_score = raw.get("minimum_score", 1)
    max_attempts = raw.get("max_attempts", 2)
    statuses = raw.get("accepted_statuses", ["PASSED"])
    _require(isinstance(minimum_score, (int, float)) and not isinstance(minimum_score, bool)
             and minimum_score >= 0, "short_probe.minimum_score must be non-negative")
    _require(isinstance(max_attempts, int) and not isinstance(max_attempts, bool) and max_attempts >= 1,
             "short_probe.max_attempts must be a positive integer")
    _require(isinstance(statuses, list) and statuses and all(isinstance(item, str) for item in statuses),
             "short_probe.accepted_statuses must be a non-empty list")
    return {"enabled": bool(raw.get("enabled", True)), "minimum_score": minimum_score,
            "max_attempts": max_attempts,
            "accepted_statuses": [item.upper() for item in statuses]}


def evaluate_probe(task: dict, result: dict, attempt: int) -> dict:
    """Evaluate a task's short probe; missing facts fail closed."""
    policy = probe_policy(task)
    status = str(result.get("status") or "").upper()
    score = result.get("score")
    score_ok = isinstance(score, (int, float)) and not isinstance(score, bool) and score >= policy["minimum_score"]
    passed = (not policy["enabled"]) or (status in policy["accepted_statuses"] and score_ok)
    retryable = not passed and attempt < policy["max_attempts"]
    return {"enabled": policy["enabled"], "passed": passed, "retryable": retryable,
            "attempt": attempt, "max_attempts": policy["max_attempts"],
            "status": status or None, "score": score, "minimum_score": policy["minimum_score"],
            "accepted_statuses": policy["accepted_statuses"],
            "reason": None if passed else "short probe did not meet status and score gate"}


def validate_campaign(campaign: dict) -> dict:
    """Validate and normalize a campaign registry without touching the network."""
    _require(isinstance(campaign, dict), "campaign must be a JSON object")
    _require(campaign.get("schema_version") == 1, "campaign schema_version must be 1")
    campaign_id = str(campaign.get("campaign_id") or "").strip()
    _require(bool(campaign_id), "campaign_id is required")
    tasks = campaign.get("tasks")
    _require(isinstance(tasks, list) and tasks, "campaign tasks must be a non-empty list")
    max_remote = campaign.get("max_parallel_remote_runs", 1)
    max_collect = campaign.get("max_parallel_readonly_collect", 2)
    max_codegen = campaign.get("max_parallel_codegen", 1)
    for value, label in ((max_remote, "max_parallel_remote_runs"),
                         (max_collect, "max_parallel_readonly_collect"),
                         (max_codegen, "max_parallel_codegen")):
        _require(isinstance(value, int) and not isinstance(value, bool) and value >= 1,
                 f"{label} must be a positive integer")
    _require(max_codegen == 1, "max_parallel_codegen must remain 1")
    _require(max_remote <= 2, "max_parallel_remote_runs may not exceed 2")

    seen: set[str] = set()
    normalized = []
    for raw in tasks:
        _require(isinstance(raw, dict), "each campaign task must be an object")
        task_key = _task_key(raw.get("task_key"))
        _require(task_key not in seen, f"duplicate task_key: {task_key}")
        seen.add(task_key)
        stage = str(raw.get("stage") or "")
        _require(stage in STAGES, f"unsupported stage for {task_key}: {stage}")
        competition = str(raw.get("competition") or "").strip()
        _require(bool(competition), f"competition is required for {task_key}")
        req = _sha(raw.get("requirements_sha256"), f"requirements_sha256 for {task_key}")
        archive = raw.get("requirements_archive_sha256")
        if archive is not None:
            archive = _sha(archive, f"requirements_archive_sha256 for {task_key}")
        mode = str(raw.get("identity_mode") or "task_requirements_only")
        _require(mode in {"suite_required", "task_requirements_only"},
                 f"invalid identity_mode for {task_key}")
        if mode == "task_requirements_only":
            _require(not raw.get("suite_key"), f"task_requirements_only must not set suite_key for {task_key}")
            provenance = str(raw.get("suite_provenance") or "")
            _require("not provide" in provenance.lower() or "不提供" in provenance or "未提供" in provenance,
                     f"suite-unavailable provenance required for {task_key}")
        else:
            _require(bool(raw.get("suite_key")) and bool(raw.get("suite_provenance")),
                     f"suite_key and suite_provenance required for {task_key}")
        depends = list(raw.get("depends_on") or [])
        _require(all(isinstance(item, str) and item in STAGES for item in depends),
                 f"depends_on contains an invalid stage for {task_key}")
        _require(stage != "E2" or not depends, "E2 cannot depend on a later stage")
        normalized.append({**raw, "task_key": task_key, "stage": stage,
                          "competition": competition, "requirements_sha256": req,
                          "requirements_archive_sha256": archive,
                          "identity_mode": mode, "depends_on": depends,
                          "short_probe": probe_policy({**raw, "task_key": task_key})})

    stage_map = {item["stage"]: item for item in normalized}
    for item in normalized:
        for dependency in item["depends_on"]:
            _require(dependency in stage_map, f"missing dependency {dependency} for {item['task_key']}")
            _require(STAGES.index(dependency) < STAGES.index(item["stage"]),
                     f"dependency {dependency} must precede {item['stage']}")
    return {**campaign, "campaign_id": campaign_id, "tasks": normalized,
            "max_parallel_remote_runs": max_remote,
            "max_parallel_readonly_collect": max_collect,
            "max_parallel_codegen": max_codegen}


def load_campaign(path: str | Path) -> dict:
    path = Path(path).resolve()
    _require(path.is_file(), f"campaign file is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise CampaignError(f"campaign JSON is invalid: {path}") from exc
    return validate_campaign(value)


def task_map(campaign: dict) -> dict[str, dict]:
    validated = validate_campaign(campaign)
    return {item["task_key"]: item for item in validated["tasks"]}


def task_state_dir(state_root: str | Path, task_key: str) -> Path:
    task_key = _task_key(task_key)
    return Path(state_root).resolve() / "tasks" / task_key


def task_identity(task: dict, *, run_id: str | None = None,
                  submission_id: str | None = None, commit_sha: str | None = None,
                  package_sha256: str | None = None, cli_revision: str | None = None) -> dict:
    """Return the minimum identity tuple used to compare one task's runs."""
    result = {
        "competition": task["competition"],
        "task_key": task["task_key"],
        "requirements_sha256": task["requirements_sha256"],
        "requirements_archive_sha256": task.get("requirements_archive_sha256"),
        "identity_mode": task["identity_mode"],
        "suite_key": task.get("suite_key"),
        "suite_provenance": task.get("suite_provenance"),
        "run_id": run_id,
        "submission_id": submission_id,
        "commit_sha": commit_sha,
        "package_sha256": package_sha256,
        "cli_revision": cli_revision,
    }
    result["identity_sha256"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result


def budget_summary(campaign: dict) -> dict:
    validated = validate_campaign(campaign)
    total = validated.get("budget_cny")
    reserve = validated.get("reserve_fraction", 0.25)
    estimates = [item.get("estimated_run_cny") for item in validated["tasks"]]
    numeric = [value for value in estimates if isinstance(value, (int, float)) and not isinstance(value, bool)]
    planned = sum(numeric)
    spendable = total * (1 - reserve) if isinstance(total, (int, float)) else None
    return {"total_budget_cny": total, "reserve_fraction": reserve,
            "planned_estimate_cny": planned, "spendable_budget_cny": spendable,
            "sufficient_for_plan": spendable is not None and planned <= spendable}


def budget_decision(campaign: dict, spent_cny: float, estimate_cny: float) -> dict:
    """Return a conservative cross-task budget decision without mutating state."""
    summary = budget_summary(campaign)
    total = summary["total_budget_cny"]
    reserve = summary["reserve_fraction"]
    if not isinstance(total, (int, float)) or isinstance(total, bool) or total <= 0:
        return {"allowed": False, "reason": "campaign budget is missing or non-positive"}
    if not isinstance(spent_cny, (int, float)) or isinstance(spent_cny, bool) or spent_cny < 0:
        return {"allowed": False, "reason": "campaign spent_cny is invalid"}
    if not isinstance(estimate_cny, (int, float)) or isinstance(estimate_cny, bool) or estimate_cny <= 0:
        return {"allowed": False, "reason": "estimated run cost is missing or non-positive"}
    spendable = total * (1 - reserve)
    remaining = spendable - spent_cny
    allowed = spent_cny + estimate_cny <= spendable
    return {"allowed": allowed,
            "reason": None if allowed else "campaign spending allowance exhausted",
            "total_budget_cny": total, "reserve_fraction": reserve,
            "spendable_budget_cny": spendable, "spent_cny": spent_cny,
            "remaining_spendable_cny": remaining, "next_estimate_cny": estimate_cny}


def campaign_status(campaign: dict, state_root: str | Path) -> dict:
    """Read task journals and derive scheduler-visible status without side effects."""
    validated = validate_campaign(campaign)
    root = Path(state_root).resolve()
    statuses = {}
    tasks = []
    for task in validated["tasks"]:
        journal = task_state_dir(root, task["task_key"]) / "controller.json"
        state = {}
        if journal.is_file():
            try:
                state = json.loads(journal.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                state = {"phase": "corrupt"}
        phase = str(state.get("phase") or "planned")
        stage_status = state.get("stage_status")
        if (stage_status == "eligible_for_next_stage" or phase == "stage_complete"
                or (phase == "round_complete" and not stage_status)):
            status = "completed"
        elif stage_status == "probe_failed":
            status = "probe_failed"
        elif phase in {"stopped", "corrupt"}:
            status = "blocked"
        elif phase == "ready":
            status = "ready"
        else:
            status = "running" if journal.is_file() else "planned"
        statuses[task["stage"]] = status
        probe = state.get("probe") or {}
        tasks.append({"stage": task["stage"], "task_key": task["task_key"],
                      "status": status, "phase": phase,
                      "round": state.get("round", 0), "spent_cny": state.get("spent_cny", 0),
                      "last_run": state.get("last_run"), "state_dir": str(journal.parent),
                      "probe": probe, "retryable": status == "probe_failed" and bool(probe.get("retryable"))})
    eligible = eligible_stages(validated, statuses)
    ledger_path = root / "campaigns" / validated["campaign_id"] / "budget.json"
    ledger = {"spent_cny": 0, "entries": [], "present": False}
    if ledger_path.is_file():
        try:
            value = json.loads(ledger_path.read_text(encoding="utf-8-sig"))
            if value.get("campaign_id") == validated["campaign_id"]:
                ledger = {"spent_cny": value.get("spent_cny", 0),
                          "entries": value.get("entries", []), "present": True}
        except (OSError, json.JSONDecodeError):
            ledger = {"spent_cny": None, "entries": [], "present": True, "error": "unreadable"}
    budget = budget_summary(validated)
    decision = budget_decision(validated, ledger["spent_cny"],
                               next((item.get("estimated_run_cny") for item in validated["tasks"]
                                     if item["stage"] in eligible), 0))
    budget.update({"ledger": ledger, "next_stage_decision": decision})
    return {"campaign_id": validated["campaign_id"], "tasks": tasks,
            "eligible_stages": eligible, "budget": budget}


def eligible_stages(campaign: dict, statuses: dict[str, str]) -> list[str]:
    """Return stages whose declared predecessors are completed successfully."""
    validated = validate_campaign(campaign)
    result = []
    for task in validated["tasks"]:
        if all(statuses.get(dep) in {"eligible_for_next_stage", "completed"}
               for dep in task["depends_on"]):
            current = statuses.get(task["task_key"], statuses.get(task["stage"], "planned"))
            if current in {"planned", "ready", "probe_failed"}:
                result.append(task["stage"])
    return result


def task_config(base_config: dict, task: dict) -> dict:
    """Project one campaign task into a Controller config without mutating the base."""
    result = dict(base_config)
    result.update({
        "competition": task["competition"],
        "task": task["task_key"],
        "task_requirements_sha256": task["requirements_sha256"],
        "platform_identity_mode": task["identity_mode"],
        "suite_key": task.get("suite_key"),
        "suite_provenance": task.get("suite_provenance"),
        "estimated_run_cny": task.get("estimated_run_cny", base_config.get("estimated_run_cny")),
    })
    return result


def validate_task_requirements_binding(config: dict, task: dict) -> None:
    """Reject a single-task config that does not match its campaign registry."""
    _require(config.get("competition") == task["competition"], "competition does not match campaign task")
    _require(config.get("task") == task["task_key"], "task does not match campaign task")
    configured_task_sha = config.get("task_requirements_sha256") or config.get("requirements_sha256")
    _require(str(configured_task_sha or "").lower() == task["requirements_sha256"],
             "task requirements SHA does not match campaign task")
    _require(config.get("platform_identity_mode", "suite_required") == task["identity_mode"],
             "identity mode does not match campaign task")
