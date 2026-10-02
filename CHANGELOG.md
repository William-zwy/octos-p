# Changelog

All notable changes to octos will be documented in this file.
## [Unreleased]

- Deploy a serialized ARC cloud optimization controller using pinned arcbench-cli and Codex exec: durable mutation intents, full paginated evidence, Git/CI/package identity gates, and updates to the existing HKT records. Paid runs stay disabled until the current budget, deadline and suite binding are supplied.
- Add a deterministic post-collection analysis layer that writes `analysis.json`, separates platform facts from log observations and local manifests, preserves unknown evidence, and feeds bounded implementation guidance to the next Codex worker. Existing Run collection remains read-only.
- Extend the ARC controller with metadata-only evidence ingest, branch context snapshots, legacy-run forensic reconstruction, and `optimization-plan.json`; default execution policy remains `plan_only` until Agent edits, packaging, and cloud runs are explicitly enabled.
- Add an explicitly authorized, isolated codegen stage: the worker runs in a disposable worktree bound to the exact parent/plan/analysis hashes, emits a schema-v2 result and patch into external state, and stops at `candidate_review` for Integrator review. Missing or conflicting external monitor reports remain `NEEDS-EVIDENCE`; harness/tests/package/cloud actions and Skill invocations are rejected in this stage.
- Add an explicit Integrator `approve` gate that applies a reviewed candidate patch only after parent, patch, path, and post-apply diff verification; expose `reconcile` and `approve` through the PowerShell launcher.

### ARC-Bench Agent

- Share a named-entity create/save result contract across UI, design, codegen and repair prompts: show the persisted name as one visible heading, preserve its navigation link and avoid duplicate success text. Add prompt regression tests; generated-app and platform validation remain pending.
- Add a requirements-driven workflow-state contract for existing context fixtures, distinct draft authoring steps, editor-scoped auxiliary properties, filter persistence, and single-owner sign-in navigation. Add frozen BookStack/Keep locator-source regressions and a standalone Playwright scope smoke; prompt tests and the synthetic-DOM browser smoke pass, but generated-app and platform behavior remain unverified.

### ARC-Bench collaboration

- Verify and acknowledge the four dedicated Phase 5 task identities; record their worktree mapping and complete a read-only Keep intake pilot without enabling automatic dispatch.
- Split phase 5 responsibilities into cross-run decision, isolated reproduction, Agent implementation, and metrics/A-B review; document verified handoffs, approval gates, and compact context transfer without changing the Agent or official tests.
- Record the confirmed Run-local Keep evidence revision `737b56972d5a` as P5-010/P5-011, retain the superseded pilot revision, and require explicit authorization before any Agent implementation or platform A/B work.
- Record controlled reproduction of BookStack Lite `P5-009` for both save flows; keep implementation authorization and platform identity gates unchanged.
- Record the `P5-009` external evidence refresh as an audit-only revision; preserve the existing repro-verified, no-dispatch decision.
- Register Lite BookStack Run `4ef2cf139806` as a conditional `needs_repro` intake, keeping it separate from prior BookStack runs and without dispatching downstream work.
- Register the authorized `P5-009` local implementation candidate `d2fe4dbc7601242896b61b3a790a912732bc5d57` as locally verified only; preserve the platform build, task-snapshot, ZIP, and A/B gates.
- Register ticket-booking Run `1aac5ece078e` as a passed 10/10 baseline with no issue or repro dispatch; retain the missing build/task-snapshot/ZIP binding as an identity gap.
- Register the A0/V1/V2/V3 Lite Agent lineage and same-manifest-configuration descriptive BookStack/Keep sequences from handoffs `phase5-lite-lineage-ledger-20260921-v1` and `phase5-lite-lineage-ledger-manifest-20260921-v1`; keep platform build and task-snapshot binding as the strict A/B gate.
- Register Keep Lite Run `ff12a7ff45f8` as `P5-012`, a pre-test authentication/generation gate requiring isolated reproduction; exclude its `0/0` result from business completion comparisons.
- Register BookStack Lite Run `d4acec5dbbdf` as `P5-013`, a pre-test package-shape/generation gate; keep its `0/0` result out of business comparisons and preserve raw-log uncertainty.
- Freeze V3 at `d2fe4dbc7601242896b61b3a790a912732bc5d57`, record the user-reported manual upload and prior A/B authorization, and set the current business/platform-benefit gate to no-go until P5-012/P5-013 and platform identity are closed.
- Archive the authorized V3.1/V4 control-plane slices on branch `codex/arc-bench-v4-control-plane-gates` and record the byte-bound candidate `octos-arc-bundle-13173bb50e55.zip` with its passing root-shape manifest and SHA-256; no platform upload or Run was performed by this workspace.
- Make the Phase 5 ledger task decision-only: it may consolidate evidence and maintain decision records, while every future direct code change must be handed to the dedicated `项目阶段5｜Agent 实现` task.
- Register BookStack Lite Run `cca008377368` as an independent `P5-012` recurrence: the platform observed HTTP 401 fail-fast exit 2 before generation, while source/build identity and an authenticated positive path remain unverified; exclude its `0/0` result from business completion and do not merge the resulting empty template into `P5-013`.
- Quarantine Keep Lite Run `bf5e742c15a4` at Phase 5 intake after two empty Phase 4 turns and a late result with incomplete structured identity; do not consume its diagnosis, create an issue, or dispatch implementation until the existing Phase 4 thread is reconciled.
- Record the user's explicit provenance that BookStack `cca008377368` and Keep `bf5e742c15a4` are the frozen V3 Run IDs; retain the unresolved conflict with both manifests naming `octos-arc-bundle-13173bb50e55.zip`, and do not upgrade either Run to platform-bound identity or business A/B evidence.
- Archive the complete Phase 3/4 evidence pair for BookStack Run `a774fb34f1b6` and Keep Run `82a833cabe9e`; preserve confirmed mechanism boundaries, unresolved Keep failures, artifact hashes, and the rule that the pair is not strict A/B evidence.
- Archive Web BookStack Run `53a102f3ee96` as a separate `34/34` positive baseline with complete read-only Phase 4 diagnosis; retain its orchestration and provenance gaps without dispatching Agent changes.
- Archive Lite Keep Run `8ea6503bfa95` as `18/32` with the confirmed task-suite routing mismatch, UI contract clusters, pin seed candidate, and complete read-only Phase 4 diagnosis; defer maximum-applicability Agent changes until more Runs are collected.
- Authorize, implement and locally verify the V4.1 `P5-005` build-provenance slice from candidate `13173bb50e556c78bcd9cfdcc25c5449eee37f65`; record implementation `bb70542d7d327b660fa672bfdbc193f3f51b40a5`, build identity `arc-agent-v1-0851fff1cfb8feeb38544f8c`, ZIP SHA-256 `680BA38F027F5CF5E60641362D041B791E952771171D3C7F4CAF85794F186783`, passing 401/403/known-good control-plane reproduction and exact-artifact conditional platform-test readiness without changing business prompts or official tests.
- Register smoke-evolution Dice Run `c48754c25fcf` as a `P5-012` platform-authentication recurrence: the exact V4.1 identity reached `main.py`, while both meter baseline and Agent probe returned HTTP 401 and the expected fail-fast exit 2; route remediation to the platform credential/authorization context, not Agent code or repackaging.
- Refine the `c48754c25fcf` diagnosis after the user confirmed the API is unchanged: compare successful Run `61f91039fbfb` and three probe implementations, rule out a V4.1 Authorization/path regression, distinguish meter and generation services, and prioritize platform secret-reference, whitelist or gateway-auth state drift.
- Receive BookStack Lite `1b0eaf914e94` at Phase 5 as `P5-014`: V4.1 generated and ran all 34 tests with only `REQ-2.2` failing at login nickname readback; require exact-template controlled reproduction before any Agent code change or business/A-B claim.
- Record `P5-014` exact-template isolated reproduction: frozen `REQ-2.2` fails locally despite successful login/session and visible nickname text, which is not a heading; retain platform-helper and A/B identity gaps and require separate authorization before Agent changes.
- Record the user-authorized `P5-014` local Agent candidate `7f3c0b0c0175701eb8ef6f19776885c521da5e9f` and ZIP SHA-256 `95A414940F5BC69DF4A9ED7EC497A3BBFFDB14697714F8F123A1AEAA03A17D99`; distinguish six old-template semantic-control passes from unproven new-Agent generation, retain the Windows full-suite failures, and keep Keep Run `88c08161c4d3` upstream until Phase 4 identity reconciliation.

### Features

- Smart Home control — list and control smart-home devices (lights, thermostats, curtains, etc.) via a per-profile bridge (e.g. Home Assistant), through both the UI Protocol (`smart_home/*` WS methods, backing octos-web's Smart Home panel) and a new bundled `smart-home` agent skill (`smart_home_list_devices`, `smart_home_control_device`). Camera video streaming stays a human-facing, WebSocket-only feature and is not exposed to the agent.

### Changed

- Per-tenant frps tunnel authentication via `metadatas.token`. Each tenant now has its own `tunnel_token` (UUID generated at registration) validated by the octos frps server plugin; the previous shared FRPS auth token is no longer needed and `auth.token` is set to `""` on both frps and frpc. `scripts/install.sh` and `scripts/install.ps1` recover the per-tenant token from an existing `/etc/frp/frpc.toml` on rerun and have updated prompt wording to reflect the per-tenant model.
- README "Quick Start" restructured into a three-step cloud-deployment walkthrough (VPS bootstrap → portal registration → tenant install) with explicit uninstall instructions for both cloud and tenant machines. The developer build flow moved under a new "Build from source" heading.

## [0.1.1] - 2026-04-07

### Highlights

- **Slides Studio** — End-to-end AI slide generation pipeline with policy-driven provider chains and task status tracking
- **Content Management** — Per-profile content catalog, directory tree browser, and workspace scanner
- **Multi-Platform Channels** — Matrix Appservice, QQ Bot (Official API v2), WeCom Group Robot WebSocket
- **Deep Search** — Exa neural search, Serper.dev, Tavily, Google CDP fallback with smart engine routing
- **Sandbox by Default** — AppContainer sandbox for Windows, per-profile isolation, sandbox enabled by default
- **Deployment** — Auto-HTTPS with `--caddy-domain`, Windows installer, tenant self-registration, cloud/local/tenant modes
- **Skill Version Check** — Pre-clone registry version comparison skips unnecessary downloads on `skills update`

### Features

- Slides studio end-to-end pipeline with policy-driven provider chain and task status checks
- Content panel with directory tree, workspace scan, and markdown viewer
- Per-profile content catalog with REST API
- Per-user soul/personality customization via /soul command and API
- AppContainer sandbox for Windows
- Per-profile sandbox isolation and skill directory layering
- Matrix Appservice channel with BotFather architecture
- QQ Bot channel with Official API v2 WebSocket gateway
- WeCom Group Robot WebSocket channel
- Discord reactions, embeds, and message dedup
- Exa neural search as top-priority web search provider
- Serper.dev as first-priority search engine in deep-search
- Tavily web search provider
- Google CDP search fallback via headless Chrome
- Smart search engine routing exposed to parent LLM
- Delta streaming for API channel (token appends instead of full replace)
- SSE progress events forwarded through API channel for web client
- MSC4357 live message markers for streaming edits
- Auto-HTTPS with `--caddy-domain` and on-demand TLS
- Windows install.ps1 auto-installs deps, Caddy, and firewall rules
- Playwright e2e testing via `--test` flag in deploy.sh
- Tenant self-registration with POST /api/register and setup scripts
- Cloud/local/tenant deployment modes via config.json
- spawn_only tools — deferred in main session, available in subagents
- Auto-redirect spawn_only tools to background spawn with retry and notify lifecycle
- spawn_only_message configurable per tool in manifest.json
- Universal auto-send hook — detect and deliver files from any plugin output
- Two-tier deferred tool dispatch with activate_tools meta-tool
- Composable multi-layer status system with per-user config
- Bot owner and visibility model with default-private enforcement
- Message metadata annotations and QoS model catalog
- Profile-scoped routing and sender identity infrastructure
- Pipeline executor observability and model catalog baseline
- API channel file download endpoint and SSE file events
- Pipeline-guard hook owns model selection
- Unified QoS model catalog as single source of truth
- Default to top-2 engine racing instead of single-best
- Native Windows support
- Dashboard skills page and sidebar refactor
- Per-profile sandbox isolation and skill directory layering
- Plugin loader returns MCP servers, hooks, and prompt fragments from skills
- Version check on skill install, add update action
- Pre-clone version check for skill updates — skip clone if already up to date
- Deep-search saves to OCTOS_WORK_DIR, agent sends report via send_file
- HTML boilerplate cleaning, adaptive stream timeout, GLM-5 provider
- Voice cloning with x-vector profiles
- Streaming support for WeCom bot channel
- Persist OTP auth sessions to disk across server restarts

### Security

- SSRF redirect bypass and DNS failure fallthrough hardened in web_fetch
- CORS wildcard replaced with explicit origin allowlist
- Path traversal in hook tilde expansion validated
- admin_shell endpoint disabled by default via config flag
- X-Profile-Id auth restricted to loopback origin
- Sandbox enabled by default (SandboxMode::Auto)
- Spawn tool restricted to append-only prompt instructions
- Sensitive data redacted from hook payloads
- Send_file path validation prevents cross-profile file exfiltration

### Bug Fixes

- Loop detection breaks agent loop instead of just warning
- Stronger spawn_only message to prevent LLM retry loops
- Model-specific max_output_tokens defaults instead of 8192
- SSE byte-buffer prevents UTF-8 corruption of CJK characters
- Concurrency cap added to pipeline parallel fan-out
- Global timeout cap added to ProviderChain (default 120s)
- Process allocation race in ProcessManager
- HNSW capacity fallback to BM25-only search
- Eliminate production unwrap/expect calls
- Report_late_failure penalizes correct provider slot
- Wrap blocking I/O in spawn_blocking (cron_service, session)
- Plugin auto-deliver checks work_dir, cwd, and output text
- SSE grace period now triggers when spawn_only tools exist
- Upload body limit raised to 100MB for file attachments
- Forward all non-audio media to agent
- Content catalog only scans profile data_dir
- Deferred file events for web clients when SSE connection is closed

### Infrastructure

- Version management with cargo-release and git-cliff
- GitHub Actions bumped: checkout@v6, upload-artifact@v7, download-artifact@v8, setup-node@v6
- Caddy config updated to proxy all requests to octos serve
- Cloud host deploy script and local-tenant-deploy.sh added

## [0.1.0] - 2026-03-05

### Bug Fixes

- Address critical and high review findings in streaming code
- Shutdown check during streaming, buffered stdout, robust session keys
- Remaining review items — retry, error truncation, atomicity, CJK
- Address 18 security and quality review findings
- Reject absolute paths, expand env blocklist, add security tests
- Close path traversal in list_dir and glob, harden sandbox
- Add symlink checks, SSRF protection, glob traversal, spawn depth
- Close IPv6 SSRF bypass in web_fetch private host check
- Block site-local and IPv4-compatible IPv6 in SSRF filter
- Block IPv6 multicast in SSRF filter
- Handle RwLock poisoning, eliminate TOCTOU, hash all config files
- Eliminate duplicate index entries and log poisoned locks
- Validate embedding dimensions and prevent UTF-8 slice panic
- Enforce provider policy at execution time and propagate to subagents
- Harden sandbox path validation and session file uniqueness
- Address remaining review findings across sandbox, coalesce, session
- Unify env blocklist, add UTF-8 safe truncation, improve error handling
- Block sandbox injection via newlines and SBPL parens, extract truncate_utf8
- Reject backslash and quote in macOS sandbox paths
- Prevent process leak and stdin race in hook executor
- Improve hook robustness for circuit breaker, success, and denials
- Harden browser tool with 6 security and quality fixes
- Resolve 8 audit issues across security, correctness, and perf
- Resolve remaining audit items C4 and S3
- Resolve 7 review findings (2 critical, 5 high)
- Close 3 remaining high-priority review findings
- Resolve 7 medium-priority review findings
- Resolve 5 low-priority review findings
- Resolve remaining audit items C4 and S3
- Add tests and harden blame/diff/parse edge cases
- Resolve 30 audit findings across security, quality, and architecture
- Merge system messages for MiniMax compatibility, add credential scrubbing and Gemini metadata
- Add allowed_senders to Telegram channel profile, improve dashboard tabs
- Webhook proxy only allocates port for Feishu webhook mode, share reqwest client
- Handle Feishu url_verification challenge at proxy level, return JSON errors
- Return JSON error responses from Feishu webhook handler
- Filter empty assistant messages and show model name in API errors
- Cron consent requirement, name-based removal, and silent response suppression
- Improve cron remove discoverability — LLM now knows to use name-based removal
- Plugin loader permission denied on .main_verified + dedup plugin dirs
- Suppress status indicator for cron/system messages
- CORS allow any origin, add Twilio channel, improve error logging
- Admin token login fails when user_store is None
- /api/my/* endpoints now work with admin token auth
- Use JSON merge patch for profile updates to preserve channels/env_vars
- Process leak prevention, UTF-8 safe truncation, headless Chrome
- Add missing platform-skills/asr/SKILL.md to git
- Weather skill multilingual geocoding support
- Filter platform models to Qwen3 ASR/TTS, weather geocoding tweaks
- Use contains() for [SILENT] cron check instead of starts_with()
- Allow unsafe in SwappableProvider lifetime extension methods
- Add SwappableProvider leak_str approach and SwitchModelTool

### Documentation

- Update README, PRD, architecture, and user manual for Phase 8
- Update README, PRD, architecture, and user manual for Phase 9
- Update all docs for OAuth, email, media, vision, voice, skills, Docker
- Update docs for tool policies, sandbox, compaction, and coalescing
- Update PRD and user manual with new features
- Fix group:memory references, add diff_edit and group:search
- Expand ARCHITECTURE.md with detailed technical design
- Expand skills system section in ARCHITECTURE.md
- Expand plugin system section in ARCHITECTURE.md
- Expand progress reporting section in ARCHITECTURE.md
- Add feature parity analysis vs Moltis
- Update feature parity to reflect completed improvements
- Document hooks system in CLAUDE.md
- Mark hooks system complete in feature parity doc
- Update all docs for browser automation tool
- Update browser tool docs with security hardening details
- Sync docs with codebase after recent feature additions
- Update docs to reflect audit hardening changes
- Update CLAUDE.md with audit hardening details
- Add deep technical audit report (2026-02-18)
- Comprehensive README with installation, channel setup, and dashboard guide
- Add search source registry design for Deep Research

### Features

- Add gateway messaging infrastructure (Phase 1)
- Add Telegram and Discord channel integrations (Phase 3)
- Add web_search and web_fetch tools (Phase 4)
- Add memory store, skills loader, and cron service (Phase 5)
- Add full gateway feature parity (Phases 6-7)
- Add interactive chat, system status, Zhipu provider, and onboard (Phase 8)
- Add ListDir tool, cron expressions, CLI subcommands, built-in skills, config migration (Phase 9)
- Add media handling, vision, voice transcription, skills CLI, Docker, WhatsApp login
- Add OAuth login (octos auth) and email channel (IMAP/SMTP)
- Add streaming responses and context window compaction
- Add full roadmap — pricing, MCP, sandbox, plugins, REST API
- Add tool policies, context compaction, and config hot-reload
- Add hybrid memory search (BM25 + HNSW vector similarity)
- Add provider-specific tool policies
- Add message coalescing, session forking, and Docker sandbox
- Execute tool calls concurrently via join_all
- Add wall-clock timeout, tool output sanitization, DNS SSRF protection, deny(unsafe_code)
- Add provider failover chain and SecretString for API keys
- Add MCP HTTP/SSE transport for remote servers
- Add hook/lifecycle system for agent events
- Add web UI, Prometheus metrics, and message queue modes
- Add browser automation tool via Chrome DevTools Protocol
- Implement 6 audit feature gaps across 5 phases
- Rewrite browser tool with chromiumoxide, add multi-LLM routing and deep research tests
- Add admin dashboard, multi-user profiles, security hardening, and 401 failover
- Add WhatsApp media reception, vision-aware content, Gemini thoughtSignature fix
- Add Feishu/Larksuite channel with webhook mode, web search logging
- Require user permission before taking photos
- Add Twilio channel for SMS/MMS/WhatsApp Business messaging
- Add dashboard multi-user auth with email OTP and user management
- Add base_url support and provider mapping to profiles
- Add webhook proxy for Feishu/Twilio, WebSocket default for Feishu
- Add tool config system, /config command, dashboard overhaul, and multi-provider improvements
- Add skill registry search and replace install-mofa with skill-store
- Add PersonaService for dynamic LLM-generated communication style
- Extract built-in skills and tools to external repos
- Restore system skills as built-in (cron, skill-store, skill-creator)
- Interactive research confirmation + fix /new to clear session
- Deep-search v2 — multi-round search, parallel crawl, reference chasing
- Deep search v1 — synthesize_research, adaptive failover, kimi fixes
- Sub-accounts, account-manager skill, hooks enrichment, admin bot, pipeline
- Add admin token login to dashboard login page
- Admin bot page reuses LlmProviderTab for full LLM setup
- Gateway stability — configurable timeouts, session guards, bus fixes
- Externalize system prompts + add admin_update_profile tool
- Admin bot refactor, cron timezone support, monitoring, dashboard updates
- Sub-account update/start/stop/restart, serve watcher enable/disable transitions
- Add update/start/stop/restart to account-manager skill
- Add sub-account dashboard UI, admin tools, and fix watchdog toggles
- Filter platform skills catalog to ASR+TTS only
- Add clock, weather, ASR app skills, voice architecture, admin tools refactor
- CI/CD workflows, self-updater, admin API enhancements, deploy improvements

### Miscellaneous

- Apply rustfmt formatting across workspace
- Apply cargo fmt formatting
- Add node_modules to .gitignore and remove from tracking
- Apply cargo fmt formatting

### Refactor

- Remove task mode (run/resume/list) and coordinator pattern
- Deduplicate truncation, configurable threshold, ~user expansion

## 2026-10-02

- `arc_optimizer` codegen worker now accepts only explicitly allowlisted external provider key variables (for example `RELAY_API_KEY`); ARC/platform credentials and other secret channels remain blocked, with missing keys failing before Codex starts.
