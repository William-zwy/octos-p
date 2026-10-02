# ArcBench evidence — 3307814a18ea

- Task: `hackathon--sheet`; submission: `3492f270f204`
- Agent commit reported by run: `faf8c784c15e5bdefbe3dea55a6c93a870e0ea38`
- ZIP SHA-256: `22E261919531D428C7155CE57213450736AE78721ABA7A5AEA1B62DAFA7B8842`
- Result: `0/100`, `0/24`; generation aborted after `REQ-1-1-1`.
- Failure class: `runtime_api_incompatibility` (confidence: high; P0-blocking).
- Exact error: `AttributeError: EventClient.mark_implementation_ready`.
- Exclusions: no 402, OOM, proxy error, timeout, or deployment failure.

## Decision

The first repair is an EventClient compatibility guard. `main.py` emits an intermediate
`implementation_ready` event before acceptance; the bundled EventClient lacked that
method, so one completed node aborted the entire flow. This is repaired on branch
`codex/hkt-runtime-compat-3307814` by adding an intermediate `ready` event that does
not map to `IMPLEMENTED`.

This repair restores flow continuity only. It does not establish business correctness,
semantic smoke coverage, or hidden-test acceptance.
