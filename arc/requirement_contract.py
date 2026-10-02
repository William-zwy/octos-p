"""Compile requirement YAML into a small, evidence-backed implementation contract.

The benchmark does not always provide acceptance specs.  In that mode the model
still needs exact actions, visible names, fixture values and persistence hints,
but replaying the complete YAML tree on every turn is expensive and ambiguous.
This module deliberately extracts facts without inventing domain-specific
routes or entities; every fact retains a source pointer and confidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


ROLE_RE = re.compile(
    r"\b(button|link|textbox|heading|checkbox|radio|combobox|alert|tab|dialog|menu|row|gridcell|navigation)\b",
    re.I,
)
PATH_RE = re.compile(r"(?<![\w-])/(?:[A-Za-z0-9_:.?=&${}-]+(?:/[A-Za-z0-9_:.?=&${}-]+)*)")
QUOTED_RE = re.compile(r"(?:\"([^\"]+)\"|'([^']+)'|`([^`]+)`|“([^”]+)”|‘([^’]+)’)")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
SCOPE_RE = re.compile(
    r"\b(?:same|each|the selected|current|target|own|owned|parent|associated|corresponding|specific|independent)"
    r"[^.]{0,100}\b(?:record|item|entity|resource|question|issue|repository|branch|user|account|page|row|cell|tag|post)\b",
    re.I,
)
PERSIST_RE = re.compile(r"\b(reload|refresh|reopen|persist|persistent|saved|survive|database|store|after signing out|session)\b", re.I)
PERMISSION_RE = re.compile(r"\b(permission|permitted|authorized|privilege|role|logged in|signed in|anonymous|owner|moderator|access)\b", re.I)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _facts(text: str) -> dict[str, list[str]]:
    quoted: list[str] = []
    for match in QUOTED_RE.finditer(text):
        value = next((part for part in match.groups() if part), "").strip()
        if value and value not in quoted:
            quoted.append(value)
    for value in EMAIL_RE.findall(text):
        if value not in quoted:
            quoted.append(value)
    roles = sorted({match.group(1).lower() for match in ROLE_RE.finditer(text)})
    paths = list(dict.fromkeys(PATH_RE.findall(text)))
    scopes = list(dict.fromkeys(_text(match.group(0)) for match in SCOPE_RE.finditer(text)))
    return {
        "exact_values": quoted[:20],
        "roles": roles[:12],
        "paths": paths[:12],
        "scope_hints": scopes[:8],
        "persistence_hints": ["reload/reopen/session/persistence mentioned"] if PERSIST_RE.search(text) else [],
        "permission_hints": ["session/permission/access mentioned"] if PERMISSION_RE.search(text) else [],
    }


def _scenario_contract(node_id: str, scenario: dict, index: int) -> dict:
    name = _text(scenario.get("name") or "scenario")
    steps = [step for step in scenario.get("steps") or [] if isinstance(step, dict)]
    step_records: list[dict] = []
    all_text = " ".join([name] + [_text(step.get("content")) for step in steps])
    for step_index, step in enumerate(steps, 1):
        keyword = _text(step.get("keyword")).upper() or "STEP"
        content = _text(step.get("content"))
        if content:
            step_records.append({
                "keyword": keyword,
                "text": content[:360],
                "evidence": f"{node_id}:scenario[{index}]:step[{step_index}]",
            })
    facts = _facts(all_text)
    facts["actions"] = [step["text"] for step in step_records if step["keyword"] == "WHEN"][:6]
    facts["expected"] = [step["text"] for step in step_records if step["keyword"] == "THEN"][:6]
    facts["setup"] = [step["text"] for step in step_records if step["keyword"] == "GIVEN"][:6]
    return {
        "name": name[:180],
        "steps": step_records[:12],
        "facts": facts,
        "evidence": f"{node_id}:scenario[{index}]",
        "confidence": "high" if step_records else "medium",
    }


def compile_requirement_contract(tree: dict) -> dict:
    """Return a compact contract for all atomic nodes in document order."""
    nodes: list[dict] = []

    def walk(node: dict, parents: tuple[str, ...] = ()) -> None:
        node_id = _text(node.get("id"))
        node_type = _text(node.get("type")).upper()
        children = node.get("children") or []
        if node_id and (node_type != "FOLDER" and not children or node_type == "ATOMIC"):
            description = _text(node.get("description"))
            scenarios = [
                _scenario_contract(node_id, scenario, index)
                for index, scenario in enumerate(node.get("scenarios") or [], 1)
                if isinstance(scenario, dict)
            ]
            facts = _facts(" ".join([_text(node.get("name")), description]))
            nodes.append({
                "id": node_id,
                "name": _text(node.get("name"))[:180],
                "description": description[:420],
                "dependencies": [_text(dep) for dep in node.get("dependencies") or [] if _text(dep)],
                "parent_ids": list(parents),
                "scenario_count": len(scenarios),
                "facts": facts,
                "scenarios": scenarios,
                "evidence": f"{node_id}:description" if description else f"{node_id}:name",
                "confidence": "high" if scenarios else "medium",
            })
            return
        for child in children:
            if isinstance(child, dict):
                walk(child, parents + ((node_id,) if node_id else ()))

    walk(tree)
    capabilities_by_parent: dict[str, dict] = {}
    for item in nodes:
        # The first parent is normally the synthetic ROOT; use the first real
        # folder so the map groups an app into a small set of capabilities.
        parent_ids = item.get("parent_ids") or []
        parent_id = parent_ids[1] if len(parent_ids) > 1 else (parent_ids[0] if parent_ids else "ROOT")
        capability = capabilities_by_parent.setdefault(parent_id, {
            "id": parent_id,
            "node_ids": [],
            "node_names": [],
            "scenario_count": 0,
            "evidence": [],
            "confidence": "medium",
        })
        capability["node_ids"].append(item["id"])
        capability["node_names"].append(item.get("name") or item["id"])
        capability["scenario_count"] += item.get("scenario_count", 0)
        capability["evidence"].append(item.get("evidence"))

    invariants: list[dict] = []
    seen_invariants: set[str] = set()
    for item in nodes:
        for scenario in item.get("scenarios") or []:
            facts = scenario.get("facts") or {}
            expected = facts.get("expected") or []
            combined = " ".join(expected + facts.get("setup", []) + facts.get("actions", []))
            checks: list[tuple[str, str]] = []
            if re.search(r"\b(refresh|reload|reopen|survive|persist|saved)\b", combined, re.I):
                checks.append(("refresh_reopen", combined[:360]))
            if re.search(r"\b(atomic|partial|rollback|unchanged|not create|no .*created|failure)\b", combined, re.I):
                checks.append(("failure_atomicity", combined[:360]))
            if re.search(r"\b(initial|seed|existing|starting state|pre-populated|verified account)\b", combined, re.I):
                checks.append(("initial_seed", combined[:360]))
            for kind, quote in checks:
                key = f"{kind}:{quote.lower()}"
                if key in seen_invariants:
                    continue
                seen_invariants.add(key)
                invariants.append({"kind": kind, "quote": quote,
                                   "evidence": scenario.get("evidence"), "confidence": "high"})

    for item in nodes:
        scenarios = item.get("scenarios") or []
        exact_values: list[str] = []
        routes: list[str] = []
        roles: list[str] = []
        actions: list[str] = []
        visible: list[str] = []
        errors: list[str] = []
        refresh: list[str] = []
        evidence: list[str] = []
        for scenario in scenarios:
            facts = scenario.get("facts") or {}
            for key, target in (("exact_values", exact_values), ("paths", routes), ("roles", roles),
                                ("actions", actions), ("expected", visible)):
                for value in facts.get(key) or []:
                    if value not in target:
                        target.append(value)
            expected = facts.get("expected") or []
            for value in expected:
                if re.search(r"\b(error|invalid|fail|cannot|empty|not found|denied|reject)\b", value, re.I):
                    errors.append(value)
                if re.search(r"\b(refresh|reload|reopen|persist|survive|saved)\b", value, re.I):
                    refresh.append(value)
            if scenario.get("evidence"):
                evidence.append(scenario["evidence"])
        item["acceptance_contract"] = {
            "fixture": exact_values[:20],
            "entry_route": routes[:12],
            "role_name": roles[:12] + [value for value in exact_values if value not in roles][:12],
            "user_action": actions[:12],
            "api_mutation": [path for path in routes if "/api" in path][:12],
            "visible_result": visible[:12],
            "error_behavior": errors[:12],
            "refresh_reopen_result": refresh[:12],
            "evidence": evidence[:12],
            "confidence": "high" if scenarios else "medium",
        }
    payload = {
        "schema_version": 1,
        "source": "requirements.yaml",
        "root": {"id": _text(tree.get("id")), "name": _text(tree.get("name")),
                 "description": _text(tree.get("description"))[:420]},
        "atomic_count": len(nodes),
        "scenario_count": sum(item["scenario_count"] for item in nodes),
        "nodes": nodes,
        "capabilities": list(capabilities_by_parent.values()),
        "invariants": invariants[:80],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["contract_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return payload


def compact_contract(contract: dict, node_id: str | None = None, max_chars: int = 7000) -> str:
    """Serialize either one node or a bounded summary for a prompt."""
    nodes = contract.get("nodes") or []
    if node_id:
        selected = [node for node in nodes if str(node.get("id")) == str(node_id)]
        payload = {
            "schema_version": contract.get("schema_version", 1),
            "contract_hash": contract.get("contract_hash"),
            "node": selected[0] if selected else {"id": node_id, "confidence": "low", "evidence": "not found"},
        }
    else:
        fixture_catalog: list[str] = []
        for node in nodes:
            for value in (node.get("facts") or {}).get("exact_values") or []:
                if value not in fixture_catalog and len(value) <= 100:
                    fixture_catalog.append(value)
        signals = []
        for node in nodes:
            facts = node.get("facts") or {}
            flags = [key for key in ("roles", "paths", "scope_hints", "persistence_hints", "permission_hints")
                     if facts.get(key)]
            signals.append({"id": node.get("id"), "flags": flags})
        payload = {
            "schema_version": contract.get("schema_version", 1),
            "contract_hash": contract.get("contract_hash"),
            "atomic_count": contract.get("atomic_count", 0),
            "scenario_count": contract.get("scenario_count", 0),
            "fixture_catalog": fixture_catalog[:40],
            "capabilities": [{"id": item.get("id"), "node_ids": item.get("node_ids"),
                              "scenario_count": item.get("scenario_count"),
                              "evidence": (item.get("evidence") or [])[:4]}
                             for item in contract.get("capabilities") or []],
            "invariants": [{"kind": item.get("kind"), "quote": str(item.get("quote") or "")[:200],
                            "evidence": item.get("evidence")}
                           for item in (contract.get("invariants") or [])[:20]],
            "nodes": [
                {"id": node.get("id"), "name": node.get("name"), "dependencies": node.get("dependencies"),
                 "scenario_count": node.get("scenario_count"), "confidence": node.get("confidence")}
                for node in nodes
            ],
            "signals": signals,
        }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    if node_id and isinstance(payload.get("node"), dict):
        node = payload["node"]
        node["scenarios"] = node.get("scenarios", [])[:2]
        node["description"] = str(node.get("description") or "")[:240]
        for facts in (node.get("facts"),):
            if isinstance(facts, dict):
                facts["exact_values"] = facts.get("exact_values", [])[:10]
                facts["scope_hints"] = facts.get("scope_hints", [])[:4]
        node["steps"] = node.get("steps", [])[:4]
        if isinstance(node.get("acceptance_contract"), dict):
            node["acceptance_contract"] = {
                key: list(value)[:4] if isinstance(value, list) else value
                for key, value in node["acceptance_contract"].items()
            }
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) > max_chars:
        # Keep the result valid JSON even when a requirement contains long prose.
        node = payload.get("node")
        if isinstance(node, dict):
            node["scenarios"] = []
            node["description"] = str(node.get("description") or "")[:120]
            node["facts"] = {"exact_values": [], "roles": [], "paths": [], "scope_hints": [],
                              "persistence_hints": [], "permission_hints": []}
        if not node_id:
            payload["fixture_catalog"] = list(payload.get("fixture_catalog") or [])[:20]
            payload["nodes"] = [{"id": item.get("id"), "name": item.get("name"),
                                 "scenario_count": item.get("scenario_count"),
                                 "dependencies": item.get("dependencies") or []}
                                for item in nodes]
            payload["capabilities"] = [{"id": item.get("id"), "node_ids": item.get("node_ids") or [],
                                         "scenario_count": item.get("scenario_count")}
                                        for item in contract.get("capabilities") or []]
            payload["invariants"] = [{"kind": item.get("kind"), "evidence": item.get("evidence")}
                                     for item in (contract.get("invariants") or [])[:20]]
            payload["signals"] = [{"id": item.get("id"), "flags": item.get("flags") or []}
                                  for item in payload.get("signals") or [] if item.get("flags")]
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        payload["truncated"] = True
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= max_chars else json.dumps({"schema_version": 1, "truncated": True,
                                                            "node_id": node_id, "contract_hash": contract.get("contract_hash")},
                                                           ensure_ascii=False, separators=(",", ":"))
