# Phase 4 final root-cause ruling

PHASE4_RESULT: complete

- run_id: `c68bef1a6343`
- task_key: `arc-bench-web--keep`
- submission_id: `362bc0d7b112`
- handoff_id: `c68bef1a6343-6D7B1A92C4E0`
- thread_id: `01a0b7e7-1cff-7380-ac81-ef35dbe70633`
- manifest_sha256: `E4008585EE9406A004D71ED70D98D2312C257D71528233C90DEE3C6449C60463`

## Recovery and scope

The automatic Codex thread route returned `-32602 Invalid app tool request` before delivery. The user-authorized manual intervention fallback used the canonical registered thread ID only as the identity anchor, analyzed only Run `c68bef1a6343`, and wrote the matching ACK/result files. No duplicate thread was created, no platform Run was started, and Stage 5 was not triggered.

## Confirmed causes

1. The submitted ZIP contains a generated-run `backend/data/db.json`. `server.js` loads that file whenever it exists, and the default notes endpoint filters trashed notes. `Delete me 2.3.1` and `Delete me 2.3.3` are already trashed in the ZIP even though `seedStore()` defines them as clean. This directly explains the missing delete fixtures.
2. The app starts in grid mode but labels the toggle `Grid view`; the official default-grid test searches for the action `List view`. The label is only changed after the first click, so the initial accessible contract is wrong.

## Strong candidates

- Archive and label mutations call `loadNotes()` or `loadLabels()` without awaiting the refresh. `renderNotes()` clears and rebuilds the notes area, which can detach a card during hover or leave stale filtered content visible to the next assertion.
- The visible settings trigger and its nested menu item both expose `Settings`. The official helper resolves a button before a menuitem, so it can toggle the menu closed and leave `#settings-save` hidden instead of opening the detail panel.
- Color mutation also refreshes the DOM asynchronously before the visual helper takes its bounding-box screenshot, which is consistent with an empty clip but not sufficient to prove the exact geometry.

## Unknowns and limits

The exact clean-seed browser replay for the settings and screenshot cases was not run because this recovery environment has no Playwright runtime. The supplied report therefore remains authoritative for symptoms, while the three cases above retain `strong_candidate` rather than `confirmed` status. Octos timeouts, the single provider proxy error, and the runner's unverified nodes remain Phase 3 execution evidence and are not merged into product-template root causes.

## Scope

This was a read-only diagnosis of Run `c68bef1a6343`. The Agent, official tests, task snapshot, source ZIP, assets, and runtime configuration were not modified. The only repository outputs are the matching Phase 4 ACK/result files and the registry state recording the manual-intervention fallback.
