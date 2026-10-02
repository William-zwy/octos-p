from __future__ import annotations

import json
from pathlib import Path

from arcbench_agent_runtime.context import RuntimePaths
from arcbench_agent_runtime.events import EventClient


def test_mark_implementation_ready_is_intermediate_only(tmpdir):
    root = Path(str(tmpdir))
    events_path = root / "runner-events.jsonl"
    paths = RuntimePaths(
        project_dir=root,
        runner_events_path=events_path,
        traceability_dir=root / "traceability",
    )
    EventClient(paths).mark_implementation_ready("REQ-1", "product delta retained")
    payload = json.loads(events_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["type"] == "requirement_state"
    assert payload["node_id"] == "REQ-1"
    assert payload["phase"] == "implement"
    assert payload["status"] == "ready"
