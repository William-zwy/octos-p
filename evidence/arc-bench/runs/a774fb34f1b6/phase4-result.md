# Phase 4 final root-cause ruling

PHASE4_RESULT: complete

- run_id: `a774fb34f1b6`
- task_key: `arc-bench-lite-evolution--bookstack`
- submission_id: `a9475f8e5f57`
- handoff_id: `a774fb34f1b6-5C8C42D46488`
- manifest_sha256: `F224DEFC19FE03590A8768298ED3D1CDEBD882A642859879B6467211AEB3FDB4`

## Final platform result

The authoritative result is `FAILED`, score `66.7%`, with `4/6` tests passing. The final Playwright execution failed only:

- `REQ-10.2`: `failed` in 484 ms. The error was `locator.allTextContents: Execution context was destroyed, most likely because of a navigation` at the official test's list read.
- `REQ-11.1`: `timedOut` in 10014 ms. The recorded locator was `getByRole('heading', { name: /This\\s+page\\s+needs\\s+review\\./i }).first()` and no matching element appeared.

The passed tests were `REQ-10.1`, `REQ-11.2`, `REQ-12.1`, and `REQ-12.2`. Final platform tests take precedence over internal acceptance turns, `node_states`, and the evolution flow's intermediate verdicts.

## Formal root-cause ruling

### REQ-10.2: confirmed primary product root cause

The generated template's sort-save handler sends the PUT request and then assigns `window.location.href` on both success and failure (`template/backend/src/server.js:1024-1039` in the submitted template ZIP). The final test reads the sorted list immediately afterward and reports that navigation destroyed its execution context. The backend PUT handler does persist `contentsOrder` (`template/backend/src/server.js:2242-2260`), so the available evidence does not support a missing sort API or a sorting algorithm error as the primary cause.

Required boundary: save the order, keep the current document alive, update or retain the already-sorted list in place, close the sort UI, and show an error without navigating if the request fails.

### REQ-11.1: confirmed primary product root cause

The generated page renders comments as `li` elements under an `h2` named `Reader discussion` (`template/backend/src/server.js:1386-1403`). The final test searches for a heading named `This page needs review.` and times out. The POST route does append the comment, persist it, and return `201` (`template/backend/src/server.js:2334-2364`), while the client then calls `window.location.reload()` (`template/backend/src/server.js:1406-1436`). Therefore the strongest supported diagnosis is an observable accessible-DOM contract mismatch, compounded by reload dependence, rather than a demonstrated POST persistence failure.

Required boundary: after a successful POST, append the returned comment in place using the exact official accessible text/heading contract, clear the input, and avoid an immediate reload.

## Stage 3 intermediate-state reconciliation

Stage 3 P0 findings are confirmed by the final report and template evidence. Its P1/P2 findings are retained with the following status:

- Confirmed generator/process issues: the checker repeatedly looked for `backend/server.js` although the template contains `backend/src/server.js`; `node_states` says every requirement passed while `tests[]` contains the two failures; `REQ-10.2` reached its 900-second implementation cap; and postflight logs show defunct `chrome-headless`, `node`, `npm start`, and `pkill` processes.
- Confirmed process boundary: `/workspace/tests` contained no `*.spec.ts` during generation, so internal checks were built from requirement text only. Those checks cannot be treated as official Playwright coverage.
- Strong candidates, not run-level causes: targeted reads for large files/reference images and minimal locator-level fallback tests when official specs are unavailable. The supplied artifacts do not quantify an unbounded read or prove that it caused either final failure.

These generator and observability problems explain wasted time and misleading intermediate state, but they do not replace the two product-level causes above.

## Unknowns and limits

The exact `arc-bench-lite-evolution` public-test source is not present in the checked-in 20260917 snapshot. The final report and failure-details attachment therefore supply the authoritative locator/error evidence. The supplied run object also has no platform agent-build, code-SHA, or upload-binding field. No claim is made about provider LLM time beyond the recorded total run duration.

## Scope

This was a read-only diagnosis of Run `a774fb34f1b6`. No Agent code, official test, task snapshot, ZIP, asset, runtime configuration, or platform Run was modified or rerun. Stage 5 was not triggered.
