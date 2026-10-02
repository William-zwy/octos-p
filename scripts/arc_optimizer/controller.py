"""Serialized Codex -> Git/CI -> ARC cloud -> evidence loop (no local tasks).

All private payloads and the durable journal stay outside the repository.
An attempted upload/run is NEVER automatically repeated after uncertainty.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "arc"))
from run_controls import atomic_json_write

TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED", "CANCELED", "TIMEOUT", "PAUSED"}
PLAN = "HKT/ARC_BENCH_ROUND345_FINAL_PLAN_20260930.md"
LOG = "HKT/CHANGELOG_20260924.md"
REGISTER = "HKT/ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md"
PROJECT_LOG = "CHANGELOG.md"
COORDINATION = "evidence/arc-bench/phase5-coordination.json"
CLI_REVISION = "15b0b27da4a4a0d412c79cbfaa318c59da5c3689"
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
_FORBIDDEN_CODEX_ENV_MARKERS = ("ARC", "COOKIE", "PASSWORD", "SECRET", "TOKEN")


class GateError(RuntimeError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_date(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise GateError("deadline must include timezone")
    return parsed


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(value)):
        raise GateError("invalid run/submission identifier")
    return str(value)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _codex_env_names(config):
    requested = config.get("codex_env_allowlist", [])
    if requested is None:
        requested = []
    if not isinstance(requested, list):
        raise GateError("codex_env_allowlist must be a list of environment variable names")
    names = []
    for name in requested:
        if not isinstance(name, str) or not _ENV_NAME.fullmatch(name):
            raise GateError("codex_env_allowlist contains an invalid environment variable name")
        if any(marker in name.upper() for marker in _FORBIDDEN_CODEX_ENV_MARKERS):
            raise GateError("codex_env_allowlist contains a forbidden platform/session variable")
        if name not in names:
            names.append(name)
    return names


def codex_auth_mode(config):
    mode = str(config.get("codex_auth_mode", "login")).lower()
    if mode not in {"login", "provider"}:
        raise GateError("codex_auth_mode must be 'login' or 'provider'")
    return mode


def codex_worker_environment(config, source=None):
    """Build the worker environment without leaking platform credentials.

    The inherited environment deliberately excludes every API-key-like name.
    A private config may opt in to one or more provider key variables, but
    platform/session/token channels are rejected and missing values stop before
    starting Codex.
    """
    source = dict(os.environ if source is None else source)
    inherited = {
        key: value for key, value in source.items()
        if not any(marker in key.upper() for marker in ("ARC", "COOKIE", "TOKEN", "PASSWORD", "SECRET", "API_KEY"))
    }
    names = _codex_env_names(config)
    missing = [name for name in names if not source.get(name)]
    if missing:
        raise GateError("configured Codex environment variables are not set: " + ", ".join(missing))
    inherited.update({name: source[name] for name in names})
    return inherited


def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_sha256(value):
    """Hash a JSON value deterministically for authorization binding."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


def _hash_json_file(path):
    path = Path(path)
    if not path.is_file():
        raise GateError("required JSON artifact is missing: " + path.name)
    return sha256(path)


def _safe_relative_paths(paths):
    result = []
    for value in paths or []:
        path = Path(str(value)).as_posix()
        if path.startswith("../") or path == ".." or path.startswith("/"):
            raise GateError("worker returned a path outside the repository")
        result.append(path)
    return sorted(set(result))


def _forbidden_codegen_path(path):
    path = Path(path).as_posix().lower()
    components = set(path.split("/"))
    return (
        "harness" in components or
        "official-tests" in components or
        "public-tests" in components or
        path.startswith("tests/") or
        "/tests/" in path or
        path.startswith("requirements") or
        path.endswith(".zip") or
        path.endswith(".yaml") and "requirement" in path
    )


def validate_codegen_skills(records):
    """Permit the required Git safety instructions, without granting actions."""
    if not isinstance(records, list):
        raise GateError("worker skill_invocations must be a list")
    for record in records:
        if not isinstance(record, dict) or record.get("status") not in {"used", "not_used"}:
            raise GateError("invalid worker Skill record")
        if record["status"] == "used" and record.get("skill") != "reliable-git-sync":
            raise GateError("worker invoked an unauthorized Skill")


def _monitor_file_candidates(state_root, run_id):
    root = Path(state_root) / "runs" / str(run_id)
    return root / "monitor-doc.json", root / "monitor-runtime.json"


def reconcile_monitor_inputs(state_root, run_id):
    """Combine externally supplied monitor reports without starting subprocesses."""
    reports = []
    missing = []
    for path in _monitor_file_candidates(state_root, run_id):
        if not path.is_file():
            missing.append(path.name)
            continue
        try:
            report = read_json(path)
        except (OSError, ValueError) as exc:
            raise GateError("invalid monitor report: " + path.name) from exc
        if not isinstance(report, dict):
            raise GateError("monitor report must be an object: " + path.name)
        reports.append({"path": str(path), "sha256": sha256(path), "report": report})
    decisions = {str(item["report"].get("decision", "NEEDS-EVIDENCE")).upper()
                 for item in reports}
    if missing or len(reports) < 2 or len(decisions) != 1:
        decision = "NEEDS-EVIDENCE"
    else:
        decision = next(iter(decisions))
        if decision not in {"GO", "NO-GO", "NEEDS-EVIDENCE"}:
            decision = "NEEDS-EVIDENCE"
    return {
        "schema_version": 1,
        "run_id": str(run_id),
        "decision": decision,
        "reports": reports,
        "missing": missing,
        "conflict": len(decisions) > 1,
        "source": "external monitor reports; no monitor subprocess was started",
        "created_at": utcnow(),
    }


def _local_files(root):
    root = Path(root)
    if not root.exists():
        return []
    return [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
             "sha256": sha256(path)} for path in sorted(root.rglob("*")) if path.is_file()]


def _run_file_records(root):
    root = Path(root)
    return [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
             "sha256": sha256(path)} for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "summary.json"]


def _read_optional_json(path):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _zip_inventory(path):
    path = Path(path)
    result = {"present": path.is_file(), "path": str(path), "bytes": None,
              "sha256": None, "entry_count": None, "agent_build": None,
              "binding_present": False, "traceability_entries": [], "screenshot_entries": [],
              "requirements_entries": []}
    if not path.is_file():
        return result
    result.update(bytes=path.stat().st_size, sha256=sha256(path))
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result["entry_count"] = len(names)
            result["binding_present"] = any(name.endswith("binding.json") for name in names)
            result["traceability_entries"] = [name for name in names if "trace" in name.lower()][:40]
            result["screenshot_entries"] = [name for name in names if "screenshot" in name.lower()][:40]
            result["requirements_entries"] = [name for name in names if "requirements" in name.lower()][:40]
            for name in names:
                if name.endswith("agent-build.json"):
                    try:
                        result["agent_build"] = json.loads(archive.read(name))
                    except (UnicodeDecodeError, ValueError):
                        result["agent_build_error"] = "invalid_json"
                    break
            for name in names:
                if name.endswith("requirements.yaml"):
                    result["local_requirements_yaml_sha256"] = _sha256_bytes(archive.read(name))
                    break
    except (OSError, zipfile.BadZipFile) as exc:
        result["archive_error"] = type(exc).__name__
    return result


def _canonical_log_lines(root):
    """Read full saved payloads once and de-duplicate stdout/stderr mirrors."""
    lines = []
    seen = set()
    for path in sorted(Path(root).glob("log-pages/*/*-logs.json")):
        payload = _read_optional_json(path) or {}
        for key in ("stdout", "stderr", "console"):
            value = payload.get(key, "")
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            for line in value.splitlines():
                canonical = re.sub(r"\[generation-agent\.(?:stdout|stderr)\]", "[generation-agent]", line)
                canonical = re.sub(r"\[runner\.(?:stdout|stderr)\]", "[runner]", canonical)
                if canonical not in seen:
                    seen.add(canonical)
                    lines.append(canonical)
    return lines


def _log_forensics(root, status):
    lines = _canonical_log_lines(root)
    text = "\n".join(lines)
    implement = {}
    pattern = re.compile(
        r"\[flow\]\s+(REQ-[A-Za-z0-9._-]+)\s+implement ok in\s+(\d+)s.*?wrote=(True|False).*?verified=(True|False)", re.I
    )
    for match in pattern.finditer(text):
        implement[match.group(1)] = {"seconds": int(match.group(2)),
                                     "wrote": match.group(3).lower() == "true",
                                     "verified": match.group(4).lower() == "true"}
    node_matches = re.findall(r"\[flow\]\s+node\s+(\d+)/(\d+)\s+(REQ-[A-Za-z0-9._-]+)\s+starting", text, re.I)
    node_states = Counter(str(value) for value in (status.get("node_states") or {}).values())
    def count(pattern):
        return len(re.findall(pattern, text, re.I))
    test_ids = sorted(set(re.findall(r"\bREQ-[A-Za-z0-9._-]+\b", "\n".join(
        line for line in lines if re.search(r"test|failed|timeout|timed.?out", line, re.I)))) )
    return {
        "canonical_log_line_count": len(lines),
        "node_events": len(node_matches),
        "node_total_observed": max((int(item[1]) for item in node_matches), default=None),
        "implement_ok_events": len(implement),
        "implement_wrote_true": sum(item["wrote"] for item in implement.values()),
        "implement_verified_true": sum(item["verified"] for item in implement.values()),
        "implement_verified_false": sum(not item["verified"] for item in implement.values()),
        "implement_events": implement,
        "node_state_counts": dict(node_states),
        "request_budget_hits": count(r"request budget|budget cap|\bcap[_ ]\d+"),
        "turn_timeout_count": count(r"turn\s+(?:timed.?out|timeout)"),
        "broken_pipe_count": count(r"BrokenPipe"),
        "connection_reset_count": count(r"ConnectionResetError"),
        "http_402_count": count(r"(?:HTTP|status|code)\s*402|\b402\b"),
        "http_429_count": count(r"(?:HTTP|status|code)\s*429|\b429\b"),
        "http_500_count": count(r"(?:HTTP|status|code)\s*500|\b500\b"),
        # Do not count statements such as "no OOM" or "OOM events: 0" as failures.
        "oom_count": count(r"out of memory|oom[_ -]?(?:kill|killed|error|failure)(?!\s*0\b)|killed[^\n]{0,60}\boom\b"),
        "rehearsal_mentions": count(r"rehearsal"),
        "repair_mentions": count(r"repair"),
        "backend_listening": bool(re.search(r"(?:listening|started).*?(?:localhost|127\.0\.0\.1|:3000)", text, re.I)),
        "main_exit_codes": [int(value) for value in re.findall(r"(?:main\.py|main).*?exit(?:ed)?(?: with)?\s*(?:code\s*)?[:=]?\s*(\d+)", text, re.I)],
        "official_acceptance_unavailable": bool(re.search(r"official acceptance suite unavailable", text, re.I)),
        "playwright_mentions": count(r"playwright"),
        "report_404_mentions": count(r"report[^\n]{0,40}\b404\b|\b404\b[^\n]{0,40}report"),
        "failure_test_ids_observed": test_ids,
        "test_details_from_platform": bool(status.get("tests")),
    }


def build_forensics(status, cursor, files, candidate, state_root, repo_root):
    state_root = Path(state_root)
    repo_root = Path(repo_root)
    run_id = str(status.get("id"))
    manifest_path = repo_root / "evidence" / "arc-bench" / "runs" / run_id / "manifest.json"
    manifest = _read_optional_json(manifest_path)
    archive = _zip_inventory(state_root / "submission.zip")
    workspace = _zip_inventory(state_root / "workspace.zip")
    source_identity = (archive.get("agent_build") or {}).get("commit_sha")
    platform_source = status.get("agent_commit") or status.get("source_commit") or status.get("generation_identity")
    runtime_identity = (manifest or {}).get("submission", {}).get("runtime_reported_identity", {}) if manifest else {}
    suite = (manifest or {}).get("verification_regime", {}) if manifest else {}
    metrics = (manifest or {}).get("metrics", {}) if manifest else {}
    usage = (manifest or {}).get("usage", {}) if manifest else {}
    log_data = _log_forensics(state_root, status)
    declared = (manifest or {}).get("evidence", []) if manifest else []
    error_counts = {key: log_data[key] for key in ("request_budget_hits", "turn_timeout_count", "broken_pipe_count",
                                                    "connection_reset_count", "http_402_count", "http_429_count",
                                                    "http_500_count", "oom_count")}
    declared_errors = {
        "turn_timeout_count": metrics.get("agent_turn_timeouts"),
        "broken_pipe_count": metrics.get("local_proxy_broken_pipe_events"),
        "oom_count": metrics.get("oom_events"),
    }
    for key, value in declared_errors.items():
        if numeric(value):
            error_counts[key] = value
    return {
        "run": {
            "run_id": run_id, "url": f"https://arc-bench.com/runs/{run_id}",
            "competition": status.get("competition_id"), "task_key": status.get("requirement_id"),
            "status": str(status.get("status", "")).upper(), "score": status.get("score"),
            "passed": status.get("passed_count"), "total": (status.get("passed_count", 0) or 0) + (status.get("failed_count", 0) or 0),
            "feature_passed": status.get("feature_implemented_count"), "feature_total": status.get("feature_total_count"),
            "created_at": status.get("created_at"), "started_at": status.get("started_at"),
            "finished_at": status.get("finished_at"), "duration_seconds": status.get("run_duration_seconds"),
            "failure_reason": status.get("failure_reason"), "model": status.get("model_name"),
            "billing_mode": status.get("billing_mode"), "token_count": status.get("token_count"),
            "cost": {"amount": status.get("token_cost_usd"), "currency": status.get("token_cost_currency")},
        },
        "suite": {
            "suite_key": status.get("suite_key") or status.get("test_suite_key") or runtime_identity.get("suite_key"),
            "bundled_specs": suite.get("bundled_acceptance_specs"),
            "mode": suite.get("mode"), "platform_generated_scenarios": suite.get("platform_generated_scenarios"),
            "task_snapshot_id": status.get("task_snapshot_id"),
            "requirements_sha256_platform": status.get("requirements_sha256"),
            "requirements_sha256_local": suite.get("requirements_yaml_sha256") or archive.get("local_requirements_yaml_sha256"),
        },
        "submission": {
            "submission_id": status.get("submission_id"), "filename": status.get("original_filename"),
            "platform_archive_sha256": status.get("submission_sha256"),
            "downloaded_archive_sha256": archive.get("sha256"), "downloaded_archive_bytes": archive.get("bytes"),
            "build_id": (archive.get("agent_build") or {}).get("build_id"),
            "archive_agent_commit": source_identity, "platform_agent_commit": platform_source,
            "payload_tree_sha256": (archive.get("agent_build") or {}).get("payload_tree_sha256"),
            "binding_closed": bool(archive.get("binding_present") and platform_source and source_identity == platform_source),
            "binding_sidecar_present": archive.get("binding_present"),
            "runtime_reported_identity": runtime_identity or None,
        },
        "generation": {
            "status": "completed" if any(step.get("key") == "start_agent" and step.get("status") == "completed" for step in (status.get("steps") or []))
                      or log_data["node_events"] > 0 else "unknown",
            "node_states": log_data["node_state_counts"], "node_events": log_data["node_events"],
            "atomic_nodes": metrics.get("atomic_nodes") or log_data["node_total_observed"],
            "implement_ok": metrics.get("implement_ok_labels", log_data["implement_ok_events"]),
            "wrote_verified": metrics.get("node_wrote_verified", log_data["implement_wrote_true"]),
            "wrote_unverified": metrics.get("node_wrote_unverified", None),
            "verified_false": log_data["implement_verified_false"],
            "request_budget_hits": log_data["request_budget_hits"],
            "main_exit_codes": log_data["main_exit_codes"],
        },
        "deployment": {
            "status": "completed" if any(step.get("key") == "deploy_agent" and step.get("status") == "completed" for step in (status.get("steps") or []))
                      or log_data["backend_listening"] else "unknown",
            "backend_listening": log_data["backend_listening"], "rehearsal_mentions": log_data["rehearsal_mentions"],
            "repair_mentions": log_data["repair_mentions"], "repair": metrics.get("rehearsal"),
        },
        "evaluation": {
            "status": "completed" if any(step.get("key") == "run_tests" and step.get("status") == "completed" for step in (status.get("steps") or []))
                      or str(status.get("status", "")).upper() in TERMINAL else "unknown",
            "tests": status.get("tests") or None,
            "official_test_ids": [test.get("name") for test in (status.get("tests") or [])
                                  if isinstance(test, dict) and test.get("name")] or None,
            "log_observed_test_ids": log_data["failure_test_ids_observed"] or None,
            "details_available": bool(status.get("tests")), "official_acceptance_unavailable": log_data["official_acceptance_unavailable"],
            "playwright_mentions": log_data["playwright_mentions"], "report_404_mentions": log_data["report_404_mentions"],
        },
        "errors": error_counts,
        "raw_log_error_counts": {key: log_data[key] for key in error_counts},
        "usage": usage or None,
        "artifacts": {"state_folder": _local_files(state_root), "declared_local_artifacts": declared,
                      "repo_evidence_folder": _local_files(manifest_path.parent),
                      "workspace_archive": workspace,
                      "missing_platform_evidence": [name for name, present in (("per_test_details", bool(status.get("tests"))),
                                                                                ("result_path", bool(status.get("result_path"))),
                                                                                ("binding", archive.get("binding_present"))) if not present]},
        "external_evidence_index": _read_optional_json(state_root / "evidence-index.json"),
        "local_manifest": {"present": bool(manifest), "path": str(manifest_path),
                           "sha256": sha256(manifest_path) if manifest_path.is_file() else None,
                           "normalized_status": (manifest or {}).get("normalized_status"),
                           "phase4": (manifest or {}).get("phase4"),
                           "source_resolution": (manifest or {}).get("submission", {}).get("source_resolution") if manifest else None,
                           "traceability": (manifest or {}).get("traceability") if manifest else None,
                           "skill_runtime_evidence": (manifest or {}).get("skill_runtime_evidence") if manifest else None,
                           "cross_run_comparability": (manifest or {}).get("cross_run_comparability") if manifest else None,
                           "evidence_provenance": (manifest or {}).get("evidence_provenance") if manifest else None,
                           "missing_evidence": (manifest or {}).get("missing_evidence") if manifest else None},
        "log_analysis": log_data,
        "provenance": {"platform_status": "arcbench_cli status --full", "platform_logs": "arcbench_cli logs --out (full payloads)",
                        "archives": "arcbench_cli archive/download", "local_manifest": bool(manifest)},
    }


def _finding(code, severity, conclusion, evidence, action, confidence="high"):
    """Create a stable, reviewable finding for the implementation worker."""
    return {"code": code, "severity": severity, "conclusion": conclusion,
            "evidence": evidence, "action": action, "confidence": confidence}


def analyze_forensics(forensics, previous=None):
    """Turn collected facts into conservative implementation guidance.

    This layer is deliberately deterministic. It may recommend what to verify or
    change, but it never upgrades an internal label into an official result and
    never infers a hidden test outcome from a missing response.
    """
    run = forensics.get("run", {})
    suite = forensics.get("suite", {})
    submission = forensics.get("submission", {})
    generation = forensics.get("generation", {})
    deployment = forensics.get("deployment", {})
    evaluation = forensics.get("evaluation", {})
    errors = forensics.get("errors", {})
    artifacts = forensics.get("artifacts", {})
    findings = []
    actions = []

    if run.get("status") in TERMINAL and numeric(run.get("score")):
        findings.append(_finding(
            "official-result", "P0",
            f"官方结果为 {run.get('score')} 分；只能以平台 score/pass 作为结果，不以内部 verified 标签替代。",
            ["run.status", "run.score", "run.passed", "run.feature_passed"],
            "先保留失败事实，再针对一个可验证的垂直切片修改代码。"))
    feature_passed = run.get("feature_passed")
    feature_total = run.get("feature_total")
    labels_outpace_result = generation.get("implement_ok") and (
        not numeric(feature_passed) or not numeric(feature_total) or feature_passed < feature_total
    )
    if labels_outpace_result:
        findings.append(_finding(
            "internal-labels-not-completion", "P0",
            "内部 implement/wrote/verified 标签与产品结果没有闭合，不能据此声称节点完成。",
            ["generation.implement_ok", "generation.wrote_verified", "generation.verified_false",
             "run.feature_passed", "run.feature_total", "evaluation.details_available"],
            "把源码变更、构建启动、行为 probe 和需求映射绑定后，才允许输出 completed/verified。"))
    if errors.get("request_budget_hits", 0) or generation.get("request_budget_hits", 0):
        hits = errors.get("request_budget_hits", 0) or generation.get("request_budget_hits", 0)
        findings.append(_finding(
            "budget-cap", "P0", f"日志观察到 {hits} 次预算上限事件；触顶后的 ok 不能视为自然完成。",
            ["log_analysis.request_budget_hits"],
            "将 inspect、write、verify 分槽；verify 额度不可被前两阶段占用，触顶时输出 inconclusive。"))
    if not evaluation.get("details_available"):
        findings.append(_finding(
            "official-details-missing", "P0",
            "平台未提供逐测试明细，失败测试 ID、断言和测试级超时保持 unknown。",
            ["evaluation.details_available", "evaluation.tests", "evaluation.official_test_ids",
             "evaluation.log_observed_test_ids"],
            "增加可获取的结果路径、逐测试结果、Playwright trace/screenshot 证据；缺失时明确标 unknown。"))
    if not submission.get("binding_closed"):
        findings.append(_finding(
            "identity-not-closed", "P0",
            "提交包、源码、task/suite/requirements 的平台身份链未闭合，不能做严格 A/B 或因果归因。",
            ["submission.binding_closed", "submission.platform_agent_commit", "suite.task_snapshot_id",
             "suite.requirements_sha256_platform", "suite.suite_key"],
            "为 ZIP、构建身份、task snapshot、suite 和 requirements 建立可复核 binding，并分别记录平台与本地来源。"))
    if artifacts.get("missing_platform_evidence"):
        findings.append(_finding(
            "evidence-gaps", "P1",
            "仍有平台证据缺口；本地文件或日志推断不能冒充官方附件。",
            ["artifacts.missing_platform_evidence", "artifacts.declared_local_artifacts"],
            "继续采集缺失附件；无法获得时在结果中保留 missing/unknown 和来源。"))
    if deployment.get("repair_mentions") or deployment.get("rehearsal_mentions"):
        findings.append(_finding(
            "rehearsal-causality", "P1",
            "rehearsal/repair 只能证明运行过程发生过恢复，不能证明 repair 修改导致恢复。",
            ["deployment.rehearsal_mentions", "deployment.repair_mentions", "deployment.repair"],
            "记录每次 rehearsal 的请求、退出码、源码 delta 和行为 probe，再判断修复是否有效。"))
    if errors.get("broken_pipe_count") or errors.get("connection_reset_count"):
        findings.append(_finding(
            "transport-signal", "P1",
            "存在传输或连接异常；它们是运行信号，不能直接解释官方得分。",
            ["errors.broken_pipe_count", "errors.connection_reset_count"],
            "把异常请求和服务存活、重试结果分开记录，并为未知路径提供稳定响应。"))

    # A previous run is useful for direction, but hidden identity gaps prevent causal claims.
    comparison = None
    if isinstance(previous, dict) and previous.get("task_key") == run.get("task_key"):
        old_score = previous.get("score")
        if numeric(old_score) and numeric(run.get("score")):
            comparison = {"previous_run_id": previous.get("run_id"),
                          "score_delta": run["score"] - old_score,
                          "strict_ab": bool(previous.get("strict_ab") and forensics.get("suite", {}).get("strict_ab"))}
            if not comparison["strict_ab"]:
                findings.append(_finding(
                    "comparison-not-causal", "P1",
                    "历史结果只能作为观察到的方向信号；身份未闭合时不能归因于本次代码变化。",
                    ["comparison.previous_run_id", "comparison.score_delta", "suite.suite_key",
                     "submission.binding_closed"],
                    "优先在同一闭合 snapshot 下做配对比较。", confidence="high"))

    priority = {item["severity"] for item in findings}
    failed_or_incomplete = run.get("status") in TERMINAL and (
        (numeric(run.get("score")) and run.get("score") <= 0) or
        (numeric(feature_total) and numeric(feature_passed) and feature_passed < feature_total)
    )
    if failed_or_incomplete and findings:
        decision = "modify"
    elif not findings:
        decision = "stop"
    else:
        decision = "needs_evidence"
    for item in findings:
        actions.append({"code": item["code"], "priority": item["severity"],
                        "instruction": item["action"], "acceptance": [
                            "保留 evidence source 和字段路径",
                            "未获得官方证据时输出 unknown",
                            "不把内部标签写成官方通过"],
                        "confidence": item["confidence"]})
    return {
        "schema_version": 1,
        "decision": decision,
        "evidence_quality": {
            "platform_identity": "closed" if submission.get("binding_closed") else "inconclusive",
            "official_test_details": "available" if evaluation.get("details_available") else "unavailable",
            "local_evidence": "present" if forensics.get("local_manifest", {}).get("present") else "absent",
            "overall": "actionable_with_gaps" if findings else "sufficient",
        },
        "findings": findings,
        "actions": actions,
        "comparison": comparison,
        "next_slice": {
            "scope": "one vertical slice only",
            "must_change": ["agent implementation or its completion gate"],
            "must_prove": ["source delta", "build/start result", "behavior probe", "requirement-to-file traceability"],
            "must_not_claim": ["official pass from internal verified", "strict A/B without closed identity",
                                "test IDs or timeout types when platform returned none"],
        },
        "source": "controller-derived from platform status/logs, downloaded archives, and local manifest",
    }


def worker_context(summary):
    """Return the bounded evidence view that is safe and useful for code changes."""
    if not isinstance(summary, dict):
        return None
    facts = summary.get("forensics") or {}
    return {
        "run": facts.get("run") or {key: summary.get(key) for key in
                                      ("run_id", "status", "score", "passed", "failed", "task_key", "submission_id")},
        "analysis": summary.get("analysis") or {},
        "optimization_plan": summary.get("optimization_plan") or {},
        "generation": facts.get("generation") or {},
        "deployment": facts.get("deployment") or {},
        "evaluation": facts.get("evaluation") or {},
        "errors": facts.get("errors") or {},
        "identity": {
            "submission": facts.get("submission") or {},
            "suite": facts.get("suite") or {},
            "local_manifest": facts.get("local_manifest") or {},
        },
        "evidence": {
            "missing_platform_evidence": (facts.get("artifacts") or {}).get("missing_platform_evidence", []),
            "state_folder": (facts.get("artifacts") or {}).get("state_folder", []),
            "repo_evidence_folder": (facts.get("artifacts") or {}).get("repo_evidence_folder", []),
            "provenance": facts.get("provenance") or {},
        },
        "raw_evidence_is_external": True,
    }


def _file_kind(path):
    suffix = Path(path).suffix.lower()
    return {
        ".json": "json", ".jsonl": "jsonl", ".md": "markdown", ".txt": "text",
        ".zip": "archive", ".yaml": "yaml", ".yml": "yaml", ".png": "image",
        ".jpg": "image", ".jpeg": "image", ".webp": "image", ".trace": "trace",
    }.get(suffix, "file")


def _external_evidence_files(source_dir):
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise GateError("evidence source must be an existing directory")
    if source == ROOT or ROOT in source.parents:
        raise GateError("evidence source must stay outside the repository")
    files, skipped = [], []
    secret_words = ("password", "token", "cookie", "secret", "credential", ".env")
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        if any(word in path.name.lower() for word in secret_words):
            skipped.append({"path": relative, "reason": "secret_like_filename"})
            continue
        files.append({"path": relative, "bytes": path.stat().st_size,
                      "sha256": sha256(path), "kind": _file_kind(path)})
    return files, skipped


def build_evidence_index(run_id, source_dir):
    """Index external evidence without copying or parsing private payloads."""
    files, skipped = _external_evidence_files(source_dir)
    return {
        "schema_version": 1, "run_id": identifier(run_id),
        "source_dir": str(Path(source_dir).resolve()), "raw_not_copied": True,
        "files": files, "skipped": skipped, "indexed_at": utcnow(),
        "provenance": "external-local-files-metadata-only",
    }


def _safe_git_ref(value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", value) or ".." in value or value.startswith("-"):
        raise GateError("invalid context branch/ref")
    return value


def build_optimization_plan(run_id, analysis, forensics=None):
    """Compile analysis findings into a plan; this never authorizes execution."""
    analysis = analysis or {}
    findings = list(analysis.get("findings") or [])
    severity_rank = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda item: (severity_rank.get(item.get("severity"), 9), item.get("code", "")))
    priorities = [{key: item.get(key) for key in ("code", "severity", "conclusion", "action", "confidence", "evidence")}
                  for item in findings]
    top = priorities[0] if priorities else None
    objective = top["action"] if top else "没有新的高置信问题；保持只读并等待新的证据。"
    run = (forensics or {}).get("run", {})
    return {
        "schema_version": 1, "run_id": identifier(run_id), "generated_at": utcnow(),
        "mode": "plan_only", "authorization_required": True,
        "decision": analysis.get("decision", "needs_evidence"), "objective": objective,
        "priorities": priorities, "comparison": analysis.get("comparison"),
        "capability_slice": analysis.get("next_slice") or {"scope": "one vertical slice only"},
        "acceptance_contract": {
            "must_prove": (analysis.get("next_slice") or {}).get("must_prove", []),
            "must_not_claim": (analysis.get("next_slice") or {}).get("must_not_claim", []),
            "evidence_levels": ["platform_fact", "local_artifact", "log_observation", "derived_hypothesis", "unknown"],
        },
        "budget_policy": {"base_requests": 22, "continuation_requests": 12,
                          "max_requests_per_slice": 36, "explicit_override_max": 50,
                          "final_reserve_fraction": 0.25},
        "stop_conditions": [
            "identity or required evidence remains unknown",
            "seed or delivery artifact changes outside the disposable workspace",
            "cap hit without an independent verification result",
            "second continuation has no new product delta",
        ],
        "authorization": {"agent_edit": False, "harness_edit": False,
                          "tests_edit": False, "package": False, "cloud_run": False},
        "evidence_refs": {"run_url": run.get("url"), "source": analysis.get("source")},
    }


def write_coordination(path, deployment):
    """Replace only our top-level member; preserve the historical JSON formatting."""
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    match = re.search(r'^  "arc_optimizer_deployment":\s*', content, re.M)
    value = json.dumps(deployment, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    if match:
        _, length = json.JSONDecoder().raw_decode(content[match.end():])
        updated = content[:match.end()] + value + content[match.end() + length:]
    else:
        index = content.rfind("}")
        prefix = content[:index].rstrip()
        updated = prefix + ("," if data else "") + '\n  "arc_optimizer_deployment": ' + value + "\n}\n"
    expected = dict(data, arc_optimizer_deployment=deployment)
    if json.loads(updated) != expected:
        raise GateError("coordination update did not preserve historical members")
    fd, temporary = tempfile.mkstemp(prefix=".coordination-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def writer_lock(directory):
    """OS releases the lock on process exit; no stale-lock deletion needed."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "writer.lock").open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise GateError("another controller owns this state directory") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Controller:
    def __init__(self, config):
        self.c = config
        self.repo = Path(config["repo"]).resolve()
        self.store = Path(config["state_dir"]).resolve()
        self.env_file = Path(config["env_file"]).resolve()
        if self.store.is_relative_to(self.repo) or self.env_file.is_relative_to(self.repo):
            raise GateError("credentials and state must be outside the repository")
        if self.repo != ROOT:
            raise GateError("execute the controller from its intended checkout")
        self.journal = self.store / "controller.json"
        self.state = read_json(self.journal) if self.journal.exists() else {
            "schema_version": 1, "phase": "ready", "round": 0, "no_improvement": 0,
            "rounds": [], "spent_cny": 0, "last_run": config.get("baseline_run")
        }
        self.secrets = []
        self.codex_env_allowlist = _codex_env_names(config)
        for name in self.codex_env_allowlist:
            value = os.environ.get(name)
            if value:
                self.secrets.append(value)
        self.github_token = None
        if self.env_file.exists():
            for line in self.env_file.read_text(encoding="utf-8-sig").splitlines():
                key, _, value = line.partition("=")
                if any(word in key.lower() for word in ("key", "cookie", "token", "password")):
                    value = value.strip().strip("\"'")
                    if value:
                        self.secrets.append(value)
                        if "cookie" in key.lower():
                            self.secrets.extend(part.partition("=")[2].strip() for part in value.split(";"))

    def safe(self, value):
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        for secret in sorted(set(self.secrets), key=len, reverse=True):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text

    def save(self):
        self.state["updated_at"] = utcnow()
        atomic_json_write(self.journal, self.state)

    def command(self, argv, *, env=None, prompt=None, timeout=120, cwd=None):
        try:
            result = subprocess.run([str(item) for item in argv], cwd=cwd or self.repo, env=env,
                                    input=prompt, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            # Never serialize exception command arguments or captured partial secret output.
            raise GateError(f"process unavailable or timed out: {type(exc).__name__}") from exc
        return result.returncode, result.stdout, result.stderr

    def git(self, *args, cwd=None):
        code, out, _ = self.command([self.c["git"], "-C", cwd or self.repo, *args], cwd=cwd)
        if code:
            raise GateError(f"git {args[0]} failed (exit {code}); preserve workspace, inspect manually")
        return out.strip()

    def api(self, suffix):
        url = "https://api.github.com/repos/" + self.c["github_repo"] + "/" + suffix
        if self.github_token is None:
            # Use the existing approved credential manager only for GitHub REST.
            # Git fetch/push keep their selected SSH URL/authentication unchanged.
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
            code, out, _ = self.command([self.c["git"], "credential", "fill"],
                                        env=env, prompt="protocol=https\nhost=github.com\n\n", timeout=20)
            values = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
            self.github_token = values.get("password", "") if code == 0 else ""
            if self.github_token:
                self.secrets.append(self.github_token)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "octos-arc-optimizer"}
        if self.github_token:
            headers["Authorization"] = "Bearer " + self.github_token
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except Exception as exc:
            raise GateError("GitHub read failed; no validation/sync claim") from exc

    def preflight(self, *, fetch=True, clean=True, equal=True):
        if Path(self.git("rev-parse", "--show-toplevel")).resolve() != self.repo:
            raise GateError("wrong Git repository root")
        if self.git("branch", "--show-current") != self.c["branch"]:
            raise GateError("wrong branch")
        if self.git("remote", "get-url", self.c["remote"]) != self.c["remote_url"]:
            raise GateError("wrong remote URL")
        if self.git("remote", "get-url", "--push", self.c["remote"]) != self.c["remote_url"]:
            raise GateError("wrong push URL")
        if self.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") != self.c["remote"] + "/" + self.c["branch"]:
            raise GateError("wrong upstream")
        if clean and self.git("status", "--porcelain=v1", "--untracked-files=all"):
            raise GateError("dirty worktree; preserve and reconcile manually")
        if fetch:
            self.git("fetch", self.c["remote"])
        head = self.git("rev-parse", "HEAD")
        tracking = self.git("rev-parse", self.c["remote"] + "/" + self.c["branch"])
        if equal and head != tracking:
            raise GateError("local/remote changed; compare before a fast-forward or push")
        return head

    def verify_sync(self, expected):
        head = self.preflight()
        hosted = self.api("branches/" + urllib.parse.quote(self.c["branch"], safe=""))["commit"]["sha"]
        if expected != head or hosted != head:
            raise GateError("three-way SHA mismatch")
        return {"local": head, "tracking": head, "github": hosted}

    def sync_commit(self, paths, message, parent):
        """Resume a known local commit/push without committing a second time."""
        head = self.preflight(clean=False, equal=False)
        remote = self.git("rev-parse", self.c["remote"] + "/" + self.c["branch"])
        if remote != parent and remote != head:
            raise GateError("remote moved during the round; no automatic integration")
        if head == parent:
            actual = self.changed_paths()
            if not actual or not actual.issubset(set(paths)):
                raise GateError("unexpected changes before commit")
            if self.git("diff", "--cached", "--name-only"):
                raise GateError("pre-existing staged changes")
            self.git("diff", "--check")
            self.git("add", "--", *sorted(actual))
            self.git("commit", "-m", message)
            head = self.git("rev-parse", "HEAD")
        else:
            if self.git("rev-parse", "HEAD^") != parent or self.git("log", "-1", "--format=%s") != message:
                raise GateError("unknown commit appeared during recovery")
            committed = set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
            if not committed.issubset(set(paths)):
                raise GateError("recovery commit contains unexpected paths")
        if self.git("status", "--porcelain=v1"):
            raise GateError("worktree not clean after commit")
        self.git("push", self.c["remote"], "HEAD:refs/heads/" + self.c["branch"])
        self.git("fetch", self.c["remote"])
        return head, self.verify_sync(head)

    def changed_paths(self, root=None, parent="HEAD"):
        root = Path(root or self.repo).resolve()
        changed = self.git("diff", "--name-only", parent, cwd=root).splitlines()
        new = self.git("ls-files", "--others", "--exclude-standard", cwd=root).splitlines()
        return set(changed + new)

    def arc(self, *args, allowed_codes=(0,), timeout=120):
        env = dict(os.environ)
        env["ARC_BENCH_RECORD_DIR"] = str(self.store / "submissions")
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        argv = [self.c["python"], "-m", "arcbench_cli", "--env-file", self.env_file, "--json", *args]
        readonly = args[0] in {"whoami", "registration", "tasks", "status", "logs", "download", "archive"}
        for attempt in range(2 if readonly else 1):
            try:
                code, out, err = self.command(argv, env=env, timeout=timeout)
            except GateError:
                if readonly and attempt == 0:
                    continue
                raise
            if code and readonly and attempt == 0:
                try:
                    details = json.loads(err.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    details = {}
                if details.get("transport_failure") or (details.get("http_status") or 0) >= 500:
                    continue
            break
        if code:
            self.store.mkdir(parents=True, exist_ok=True)
            # CLI sanitizes account keys before logging; local redaction adds env secrets.
            (self.store / "last-cli-error.txt").write_text(self.safe(err), encoding="utf-8")
        try:
            result = json.loads(out)
        except json.JSONDecodeError as exc:
            raise GateError(f"ARC {args[0]} returned no complete JSON (exit {code})") from exc
        if code not in allowed_codes:
            raise GateError(f"ARC {args[0]} failed (exit {code}); inspect private CLI diagnostics")
        return result

    def doctor(self):
        report = {"repo": str(self.repo), "branch": self.c["branch"], "cli_revision": CLI_REVISION}
        auth_mode = codex_auth_mode(self.c)
        checks = (("python", [self.c["python"], "--version"]),
                  ("arcbench", [self.c["python"], "-m", "arcbench_cli", "--version"]),
                  ("codex", [self.c["codex"], "--version"]))
        for label, args in checks:
            code, out, err = self.command(args)
            report[label] = {"exit_code": code, "detail": self.safe((out + err).strip())}
        if auth_mode == "provider":
            report["codex_auth"] = {"exit_code": 0,
                                    "detail": "provider mode; codex login status is not required"}
        else:
            code, out, err = self.command([self.c["codex"], "login", "status"])
            report["codex_auth"] = {"exit_code": code, "detail": self.safe((out + err).strip())}
        try:
            report["sync"] = self.verify_sync(self.preflight())
        except GateError as exc:
            report["git_error"] = str(exc)
        try:
            report["arc_logged_in"] = bool(self.arc("whoami").get("logged_in"))
            registration = self.arc("registration", self.c["competition"])
            report["registration"] = {key: registration.get(key) for key in
                                      ("registered", "competition_id", "remaining_budget_cny")}
            tasks = self.arc("tasks", self.c["competition"])
            report["tasks"] = tasks.get("tasks", [])
        except GateError as exc:
            report["arc_error"] = str(exc)
        report["paid_loop_enabled"] = bool(self.c.get("enabled"))
        report["pending"] = [key for key in ("budget_cny", "deadline", "suite_key", "suite_provenance")
                             if not self.c.get(key)]
        report["status"] = "blocked" if ("git_error" in report or "arc_error" in report
                                          or not report.get("arc_logged_in")
                                          or any(report[label]["exit_code"] for label in ("python", "arcbench", "codex", "codex_auth"))) else "collection_ready"
        atomic_json_write(self.store / "doctor.json", report)
        return report

    def guard(self):
        c = self.c
        if not c.get("enabled"):
            raise GateError("paid loop disabled in external config")
        budget, estimate = c.get("budget_cny"), c.get("estimated_run_cny")
        if not numeric(budget) or budget <= 0 or not numeric(estimate) or estimate <= 0:
            raise GateError("explicit positive budget and conservative estimated_run_cny required")
        reserve = c.get("reserve_fraction", .25)
        if not numeric(reserve) or not .25 <= reserve < 1:
            raise GateError("reserve_fraction must be at least 25% and below 100%")
        if not c.get("deadline") or datetime.now(timezone.utc) >= parse_date(c["deadline"]):
            raise GateError("deadline missing or reached; do not create new runs")
        if self.state["round"] >= c["max_rounds"]:
            raise GateError("round limit reached")
        if self.state["no_improvement"] >= c["max_no_improvement"]:
            raise GateError("no-improvement limit reached")
        if self.state["spent_cny"] + estimate > budget * (1 - reserve):
            raise GateError("local spending allowance exhausted; preserve reserve")
        registration = self.arc("registration", c["competition"])
        remaining = registration.get("remaining_budget_cny")
        if not registration.get("registered") or not numeric(remaining) or remaining < budget * reserve + estimate:
            raise GateError("official remaining balance missing/too low")
        if not c.get("official_evaluation"):
            raise GateError("v1 supports official-evaluation budget only")
        if not c.get("suite_key") or not c.get("suite_provenance"):
            raise GateError("platform suite identity/provenance required; do not guess")
        requirements = self.repo / c["requirements_file"]
        if sha256(requirements).lower() != c["requirements_sha256"].lower():
            raise GateError("requirements archive SHA mismatch")

    def collect(self, run_id):
        """Read every log page using saved payloads, never CLI's truncated tail."""
        run_id = identifier(run_id)
        root = self.store / "runs" / run_id
        root.mkdir(parents=True, exist_ok=True)
        cursor_file = root / "collection.json"
        cursor = read_json(cursor_file) if cursor_file.exists() else {"offset": 0, "pages": [], "errors": {}}
        status = self.arc("status", run_id, "--full", allowed_codes=(0, 1))
        if not isinstance(status, dict) or status.get("id") != run_id or not status.get("status"):
            raise GateError("status response is not the requested run")
        atomic_json_write(root / "status.json", json.loads(self.safe(status)))
        cursor["logs_drained"] = False
        for _ in range(self.c.get("max_log_pages", 1000)):
            offset = cursor["offset"]
            page = root / "log-pages" / f"{offset:012d}"
            payload_path = page / f"{run_id}-logs.json"
            if not payload_path.exists() or cursor.get("terminal_offset") == offset:
                self.arc("logs", run_id, "--offset", str(offset), "--tail", "1", "--out", str(page))
            payload = read_json(payload_path)
            next_offset = payload.get("log_offset")
            if not isinstance(next_offset, int) or next_offset < offset:
                raise GateError("invalid/missing log cursor; completeness unknown")
            if next_offset == offset:
                cursor["terminal_offset"] = offset
                cursor["logs_drained"] = True
                atomic_json_write(cursor_file, cursor)
                break
            record = {"offset": offset, "next_offset": next_offset,
                      "path": payload_path.relative_to(root).as_posix(), "sha256": sha256(payload_path),
                      "last_event_id": payload.get("last_event_id")}
            if not any(item["offset"] == offset for item in cursor["pages"]):
                cursor["pages"].append(record)
            cursor["offset"] = next_offset
            atomic_json_write(cursor_file, cursor)
        if str(status["status"]).upper() in TERMINAL:
            outputs = [("workspace", "download", run_id, root / "workspace.zip")]
            submission_id = status.get("submission_id")
            if submission_id:
                outputs.append(("archive", "archive", identifier(submission_id), root / "submission.zip"))
            for label, command, remote_id, output in outputs:
                if not output.exists():
                    try:
                        self.arc(command, remote_id, "--output", str(output), timeout=300)
                        cursor["errors"].pop(label, None)
                    except GateError as exc:
                        cursor["errors"][label] = str(exc)
            atomic_json_write(cursor_file, cursor)
        files = [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
                 for p in sorted(root.rglob("*")) if p.is_file() and p.name not in {"summary.json", "analysis.json"}]
        forensics = build_forensics(status, cursor, files, self.state.get("candidate", {}), root, self.repo)
        previous = None
        last_run = self.state.get("last_run")
        if last_run and str(last_run) != run_id:
            previous_path = self.store / "runs" / str(last_run) / "summary.json"
            if previous_path.exists():
                previous = read_json(previous_path)
        analysis = analyze_forensics(forensics, previous)
        optimization_plan = build_optimization_plan(run_id, analysis, forensics)
        atomic_json_write(root / "analysis.json", analysis)
        atomic_json_write(root / "optimization-plan.json", optimization_plan)
        forensics["artifacts"]["state_folder"] = _local_files(root)
        files = [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
                 for p in sorted(root.rglob("*")) if p.is_file() and p.name != "summary.json"]
        summary = normalize(status, cursor, files, self.state.get("candidate", {}))
        summary["forensics"] = forensics
        summary["analysis"] = analysis
        summary["optimization_plan"] = optimization_plan
        atomic_json_write(root / "summary.json", summary)
        return summary

    def ingest(self, run_id, source_dir):
        """Index an external evidence directory; raw files remain outside the repository."""
        run_id = identifier(run_id)
        root = self.store / "runs" / run_id
        root.mkdir(parents=True, exist_ok=True)
        index = build_evidence_index(run_id, source_dir)
        atomic_json_write(root / "evidence-index.json", index)
        return index

    def analyze(self, run_id):
        """Recompute analysis and plan from already-collected state without ARC calls."""
        run_id = identifier(run_id)
        root = self.store / "runs" / run_id
        summary_path = root / "summary.json"
        summary = read_json(summary_path) if summary_path.is_file() else {}
        forensics = summary.get("forensics")
        if not isinstance(forensics, dict):
            status = _read_optional_json(root / "status.json")
            cursor = _read_optional_json(root / "collection.json") or {"offset": 0, "pages": [], "errors": {}}
            if not isinstance(status, dict) or status.get("id") != run_id:
                raise GateError("collect this run before analyze")
            files = [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
                     for p in sorted(root.rglob("*")) if p.is_file() and p.name not in {"summary.json", "analysis.json", "optimization-plan.json"}]
            forensics = build_forensics(status, cursor, files, self.state.get("candidate", {}), root, self.repo)
            summary = normalize(status, cursor, files, self.state.get("candidate", {}))
            summary["forensics"] = forensics
        previous = None
        last_run = self.state.get("last_run")
        if last_run and str(last_run) != run_id:
            previous_path = self.store / "runs" / str(last_run) / "summary.json"
            if previous_path.exists():
                previous = read_json(previous_path)
        analysis = analyze_forensics(forensics, previous)
        plan = build_optimization_plan(run_id, analysis, forensics)
        atomic_json_write(root / "analysis.json", analysis)
        atomic_json_write(root / "optimization-plan.json", plan)
        summary["analysis"] = analysis
        summary["optimization_plan"] = plan
        summary["files"] = _run_file_records(root)
        summary["collected_at"] = summary.get("collected_at", utcnow())
        atomic_json_write(summary_path, summary)
        return {"run_id": run_id, "analysis": analysis, "optimization_plan": plan}

    def plan(self, run_id):
        """Return the saved plan or compile one from an existing analysis artifact."""
        run_id = identifier(run_id)
        root = self.store / "runs" / run_id
        summary = read_json(root / "summary.json") if (root / "summary.json").is_file() else {}
        analysis = summary.get("analysis") or _read_optional_json(root / "analysis.json")
        if not isinstance(analysis, dict):
            raise GateError("analyze this run before plan")
        forensics = summary.get("forensics") or {}
        plan = build_optimization_plan(run_id, analysis, forensics)
        atomic_json_write(root / "optimization-plan.json", plan)
        if summary:
            summary["optimization_plan"] = plan
            atomic_json_write(root / "summary.json", summary)
        return plan

    def context_snapshot(self, branch):
        """Record context-file identities from another branch without merging it."""
        branch = _safe_git_ref(branch)
        commit = self.git("rev-parse", branch + "^{commit}")
        records = []
        for relative in self.c.get("context", []):
            code, output, _ = self.command([self.c["git"], "-C", self.repo, "ls-tree", "-r", commit, "--", relative])
            if code:
                raise GateError("unable to inspect context branch")
            matches = [line for line in output.splitlines() if "\t" in line]
            if not matches:
                records.append({"path": relative, "present": False})
                continue
            mode, kind, blob, path = matches[0].split(None, 3)
            records.append({"path": path, "present": True, "mode": mode, "kind": kind, "blob": blob})
        snapshot = {"schema_version": 1, "branch": branch, "commit": commit,
                    "files": records, "merged": False, "raw_not_copied": True,
                    "created_at": utcnow()}
        target = self.store / "contexts" / (commit + ".json")
        atomic_json_write(target, snapshot)
        return snapshot

    def reconcile(self, run_id):
        """Persist the two external monitor inputs as a conservative decision."""
        run_id = identifier(run_id)
        target = self.store / "runs" / run_id / "reconciled-plan.json"
        result = reconcile_monitor_inputs(self.store, run_id)
        atomic_json_write(target, result)
        return result

    def _codegen_authorization(self, parent, plan_sha, analysis_sha):
        """Validate an explicit, short-lived authorization for one codegen slice."""
        if self.c.get("execution_policy", "plan_only") != "agent_edit":
            raise GateError("execution policy is plan_only; codegen is stopped")
        if self.c.get("allow_agent_edit") is not True:
            raise GateError("allow_agent_edit must be explicitly true")
        for key in ("allow_harness_edit", "allow_tests_edit", "allow_package", "allow_cloud_run"):
            if self.c.get(key):
                raise GateError(key + " is forbidden during isolated codegen")
        authorization = self.c.get("codegen_authorization") or {}
        if authorization.get("enabled") is not True:
            raise GateError("codegen authorization is disabled")
        if authorization.get("parent_sha") != parent:
            raise GateError("codegen authorization parent SHA does not match current HEAD")
        if authorization.get("plan_sha256", "").lower() != plan_sha.lower():
            raise GateError("codegen authorization plan hash does not match")
        if authorization.get("analysis_sha256", "").lower() != analysis_sha.lower():
            raise GateError("codegen authorization analysis hash does not match")
        expires_at = authorization.get("expires_at")
        if not expires_at or datetime.now(timezone.utc) >= parse_date(expires_at):
            raise GateError("codegen authorization is expired or missing TTL")
        issued_at = authorization.get("issued_at")
        if issued_at:
            ttl = (parse_date(expires_at) - parse_date(issued_at)).total_seconds()
            maximum = self.c.get("authorization_ttl_seconds", 3600)
            if ttl <= 0 or ttl > maximum:
                raise GateError("codegen authorization TTL exceeds configured limit")
        allowed = authorization.get("allowed_paths") or self.c.get("allowed_paths", [])
        allowed = _safe_relative_paths(allowed)
        if not allowed or any(_forbidden_codegen_path(path) for path in allowed):
            raise GateError("codegen allowed paths contain forbidden harness/test/requirements files")
        return {"enabled": True, "expires_at": expires_at, "allowed_paths": allowed,
                "parent_sha": parent, "plan_sha256": plan_sha, "analysis_sha256": analysis_sha,
                "source": authorization.get("source", "explicit external codegen authorization")}

    def _check_monitor_binding(self, reconciliation, parent, plan_sha, analysis_sha):
        if reconciliation.get("decision") != "GO" or len(reconciliation.get("reports", [])) != 2:
            raise GateError("two bound GO monitor reports are required")
        for item in reconciliation["reports"]:
            report = item["report"]
            if str(report.get("run_id")) != str(self.state.get("last_run")) or \
                    report.get("reviewed_parent_sha") != parent or \
                    str(report.get("plan_sha256", "")).lower() != plan_sha.lower() or \
                    str(report.get("analysis_sha256", "")).lower() != analysis_sha.lower():
                raise GateError("monitor report Run/parent/plan/analysis binding mismatch")

    def resume_codegen(self):
        """Begin an explicitly authorized retry while preserving the stopped journal."""
        if self.state.get("phase") != "stopped":
            raise GateError("resume-codegen requires a stopped controller")
        previous_folder = Path(self.state.get("worker_dir", self.store / "rounds/001"))
        candidate = self.state.get("candidate") or {}
        if candidate.get("submission_id") or candidate.get("run_id") or \
                (previous_folder / "upload.json").exists() or (previous_folder / "run.json").exists():
            raise GateError("cloud outcome must be reconciled before resuming codegen")
        parent = self.preflight()
        run_id = identifier(self.state.get("last_run"))
        root = self.store / "runs" / run_id
        plan_sha = _hash_json_file(root / "optimization-plan.json")
        analysis_sha = _hash_json_file(root / "analysis.json")
        authorization = self._codegen_authorization(parent, plan_sha, analysis_sha)
        reconciliation = reconcile_monitor_inputs(self.store, run_id)
        self._check_monitor_binding(reconciliation, parent, plan_sha, analysis_sha)
        resumed_at = utcnow()
        record = {"schema_version": 1, "previous_state": dict(self.state),
                  "parent_sha": parent, "authorization": authorization,
                  "monitor_reconciliation": reconciliation, "resumed_at": resumed_at}
        history = self.store / "transitions"
        history.mkdir(parents=True, exist_ok=True)
        sequence = 1
        while (history / f"resume-{sequence:06d}.json").exists() or \
                (history / f"resume-{sequence:06d}.previous.json").exists():
            sequence += 1
        target = history / f"resume-{sequence:06d}.json"
        previous_journal = history / f"resume-{sequence:06d}.previous.json"
        if self.journal.exists():
            raw = self.journal.read_bytes()
            with previous_journal.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            record.update(previous_journal=str(previous_journal),
                          previous_journal_sha256=_sha256_bytes(raw))
        atomic_json_write(target, record)
        self.state.update(phase="ready", resume_record=str(target), resumed_at=resumed_at)
        self.save()
        return {"phase": "ready", "resume_record": str(target), "parent_sha": parent,
                "cloud_run": False, "worker_started": False}

    def _new_worker_folder(self, round_id):
        """Allocate an attempt without overwriting evidence from a failed retry."""
        root = self.store / "rounds"
        root.mkdir(parents=True, exist_ok=True)
        attempt = 1
        while True:
            name = f"{round_id:03d}" if attempt == 1 else f"{round_id:03d}-attempt-{attempt:03d}"
            folder = root / name
            try:
                folder.mkdir()
                return folder
            except FileExistsError:
                attempt += 1

    def _create_codegen_worktree(self, path, parent):
        path = Path(path).resolve()
        if path.exists():
            raise GateError("disposable worktree already exists; inspect before retry")
        path.parent.mkdir(parents=True, exist_ok=True)
        code, _, _ = self.command([self.c["git"], "-C", self.repo, "worktree", "add", "--detach", path, parent],
                                   timeout=180)
        if code:
            raise GateError("unable to create disposable codegen worktree")
        if self.git("rev-parse", "HEAD", cwd=path) != parent:
            raise GateError("disposable worktree parent SHA mismatch")
        return path

    def _remove_codegen_worktree(self, path):
        path = Path(path)
        if not path.exists():
            return
        if self.git("status", "--porcelain=v1", "--untracked-files=all", cwd=path):
            raise GateError("codegen worktree has changes; preserve it for inspection")
        code, _, _ = self.command([self.c["git"], "-C", self.repo, "worktree", "remove", path],
                                   timeout=180)
        if code:
            raise GateError("unable to remove disposable codegen worktree; preserve it for inspection")

    def snapshot_codegen_worktree(self, path, folder, parent):
        """Archive the diff before validation; untracked files remain in place."""
        paths = self.changed_paths(path, parent)
        code, diff_text, _ = self.command([self.c["git"], "-C", path, "diff", "--binary", parent],
                                         cwd=path)
        if code:
            raise GateError("unable to snapshot codegen diff; preserve worktree")
        payload = diff_text.encode("utf-8")
        target = folder / "worker.patch"
        target.write_bytes(payload)
        snapshot = {"parent_sha": parent, "changed_files": sorted(paths),
                    "patch": str(target), "diff_sha256": _sha256_bytes(payload),
                    "worktree": str(path), "created_at": utcnow()}
        atomic_json_write(folder / "worker-snapshot.json", snapshot)
        self.state.update(worker_snapshot=str(folder / "worker-snapshot.json"),
                          worktree_preserved=True)
        return snapshot

    def worker(self):
        parent = self.preflight()
        round_id = self.state["round"] + 1
        folder = self._new_worker_folder(round_id)
        last = self.state.get("last_run")
        if not last:
            raise GateError("no collected Run is available for codegen")
        run_root = self.store / "runs" / str(last)
        summary_path = run_root / "summary.json"
        evidence = read_json(summary_path) if summary_path.exists() else {}
        analysis_path = run_root / "analysis.json"
        plan_path = run_root / "optimization-plan.json"
        analysis = _read_optional_json(analysis_path)
        plan = _read_optional_json(plan_path)
        if not isinstance(analysis, dict) or not isinstance(plan, dict):
            raise GateError("analyze and plan this Run before codegen")
        analysis_sha = _hash_json_file(analysis_path)
        plan_sha = _hash_json_file(plan_path)
        authorization = self._codegen_authorization(parent, plan_sha, analysis_sha)
        reconciliation = reconcile_monitor_inputs(self.store, last)
        override = self.c.get("monitor_reconciliation_override") or {}
        override_marker = self.store / "monitor-overrides" / (str(last) + ".json")
        if reconciliation["decision"] != "GO" and override.get("enabled") is True and \
                str(override.get("run_id")) == str(last) and not override_marker.exists():
            expires_at = override.get("expires_at")
            if expires_at and datetime.now(timezone.utc) >= parse_date(expires_at):
                raise GateError("monitor reconciliation override is expired")
            reason = str(override.get("reason", "")).strip()
            if not reason:
                raise GateError("monitor reconciliation override requires a reason")
            original = reconciliation["decision"]
            reconciliation.update({"decision": "GO", "original_decision": original,
                                   "override_applied": True, "override_reason": reason,
                                   "override_source": "explicit external authorization",
                                   "override_run_id": str(last), "override_expires_at": expires_at,
                                   "override_marker": str(override_marker)})
            atomic_json_write(override_marker, {"schema_version": 1, "run_id": str(last),
                                                "original_decision": original, "reason": reason,
                                                "applied_at": utcnow(), "expires_at": expires_at})
        atomic_json_write(folder / "reconciled-plan.json", reconciliation)
        if reconciliation["decision"] != "GO":
            raise GateError("monitor reconciliation is " + reconciliation["decision"] + "; codegen stopped")
        if not reconciliation.get("override_applied"):
            self._check_monitor_binding(reconciliation, parent, plan_sha, analysis_sha)
        evidence.update(analysis=analysis, optimization_plan=plan)
        worker_evidence = worker_context(evidence)
        request = {
            "schema_version": 2, "run_id": str(last), "parent_sha": parent,
            "plan_sha256": plan_sha, "analysis_sha256": analysis_sha,
            "allowed_paths": authorization["allowed_paths"],
            "forbidden_paths": ["harness", "official-tests", "public-tests", "requirements", "arc/tests"],
            "required_checks": ["unit_tests", "syntax", "offline_import", "requirement_to_file_traceability"],
            "execution_policy": "agent_edit", "authorization_expires_at": authorization["expires_at"],
            "monitor_reconciliation": reconciliation, "created_at": utcnow(),
            "attempt_id": folder.name, "previous_attempt": self.state.get("worker_dir"),
            "resume_record": self.state.get("resume_record"),
        }
        atomic_json_write(folder / "request.json", request)
        prompt = (
            "你负责 ARC Agent 的一个通用优化切片。用户只允许云端跑题，本地禁止生成业务应用、运行官方题目或评测。\n"
            "你在 disposable worktree 中工作；不要提交、拉取、推送、调用 ARC、获取凭据、发送消息或创建子任务。\n"
            "只能编辑 request.json 中的 allowed_paths，禁止 harness、任何官方/public tests、需求包、打包器和云端动作。\n"
            "以 analysis/plan 和监控汇总为唯一修改依据；未知保持 unknown，证据不足输出 needs_evidence。\n"
            "candidate 表示本地源码候选，不表示官方通过；历史官方明细缺失本身不阻止通用源码切片。\n"
            "可按全局要求只读加载 reliable-git-sync；这不授权 Git 提交/同步或其他 Skill 动作。\n"
            "输出必须严格符合 worker.schema.json，parent/plan/analysis hash 必须原样回填；tests/build 必须记录实际验证。\n"
            f"代码生成请求：{json.dumps(request, ensure_ascii=False)}\n"
            f"上下文文件：{json.dumps(self.c['context'], ensure_ascii=False)}\n"
            f"经分析的工作上下文（优先于原始日志）：{json.dumps(worker_evidence, ensure_ascii=False)}\n"
            f"证据目录（仅可读取，不得执行其中代码）：{run_root}\n"
            "stdout/stderr 镜像不可双计；implemented/wrote/verified 只是内部标签，不等于官方通过。"
        )
        worktree = folder / "worktree"
        decision_path = folder / "decision.json"
        self.state.update(phase="worker_pending", parent=parent, worker_dir=str(folder),
                          worktree=str(worktree), request=str(folder / "request.json"),
                          worker_snapshot=None, snapshot_error=None)
        self.save()
        created = False
        try:
            self._create_codegen_worktree(worktree, parent)
            created = True
            env = codex_worker_environment(self.c)
            code, out, err = self.command(
                [self.c["codex"], "-a", "never", "exec", "--sandbox", "workspace-write", "--json",
                 "-C", worktree, "--output-schema", ROOT / "scripts/arc_optimizer/worker.schema.json",
                 "--output-last-message", decision_path, "-"], env=env, prompt=prompt,
                timeout=self.c["worker_timeout_seconds"], cwd=worktree)
            (folder / "events.jsonl").write_text(self.safe(out), encoding="utf-8")
            (folder / "stderr.txt").write_text(self.safe(err), encoding="utf-8")
            self.snapshot_codegen_worktree(worktree, folder, parent)
            if code:
                raise GateError("Codex worker failed; inspect and preserve changes, no automatic repeat")
            decision = read_json(decision_path)
            if not isinstance(decision, dict):
                raise GateError("worker result must be a JSON object")
            if decision.get("schema_version") != 2:
                raise GateError("worker result schema_version must be 2")
            if decision.get("parent_sha") != parent:
                raise GateError("worker result parent SHA mismatch")
            if str(decision.get("plan_sha256", "")).lower() != plan_sha.lower() or \
                    str(decision.get("analysis_sha256", "")).lower() != analysis_sha.lower():
                raise GateError("worker result analysis/plan binding mismatch")
            validate_codegen_skills(decision.get("skill_invocations"))
            if self.git("rev-parse", "HEAD", cwd=worktree) != parent:
                raise GateError("worker changed its parent commit; preserve for inspection")
            if not isinstance(decision.get("tests"), list) or not isinstance(decision.get("build"), dict):
                raise GateError("worker result must include tests[] and build{}")
            if decision.get("decision") in {"stop", "needs_evidence"} and not decision.get("stop_reason"):
                raise GateError("stopped worker result must include stop_reason")
            paths = self.changed_paths(worktree, parent)
            reported = set(_safe_relative_paths(decision.get("changed_files")))
            allowed = set(authorization["allowed_paths"])
            forbidden = [Path(str(item)).as_posix().strip("/").lower()
                         for item in self.c.get("forbidden_paths", [])]
            if any(_forbidden_codegen_path(path) or any(
                    path.lower() == item or path.lower().startswith(item + "/")
                    for item in forbidden) for path in paths):
                raise GateError("worker changed a forbidden harness/test/requirements path")
            if any(path not in allowed for path in paths) or paths != reported:
                raise GateError("worker changed unexpected or unreported paths")
            if decision.get("decision") == "candidate":
                if not paths:
                    raise GateError("candidate has no source changes")
                if not any(path.startswith("arc/") and not path.startswith("arc/tests/") for path in paths):
                    raise GateError("candidate has no Agent implementation change")
            elif decision.get("decision") not in {"stop", "needs_evidence"}:
                raise GateError("unknown worker decision")
            code, patch_text, _ = self.command([self.c["git"], "-C", worktree, "diff", "--binary", parent],
                                               cwd=worktree)
            if code:
                raise GateError("unable to read disposable worktree diff")
            patch_bytes = patch_text.encode("utf-8")
            diff_sha = _sha256_bytes(patch_bytes)
            if str(decision.get("diff_sha256", "")).lower() != diff_sha.lower():
                raise GateError("worker result diff hash mismatch")
            (folder / "candidate.patch").write_bytes(patch_bytes)
            decision["changed_files"] = sorted(paths)
            decision["diff_sha256"] = diff_sha
            atomic_json_write(folder / "result.json", decision)
            if decision.get("decision") != "candidate":
                self.state.update(phase="stopped", reason=decision.get("stop_reason") or decision.get("decision"),
                                  candidate_result=str(folder / "result.json"))
            else:
                self.state.update(phase="candidate_review", changed_files=sorted(paths), decision=decision,
                                  candidate_result=str(folder / "result.json"), diff_sha256=diff_sha,
                                  patch=str(folder / "candidate.patch"))
            self.save()
        except (GateError, OSError, ValueError, KeyError) as exc:
            self.state.update(phase="stopped", reason=self.safe(str(exc)),
                              worktree_preserved=bool(created and worktree.exists()))
            if created and worktree.exists() and not self.state.get("worker_snapshot"):
                try:
                    self.snapshot_codegen_worktree(worktree, folder, parent)
                except (GateError, OSError, ValueError, KeyError) as snapshot_error:
                    self.state["snapshot_error"] = self.safe(str(snapshot_error))
            atomic_json_write(folder / "failure.json", {
                "parent_sha": parent, "plan_sha256": plan_sha, "analysis_sha256": analysis_sha,
                "reason": self.state["reason"], "worktree": str(worktree),
                "worktree_preserved": self.state["worktree_preserved"], "created_at": utcnow()})
            self.save()
            raise
        finally:
            # Keep the workspace even after a rejected result or timeout. A
            # snapshot is evidence, not permission to discard unknown files.
            if created and worktree.exists():
                self.state["worktree_preserved"] = True
                self.save()

    def approve_candidate(self):
        """Apply a reviewed external patch and resume the serialized commit gate."""
        if self.state.get("phase") != "candidate_review":
            raise GateError("no candidate is awaiting Integrator approval")
        parent = self.state.get("parent")
        if not parent or self.git("rev-parse", "HEAD") != parent:
            raise GateError("candidate parent SHA no longer matches integration HEAD")
        self.preflight()
        if self.changed_paths():
            raise GateError("integration worktree is not clean; preserve and reconcile manually")
        patch_path = Path(self.state.get("patch", ""))
        if not patch_path.is_file():
            raise GateError("candidate patch is missing")
        patch_bytes = patch_path.read_bytes()
        expected = str(self.state.get("diff_sha256", "")).lower()
        if not expected or _sha256_bytes(patch_bytes).lower() != expected:
            raise GateError("candidate patch SHA does not match the reviewed result")
        try:
            patch_text = patch_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GateError("candidate patch is not UTF-8 text") from exc
        check = [self.c["git"], "-C", self.repo, "apply", "--check", "--whitespace=error", "-"]
        code, _, _ = self.command(check, prompt=patch_text, timeout=120)
        if code:
            raise GateError("candidate patch no longer applies cleanly")
        apply = [self.c["git"], "-C", self.repo, "apply", "--whitespace=error", "-"]
        code, _, _ = self.command(apply, prompt=patch_text, timeout=120)
        if code:
            raise GateError("candidate patch application failed")
        actual = self.changed_paths()
        expected_paths = set(self.state.get("changed_files") or [])
        if actual != expected_paths:
            raise GateError("applied candidate paths differ from reviewed result")
        code, diff_text, _ = self.command([self.c["git"], "-C", self.repo, "diff", "--binary", parent], timeout=120)
        if code or _sha256_bytes(diff_text.encode("utf-8")).lower() != expected:
            raise GateError("applied candidate diff SHA does not match reviewed result")
        self.state.update(phase="candidate_sync", approved_at=utcnow())
        self.save()
        return self.state

    def validate_ci(self, source):
        data = self.api("actions/workflows/arc-optimizer-check.yml/runs?head_sha=" + source + "&per_page=20")
        runs = [item for item in data.get("workflow_runs", [])
                if item.get("head_sha") == source and item.get("head_branch") == self.c["branch"] and item.get("event") == "push"]
        if not runs:
            return False
        run = max(runs, key=lambda item: item["id"])
        if run.get("status") != "completed":
            return False
        if run.get("conclusion") != "success":
            raise GateError("candidate CI failed; no upload")
        self.state["candidate"]["ci"] = {"id": run["id"], "url": run["html_url"], "head_sha": source}
        return True

    def package(self):
        if self.c.get("allow_package") is not True:
            raise GateError("allow_package must be explicitly true; no package created")
        self.guard()
        source = self.state["candidate"]["source_commit"]
        self.verify_sync(source)
        folder = Path(self.state["worker_dir"])
        archive = folder / ("agent-" + source[:12] + ".zip")
        if archive.exists():
            raise GateError("package already exists without journal entry; verify manually")
        env = dict(os.environ)
        env["PATH"] = str(Path(self.c["python"]).parent) + os.pathsep + str(Path(self.c["git"]).parent) + os.pathsep + env.get("PATH", "")
        env.update(ARCBENCH_TASK_KEY=self.c["task"], ARCBENCH_TEST_SUITE_KEY=self.c["suite_key"],
                   ARCBENCH_REQUIREMENTS_SHA256=self.c["requirements_sha256"])
        argv = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", self.repo / "arc/pack.ps1", "-OutputPath", archive]
                if os.name == "nt" else ["bash", self.repo / "arc/pack.sh", archive])
        code, out, err = self.command(argv, env=env, timeout=300)
        (folder / "pack.log").write_text(self.safe(out + err), encoding="utf-8")
        if code:
            raise GateError("existing package gate failed")
        binding = read_json(archive.with_suffix(".binding.json"))
        if binding.get("status") != "verified" or binding["source"]["commit_sha"] != source or binding["artifact"]["sha256"].lower() != sha256(archive):
            raise GateError("package/source binding mismatch")
        self.state["candidate"].update(package=str(archive), package_sha256=sha256(archive), binding=binding)
        self.state["phase"] = "packaged"
        self.save()

    def mutate_once(self, operation, args):
        if operation in {"upload", "run"} and self.c.get("allow_cloud_run") is not True:
            raise GateError("allow_cloud_run must be explicitly true; no cloud mutation")
        # Journal BEFORE request. Unknown outcomes require explicit reconciliation.
        self.state["phase"] = operation + "_pending"
        self.save()
        result = self.arc(*args, allowed_codes=(0, 1), timeout=300)
        atomic_json_write(Path(self.state["worker_dir"]) / (operation + ".json"), json.loads(self.safe(result)))
        return result

    def step(self):
        phase = self.state["phase"]
        if phase == "ready":
            self.worker()
        elif phase == "candidate_review":
            raise GateError("candidate patch is awaiting Integrator review; no package or cloud action")
        elif phase == "candidate_sync":
            head, sync = self.sync_commit(self.state["changed_files"],
                                          f"fix(arc): optimizer round {self.state['round'] + 1}", self.state["parent"])
            self.state.update(phase="ci_wait", ci_started_at=utcnow(), candidate={"source_commit": head, "sync": sync})
            self.save()
        elif phase == "ci_wait":
            source = self.state["candidate"]["source_commit"]
            if self.validate_ci(source):
                self.state["phase"] = "validated"
                self.save()
            elif (datetime.now(timezone.utc) - parse_date(self.state["ci_started_at"])).total_seconds() > self.c["ci_timeout_seconds"]:
                raise GateError("CI validation deadline exceeded; preserve candidate")
        elif phase == "validated":
            self.package()
        elif phase == "packaged":
            self.guard()
            candidate = self.state["candidate"]
            self.verify_sync(candidate["source_commit"])
            if sha256(candidate["package"]) != candidate["package_sha256"]:
                raise GateError("package changed after validation")
            result = self.mutate_once("upload", ["upload", candidate["package"], "--competition", self.c["competition"],
                                                 "--name", "octos-optimizer-" + candidate["source_commit"][:12],
                                                 "--model", self.c["model"], "--official-evaluation"])
            sid = result.get("submission", {}).get("id")
            if not sid or not result.get("archive_verified") or result.get("uploaded_sha256", "").lower() != candidate["package_sha256"]:
                raise GateError("upload identity not verified; reconcile, never upload again blindly")
            candidate["submission_id"] = identifier(sid)
            self.state["phase"] = "uploaded"
            self.save()
        elif phase == "uploaded":
            self.guard()
            result = self.mutate_once("run", ["run", self.state["candidate"]["submission_id"],
                                               "--task", self.c["task"], "--queue-timeout", "30"])
            if not isinstance(result, list) or len(result) != 1 or not result[0].get("run_id"):
                raise GateError("run creation outcome uncertain; inspect existing runs, never recreate")
            self.state["candidate"]["run_id"] = identifier(result[0]["run_id"])
            self.state["phase"] = "running"
            self.state["start_error"] = result[0].get("start_error")
            self.save()
        elif phase == "running":
            summary = self.collect(self.state["candidate"]["run_id"])
            # Polling/deadline does not imply cancellation; never lose collection on budget gates.
            if summary["status"] in TERMINAL:
                if not summary["logs_drained"] or "workspace.zip" in summary["missing_evidence"] or not summary["candidate_identity_closed"]:
                    raise GateError("terminal run evidence incomplete; resume collection before optimization")
                if summary["submission_id"] != self.state["candidate"]["submission_id"] or summary["task_key"] != self.c["task"]:
                    raise GateError("platform run/submission/task binding mismatch")
                self.state.update(phase="evidence_publish", result=summary, evidence_parent=self.preflight())
                self.save()
            elif self.state.get("start_error") and summary["status"] == "PENDING":
                raise GateError("known run remains PENDING; inspect then explicitly start the same run ID")
        elif phase == "evidence_publish":
            self.publish()
        elif phase == "round_complete":
            self.guard()
            self.state["phase"] = "ready"
            self.save()
        elif phase.endswith("_pending"):
            raise GateError("interrupted operation: reconcile journal and platform, no automatic repeat")
        elif phase == "stopped":
            raise GateError("controller stopped: " + self.state.get("reason", "decision"))
        else:
            raise GateError("unknown controller phase")
        return self.state

    def publish(self):
        result = self.state["result"]
        run_id = result["run_id"]
        candidate = self.state["candidate"]
        relative = "evidence/arc-bench/automation/" + run_id + ".json"
        # Write only a normalized manifest, never account data, raw logs or ZIPs.
        self.preflight(clean=False, equal=False)
        allowed = {relative, PLAN, LOG, REGISTER, PROJECT_LOG, COORDINATION}
        dirty = self.changed_paths()
        if not dirty.issubset(allowed):
            raise GateError("unrelated changes before evidence publication")
        atomic_json_write(self.repo / relative, result)
        marker = f"<!-- arc-optimizer:{run_id} -->"
        entry = (f"\n\n{marker}\n### CLI 云端闭环 Run `{run_id}`\n\n"
                 f"- 源提交：`{candidate['source_commit']}`；ZIP SHA-256：`{candidate['package_sha256']}`。\n"
                 f"- submission：`{candidate['submission_id']}`；状态：`{result['status']}`；score：`{result['score']}`。\n"
                 f"- 成本：`{result['cost']}`；完整归一化证据：[automation/{run_id}](../{relative})。\n"
                 "- CLI 状态、全分页日志、workspace/提交包已采集；隐藏 suite/test 身份缺失保持 unknown，不能称严格 A/B。\n"
                 "- 原始文件在仓库外；此记录不覆盖历史人工分析。下一切片须依据证据与剩余预算。\n")
        for path in (PLAN, LOG, REGISTER, PROJECT_LOG):
            target = self.repo / path
            content = target.read_text(encoding="utf-8")
            if marker not in content:
                adjusted = entry.replace("../evidence/", "evidence/") if path == PROJECT_LOG else entry
                target.write_text(content.rstrip() + adjusted, encoding="utf-8")
        coordination_path = self.repo / COORDINATION
        coordination = read_json(coordination_path)
        deployment = coordination.setdefault("arc_optimizer_deployment", {})
        deployment.setdefault("runs", {})[run_id] = {
            "source_commit": candidate["source_commit"], "submission_id": candidate["submission_id"],
            "package_sha256": candidate["package_sha256"], "manifest": relative,
            "status": result["status"], "strict_ab": False
        }
        write_coordination(coordination_path, deployment)
        head, sync = self.sync_commit(allowed, f"docs(arc): archive optimizer run {run_id}", self.state["evidence_parent"])
        previous, previous_task = None, None
        if self.state.get("last_run"):
            previous_path = self.store / "runs" / self.state["last_run"] / "summary.json"
            if previous_path.exists():
                prior = read_json(previous_path)
                previous, previous_task = prior.get("score"), prior.get("task_key")
        if previous_task != result["task_key"] or not numeric(result["score"]) or not numeric(previous) or result["score"] <= previous:
            self.state["no_improvement"] += 1
        else:
            self.state["no_improvement"] = 0
        cost = result["cost"]
        if cost and cost.get("currency") == "CNY" and numeric(cost.get("amount")):
            self.state["spent_cny"] += cost["amount"]
        else:
            # Unknown billing conservatively spends the reservation and stops.
            self.state["spent_cny"] += self.c["estimated_run_cny"]
            self.state["no_improvement"] = self.c["max_no_improvement"]
        self.state["round"] += 1
        self.state["last_run"] = run_id
        self.state["rounds"].append({"candidate": candidate, "evidence_commit": head, "sync": sync,
                                     "result": result, "finished_at": utcnow()})
        self.state["phase"] = "round_complete"
        self.save()


def normalize(status, cursor, files, candidate):
    names = {item["path"] for item in files}
    missing = [name for name in ("workspace.zip", "submission.zip") if name not in names]
    if not cursor.get("logs_drained"):
        missing.append("complete_log_pagination")
    tests = status.get("tests")
    if not isinstance(tests, list) or not tests:
        missing.append("per_test_details")
    amount, currency = status.get("token_cost_usd"), status.get("token_cost_currency")
    archive = next((item for item in files if item["path"] == "submission.zip"), None)
    closed = bool(archive and candidate.get("package_sha256") and archive["sha256"].lower() == candidate["package_sha256"].lower())
    return {
        "schema_version": 1, "run_id": status["id"], "status": str(status["status"]).upper(),
        "score": status.get("score"), "passed": status.get("passed_count"), "failed": status.get("failed_count"),
        "failure_reason": status.get("failure_reason"),
        "failed_tests": [{key: test.get(key) for key in ("name", "status", "error")}
                         for test in (tests or []) if isinstance(test, dict) and test.get("passed") is False],
        "tokens": status.get("token_count"), "duration_seconds": status.get("run_duration_seconds"),
        "cost": {"amount": amount, "currency": currency} if amount is not None else None,
        "task_key": status.get("requirement_id"), "submission_id": status.get("submission_id"),
        "source_commit": candidate.get("source_commit") if closed else None,
        "package_sha256": candidate.get("package_sha256") if closed else None,
        "candidate_identity_closed": closed, "platform_identity": "platform_identity_inconclusive",
        "hidden_suite_identity": None, "strict_ab": False,
        "logs_drained": bool(cursor.get("logs_drained")), "log_pages": len(cursor["pages"]),
        "log_next_offset": cursor["offset"], "files": files, "missing_evidence": missing,
        "collection_errors": cursor.get("errors", {}), "collected_at": utcnow()
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="external JSON config (never secrets in arguments)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    ingest = sub.add_parser("ingest", help="index external evidence without copying raw files")
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--source-dir", required=True)
    ingest.add_argument("--metadata-only", action="store_true", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    analyze = sub.add_parser("analyze", help="recompute analysis from collected state")
    analyze.add_argument("--run-id", required=True)
    plan = sub.add_parser("plan", help="compile a plan from analysis without executing it")
    plan.add_argument("--run-id", required=True)
    context = sub.add_parser("context", help="snapshot context identities from another branch")
    context.add_argument("--branch", required=True)
    reconcile = sub.add_parser("reconcile", help="reconcile external monitor reports without starting monitors")
    reconcile.add_argument("--run-id", required=True)
    sub.add_parser("approve", help="apply a reviewed codegen patch and resume commit gates")
    sub.add_parser("resume-codegen", help="preserve a stopped journal and validate a newly authorized attempt")
    sub.add_parser("step")
    loop = sub.add_parser("loop")
    loop.add_argument("--max-steps", type=int, default=10000)
    args = parser.parse_args(argv)
    try:
        ctl = Controller(read_json(args.config))
        # One lock per checkout as well as state directory; separate configs cannot bypass it.
        common = Path(ctl.git("rev-parse", "--git-path", "arc-optimizer-lock"))
        if not common.is_absolute():
            common = ctl.repo / common
        with writer_lock(common), writer_lock(ctl.store):
            if args.command == "doctor":
                output = ctl.doctor()
            elif args.command == "ingest":
                output = ctl.ingest(args.run_id, args.source_dir)
            elif args.command == "collect":
                output = ctl.collect(args.run_id)
            elif args.command == "analyze":
                output = ctl.analyze(args.run_id)
            elif args.command == "plan":
                output = ctl.plan(args.run_id)
            elif args.command == "context":
                output = ctl.context_snapshot(args.branch)
            elif args.command == "reconcile":
                output = ctl.reconcile(args.run_id)
            elif args.command == "approve":
                output = ctl.approve_candidate()
            elif args.command == "resume-codegen":
                output = ctl.resume_codegen()
            elif args.command == "step":
                output = ctl.step()
            else:
                for _ in range(args.max_steps):
                    ctl.step()
                    print(json.dumps({"phase": ctl.state["phase"], "round": ctl.state["round"],
                                      "run_id": ctl.state.get("candidate", {}).get("run_id")}), flush=True)
                    if ctl.state["phase"] == "stopped":
                        break
                    if ctl.state["phase"] in ("running", "ci_wait"):
                        time.sleep(max(5, ctl.c["poll_seconds"]))
                output = {"phase": ctl.state["phase"], "round": ctl.state["round"]}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2 if output.get("status") == "blocked" else 0
    except (GateError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
