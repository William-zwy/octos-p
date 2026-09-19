# CODEX CONTEXT — code-philia Agentic SE Hackathon (repo prep session)

> Compiled 2026-09-17 (JST). Source of truth: verified live state of the machine, not memory.
> Audience: Codex. Style: dense, machine-oriented. Every path/command/hash was executed and confirmed.

---

## 0. MISSION & STATUS

User intends to participate in the **code-philia Agentic Software Engineering Hackathon**.
Local repo: `D:\agentic-software-engineering-hackathon` (upstream: `https://github.com/code-philia/agentic-software-engineering-hackathon.git`).

Two user-ordered actions, both COMPLETE:
1. **Step 1 — `rehearse:gui` (offline GUI pipeline rehearsal): PASSED** (exit 0; TDD validation 36/36).
   Fixed 2 Windows-specific bugs in Lab02 source (3 files modified, typecheck green, git status shows exactly these 3 `M`).
2. **Step 2 — fetch official Labs Lab01, Lab03–07**: DONE. 44 previously-missing tracked files restored to disk and byte-verified against `origin/main` tree blob SHAs. git status clean (only the 3 patches).

Environment readiness audit (earlier): 10/11 → now **11/11** (Node v24, npm 11, Playwright browsers, doctor [ok], demo:api passed, GUI pipeline verified, all 7 Labs present).

---

## 1. ENVIRONMENT FACTS (verified)

| Item | Value |
|---|---|
| OS | Windows (desktop) |
| Repo root | `D:\agentic-software-engineering-hackathon` |
| git version | 2.33.0.windows.2 |
| HEAD | `1d1f0bbcb4abdf7911a4635f1cec72c36417f008` (= `origin/main`, re-fetched 2026-09-15, confirmed current) |
| Node (real) | `D:\nodejs\node.exe` v24.21.0 — **must use** `D:\nodejs\npm.cmd` for Lab02 npm scripts |
| npm | 11.19.0 |
| Assistant shell node | v22.23.2 (sandbox) — DO NOT use bare `npm`/`node` from the agent shell |
| Playwright | v1.63.0 (Lab02 dep) |
| Browsers | `D:\ms-playwright\` (chromium-1243, chromium_headless_shell-1243, ffmpeg-1011, winldd-1007). C-drive default `C:\Users\dayuruozhi\AppData\Local\ms-playwright` does NOT exist |
| Env var (User scope) | `PLAYWRIGHT_BROWSERS_PATH=D:\ms-playwright` |
| VS Code | `E:\Users\dayuruozhi\AppData\Local\Programs\Microsoft VS Code` |
| User temp (Write tool) | `C:\Users\dayuruozhi\AppData\Local\Temp` |
| Agent tool `$env:TEMP` | `E:\Temp` (DIFFERENT — resolve absolute paths, never rely on `$env:TEMP`) |
| User location | Japan (UTC+9, since 2026-09-17). Network topology may differ from when downloads ran (China) |
| `.env` (Lab02) | keys present: `api_key` (len 46), `model` (len 17), `base_url` (len 28 = `https://api.arc-bench.com/v1`) — values not shown; model = deepseek-v4-flash |

### git topology (critical)
- **Partial clone**: `remote.origin.promisor=true`, `remote.origin.partialclonefilter=blob:none` → blobs fetched lazily on demand.
- **Shallow** clone (depth cut at some point).
- **Sparse checkout**: `core.sparseCheckout=true`, cone pattern = `Lab/Lab02`. Files outside cone exist in index with skip-worktree bit.
- `core.autocrlf=true`. No `.gitattributes`.
- Repo-local git config added during session: `http.version=HTTP/1.1`, `http.postBuffer=524288000`.
- Remote refs also present locally: `refs/remotes/origin/feat/prepare-gui-demo` (8300ae70), `refs/remotes/origin/pr/*` (1..6).

---

## 2. ARTIFACT INVENTORY (产物清单)

### 2.1 Modified source files (git status `M`, all 3 — the only local changes)
| File (repo-relative) | Change |
|---|---|
| `Lab/Lab02/src/testing/process.ts` | Added `"PLAYWRIGHT_BROWSERS_PATH"` to `SAFE_ENVIRONMENT_KEYS` whitelist (fix: subprocess env stripping → Playwright couldn't find browsers on D:) |
| `Lab/Lab02/src/testing/run-generated-tests.ts` | Added `projectRelativePath()` (relativize against projectRoot, POSIX `/` separators); GUI train-test positional args + `--config` now relative |
| `Lab/Lab02/src/validation/run-validation.ts` | Same `projectRelativePath()` treatment for GUI validation spec/config args |

Diff stat: 3 files, +24/-5. Files preserved as CRLF, UTF-8 no BOM. `npm run typecheck` PASSES.

### 2.2 Rehearsal run artifacts (under `Lab/Lab02/runs/`)
- **SUCCESS**: `runs\20260915T144956Z-gui-fe64c72d\` — `result.json` (outcome GREEN; directValidation 8/36; referenceTrain 3/3; initialTrain RED 1/3; finalTrain GREEN 3/3; tddValidation **36/36**; repairs=1; model=offline-rehearsal, 0 tokens), plus `raw/`, `test-output/` (playwright json reports + error-context.md per check).
- Failed archives (diagnostic value):
  - `runs\20260915T135346Z-gui-7583d9df` — "No tests found" (absolute-path bug).
  - `runs\20260915T140313Z-gui-471528a7` — reference-train 3 tests failed at `browserType.launch` (PLAYWRIGHT_BROWSERS_PATH stripped).
- Other runs present (not this session's focus): `20260915T131038Z-api-*` … `20260915T140657Z-api-86b6a25b`, `20260915T135219Z-gui-bcbf718a`, `20260915T141542Z-gui-536521a6`, `20260915T142456Z-gui-da159c94`, `20260915T143542Z-gui-59c38196`, `20260915T145741Z-gui-7c1c1c4d`, `doctor/`.

### 2.3 Downloaded official Labs (Step 2)
All 7 lab dirs present on disk (file counts incl. everything under each Lab):
`Lab01: 2 · Lab02: 9120 (incl. node_modules/workspace) · Lab03: 2 · Lab04: 13 · Lab05: 8 · Lab06: 16 · Lab07: 9`.

44 files were missing (tree had them, disk didn't). ALL restored. Verification ledger:
- 43/44: `git hash-object --path=<p> <file>` == tree blob SHA (`git ls-tree -r origin/main Lab/`). Includes the 6 big binaries:
  - `Lab04/demo_full.zip` 58,549,085 B · `Lab04/demo_wo_ref.zip` 58,367,067 B · `Lab05/demo_git.zip` 54,652,150 B · `Lab07/demo_added.zip` 58,478,476 B (zips) · `Lab04/lab4.pptx` 6,819,604 B · `Lab05/lab567.pptx` 7,653,569 B.
- 1/44 `Lab/Lab04/ticketbooking-quickstart/requirements.yaml`: **upstream repo anomaly** (see §4.4). File content verified byte-identical to what GitHub actually serves.

Post-state: `git ls-files Lab/ | missing-on-disk` count = **0**. `git status --short` = the 3 `M` files only.

### 2.4 Other files
- Logs: `C:\Users\dayuruozhi\AppData\Local\Temp\rehearse-gui.log`, `rehearse-gui2.log`, `rehearse-gui3.log` (3 rehearsal runs).
- Helper scripts (agent-made, still in user temp): `fix9.ps1` (ghfast 9-file download+hash-verify loop), `verify44.ps1` (523-file raw-vs-filtered hash audit). Harmless to delete.
- Early-session HTML "readiness board": one-time renderer output, **no persistent file**.
- `.git/objects/pack/` temp garbage: 10 × `tmp_pack_*` (~135.3 MB) from interrupted lazy fetches — **deleted** (safe; git never references them).

---

## 3. COMMANDS (all verified on this machine)

### 3.1 Lab02 lifecycle (MUST prefix with real node)
```powershell
Push-Location "D:\agentic-software-engineering-hackathon\Lab\Lab02"
& "D:\nodejs\npm.cmd" run doctor          # env/endpoint/model check — [ok] READY
& "D:\nodejs\npm.cmd" run demo:api        # online API demo — earlier best: TDD 54/55 vs Direct 44/55
& "D:\nodejs\npm.cmd" run rehearse:gui -- --no-interactive --no-open   # offline, ~3–4 min, zero cost
& "D:\nodejs\npm.cmd" run typecheck       # passes
```

### 3.2 Git state & verification
```powershell
$repo="D:\agentic-software-engineering-hackathon"
git -C $repo status --short
git -C $repo rev-parse HEAD               # 1d1f0bb…
git -C $repo -c http.version=HTTP/1.1 fetch origin main    # works; origin/main confirmed current
# missing-on-disk check:
git -C $repo ls-files Lab/ | Where-Object { -not (Test-Path (Join-Path $repo $_)) }
# per-file byte verify (single authoritative form for text under autocrlf=true):
git -C $repo hash-object --path=Lab/Lab04/demo_full.zip "D:\...\Lab\Lab04\demo_full.zip"   # == tree blob SHA
# raw (no CRLF filter) comparison:
git -C $repo hash-object --no-filters <file>
# independent ground truth (bypasses git hash-object quirks):
[Security.Cryptography.SHA1]::Create().ComputeHash([IO.File]::ReadAllBytes($f)) | ForEach-Object {$_.ToString('x2')} -join ''
```

### 3.3 Network channel matrix (Step 2, from China network; Japan may differ)
| Channel | Result |
|---|---|
| `git ... fetch origin main` / small lazy fetches | WORKS (single small blobs OK) |
| Lazy fetch of large batch (sparse-set on `Lab`) | HANGS/dies mid-transfer (curl 18 early EOF; left tmp_packs) — do NOT retry naively |
| `raw.githubusercontent.com` | curl 28 connect timeout (blocked) |
| `cdn.jsdelivr.net/gh/<owner>/<repo>@main/<path>` | WORKS for files ≤20 MB; **>20 MB → 404 placeholder**; occasional "Package size exceeded 50 MB" / stale cache → ALWAYS hash-verify |
| `fastly.jsdelivr.net/gh/...` | connection reset |
| `ghfast.top/https://raw.githubusercontent.com/...` | **WORKS incl. 50 MB+ binaries**; stalls possible → use `curl -C -` resume + retry loop |
| `git fetch origin <blob-sha>` | REJECTED by GitHub ("did not send all necessary objects") — cannot fetch blob by bare SHA |
| `git fetch --refetch` | NOT available (git 2.33; needs 2.38+) |

Resilient download pattern used: per-file loop, `curl.exe -L -C - --connect-timeout 15 --max-time 240 -sS -o <tmp> <url>`, verify `git hash-object --path=` against expected SHA, `Copy-Item` on match, ≤6 attempts.

---

## 4. TECHNICAL POINTS / GOTCHAS (things Codex must know before touching this repo)

### 4.1 Playwright on Windows — absolute paths kill test collection
`playwright test <abs-drive-path>` collects **0 tests** ("No tests found"). Relative POSIX paths collect all 36.
Fix (applied): both `run-validation.ts` and `run-generated-tests.ts` now pass `projectRelativePath()` output (relative to projectRoot, `/` separators) for the spec positional arg AND the `--config` arg; `runProcess` cwd = projectRoot.

### 4.2 Subprocess env is WHITELISTED (`src/testing/process.ts` → `filteredEnvironment`)
Only `SAFE_ENVIRONMENT_KEYS` (PATH, PATHEXT, SystemRoot, WINDIR, COMSPEC, TEMP, TMP, TMPDIR, HOME, USERPROFILE, LOCALAPPDATA, APPDATA, LANG, LC_ALL, TERM, NO_COLOR/FORCE_COLOR + custom) + now `PLAYWRIGHT_BROWSERS_PATH` pass through to agent/test subprocesses. Any other env var (API keys, proxy vars) is STRIPPED — add to the whitelist deliberately, not by hope.

### 4.3 autocrlf / hash verification trap
`core.autocrlf=true`, no `.gitattributes`. `git hash-object --path=` applies the CRLF clean filter; `git hash-object --no-filters` is raw; the two disagree for any working file whose disk line-endings differ from the blob. For **verification**, prefer: raw compare via `--no-filters` for binaries; `--path` for LF-committed text; `.NET SHA-1` + `git cat-file blob <oid> | byte-compare` as the absolute ground truth. Plain `git hash-object <file>` ALSO applies filters here (observed). Do not trust a single git hash-object call for a verdict on text files.

### 4.4 requirements.yaml upstream anomaly (IMPORTANT — do not "fix")
`Lab/Lab04/ticketbooking-quickstart/requirements.yaml` (6648 B, CRLF):
- Tree oid (origin/main): `c31bf8292d341dd7c0f452f7919984ff89f672a3`
- Actual stored blob content raw SHA-1: `d14aca94fdc6e816f95bb2fe0fc0d5ca7c7d12ab` (oid/content MISMATCH in the upstream repo; object is valid, fsck-clean — the pack is self-consistent under the WRONG oid)
- CRLF→LF filtered hash: `e23b114dce17882f728aacd35eaafc9a59102889`
- Three independent channels (jsdelivr pinned to commit `1d1f0bb…`, `git cat-file blob c31bf829…`, .NET SHA-1) all confirm the on-disk file == what GitHub serves for that path.
- Consequence: `git status` may show this file as `modified` forever (git compares filtered hash `e23b114d` vs index oid `c31bf829`). This is EXPECTED and upstream-caused. Do not commit it, do not "restore" it.

### 4.5 Sparse/partial-clone DON'Ts
- **DO NOT run `git sparse-checkout set Lab`** — it triggers a lazy fetch of missing blobs (object store is INCOMPLETE for the 44 externally-downloaded files; they exist on disk only). On this network it hangs for 15+ min and leaves `tmp_pack_*` garbage.
- Lab01/03–07 files are skip-worktree (outside cone `Lab/Lab02`): `git status` ignores them (good), but a future `git checkout .` / cone change could prune them. For git-proper tracking: complete the object store first (e.g., re-clone full or fetch all blobs on a stable network — from Japan, raw.githubusercontent may now be reachable).
- If a lazy fetch is killed, clean `tmp_pack_*` in `.git/objects/pack/` and stale locks (`.git/index.lock`, `.git/info/sparse-checkout.lock`) before retrying.

### 4.6 jsdelivr behaviors
- File >20 MB → 404 placeholder page (small HTML, curl `-sS` exits 0 → "success" check must be hash, not exit code/size).
- Whole-package >50 MB → per-node errors; different edge nodes return different things — always verify hash.
- Stale cache possible on `@main`; use `@<full-commit-sha>` to pin.

---

## 5. VERIFICATION LEDGER (how "done" was established)

| Claim | Method | Result |
|---|---|---|
| rehearse:gui passes | 3rd run `20260915T144956Z-gui-fe64c72d`, exit 0, result.json | Direct 8/36 → initialTrain RED(1/3) → repair 1 → finalTrain GREEN(3/3) → **TDD 36/36** (9/9,9/9,10/10,8/8) |
| typecheck green | `npm run typecheck` (D:\nodejs) | pass |
| 44 files on disk | `git ls-files Lab/` missing-count query | 0 missing |
| 43 files byte-correct | `git hash-object --path` == tree blob SHA | 43/43 (incl. all 6 big binaries) |
| requirements.yaml correct | jsdelivr@commit + `git cat-file blob` + .NET SHA-1 cross-check | disk == GitHub-served content (upstream oid anomaly, §4.4) |
| git clean | `git status --short` | exactly 3 `M` files (§2.1) |
| origin/main current | `git fetch origin main` then `rev-parse` | HEAD == origin/main == `1d1f0bb…` |

---

## 6. OPEN ITEMS / CONSTRAINTS FOR NEXT SESSION

- [ ] (optional) From Japan, test if `raw.githubusercontent.com` is now reachable; if yes, consider completing the object store (`git fetch` all blobs / full re-clone) so sparse cone can be expanded properly — only if user wants git-proper tracking.
- [ ] Do NOT expand sparse cone or run destructive git ops without that.
- [ ] Any new npm/npx command against Lab02 must use `D:\nodejs\npm.cmd` (course requires Node v24; agent shell node is v22).
- [ ] If Playwright is re-installed/updated: browsers must land in `D:\ms-playwright` (keep `PLAYWRIGHT_BROWSERS_PATH` at User scope) and the whitelist entry in `process.ts` must stay.
- [ ] requirements.yaml phantom-`M` is expected; leave untouched.
- [ ] API key in `.env` is live (arc-bench endpoint) — never print it.
