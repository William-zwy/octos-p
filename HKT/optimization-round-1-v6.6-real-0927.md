# Octos Agent v6.6-real

Date: 2026-09-27

## Goal

Adapt v6.5 to the two real cloud requirements with success rate as the first
priority. Speed shortcuts remain opt-in until they are proven not to reduce
acceptance reliability.

The two known product domains are:

- GitHub collaboration: session, organization, repository, branch, issue, pull
  request, review, permissions, branch protection, and merge state.
- Spreadsheet: workbook, worksheet, cell, formula dependencies, validation,
  filtering, and pivot-derived state.

This version keeps the v6.5 regression gate, best checkpoint, rollback,
scope guard, and no-progress guard.

## Changes

### 1. Deterministic bootstrap instead of an unbounded model skeleton

The v6.6 timeout log showed the bootstrap skeleton turn consuming the full
1200-second allowance before any requirement work started. The default path
now creates only the minimum runnable frontend/backend shell locally:

- `frontend/package.json` with a dependency-free build
- `frontend/src/index.html`
- `backend/package.json` and `backend/server.js`
- `backend/data/db.json`

The model skeleton remains available only with `OCTOS_MODEL_SKELETON=1`.
When enabled, it has a 600-second per-turn cap, a 900-second total cap, a
single build/smoke check, and does not repeat a full skeleton turn after a
timeout.

### 2. Timed-out turn cleanup and proxy disconnect handling

When the caller times out, v6.6 closes the stale Octos session before a later
repair can overlap it. The local LLM proxy also catches
`BrokenPipeError`/connection resets when the caller has already disconnected.
This keeps a late provider response from producing noisy server exceptions or
holding the next repair path open.

### 3. Adaptive implementation budget

`arc/main.py` now selects the first implementation timeout from the node
complexity:

- GitHub/Sheet, long workflows, and stateful nodes keep the v6.5
  `implement_fraction` budget.
- Generic short nodes use a shorter default first-turn fraction of `0.42`,
  capped at `720` seconds.
- The behavior can be disabled with `OCTOS_ADAPTIVE_TIMEOUT=0`.

The default is intentionally conservative. It does not globally shorten the
hard cloud requirements.

### 4. Bounded repair and rewrite time

The old zero-pass path could use every second remaining in the node budget for
one full rewrite. v6.6-real changes this:

- Full rewrite cap: `OCTOS_REWRITE_TIMEOUT_CAP`, default `420` seconds.
- Targeted repair cap: `OCTOS_REPAIR_TIMEOUT_CAP`, default `480` seconds.
- A first implementation that timed out is treated as partial work and goes
  through targeted repair instead of an unrestricted full rewrite.
- Acceptance results remain authoritative; a model timeout does not discard
  useful files that were already written.

### 5. Domain-aware RepairContext

`arc/repair_context.py` now infers only `github`, `sheet`, or `generic`.
For the two known domains, repair prompts receive:

- business flow
- state owners
- read and write paths
- persistence and refresh paths
- permission boundary
- derived state
- workflow transition
- business invariants to preserve

The generic path stays empty rather than injecting incorrect GitHub or
spreadsheet assumptions.

### 6. Tests

Added coverage for:

- simple versus real-domain timeout selection
- independent rewrite and targeted-repair caps
- avoiding full rewrite after an implementation timeout
- GitHub and Sheet context inference
- generic-domain non-invention

### 7. Simple-node acceptance fast path

The v6.5 logs showed that the agent was spending a full model turn on a
requirement even when the skeleton or an earlier node had already made that
node pass locally. v6.6-real now probes the node's official local acceptance
specs before starting its design and implementation turn.

- A fully passing generic/simple node is marked as implemented and verified
  without an LLM turn.
- GitHub, Spreadsheet, long, multi-scenario, and state-heavy nodes are not
  eligible; they keep the normal implementation path for cloud reliability.
- The behavior is enabled by default and can be disabled with
  `OCTOS_FAST_PASS=0`.
- The probe is an acceptance run, not a text or filename heuristic, so partial
  passes still go through the model and repair loop.

### 8. Smaller simple-node repair context

Generic/simple repair and zero-pass rewrite prompts now quote at most 12,000
source characters by default instead of the general 40,000-character budget.
Complex domain nodes retain the full source budget. This reduces repeated
context transfer after a small failure without hiding the relevant app code.
The limit can be adjusted with `OCTOS_SIMPLE_SOURCE_CHARS`.

### 9. Early handoff after successful local verification

The v6.6 logs exposed a separate latency problem: the model had already
written the implementation and successfully verified it, but the runner still
waited for the model's final response. The turn then hit its 630-second cap,
after which acceptance finally ran and passed.

For non-evolution, generic/simple implementation nodes, the runner now watches
tool events for writes followed by a successful build, start, curl, Playwright,
or equivalent verification command. It closes that model turn immediately and
runs the official acceptance spec against the files on disk. If acceptance
fails, the existing targeted repair loop continues normally.

This path is disabled for GitHub/Spreadsheet and other complex nodes, evolution
runs, and codegen turns. Set `OCTOS_EARLY_STOP_AFTER_VERIFY=0` to disable it.
A local verification success is only a handoff signal, not an acceptance
verdict; the official acceptance result remains authoritative.

The implementation also removes an accidental duplicate implementation call
introduced while wiring this optimization. Each node now has exactly one
implementation turn.

### 10. Hotfix after the REQ-2.2 run

The first early-stop run showed that `REQ-2.2` was incorrectly classified as a
simple node because its description was short, even though it required a
dialog, labelled textboxes, form filling, and autosave. Complexity detection
now treats interactive workflow terms such as `dialog`, `textbox`, `form`,
`fill`, `autosave`, `dropdown`, and `undo` as complex signals. Early-stop is
now narrower than fast-pass and is limited to short, low-risk shell tasks.

The same run also showed a repair turn that made no file changes before the
no-progress guard ended the node. The guard now allows one additional repair
with an explicit must-edit instruction and a larger request budget
(`OCTOS_NO_PROGRESS_REPAIR_REQUESTS`, default `16`). A second identical
no-progress result still stops the node and preserves the best checkpoint.

## Expected effect

For success-rate-first runs, every node follows the same full lifecycle as a
GitHub or Spreadsheet node: design context, implementation, official
acceptance, targeted repair, checkpointing, and final regression acceptance.
Short descriptions no longer receive a special shorter timeout or a weaker
verification mode.

This intentionally gives up some local speed. A simple node can use the same
first-turn budget as a complex node, but it is less likely to be handed off
after a smoke check that missed a required interaction such as a dialog,
textbox, persistence transition, or accessible state.

GitHub and Sheet nodes still receive their domain-specific repair context. The
shared execution lifecycle does not mean that generic nodes are given
incorrect GitHub or spreadsheet business assumptions.

This is not a guarantee of 32/32 or cloud completion. The downloaded real
requirements are much larger than the local 32-test set, and the simulator is
not available on this machine.

## Verification

Passed:

```text
python -m py_compile arc/main.py arc/acceptance.py arc/repair_context.py
git diff --check
cd arc
python -m unittest tests.test_guard tests.test_main_helpers.AdaptiveTimeoutTests tests.test_main_helpers.DomainContextTests tests.test_main_helpers.AlreadyPassingProbeTests
```

The targeted v6.6 tests ran 24 tests and passed, including the reliability-first
shared-budget check, early-stop readiness, and failed-verification gating. The
full unittest collection
loaded and ran 101 tests, but the complete run is currently blocked by
pre-existing Windows test-environment issues:

- temporary-directory creation/cleanup returns `WinError 5` in this managed
  environment;
- one existing test asserts POSIX `/private/x` path behavior on Windows.

The full collection therefore reported 1 existing assertion failure and 13
temporary-directory errors; none were in the targeted v6.6 behavior tests.

The Windows bundle used before the latest repair was:

```text
octos-arc-bundle_v6_6-real-hotfix_0927.zip
SHA256: 51E70EBA03DDC745F7520869E913C09B7C4A69A699235C07D779D4ADB812CBBC
```

That bundle predates the final REQ-2.2 hotfix and must not be used for the
next run. The current Windows bundle is:

```text
octos-arc-bundle_v6_6-real-hotfix3_0927.zip
SHA256: B7296C72D8E95B3F2F9B008FCFC29CFA867CD31A8C04BEE4E6C26F5CE359CA7E
```

It contains the interactive-task classification, no-progress repair fixes, and
the reliability-first unified execution path.
`arc/pack.ps1` is the Windows packaging script; `arc/pack.sh` remains
available for Linux/macOS environments. The command used was:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\arc\pack.ps1 `
  -OutputPath .\octos-arc-bundle_v6_6-real-hotfix3_0927.zip
```

## Reliability-first run settings

These are the intended defaults for the next cloud run:

```text
OCTOS_RELIABILITY_FIRST=1
OCTOS_ADAPTIVE_TIMEOUT=1
OCTOS_FAST_PASS=0
OCTOS_EARLY_STOP_AFTER_VERIFY=0
OCTOS_ARC_CODEGEN=0
OCTOS_VERIFY_MODE=full
```

The previous speed-focused settings remain available only as an explicit
experiment with `OCTOS_RELIABILITY_FIRST=0`; they should not be used for the
success-rate comparison.
