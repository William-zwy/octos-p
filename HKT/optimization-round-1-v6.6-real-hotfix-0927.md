# Octos Agent v6.6-real hotfix

Date: 2026-09-27

## Problem

The v6.6-real log showed a skeleton turn timing out after 1200 seconds,
followed by another full skeleton turn. The old session could also remain
usable after a timeout, and the local LLM proxy printed `BrokenPipeError`
when the timed-out caller closed its HTTP socket before the upstream response
finished.

## Fix

- The default skeleton path is now deterministic: the harness writes the
  product-neutral frontend/backend shell, health endpoint, and JSON store
  locally without spending an LLM turn on bootstrap. The first model turn is
  reserved for the first real requirement node.
- The previous model-driven skeleton remains available with
  `OCTOS_MODEL_SKELETON=1` for diagnosis or rollback. Its first turn is capped
  at 600 seconds and its total bootstrap budget defaults to 900 seconds.
- Timed-out stdio turns now invalidate and close their session in every
  session scope.
- Skeleton setup has a total timeout budget controlled by
  `OCTOS_SKELETON_TOTAL_TIMEOUT` (default `900` seconds).
- A timed-out skeleton uses targeted nudges for missing manifests/files
  instead of immediately replaying another full 1200-second skeleton prompt.
- Skeleton turns and nudges reserve time for cleanup and stop when the total
  skeleton budget is exhausted.
- `llm_proxy.py` treats `BrokenPipeError` and connection-reset writes as a
  normal caller timeout, so they no longer produce a misleading traceback.

## Verification

```text
python -m py_compile arc/main.py arc/llm_proxy.py arc/repair_context.py
targeted timeout/skeleton tests
git diff --check
```

The full simulator is not available in this environment. The fix is designed
to prevent the exact sequence in the uploaded log: timeout -> second full
skeleton turn -> stale proxy write.

The deterministic bootstrap was also checked locally with `npm run build`,
`node --check backend/server.js`, and a live `/api/health` request.
