"""Structured evidence passed from acceptance runs into repair turns."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


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
        )
