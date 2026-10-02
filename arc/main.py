#!/usr/bin/env python3
"""ARC-Bench custom agent bundle: Octos as the coding agent.

The ARC-Bench platform invokes this as:

    python main.py <requirement_path> [--output-dir DIR] [--web-port N]

Flow (one requirement node at a time, dependencies first):

    skeleton turn (create mode only)
    for node in topological order:
        design turn      -> .arc/design/<node>.json + traceability contract
        implement turn   -> code
        acceptance loop  -> run the node's Playwright specs locally, feed the
                            four-field failure digest back, K <= 5 repairs,
                            commit on improvement, roll back on regression
        traceability     -> design_done / implementation_done / test_passed|failed
    startup rehearsal (build + start exactly like the grader)

Evolution mode (ARCBENCH_TEMPLATE_DIR already holds frontend/ + backend/):
skip the skeleton, diff the requirement tree against the previous run's
`.arc/traceability/requirements.json`, implement only new/changed nodes and
regression-test the unchanged ones.

Environment (all optional):
    OPENAI_API_KEY / OPENAI_BASE_URL / MODEL   OpenAI-compatible endpoint
    OCTOS_BIN                 octos binary (default: ./bin/octos, PATH, download)
    OCTOS_NODE_TIMEOUT        seconds per model turn (default 1200)
    OCTOS_TIME_BUDGET         seconds for the whole generation (default max(3600, 1500 x nodes))
    OCTOS_SECONDS_PER_NODE    per-node allowance used for that default (1500)
    OCTOS_MIN_REPAIR_SECONDS  do not start a repair turn with less than this left (300)
    OCTOS_NODE_TIME_BUDGET    cap per node incl. repairs (default 1500)
    OCTOS_REPAIR_ROUNDS       K, acceptance repair rounds per node (default 5)
    OCTOS_DESIGN_TURN         "0" disables the design turn
    OCTOS_DESIGN_MODE         inline (default) | separate (own read-only design turn)
    OCTOS_DESIGN_MIN_NODES    design only for trees with at least this many nodes (3)
    OCTOS_SKELETON_MIN_NODES  separate skeleton turn only for trees with at least this many nodes (3)
    OCTOS_SMALL_TASK_NODES    trees up to this size get the minimal self-verification text (2)
    OCTOS_VERIFY_MODE         auto (default) | minimal | full
    OCTOS_ARC_REASONING       auto (default: none for <=1 node to implement, else low) | low | medium | high | none | passthrough
    OCTOS_ARC_IMPLEMENT_REASONING  optional override for first implement turns of small tasks (default: base mode)
    OCTOS_ARC_INLINE_SPECS    "0" stops quoting the node's spec files into the prompt (default: quote up to 24k chars)
    OCTOS_ARC_DESTREAM        "0" lets streaming requests reach the platform as SSE (default: one JSON response upstream)
    OCTOS_ARC_TRIM_PROMPT     "0" keeps the kernel system prompt and all tool schemas (default: drop ARC-irrelevant sections/tools)
    OCTOS_ARC_DROP_SHELL      "0" leaves bash/shell available in minimal-verification turns (default: removed)
    OCTOS_ARC_IMPLEMENT_REQUESTS / OCTOS_ARC_REPAIR_REQUESTS  hard per-turn request caps enforced at the proxy (22 implement, 10 repair; 0 = off)
    OCTOS_ARC_CONTINUATION_REQUESTS  one same-node timeout/cap continuation (default 12, max 12)
    OCTOS_ARC_SKELETON_REQUESTS  per-turn request cap for the scaffold turn (default max(20, implement budget))
    OCTOS_ARC_REWRITE_ON_ZERO "0" disables the single full-rewrite turn when round 0 passes nothing
    OCTOS_ARC_INLINE_SOURCE_CHARS  budget for quoting the app's sources into repair/rewrite prompts (40000; 0 = off)
    OCTOS_ARC_MAX_TOKENS      minimum max_tokens the proxy enforces on chat requests (32768; kernel arc.11 sends 4096)
    OCTOS_ARC_CODEGEN         "0" disables one-request codegen turns for one-node tasks (default on)
    OCTOS_SESSION_SCOPE       turn (default) | node | run — when a fresh octos session starts
    OCTOS_ARC_INSTALL_PLAYWRIGHT  "0" never installs Playwright on the fly
    OCTOS_ARC_ALIAS_SPEC_IDS  "0" stops mirroring node states onto spec ids
    OCTOS_PERF_CONTRACT       "0" drops the performance rules from prompts
    OCTOS_GUARD               "0" logs guard findings without injecting them
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arcbench_agent_runtime import AgentRuntime  # noqa: E402
from acceptance import (  # noqa: E402
    workers_for_memory,
    AcceptanceRunner, AppServer, RunSummary, acceptance_work_dir, container_memory_limit, ensure_playwright,
    failure_summaries, find_playwright_by_search, find_playwright_root, map_specs_to_nodes,
    nodes_for_failures, playwright_candidates, playwright_version_hint, restore_tree,
    restore_worktree, snapshot_worktree, tree_digest,
)
from codegen import FORMAT_INSTRUCTIONS, dedupe_nav_links, parse_file_blocks, write_files  # noqa: E402
from guard import TurnMonitor  # noqa: E402
from llm_proxy import LlmProxy  # noqa: E402
from requirement_order import ancestors_of, node_fingerprint, topo_order  # noqa: E402
from requirement_contract import compact_contract, compile_requirement_contract  # noqa: E402
from run_controls import CheckpointStore, atomic_json_write  # noqa: E402

BUNDLE_DIR = Path(__file__).resolve().parent
_READ_CACHE: dict[str, tuple[int, int, str, str]] = {}


def _cached_text(path: Path) -> tuple[str, str] | None:
    """Read a file once per unchanged mtime/size and return text plus SHA.

    This is a harness-side guard; it does not rely on the model remembering a
    prompt rule not to reread the same source.
    """
    try:
        stat = path.stat()
        key = str(path.resolve())
        cached = _READ_CACHE.get(key)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2], cached[3]
        text = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        _READ_CACHE[key] = (stat.st_mtime_ns, stat.st_size, text, digest)
        return text, digest
    except OSError:
        return None


def log(msg: str) -> None:
    """Progress lines go to BOTH stdout and stderr (the platform truncates
    stdout on long runs but keeps stderr as a separate field)."""
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)


def requirements_digest(req_dir: Path) -> str:
    """Stable identity for resume and test-suite binding."""
    digest = hashlib.sha256()
    for path in sorted(p for p in req_dir.rglob("*") if p.is_file()):
        try:
            digest.update(str(path.relative_to(req_dir)).replace("\\", "/").encode())
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


# ---------------------------------------------------------------- postflight

def _postflight_structure_check(output_dir: Path) -> None:
    """Log the deliverable tree; lift a one-level-nested app into place."""
    tree_lines = []
    for root, dirs, files in os.walk(output_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", "__pycache__")]
        depth = Path(root).relative_to(output_dir).parts
        if len(depth) > 2:
            dirs[:] = []
            continue
        indent = "  " * len(depth)
        tree_lines.append(f"{indent}{Path(root).name}/")
        for f in sorted(files)[:8]:
            tree_lines.append(f"{indent}  {f}")
        if len(tree_lines) > 60:
            tree_lines.append("... (truncated)")
            break
    log("[postflight] workspace tree:\n" + "\n".join(tree_lines))
    backend_entry = next((output_dir / rel for rel in ("backend/server.js", "backend/src/server.js")
                          if (output_dir / rel).is_file()), None)
    if (output_dir / "frontend").is_dir() and (output_dir / "backend").is_dir() and backend_entry:
        log(f"[postflight] frontend/ and backend/ present at workspace root ({backend_entry.relative_to(output_dir)})")
        return
    for child in [p for p in output_dir.iterdir() if p.is_dir() and p.name not in (".git", ".arc", "requirements")]:
        if ((child / "frontend").is_dir() and (child / "backend").is_dir()
                and any((child / rel).is_file() for rel in ("backend/server.js", "backend/src/server.js"))):
            log(f"[postflight] app found nested at {child.name}/; lifting to root")
            for item in child.iterdir():
                dest = output_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            return
    log("[postflight] WARNING: no frontend/+backend/ found anywhere; runner will reject the template")


def _reap_stray_processes(tag: str) -> None:
    """Log memory + the fattest processes, then kill whatever the agent left
    behind (browsers it launched to run the specs itself, servers, the
    octos runtime). Cloud runs 0764e8d77c54 / e60fb3545eae (2026-09-12):
    generation finished cleanly, then the grader's Playwright process was
    SIGKILLed one second after spawning 4 workers and every test was
    reported as skipped — the container had no memory left for it."""
    me = os.getpid()
    def _run(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"<{cmd[0]} unavailable: {exc}>"
    log(f"[reap:{tag}] memory:\n" + _run(["free", "-m"]).rstrip())
    # `free` shows the host, not the container's cgroup limit — that limit
    # is what SIGKILLs the grader's 4-worker Playwright run.
    cg = []
    for f in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current",
              "/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory.events",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes",
              "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
              "/sys/fs/cgroup/memory/memory.failcnt", "/sys/fs/cgroup/pids.max"):
        try:
            cg.append(f"{f}={Path(f).read_text().strip().replace(chr(10), ' ')}")
        except OSError:
            pass
    log(f"[reap:{tag}] cgroup: " + ("; ".join(cg) or "<no cgroup files>"))
    ps = _run(["ps", "-eo", "pid,ppid,rss,etime,args", "--sort=-rss"])
    log(f"[reap:{tag}] top processes by RSS:\n"
        + "\n".join(ps.splitlines()[:20]))
    victims: list[int] = []
    for line in ps.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, args_ = int(parts[0]), parts[4]
        if pid == me or pid == os.getppid():
            continue
        low = args_.lower()
        if any(k in low for k in ("chrom", "headless_shell", "playwright",
                                  "octos serve", "node ", "npm ", "/node")):
            victims.append(pid)
    for sig in tuple(getattr(signal, s) for s in ("SIGTERM", "SIGKILL") if hasattr(signal, s)):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(2 if sig == signal.SIGTERM else 0)
    if victims:
        log(f"[reap:{tag}] killed {len(victims)} stray process(es): {victims}")
        log(f"[reap:{tag}] memory after:\n" + _run(["free", "-m"]).rstrip())
    else:
        log(f"[reap:{tag}] nothing to kill")




def _free_web_port(web_port: int) -> None:
    """Best-effort kill of whatever still listens on the app port."""
    try:
        pids = subprocess.run(["lsof", "-ti", f":{web_port}"], capture_output=True, text=True, timeout=15).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        pids = []
    if not pids:
        log(f"[postflight] port {web_port} already free")
        return
    for cmd in (["fuser", "-k", f"{web_port}/tcp"], ["sh", "-c", f"lsof -ti :{web_port} | xargs -r kill"]):
        try:
            if subprocess.run(cmd, capture_output=True, text=True, timeout=15).returncode == 0:
                log(f"[postflight] killed {len(pids)} listener(s) on port {web_port} via {cmd[0]}: {pids}")
                return
        except (OSError, subprocess.TimeoutExpired):
            continue
    log(f"[postflight] port {web_port} cleanup attempted (no tool matched)")


def _port_watchdog(web_port: int, output_dir: Path, stop: threading.Event) -> None:
    """Kill OUR processes that bind the grading port during generation (the
    runner terminates a run that serves the grading port early). Foreign
    listeners are left alone: the runner host is shared."""
    root = str(output_dir).rstrip("/")
    while not stop.is_set():
        try:
            pids = subprocess.run(["lsof", "-ti", f":{web_port}"], capture_output=True, text=True, timeout=10).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            pids = []
        for pid in pids:
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = ""
            if cwd.startswith(root):
                log(f"[watchdog] port {web_port} bound by our process {pid} (cwd={cwd}); killing")
                try:
                    os.kill(int(pid), getattr(signal, "SIGKILL", signal.SIGTERM))
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
            else:
                log(f"[watchdog] port {web_port} held by foreign process {pid} (cwd={cwd or '?'}); leaving it")
        stop.wait(5)


# ---------------------------------------------------------------- requirements

def load_requirement_tree(req_dir: Path) -> dict:
    req_file = req_dir / "requirements.yaml"
    if not req_file.exists():
        req_file = req_dir / "requirements.yml"
    data = yaml.safe_load(req_file.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "id" not in data:
        for wrapper in ("root", "requirement"):
            if isinstance(data.get(wrapper), dict):
                data = data[wrapper]
                break
    if not isinstance(data, dict) or "id" not in data:
        raise ValueError(f"invalid requirements.yaml in {req_dir}")
    return data


def describe_node(node: dict) -> str:
    lines = [f"ID: {node.get('id')}", f"Name: {node.get('name', '')}"]
    if node.get("description"):
        lines.append(f"Description: {node['description']}")
    scenarios = node.get("scenarios") or []
    if scenarios:
        lines.append("Scenarios:")
        for sc in scenarios:
            lines.append(f"  - {sc.get('name', 'scenario')}")
            for step in sc.get("steps") or []:
                if isinstance(step, dict):
                    lines.append(f"      {step.get('keyword', '')} {str(step.get('content', '')).strip()}")
    deps = node.get("dependencies") or []
    if deps:
        lines.append(f"Depends on: {', '.join(map(str, deps))}")
    return "\n".join(lines)


def requirement_outline(tree: dict, max_chars: int = 12000) -> str:
    """Compact harness-parsed requirement context for the skeleton turn.

    Requirement-only hackathon runs have no acceptance files.  Asking the
    model to rediscover the YAML tree through tools consumed most of the
    skeleton request budget in recent runs.  The harness has already parsed
    the tree, so provide a bounded outline and make the first model actions
    product writes instead of repeated filesystem reads.
    """
    lines: list[str] = []
    used = 0
    marker = "- ... remaining nodes omitted; exact node details are supplied in later turns"
    for node in topo_order(tree):
        node_id = str(node.get("id") or "")
        name = " ".join(str(node.get("name") or "").split())
        description = " ".join(str(node.get("description") or "").split())
        scenarios = [" ".join(str(sc.get("name") or "scenario").split())
                     for sc in (node.get("scenarios") or []) if isinstance(sc, dict)]
        item = f"- {node_id}: {name}"
        if description:
            item += f" — {description[:320]}"
        if scenarios:
            item += " | scenarios: " + "; ".join(scenarios[:4])
        separator = 1 if lines else 0
        if used + separator + len(item) > max_chars:
            remaining = max(0, max_chars - used - separator)
            if remaining:
                lines.append(marker[:remaining])
            break
        lines.append(item)
        used += separator + len(item)
    return "\n".join(lines)[:max_chars]


def folder_descendants(tree: dict) -> dict[str, list[str]]:
    """Non-atomic node id -> ids of its ATOMIC descendants (document order)."""
    out: dict[str, list[str]] = {}

    def walk(node: dict) -> list[str]:
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        node_type = str(node.get("type") or "").upper()
        node_id = str(node.get("id") or "")
        if node_type == "ATOMIC" or (not children and node_type != "FOLDER"):
            return [node_id]
        ids: list[str] = []
        for child in children:
            ids.extend(walk(child))
        if node_id:
            out[node_id] = ids
        return ids

    walk(tree)
    return out


def previous_requirement_records(output_dir: Path) -> dict[str, dict]:
    """The previous run's requirement table (committed with the template)."""
    path = output_dir / ".arc" / "traceability" / "requirements.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def unchanged_node_ids(nodes: list[dict], previous: dict[str, dict]) -> set[str]:
    out = set()
    for node in nodes:
        prev = previous.get(str(node.get("id")))
        if prev and node_fingerprint(prev) == node_fingerprint(node):
            out.add(str(node.get("id")))
    return out


CODEGEN_MANIFESTS = {
    # Pages are copied twice: `register.html` and extensionless `register`, so a naive static
    # server that maps /register -> dist/register still finds the page (local s5/s8 first pass: 404 -> 0/6).
    "frontend/package.json": {"name": "f", "private": True, "scripts": {"build": "node -e \"const f=require('fs');f.mkdirSync('dist',{recursive:true});for(const n of f.readdirSync('src')){f.copyFileSync('src/'+n,'dist/'+n);if(n.endsWith('.html')&&n!=='index.html')f.copyFileSync('src/'+n,'dist/'+n.slice(0,-5))}\""}},
    # "type": "commonjs" pins the loader: Node 20.19 module detection treated a server.js mixing
    # import and require as ESM (cloud 3e425ce2ebf6: "require is not defined in ES module scope").
    "backend/package.json": {"name": "b", "private": True, "type": "commonjs", "scripts": {"start": "node server.js"}},
}


def write_codegen_manifests(output_dir: Path) -> list[str]:
    """Codegen turns never emit package.json: the harness writes the two fixed
    manifests (idempotent build copying src/* to dist, start running server.js)."""
    written = []
    for rel, data in CODEGEN_MANIFESTS.items():
        path = output_dir / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        written.append(rel)
    return written


def inline_sources(output_dir: Path, max_chars: int = 40000, exts: tuple = (".js", ".mjs", ".cjs", ".html", ".css", ".json")) -> str:
    """Quote the app's source files (frontend sources, backend JS) so a repair
    turn edits immediately instead of spending its request budget on reads.
    Bounded; largest files first are skipped when they would not fit."""
    files: list[Path] = []
    for part in ("frontend", "backend"):
        base = output_dir / part
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                rel = path.relative_to(output_dir)
                if any(seg in ("node_modules", "dist", ".git", "data") for seg in rel.parts):
                    continue
                if path.is_file() and path.suffix in exts:
                    files.append(path)
    parts, total = [], 0
    for path in sorted(files, key=lambda p: p.stat().st_size):
        cached = _cached_text(path)
        if cached is None:
            continue
        text, digest = cached
        if total + len(text) > max_chars:
            parts.append(f"--- {path.relative_to(output_dir).as_posix()} --- (omitted, {len(text)} chars, sha256={digest[:12]}; "
                         "use the source-cache reference and read only if this file is in the change impact)\n")
            continue
        total += len(text)
        parts.append(f"--- {path.relative_to(output_dir).as_posix()} ---\n{text.rstrip()}\n")
    return ("Current source files (quoted; edit them directly, no need to read):\n" + "".join(parts)) if parts else ""


def source_listing(output_dir: Path, limit: int = 60) -> str:
    """Short, stable listing of the app sources for evolution prompts."""
    lines = []
    for part in ("frontend", "backend"):
        base = output_dir / part
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(output_dir)
            if any(seg in ("node_modules", "dist", ".git") for seg in rel.parts):
                continue
            if path.is_file():
                lines.append(f"{rel} ({path.stat().st_size} B)")
            if len(lines) >= limit:
                lines.append("...")
                return "\n".join(lines)
    return "\n".join(lines)


def source_fingerprint(output_dir: Path) -> str:
    """Return a compact content fingerprint for structural-gate de-duplication."""
    digest = hashlib.sha256()
    paths = list(_generated_source_files(output_dir))
    paths.extend(output_dir / rel for rel in ("frontend/package.json", "backend/package.json")
                 if (output_dir / rel).is_file())
    for path in sorted(set(paths)):
        try:
            rel = path.relative_to(output_dir).as_posix().encode("utf-8")
            payload = path.read_bytes()
        except OSError:
            continue
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def product_fingerprint(output_dir: Path) -> str:
    """Fingerprint deployable product inputs, excluding build/cache output.

    This is deliberately broader than ``source_fingerprint``: frontend assets,
    manifests and common source types are legitimate product changes. Mutable
    backend JSON, package locks, node_modules, dist and harness-owned ``.arc``
    state are not completion evidence.
    """
    digest = hashlib.sha256()
    paths: list[Path] = []
    for part in ("frontend", "backend"):
        base = output_dir / part
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(output_dir)
            if any(seg in ("node_modules", "dist", ".git") for seg in rel.parts):
                continue
            if path.name in ("package-lock.json", "npm-shrinkwrap.json"):
                continue
            # Backend JSON is normally mutable runtime state. A model-side
            # curl smoke must not turn db.json into evidence that source code
            # changed. package.json remains part of the deployable contract.
            if part == "backend" and path.suffix.lower() == ".json" and path.name != "package.json":
                continue
            paths.append(path)
    for path in sorted(set(paths)):
        try:
            rel = path.relative_to(output_dir).as_posix().encode("utf-8")
            payload = path.read_bytes()
        except OSError:
            continue
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def product_turn_incomplete_reason(wrote: bool, budget_exhausted: bool) -> str | None:
    """Return the truthful non-completion reason after a real product delta."""
    if budget_exhausted:
        return "request_budget_exhausted"
    if not wrote:
        return "untracked_product_write"
    return None


class _StaticUiParser(HTMLParser):
    """Collect only cheap, high-confidence facts from generated HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[dict] = []
        self.labels: list[dict] = []
        self.headings: list[dict] = []
        self.buttons: list[dict] = []
        self._captures: list[dict] = []
        self._form_depth = 0

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(k).lower(): str(v or "") for k, v in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = self._attrs(attrs)
        if tag == "form":
            self._form_depth += 1
        if tag in ("input", "select", "textarea"):
            if values.get("type", "").lower() != "hidden":
                self.controls.append({"tag": tag, "attrs": values, "in_form": self._form_depth > 0})
        if tag in ("label", "button", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._captures.append({"tag": tag, "attrs": values, "text": []})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for capture in self._captures:
            capture["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._captures) - 1, -1, -1):
            capture = self._captures[index]
            if capture["tag"] != tag:
                continue
            self._captures.pop(index)
            capture["text"] = " ".join("".join(capture["text"]).split())
            if tag == "label":
                self.labels.append(capture)
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.headings.append(capture)
            elif tag == "button":
                self.buttons.append(capture)
            break
        if tag == "form":
            self._form_depth = max(0, self._form_depth - 1)


def _generated_source_files(output_dir: Path) -> list[Path]:
    files: list[Path] = []
    for part in ("frontend/src", "backend"):
        base = output_dir / part
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any(p in ("node_modules", "dist", "data") for p in path.parts):
                continue
            if path.suffix.lower() in (".html", ".js", ".mjs", ".cjs", ".css"):
                files.append(path)
    return files


def structural_self_check(output_dir: Path, design: dict | None = None,
                          requirement_text: str = "") -> list[str]:
    """Return actionable static contract findings without running the app.

    This is intentionally advisory: acceptance tests remain the verdict. The
    check catches omissions that repeatedly waste a repair turn while leaving
    dynamic/template-heavy implementations to Playwright.
    """
    issues: list[str] = []
    required = ("frontend/package.json", "backend/package.json")
    for rel in required:
        if not (output_dir / rel).is_file():
            issues.append(f"missing generated file {rel}; create the required app file before repairing UI")
    backend_entry = next((output_dir / rel for rel in ("backend/server.js", "backend/src/server.js")
                          if (output_dir / rel).is_file()), None)
    if backend_entry is None:
        issues.append("missing backend entry (backend/server.js or backend/src/server.js); create the app entry before repairing UI")
    if not any((output_dir / rel).is_file() for rel in ("frontend/src/index.html", "frontend/index.html")):
        issues.append("missing generated file frontend/index.html or frontend/src/index.html; create the app entry before repairing UI")
    for rel, script, command in (("frontend/package.json", "build", "build"),
                                 ("backend/package.json", "start", "start")):
        path = output_dir / rel
        if not path.is_file():
            continue
        try:
            package = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{rel} is not valid JSON ({exc}); restore the generated manifest")
            continue
        if not isinstance(package.get("scripts"), dict) or not package["scripts"].get(script):
            issues.append(f"{rel} lacks scripts.{script}; keep the required {command} command wired")

    source_paths = _generated_source_files(output_dir)
    source_text: dict[Path, str] = {}
    for path in source_paths:
        try:
            source_text[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    all_source = "\n".join(source_text.values())
    script_source = "\n".join(
        text for path, text in source_text.items()
        if path.suffix.lower() in (".js", ".mjs", ".cjs")
    )
    server_path = backend_entry or (output_dir / "backend" / "server.js")
    server_text = source_text.get(server_path, "")
    html_paths = [p for p in source_paths if p.suffix.lower() == ".html"]
    designs = design if isinstance(design, dict) else {}

    for path in html_paths:
        parser = _StaticUiParser()
        try:
            parser.feed(source_text[path])
        except Exception as exc:  # HTMLParser is best-effort by design.
            log(f"[structural] could not parse {path.name}: {exc}")
            continue
        rel = path.relative_to(output_dir).as_posix()
        controls_by_id: dict[str, int] = {}
        for control in parser.controls:
            control_id = control["attrs"].get("id", "")
            if not control_id:
                issues.append(f"{rel} has a visible {control['tag']} without id/label wiring; add a unique id and <label for=...>")
                continue
            controls_by_id[control_id] = controls_by_id.get(control_id, 0) + 1
            label_count = sum(1 for label in parser.labels if label["attrs"].get("for") == control_id)
            if label_count != 1:
                issues.append(f"{rel} control #{control_id} has {label_count} explicit labels; add exactly one visible <label for=\"{control_id}\">")
        for control_id, count in controls_by_id.items():
            if count > 1:
                issues.append(f"{rel} repeats control id #{control_id}; keep label/control relationships unique")
        heading_counts: dict[str, int] = {}
        for heading in parser.headings:
            text = str(heading["text"]).strip()
            if text:
                heading_counts[text.casefold()] = heading_counts.get(text.casefold(), 0) + 1
        for text, count in heading_counts.items():
            if count > 1:
                issues.append(f"{rel} renders heading {text!r} {count} times; keep the success/runtime heading unique")
        for button in parser.buttons:
            button_id = button["attrs"].get("id", "")
            attrs = button["attrs"]
            if attrs.get("onclick") or attrs.get("type", "").lower() == "submit":
                continue
            label = button["text"] or attrs.get("aria-label", "")
            if button_id:
                escaped = re.escape(button_id)
                handler = re.search(
                    rf"(?:getElementById\s*\(\s*['\"]{escaped}['\"]\s*\)|querySelector\s*\(\s*['\"]#?{escaped}['\"]\s*\))"
                    rf".{{0,320}}(?:addEventListener|\.onclick)", script_source, re.S)
                if not handler:
                    issues.append(f"{rel} button #{button_id} ({label!r}) has no explicit handler; wire its action to the page flow")
            for attr_name in attrs:
                if not attr_name.startswith("data-") or attr_name in ("data-testid", "data-test-id"):
                    continue
                if attr_name not in script_source:
                    issues.append(f"{rel} button [{attr_name}] ({label!r}) has no delegated handler; connect the data action in the page script")

    for route in designs.get("routes") or []:
        if not isinstance(route, dict):
            continue
        method = str(route.get("method") or "GET").upper()
        path = str(route.get("path") or "")
        if not path:
            continue
        if path.startswith("/api/") and path not in server_text:
            issues.append(f"declared route {method} {path} is absent from backend/server.js; add it to the main dispatcher")
        elif path not in all_source:
            issues.append(f"declared route {method} {path} is not referenced by generated files; connect the UI action and route")
        elif path in server_text and not re.search(r"req\.method|req\.url|pathname|router|routes|switch\s*\(", server_text, re.I):
            issues.append(f"declared route {method} {path} has no visible request-dispatch branch; register the route in the main handler")

    for page in designs.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for element in page.get("elements") or []:
            if not isinstance(element, dict):
                continue
            role = str(element.get("role") or "").lower()
            name = str(element.get("name") or "").strip()
            if role not in ("button", "link", "heading") or not name or len(name) > 100:
                continue
            if name.casefold() not in all_source.casefold():
                issues.append(f"declared {role} {name!r} is missing from generated source; render the required accessible action")

    requirement_lower = requirement_text.casefold()
    if "favorite" in requirement_lower:
        favorite_buttons = re.findall(r"<button\b([^>]*)>(.*?)</button>", all_source, re.I | re.S)
        for attrs, text in favorite_buttons:
            if re.search(r"favorite", re.sub(r"<[^>]+>", "", text), re.I) and "aria-pressed" not in attrs.lower():
                issues.append("Favorite/Unfavorite button lacks aria-pressed; derive initial state from data and update the attribute on click")
    if "book tags" in all_source.casefold() and "classlist.toggle" in all_source.casefold():
        issues.append("Book Tags disclosure uses unconditional classList.toggle; use explicit show/hide state and keep its input editable")

    # Preserve order while avoiding repeated findings from multiple pages.
    return list(dict.fromkeys(issues))


# ---------------------------------------------------------------- octos driver

OCTOS_RELEASE_URL = (
    "https://github.com/octos-org/octos-arc/releases/download/v2.0.3-rc.11-arc.11/"
    "octos-bundle-x86_64-unknown-linux-gnu.tar.gz"
)


def _download_octos(dest_dir: Path) -> str:
    """Fetch the Linux octos binary at runtime via gh-proxy mirrors first (the
    runner's path to GitHub stalls / kills HTTP/2 streams)."""
    import tarfile
    import urllib.request

    dest_dir.mkdir(parents=True, exist_ok=True)
    tarball = dest_dir / "octos-bundle.tar.gz"
    url = os.environ.get("OCTOS_RELEASE_URL", OCTOS_RELEASE_URL)

    def tarball_ok() -> bool:
        try:
            with tarfile.open(tarball) as tf:
                return tf.getmember("octos") is not None
        except Exception:  # noqa: BLE001
            return False

    ok = tarball_ok()
    mirrors = [f"{prefix}/{url}" for prefix in ("https://ghfast.top", "https://gh-proxy.com")] + [url]
    for attempt in range(1, 13):
        if ok:
            break
        mirror = mirrors[(attempt - 1) % len(mirrors)]
        log(f"[octos] download attempt {attempt} ({mirror}) ...")
        if shutil.which("curl"):
            try:
                subprocess.run(["curl", "-fsSL", "--http1.1", "-C", "-", "--connect-timeout", "30",
                                "--speed-limit", "10240", "--speed-time", "60", "--retry", "2",
                                "-o", str(tarball), mirror], check=False, timeout=600)
            except subprocess.TimeoutExpired:
                log(f"[octos] attempt {attempt} killed after 600s stall; rotating mirror")
        else:
            try:
                urllib.request.urlretrieve(mirror, tarball)
            except Exception as exc:  # noqa: BLE001
                log(f"[octos] download error: {exc}")
        ok = tarball_ok()
    if not ok:
        raise RuntimeError("failed to download octos binary after 12 attempts")
    with tarfile.open(tarball) as tf:
        for member in ("octos", "octos-sandbox"):
            try:
                tf.extract(member, dest_dir, filter="data")
            except KeyError:
                pass
    binary = dest_dir / "octos"
    binary.chmod(0o755)
    if (dest_dir / "octos-sandbox").exists():
        (dest_dir / "octos-sandbox").chmod(0o755)
    return str(binary)


def find_octos() -> str:
    env_bin = os.environ.get("OCTOS_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin
    bundled = BUNDLE_DIR / "bin" / "octos"
    if bundled.exists():
        return str(bundled)
    found = shutil.which("octos")
    if found:
        return found
    cache_dir = Path(os.environ.get("OCTOS_CACHE_DIR", "/tmp/octos-bin"))
    if (cache_dir / "octos").exists():
        return str(cache_dir / "octos")
    return _download_octos(cache_dir)


def protected_hooks(protected_dirs: list[Path] | None) -> list[dict]:
    """before_tool_call hook denying file writes into the official tests /
    requirements directories (exit 1 = deny). Shell commands are redacted by
    the kernel and cannot be checked here; the harness restores the trees
    after every turn as the second layer."""
    hook_script = BUNDLE_DIR / "hooks" / "deny_protected.py"
    if not protected_dirs or not hook_script.is_file():
        return []
    return [{
        "event": "before_tool_call",
        "command": [sys.executable, str(hook_script), *[str(p) for p in protected_dirs]],
        "timeout_ms": 4000,
        "tool_filter": ["write_file", "edit_file", "diff_edit", "apply_patch", "create_file", "append_file"],
    }]


def write_profile_defaults(data_dir: Path, config_dir: Path, hooks: list[dict]) -> None:
    """Belt and braces: the solo ProfileRuntime builds its HookExecutor from
    the profile's own config (the stdio driver patches `hooks` into the
    profile registry file — the mechanism verified to deny with a real turn);
    a `profile-defaults.json` covers code paths that merge store defaults."""
    if not hooks:
        return
    for root in (data_dir, config_dir):
        try:
            root.mkdir(parents=True, exist_ok=True)
            (root / "profile-defaults.json").write_text(json.dumps({"hooks": hooks}, indent=2), encoding="utf-8")
        except OSError:
            pass


def stage_bundled_skills(data_dir: Path, bundle_dir: Path | None = None) -> Path | None:
    """Install the bundled read-only context skill into this disposable run.

    ZIP extractors do not reliably preserve executable bits. Stage the skill
    into the per-run profile and assert its launcher is executable on Unix.
    The skill is only an optimisation: staging failure never weakens runtime
    quota, checkpoint, or acceptance enforcement.
    """
    source_root = (bundle_dir or BUNDLE_DIR) / "skills" / "arc-project-context"
    required = ("SKILL.md", "manifest.json", "index.js", "main")
    if not source_root.is_dir() or any(not (source_root / name).is_file() for name in required):
        return None
    target_root = data_dir / "skills"
    target = target_root / "arc-project-context"
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name in required:
            shutil.copy2(source_root / name, target / name)
        launcher = target / "main"
        launcher.chmod(launcher.stat().st_mode | 0o111)
        log(f"[skills] staged arc-project-context at {target}")
        return target_root
    except OSError as exc:
        log(f"[skills] arc-project-context unavailable: {exc}")
        return None


def build_octos_env(config_dir: Path, protected_dirs: list[Path] | None = None,
                    data_dir: Path | None = None) -> dict:
    """Prepare env + minimal config.json for non-interactive octos.

    `protected_dirs` (official tests, requirements) get a before_tool_call
    hook that denies write_file/edit_file into them (exit 1 = deny)."""
    env = os.environ.copy()
    api_key = env.get("OPENAI_API_KEY", "")
    base_url = env.get("OPENAI_BASE_URL", "")
    model = os.environ.get("OCTOS_MODEL") or env.get("MODEL", "")
    provider = os.environ.get("OCTOS_PROVIDER")
    if not provider:
        provider = "deepseek" if "deepseek" in base_url else "anthropic" if "anthropic" in base_url else "openai"
    key_env = "OPENAI_API_KEY"
    if provider == "deepseek" and api_key:
        env.setdefault("DEEPSEEK_API_KEY", api_key)
        key_env = "DEEPSEEK_API_KEY"
    elif provider == "anthropic" and api_key:
        env.setdefault("ANTHROPIC_API_KEY", api_key)
        key_env = "ANTHROPIC_API_KEY"
    elif provider not in ("openai", "deepseek", "anthropic") and api_key:
        env.setdefault(f"{provider.upper()}_API_KEY", api_key)
        key_env = f"{provider.upper()}_API_KEY"
    config = {
        "provider": provider,
        "model": model,
        "sandbox": {"allow_network": True},
        "memory": {"refresh": {"enabled": False}},
        # deepseek-v4 spends its default 4096 output budget on reasoning and
        # returns empty content; give it real headroom.
        "gateway": {"max_output_tokens": 65536},
    }
    if provider not in ("openai", "deepseek", "anthropic") and base_url:
        config["base_url"] = base_url
    if provider == "deepseek":
        config["gateway"]["reasoning_effort"] = "low"
    hooks = protected_hooks(protected_dirs)
    if hooks:
        config["hooks"] = hooks
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    env["OCTOS_CONFIG_DIR"] = str(config_dir)
    if data_dir is not None:
        skills_root = stage_bundled_skills(data_dir)
        if skills_root is not None:
            current = env.get("OCTOS_SKILLS_PATH", "").strip()
            env["OCTOS_SKILLS_PATH"] = (
                str(skills_root) if not current else str(skills_root) + os.pathsep + current
            )
    env.setdefault("OCTOS_DISABLE_STREAMING", "1")   # platform proxies reject SSE
    env.setdefault("OCTOS_DANGER_FULL_ACCESS", "1")  # the container is the sandbox
    env.setdefault("npm_config_registry", "https://registry.npmmirror.com")
    env.setdefault("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com")
    rules_file = BUNDLE_DIR / "EXTRA_RULES.md"
    if rules_file.is_file() and "OCTOS_ARC_EXTRA_RULES" not in env:
        env["OCTOS_ARC_EXTRA_RULES"] = rules_file.read_text(encoding="utf-8")[:8000]
    env["_ARC_PROVIDER"] = provider
    env["_ARC_MODEL"] = model
    env["_ARC_BASE_URL"] = base_url
    env["_ARC_KEY_ENV"] = key_env
    return env


_CHAT_FLAGS_CACHE: dict[str, set[str]] = {}


def _chat_supported_flags(octos_bin: str) -> set[str]:
    if octos_bin not in _CHAT_FLAGS_CACHE:
        try:
            proc = subprocess.run([octos_bin, "chat", "--help"], capture_output=True, text=True, timeout=30)
            help_text = (proc.stdout or "") + (proc.stderr or "")
        except Exception:  # noqa: BLE001
            help_text = ""
        _CHAT_FLAGS_CACHE[octos_bin] = {
            flag for flag in ("--json", "--cwd", "--data-dir", "--sandbox", "--profile",
                              "--max-iterations", "--no-session-persistence") if flag in help_text}
    return _CHAT_FLAGS_CACHE[octos_bin]


def run_octos(octos_bin: str, cwd: Path, prompt: str, env: dict, data_dir: Path,
              timeout: int, max_iterations: int) -> tuple[bool, str]:
    """One non-interactive `octos chat` turn (fallback driver)."""
    flags = _chat_supported_flags(octos_bin)
    cmd = [octos_bin, "chat", "-m", prompt]
    if "--json" in flags:
        cmd.append("--json")
    if "--cwd" in flags:
        cmd += ["--cwd", str(cwd)]
    if "--data-dir" in flags:
        cmd += ["--data-dir", str(data_dir)]
    if "--max-iterations" in flags:
        cmd += ["--max-iterations", str(max_iterations)]
    if "--no-session-persistence" in flags:
        cmd.append("--no-session-persistence")
    if "--sandbox" in flags and env.get("OCTOS_DANGER_FULL_ACCESS") == "1":
        cmd += ["--sandbox", "danger-full-access"]
    if "--profile" in flags:
        cmd += ["--profile", os.environ.get("OCTOS_CHAT_PROFILE", "coding")]
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, f"octos timed out after {timeout}s"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, f"octos exited {proc.returncode}: {out or (proc.stderr or '').strip()[-2000:]}"
    try:
        payload = json.loads(out)
        if isinstance(payload, dict) and payload.get("error"):
            return False, str(payload["error"])
        return True, str(payload.get("text", "")) if isinstance(payload, dict) else out
    except json.JSONDecodeError:
        return True, out[-4000:]


class OctosDriver:
    """stdio UI-protocol session (default) or one-shot chat turns.

    By default every turn gets a fresh session: the per-turn prompt already
    carries all the state the model needs, and a short, byte-stable prefix
    (system prompt + tool schemas) is what the provider's prefix cache keys on.
    """

    def __init__(self, octos_bin: str, cwd: Path, env: dict, data_dir: Path,
                 max_iterations: int, events_log: Path) -> None:
        self.mode = os.environ.get("OCTOS_DRIVER", "stdio")
        # "turn": new session every turn; "node": one session per requirement
        # node (design -> implement -> repairs share context); "run": one session.
        # Default "turn" since specs are quoted into every prompt: a repair turn
        # is self-contained, while a shared node session made each repair
        # request carry the whole implement history (v8-tb: 49 requests, 1.1M
        # prompt tokens for 7 repairs).
        self.session_scope = os.environ.get("OCTOS_SESSION_SCOPE", "turn")
        if os.environ.get("OCTOS_SESSION_PER_TURN") == "0" and "OCTOS_SESSION_SCOPE" not in os.environ:
            self.session_scope = "run"
        self.octos_bin = octos_bin
        self.cwd = cwd
        self.env = env
        self.data_dir = data_dir
        self.max_iterations = max_iterations
        self.events_log = events_log
        self._session = None
        self.monitor: TurnMonitor | None = None
        self.hooks: list = []  # profile hooks (protected-directory deny), set by the flow

    def _log_event(self, method: str, params: dict) -> None:
        if method == "core/marker":
            log(f"[core-mod] {params.get('line', '')}")
        if self.monitor is not None and method in ("tool/started", "tool/completed"):
            try:
                self.monitor.observe(method, params)
            except Exception:  # noqa: BLE001 - guard must never break a turn
                pass
        try:
            with self.events_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"method": method, "params": params}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _get_session(self):
        if self._session is None:
            from octos_stdio import OctosStdioSession
            self._session = OctosStdioSession(self.octos_bin, self.cwd, self.env, self.data_dir,
                                              on_event=self._log_event)
            self._session.bootstrap_profile(
                provider=self.env.get("_ARC_PROVIDER", "openai"),
                model=self.env.get("_ARC_MODEL", ""),
                base_url=self.env.get("_ARC_BASE_URL") or None,
                api_key_env=self.env.get("_ARC_KEY_ENV") or None,
                hooks=self.hooks,
            )
            self._session.open()
        return self._session

    def run(self, prompt: str, timeout: int, monitor: TurnMonitor | None = None) -> tuple[bool, str]:
        self.monitor = monitor
        if self.mode == "chat":
            fn = lambda: run_octos(self.octos_bin, self.cwd, prompt, self.env, self.data_dir,  # noqa: E731
                                   timeout, self.max_iterations)
        else:
            fn = lambda: self._run_stdio(prompt, timeout)  # noqa: E731
        try:
            ok, text = self._run_with_heartbeat(lambda: self._run_with_retries(fn))
        finally:
            self.monitor = None
            if self.session_scope == "turn":
                self.close()
        if monitor is not None:
            monitor.finish(text)
        return ok, text

    @staticmethod
    def _run_with_heartbeat(fn) -> tuple[bool, str]:
        """Run a turn in a thread, logging a keepalive every 30s (the runner
        kills silent processes)."""
        box: dict = {}

        def target() -> None:
            try:
                box["r"] = fn()
            except Exception as exc:  # pragma: no cover - defensive
                box["r"] = (False, f"turn raised: {exc}"[:500])

        th = threading.Thread(target=target, daemon=True)
        th.start()
        t0 = time.time()
        while True:
            th.join(30)
            if not th.is_alive():
                break
            log(f"[flow] turn still running ({int(time.time() - t0)}s elapsed)")
        return box.get("r", (False, "turn thread ended without result"))

    @staticmethod
    def _transient(text: str) -> bool:
        lowered = text.lower()
        if "octos turn timed out" in lowered or "octos timed out after" in lowered:
            return False  # our own wall-clock cap, not a provider hiccup: never replay the turn
        if "402" in lowered or "insufficient_balance" in lowered or "quota_gated" in lowered \
                or "insufficient balance" in lowered:
            return False  # billing failures are terminal for this run, never retry them
        return any(k in lowered for k in (
            "temporarily unavailable", "503", "502", "429", "rate limit", "timeout", "timed out",
            "connection reset", "overloaded", "failed to send", "streaming request",
            "403", "authentication failed", "401", "unauthorized"))

    def _run_with_retries(self, fn, attempts: int = 3) -> tuple[bool, str]:
        ok, text = fn()
        for attempt in range(2, attempts + 1):
            if ok or not self._transient(text):
                break
            wait = 30 * (attempt - 1)
            log(f"[driver] transient error, retry {attempt}/{attempts} after {wait}s: {text[:200]}")
            time.sleep(wait)
            self.close()
            ok, text = fn()
        return ok, text

    def _run_stdio(self, prompt: str, timeout: int) -> tuple[bool, str]:
        try:
            return self._get_session().run_turn(prompt, timeout=float(timeout))
        except Exception as exc:  # noqa: BLE001
            self.close()
            chat_ok, chat_text = run_octos(self.octos_bin, self.cwd, prompt, self.env, self.data_dir,
                                           timeout, self.max_iterations)
            if chat_ok:
                return True, chat_text
            return False, f"stdio driver error: {exc}; chat fallback: {chat_text}"[:1000]

    def end_scope(self, scope: str) -> None:
        """Called by the flow at node boundaries; closes the session when the
        configured scope ends."""
        if scope == self.session_scope or self.session_scope == "turn":
            self.close()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


# ---------------------------------------------------------------- prompts
#
# Prompt text is deliberately static (no timestamps, fixed section order) so
# that identical turns share the provider's prefix cache.

CREATE_RESULT_CONTRACT = """\
- Only for create/save flows with a named entity: after a successful 2xx response and persistence, render the exact entity name in one visible semantic heading on the stable destination. Preserve navigation with a link inside that heading, e.g. <h2><a href="...">name</a></h2>, using the existing destination and appropriate heading level. Do not duplicate the name in a separate success title, link or toast. On failure, keep the form and error feedback; show no success heading. Other interactions retain their existing semantics.
"""

WORKFLOW_STATE_CONTRACT = """\
- Scenario state: when an acceptance flow starts from an existing named record or parent/context, initialize it in the required pre-action state. Do not pre-create an entity the flow is meant to create, or leave same-name duplicates that make first-match selection ambiguous. Preserve normal persistence; do not clear shared data to imitate a fresh seed.
- Draft authoring: only when required by the scenario, keep draft-save distinct from the existing publish/save action and available from the editor the flow enters. If the flow explicitly requires an edit step on a draft detail view, expose that action there and enter edit mode only when invoked.
- Auxiliary editor properties: when a scenario opens property controls from an item's editor, keep those controls in that editor's accessible scope (prefer a fieldset, region, or disclosure panel over a second dialog). Keep the editor open, preserve unsaved content, and restore focus when the auxiliary panel closes.
- Filtered views: preserve the selected filter through rendering or navigation within that view; clear it only on an explicit action that leaves or resets the filter.
- Authentication navigation: if sign-in redirects, use one navigation owner; do not schedule a competing same-destination redirect after another navigation may have begun.
"""

UI_CONTRACT_CORE = """\
UI contract (the hidden Playwright tests depend on these; a violation scores 0):
- Buttons are real <button> elements, links are <a href>, every form control has a visible <label for=id>; their texts are copied VERBATIM from the requirement/spec (anchored regexes like /^name$/i reject "Full Name"). Use plain text/password/email inputs, native <select>/checkbox/radio; NEVER type="date"/"number". All controls exist in the served HTML itself and stay visible, enabled and editable at all times; no CSS transitions/animations and no JavaScript that re-renders or re-creates form controls after load (Playwright waits for elements to be "stable" — cloud run 954a231a3d23 timed out on a checkbox that kept changing).
- Sort controls: when a test locates sorting with getByRole('button'), implement each sorting action as a real native <button>, never a <select> or a select styled to look like a button. For the name sort control, its accessible name must be exactly `Alphabetical/Name` (use visible text or aria-label as appropriate), it must remain keyboard-focusable/activatable, and each activation must preserve the required ascending/descending sort toggle. Do not add a second control with the same accessible name.
- Comments sections: do not put `Comment` or `Comments` in the section's aria-label or other landmark accessible name when the test uses getByLabel(/Comment/i).first(); otherwise the section can be captured before the editor. Give the actual comment textarea one unique, explicit label containing `Comment` (for example `<label for="comment-input">Comment</label><textarea id="comment-input">`), and keep the section heading/region separately named without the word Comment. The first matching `getByLabel(/Comment/i)` must therefore be the textarea, which remains keyboard-editable.
- Authentication: after a successful login, render the runtime nickname returned by the session verbatim in exactly one visible semantic heading. Never replace it with a hard-coded example/placeholder nickname and never expose a duplicate accessible copy of that heading.
- Actions and routes: every declared UI action has an explicit reachable handler (button/form/link), and every mutating action has a backend route that is registered in the main request dispatcher. Do not leave a named route function or an Edit/Delete/Confirm button disconnected from the page flow.
- Disclosure controls: model show/hide as explicit state (`show`/`hide` or equivalent), not unconditional toggle inversion. After a disclosure such as a tags section is opened, its target input remains stably visible and editable.
- Detail and draft pages: render each requirement-mandated Edit, Delete, Confirm, or equivalent action on the detail/draft page where the test starts; an API or action on another page is not a substitute.
- Authenticated dashboard: provide stable accessible headings/links for dashboard entry points, including recently updated content, in the initial authenticated page HTML; do not require a late fetch just to expose the entry.
- Favorites: initialize the Favorite/Unfavorite control from the actual persisted item state and update it on click with matching text and `aria-pressed="true"|"false"`. Do not hard-code a particular fixture/seed name to decide the state.
- No native HTML5 validation attributes; validate in JavaScript and show ONE inline error element (role="alert") naming the problem (required / invalid / match / terms / duplicate). On error stay on the page and create no record.
- Strict mode: every echoed value (username, city, date) appears in EXACTLY ONE element per page; every link target appears in EXACTLY ONE <a> per page (one "Register" link, one "Login" link — never a nav link plus a call-to-action to the same href; the specs click `a[href="/register"]` and fail on two matches); never both a short and a long form of one entity, never a per-field error plus a summary. Serve a SEPARATE HTML document per route (`/`, `/register`, `/login`, ...) — never several forms in one document with hidden views: hidden inputs and labels still collide in getByLabel/getByRole.
- State: persist ONLY what the requirement says is persisted and reproduce that seed on EVERY fresh start; a page's initial state (e.g. "the count is initially 0") is per-page-load client state, never a shared server value — the grader runs several test files in parallel against ONE server. The initial state must already be in the served HTML (e.g. the element contains `0` in the markup); never leave it empty until a fetch completes — the tests assert immediately after load.
- Zero external requests (no CDN, fonts, analytics); assets small and same-origin.
- Live indicators (password-strength meters, counters, previews) update their OWN element's text/attributes synchronously in the `input` event handler — never on change/blur, never debounced, never only a wrapper's class (specs compare the element's outerHTML before and after typing).
- Text only: never OCR reference images. Write files in your first actions.
""" + CREATE_RESULT_CONTRACT + WORKFLOW_STATE_CONTRACT

CODEGEN_SYSTEM = "You write complete, minimal web apps. Reply only with file blocks in the requested format."

CODEGEN_PROMPT = """\
Requirement {node_id}: {description}

Acceptance test (ground truth):
{spec}
Files: frontend/src/index.html (+ one html per further route); backend/server.js = CommonJS (require) Node http server on process.env.PORT||{port} serving ../frontend/dist files (index.html for /, <name>.html for /<name>) plus any API routes the requirement needs (in-memory state), 404 for anything else, wrapped in try/catch and process.on('uncaughtException').{ports} Both package.json files already exist (build copies src/* to dist; start runs server.js): do not output them.
Rules: texts, button names, labels and test ids exactly as in the test; the initial state is literally in the HTML; state lives in the page script unless the requirement says it is persisted; no external resources, no CSS, no comments, no notes; Playwright strict mode: every locator in the test must match exactly one element on the served page (no duplicate links, labels, texts or ids; each label's for= resolves to its own control). {size_rule}
""" + UI_CONTRACT_CORE

CODEGEN_SIZE_SMALL = "index.html <= 20 lines, server.js <= 20 lines."
CODEGEN_SIZE_FULL = ("As short as the tests allow; one page file per route. Mechanisms (follow exactly): "
                     "(1) every page contains the literal `<!--NAV-->` and no other navigation links; the server replaces it "
                     "with `<a href=\"/login\">登录</a> <a href=\"/register\">Register</a>` when signed out or "
                     "`<span>USERNAME</span> <a href=\"/logout\">退出登录</a>` when signed in (read from the cookie) before sending. "
                     "(2) Session cookie exactly `session=TOKEN; Path=/; HttpOnly; SameSite=Lax`; sign-out clears it and redirects to /. "
                     "(3) Validation: the values produced by the test helpers (see the support file) are valid input and MUST be "
                     "accepted (names with spaces, any document number, phone, email the helper uses); reject only the cases the "
                     "tests assert are rejected; each message is the FIRST alternative of the test's regex copied verbatim, shown in one persistent `role=alert` element. "
                     "(4) Elements the test expects visible have a non-empty box (never an empty div/span). "
                     "(5) No HTML5 validation attributes (required/pattern/type=email): the server validates.")

UI_CONTRACT_DATA = """\
- Concrete example values in the requirement (seed records, option labels, sample accounts, nationalities, seat classes) are FIXTURE DATA: they must exist verbatim as <option>s / seed rows. When a control's values are described but not listed, offer a broad standard set.
- If a scenario opens a named existing record or context before acting, seed that required starting record once with the specified initial state; distinguish it from records created by the scenario and never use a post-test snapshot as the initial seed.
"""

UI_CONTRACT_SESSION = """\
- Sessions: after register/login navigate to `/`, show the exact username in one element and a "Sign out" link; the session survives reload. Failed login/registration shows one generic error, keeps the anonymous header, creates nothing.
"""

UI_CONTRACT = UI_CONTRACT_CORE + UI_CONTRACT_DATA + UI_CONTRACT_SESSION  # full set (multi-node tasks)

PERFORMANCE_CONTRACT = """\
Performance & robustness (the grader is a slow container, tests run in parallel, EACH TEST HAS A 10 s BUDGET including reloads):
- The grader CPU is 5–10x slower than a laptop and runs 4 browsers at once, so budget CPU per request at 30 ms: hash passwords with crypto.scryptSync(password, salt, 64, {N: 4096, r: 8, p: 1}) or pbkdf2Sync with <= 10000 iterations — never the default scrypt cost, never bcrypt; keep the JSON store small and rewrite it only on mutation.
- Session cookie: HttpOnly; Path=/; SameSite=Lax; Max-Age at least 7 days; NO `Secure`, NO `Domain` attribute (tests run on http://127.0.0.1). Render every page server-side from the cookie (signed-in header, username) so a page needs NO XHR after load; keep pages tiny (one small inline script, no separate JS bundles) — the grader's browsers are slow and memory-starved.
- Persistence: the in-memory store is the single source of truth; never re-read the JSON file per request. Mutations update memory first and then write the whole file synchronously (writeFileSync to a temp file, then rename) — never an async read-modify-write, because the grader runs 2–4 test files in parallel against ONE backend and a concurrent register/login pair must never lose a user. No setTimeout delays, polling, service workers, beforeunload handlers, or debounced writes.
"""

ARCHITECTURE_CONTRACT = """\
Architecture (the runner depends on this EXACT layout; violation = 0 score):
- frontend/ — package.json with a working `npm run build` that produces frontend/dist/ (a plain HTML/CSS/JS app plus a tiny Node copy script is ideal; no TypeScript, no framework needed).
- backend/  — Node.js, package.json with `npm run start`, ZERO npm dependencies: `http.createServer` + a hand-written router, `fs`, `path`, `url`, `crypto` only. It reads PORT (default {port}), serves frontend/dist/ at `/` and JSON APIs under /api/. Persistence is a JSON file (backend/data/db.json) loaded at startup and rewritten on every mutation. Never better-sqlite3/sqlite3/bcrypt or any native module.
- SINGLE ORIGIN (violation = 0 score): the SAME backend process serves BOTH the HTML/CSS/JS at `/` AND the JSON APIs under `/api/` on ONE port. There is no separate frontend dev server. The frontend MUST call the API with SAME-ORIGIN RELATIVE paths only — `fetch('/api/...')`. NEVER hardcode an absolute origin like `http://127.0.0.1:3001` or `http://localhost:<port>` or any `API_BASE`/host:port constant in the frontend: the grader loads the page from its own host/port and an absolute URL points the browser at a port that does not exist there, so every request fails and every test fails. If you need a base, use the empty string or a relative path, never a host or port.
- Crash safety: the process must never exit on a request. Wrap every request handler in try/catch (respond 500 JSON), return 404 for unknown paths and missing static files (browsers request /favicon.ico — an unhandled ENOENT there kills the server and fails every test), and register process.on('uncaughtException') / process.on('unhandledRejection') handlers that log and keep serving.
- If a package is truly unavoidable, install it only with `npm install --registry=https://registry.npmmirror.com <pkg>` and write `registry=https://registry.npmmirror.com` into that folder's .npmrc.
"""

VERIFY_FULL = """\
Verify incrementally as you implement — test every major UI component or API endpoint immediately after writing it (every 5-10 minutes of work). The harness runs the official acceptance tests for this node right after your turn and hands you the failures, so do not build your own test suite: `npm run build` in frontend/, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, one curl per new endpoint (one success, one error case), stop the server. Run verification early and often to catch mistakes before running out of time.
"""

VERIFY_MINIMAL = """\
You have no shell in this turn — the harness runs `npm run build`, starts the backend and runs the official Playwright spec right after your turn and hands you any failure. Tool budget for this turn: at most 8 write_file/edit_file calls (one backend file backend/server.js plus at most 4 frontend files; write each file once, complete) and at most 2 read_file calls. Group the write_file calls into as few responses as possible — small files together, but a large file (more than ~150 lines) alone in its own response — then finish with a one-line summary; every extra round trip resends the whole context and is billed, and an oversized response gets truncated and loses everything in it. Do not list directories or re-read files you just wrote; the file listing above is authoritative. Double-check syntax mentally before writing: a build or start failure costs a repair round.
"""

VERIFY_REQUIREMENT_ONLY = """\
No official/local acceptance spec is available for this task. Do NOT search for hidden tests, Playwright files, reports, git history or extra requirement files: they are unavailable and repeated searching only burns the turn. Treat the supplied requirement node as the contract. After writing the smallest complete vertical slice, run only harness-aligned checks: `npm run build`, start the canonical backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, verify `GET /`, `GET /api/health`, and one success plus one error request for the new route, then stop. These are inferred local probes, not an official test verdict. Finish immediately after they pass.
"""

CONTINUATION_PROMPT = """\
Resume the incomplete implementation of requirement node {node_id}. This is the ONE allowed continuation for this node.
The previous turn ended because of a timeout or request cap. Do not re-plan or search for tests. Use the compact contract and
the current source listing below as authoritative. First inspect only the changed file regions, then write the smallest complete
vertical slice, run a build and one start/health/request smoke, and finish. Preserve every existing route and entity.

COMPACT REQUIREMENT CONTRACT:
{contract}

CURRENT PRODUCT FINGERPRINT: {fingerprint}
CURRENT SOURCES:
{sources}
LAST TURN TAIL:
{tail}
"""

PORT_RULES = """\
Ports: run your own smoke servers ONLY with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start` (port {smoke}). NEVER bind port {port} — the runner watches it and terminates the run. Stop every server you started before you finish. Do not run git; the harness commits.
"""

SKELETON_PROMPT = """\
Build the skeleton of a full-stack web application in the current working directory. The harness already parsed the requirement tree at {req_dir}. Do NOT spend tool calls listing or rereading requirement files. Use this bounded outline as the complete planning input for the shared foundation:
{requirements_outline}

Use this additional compiled contract to preserve exact scenario actions, fixtures, permissions and reload invariants across nodes. It is derived evidence, not an official test suite; do not invent locators that are absent:
{requirement_contract}

""" + ARCHITECTURE_CONTRACT + """
{tests}
This skeleton is the SHARED FOUNDATION every later feature turn extends; later turns have a small per-turn tool budget and cannot afford to rediscover or rebuild it. So in THIS turn, from your skim of the whole requirement tree, lay down:
- A central request router/dispatcher in backend/server.js that is trivial to extend: a route table (method+path -> handler) or equivalent, so a later turn adds one entry and one handler, never rewrites routing.
- The core data model in the JSON store: one seeded collection (even if near-empty) for EVERY top-level entity the requirements mention (e.g. users/sessions, and the main domain objects), with realistic seed rows the tests can read. Later turns add fields/rows, not whole collections.
- A page shell / layout the feature pages slot into (shared header, nav, server-side-rendered-from-cookie if the app has sessions), plus a home page and a health endpoint.
Keep it minimal but STRUCTURALLY COMPLETE: no feature logic yet, but the router, every entity collection, and the page shell must already exist so later turns only fill in behaviour.
Steps: create frontend/ and backend/ as specified, build the router + seed every entity collection + the page shell + health endpoint, run `npm run build` in frontend/, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, then confirm SINGLE-ORIGIN serving on that ONE port: `curl http://127.0.0.1:{smoke}/` returns the built HTML AND `curl http://127.0.0.1:{smoke}/api/health` returns JSON — both from the same server. Grep the frontend sources for `127.0.0.1`, `localhost`, and `API_BASE`: if any absolute origin is hardcoded, replace it with a relative `/api/...` path now, before any feature turn inherits it. Then stop the server.
""" + PORT_RULES

NUDGE_PROMPT = """\
You ended your last turn before creating any files. Stop analysing. In your very next actions CREATE the project files with your file-writing tools: frontend/package.json (build script), the frontend page sources, backend/package.json (start script) and the backend server with the JSON store and seed data. Do not describe the plan — write the files now.\
"""

# Domain-neutral last-resort files keep a budget-truncated generation deployable.
# Existing files are preserved; the fallback only fills missing or empty entries.
MINIMAL_FRONTEND_PACKAGE = '{"name":"arc-minimal-frontend","private":true,"scripts":{"build":"node copy.js"}}\n'
MINIMAL_FRONTEND_COPY = """const fs=require('fs');const path=require('path');
const src=path.join(__dirname,'src'), out=path.join(__dirname,'dist');
fs.cpSync(src,out,{recursive:true,force:true});
console.log('minimal frontend build complete');
"""
MINIMAL_FRONTEND_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Application</title><link rel="stylesheet" href="/styles.css"></head><body><main><h1>Application</h1><p>Ready for feature implementation.</p></main></body></html>\n"""
MINIMAL_FRONTEND_CSS = """*{box-sizing:border-box}body{margin:0;font:16px system-ui,sans-serif;color:#1f2937;background:#f8fafc}main{max-width:960px;margin:4rem auto;padding:2rem;background:#fff;border:1px solid #e5e7eb}h1{margin-top:0}\n"""
MINIMAL_BACKEND_PACKAGE = '{"name":"arc-minimal-backend","private":true,"scripts":{"start":"node server.js"}}\n'
MINIMAL_BACKEND_SERVER = r'''const http=require('http');
const fs=require('fs');const path=require('path');
const root=path.join(__dirname,'..','frontend','dist');const port=Number(process.env.PORT||3000);
function send(res,status,body,type){res.writeHead(status,{'content-type':type||'text/plain; charset=utf-8'});res.end(body)}
function serve(req,res){const url=new URL(req.url||'/', 'http://127.0.0.1');
  if(url.pathname==='/health'||url.pathname==='/api/health')return send(res,200,JSON.stringify({ok:true}),'application/json; charset=utf-8');
  const rel=url.pathname==='/'?'index.html':url.pathname.replace(/^\/+/,''), file=path.resolve(root,rel);
  if(!file.startsWith(path.resolve(root)+path.sep))return send(res,404,'Not found');
  try{const body=fs.readFileSync(file);const type=file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.css')?'text/css; charset=utf-8':'application/octet-stream';send(res,200,body,type)}catch(_){send(res,404,'Not found')}
}
const server=http.createServer((req,res)=>{try{serve(req,res)}catch(_){send(res,500,'Internal error')}});
process.on('uncaughtException',err=>console.error(err));process.on('unhandledRejection',err=>console.error(err));
server.listen(port,'0.0.0.0',()=>console.log(`listening ${port}`));
'''

DESIGN_PROMPT = """\
Design — do NOT implement yet — requirement node {node_id} of the web application in the current directory.

{node_spec}
{ancestors}
{tests}
Read the acceptance spec files for this node in full and the existing code they will exercise. Then write ONE JSON object (at most 80 lines) to the file .arc/design/{node_id}.json AND repeat it in your reply inside a ```json fence. Shape:
{{"routes": [{{"method": "POST", "path": "/api/...", "request": {{}}, "response": {{}}, "errors": []}}],
 "pages": [{{"path": "/...", "elements": [{{"role": "textbox|button|link|heading|combobox|checkbox|radio|alert", "name": "exact accessible name", "notes": ""}}]}}],
 "data_model": {{"collection": {{"field": "type"}}}},
 "files": ["backend/server.js", "frontend/src/..."],
 "notes": "validation rules, session handling, seed data, performance decisions"}}
Copy every accessible name verbatim from the specs. This is a reading turn: use only file reading, listing and grep — no builds, servers, curl or other shell commands — and do not create or modify any other file.
""" + UI_CONTRACT_CORE

NODE_PROMPT = """\
{preamble}
{node_spec}
{design}{ancestors}
{tests}

{execution}

{ui}{performance}
{verify}
""" + PORT_RULES

SPEC_EXECUTION_GUIDANCE = """\
CRITICAL — the quoted acceptance specs are ground truth. Before writing, extract the exact routes, roles, accessible names, option labels and error text they query. Do not reread quoted specs through tools. Implement the complete vertical slice in the same turn, then run the smallest relevant build/start/request check; if a test fails, change the implementation rather than repeatedly inspecting unchanged files.
"""

REQUIREMENT_ONLY_EXECUTION_GUIDANCE = """\
CRITICAL — no acceptance specs exist in the workspace. Do not search for tests, reports, snapshots, git history or additional requirement files. The requirement node above and the harness-maintained application contract are the complete input. Use at most the first two tool calls to read the exact backend/page regions you will edit; by tool call 3 make the first product write. Implement one complete vertical slice now: persistence/data, API route, page/controls and visible success/error state. Preserve existing routes and labels. Do not end with a plan, TODO or description, and do not reread files you just wrote. Before adding a low-fanout feature, repair any shared surface that this node depends on: the home/editor entry route, stable same-origin navigation, the primary entity list/detail surface, and the semantic roles/names required by the contract. Treat the contract as a checklist: fixture/seed, entry route, accessible role/name, user action, mutation, visible result, error behavior, and refresh/reopen persistence. A node is complete only when that whole chain exists; an API-only stub or a button with no persisted visible result is incomplete. Keep the initial seed deterministic and scope every mutation to the selected entity; failed requests must leave the prior state unchanged.
"""

NODE_PREAMBLE_EXTEND = """\
Implement requirement node {node_id} in the existing application (frontend/ built by `npm run build` into frontend/dist/; zero-dependency Node backend in backend/, `npm start`, PORT env var). Extend the app; do not rewrite or break existing features.
The skeleton turn already built the SHARED FOUNDATION: a central router/dispatcher in backend/server.js, a seeded JSON collection for every top-level entity, and the page shell/layout. ASSUME IT EXISTS — add your route to the existing router table and your rows/fields to the existing collection; do NOT rebuild routing, re-seed collections from scratch, or re-scaffold the app. Your budget is small: read only the one backend handler area and the one page you extend (the file listing above is authoritative — do not grep the whole tree or replay git log), then spend the rest of the turn WRITING the feature code so the turn ends with working, verified behaviour, not a design note.
SAME ORIGIN: the backend serves the page and the API on one port. In frontend code call the API with relative paths only — `fetch('/api/...')`. NEVER write an absolute `http://127.0.0.1:<port>`, `http://localhost:<port>`, or an API_BASE host/port constant: the grader serves from a different port and any absolute origin makes every request fail. If an existing frontend file already hardcodes one, fix it to a relative path as part of this node. SHARED SURFACE PRIORITY: preserve and strengthen the existing entry route, primary list/detail page, stable navigation, and accessible role/name surface before implementing advanced behavior. Finish this node as a vertical slice: visible control → handler → same-origin API → JSON persistence → in-place visible result → refresh/reopen restore → failure leaves state unchanged. Use the exact contract fixture and entity scope; do not create generic placeholder buttons, orphan routes, or unrelated seed rows.
"""

NODE_PREAMBLE_CREATE = """\
Build a full-stack web application in the current working directory that implements requirement node {node_id} (the whole requirement tree is at {req_dir}; further nodes, if any, come in later turns — leave room for them but implement only this one).

""" + ARCHITECTURE_CONTRACT + """
Mandatory files (all in this turn): frontend/package.json (with the `build` script), the frontend page sources plus the tiny build script that fills frontend/dist/, backend/package.json (with the `start` script, empty dependencies) and backend/server.js.
"""


INLINE_DESIGN_NOTE = """\
First, in one short paragraph, name the routes, pages (with the accessible element names copied verbatim from the specs) and data fields this node needs — then implement them straight away in the SAME turn. Do NOT spend a write_file call on a separate .arc/design/{node_id}.json file; your request budget is for the application code, not a design document.
"""

EVOLUTION_NOTE = """\
This is an EXISTING application that already passed its previous acceptance tests. Current sources:
{listing}
Read the files you need before changing them, keep every existing route, label and behaviour intact, and change only what this node requires.
"""

REPAIR_PROMPT = """\
The official acceptance tests for requirement node {node_id} just ran against your app: {passed}/{total} passed. Failing tests (Feature / where it failed / what was observed / the last steps before failure):
{failures}
{corrections}{slow}{sources}

CRITICAL - Before attempting repairs:
1. If this is your second repair attempt and the error is similar to the first, your approach is fundamentally wrong - read the test code carefully and implement a COMPLETELY DIFFERENT solution
2. Analyze the test helper functions to understand what DOM structure and accessibility labels are expected
3. Check if you misunderstood the requirement (e.g., "Edit labels" means editing label definitions, NOT assigning labels to notes)

Fix frontend/ and/or backend/ so these tests pass without breaking the passing ones. You have about 10 requests: in the FIRST response read at most two files (only the ones you will change), in the SECOND response emit every edit_file/write_file call together, then finish — do not read more files afterwards. No shell commands. The harness rebuilds and re-runs the official tests right after your turn. The spec files are read-only ground truth.
""" + UI_CONTRACT_CORE + PORT_RULES

FINAL_CHECK_PROMPT = """\
Final end-to-end check of the web application in the current directory:
1. `npm run build` in frontend/ — fix any error.
2. Kill leftover servers, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, confirm `curl http://127.0.0.1:{smoke}/` serves the app and every API endpoint answers (success and error cases).
3. Audit every page against the contracts below and fix violations; run a mechanical strict-mode check: for each value the pages echo, count the elements containing it (`curl -s <page> | grep -o '<value>' | wc -l` for server-rendered pages, or read the render code) — the count must be 1.
{tests}
{ui}{performance}
""" + PORT_RULES

REHEARSAL_REPAIR_PROMPT = """\
The app failed the pre-grading startup rehearsal. The runner executes exactly:
1. cd frontend && npm install && npm run build   (must exit 0)
2. cd backend && npm install && npm start        (must bind PORT and stay up)
Rehearsal error:
{error}
Fix the project so this sequence works (typical causes: a require() path that does not match a real file, a file referenced but never written, a startup syntax error, a dependency missing from package.json). Verify with the canonical command: build the frontend, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, confirm `GET /` returns the app and `GET /api/health` returns 2xx from that same process, then stop it. A transient reset on `/favicon.ico` is not a reason to rewrite product code if `/`, health and the process remain healthy. Never bind {port}. Write only a product-source fix supported by the error; if no product delta is needed, say so and finish.\
"""

ACCEPTANCE_TESTS_PROMPT = """\
OFFICIAL ACCEPTANCE TESTS (ground truth; when prose and spec disagree, the spec wins) live under {tests_dir}. Files: {files}. They define routes, hrefs, accessible names, option labels, exact texts, error wording and action order. Never modify, copy or delete them.
"""

INLINE_SPEC_HEADER = """\
The spec files are quoted below in full — do NOT spend tool calls reading them or the requirement again:
"""


def inline_spec_text(tests_dir: Path, files: list[str], max_chars: int) -> str:
    """Quote spec + helper files into the prompt (bounded). Each read_file the
    model would otherwise issue is a full-context round trip (~11k tokens)."""
    parts = []
    total = 0
    omitted = []
    for rel in files:
        path = tests_dir / rel
        cached = _cached_text(path)
        if cached is None:
            continue
        text, digest = cached
        if total + len(text) > max_chars:
            omitted.append(f"{rel} ({len(text)} chars, sha256={digest[:12]})")
            continue
        total += len(text)
        parts.append(f"--- {rel} ---\n{text.rstrip()}\n")
    if not parts and not omitted:
        return ""
    suffix = ("\nOMITTED SPEC RANGES (do not reread unchanged files; request only the "
              "specific range needed for the current node): " + "; ".join(omitted) + "\n") if omitted else ""
    return INLINE_SPEC_HEADER + "".join(parts) + suffix


def locate_acceptance_tests(tree: dict, bundle_dir: Path) -> Path | None:
    """ARCBENCH_TESTS_DIR, then the runner's /workspace/tests, then the public
    specs shipped in the bundle (matched by requirement root name)."""
    candidates: list[Path] = []
    env_dir = os.environ.get("ARCBENCH_TESTS_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path("/workspace/tests"))
    bundled = bundle_dir / "public-tests"
    manifest = bundled / "manifest.json"
    if manifest.is_file():
        try:
            mapping = json.loads(manifest.read_text(encoding="utf-8"))
            root_name = str(tree.get("name", "")).strip()
            for req_id, title in mapping.items():
                if str(title).strip() == root_name and (bundled / req_id).is_dir():
                    candidates.append(bundled / req_id)
        except Exception as exc:  # noqa: BLE001
            log(f"[tests] manifest unreadable: {exc}")
    for cand in candidates:
        try:
            if cand.is_dir() and any(cand.rglob("*.spec.ts")):
                return cand.resolve()
            log(f"[tests] candidate {cand}: {'no *.spec.ts' if cand.is_dir() else 'absent'}")
        except Exception as exc:  # noqa: BLE001
            log(f"[tests] candidate {cand} unreadable: {exc}")
    return None


def spec_base_ports(tests_dir: Path | None) -> list[int]:
    """Ports the specs hard-code as their default base URL (e.g. 3301)."""
    if not tests_dir:
        return []
    ports: set[int] = set()
    for path in tests_dir.rglob("*.ts"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"https?://(?:127\.0\.0\.1|localhost):(\d{2,5})", text):
            ports.add(int(m.group(1)))
    return sorted(ports)


def acceptance_tests_prompt(tests_dir: Path | None, web_port: int, smoke_port: int,
                            files: list[str] | None = None, inline: bool = False) -> str:
    if not tests_dir:
        return ""
    if files is None:
        files = sorted(str(p.relative_to(tests_dir)) for p in tests_dir.rglob("*.ts"))
    text = ACCEPTANCE_TESTS_PROMPT.format(tests_dir=tests_dir, files=", ".join(files[:40]) or "(none)")
    if inline:
        text += inline_spec_text(tests_dir, files, int(os.environ.get("OCTOS_ARC_INLINE_SPEC_CHARS", "24000")))
    extra = [p for p in spec_base_ports(tests_dir) if p != web_port]
    if extra:
        ports = ", ".join(map(str, extra))
        text += (f"PORT CONTRACT (mandatory): the specs default to port(s) {ports} while the grader starts the "
                 f"backend with PORT={web_port}. Serve the identical app on BOTH the PORT value and port(s) {ports}: "
                 f"create a SEPARATE http.createServer(handler) for each port (one Server can listen only once — "
                 f"calling listen() twice throws ERR_SERVER_ALREADY_LISTEN and the process dies), binding the extra "
                 f"port(s) only when process.env.ARC_EXTRA_PORTS is not '0'. The grader sets ONLY PORT, so the "
                 f"extra port(s) ARE bound during grading.\n")
    return text


# ---------------------------------------------------------------- flow

class Flow:
    def __init__(self, args, output_dir: Path, req_dir: Path) -> None:
        self.args = args
        self.output_dir = output_dir
        self.req_dir = req_dir
        self.web_port = args.web_port
        self.smoke_port = int(os.environ.get("OCTOS_SMOKE_PORT", "3100"))
        if self.smoke_port == self.web_port:
            self.smoke_port += 1
        self.node_timeout = int(os.environ.get("OCTOS_NODE_TIMEOUT", "1200"))  # Keep baseline for reliability - success rate > speed
        self.design_timeout = int(os.environ.get("OCTOS_DESIGN_TIMEOUT", "420"))
        self.budget = int(os.environ["OCTOS_TIME_BUDGET"]) if os.environ.get("OCTOS_TIME_BUDGET") else 3600
        self.budget_explicit = bool(os.environ.get("OCTOS_TIME_BUDGET"))
        # keep-local-3 (workflow C): with 480 s/node, 16 of 17 implement/repair
        # turns were cut at 283 s; Web nodes need 10-20 min of implementation.
        self.seconds_per_node = int(os.environ.get("OCTOS_SECONDS_PER_NODE", "1500"))
        self.min_repair_seconds = int(os.environ.get("OCTOS_MIN_REPAIR_SECONDS", "300"))  # Keep baseline for more repair opportunities
        self.node_budget_cap = int(os.environ.get("OCTOS_NODE_TIME_BUDGET", "1500"))
        self.repair_rounds = int(os.environ.get("OCTOS_REPAIR_ROUNDS", "5"))
        self.final_reserve_seconds = int(os.environ.get("OCTOS_FINAL_RESERVE_SECONDS", "300"))
        self.design_enabled = os.environ.get("OCTOS_DESIGN_TURN", "1") != "0"
        self.design_min_nodes = int(os.environ.get("OCTOS_DESIGN_MIN_NODES", "3"))
        self.skeleton_min_nodes = int(os.environ.get("OCTOS_SKELETON_MIN_NODES", "3"))
        self.small_task_nodes = int(os.environ.get("OCTOS_SMALL_TASK_NODES", "2"))
        # "separate": own read-only turn before implementing; "inline": the
        # implement turn writes .arc/design/<node>.json first, then codes.
        self.design_mode = os.environ.get("OCTOS_DESIGN_MODE", "inline")
        self.implement_fraction = float(os.environ.get("OCTOS_IMPLEMENT_FRACTION", "0.6"))  # Keep baseline - quality over speed
        self.alias_states = os.environ.get("OCTOS_ARC_ALIAS_SPEC_IDS", "1") != "0"
        self.perf_contract = os.environ.get("OCTOS_PERF_CONTRACT", "1") != "0"
        self.guard_enabled = os.environ.get("OCTOS_GUARD", "1") != "0"
        self.t_start = time.time()
        self.runtime = None
        self.events = None
        self.driver: OctosDriver | None = None
        self.tests_dir: Path | None = None
        self.spec_map: dict = {None: []}
        self.probe_summaries: dict = {}
        self.aliases: dict[str, str] = {}
        self.runner: AcceptanceRunner | None = None
        self.designs: dict[str, dict] = {}
        self.test_verdict: dict[str, bool | None] = {}
        self.impl_failed: list[str] = []
        self.pending_corrections: list[str] = []
        self.evolution = False
        self.folder_children: dict[str, list[str]] = {}
        self.tree: dict = {}
        self.ordered_nodes: list[dict] = []
        self.application_contract: dict = {}
        self.requirement_contract: dict = {}
        self.contract_path: Path | None = None
        self.implemented_nodes: set[str] = set()
        self.node_states: dict[str, str] = {}
        self.current_node: str | None = None
        self.current_phase = "initializing"
        self.quota_gated = False
        self.last_turn_wrote = False
        self.last_turn_verified = False
        self.last_turn_budget_exhausted = False
        self.run_id = f"run-{os.getpid()}-{int(self.t_start * 1000)}"
        self.requirements_hash: str | None = None
        self.checkpoints = CheckpointStore(output_dir)
        self._last_structural_key: tuple[str, str] | None = None
        self.acceptance_unavailable = False

    # -- helpers ----------------------------------------------------------
    def remaining(self) -> float:
        return self.budget - (time.time() - self.t_start)

    def time_up(self) -> bool:
        return self.remaining() <= 0

    def checkpoint(self, reason: str, **extra) -> None:
        """Persist a small recoverable boundary; never make resume depend on it."""
        payload = {
            "run_id": self.run_id,
            "workspace": str(self.output_dir.resolve()),
            "requirements_hash": self.requirements_hash,
            "current": {"node_id": self.current_node, "phase": self.current_phase},
            "node_states": dict(self.node_states),
            "test_verdict": dict(self.test_verdict),
            "quota_gated": self.quota_gated,
            "git_head": self.head() if self.runtime is not None else None,
            "reason": reason,
        }
        payload.update(extra)
        try:
            self.checkpoints.write(payload)
        except OSError as exc:
            log(f"[checkpoint] could not write {reason}: {exc}")

    def set_node_state(self, node_id: str, state: str, **extra) -> None:
        self.node_states[str(node_id)] = state
        # ``checkpoint.reason`` is reserved for the event name.  Node-state
        # callers historically supplied ``reason=...`` as diagnostic detail;
        # keep that detail under a distinct key so it cannot collide with the
        # positional event argument.
        if "reason" in extra:
            extra = dict(extra)
            extra["state_reason"] = extra.pop("reason")
        self.checkpoint("node_state", node_id=str(node_id), state=state, **extra)

    def enter_quota_gate(self, reason: str) -> None:
        if self.quota_gated:
            return
        self.quota_gated = True
        log(f"[quota] HARD STOP: {reason[:240]}")
        self.current_phase = "quota_gated"
        # `reason` names the checkpoint event; keep provider detail separate
        # so a billing stop cannot crash the whole flow via duplicate kwargs.
        self.checkpoint("quota_gated", quota_reason=reason[:500])

    def write_run_identity(self, tree: dict) -> None:
        """Persist enough identity to reject a misleading suite/result pairing."""
        task_key = os.environ.get("ARCBENCH_TASK_KEY", os.environ.get("ARCBENCH_TASK", ""))
        suite_key = os.environ.get("ARCBENCH_TEST_SUITE_KEY", "")
        if task_key and suite_key and task_key != suite_key:
            raise RuntimeError(f"suite identity mismatch: task={task_key!r} suite={suite_key!r}")
        specs = []
        if self.tests_dir and self.tests_dir.is_dir():
            for path in sorted(self.tests_dir.rglob("*.spec.ts")):
                cached = _cached_text(path)
                if cached:
                    specs.append({"path": str(path.relative_to(self.tests_dir)), "sha256": cached[1]})
        identity = {
            "schema_version": 1,
            "run_id": self.run_id,
            "task_key": task_key or None,
            "suite_key": suite_key or None,
            "requirement_root": str(tree.get("name") or tree.get("id") or ""),
            "requirements_hash": self.requirements_hash,
            "tests_dir": str(self.tests_dir) if self.tests_dir else None,
            "specs": specs,
            "agent_commit": os.environ.get("OCTOS_AGENT_COMMIT") or (self.head() if self.runtime else None),
            "submission_sha256": os.environ.get("ARCBENCH_SUBMISSION_SHA256") or None,
            "verification_mode": "acceptance_specs" if specs else "requirement_only",
            "official_suite_available": bool(specs),
        }
        try:
            atomic_json_write(self.output_dir / ".arc" / "run-identity.json", identity)
            # Keep identity in the exported runner log as well as .arc.  Some
            # hackathon runs do not expose .arc artifacts, which otherwise
            # makes a result impossible to bind to its task and requirements.
            log("[identity] " + json.dumps({
                "task_key": identity["task_key"],
                "suite_key": identity["suite_key"],
                "requirements_hash": identity["requirements_hash"],
                "agent_commit": identity["agent_commit"],
                "submission_sha256": identity["submission_sha256"],
            }, ensure_ascii=False, sort_keys=True))
        except OSError as exc:
            log(f"[identity] could not write run identity: {exc}")

    def mark(self, kind: str, node_id: str, message: str | None = None) -> None:
        fn = getattr(self.events, f"mark_{kind}")
        fn(node_id, message)
        if self.alias_states:
            for alias, target in self.aliases.items():
                if target == node_id:
                    fn(alias, message)

    def protected_prefixes(self) -> list[str]:
        prefixes = [".arc/", str(self.output_dir / ".arc"), "requirements/", str(self.req_dir)]
        if self.tests_dir:
            prefixes.append(str(self.tests_dir))
        return prefixes

    def sources_text(self) -> str:
        limit = int(os.environ.get("OCTOS_ARC_INLINE_SOURCE_CHARS", "40000"))
        return inline_sources(self.output_dir, limit) + "\n" if limit > 0 else ""

    def corrections_text(self) -> str:
        if not self.pending_corrections:
            return ""
        text = "Corrections from the harness:\n" + "\n".join(f"- {c}" for c in self.pending_corrections) + "\n"
        self.pending_corrections = []
        return text

    def queue_structural_corrections(self, design: dict | None = None,
                                     requirement_text: str = "", enqueue: bool = True) -> list[str]:
        findings = structural_self_check(self.output_dir, design=design,
                                         requirement_text=requirement_text)
        if findings:
            finding_digest = hashlib.sha256("\n".join(findings).encode("utf-8")).hexdigest()
            source_digest = source_fingerprint(self.output_dir)
            key = (finding_digest, source_digest)
            if key == self._last_structural_key:
                log("[structural] unchanged findings and source fingerprint; skipping duplicate correction")
                return findings
            self._last_structural_key = key
            log("[structural] " + "; ".join(findings[:8]))
            if enqueue:
                for finding in findings:
                    correction = "Structural self-check: " + finding
                    if correction not in self.pending_corrections:
                        self.pending_corrections.append(correction)
        return findings

    def _spec_owner(self, spec_file: str) -> str | None:
        """Return a unique node owner for a report file, or None for shared/
        unmapped files. Reports only contain basenames, so ambiguity matters."""
        name = Path(spec_file or "").name
        owners = {
            str(node_id) for node_id, paths in self.spec_map.items()
            if node_id is not None and any(Path(path).name == name for path in (paths or []))
        }
        return next(iter(owners)) if len(owners) == 1 else None

    def _contract_payload(self) -> dict:
        requirements = []
        for node in self.ordered_nodes:
            node_id = str(node.get("id"))
            requirements.append({
                "id": node_id,
                "name": str(node.get("name") or ""),
                "description": str(node.get("description") or "")[:1200],
                "dependencies": [str(dep) for dep in (node.get("dependencies") or [])],
            })
        module_by_node = {}

        def atomic_ids(node: dict) -> list[str]:
            children = [child for child in (node.get("children") or []) if isinstance(child, dict)]
            node_type = str(node.get("type") or "").upper()
            if node_type == "ATOMIC" or (not children and node_type != "FOLDER"):
                return [str(node.get("id"))]
            ids = []
            for child in children:
                ids.extend(atomic_ids(child))
            return ids

        for module in (self.tree.get("children") or []) if isinstance(self.tree, dict) else []:
            if not isinstance(module, dict):
                continue
            label = str(module.get("name") or module.get("id") or "root")
            for node_id in atomic_ids(module):
                module_by_node[node_id] = label
        route_owners: dict[str, list[str]] = {}
        pages: dict[str, list[dict]] = {}
        data_models: dict[str, object] = {}
        designs = {}
        for node_id, design in self.designs.items():
            if not isinstance(design, dict):
                continue
            slim = {key: design[key] for key in ("routes", "pages", "data_model", "files", "notes")
                    if key in design}
            designs[node_id] = slim
            for route in design.get("routes") or []:
                if not isinstance(route, dict):
                    continue
                path = str(route.get("path") or "")
                method = str(route.get("method") or "GET").upper()
                if path:
                    route_owners.setdefault(f"{method} {path}", []).append(node_id)
            if design.get("pages"):
                pages[node_id] = design["pages"]
            if design.get("data_model"):
                data_models[node_id] = design["data_model"]
        ownership = {}
        for node_id, paths in self.spec_map.items():
            owner = str(node_id) if node_id is not None else "integration/shared"
            for path in paths or []:
                ownership[str(path)] = owner
        return {
            "version": 1,
            "requirements": requirements,
            "module_by_node": module_by_node,
            "implemented_nodes": sorted(self.implemented_nodes),
            "passed_nodes": sorted(node_id for node_id, verdict in self.test_verdict.items() if verdict is True),
            "routes": {key: sorted(set(value)) for key, value in sorted(route_owners.items())},
            "pages": pages,
            "data_models_by_node": data_models,
            "designs": designs,
            "source_listing": source_listing(self.output_dir, limit=80),
            "acceptance_ownership": ownership,
            "invariants": [
                "Preserve routes, accessible labels, and data owned by already implemented nodes.",
                "When extending a shared server, keep every existing route reachable and return JSON errors instead of crashing.",
                "Use one coherent data model across dependent nodes; do not create duplicate stores for the same entity.",
                "Keep browser sessions isolated unless the requirement explicitly requires shared state.",
            ],
        }

    def update_application_contract(self) -> None:
        """Persist cross-node context owned by the harness, not by the model."""
        if self.contract_path is None:
            self.contract_path = self.output_dir / ".arc" / "application-contract.json"
        try:
            self.contract_path.parent.mkdir(parents=True, exist_ok=True)
            self.application_contract = self._contract_payload()
            self.contract_path.write_text(
                json.dumps(self.application_contract, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        except OSError as exc:
            log(f"[contract] could not write {self.contract_path}: {exc}")

    def initialize_application_contract(self, tree: dict, ordered: list[dict]) -> None:
        self.tree = tree
        self.ordered_nodes = list(ordered)
        self.contract_path = self.output_dir / ".arc" / "application-contract.json"
        self.update_application_contract()

    def application_context_text(self, node_id: str | None = None) -> str:
        if not self.application_contract:
            return ""
        payload = dict(self.application_contract)
        # Skeleton and the first node carry no cross-node state: nothing is
        # implemented, passed, or designed yet. Injecting the contract there is
        # pure token cost and its "protect already implemented nodes" invariants
        # are misleading, so keep the turn lean until real state exists.
        if not (payload.get("implemented_nodes") or payload.get("passed_nodes")
                or payload.get("designs")):
            return ""
        # Invariants describe how to protect already-implemented work; they only
        # apply once a node has actually been implemented.
        if not payload.get("implemented_nodes"):
            payload.pop("invariants", None)
        payload["current_node"] = node_id
        payload["source_listing"] = str(payload.get("source_listing") or "")[:4000]
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(text) > 14000:
            payload["designs"] = {}
            payload["pages"] = {}
            payload["source_listing"] = str(payload.get("source_listing") or "")[:1800]
            payload["requirements"] = [
                {**req, "description": str(req.get("description") or "")[:300]}
                for req in payload.get("requirements") or []
            ]
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return ("HARNESS-MAINTAINED APPLICATION CONTRACT (read-only; do not edit this file directly):\n"
                + text + "\n\n")

    def requirement_contract_text(self, node_id: str | None = None, max_chars: int = 7000) -> str:
        if not self.requirement_contract:
            return ""
        compact = compact_contract(self.requirement_contract, node_id=node_id, max_chars=max_chars)
        return ("HARNESS-COMPILED REQUIREMENT CONTRACT (derived from YAML; not official test output; "
                "facts carry evidence and confidence; do not invent missing locators):\n" + compact + "\n\n")

    def contract_progress(self, node_id: str, verdict: bool | None = None) -> dict:
        """Summarize contract coverage without treating model claims as proof."""
        node = next((item for item in self.requirement_contract.get("nodes", [])
                     if str(item.get("id")) == str(node_id)), {})
        contract = node.get("acceptance_contract") or {}
        items = [key for key in ("fixture", "entry_route", "role_name", "user_action",
                                 "api_mutation", "visible_result", "error_behavior",
                                 "refresh_reopen_result") if contract.get(key)]
        if verdict is True:
            completed = list(items)
            missing: list[str] = []
            verification = {"type": "acceptance", "status": "passed"}
        elif verdict is False:
            completed = []
            missing = list(items)
            verification = {"type": "acceptance", "status": "failed"}
        else:
            completed = []
            missing = list(items)
            verification = {"type": "acceptance", "status": "unknown"}
        return {
            "contract_items": items,
            "completed_contract_items": completed,
            "missing_contract_items": missing,
            "last_real_verification": verification,
        }

    def acceptance_specs_for(self, node_id: str, ordered: list[dict] | None = None) -> list[str]:
        """Run the node's own specs plus a bounded set from its dependencies."""
        current = list(self.spec_map.get(node_id) or [])
        if not current or os.environ.get("OCTOS_ARC_DEP_REGRESSION", "1") == "0":
            return current
        ordered = ordered or self.ordered_nodes
        # Keep regression evidence bounded under the short exploration window;
        # callers can opt into a larger set after a no-regression canary.
        limit = max(0, int(os.environ.get("OCTOS_ARC_DEP_REGRESSION_MAX_SPECS", "3")))
        selected = list(current)
        seen = set(selected)

        def take(spec: str) -> bool:
            """Add one regression spec; return False once the budget is full."""
            if spec in seen:
                return True
            if len(selected) - len(current) >= limit:
                return False
            selected.append(spec)
            seen.add(spec)
            return True

        for ancestor in ancestors_of(node_id, ordered):
            for spec in self.spec_map.get(ancestor) or []:
                if not take(spec):
                    return selected
        # Backfill remaining budget with the earliest already-passed, non-ancestor
        # nodes. Cross-node breakage travels along shared UI/data surface, not the
        # declared dependency edges: keep-0927 REQ-2.4 (Update Note) passed alone
        # but a later editor node rewrote the note card and broke it, and 2.4 was
        # never a *declared* ancestor so dep-regression missed it until the full
        # suite. The earliest passed nodes build the app shell + CRUD core every
        # later node sits on, so regressing them guards that shared surface.
        for spec in self.core_regression_specs(node_id, ordered):
            if not take(spec):
                break
        return selected

    def core_regression_specs(self, node_id: str, ordered: list[dict]) -> list[str]:
        """Foundational specs to regress on every node, beyond declared ancestors.
        OCTOS_ARC_CORE_REGRESSION=0 disables it. OCTOS_ARC_CORE_REGRESSION_SPECS
        (comma/space-separated spec basenames) pins an explicit set; otherwise the
        earliest already-passed nodes (build order) stand in for the app's core."""
        if os.environ.get("OCTOS_ARC_CORE_REGRESSION", "1") == "0":
            return []
        pinned = os.environ.get("OCTOS_ARC_CORE_REGRESSION_SPECS", "")
        if pinned.strip():
            wanted = {p.strip() for p in re.split(r"[,\s]+", pinned) if p.strip()}
            out = []
            for specs in self.spec_map.values():
                for spec in specs or []:
                    if spec in wanted or os.path.basename(spec) in wanted:
                        out.append(spec)
            return out
        passed = {n for n, v in self.test_verdict.items() if v is True and n != node_id}
        order = {str(n.get("id")): i for i, n in enumerate(ordered)}
        out = []
        for nid in sorted(passed, key=lambda n: order.get(n, 1 << 30)):
            out.extend(self.spec_map.get(nid) or [])
        return out

    def implement_request_budget(self) -> int:
        """Requests one implement turn may spend before the proxy forces it to
        finish. Finite (zero/unbounded requests caused quota tails), but not so
        small the turn is cut before it writes code: platform runs 2b6a1f545c37
        (sheet 0/24) and 0564f5955f16 (github 0/47) hit "request budget 8 hit"
        on every node and ended wrote=False verified=False, feature 0%. Raising
        it to 18 was still too tight on a large app: run 3d6713b1 (prestashop,
        87 tests / 47 nodes) scored 13/100 with 92 nodes hitting "request
        budget 18 hit", starving the whole second half of the tree. A feature
        node must implement + `npm run build` + curl-verify in one turn, so the
        multi-node default is 22, with one separately capped 12-request
        continuation. OCTOS_ARC_IMPLEMENT_REQUESTS overrides the base cap when
        a controlled experiment needs a different budget."""
        return int(os.environ.get("OCTOS_ARC_IMPLEMENT_REQUESTS", "22"))

    def continuation_request_budget(self) -> int:
        configured = int(os.environ.get("OCTOS_ARC_CONTINUATION_REQUESTS", "12"))
        return max(1, min(configured, 12))

    def max_node_request_budget(self) -> int:
        return self.implement_request_budget() + self.continuation_request_budget()

    def skeleton_request_budget(self) -> int:
        """The skeleton turn scaffolds a whole app shell (both package.json
        files, entrypoints, build/start scripts) in one turn; on the two runs
        above the first "request budget 8 hit" fired during skeleton attempt 1,
        so neither end got scaffolded. It now also lays the shared foundation
        every later node extends (central router table, a seeded collection per
        top-level entity, the page shell), so it needs more room than a single
        feature node — give it the implement budget plus headroom, never below
        28."""
        default = max(28, self.implement_request_budget() + 8)
        return int(os.environ.get("OCTOS_ARC_SKELETON_REQUESTS", str(default)))

    def rewrite_request_budget(self) -> int:
        """One bounded rewrite, preserving a request reserve for final checks."""
        configured = int(os.environ.get("OCTOS_ARC_REWRITE_REQUESTS", str(self.implement_request_budget())))
        return max(1, min(configured, int(os.environ.get("OCTOS_ARC_MAX_REWRITE_REQUESTS", "8"))))

    def turn(self, prompt: str, timeout: int, label: str, expect_verification: bool = True,
             request_budget: int | None = None) -> tuple[bool, str]:
        if self.quota_gated:
            return False, "quota_gated: no further model turns are allowed"
        monitor = TurnMonitor(self.protected_prefixes(), expect_verification=expect_verification,
                              allowed_prefixes=[".arc/design/", str(self.output_dir / ".arc" / "design")])
        proxy = getattr(self, "llm_proxy", None)
        if proxy is not None:
            # Per-turn reasoning: OCTOS_ARC_IMPLEMENT_REASONING (e.g. "none") applies
            # to first implement turns of small tasks; rewrite/repair keep the base mode.
            base_mode = getattr(self, "base_reasoning_mode", proxy.mode)
            impl_mode = os.environ.get("OCTOS_ARC_IMPLEMENT_REASONING", "")  # auto already gives "none" to 1-node tasks
            is_implement = label.endswith(" implement") or label.startswith("skeleton")
            proxy.mode = impl_mode if (impl_mode and is_implement and self.minimal_mode(getattr(self, "n_nodes", 99))) else base_mode
            if request_budget is None:
                request_budget = int(os.environ.get("OCTOS_ARC_REPAIR_REQUESTS", "10")) if "repair" in label \
                    else self.implement_request_budget()
            proxy.begin_turn(request_budget)
        t0 = time.time()
        ok, text = self.driver.run(prompt, max(60, int(timeout)), monitor)
        self.last_turn_wrote = bool(monitor.wrote_files)
        self.last_turn_budget_exhausted = bool(
            proxy is not None and proxy.turn_budget and proxy.turn_requests > proxy.turn_budget)
        # This is only a model-turn smoke hint. Official/local acceptance is
        # recorded separately by acceptance_loop and must never be inferred from
        # a model's final summary or an arbitrary curl command.
        self.last_turn_verified = bool(monitor.verified and ok
                                       and not self.last_turn_budget_exhausted)
        log(f"[flow] {label} {'ok' if ok else 'FAILED'} in {time.time()-t0:.0f}s "
            f"(tools={monitor.tool_calls} wrote={monitor.wrote_files} turn_smoke_hint={self.last_turn_verified}): {text[-240:]!r}")
        if self.last_turn_budget_exhausted:
            log(f"[guard] {label}: request budget {proxy.turn_budget} hit; turn forced to finish")
        if proxy is not None and proxy.quota_gated:
            self.enter_quota_gate(proxy.quota_reason or f"{label}: upstream billing limit")
        self.current_phase = "turn_end"
        self.checkpoint("turn_end", label=label, ok=ok, tool_calls=monitor.tool_calls,
                        wrote=monitor.wrote_files, turn_smoke_hint=self.last_turn_verified,
                        request_budget_exhausted=self.last_turn_budget_exhausted)
        for c in monitor.corrections():
            log(f"[guard] {label}: {c[:160]}")
            if self.guard_enabled:
                self.pending_corrections.append(c)
        restored = self.restore_protected()
        if restored:
            self.pending_corrections.append(
                "You changed official test/requirement files; the harness restored them: "
                + ", ".join(restored[:5]) + ". They are read-only ground truth — fix the app instead.")
        return ok, text

    def perf_text(self) -> str:
        return PERFORMANCE_CONTRACT if self.perf_contract and self.needs_session else ""

    def classify_tree(self, tree: dict) -> None:
        """Keyword-gate the optional contract blocks so a counter never reads
        session/hashing rules; the hidden specs only test what the tree says."""
        text = json.dumps(tree, ensure_ascii=False).lower()
        self.needs_session = bool(re.search(r"login|log in|sign in|password|session|register|注册|登录|密码|会话", text))
        self.needs_data = bool(re.search(
            r"seed|published|fixture|option|select|dropdown|nationalit|车次|train|选项|下拉|预置|"
            r"starting state|initial state|existing (?:record|item|parent|context)|parent record|context record",
            text,
        ))

    def ui_contract(self) -> str:
        blocks = [UI_CONTRACT_CORE]
        if getattr(self, "needs_data", True):
            blocks.append(UI_CONTRACT_DATA)
        if getattr(self, "needs_session", True):
            blocks.append(UI_CONTRACT_SESSION)
        return "".join(blocks)

    SHELL_TOOLS = {"bash", "shell", "exec_command"}

    def minimal_mode(self, total_nodes: int) -> bool:
        mode = os.environ.get("OCTOS_VERIFY_MODE", "auto")
        return mode == "minimal" or (mode != "full" and total_nodes <= self.small_task_nodes)

    def verify_text(self, total_nodes: int, has_specs: bool = True) -> str:
        minimal = self.minimal_mode(total_nodes)
        # Prompt budgets alone are ignored often enough (v9-tb-a: 41 tool calls
        # incl. servers in a "no shell" repair turn); in minimal mode the proxy
        # removes the shell tools so commands are impossible, the harness builds.
        proxy = getattr(self, "llm_proxy", None)
        if not has_specs:
            # Requirement-only verification explicitly asks for build/start/
            # request probes. Do not simultaneously hide the shell tools.
            if proxy is not None:
                proxy.extra_drop_tools = set()
            return VERIFY_REQUIREMENT_ONLY.format(smoke=self.smoke_port)
        if proxy is not None and os.environ.get("OCTOS_ARC_DROP_SHELL", "1") != "0":
            proxy.extra_drop_tools = set(self.SHELL_TOOLS) if minimal else set()
        return VERIFY_MINIMAL if minimal else VERIFY_FULL.format(smoke=self.smoke_port)

    def codegen_mode(self) -> bool:
        """One-request generation for one-node tasks (OCTOS_ARC_CODEGEN=0 disables)."""
        return (os.environ.get("OCTOS_ARC_CODEGEN", "1") != "0" and getattr(self, "llm_proxy", None) is not None
                and not getattr(self, "codegen_blocked", False)
                and getattr(self, "n_nodes", 99) <= int(os.environ.get("OCTOS_ARC_CODEGEN_MAX_NODES", "2")))

    def codegen_turn(self, prompt: str, timeout: int, label: str) -> tuple[bool, str]:
        """Run a tool-less turn; parse and write the file blocks from the reply."""
        proxy = self.llm_proxy
        proxy.no_tools = True
        proxy.system_override = CODEGEN_SYSTEM
        try:
            ok, text = self.turn(prompt + "\n" + FORMAT_INSTRUCTIONS, timeout, label, expect_verification=False,
                                 request_budget=int(os.environ.get("OCTOS_ARC_CODEGEN_REQUESTS", "3")))
        finally:
            proxy.no_tools = False
            proxy.system_override = None
        files = parse_file_blocks(text) if ok else {}
        if files:
            written = write_files(self.output_dir, files)
            self.last_turn_wrote = bool(written)
            log(f"[codegen] {label}: wrote {len(written)} file(s): {written[:8]}")
            deduped = dedupe_nav_links(self.output_dir)
            if deduped:
                log(f"[codegen] {label}: removed static nav links duplicating the NAV placeholder in {deduped}")
            self.queue_structural_corrections(enqueue=False)
            return True, text
        if ok:
            log(f"[codegen] {label}: reply contained no file blocks")
            return False, "codegen reply contained no <<<FILE>>> blocks"
        return ok, text

    def codegen_ports_clause(self) -> str:
        extra = [p for p in spec_base_ports(self.tests_dir) if p != self.web_port]
        if not extra:
            return ""
        ports = ", ".join(map(str, extra))
        return (f" The tests default to port(s) {ports} while the grader sets only PORT: ALSO listen on {ports} with a "
                f"separate http.createServer(handler) (same handler) unless process.env.ARC_EXTRA_PORTS === '0'.")

    def spec_bodies(self, node_id: str | None) -> str:
        """Just the spec file contents for a node (codegen prompts)."""
        if not self.tests_dir:
            return "(none)"
        # Inject only the node's own spec. Ancestor specs are still RUN for
        # regression (acceptance_specs_for), but injecting their bodies here
        # scatters the model's attention and tempts it to edit ancestor tests.
        files = list(self.spec_map.get(node_id) or []) if node_id else []
        files += sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                        if not p.name.endswith(".spec.ts") and str(p.relative_to(self.tests_dir)) not in files)
        parts = []
        for rel in files:
            try:
                text = (self.tests_dir / rel).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            parts.append(text if len(files) == 1 else f"--- {rel} ---\n{text}")
        return "\n".join(parts) or "(none)"

    def tests_prompt_for(self, node_id: str | None, skeleton: bool = False) -> str:
        if not self.tests_dir:
            return ""
        if skeleton:
            support = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                             if not p.name.endswith(".spec.ts"))
            n_specs = len(list(self.tests_dir.rglob("*.spec.ts")))
            return (f"The official Playwright specs ({n_specs} files) live under {self.tests_dir}; each later turn "
                    f"receives the spec files for its own node. In THIS turn read only the shared helpers "
                    f"({', '.join(support[:10]) or 'none'}) and at most two spec files to learn the base URL, "
                    f"navigation and header conventions; do not implement the features yet.\n"
                    + acceptance_tests_prompt(self.tests_dir, self.web_port, self.smoke_port, []).split("\n", 1)[-1])
        # Own spec only for the prompt; ancestor regression is run, not injected.
        files = list(self.spec_map.get(node_id) or []) if node_id else []
        support = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                         if not p.name.endswith(".spec.ts"))
        if not files:  # node without its own spec: show everything
            files = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
        return acceptance_tests_prompt(self.tests_dir, self.web_port, self.smoke_port, files + support,
                                       inline=os.environ.get("OCTOS_ARC_INLINE_SPECS", "1") != "0")

    def ancestors_text(self, node_id: str, ordered: list[dict]) -> str:
        anc = ancestors_of(node_id, ordered)
        if not anc:
            return ""
        parts = []
        for dep in anc:
            design = self.designs.get(dep)
            if design:
                slim = {k: design.get(k) for k in ("routes", "pages", "data_model") if design.get(k)}
                parts.append(f"{dep}: {json.dumps(slim, ensure_ascii=False)[:1500]}")
            else:
                parts.append(f"{dep}: implemented (see code)")
        return "Already implemented dependencies — reuse their routes/data, never break them:\n" + "\n".join(parts) + "\n"

    # -- git --------------------------------------------------------------
    def head(self) -> str | None:
        return self.runtime.git.current_head()

    def commit(self, message: str) -> bool:
        try:
            return self.runtime.git.commit(message)
        except Exception as exc:  # noqa: BLE001
            log(f"[git] commit failed: {exc}")
            return False

    def restore_app(self, sha: str) -> None:
        git = self.runtime.git
        for part in ("frontend", "backend"):
            if (self.output_dir / part).exists():
                git.run(["checkout", sha, "--", part], check=False)
        git.run(["clean", "-fd", "-e", "node_modules", "-e", "dist", "--", "frontend", "backend"], check=False)
        log(f"[flow] restored frontend/ and backend/ to best commit {sha[:8]}")

    # -- acceptance -------------------------------------------------------
    def setup_playwright(self) -> None:
        """Prefer the Playwright already on the machine (the runner image ships
        one). A private install is the last resort and never touches shared
        state: own npm cache, own browser dir, pinned version, removed at exit.
        Run da9a64b32c09: an unisolated install made the platform's own
        `npx playwright test` resolve a different version whose chromium build
        was missing, and every graded test failed."""
        if not self.tests_dir:
            return
        env_extra: dict = {}
        root = find_playwright_root(playwright_candidates(BUNDLE_DIR, self.tests_dir, self.output_dir))
        if root is None:
            root = find_playwright_by_search(log)
        if root is None and os.environ.get("OCTOS_ARC_INSTALL_PLAYWRIGHT", "1") != "0":
            version = playwright_version_hint(self.tests_dir)
            log(f"[acceptance] no preinstalled Playwright found; private install of @playwright/test@{version}")
            self.private_playwright = Path(tempfile.mkdtemp(prefix="octos-arc-playwright-"))
            installed = ensure_playwright(self.private_playwright, log, version=version)
            if installed:
                root, env_extra = installed
        if root is None:
            log("[acceptance] Playwright unavailable; nodes will be judged by the final check only")
            return
        limit = container_memory_limit()
        self.mem_limit = limit
        workers = workers_for_memory(limit, int(os.environ.get("OCTOS_ARC_TEST_WORKERS", "2")))
        self.runner = AcceptanceRunner(root, self.tests_dir, acceptance_work_dir(root), log,
                                       timeout_ms=int(os.environ.get("OCTOS_ARC_TEST_TIMEOUT_MS", "10000")),
                                       workers=workers, env_extra=env_extra)
        log(f"[acceptance] using Playwright at {root}; workers={workers}"
            + (f" (container memory limit {limit // (1024 * 1024)} MiB)" if limit else ""))

    def snapshot_protected(self) -> None:
        """Copy the official tests dir (and requirements) so any edit the model
        sneaks past the hook (e.g. via a shell redirect) is undone after the
        turn — the platform grades with THESE files."""
        self.protected_snapshots = []
        for live in (self.tests_dir, self.req_dir):
            if not live or not live.is_dir():
                continue
            snap = Path(tempfile.mkdtemp(prefix="octos-protected-"))
            shutil.copytree(live, snap / "tree", ignore=shutil.ignore_patterns("node_modules"))
            self.protected_snapshots.append((live, snap / "tree", tree_digest(live)))

    def restore_protected(self) -> list[str]:
        fixed_all: list[str] = []
        for live, snap, digest in getattr(self, "protected_snapshots", []):
            try:
                fixed = restore_tree(live, snap, digest)
            except OSError as exc:
                log(f"[guard] could not restore {live}: {exc}")
                continue
            if fixed:
                log(f"[guard] restored {len(fixed)} protected file(s) under {live}: {fixed[:5]}")
                fixed_all.extend(f"{live}/{rel}" for rel in fixed)
        return fixed_all

    def start_llm_proxy(self) -> None:
        """Front the model endpoint with llm_proxy so DeepSeek reasoning is
        capped (`OCTOS_ARC_REASONING`: low (default) | medium | high | none |
        passthrough) and exact per-request usage lands in .arc/llm-usage.jsonl."""
        mode = os.environ.get("OCTOS_ARC_REASONING", "auto")
        if mode == "auto":
            # Thinking off is safe for one-node builds and one-node evolutions
            # (v10: Counter/Dice/Evolution all pass, completion 0.5-1.9k tokens)
            # but TB repairs without thinking looped 22 calls with no write.
            mode = "none" if getattr(self, "nodes_to_implement", 2) <= 1 else "low"
        upstream = os.environ.get("OPENAI_BASE_URL", "")
        if mode == "passthrough" or not upstream.startswith("http"):
            return
        try:
            dump = (self.output_dir / ".arc" / "llm-requests") if os.environ.get("OCTOS_ARC_PROXY_DUMP") == "1" else None
            self.llm_proxy = LlmProxy(upstream, mode, self.output_dir / ".arc" / "llm-usage.jsonl", dump_dir=dump,
                                      destream=os.environ.get("OCTOS_ARC_DESTREAM", "1") != "0",
                                      trim=os.environ.get("OCTOS_ARC_TRIM_PROMPT", "1") != "0",
                                      min_max_tokens=int(os.environ.get("OCTOS_ARC_MAX_TOKENS", "32768"))).start()
        except OSError as exc:
            log(f"[proxy] could not start local LLM proxy ({exc}); using the endpoint directly")
            return
        self.base_reasoning_mode = mode
        os.environ["OPENAI_BASE_URL"] = self.llm_proxy.base_url
        log(f"[proxy] LLM requests via {self.llm_proxy.base_url} -> {upstream} (reasoning={mode}, "
            f"destream={'on' if self.llm_proxy.destream else 'off'}, trim={'on' if self.llm_proxy.trim else 'off'})")

    def stop_llm_proxy(self) -> None:
        proxy = getattr(self, "llm_proxy", None)
        if proxy:
            proxy.stop()
        self.log_usage_summary()

    def log_usage_summary(self) -> None:
        """Provider-reported usage totals (same numbers the platform bills on),
        printed so the runner log carries them even when .arc/ is not exported."""
        path = self.output_dir / ".arc" / "llm-usage.jsonl"
        if not path.is_file():
            return
        tot = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
               "prompt_cache_hit_tokens": 0, "total_tokens": 0, "request_bytes": 0, "response_bytes": 0,
               "sse_chunks": 0}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            tot["requests"] += 1
            for k in list(tot)[1:]:
                tot[k] += int(rec.get(k) or 0)
        log(f"[usage] provider totals: {json.dumps(tot)}")

    def cleanup_playwright(self) -> None:
        private = getattr(self, "private_playwright", None)
        if private and Path(private).exists():
            shutil.rmtree(private, ignore_errors=True)
            log(f"[acceptance] removed private Playwright install {private}")

    def app_server(self, grader_like: bool) -> AppServer:
        return AppServer(self.output_dir, self.smoke_port, log, grader_like=grader_like,
                         extra_ports=[p for p in spec_base_ports(self.tests_dir) if p != self.web_port])

    def run_specs(self, specs: list[str], workers: int | None = None, grader_like: bool = False) -> RunSummary:
        """Build, start, run the specs, then undo whatever the test run mutated
        (a persisted counter at -1 would otherwise be committed as the seed).
        `grader_like` starts the backend with only PORT set, as the platform does."""
        git_run = lambda args: self.runtime.git.run(args, check=False)  # noqa: E731
        snapshot_worktree(git_run)
        server = self.app_server(grader_like)
        try:
            err = server.build()
            if err is None:
                err = server.start()
            if err is not None:
                return RunSummary(error=err)
            return self.runner.run(specs, f"http://127.0.0.1:{self.smoke_port}", workers=workers)
        finally:
            server.stop()
            restore_worktree(git_run)

    def record_tests(self, node_id: str, specs: list[str], summary: RunSummary) -> None:
        try:
            for r in summary.results:
                test_id = re.sub(r"[^A-Za-z0-9._-]+", "-", r.title)[:120]
                owner = self._spec_owner(r.file)
                if owner is None:
                    continue
                self.runtime.traceability.upsert_test(test_id=test_id, req_id=owner, type="e2e",
                                                      file_path=r.file or None, passed=r.ok, emit_event=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[trace] test rows not recorded: {exc}")

    def acceptance_loop(self, node_id: str, specs: list[str], deadline: float,
                        rebuild_prompt=None) -> bool | None:
        """Returns True/False for a real verdict, None when no local run happened.
        `rebuild_prompt(failures)` (optional) yields a full re-implementation
        prompt; it is used once when round 0 passes nothing — rewriting beats
        patching a structurally broken first attempt (v13-tb-a)."""
        if self.runner is None or not specs:
            return None
        best_passed, best_sha, regressions, stalls = -1, self.head(), 0, 0
        rewrite_used = False
        previous_failures = None
        same_failure_streak = 0
        self.codegen_blocked = False  # same failure twice in codegen mode -> tool mode for this node
        for attempt in range(self.repair_rounds + 1):
            if self.quota_gated:
                self.set_node_state(node_id, "inconclusive", reason="quota_gated")
                return None
            summary = self.run_specs(specs)
            if summary.error and summary.killed:
                log(f"[acceptance] {node_id}: test runner killed ({summary.error[:120]}); no verdict from this round")
                return None
            if summary.error:
                log(f"[acceptance] {node_id} infrastructure error: {summary.error[:300]}")
                failures = f"- Feature: app startup\n  Failed at: build/start\n  Observation: {summary.error[:600]}\n  Steps: npm run build -> npm start"
                summary = RunSummary(passed=0, total=max(1, len(specs)))
                passed = 0
            else:
                passed = summary.passed
                failures = failure_summaries(summary)
                self.record_tests(node_id, specs, summary)
                # run_specs has already built, started and reached the app;
                # keep those facts separate from the later official verdict.
                self.node_states[node_id] = "built"
                self.set_node_state(node_id, "smoke_verified", passed=passed, total=summary.total)
            log(f"[acceptance] {node_id} round {attempt}: {passed}/{summary.total}")
            normalized = re.sub(r"\d+", "#", failures or "")
            if normalized and normalized == previous_failures:
                same_failure_streak += 1
                self.codegen_blocked = True
                self.pending_corrections.append(
                    "Your last two attempts produced EXACTLY the same failure. The same logic will fail again: read the "
                    "Expected/Received values in the observation, change the approach (e.g. render the initial state in "
                    "the served HTML instead of after a fetch), and check the spec's locator against your markup.")
                log(f"[flow] {node_id}: identical failure twice; switching repairs to tool mode")
                if same_failure_streak >= 2:
                    log(f"[flow] {node_id}: failure digest did not change after strategy switch; stopping repair")
                    self.checkpoint("repair_stopped", node_id=node_id, failure_digest=normalized[:500])
                    break
            else:
                same_failure_streak = 0
            previous_failures = normalized
            if attempt >= int(os.environ.get("OCTOS_ARC_CODEGEN_REPAIRS", "2")) and passed < summary.total \
                    and self.codegen_mode():
                # Cloud 91aaecaf31af / 5747e6bcf530: repeated codegen repairs re-emit the same files.
                # One cheap codegen repair (failure digest + quoted sources) is allowed; then tools.
                self.codegen_blocked = True
                log(f"[flow] {node_id}: codegen attempt {attempt} still failing; repairs use tool mode")
            for line in (failures or "").splitlines():
                if line.strip().startswith(("Failed at:", "Observation:")):
                    log(f"[acceptance]   {' '.join(line.strip().split())[:360]}")
            if summary.total and passed == summary.total:
                self.set_node_state(node_id, "acceptance_verified", passed=passed, total=summary.total)
                self.commit(f"{node_id} (accepted): {passed}/{summary.total} acceptance tests pass")
                return True
            self.queue_structural_corrections(design=self.designs.get(node_id), enqueue=True)
            if passed > best_passed:
                if best_passed >= 0:
                    self.commit(f"{node_id} (repair {attempt}): {passed}/{summary.total} pass")
                best_passed, best_sha, regressions, stalls = passed, self.head(), 0, 0
            elif passed == best_passed and attempt > 0:
                stalls += 1
                if stalls >= 2:
                    # Cloud f9f0026819f1: six rounds oscillating 4/6 <-> 3/6.
                    log(f"[flow] {node_id}: no improvement for two repairs; keeping the best state")
                    break
            elif passed < best_passed:
                regressions += 1
                if regressions >= 2 and best_sha:
                    self.restore_app(best_sha)
                    self.pending_corrections.append(
                        f"Your last two repairs made the tests worse; the harness restored frontend/ and backend/ "
                        f"to the best state ({best_passed}/{summary.total}). Start from that code.")
                    regressions = 0
            if attempt == self.repair_rounds:
                break
            left = deadline - time.time()
            if left < self.min_repair_seconds + self.final_reserve_seconds or self.time_up():
                # A repair turn that starts with only a couple of minutes left
                # times out too (keep-local-3); keep the best state instead.
                log(f"[flow] {node_id}: {left:.0f}s left, below repair+final reserve "
                    f"({self.min_repair_seconds + self.final_reserve_seconds}s); keeping the best state")
                break
            self.snapshot_sources(node_id, attempt)
            self.checkpoint("acceptance_verdict", node_id=node_id, attempt=attempt,
                            passed=passed, total=summary.total)
            slow = summary.slow(int(os.environ.get("OCTOS_ARC_SLOW_MS", "3000")))
            slow_text = ("Also, these tests took over 3 s on this fast machine and will exceed the grader's "
                         "10 s budget: " + "; ".join(slow) + ". Remove the latency.\n" + self.perf_text()) if slow else ""

            # Time budget awareness in repair prompts
            time_pressure_repair = ""
            if left < 400:
                time_pressure_repair = f"\n⚠️ CRITICAL: Only {left:.0f}s remaining. Make the most targeted fix possible.\n"
            elif left < 600:
                time_pressure_repair = f"\n⏱️ TIME LIMITED: {left:.0f}s left. Focus on the root cause only.\n"
            if passed == 0 and rebuild_prompt is not None and not rewrite_used \
                    and os.environ.get("OCTOS_ARC_REWRITE_ON_ZERO", "1") != "0":
                rewrite_used = True
                log(f"[flow] {node_id}: nothing passed; one full rewrite turn instead of a patch")
                prompt = rebuild_prompt((failures or "(no detail)") + self.corrections_text())
                if self.codegen_mode():
                    self.codegen_turn(prompt, min(self.node_timeout, left), f"{node_id} rewrite (repair {attempt + 1})")
                else:
                    rewrite_budget = self.rewrite_request_budget()
                    self.turn(prompt, min(self.node_timeout, left), f"{node_id} rewrite (repair {attempt + 1})",
                              request_budget=rewrite_budget)
                continue
            prompt = self.application_context_text(node_id) + REPAIR_PROMPT.format(node_id=node_id, passed=passed, total=summary.total,
                                          failures=failures or "(no detail)", corrections=self.corrections_text(),
                                          slow=slow_text, smoke=self.smoke_port, port=self.web_port,
                                          sources=self.sources_text())
            prompt = time_pressure_repair + prompt
            if self.codegen_mode():
                self.codegen_turn(prompt + "\nReturn every file you change as a complete file block.",
                                  min(self.node_timeout, left), f"{node_id} repair {attempt + 1}/{self.repair_rounds}")
            else:
                self.turn(prompt, min(self.node_timeout, left), f"{node_id} repair {attempt + 1}/{self.repair_rounds}")
        if best_passed > 0 and best_sha and self.head() != best_sha:
            self.restore_app(best_sha)
            self.commit(f"{node_id}: keep best acceptance state {best_passed}")
        return False

    # -- per node ---------------------------------------------------------
    def design(self, node: dict, ordered: list[dict], deadline: float) -> dict | None:
        node_id = str(node.get("id"))
        prompt = self.application_context_text(node_id) + DESIGN_PROMPT.format(node_id=node_id, node_spec=describe_node(node),
                                      ancestors=self.ancestors_text(node_id, ordered),
                                      tests=self.tests_prompt_for(node_id))
        ok, text = self.turn(prompt, min(self.design_timeout, deadline - time.time()), f"{node_id} design",
                             expect_verification=False)
        design = None
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
        if ok and m:
            try:
                design = json.loads(m.group(1))
            except json.JSONDecodeError:
                design = None
        if not isinstance(design, dict):
            written = self.output_dir / ".arc" / "design" / f"{node_id}.json"
            if written.is_file():
                try:
                    design = json.loads(written.read_text(encoding="utf-8"))
                    log(f"[flow] {node_id}: design read from {written.relative_to(self.output_dir)}")
                except (OSError, json.JSONDecodeError):
                    design = None
        if not isinstance(design, dict):
            log(f"[flow] {node_id}: design turn produced no JSON; continuing with prose design")
            return {"notes": text.strip()[-1500:]} if text.strip() else None
        return design

    def save_design(self, node_id: str, design: dict) -> None:
        design_dir = self.output_dir / ".arc" / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / f"{node_id}.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
        self.update_application_contract()
        try:
            self.runtime.traceability.upsert_node_contract(node_id, design)
            for i, route in enumerate(design.get("routes") or []):
                if isinstance(route, dict):
                    self.runtime.traceability.upsert_interface(
                        interface_id=f"{node_id}:route:{i}", req_ids=[node_id], type="http",
                        content=f"{route.get('method', '')} {route.get('path', '')}".strip(), emit_event=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[trace] design not recorded: {exc}")

    def node_cycle(self, node: dict, ordered: list[dict], index: int, total: int) -> None:
        node_id = str(node.get("id"))
        self.current_node, self.current_phase = node_id, "node_start"
        self.checkpoint("node_start", node_id=node_id, index=index, total=total)
        specs = self.acceptance_specs_for(node_id, ordered)
        self.codegen_blocked = False  # a previous node's fallback to tool mode must not leak into this one
        nodes_left = total - index + 1
        # Keep a final verification reserve and a small floor for each future
        # node; otherwise an early long node can consume the entire run budget
        # before the harness gets a chance to start and grade the product.
        future_floor = max(0, nodes_left - 1) * 240
        current_available = max(0.0, (self.remaining() - self.final_reserve_seconds - future_floor) / nodes_left)
        node_budget = min(self.node_budget_cap, max(240, current_available))
        deadline = time.time() + node_budget
        log(f"[flow] node {index}/{total} {node_id} starting (budget {node_budget:.0f}s, specs={specs})")

        self.mark("design_started", node_id)
        design = None
        design_wanted = self.design_enabled and total >= self.design_min_nodes and (bool(specs) or os.environ.get("OCTOS_REQUIREMENT_DESIGN", "0") == "1")
        inline_design = design_wanted and self.design_mode == "inline"
        if design_wanted and not inline_design:
            design = self.design(node, ordered, deadline)
        if design:
            self.designs[node_id] = design
            self.save_design(node_id, design)
            self.mark("design_done", node_id, "design JSON written to .arc/design/" + node_id + ".json")
        elif not inline_design:
            self.mark("design_done", node_id, "design folded into the implementation prompt")

        self.mark("implementation_started", node_id)
        self.set_node_state(node_id, "implementing", **self.contract_progress(node_id))
        design_text = ("Design contract for this node (follow it):\n"
                       + json.dumps(design, ensure_ascii=False)[:4000] + "\n") if design else ""
        if inline_design:
            design_text = INLINE_DESIGN_NOTE.format(node_id=node_id)
        if self.evolution:
            design_text = EVOLUTION_NOTE.format(listing=source_listing(self.output_dir)) + design_text
        elif self.has_app():
            design_text = ("Current application files (read only backend/server.js and the page you extend):\n"
                           + source_listing(self.output_dir) + "\n") + design_text
        if self.has_app():
            preamble = NODE_PREAMBLE_EXTEND.format(node_id=node_id)
        else:  # single-node tree without a skeleton turn: create the app in this turn
            preamble = NODE_PREAMBLE_CREATE.format(node_id=node_id, req_dir=self.req_dir, port=self.web_port)
        # Time budget awareness: inject remaining time context
        time_left = deadline - time.time()
        time_pressure_hint = ""
        if time_left < 600:
            time_pressure_hint = f"\n⚠️ TIME CONSTRAINT: You have only {time_left:.0f}s remaining for this node. Implement the minimum viable solution that passes tests. Focus on core functionality only.\n"
        elif time_left < 900:
            time_pressure_hint = f"\n⏱️ TIME AWARENESS: You have {time_left:.0f}s for this node. Work efficiently and test frequently.\n"

        execution = SPEC_EXECUTION_GUIDANCE if specs else REQUIREMENT_ONLY_EXECUTION_GUIDANCE
        node_spec = describe_node(node) if specs else (
            f"ID: {node_id}\nName: {' '.join(str(node.get('name') or '').split())}\n"
            f"Dependencies: {', '.join(map(str, node.get('dependencies') or []))}"
        )
        prompt = (self.requirement_contract_text(node_id) + self.application_context_text(node_id)
                  + NODE_PROMPT.format(node_id=node_id, node_spec=node_spec, design=design_text,
                                    preamble=preamble, ancestors=self.ancestors_text(node_id, ordered),
                                    tests=self.tests_prompt_for(node_id), smoke=self.smoke_port, port=self.web_port,
                                    performance=self.perf_text(), ui=self.ui_contract(), execution=execution,
                                     verify=self.verify_text(total, has_specs=bool(specs))))
        prompt = self.corrections_text() + time_pressure_hint + prompt
        codegen_prompt = None
        implement_timeout = min(self.node_timeout, self.implement_fraction * node_budget, deadline - time.time())
        product_before = product_fingerprint(self.output_dir)
        if self.codegen_mode():
            compact = CODEGEN_PROMPT.format(node_id=node_id, description=str(node.get("description") or "").strip(),
                                            spec=self.spec_bodies(node_id), port=self.web_port, ports=self.codegen_ports_clause(),
                                            size_rule=CODEGEN_SIZE_SMALL if self.n_nodes <= 1 else CODEGEN_SIZE_FULL)
            compact = self.requirement_contract_text(node_id, max_chars=5000) + self.application_context_text(node_id) + compact
            if self.has_app():  # evolution: keep the existing app, return every changed file complete
                compact = (compact.replace("Files:", "Existing app below; keep everything that works and output "
                                           "every changed file complete. Files:", 1)
                           + inline_sources(self.output_dir, 30000, exts=(".html", ".js")))
            codegen_prompt = compact
            write_codegen_manifests(self.output_dir)
            ok, text = self.codegen_turn(compact, implement_timeout, f"{node_id} implement")
        else:
            ok, text = self.turn(prompt, implement_timeout, f"{node_id} implement")
        continuation_used = False
        if not ok and "truncated" in text.lower():
            # Cloud 76fb32a69d81: output cut by max_tokens, nothing written. Retry
            # once, one file per response (fresh session, same prompt).
            log(f"[flow] {node_id}: output truncated; retrying with one file per response")
            self.driver.close()
            retry = prompt + ("\nYOUR PREVIOUS RESPONSE WAS TRUNCATED BY THE OUTPUT LIMIT AND NOTHING WAS SAVED. "
                              "Write exactly ONE file per response (one write_file call, complete file), "
                              "starting with backend/server.js, then finish.\n")
            continuation_used = True
            ok, text = self.turn(retry, min(self.node_timeout, deadline - time.time()),
                                 f"{node_id} implement (retry)",
                                 request_budget=self.continuation_request_budget())
        timed_out = (not ok) and "timed out" in text.lower()
        initial_wrote = self.last_turn_wrote
        initial_budget_exhausted = self.last_turn_budget_exhausted
        # A cap/timeout is recoverable exactly once. The continuation gets a
        # fresh bounded turn and a compact resume context; it cannot turn into
        # an unbounded repair loop or consume the reserve for later nodes.
        if (timed_out or initial_budget_exhausted) and not continuation_used and not self.quota_gated:
            reserve = max(120, self.final_reserve_seconds)
            left = min(deadline - time.time(), self.remaining() - reserve)
            can_resume = (left >= 180 and product_fingerprint(self.output_dir) != product_before)
            if can_resume:
                self.driver.close()
                self.checkpoint("node_resume", node_id=node_id, attempt=1,
                                 before=product_before, after=product_fingerprint(self.output_dir),
                                 initial_timeout=timed_out,
                                 initial_request_budget_exhausted=initial_budget_exhausted)
                resume_prompt = CONTINUATION_PROMPT.format(
                    node_id=node_id,
                    contract=compact_contract(self.requirement_contract, node_id=node_id, max_chars=5000),
                    fingerprint=product_fingerprint(self.output_dir),
                    sources=source_listing(self.output_dir, limit=40),
                    tail=text[-1200:],
                    port=self.web_port,
                    smoke=self.smoke_port,
                ) + PORT_RULES.format(port=self.web_port, smoke=self.smoke_port)
                resume_timeout = max(120, min(self.node_timeout, left))
                resume_ok, resume_text = self.turn(
                    resume_prompt, resume_timeout, f"{node_id} implement continuation",
                    request_budget=self.continuation_request_budget())
                ok, text = resume_ok, resume_text or text
                timed_out = (not resume_ok) and "timed out" in text.lower()
                self.last_turn_wrote = bool(initial_wrote or self.last_turn_wrote)
                # A successful continuation clears the first-turn cap. Keep
                # the first-turn value in the checkpoint for diagnostics, but
                # only the final turn controls truthful completion.
                self.last_turn_budget_exhausted = bool(self.last_turn_budget_exhausted)
                log(f"[flow] {node_id}: continuation {'ok' if resume_ok else 'FAILED'}; "
                    f"wrote_any={self.last_turn_wrote} budget_exhausted={self.last_turn_budget_exhausted}")
            else:
                log(f"[flow] {node_id}: continuation skipped (left={left:.0f}s, wrote={initial_wrote})")
        if ok and not self.has_app():
            # v6-counter: one package.json missing after the turn. Do not give
            # up — the acceptance loop's build error becomes the repair prompt.
            log(f"[flow] {node_id}: app layout incomplete after the turn; acceptance loop will drive the repair")
            self.pending_corrections.append(
                "Your turn ended without both frontend/package.json and backend/package.json (with `build` and "
                "`start` scripts) on disk; the harness could not even build the app. Create the missing files.")
        if not ok and not timed_out:
            self.mark("implementation_failed", node_id, text[-500:])
            self.impl_failed.append(node_id)
            return
        if timed_out:
            # The files written so far stay on disk; let the acceptance loop judge them.
            log(f"[flow] {node_id}: implement turn hit its {implement_timeout:.0f}s cap; testing what exists")
            self.driver.close()
            self.pending_corrections.append(
                "Your implementation turn ran out of time; work in smaller steps and verify with curl early.")
            # A partial turn must remain resumable, but it is not an
            # implementation verdict.  Do not emit implementation_done or
            # consume this node as completed merely because files exist.
            self.mark("implementation_failed", node_id, "implement turn timed out; partial code retained")
            self.impl_failed.append(node_id)
            self.set_node_state(node_id, "inconclusive", reason="implement_timeout")
            return
        if inline_design:
            written = self.output_dir / ".arc" / "design" / f"{node_id}.json"
            try:
                design = json.loads(written.read_text(encoding="utf-8")) if written.is_file() else None
            except (OSError, json.JSONDecodeError):
                design = None
            if isinstance(design, dict):
                self.designs[node_id] = design
                self.save_design(node_id, design)
                self.mark("design_done", node_id, "design JSON written inline to .arc/design/" + node_id + ".json")
            else:
                self.mark("design_done", node_id, "design folded into the implementation turn (no JSON file)")
        findings = self.queue_structural_corrections(
            design=design if isinstance(design, dict) else self.designs.get(node_id),
            requirement_text=str(node.get("description") or ""), enqueue=False)
        hard_findings = tuple(issue for issue in findings if (
            issue.startswith("missing generated file")
            or issue.startswith("missing backend entry")
            or "is not valid JSON" in issue
            or "lacks scripts." in issue
        ))
        if hard_findings or not self.has_app():
            self.mark("implementation_failed", node_id,
                      "scaffold gate failed; structural corrections required before this node can complete")
            self.impl_failed.append(node_id)
            self.set_node_state(node_id, "inconclusive", reason="scaffold_gate", findings=list(hard_findings))
            return
        product_after = product_fingerprint(self.output_dir)
        product_delta = product_after != product_before
        self.checkpoint("product_delta", node_id=node_id, changed=product_delta,
                        before=product_before, after=product_after,
                        request_budget_exhausted=self.last_turn_budget_exhausted)
        if not product_delta:
            # A successful model reply, write-tool label, package-lock update or
            # design note is not a feature implementation.  Do not let it enter
            # the application contract as completed and mislead later turns.
            log(f"[flow] {node_id}: no frontend/backend product delta; node remains inconclusive")
            self.mark("implementation_failed", node_id, "no deployable product source changed")
            self.impl_failed.append(node_id)
            self.set_node_state(node_id, "inconclusive", reason="no_product_delta",
                                request_budget_exhausted=self.last_turn_budget_exhausted)
            return
        incomplete_reason = product_turn_incomplete_reason(
            self.last_turn_wrote, self.last_turn_budget_exhausted)
        if incomplete_reason:
            # A forced summary can return ok=True even though the model ran out
            # of requests mid-feature. Keep and commit useful partial source,
            # but never report the requirement as implemented.
            reason = incomplete_reason
            log(f"[flow] {node_id}: product changed but turn is incomplete ({reason})")
            self.mark("implementation_failed", node_id, f"partial product delta retained: {reason}")
            self.impl_failed.append(node_id)
            self.set_node_state(node_id, "inconclusive", reason=reason, product_delta=True,
                                wrote=self.last_turn_wrote,
                                request_budget_exhausted=self.last_turn_budget_exhausted)
            self.update_application_contract()
            self.commit(f"{node_id} (partial): {node.get('name', '')}")
            return
        self.mark("implementation_done", node_id, (text[-500:] or None) if ok else "product delta retained")
        self.implemented_nodes.add(node_id)
        self.set_node_state(node_id, "implemented", wrote=self.last_turn_wrote, turn_ok=ok,
                            product_delta=True, model_smoke_hint=self.last_turn_verified,
                            request_budget_exhausted=self.last_turn_budget_exhausted,
                            verification="pending_acceptance", **self.contract_progress(node_id))
        self.update_application_contract()
        self.commit(f"{node_id} (implement): {node.get('name', '')}")

        def rebuild_prompt(failures: str) -> str:
            if self.codegen_mode() and codegen_prompt:
                return (codegen_prompt + "\nYour previous files (quoted below) failed every test. Failures:\n" + failures
                        + "\n" + inline_sources(self.output_dir, 30000, exts=(".html", ".js"))
                        + "Fix the root causes and return every file you change, complete.\n")
            return (prompt + "\nYOUR PREVIOUS ATTEMPT FAILED EVERY ACCEPTANCE TEST — the failures (Feature / where / "
                    "observation / steps):\n" + failures + "\n" + self.sources_text()
                    + "Rewrite the files for this node completely (full write_file for each file, not edits), "
                    "fixing the root causes above.\n")

        verdict = self.acceptance_loop(node_id, specs, deadline, rebuild_prompt=rebuild_prompt)
        self.test_verdict[node_id] = verdict
        self.update_application_contract()
        if verdict is True:
            self.set_node_state(node_id, "accepted", **self.contract_progress(node_id, True))
            self.mark("test_passed", node_id, f"{len(specs)} acceptance spec file(s) pass locally")
            try:
                for iface in self.runtime.traceability.list_interfaces(req_id=node_id):
                    self.runtime.traceability.set_interface_implemented(iface["interface_id"], True, emit_event=False)
            except Exception:  # noqa: BLE001
                pass
        elif verdict is False:
            self.set_node_state(node_id, "inconclusive", reason="acceptance_failed",
                                **self.contract_progress(node_id, False))
            self.mark("test_failed", node_id, "acceptance specs still failing after repair rounds")
        else:
            self.set_node_state(node_id, "implementation_unverified",
                                reason="verification_unavailable" if self.acceptance_unavailable
                                else "no_local_acceptance_verdict",
                                **self.contract_progress(node_id, None))

    def snapshot_sources(self, node_id: str, attempt: int) -> Path | None:
        """Copy the app sources that the next repair will overwrite into
        .arc/codegen/<node>-r<attempt>/ (the platform keeps the workspace but not
        our git history, so the first-pass code was unrecoverable: cloud 27de75de0cd0)."""
        dest = self.output_dir / ".arc" / "codegen" / f"{node_id}-r{attempt}"
        try:
            if dest.exists():
                shutil.rmtree(dest)
            count = 0
            for rel in ("frontend/src", "backend"):
                src = self.output_dir / rel
                if not src.is_dir():
                    continue
                for path in src.rglob("*"):
                    if not path.is_file() or "node_modules" in path.parts or path.suffix not in (".html", ".js", ".json", ".css"):
                        continue
                    target = dest / path.relative_to(self.output_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    count += 1
            log(f"[flow] {node_id}: {count} source file(s) snapshotted to {dest.relative_to(self.output_dir)}")
            return dest
        except OSError as exc:
            log(f"[flow] {node_id}: source snapshot failed: {exc}")
            return None

    def already_passing_nodes(self, node_ids: list[str]) -> set[str]:
        """Evolution probe: run each candidate node's specs against the existing app
        (no LLM); nodes that fully pass need no implementation turn."""
        out: set[str] = set()
        for node_id in node_ids:
            specs = list(self.spec_map.get(node_id) or [])
            if not specs:
                continue
            summary = self.run_specs(specs)
            if summary.error or not summary.total:
                continue
            log(f"[acceptance] probe {node_id}: {summary.passed}/{summary.total} against the existing app")
            if summary.all_passed:
                out.add(node_id)
                self.probe_summaries[node_id] = summary  # regression_cycle reuses it
        return out

    def regression_cycle(self, node: dict) -> None:
        """Evolution: unchanged node — carry the design/impl over, re-run its specs."""
        node_id = str(node.get("id"))
        self.current_node, self.current_phase = node_id, "regression"
        self.checkpoint("node_start", node_id=node_id, mode="regression")
        specs = self.acceptance_specs_for(node_id)
        self.mark("design_started", node_id)
        self.mark("design_done", node_id, "unchanged since the previous requirement version; carried over")
        self.mark("implementation_started", node_id)
        self.mark("implementation_done", node_id, "carried over from the template application")
        verdict = None
        if self.runner is not None and specs:
            summary = self.probe_summaries.pop(node_id, None) or self.run_specs(specs)
            if summary.error:
                log(f"[acceptance] regression {node_id} infrastructure error: {summary.error[:300]}")
            else:
                self.record_tests(node_id, specs, summary)
                verdict = summary.all_passed
                log(f"[acceptance] regression {node_id}: {summary.passed}/{summary.total}")
                if not verdict:
                    deadline = time.time() + min(self.node_budget_cap, max(240, self.remaining() / 2))
                    self.pending_corrections.append(
                        "This node passed before this evolution round; the regression below must be fixed "
                        "without removing the new behaviour.")
                    verdict = self.acceptance_loop(node_id, specs, deadline)
        self.test_verdict[node_id] = verdict
        self.implemented_nodes.add(node_id)
        self.set_node_state(node_id, "acceptance_verified" if verdict is True else "inconclusive",
                            reason="regression_cycle")
        self.update_application_contract()
        if verdict is True:
            self.mark("test_passed", node_id, "regression specs pass locally")
        elif verdict is False:
            self.mark("test_failed", node_id, "regression specs fail after repair rounds")

    def final_acceptance(self) -> None:
        """Run EVERY spec file together, files in parallel, like the grader does.
        Per-node runs cannot see cross-node interference through shared server
        state; this pass can, and it repairs the nodes whose tests fail."""
        if self.quota_gated or self.runner is None or not self.tests_dir:
            return
        all_specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
        unverified = [n for n, v in self.test_verdict.items() if v is not True] or \
            [n for n in self.spec_map if n and self.spec_map[n] and n not in self.test_verdict]
        if len(all_specs) < 2 and not unverified:
            return  # single spec already judged by the node run
        rounds = int(os.environ.get("OCTOS_FINAL_REPAIR_ROUNDS", "1"))
        workers = workers_for_memory(getattr(self, "mem_limit", None), int(os.environ.get("OCTOS_ARC_FINAL_WORKERS", "4")))
        previous_failing: set[str] | None = None
        for attempt in range(rounds + 1):
            summary = self.run_specs(all_specs, workers=workers, grader_like=True)
            shared_failure = False
            if summary.error and summary.killed:
                # Cloud 29c840566f36: the runner was OOM-killed under a 512 MiB
                # cgroup; two repair rounds were wasted on a non-failure.
                log(f"[acceptance] full suite could not run ({summary.error[:120]}); keeping per-node verdicts")
                return
            if summary.error:
                # The app does not even start the way the grader starts it: every node fails.
                log(f"[acceptance] full suite (grader-like start) failed: {summary.error[:300]}")
                for node_id in self.spec_map:
                    if node_id:
                        self.test_verdict[node_id] = False
                grouped = {None: []}
                failures = (f"- Feature: application startup exactly as the grader runs it (only PORT set)\n"
                            f"  Failed at: npm start\n  Observation: {summary.error[:700]}\n  Steps: npm run build -> npm start")
                summary = RunSummary(passed=0, total=len(all_specs))
                shared_failure = True
            else:
                grouped = nodes_for_failures(summary.results, self.spec_map)
                failures = failure_summaries(RunSummary(results=[r for rs in grouped.values() for r in rs]))
                shared_failure = bool(grouped.get(None))
            log(f"[acceptance] full suite round {attempt}: {summary.passed}/{summary.total}; failing nodes "
                f"{sorted(k for k in grouped if k) or ('integration/shared application' if shared_failure else [])}")
            for node_id, specs in self.spec_map.items():
                if node_id and specs and summary.results:
                    self.record_tests(node_id, specs, RunSummary(results=[
                        r for r in summary.results if self._spec_owner(r.file) == node_id]))
                    self.test_verdict[node_id] = False if shared_failure else node_id not in grouped
            if shared_failure:
                for node_id, specs in self.spec_map.items():
                    if node_id and specs:
                        self.test_verdict[node_id] = False
            self.update_application_contract()
            if not grouped:
                self.commit(f"chore: full acceptance suite {summary.passed}/{summary.total} pass (parallel)")
                return
            failing_titles = {r.title for rs in grouped.values() for r in rs}
            if previous_failing is not None and failing_titles == previous_failing:
                log("[acceptance] full suite: same failures as the previous round; stopping repairs")
                break
            previous_failing = failing_titles
            if attempt == rounds or self.remaining() < 240:
                break
            failing = sorted(k for k in grouped if k)
            if shared_failure:
                failing.append("integration/shared application")
            if not failing:
                failing = ["all nodes"]
            prompt = self.application_context_text(", ".join(failing)) + REPAIR_PROMPT.format(
                node_id=", ".join(failing), passed=summary.passed, total=summary.total, failures=failures,
                sources=self.sources_text(),
                corrections=self.corrections_text() + "The grader runs all spec files IN PARALLEL against one "
                "server; tests from different files must not interfere through shared server state "
                "(e.g. a counter that every browser session shares). Keep persisted data only where the "
                "requirement demands persistence.\n",
                slow="", smoke=self.smoke_port, port=self.web_port)
            self.turn(prompt, min(self.node_timeout, max(120, self.remaining() - 200)),
                      f"full-suite repair {attempt + 1}/{rounds}")
            if self.quota_gated:
                return
            self.commit(f"fix: full-suite repair {attempt + 1}")

    def ensure_minimal_scaffold(self) -> bool:
        """Fill missing deploy-critical files after a truncated model turn.

        This is deliberately additive: a non-empty file belongs to the model's
        output and is never replaced by the generic scaffold.  That keeps the
        recovery path domain-neutral without erasing partial business work.
        """
        root = self.output_dir
        files = {
            "frontend/package.json": MINIMAL_FRONTEND_PACKAGE,
            "frontend/copy.js": MINIMAL_FRONTEND_COPY,
            "frontend/src/index.html": MINIMAL_FRONTEND_HTML,
            "frontend/src/styles.css": MINIMAL_FRONTEND_CSS,
            "backend/package.json": MINIMAL_BACKEND_PACKAGE,
            "backend/server.js": MINIMAL_BACKEND_SERVER,
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            # Never replace a non-empty model-generated file.  A malformed or
            # incomplete manifest remains visible to the normal scaffold gate,
            # which can report the failure instead of silently losing work.
            try:
                if path.exists() and (not path.is_file() or path.stat().st_size):
                    continue
            except OSError:
                continue
            path.write_text(content, encoding="utf-8")
        return self.has_app()

    # -- skeleton ---------------------------------------------------------
    def skeleton(self, tree: dict) -> None:
        log("[flow] skeleton turn starting")
        prompt = SKELETON_PROMPT.format(req_dir=self.req_dir, port=self.web_port, smoke=self.smoke_port,
                                        requirements_outline=requirement_outline(tree),
                                         requirement_contract=compact_contract(self.requirement_contract, max_chars=12000),
                                        tests=self.tests_prompt_for(None, skeleton=True))
        # No application_context_text here: at skeleton time the contract holds no
        # implemented nodes, designs, or routes, so it is empty overhead. The
        # skeleton turn must stay a fast scaffold, not a whole-app planning pass.
        for attempt in range(1, 5):
            if self.time_up():
                raise RuntimeError("time budget exhausted before the skeleton existed")
            ok, text = self.turn(prompt, self.node_timeout, f"skeleton attempt {attempt}",
                                 request_budget=self.skeleton_request_budget())
            if ok and not self.has_app():
                log("[flow] skeleton turn wrote no frontend/backend; nudging")
                for nudge in range(1, 3):
                    self.turn(NUDGE_PROMPT, 600, f"nudge {nudge}/2")
                    if self.has_app():
                        break
            if not self.has_app() and self.ensure_minimal_scaffold():
                log("[flow] deterministic minimal scaffold filled missing deploy files")
            if self.has_app():
                self.queue_structural_corrections(enqueue=False)
                self.commit("chore: scaffold web application skeleton")
                return
            time.sleep(30)
        raise RuntimeError("skeleton scaffolding failed: no frontend/ and backend/ after 4 attempts")

    def has_app(self) -> bool:
        """Only treat a scaffold as usable after its real entrypoints exist.

        Empty package manifests were previously enough to enter the node loop,
        which caused every later turn to rediscover the missing app and spend
        its request budget repeating structural corrections.
        """
        manifests = (self.output_dir / "frontend" / "package.json",
                     self.output_dir / "backend" / "package.json")
        if not all(path.is_file() for path in manifests):
            return False
        try:
            frontend = json.loads(manifests[0].read_text(encoding="utf-8"))
            backend = json.loads(manifests[1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(frontend.get("scripts"), dict) or not frontend["scripts"].get("build"):
            return False
        if not isinstance(backend.get("scripts"), dict) or not backend["scripts"].get("start"):
            return False
        frontend_entry = any((self.output_dir / rel).is_file()
                             for rel in ("frontend/src/index.html", "frontend/index.html"))
        backend_entry = any((self.output_dir / rel).is_file()
                            for rel in ("backend/server.js", "backend/src/server.js"))
        return frontend_entry and backend_entry

    # -- final ------------------------------------------------------------
    def rehearsal(self) -> bool:
        if self.quota_gated:
            log("[rehearsal] skipped: run is quota_gated")
            return False
        for attempt in range(1, 4):
            log(f"[rehearsal] startup rehearsal {attempt}/3 (smoke port {self.smoke_port}, grader-like env)")
            server = self.app_server(grader_like=True)
            err = server.build() or server.start()
            server.stop()
            if err is None:
                log("[rehearsal] app builds and starts cleanly")
                return True
            log(f"[rehearsal] FAILED: {err.splitlines()[0][:200]}")
            if attempt == 3 or self.remaining() < -600:
                log("[rehearsal] giving up; submitting as-is")
                return False
            self.turn(REHEARSAL_REPAIR_PROMPT.format(error=err[-1200:], port=self.web_port, smoke=self.smoke_port),
                      self.node_timeout, f"rehearsal repair {attempt}")
            self.commit("fix: startup rehearsal repair")
        return False

    # -- run --------------------------------------------------------------
    def run(self) -> int:
        self.runtime = AgentRuntime.from_env(project_dir=str(self.output_dir))
        self.events = self.runtime.events
        self.events.mark_run_started("octos bundle started")
        ordered: list[dict] = []
        watchdog_stop = threading.Event()
        try:
            previous = previous_requirement_records(self.output_dir)
            tree = load_requirement_tree(self.req_dir)
            self.requirements_hash = requirements_digest(self.req_dir)
            self.requirement_contract = compile_requirement_contract(tree)
            self.requirement_contract["requirements_hash"] = self.requirements_hash
            contract_payload = dict(self.requirement_contract)
            contract_payload.pop("contract_hash", None)
            self.requirement_contract["contract_hash"] = hashlib.sha256(
                json.dumps(contract_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            try:
                atomic_json_write(self.output_dir / ".arc" / "requirement-contract.json", self.requirement_contract)
                log("[contract] compiled requirement contract " + json.dumps({
                    "atomic_count": self.requirement_contract.get("atomic_count"),
                    "scenario_count": self.requirement_contract.get("scenario_count"),
                    "contract_hash": self.requirement_contract.get("contract_hash"),
                    "requirements_hash": self.requirements_hash,
                }, ensure_ascii=False, sort_keys=True))
            except OSError as exc:
                log(f"[contract] could not persist requirement contract: {exc}")
            self.runtime.traceability.store_requirement_tree(tree)
            ordered = topo_order(tree)
            if not ordered:
                raise ValueError("no ATOMIC requirement nodes found")
            self.classify_tree(tree)
            node_ids = [str(n.get("id")) for n in ordered]
            if not self.budget_explicit:
                # 32-node trees need hours, not the 1-hour smoke default.
                self.budget = max(self.budget, self.seconds_per_node * len(ordered))
            log(f"[flow] {len(ordered)} atomic nodes in dependency order: {node_ids}; time budget {self.budget}s")
            self.folder_children = folder_descendants(tree)

            self.evolution = self.has_app()
            unchanged: set[str] = set()
            if self.evolution:
                unchanged = unchanged_node_ids(ordered, previous)
                log(f"[flow] evolution mode: existing app detected; unchanged nodes {sorted(unchanged)}, "
                    f"to implement {[i for i in node_ids if i not in unchanged]}")
            self.nodes_to_implement = len([n for n in node_ids if n not in unchanged])
            self.n_nodes = len(ordered)

            self.tests_dir = locate_acceptance_tests(tree, BUNDLE_DIR)
            if self.tests_dir:
                specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
                self.spec_map, self.aliases = map_specs_to_nodes(specs, node_ids)
                self.acceptance_unavailable = not specs
                log(f"[tests] {len(specs)} spec files at {self.tests_dir}; mapping "
                    f"{ {k: v for k, v in self.spec_map.items() if v} }; aliases {self.aliases}")
            else:
                self.acceptance_unavailable = True
                log("[tests] no acceptance specs found; building from requirement text only")
            self.initialize_application_contract(tree, ordered)

            self.runtime.git.ensure_repo()
            self.write_run_identity(tree)
            self.current_phase = "run_initialized"
            self.checkpoint("run_start", node_count=len(ordered))
            self.setup_playwright()
            if self.evolution and self.runner is not None:
                # The platform's template app carries no traceability records, so
                # fingerprints cannot tell what is new. A node whose specs already
                # pass against the existing app is unchanged — no LLM turn for it.
                unchanged |= self.already_passing_nodes([n for n in node_ids if n not in unchanged])
                self.nodes_to_implement = len([n for n in node_ids if n not in unchanged])
                log(f"[flow] evolution mode after probing the existing app: unchanged {sorted(unchanged)}, "
                    f"to implement {[i for i in node_ids if i not in unchanged]}")

            octos_bin = find_octos()
            log(f"[octos] binary {octos_bin}")
            data_dir = Path(tempfile.mkdtemp(prefix="octos-data-"))
            protected = [p for p in (self.tests_dir, self.req_dir) if p and p.is_dir()]
            config_dir = Path(tempfile.mkdtemp(prefix="octos-config-"))
            self.start_llm_proxy()
            env = build_octos_env(config_dir, protected, data_dir=data_dir)
            write_profile_defaults(data_dir, config_dir, protected_hooks(protected))
            self.snapshot_protected()
            env["PORT"] = str(self.smoke_port)  # a bare `npm start` inside a turn must not hit the grading port
            self.driver = OctosDriver(octos_bin, self.output_dir, env, data_dir,
                                      int(os.environ.get("OCTOS_MAX_ITERATIONS", "500")),
                                      events_log=self.output_dir / ".arc" / "octos-events.jsonl")
            self.driver.hooks = protected_hooks(protected)
            threading.Thread(target=_port_watchdog, args=(self.web_port, self.output_dir, watchdog_stop),
                             daemon=True).start()
            try:
                if not self.evolution and (len(ordered) >= self.skeleton_min_nodes
                                           or os.environ.get("OCTOS_SKELETON_ALWAYS") == "1"):
                    self.skeleton(tree)
                    self.driver.end_scope("node")
                elif not self.evolution:
                    log(f"[flow] {len(ordered)}-node tree: skeleton folded into the first node turn")
                for index, node in enumerate(ordered, 1):
                    node_id = str(node.get("id"))
                    if self.quota_gated:
                        log(f"[flow] quota gated; skipping remaining node {node_id}")
                        self.mark("implementation_started", node_id)
                        self.mark("implementation_failed", node_id, "skipped: quota_gated")
                        self.impl_failed.append(node_id)
                        self.set_node_state(node_id, "inconclusive", reason="quota_gated")
                        continue
                    if self.time_up():
                        log(f"[flow] time budget exhausted; skipping {node_id}")
                        self.mark("implementation_started", node_id)
                        self.mark("implementation_failed", node_id, "skipped: time budget exhausted")
                        self.impl_failed.append(node_id)
                        self.set_node_state(node_id, "inconclusive", reason="time_budget_exhausted")
                        continue
                    if node_id in unchanged:
                        self.regression_cycle(node)
                    else:
                        self.node_cycle(node, ordered, index, len(ordered))
                    self.driver.end_scope("node")

                if not self.time_up() and not self.quota_gated:
                    self.final_acceptance()
                    self.driver.end_scope("node")
                undecided = [i for i in node_ids if self.test_verdict.get(i) is None and i not in self.impl_failed]
                final_ok = None
                if self.acceptance_unavailable:
                    log("[verification] official acceptance suite unavailable; startup rehearsal is not a test verdict")
                    for node_id in undecided:
                        self.set_node_state(node_id, "inconclusive", reason="verification_unavailable")
                elif undecided and not self.time_up() and not self.quota_gated:
                    log(f"[flow] final check turn for nodes without a local verdict: {undecided}")
                    final_ok, _ = self.turn(self.application_context_text(None) + FINAL_CHECK_PROMPT.format(
                                                                      smoke=self.smoke_port, port=self.web_port,
                                                                      tests=self.tests_prompt_for(None),
                                                                      performance=self.perf_text(), ui=self.ui_contract()),
                                            self.node_timeout, "final check")
                    self.commit("chore: final verification pass")
                rehearsed = self.rehearsal()
                if not self.acceptance_unavailable:
                    for node_id in undecided:
                        if rehearsed and final_ok is not False:
                            self.mark("test_passed", node_id, "final check and startup rehearsal passed")
                        else:
                            self.mark("test_failed", node_id, "final check or startup rehearsal failed")
                        self.test_verdict[node_id] = bool(rehearsed and final_ok is not False)
            finally:
                watchdog_stop.set()
                if self.driver:
                    self.driver.close()
                self.cleanup_playwright()
                self.stop_llm_proxy()
            for node_id in node_ids:  # final per-node verdicts (full-suite run may have changed them)
                if self.test_verdict.get(node_id) is True:
                    self.mark("test_passed", node_id, "acceptance specs pass (node run and full parallel suite)")
                elif self.test_verdict.get(node_id) is False:
                    self.mark("test_failed", node_id, "acceptance specs failing")
            self.mark_folders()
            self.commit("chore: traceability and acceptance state")
            failed = [i for i in node_ids if self.test_verdict.get(i) is not True]
            if failed:
                self.events.mark_run_completed(f"completed; nodes not verified: {', '.join(failed)}")
            else:
                self.events.mark_run_completed("all requirement nodes implemented and verified")
            _reap_stray_processes("postflight")
            _postflight_structure_check(self.output_dir)
            _free_web_port(self.web_port)
            self.write_preview_ready()
            return 0
        except Exception as exc:  # the platform judges by events, not exit code
            log(f"[flow] aborted: {exc!r}")
            watchdog_stop.set()
            if self.driver:
                self.driver.close()
            self.cleanup_playwright()
            self.stop_llm_proxy()
            for node in ordered:
                node_id = str(node.get("id"))
                if node_id not in self.test_verdict:
                    self.mark("test_failed", node_id, f"run aborted: {str(exc)[:200]}")
            try:
                self.mark_folders()
            except Exception:  # noqa: BLE001
                pass
            _reap_stray_processes("exception")
            _postflight_structure_check(self.output_dir)
            _free_web_port(self.web_port)
            self.events.mark_run_failed(str(exc)[:1000])
            return 0

    def mark_folders(self) -> None:
        """The platform counts FOLDER nodes as requirements too ("45 requirements
        and 32 scenarios" for a 32-leaf tree); derive their state from their
        atomic descendants so the functional-rate denominator is covered."""
        for folder_id, leaves in self.folder_children.items():
            if not leaves:
                continue
            verdicts = [self.test_verdict.get(leaf) for leaf in leaves]
            self.events.mark_design_started(folder_id)
            self.events.mark_design_done(folder_id, f"{len(leaves)} atomic children designed")
            self.events.mark_implementation_started(folder_id)
            if all(v is not None for v in verdicts) or any(leaf in self.impl_failed for leaf in leaves):
                done = [leaf for leaf in leaves if leaf not in self.impl_failed]
                if done:
                    self.events.mark_implementation_done(folder_id, f"{len(done)}/{len(leaves)} atomic children implemented")
                else:
                    self.events.mark_implementation_failed(folder_id, "no atomic child implemented")
            if self.acceptance_unavailable:
                # Build/start evidence is useful, but cannot replace the
                # private official suite. Leave folder test state absent so
                # the traceability stream does not report a synthetic pass.
                continue
            if all(v is True for v in verdicts):
                self.events.mark_test_passed(folder_id, f"all {len(leaves)} atomic children pass")
            else:
                failing = [leaf for leaf, v in zip(leaves, verdicts) if v is not True]
                self.events.mark_test_failed(folder_id, f"children not verified: {', '.join(failing)}")

    def write_preview_ready(self) -> None:
        artifacts_dir = os.environ.get("ARCBENCH_ARTIFACTS_DIR")
        if artifacts_dir:
            try:
                Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
                (Path(artifacts_dir) / "preview-ready.json").write_text(
                    json.dumps({"ready": True, "reason": "octos bundle completed"}) + "\n", encoding="utf-8")
            except OSError:
                pass


# ---------------------------------------------------------------- main

def probe_endpoint() -> None:
    """Raw chat.completions probe; waits out proxy outages (up to 10 min)."""
    key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_BASE_URL")
    if not (key and base):
        return
    import urllib.request as _ur
    body = json.dumps({"model": os.environ.get("MODEL", "deepseek-chat"),
                       "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "max_tokens": 4}).encode()
    deadline = time.time() + 600
    attempt = 0
    while True:
        attempt += 1
        req = _ur.Request(base.rstrip("/") + "/chat/completions", data=body, method="POST",
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with _ur.urlopen(req, timeout=60) as resp:
                log(f"[probe] raw chat/completions -> HTTP {resp.status}: {resp.read()[:120]!r}")
                return
        except Exception as exc:  # noqa: BLE001
            log(f"[probe] attempt {attempt} -> {exc}")
            if time.time() >= deadline:
                log("[probe] endpoint still failing after 10min; proceeding anyway")
                return
            time.sleep(30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Octos agent bundle for ARC-Bench")
    parser.add_argument("requirement_path", nargs="?", default=os.environ.get("ARCBENCH_TASK_DIR", "/workspace/task"))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--type", "--app-type", dest="app_type", default="web")
    parser.add_argument("--web-port", type=int,
                        default=int(os.environ.get("ARCBENCH_WEB_PORT", os.environ.get("ARC_WEB_PORT", "3000"))))
    args = parser.parse_args()

    key = os.environ.get("OPENAI_API_KEY", "")
    print(f"[env] OPENAI_BASE_URL={os.environ.get('OPENAI_BASE_URL', '<unset>')}", flush=True)
    print(f"[env] MODEL={os.environ.get('MODEL', '<unset>')}", flush=True)
    print(f"[env] OPENAI_API_KEY={'set(len=%d)' % len(key) if key else '<unset>'}", flush=True)
    print(f"[env] ARCBENCH_TEMPLATE_DIR={os.environ.get('ARCBENCH_TEMPLATE_DIR', '<unset>')}", flush=True)
    print(f"[env] ARCBENCH_TASK_DIR={os.environ.get('ARCBENCH_TASK_DIR', '<unset>')}", flush=True)
    print(f"[env] argv requirement_path={args.requirement_path}", flush=True)
    probe_endpoint()

    req_src = Path(args.requirement_path).resolve()
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    elif os.environ.get("ARCBENCH_TEMPLATE_DIR"):
        output_dir = Path(os.environ["ARCBENCH_TEMPLATE_DIR"]).resolve()
    else:
        output_dir = Path.cwd() / "workspace" / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    on_platform = bool(os.environ.get("ARCBENCH_TEMPLATE_DIR"))
    if on_platform:
        req_dir = req_src
    else:
        req_dir = output_dir / "requirements"
        if req_dir.exists():
            shutil.rmtree(req_dir)
        shutil.copytree(req_src, req_dir)
    return Flow(args, output_dir, req_dir).run()


if __name__ == "__main__":
    sys.exit(main())
