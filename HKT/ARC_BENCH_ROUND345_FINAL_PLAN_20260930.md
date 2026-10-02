# ARC-Bench Round 3/4/5 Agent 优化协作计划

日期：2026-09-30
状态：`REQUIREMENTS_V4_INTEGRATED`（Agent 与官方需求输入已完成归档） 当前只更新需求证据、项目记忆和计划；未修改官方测试或平台 Run。
目标分支：`codex/hkt-round345-integration`
基线：`codex/urgent-bookstack-contract-fix-r2` @ `f10bd9f42429c09672c9a68b79f486c44cc41e9f`

## 1. 最新决策

用户已接受新分支名，并要求在方案形成后直接开始 Agent 修改。新的硬约束是：

- 探索预算：`200–300 CNY`，建议目标 `250 CNY`，`300 CNY` 为硬上限。
- 剩余窗口：`36 小时`，必须冻结并提交终版。
- 新题官方测试/snapshot 不公开，不能宣称平台因果 A/B。
- 优先级：提高完成率 > 防止配额/超时中断 > Token/耗时优化 > 完整领域架构。
- 后续优化不得绑定旧题名称、旧 REQ 编号、旧实体或旧 locator。

因此原计划的“四个 Run 串行、严格 A/B、先做完整架构”已收缩为：

1. 先实现一组高收益 runtime 硬门禁。
2. Sheet 做第一主探针；只有成本和时间都在阈值内，才运行 GitHub 探针。
3. 每题最多一次探索性 Run，必要时一次定点修复；不称为严格 A/B。
4. 至少保留 25% 预算给 final check、定点修复和终版证据。

## 2. 原计划（预算调整前）

原计划拟在 `codex/hkt-round345-integration` 中从指定基线整合 Round 3/4/5，并安排 Sheet A/B、GitHub A/B 共四个串行 Run，预算约 `1600 CNY`、窗口约 `72 小时`。

原计划的实施顺序：

1. quota guard、usage ledger、project/source map shadow；
2. Round 4 有界 rewrite budget；
3. Round 5 impact regression shadow；
4. Round 3 checkpoint/observability；
5. source-cache/context shadow；
6. 最后才启用实际 context compaction 和 repair strategy switch。

原计划的主要收益：较完整地覆盖额度、长上下文、循环修复、恢复和跨节点回归。主要问题是预算不足时无法完成四组 Run，且会把架构建设成本置于比赛交付之前。

## 2A. 当前已落地的第一批改动

为满足“方案确定后直接出手”，当前分支已先实现以下最小切片；每项均保留短注释、测试和 checkpoint 证据：

- `arc/llm_proxy.py`：识别 `402` 与带 billing 标记的 `429`，第一次命中后进入代理级 `quota_gated`，后续 chat completion 直接拒绝；额度错误不再进入 transient retry。
- `arc/run_controls.py`：新增原子 JSON checkpoint store，临时文件 flush/fsync 后 rename，保留编号快照和 manifest。
- `arc/main.py`：写入 requirements/spec/build identity；在 run/node/turn/acceptance/quota 边界写 checkpoint；quota-gated 跳过剩余节点、full-suite repair 和 rehearsal；区分 implemented、built、smoke_verified、acceptance_verified、inconclusive；将多节点 rewrite 从无界改成有限预算；同一 failure digest 重复后切换策略并停止；读取缓存和 omitted-range 摘要避免超限后整文件重读；允许两种后端入口路径，降低结构检查器误报。
- `arc/tests/test_llm_proxy.py`、`arc/tests/test_main_helpers.py`、`arc/tests/test_run_controls.py`：覆盖 billing gate、有限 rewrite、spec omitted 摘要、回归上限和 checkpoint 原子写入。

本地定向验证：`58 tests` 通过；`py_compile` 和 `git diff --check` 通过。完整测试集合仍有基线中的 Windows 临时目录权限、npm cache 路径和路径分隔符断言问题，未归因于本切片。测试命令必须从 `arc/` 目录运行，避免把仓库外部同名 `tests` 包误当作项目测试。

### 2C. 首次打包门禁（已落地，平台前置）

Round 3/4/5 的运行时保护只有在交付包不丢文件、身份不漂移时才有意义，因此新增提交 `61ab832c`、`f086f729`、`2b35512a`：

- `arc/pack.ps1` 与 `arc/pack.sh` 都纳入 `run_controls.py`、构建身份和包形状门禁；Windows 使用 Python ZIP 写入，Git Bash 通过 `cygpath` 将 Python 参数转换为原生路径。
- `agent-build.json` 绑定源提交、payload tree SHA 和 build id；sidecar 绑定 task key、suite key、需求包 SHA 与最终 ZIP SHA。
- 离线解包后执行 `import main` smoke，并拒绝危险/重复/禁止条目、缺失身份和 placeholder identity。
- 当前 [需求包 v4 远程镜像](https://github.com/William-zwy/octos-p/raw/codex/hkt-round345-integration/evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.zip) 的 SHA-256 为 `8F07E80BE1DB82F68F7AB373ACBD3AF28B735D719B83751D0A378C1043960BF9`；完整差异见 [v4 manifest](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.manifest.json)。v3 的 SHA-256 `9884F23EA10C3DFEEE170D1EED57966C8FCE9A5CE18A0AC43B3D7942EBA8C414` 仅保留作历史输入。正式上传前必须使用平台实际分配的 suite key，不能用本地猜测值冒充官方绑定。
- 当前 ZIP 仍包含 `public-tests` 作为本地回归夹具；它不是新题私有官方 suite，也不能作为官方成绩证据。若发布流程要求最小包，应在平台契约明确后再单独裁剪并重新计算所有 SHA。

门禁验证：从 `arc/` 运行定向测试共 `60`（`OK, skipped=1`；唯一跳过项是本机没有独立 `sh` 命令的语法测试）；递归 `py_compile`、`git diff --check`、`node skills/arc-project-context/test.js`（8 assertions）通过。PowerShell 和 Windows Git Bash 两条打包链路均使用真实需求包 SHA 完成结构/离线导入检查；Git Bash 自动跳过无 PyYAML 的 Windows Store `python3` shim，选择可用解释器。修复提交为 `a77443c0c960adf23eb0a01f5e87f4c31453e2e5`，已由 Integrator 接入。

### 2B. 通用上下文 Skill 已落地

已新增可调用 Skill：`skills/arc-project-context/`。

- `project_map`：对工作区做一次有界文件/目录索引，排除 `.git`、`.arc`、`node_modules`、构建产物和缓存目录，并返回稳定 `project_map_hash`、入口/路由/模型线索。
- `source_read`：按 `path + SHA-256 + 行范围 + max_chars` 缓存读取结果；文件变化自动失效；超限时返回 `excerpt`、`returned_line_range` 和 `omitted`，避免 Agent 重新读取整文件。
- 缓存写入 `.arc/context-cache/cache.json`，采用临时文件改名；Skill 不执行 shell、不修改源码、不承担 quota/checkpoint/预算/官方验收职责。
- `manifest.json` 使用标准 stdin/stdout 工具协议，输入路径经过工作区边界和真实路径校验，拒绝路径逃逸与外部 symlink。

验证记录：

- `node skills/arc-project-context/test.js`：退出码 `0`，8 项行为断言通过。
- `skill-creator quick_validate.py skills/arc-project-context`：退出码 `0`（脚本属于用户级技能环境，不纳入项目仓库）。
- 尚未进行平台 Run；本 Skill 的缓存命中率和最终比赛完成率仍需在后续探索性 Run 中观察，不能预先宣称因果收益。

开源复用审查：仓库已有 `arc/acceptance.py` 的 SHA-256 文件指纹逻辑、Rust `globset`/`walkdir`/`sha2` 依赖，以及 Agent 内部 `file_state_cache`；这些组件分别服务于 Python 验收、Rust 工具层和进程内文件状态，不能直接作为独立 Skill 的 stdin/stdout 入口。当前 Skill 因需零安装、跨 Windows/Linux 直接运行，使用 Node.js 标准库实现协议适配和原子缓存，不新增重复第三方依赖；其路径边界、SHA 指纹和忽略目录规则与现有实现保持一致。后续若宿主暴露 `file_state_cache` 或稳定的 `walkdir` Skill API，应优先替换此适配层，而不是继续扩展本地实现。

## 3. 新计划（36 小时终版）

### 3.1 P0：必须实现的高收益硬门禁

这些改动直接针对历史中断和错误判定，不依赖任何旧题：

1. **Quota hard-stop**
   - 第一次 `402` 或带明确 billing/quota 标记的 `429` 进入 `quota_gated`。
   - 原子写入 checkpoint 与 usage 摘要。
   - 禁止后续 LLM turn、repair、full-suite repair 和 billing retry。
   - proxy EOF 最多一次有界重试；连续两次立即停止当前 Run。

2. **预算隔离**
   - design、implement、node repair、full-suite repair、final check 分开计量。
   - rewrite 不再使用多节点 `0=requests` 的无界预算。
   - rewrite 最多一次，预算为 `remaining - final_reserve`，并要求 rewrite 后 build/start/smoke。

3. **状态分离**
   - 分开记录 `implemented`、`built`、`smoke_verified`、`acceptance_verified`、`official_verified`、`inconclusive`。
   - `wrote=True`、`implemented` 或中间 runner passed 不能升级为 verified。
   - 没有真实测试证据时只能是 `inconclusive`。

4. **Repair 防循环**
   - 失败生成结构化 digest 和类别。
   - 同一 digest 第二次出现时切换策略；继续出现则停止，不重复同一 prompt。
   - 回归时恢复 best checkpoint，而不是接受局部通过但破坏旧功能的状态。

5. **Suite/build 身份 fail-closed**
   - 记录 task key、suite key、requirements hash、spec hash、Agent commit/build、submission/ZIP SHA（若平台提供）。
   - 发现 suite 与任务不匹配、身份字段缺失或内部 suite 与官方 suite 不同，标记 `identity_inconclusive` 并停止，不继续消耗 repair 预算。

6. **轻量 checkpoint**
   - 在 run start、node start、design saved、turn end、acceptance verdict、timeout、402、run end 写原子 checkpoint。
   - 第一版只支持同一 run、workspace 和 requirements hash 的恢复校验。
   - 不做跨机器 resume，不默认开启 run 级共享 session。

### 3.2 P1：低风险上下文/文件读取优化

第一版不做激进压缩，只做旁路和去重：

- `project-map`：输出入口、路由、文件、数据模型和稳定 hash。
- `source-cache`：按 `path + SHA + range` 缓存读取；写入后失效。
- `inline_sources` 和 `inline_spec_text` 不能因超限返回空串；应返回摘要、引用和 omitted ranges，避免模型重新读整文件。
- 记录 cache hit、读取字节数、prompt hash 和被裁剪区段。
- `change-impact` 先 shadow；无法建立影响面时不得自动扩张全量回归。

### 3.3 P2：Round 5 capped regression

- 只回归当前 node 的 spec、祖先 spec 和最多 `2–3` 个已通过 foundation spec。
- 改动文件未命中 foundation footprint 时不做全历史 backfill。
- 影响面未知时只记录建议，不自动启动更多 LLM 修复。

### 3.4 P3：新题通用语义契约

仅抽象跨任务能力，不写旧题字面量：

- 写入成功后原地更新，并用规范 URL 保持可刷新/可重开的状态；不无条件 full navigation。
- 实体动作位于目标实体自己的可访问作用域。
- `data-*` 写入字段与 handler 读取字段由单一契约生成。
- 认证成功跳转只有一个导航所有者。
- mutation 必须原子提交，失败不得留下半记录。

## 4. 为什么先做 Sheet，再决定 GitHub

新题需求暴露出的共同能力是 Identity/Session、Resource Graph、Scoped Action、Atomic Mutation、Route/Rehydration 和 Semantic Verification。

Sheet 更适合作为第一主探针：原子节点较少，先验证 workbook/worksheet/grid、持久化、规范 URL、grid 语义和 mutation 原子性。GitHub 原子节点更多，涉及认证、组织权限、仓库/分支、issue/PR/review/merge；只有 Sheet 没有触发 P0 告警且成本低于阈值时才运行。

官方 snapshot 不公开时，Run 结论只能标为 `exploratory`，不能把需求派生 smoke 或内部 suite 当作官方成绩。

## 5. 预算与运行策略

### 5.1 动态预算

建议以 `250 CNY` 为目标、`300 CNY` 为硬上限：

| 阶段 | 建议比例 | 250 CNY 参考 | 停止条件 |
|---|---:|---:|---|
| 实现与基础 smoke | 45% | 112 | 仍未 build/start/health 则不进入下游 |
| node repair | 15% | 38 | 同 digest 重复或无进展即停 |
| final check | 25% | 63 | 不得提前消耗 |
| contingency/提交证据 | 15% | 37 | 首次 402 或硬上限立即冻结 |

单题 Run 同时受费用和 request 上限约束，任一先触线即停止。余额低于 final reserve 时禁止 repair。

### 5.2 Run 矩阵

1. Sheet candidate：硬上限约 `40–70 CNY`，最多 `6 小时`。
2. 只有 Sheet 未 quota-gated、完成 build/start/health/smoke 且实际成本低于总预算约 40% 时，才运行 GitHub candidate：约 `80–130 CNY`，最多 `8–10 小时`。
3. 若 Sheet 已消耗过多、出现身份问题或 quota gate，放弃 GitHub 平台 Run，转本地终版交付。
4. 两个 candidate 各一次不能称严格 A/B；严格 A/B 至少需要三组闭合身份配对，本窗口不追求统计结论。

### 5.3 36 小时排程

| 时间 | 工作 | 交付门槛 |
|---|---|---|
| 0–4h | 分支、接口、checkpoint schema、测试夹具冻结 | 单写者和基线 SHA 明确 |
| 4–14h | P0 quota/预算/状态/repair；P1 source cache shadow | 本地单测可运行 |
| 14–18h | Integrator 合并、静态检查、打包和身份预检 | `py_compile`、diff check、smoke 通过 |
| 18–24h | Sheet 主探针 | 预算、quota、身份三项均正常才继续 |
| 24–32h | GitHub 探针或 Sheet 定点修复 | 不超过一次定点 repair |
| 32–34h | 证据归一化、失败分类、最终构建 | 不再新增大改动 |
| 34–36h | 冻结终版、提交、远程同步 | 工作树干净、SHA 可核验 |

## 6. 验收与 NO-GO

### GO

- quota gate 能在第一次 402/429 billing marker 后触发；
- 不再出现 402 后继续 repair；
- `wrote`、`implemented`、`verified` 互不混淆；
- checkpoint 可原子写入，损坏文件不会覆盖有效状态；
- 相同 failure digest 不会无限循环；
- suite/task/build 身份闭合；
- 没有新增本地硬失败；
- 官方 Run 若未完成，明确标注 `exploratory` 或 `partial`。

### NO-GO

- suite 身份不匹配或缺失关键绑定；
- 第一次 402 后继续计费调用；
- checkpoint 损坏导致覆盖源码；
- 中间 runner 状态覆盖最终官方结果；
- 新增通过率下降证据；
- 余额低于 final reserve 仍启动 full-suite repair。

## 7. 旧方案中不能直接照搬的内容

- Evolution 两个 Run 的分数不能相加，也不能视为严格 A/B；只能合并“原地更新、实体作用域、data-* 契约”机制。
- Keep `REQ-7.2`、`REQ-9.1` 等缺少 clean seed/精确 spec 的项目保持 `unknown`。
- `900s timeout`、proxy EOF、favicon、残留进程不是自动业务根因。
- Lite Keep 存在任务与 suite 错配，说明 suite identity 必须 fail-closed。
- Web Keep 出现提交物携带已运行数据库的污染风险，打包前必须隔离运行数据。
- “禁止 reload”需改为“写入后同文档更新、规范 URL 保持稳定”；新题要求刷新/重开恢复状态。

## 8. 已阅读资料索引

### 8.1 项目权威记录

- [项目记忆](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_HACKATHON_PROJECT_MEMORY.md)
- [阶段 5 决策台账](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md)
- [执行计划](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_HACKATHON_EXECUTION_PLAN.md)
- [阶段 5 协作工作流](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_HACKATHON_PHASE5_COLLABORATION_WORKFLOW.md)
- [阶段 5 上下文交接](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_HACKATHON_PHASE5_CONTEXT_HANDOFF.md)
- [项目摘要](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/SUMMARY.md)
- [变更日志](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/CHANGELOG_20260924.md)

### 8.2 Round 3/4/5 方案记录

- [Round 3 runtime plan](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/optimization-round-3-agent-runtime-plan-0927.md)
- [Round 4 rewrite budget](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/optimization-round-4-rewrite-budget-0927.md)
- [Round 5 core regression](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/optimization-round-5-core-regression-0927.md)
- [Round 2 application contract](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/optimization-round-2-application-contract-0927.md)
- [Round 1](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/optimization-round-1-0926.md)
- [Round 1 v2](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/optimization-round-1-v2-0926.md)

### 8.3 最近 Run 与 Evolution 证据

- [Evolution 配对交接](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_EVOLUTION_RUN_PAIR_HANDOFF_20260930.md)
- [Evolution 配对索引](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/evolution-run-pair-20260930.json)
- [Web BookStack Run 交接](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_WEB_BOOKSTACK_RUN_53A102F3EE96_HANDOFF_20260930.md)
- [Web Keep Run 交接](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_WEB_KEEP_RUN_C68BEF1A6343_HANDOFF_20260930.md)
- [Lite Keep Run 交接](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_LITE_KEEP_RUN_8EA6503BFA95_HANDOFF_20260930.md)
- [Web StackOverflow Run 交接](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/HKT/ARC_BENCH_WEB_STACKOVERFLOW_RUN_CA67B1D8EE97_HANDOFF_20260930.md)
- [Web StackOverflow 机器记录](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/web-stackoverflow-run-ca67b1d8ee97.json)
- [阶段 3 分析](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/runs/ca67b1d8ee97/phase3-analysis.md)
- [阶段 4 handoff](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/runs/ca67b1d8ee97/phase4-handoff.json)
- [阶段 5 协同索引](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/phase5-coordination.json)
- [阶段 4 线程注册表](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/phase4-thread-registry.json)

### 8.4 额度中断记录

- [Run E5CB3CA21874 quota 分析](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/quota/ARC_BENCH_RUN_E5CB3CA21874_QUOTA_INTERRUPTION_ANALYSIS.md)
- [Run 06612411282D quota 分析](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/quota/ARC_BENCH_RUN_06612411282D_QUOTA_INTERRUPTION_ANALYSIS.md)
- [Run FB4903ECEF12 quota 分析](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/quota/ARC_BENCH_RUN_FB4903ECEF12_QUOTA_INTERRUPTION_ANALYSIS.md)

记录摘要：三次额度中断均出现 timeout/proxy/repair guard 后仍继续计费；项目归纳分别报告约 `71/86`、`32/117`、`83/125`，并确认没有 OOM 作为主因。具体金额、请求数和哈希在最终 Run 前应重新从原文核验。

### 8.5 新题 requirements ZIP（v4 当前输入）

- [新题 requirements ZIP v4（远程镜像）](https://github.com/William-zwy/octos-p/raw/codex/hkt-round345-integration/evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.zip)
- [v4 机器清单与差异摘要](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.manifest.json)
- ZIP SHA-256：`8F07E80BE1DB82F68F7AB373ACBD3AF28B735D719B83751D0A378C1043960BF9`
- `hackathon--sheet/requirements.yaml`：Workbook、Worksheet、Grid、Formula、CSV、排序/过滤、验证、Pivot 等能力。
- `hackathon--sheet/reference/`：9 张界面参考图。
- `hackathon--github/requirements.yaml`：Identity、Organization、Repository、Version Control、Issue、Pull Request、Review、Merge、权限等能力；`47/100` 计数不变，但 `46/47` 个 atomic 的描述或 scenario 已更新。
- `hackathon--github-stage-1/requirements.yaml`：REQ-1/REQ-2，`12/30` atomic/scenario。
- `hackathon--github-stage-2/requirements.yaml`：REQ-3/REQ-4，`14/29` atomic/scenario。
- `hackathon--github-stage-3/requirements.yaml`：REQ-5/REQ-6，`21/41` atomic/scenario。
- `hackathon--github/reference/`：27 张界面参考图；Stage 1 有 5 张，Stage 2/3 各有 27 张。

#### 8.5.1 v4 对下一版 Agent 的直接约束

1. **需求身份必须升级**：所有候选包和 Run 侧车必须绑定 v4 ZIP SHA、具体 task key 和 stage key；不能复用绑定 v3 的候选 ZIP。
2. **GitHub fixture 不得共享复用**：v4 将多个场景改为独立账号/实体/权限 fixture。contract 编译器应按 scenario 提取 fixture variant，并在每次本地 smoke 前恢复对应副本。
3. **阶段优先级应可配置**：默认先用 Stage 1 做短探针，再按预算选择 Stage 2 或 Stage 3；完整 `hackathon--github` 仅在 stage 输入和身份门禁通过后运行。
4. **语义契约重编译**：精确 role/name、route、scope、permission、persist/reload 和 atomic mutation 必须从 v4 YAML 重新生成，不能使用 v3 缓存；Sheet 虽语义未变，也要在 sidecar 中记录其与 v4 的相同哈希。
5. **禁止把阶段拆分当成官方 A/B**：Stage 1/2/3 是新的官方需求输入和测试边界，不代表同一应用的可直接分数分解；每个 stage 的结果单独标识为 `exploratory`，不能与主任务成绩混算。

### 8.6 Agent 源码与运行时材料

- [Agent 主流程](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/arc/main.py)
- [LLM proxy](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/arc/llm_proxy.py)
- [Guard](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/arc/guard.py)
- [Acceptance](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/arc/acceptance.py)
- [Metrics](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/arc/metrics.py)
- [Run log collector Skill](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/skills/arc-run-log-collector/SKILL.md)
- [App Skill 开发指南](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/docs/app-skill-dev-guide-zh.md)
- `reliable-git-sync` 是用户级技能，不属于项目仓库；队友需在自己的 Codex 环境安装同名技能。

### 8.7 子智能体只读评估

- `budget_plan`：核算 36 小时/200–300 CNY 下的动态 Run 矩阵、止损线和交付排程。
- `r345_scope`：评估 Round 3/4/5 最小高收益并入范围、失败分类、checkpoint、rewrite 和 capped regression。

### 8.8 远程发布产物

- [Sheet Agent ZIP（1821c3f5 修复候选）](https://github.com/William-zwy/octos-p/raw/codex/hkt-round345-integration/releases/arc-agent-hackathon-sheet-1821c3f5.zip)
- [ZIP binding](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/releases/arc-agent-hackathon-sheet-1821c3f5.binding.json)
- [ZIP shape manifest](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/releases/arc-agent-hackathon-sheet-1821c3f5.shape.json)
- [ZIP checksum](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/releases/arc-agent-hackathon-sheet-1821c3f5.zip.sha256)

上述包绑定 task/suite `hackathon--sheet`、需求 ZIP SHA `9884F23EA10C3DFEEE170D1EED57966C8FCE9A5CE18A0AC43B3D7942EBA8C414` 和 Agent commit `1821c3f5e99836765d23c0f0b7b49d5155e150ab`。平台若返回不同的 suite key，必须重新打包，不得直接复用该 ZIP。旧候选 `c0976cc2` 保留为历史证据，不作为当前上传包。

## 9. 协作门禁

- 本工作树只允许当前 Integrator 写入；子智能体只读审查或在隔离 worktree 工作。
- Agent 源码、官方测试、requirements ZIP、平台 Run 互相隔离；官方测试禁止修改。
- 每次修改必须记录文件、原因、测试命令、退出码和 commit SHA。
- 平台结果必须绑定 task、suite、requirements、Agent build/commit、ZIP/submission 和 Run 配置；缺字段只能作为 exploratory。
- 终版前必须完成 `git diff --check`、本地测试/静态检查、打包身份检查和工作树清洁验证。
- 当前首次打包状态：PowerShell/Git Bash 本地 fixture 包均通过形状、身份和离线导入门禁；正式平台上传保持 `NO-GO`，直到平台提供与需求包精确对应的 suite key、task snapshot（以及可记录的 submission/ZIP SHA）。
- 远程协作规则：提交到远程后，协作文档只引用当前分支的 GitHub `blob`/`raw` 地址；本机绝对路径只能保留在“来源 provenance/不可远程读取”说明中，不能作为队友唯一入口。新增证据、输入镜像和发布包必须在同一同步周期内提交并验证远程存在。

## 10. 新题首轮 Run 复盘（2026-09-30）

### 10.1 可确认事实

- `39626bbcf702`（`hackathon--sheet`）：`0/100`、`0/24`，Agent 段约 `1338s`、`254` requests、`3307706` provider tokens、约 `3.605376 CNY`；生成和最终 startup rehearsal 到达，首轮 rehearsal 曾有一次后端提前退出，随后恢复监听。
- `1c498c860d81`（`hackathon--github`）：`0/100`、`0/47`，Agent 段约 `4634s`、`446` requests、`8460563` provider tokens、约 `9.680698 CNY`；生成和 rehearsal 到达，日志有 `262` 行长 turn keepalive。
- 两个 Run 共用 submission `1becbe535e9b` 和 Agent ZIP SHA-256 `9d4cad2d1136d1edd3f326fe0c58048be281b50b0c06853e63236a7cf71f5c17`；平台未提供 Agent commit、build identity、requirements/snapshot SHA 或 suite key。
- 两个 Run 均为 requirement-text-only：`tests[]` 为空，Playwright 输出、`.arc` 产物和逐测试失败明细均不可用；`node_states` 的 `test-passed` 不能单独作为官方验收证据。

### 10.2 诊断边界与高置信度线索

- `0/100` 不能被分类为“100 个业务断言失败”，因为平台没有暴露测试入口、测试 ID、locator、DOM、trace 或 report；本轮结果标记为 `exploratory / needs_reconciliation`。
- 生成产物仍显示真实收敛问题：Sheet 最终模板只有首页骨架和 `GET /api/workbooks`，GitHub 虽有登录/健康/Fork 等少量路由，但仍缺失大部分需求功能。日志中大量 `wrote=True, verified=False`、结构门禁重复和最终 check 承认未实现，说明 Agent 侧确有高概率不完整。
- 两个 Run 的耗时和请求量随节点数显著增长，重复的 scaffold/repair 上下文是主要优化目标；不能用本次平台 0 分估计每个业务节点的缺陷率。

### 10.3 已并入基线的领域无关门禁

- `has_app()` 现在要求合法 manifest、`build/start` 脚本、真实 frontend entry 和 backend entry，空 `package.json` 不再触发节点循环。
- 工具 Guard 只在 `tool/completed(success=true)` 后记录写入/验证；失败命令和模型口头声明不能制造 evidence。
- 实现 turn 超时或 scaffold hard finding 时进入 `inconclusive`，不再发出 `implementation_done`/`implemented` 的虚假完成状态。
- 无官方 acceptance spec 时写入 `verification_mode=requirement_only` 和 `official_suite_available=false`，startup rehearsal 只证明可启动，不再合成 `test_passed`。
- 结构 findings 按 finding digest + source fingerprint 去重，未改变源码时不重复消耗 repair turn。

### 10.4 下一次平台 Run 门禁

1. 先用 Sheet 作为短探针；候选包必须重新绑定当前 Agent commit、ZIP SHA、requirements SHA 和 task/suite 身份。
2. 平台若仍返回 `tests[]=[]`、无 Playwright/report 和无 build identity，只记录 exploratory，不进入业务定点修复 A/B。
3. 只有出现可复核的真实 test ID/DOM/trace 失败，且身份闭合，才允许进入 GitHub 或第二轮平台 Run；单个候选 Run 触发 quota/余额中断立即 hard-stop，并保留 final reserve。

### 10.5 新增 Run 证据与运行时修复门禁（2026-09-30）

- `09599b312591`（`hackathon--sheet`）在 skeleton 阶段失败：四次尝试均未形成完整 frontend/backend，随后部署因缺少 `backend/package.json` 以 ENOENT 终止；中间态有 `request budget 8 hit`。该 Run 只能证明生成/部署前置失败，不能解释业务测试完成率。
- `451174abe760`（`hackathon--github`）形成可部署模板并达到 `2/100`，但日志出现 `Flow.checkpoint() got multiple values for argument 'reason'`，同时 skeleton 与首个 implement turn 均触发 request budget 截断；该 TypeError 会提前中止 Agent flow，平台结果保留为 exploratory。
- `enter_quota_gate()` 将 provider 详情写入 `quota_reason`，避免与 checkpoint 事件名参数冲突；quota hard-stop 的行为和字段由回归测试锁定。
- skeleton 的 deterministic fallback 只填充缺失或空的 deploy-critical 文件（manifest、入口和静态构建器），不覆盖任何非空业务文件；不完整的既有 manifest 仍由 `has_app()` fail-closed，不能被泛化 scaffold 静默替换。
- 新增门禁：quota checkpoint 不得抛 `TypeError`；空 workspace fallback 必须通过 `has_app()`，且非空业务文件内容在 fallback 前后完全一致。该门禁不绑定 Sheet/GitHub 或任何旧题名称。

## 11. 修复候选 `1821c3f5` 双 Run 只读复盘（2026-09-30）

本节归并 `2b6a1f545c37`（Sheet）与 `0564f5955f16`（GitHub）的阶段 3只读审计。原始附件仍位于用户侧归档目录，尚未镜像进仓库；本节只记录可由 Run JSON、logs、traceability、发布 sidecar 和当前源码相互核验的事实。由于仓库中没有这些原始附件，本节属于 `analysis_only / evidence_not_independently_reproducible`，不能单独作为阶段 5最终裁决或修改授权；后续裁决仍须先镜像并校验原始证据。本轮只更新计划和变更日志，不修改 Agent、Skill、ZIP、requirements 或官方测试，也不启动平台 Run。

归档入口：[Sheet manifest](../evidence/arc-bench/runs/2b6a1f545c37/manifest.json)、[Sheet Phase 3 analysis](../evidence/arc-bench/runs/2b6a1f545c37/phase3-analysis.md)、[GitHub manifest](../evidence/arc-bench/runs/0564f5955f16/manifest.json)、[GitHub Phase 3 analysis](../evidence/arc-bench/runs/0564f5955f16/phase3-analysis.md)。上述 manifest 只登记本地原始附件的大小与 SHA-256；原始附件仍为 `local_only`，未复制进仓库。

### 11.1 终态和证据边界

| Run | 平台终态 | Agent 过程 | 最终部署 | 官方测试可见性 |
|---|---|---|---|---|
| `2b6a1f545c37` / `hackathon--sheet` | `FAILED`，`0/100`，feature `0/24`，约 `5.677578 CNY` | deterministic fallback 后跑完 `24/24` 节点；provider `269` requests、约 `4.28M` tokens | rehearsal 第三轮通过，随后 `template-app` listening `3000` | `run_tests=completed`、`Evaluation completed`；`tests=[]`、无 Playwright report/locator/trace |
| `0564f5955f16` / `hackathon--github` | `FAILED`，`0/100`，feature `0/47`，约 `10.559866 CNY` | deterministic fallback 后跑完 `47/47` 节点；provider `465` requests、约 `8.51M` tokens | rehearsal 第二轮通过，随后 frontend build 和 backend listening `3000` | `run_tests=completed`、`Evaluation completed`；`tests=[]`、无 Playwright report/locator/trace |

因此两次官方测试都已执行，不能写成“未执行”；但 `0/100` 不能进一步拆成 100 个断言失败、100 个 timeout 或某个统一前置失败。测试级 timeout 数量应记为“未知/平台未提供”，不能记为 `0`。平台测试后的 repair 是否存在也未知；Agent 内部 startup rehearsal repair 则有明确日志证据。

### 11.2 对原始汇总的必要纠错

Agent 的 `log()` 同时写 stdout 和 stderr，平台聚合日志又保留两条带通道标签的镜像行。统计事件必须按时间戳和消息体去重：

| 指标 | 原始行数口径 | 去重后的逻辑事件 |
|---|---:|---:|
| Sheet request-budget hit | 58 | 29：cap 8 共 27（skeleton、两次 nudge、24 个节点），cap 10 共 2（两次 rehearsal repair） |
| GitHub request-budget hit | 102 | 51：cap 8 共 50（skeleton、两次 nudge、47 个节点），cap 10 共 1（一次 rehearsal repair） |
| Sheet rehearsal FAILED | 4 行 | 2 次：favicon `ConnectionResetError`；下一轮 `npm start rc=1` |
| GitHub rehearsal FAILED | 2 行 | 1 次：favicon `ConnectionResetError` |

其他口径修正：

- Agent 自报时间预算并非缺失：Sheet 为 `36000s`，GitHub 为 `70500s`；平台自身 timeout 配置仍未提供。
- Sheet 的两次、GitHub 的一次 rehearsal repair 均真实执行。虽然 repair turn 触及 cap 10，后续 rehearsal 最终通过，不能写成“repair 不适用”或“被预算掐断所以没有修复”。
- 两次 favicon reset 都在后续 rehearsal 中恢复，最终平台服务也成功监听。它是通用 unknown-path/连接生命周期风险，不是本轮 `0/100` 的已确认根因；历史 `34/34` BookStack Run 也曾出现并恢复同类中间噪声。
- 发布 ZIP 的 SHA-256 `9b7b39d38efde6cf75f4129a70dbcf421faff9f7a0e34b536737ed3b8cd51f1e` 与 sidecar 可绑定源码提交 `1821c3f5e99836765d23c0f0b7b49d5155e150ab`。运行日志却将生成 workspace 的 Git HEAD 分别打印为 Sheet `d5b777...`、GitHub `00fdb8...`，原因是 `OCTOS_AGENT_COMMIT` 未注入时 `write_run_identity()` 回退到 `self.head()`；这些值不是 Agent 源码提交。平台 Run 对象仍没有 generation identity。
- 日志计算出了 requirements 内容哈希（Sheet `b3f5f6...`、GitHub `64e8a0...`），它与整个 requirements ZIP 的 SHA-256 属于不同口径，不能互相替代或判为冲突。
- 当前发布 sidecar 明确绑定 `hackathon--sheet`。同一个通用 Agent ZIP 被用于 GitHub 可以执行，但该 sidecar 不能为 GitHub Run 提供严格 task/suite/requirements 身份闭环；GitHub 后续候选必须单独生成正确 binding。即使候选侧 embedded build、ZIP SHA 和专用 binding 全部一致，也只表示 `candidate_identity_closed`；只要平台仍不回传 generation identity、task snapshot 或可核验的 submission/ZIP 绑定，平台侧仍是 `platform_identity_inconclusive`，该 Run 仍不能升级为严格 A/B。

### 11.3 “流程跑完但仍为 0 分”的机制解释

两个 Run 都证明 checkpoint TypeError 和空骨架部署失败已被修复：没有 `[flow] aborted`，fallback 产出了可部署布局，并完成全部节点和最终 startup rehearsal。这是确定的运行机制收益，但不是业务完成率收益。

节点证据揭示了新的主瓶颈：

| Run | 节点 turn | `wrote=True, verified=True` | `wrote=True, verified=False` | `wrote=False, verified=False` | 每节点命中 cap 8 |
|---|---:|---:|---:|---:|---:|
| Sheet | 24 | 2 | 19 | 3 | 24/24 |
| GitHub | 47 | 1 | 43 | 3 | 47/47 |

这里的 `wrote=True` 不是产品源码证据。`TurnMonitor` 会把成功写入 `.arc/design` 等元数据也计为 write；多条模型摘要同时承认“仍在分析”“未修改代码”或“尚未实现”。当前 `node_cycle()` 在已有可部署 app 且未发现 scaffold hard finding 时，即使没有 frontend/backend 内容变化、没有外部验证，也会发出 `implementation_done` 并把节点加入 `implemented_nodes`。最终 traceability 进一步印证状态过宽：Sheet 仅 11 个 interface、GitHub 仅 25 个 interface，全部 `implemented=false`、`file_path` 为空、`tests=[]`。

高置信度结论是：

1. cap 8 不是偶发事件，而是两个 Run 的每一个业务节点都触发；
2. 无 bundled acceptance spec 时，Agent 没有逐节点的真实失败反馈，节点循环会把“turn 正常结束”和“已有 app 骨架”误当成可以前进；
3. 24/47 个冷启动式节点 turn 反复读取不断增长的共享文件，造成大量上下文与请求空耗；
4. 后续节点缺少可观察的跨节点回归门禁，可能覆盖或破坏早期功能。

官方 100 项的精确失败机制、模型随机性占比以及后续节点是否实际破坏早期功能仍为 unknown。不得从当前证据猜测隐藏 locator、测试源码或专用业务修补。

### 11.4 跨 Run 成绩和成本波动

| 任务 | 历史候选 | 结果 | 新候选 `1821c3f5` | 可作出的判断 |
|---|---|---:|---:|---|
| Sheet | `39626bbcf702`：`0/100`，约 `3.61 CNY`；`09599b312591`：skeleton 失败、`0/0`，约 `1.00 CNY` | 无稳定业务分 | `2b6a1f545c37`：`0/100`，约 `5.68 CNY` | 新候选把 skeleton/deploy 前置失败推进到完整测试，但没有分数收益；相对 `396...` 成本和耗时上升，仍是系统性 requirement-only 收敛问题 |
| GitHub | `1c498c860d81`：`0/100`，约 `9.68 CNY`；`451174abe760`：checkpoint 崩溃后仍为 `2/100`，约 `0.88 CNY` | `451...` 只实现到首节点，不能作完整基线 | `0564f5955f16`：`0/100`，约 `10.56 CNY` | checkpoint/fallback 修复让请求、token、耗时和费用大幅增加并跑完 47 节点，但观察分数 `2→0`；这是非严格、单样本的 score regression，不能证明修复导致回归 |

新旧 ZIP、生成随机性、缺失 task snapshot/官方测试明细和不完整身份链使这些 Run 不是严格 A/B。最重要的经验不是“继续把 8 调大”：历史 Sheet 大预算 Run 也长期接近零分；相反，Web BookStack `34/34`、Stack Overflow `60/66` 等可见 acceptance 反馈任务证明，Agent 在有具体失败证据时能够收敛。verification regime 是当前最显著且可确认的流程差异之一，也是强候选优化方向；由于没有因果 A/B，不能据此断言它是分数差异的唯一原因，也不能据单次结果断言模型整体退化。

### 11.5 Agent 层候选方案

| 优先级 | 候选 | 预期收益 | 主要风险 | 必须取得的 A/B 证据 |
|---|---|---|---|---|
| P0 | 产品源码 delta 门禁：turn 前后独立计算 `frontend/`、`backend/` fingerprint；`.arc/design` 不计产品写入。无产品 delta 不得 `implementation_done`，只记 `inconclusive/no_product_delta` | 消除假完成；把预算集中到真正产出业务代码的节点 | evolution 中需求可能已被既有代码满足；不能因 no-delta 自动覆盖已有功能 | 每节点 product-delta、首个产品写入请求序号、no-op 节点率、外部 build/start/route probe；状态与 diff 一一对应 |
| P0 | deterministic scaffold 前置：空 workspace 先由 harness 写最小可部署骨架，再开始业务 turn，不再先消耗 skeleton+nudge 三个 LLM turn | 每 Run 直接省去 3 个已证实无产出的 cap-8 turn，降低部署前失败率 | 通用骨架可能对模型形成架构锚定 | 同一需求下 skeleton 请求数 `3→0`、time-to-first-product-write、最终 app shape 和 build/start 结果 |
| P0 | requirement-only vertical slice：按 requirement tree 顶层模块、共享数据模型、路由和页面聚类，先实现高扇出骨干，再实现交互/边界；不绑定 Sheet/GitHub 名称 | 减少 24/47 次冷启动和重复读取；统一共享状态、路由与页面语义 | slice 太大可能输出截断或扩大回归面 | 相同模型/需求下 requests、prompt tokens、冷启动数、product-delta 密度、模块契约覆盖和成本；平台只作后置探针 |
| P0 | harness 外部验证：模型 turn 后由 harness 执行 build、start、health、unknown-path 404、设计中已声明 route 和最小 DOM/可访问语义检查；模型自述不计 verified | 不占 LLM request 预算；尽早发现语法、启动和共享路由回归 | requirement-derived probe 可能与隐藏测试不一致 | 清楚区分 `inferred_local` 与 `official`；保存命令、退出码、HTTP/DOM 观察值；不得生成 `test_passed` 官方结论 |
| P0 | 运行身份读取 ZIP 内 `agent-build.json`，并为 Sheet/GitHub 分别生成 task/suite/requirements binding | 不直接提分；先闭合候选侧身份，为后续可比性提供必要条件，但不自动形成严格 A/B | 平台仍可能不回传 submission/task snapshot；专用 binding 不能替代平台五元组 | 日志中的 full Agent commit/build id 与 sidecar 完全一致，标记 `candidate_identity_closed`；只有平台也回传并匹配 Run、submission/ZIP、task、suite、requirements 才标记 `platform_identity_closed`，否则保持 exploratory |
| P1 | phase-aware request budget：不全局盲升 8；预注入相关上下文，要求前 2–4 requests 出现产品写入；只读到阈值则中止、压缩上下文并允许一次续跑；为外部验证预留预算 | 同时降低重复读取与强制结束；预算随实际工作阶段分配 | 首写阈值过紧会截断复杂 legacy 分析 | time-to-first-write、重复 read 次数、cap-hit 率、productive request 比例、单 slice 成本；与固定 8 做成对本地试验 |
| P1 | best checkpoint + 单调回归：每个通过本地 contract 的 slice 建快照；后续变更至少回归既有核心 route/role/name/持久化读回，失败则恢复 best state | 防止“节点越多、完成率越低”的破坏性积累 | inferred contract 不完整；回滚可能丢失部分有价值改动 | 每次回归的受影响文件、通过/失败 contract、恢复 SHA；不以无测试的 source diff 作为 best |
| P1 | favicon/startup 固化为确定性 runtime contract，在每个 slice 边界运行；失败时只给一次带 server tail 和相关源片段的聚焦 repair | 提前捕获两次 Run 都出现的 unknown-path 风险，避免终局大修 | 自动改写业务 server 风险高，因此只允许验证和聚焦 repair，不做字符串式盲补丁 | `/favicon.ico`、未知页面、未知 API 均返回 HTTP 响应且进程存活；连续相同失败停止 |
| P2 | 扩展通用语义契约：成功后原地更新、实体动作留在实体可访问作用域、`data-*` 读写一致、mutation 后读回/刷新保持状态 | 吸收历史 BookStack/Keep/Stack Overflow 已确认机制，形成长期领域架构 | 提示过长、误用于不相关任务会增加 token 或改变正确行为 | 条件触发命中记录、locator-level 合成回归、旧高分 fixture 无回归；不能以提示存在宣称平台已修 |

### 11.6 Skill 层候选方案与当前事实

`skills/arc-project-context/` 的源码、`project_map`、`source_read` 和 8 项本地断言已存在，但本次上传 ZIP 的 shape 不含该目录，`main.py` 也没有为下载的 Octos 运行时安装或设置 `OCTOS_SKILLS_PATH`；两次日志没有 `project_map`/`source_read` 调用。因此该 Skill 在这两个 Run 中没有生效，不能把任何缓存收益归因给它。

| 优先级 | Skill 方案 | 收益 | 风险 | 验证门禁 |
|---|---|---|---|---|
| P0 | 复用 Octos 现有 Skill/plugin loader，把 `arc-project-context` 真正纳入候选包并注册；或把同等能力作为 harness 预计算上下文，不另造加载器 | 让 project map/source cache 从“仓库文件”变成真实运行能力 | manifest/entrypoint 不兼容会增加启动失败；新增 tool schema 也增加提示长度 | 解包后实际 `octos` tool registry 可见两工具，各调用一次成功；shape、offline import、路径逃逸和 SHA 失效测试通过；平台日志出现受控调用 |
| P0 | project map 由 harness 在 turn 前生成并直接注入；source excerpt 按 change-impact 选择。Skill 调用仅用于模型主动补读 | 少一次 LLM 工具往返；避免每个节点重新 list/read 整个 server/page | 自动影响面可能漏文件 | prompt 中记录 map hash、source SHA/range/omitted；比较重复读取字节、请求数、prompt tokens 和漏读后的修复率 |
| P1 | write-first vertical-slice Skill：需求读取一次后产出接口/状态/可访问语义图、共享文件聚类、首写截止和证据清单 | 把通用工作流复用到未来题目，不写死实体或 REQ | 仅靠 SKILL.md 指令无法强制模型遵循，硬门禁仍必须在 Agent | Skill 被实际加载；前 2–4 requests 产品写入率、slice 完成率、无重复全文件读取；与无 Skill 路径成对比较 |
| P1 | requirement-only contract Skill：生成 happy/error/persistence/reload/404 等本地 probe，输出明确 `inferred_non_official` 类型 | 在隐藏测试环境提供最小可执行反馈 | 推导错误会形成代理目标，不能冒充官方 suite | 输出带来源 requirement hash、probe 类型和观察值；官方字段始终为空；旧 fixture 的 false-positive/false-negative 率可测 |
| P2 | 缓存指标与去重策略：缓存 key 使用 path+SHA+range；同一 turn 对相同 key 直接复用，文件变化后失效；只传变化区段 | 为长期上下文架构提供可量化基础 | 文件系统 cache 命中本身不减少 provider token；若仍把同样 excerpt 回传模型，收益有限 | 同时记录 cache hit、LLM tool request、返回字符和 prompt token；只有请求/字符/token 实际下降才判为收益 |

优先复用现有 Octos loader、Git 内容指纹/差异、Playwright 与当前 `arc/acceptance.py`，不为 project map、diff 或浏览器 probe另造平行框架。Skill 负责可复用工作流和有界读取，runtime 负责 quota、状态、预算、checkpoint 和验收真实性。

### 11.7 下一次单探针 Go/No-Go

当前结论：**对现有 `1821c3f5` 包继续运行 Sheet/GitHub 均为 NO-GO**。它已充分证明部署链恢复，同时也证明 requirement-only 的逐节点 `8 requests` 路径无法产生有效完成率；重复运行只会继续消耗时间与预算。

仅在以下门禁全部满足后，允许一次新的 Sheet 单探针：

1. Agent 日志读取 embedded build identity，候选包、task、suite、requirements binding 完整且一致，先达到 `candidate_identity_closed`；这不代表平台身份已闭合；
2. project-map/source-cache 已在真实解包运行时可调用，或等价的 harness 预计算路径有明确日志和测试；
3. `.arc` 写入与 frontend/backend product delta 分离，无 product delta 的节点绝不记 implemented；
4. 空 workspace 不再消耗三轮 skeleton/nudge；本地 fixture 中首个业务 slice 在 2–4 requests 内产生 product delta；
5. 每个 slice 有 harness 外部 build/start/404/route/DOM contract 证据，且所有证据标记为 `inferred_non_official`；
6. 本地固定需求试验相较当前路径显著降低 cap-hit、重复读取和 prompt tokens，且无已知旧高分 fixture 回归；
7. 单次 Sheet 平台预算设硬上限并保留总预算至少 25%（`50–75 CNY`）作为终版 reserve。

该 Sheet 探针仍只标记 exploratory。专用 binding 和候选侧闭合不等于平台五元组闭合；平台没有回传并匹配 generation identity、submission/ZIP、task snapshot、suite 和 requirements 时，必须继续标记 `platform_identity_inconclusive`。满足以下任一条件才讨论 GitHub：Sheet 平台出现可复核的非零改善；或平台虽继续隐藏测试明细，但 product-delta、inferred contract、部署和候选侧身份链全部闭合且成本低于预设上限。即便进入 GitHub，也不能把该条件描述成严格 A/B。若仍为 `tests=[]` 且本地证据未改善，停止平台消耗，不用单次分数驱动业务猜测或全局抬高 request budget。

## 12. `effd5e7777ce` 只读归档与阶段 3结论（2026-10-01）

远程归档入口：[manifest](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/runs/effd5e7777ce/manifest.json) · [Phase 3 analysis](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/runs/effd5e7777ce/phase3-analysis.md)。原始 7 件附件仍仅在用户本地归档，远程 manifest 保存大小、SHA-256 和 provenance，不复制大型原始附件。

### 12.1 本轮已确认的运行结论

- `hackathon--github` 平台结果为 `2/100`、feature `0/47`；官方 evaluation 已到达，但 `tests=[]`，98 项失败的 ID、类型和 timeout 仍为 unknown。
- Agent 遍历 47 个节点，去重后为 46 次内部 ok 标签和 `REQ-1-1-3` 一次 900s timeout；47/47 节点都是 `wrote=True, verified=False`。
- stdout/stderr 镜像去重后，request-budget 为 49 个逻辑事件，而不是原汇总的 98：skeleton cap 20 × 1、节点 cap 16 × 47、rehearsal repair cap 10 × 1。
- rehearsal 只有 1 次独立 favicon connection-reset 失败，repair 后恢复，最终 build、install 和 port 3000 监听成功。该中间失败不是官方 98 项失败的已证因果。
- 没有上游 402/500 或 OOM 证据；存在 2 次本地 proxy BrokenPipe，不得笼统记为“Proxy/API 错误为无”。

### 12.2 历史比较和非因果边界

`effd5e7777ce` 并非 GitHub 系列首个非零 Run：`451174abe760` 已经为 `2/100`。相对 `0564f5955f16`，本 Run 从 `0/100` 变为 `2/100`，但 requests/tokens/成本/耗时分别约为 1.80×/2.72×/1.72×/2.31×；相对 `451174abe760`，得分相同而成本约为 20.70×。因为 requirements/test snapshot 无 SHA、官方失败明细不可见、候选与平台身份链都未闭合，这只是 observed fluctuation，不是严格 A/B，也不能证明提高 request cap 带来稳定收益。

同步协作分支后，ZIP 内 commit `9ff7e750...` 已可解析，仓库 release ZIP 与 Run 下载包 SHA-256 一致，且 ZIP `main.py` 与提交 Git blob 逐字节一致；候选源码/归档对应关系已补强。但 ZIP 没有 GitHub task-correct binding，平台也未回传 generation identity，因此候选侧解析不能冒充平台绑定，状态仍为 `platform_identity_inconclusive`。

### 12.3 对 Agent / Skill 方案的更新（仅建议）

- Agent P0 优先级不变：产品源码 fingerprint 门禁、harness 外部 build/start/route/DOM 验证、vertical-slice 聚类、inspect/implement/verify 分预算、连续无 verified slice 止损。本 Run 新增证据表明，将节点 cap 从 8 抬高到 16 仍然使 47/47 节点全部触顶且 0/47 verified，不应继续全局抬高 cap。
- Skill 在本 Run 中仍未进入运行链：ZIP 不含 `skills/`/project-context 文件，日志也无 `project_map`、`source_read`或 `source_cache` 调用。`prompt_cache_hit_tokens` 不是 Skill 启用证据，因此本 Run 不能评价 Skill 收益。
- 后续只能在真实打包、tool registry 可见、日志可证调用后验收 Skill；project map 应主动注入，source cache 必须实际降低 provider read requests/字符/token。
- evidence-normalizer 需将 stdout/stderr 镜像去重、ZIP/runtime/workspace/platform 身份分类与 unknown 保留变成硬规则，防止错误统计继续影响修复决策。

本节不授权任何 Agent/Skill 修改、重新打包、发布或平台 Run。Phase 4 仍为 pending，只允许只读诊断。

## 13. `12b3dea74607` 只读归档与阶段 3结论（2026-10-01）

远程归档入口：[manifest](../evidence/arc-bench/runs/12b3dea74607/manifest.json) · [Phase 3 analysis](../evidence/arc-bench/runs/12b3dea74607/phase3-analysis.md)。原始 7 件附件仍仅在用户本地归档，远程 manifest 保存大小、SHA-256 和 provenance，不复制大型原始附件。

### 13.1 已确认结论与口径纠错

- `hackathon--sheet` 平台结果为 `1/100`、feature `0/24`；官方 evaluation 已到达，但 `tests=[]`，99 项失败的 ID、类型和 timeout 为 unknown。
- stdout/stderr 镜像去重后，Agent 为 23 次 `implement ok` 和 `REQ-3-1-1` 一次 900s timeout，不是 46 次 ok。独立 budget-cap 为 24 个，不是 48 行：skeleton cap 20 × 1、节点 cap 16 × 23。
- 24 个业务节点全部 `wrote=True`，但只有 3 个 `verified=True`；23 个完成节点全部触及 cap。skeleton verified，startup rehearsal 一次即通过，最终 build、install 和 port 3000 监听成功。
- 无上游 HTTP 402/500 或 OOM 证据；存在 1 次本地 proxy BrokenPipe，不能笼统记为“Proxy/API 错误为无”。
- traceability 只有 9 条 interface record、覆盖 2 个 requirement ID，全部未映射文件或 tests；这是探测器输出，不是业务完成度真值。
- 23 个 `implement ok` 摘要中至少 10 个自述未实现/部分完成/仍需预算；`REQ-1-3-2` 即使标成 verified 仍报告 404。内部 `ok`/`verified` 存在假收敛，不能把剩余差距集中归因于唯一 timeout。

### 13.2 历史边界与计划更新

相对 `2b6a1f545c37`，本 Run 的 requests/tokens/成本/耗时约为 `1.59×/2.27×/1.66×/3.02×`，业务 verified 节点仅从 2 增至 3，官方结果从 0 变为 1。历史 `002c882794af` 已经为 `1/100`，因此本 Run 不是 Sheet 首次得分；它只能形成弱正向、探索性信号。相对历史同分 Run，单位同分成本较低，但候选包和隐藏测试 snapshot 不同且平台身份链缺失，不能形成因果 A/B。

新包的生成/部署路径更稳定，但“将 cap 从 8 提升到 16”仍让所有可完成节点触顶，没有形成普遍外部验证。计划优先级保持：产品源码 delta 门禁、harness 外部验证、vertical slice、inspect/implement/verify 分预算、连续无 verified slice 止损；不得根据单个 `1/100` 继续全局抬高 cap。

ZIP 内 `agent-build.json` 可定位归档候选，但平台没有 generation identity/build ID/task snapshot；runtime workspace commit 与 embedded commit 不一致。状态继续为 `platform_identity_inconclusive`。post-run template 的需求文本与部分历史模板内容一致，不代表隐藏 100 scenarios 一致。

### 13.3 Skill 证据与限制

本 Run 的 ZIP 不含 `skills/`/project-context 文件，日志也没有 `project_map`、`source_read`、`source_cache` 调用；不能把 provider prompt cache 命中解释为 Skill 生效。后续只有在 Skill 真实打包、tool registry 可见、日志可证调用，并实际降低 provider read request/字符/token 时才能验收收益。

本节不授权 Agent/Skill 修改、重新打包、发布或平台 Run。Phase 4 仍为 pending，只允许只读诊断。

## 14. `f1ff68f69dac` 本地只读归档与阶段 3 结论（2026-10-01）

> **ANALYSIS-ONLY / REPOSITORY-SYNC AUTHORIZED（2026-10-01）**：用户已授权将本节及对应归一化证据同步到协作分支；原始 7 件附件仍仅位于用户本地归档，仓库只保存大小、SHA-256 和 provenance。

### 14.1 对外部终态分析的纠错

- `hackathon--sheet` 平台结果为 `0/100`、feature `0/24`；官方 evaluation 已到达，但 `tests=[]`，100 项失败的 ID、断言、类型与 timeout 均为 unknown。Agent 侧没有 turn timeout，不能把它扩展成“官方超时为 0”。
- stdout/stderr 镜像去重后是 24 次内部 `implement ok` 标签，不能写成“24 节点全部实现”；11 个 `verified=True` 也只能称内部标签，不能称“11 个自验通过”。至少 11 个 ok 摘要明确自述未完成或仍需后续，至少 4 个 `wrote=True` 节点反称没有写入。
- skeleton attempt 1 标记 `wrote=True, verified=True`，但摘要和结构门禁均确认没有 frontend/backend；nudge 1 同样标记 wrote 却自述 no writes。nudge 2 后才出现骨架，并由 deterministic fallback 补齐缺失部署文件。这是比“隐藏测试不对齐”更直接的假收敛证据。
- 独立 request-budget hit 为 27：skeleton cap 28 × 1、nudge cap 18 × 1、24 个业务节点 cap 18 × 24、rehearsal repair cap 10 × 1。24/24 业务节点全部触顶成立，但不能把每个 turn 一概描述为“文件写了一半”；更准确的是没有业务节点自然结束，cap 后仍产生 ok 标签，且没有可靠区分完整、部分和无实现。
- startup rehearsal 第一次出现 favicon ConnectionResetError；repair turn 为 `wrote=False, verified=True` 并触 cap，随后第二次通过。因此只确认“重试后恢复”，不确认产品代码修复生效，也不能把该中间告警作为官方 0 分根因。
- 最终 traceability 文件为 0 interfaces、0 tests。deploy_agent 的“initialized 42 requirements and 100 scenarios”不能替代最终结构化映射，也不能证明需求覆盖。

### 14.2 历史比较和因果边界

本 Run 与 `12b3dea74607` 的 post-run template 内 `requirements.yaml` SHA-256 相同，runtime requirements content hash 也一致，支持需求文本相同；但平台仍未提供 hidden suite/scenario snapshot、generation identity、build binding 或逐测试明细，最终生成产品也不同，因此只记录 observed regression `1/100 → 0/100`，不归因为新包导致回退。

相对 `12b3dea74607`，本 Run 的 requests/tokens/成本/耗时约为 `1.231× / 1.111× / 0.973× / 1.018×`；内部 verified 标签从 3 增至 11，却没有官方收益。这否定 verified 标签作为完成率代理，不构成新包质量的严格 A/B。相对 `2b6a1f545c37`，requests/tokens/成本/耗时约为 `1.963× / 2.527× / 1.615× / 3.072×`，官方结果仍为 0，继续全局提高 cap 没有可观测收益。

同步协作分支后，ZIP embedded commit `7fc46206...` 已可解析，且下载 ZIP 的 `main.py` 与该提交 Git blob 逐字节一致；原先“commit 不可达”的不确定性已消除。但平台没有回传绑定，runtime workspace commit 又与 embedded commit 不同，完整 payload 也未重建，状态仍为 `platform_identity_inconclusive`。模板基线分仍只是候选假说，需要同 snapshot 下 deterministic scaffold 与 scaffold+Agent 配对 probe 才能验证。

### 14.3 Agent / Skill 建议更新（仅建议，不实施）

优先级调整为：P0 修复 `ok/wrote/verified` 真实性（product delta + harness build/start/route/DOM/持久化门禁）；P0 用 vertical slice 取代逐 atomic node 冷启动；P0 将 inspect/write/verify 分预算槽并规定 cap 后为 inconclusive；P0 补 requirement-derived、明确标注 `inferred_non_official` 的契约 probe。P1 再补 traceability、候选/平台身份链、Skill 真实接入和成本测量。favicon 属于 P2 运行信号。

submission ZIP 不含 `skills/`/`arc-project-context`，日志无 `project_map`、`source_read`、`source_cache` 调用，因此本 Run 不能评价 Skill 收益。provider prompt cache hit 占 prompt 约 84.42% 只说明共享前缀复用，不能冒充 Skill 命中、无效 Token 或全价成本。后续必须真实打包注册 Skill，并以 provider read requests、返回字符和 prompt tokens 的实际下降验收。

本节不授权任何 Agent/Skill 修改、重新打包、发布或平台 Run。Phase 4 仍为 pending，只允许只读诊断；本次授权仅覆盖分析与归一化证据的仓库同步。

## 18. 截止前下一版 Agent 有效性最大化方案（2026-10-02）

> **PLAN STATUS UPDATED 2026-10-02**：本节合并 `a7964e4411af` 产物审计、历史 Run 证据、当前源码审查和 Agent 实现经验。P0-A 的结构化合同、P0-C 的有界预算/续作和 truthful state 已落地；本次继续补齐合同的不变量/能力聚合/验收合同证据。P0-B 的稳定优先调度、P0-D seed 隔离和 P0-E 浏览器执行器仍未完成，下面明确保留为待办。

### 18.1 决策更新

`65c381d2` 的 request cap `18 → 50` 不是“过程上完全无效”，但作为全局默认提分手段已经失效：`a7964e4411af` 的 cap-hit 从近乎全节点降至 `14/24`，实现段没有 900 秒 timeout；与此同时结果仍为 `1/100`、feature `0/24`，相对同为 `1/100` 的 `12b3dea74607`，requests/provider tokens/费用约为 `2.43× / 3.74× / 3.94×`。因此下一版不得继续把固定 cap 50 当作完成率修复，也不得简单退回已证实普遍饥饿的固定 cap 18。

`65c381d2` 的提交依据还存在日志去重错误：所谓“92 nodes hit cap”来自 stdout/stderr 重复行；正确口径是 49 个独立事件，其中 feature 46/47、skeleton 1、rehearsal repair 2。后续所有预算决策必须按 Run、阶段、节点、product delta 和唯一事件分层统计。

本轮确认的最大得分阻断并非“代码量不足”，而是实现工作单元和验收入口错误：

- Agent 平均遍历 atomic node，持续向巨型 `server.js` / `editor.js` 追加局部实现，后端 API 与可见 UI、ARIA、持久化之间没有闭环。
- 交付 seed 被 Agent 自测污染；`Q3 Sales` 的活动 worksheet、关键 cell 和更新时间在官方测试启动前已经漂移。
- 共享语义入口缺失：命名 `Worksheet grid` 的元素没有 `role="grid"`，`Formula bar` 实际标记为 `Formula`。
- Sort、Validation、Pivot、Undo/Redo 存在“只有 API 或局部数据结构、没有完整可见工作流”的确定性缺口。
- cap-hit、缺 UI、未跑浏览器 smoke 的 turn 仍被旧版本标成 `implement ok/verified=True`，内部标签不能代表完成率。
- 日志没有官方 Playwright 用例名、断言或逐项 timeout；`requirements.yaml` 的 100 个公开 scenario 和测试后 `pw-*` 数据只能用于需求派生验收与行为推断，不能冒充官方测试明细。

现有 `0d580c74` 候选已修复 cap-hit 状态真实性、product delta、readiness 和 Skill 入包；当前 `97bf3087` 进一步将默认实现预算收敛为 `22 + 12`，并接入需求合同编译。seed 隔离、需求派生浏览器验收和能力级调度仍未完成，不能把当前版本描述为完整能力切片 Agent。

### 18.2 下一版唯一目标和三层职责

截止前不进行完整架构重写。唯一目标是：用最少改动把 Agent 从“平均生成很多局部代码”切换为“优先交付少数可由浏览器完整验收的共享能力”，同时把单次 Run 成本压回可控区间。

```text
Runtime / Harness
  预算、seed 隔离、状态真实性、浏览器门禁、续作队列
        +
Requirement contract / Skill
  短结构化合同、project map、source cache；失败不影响硬门禁
        +
Prompt
  当前 capability、精确 role/name/fixture/postcondition、相关源码片段
```

Skill 继续只负责减少重复读取和提供结构化摘要；quota、checkpoint、seed、完成状态与验收仍由 Runtime 强制控制。

### 18.3 截止前必须完成的 P0 修改

#### P0-A：高置信 Requirement Contract（基础版已完成，fixture variants 待完成）

在 `arc/main.py` 旁新增小型、确定性的 contract 编译层（建议独立为 `arc/requirement_contract.py`），从解析后的 tree/description/scenarios 提取：

```text
fixture / GIVEN
page / route
role + accessible name
visible action
exact error text
success postcondition
failure atomicity
refresh / reopen invariant
scenario_count
```

截止前只处理高置信规则：显式 role/name、错误原文、GIVEN、refresh/reopen 和显式 route；每项必须保留 `evidence/source/confidence`。不能把所有引号都当 locator，也不能把 `the requested workflow` 等占位句解析成合同。当前已落地 `arc/requirement_contract.py`：输出短 JSON、`invariants`、folder-based `capabilities` 和逐节点 `acceptance_contract`，写入 `.arc/requirement-contract.json` 并注入当前节点 prompt；checkpoint 同步记录合同完成/缺失项。互相冲突的 fixture variants 和 seed 映射仍待完成。

#### P0-B：从 atomic node 改为 capability vertical slice（合同聚合已完成，调度仍待完成）

截止前只做 `B-lite`：当前 contract 已为每个 node 生成 capability cluster，但运行时仍保留“一 atomic node 一 turn / 一事件 / 一 verdict”，尚未启用稳定优先拓扑排序。下一步只允许在不重写 traceability 和 acceptance 生命周期的前提下启用优先级；完整的多节点合并 capability executor 会牵动 spec owner、folder state、checkpoint 与 verdict，继续延期。

Sheet 的首轮优先序：

1. 首页、干净 seed、editor 直达、grid/tab/formula bar 语义；
2. cell 编辑、矩形选择、公式、错误和重算；
3. worksheet 与行列生命周期；
4. copy/paste/cut、undo/redo、公式复制；
5. CSV import/export；
6. filter、sort、validation、pivot。

Prompt 仍要求每个 node 服务于所属 capability 的 `可见入口 → UI → handler → API → storage → 页面结果` 闭环，但首版不合并 turn。共享入口失败时降低高级节点优先级和预算，不硬跳过所有后续节点，以免丢失低成本可得分项。

#### P0-C：自适应预算与 completion continuation（已完成基础版）

取消固定 50 默认：

- 基础 implement cap 默认 `22`（可配置 `18–24`）；
- 已产生真实 product delta、没有重复读取/失败且属于高优先级 capability 时，允许一次 `12` 的 continuation；
- 单节点默认总上限 `36`；`50` 只保留为显式 override；
- cap-hit、无 delta、没有成功写证据、连续读取或相同 failure digest 使用同策略时立即停止当前 turn；
- 全局至少保留 25% 时间给最终浏览器验收与针对性修复；本切片先真正扣除 time reserve，完整 run-level request 账本延期。

cap-hit 后已保存 contract 条目、合同完成/缺失项、cap 原因和 `last_real_verification`；模型声明不能充当 verdict。续作只包含当前合同与相关源码；第二次 cap-hit 或仍未通过门禁则降级，不无限重开。`work_remaining = remaining - final_reserve`，进入 reserve 后不再启动新实现，只允许 final gates。build/start/health 由 Harness 执行；完整 run-level request 账本仍待补齐。

#### P0-D：seed 不可变与自测隔离（未完成，保留为下一项）

截止前采用 `D-lite`，不把所有生成应用立即支持 `seed.json/runtime.json/ARC_DATA_FILE` 作为硬前提。Harness 在 skeleton 后记录生成工作区和数据目录 baseline digest；build/start/smoke 在 disposable workspace/data copy 中运行，结束后比较交付目录前后 hash。已有应用若支持 `ARC_DATA_FILE`，可优先指向临时副本；忽略该环境变量时仍由工作区副本保证隔离。

对新生成应用，Prompt 建议区分不可变 seed 与 runtime，并支持 `ARC_DATA_FILE`，但首版 strict 只保护明确的 `seed.json`。遗留单一 `db.json` 发生变化时，Harness 恢复 baseline 并将 turn 标为 inconclusive；不能无条件删除模型为新需求合法添加的 fixture。完整 fixture-variant 到运行数据路径的自动映射延期。

#### P0-E：requirements-derived browser smoke（未完成，保留为下一项）

在 `arc/acceptance.py` 或小型新模块中加入明确标记为 `requirement_smoke` 的 `E-surface` 浏览器验收；它不能冒充 official acceptance。首版只验证确定性、只读的公共 surface：canonical root/editor 可达；高置信 role/name 在可达页面唯一可见；公开 seed 值可观察；页面无启动级异常。它应捕获缺 `role="grid"` 和 `Formula bar` 名称错误，但不得从自然语言自动猜复杂 mutation 动作。

复杂 Sort/Pivot/Validation 首版只做合同、DOM action 和 route parity；完整成功/失败/refresh/reopen 动作生成延期。若 Playwright 不可用，结果必须为 `unknown`，绝不能用静态 grep 代替通过。节点状态改为 `source_changed → requirement_surface_passed → official_acceptance_unknown`；只有 Harness 可以产生本地 surface verdict，模型的 `verified` 文本只保留为备注。

### 18.4 截止前有余量再做的 P1

- Harness 主动运行已打包的 `project-map`，而不是等待模型选择 Skill；按 `path + SHA + range` 缓存 source，只注入当前 capability 的符号、route、DOM 控件和片段。
- 在 contract 明确提供安全动作 DSL 后，再逐步启用成功 mutation、失败原子性和 refresh/reopen 浏览器流；截止前不做任意自然语言工作流生成器。
- 将 `seed.json/runtime.json + ARC_DATA_FILE` 升级为生成架构强制协议；截止前仅使用 disposable workspace/data copy 与可选环境变量。
- 为共享热点设置软上限（建议 600 LOC 或 25–35 KB）；超限后先拆 router/store/workbook/cells/formula/data-actions 与 grid/worksheet/data-dialogs，再继续功能。截止前只做生成规则和软门禁，不手工重构历史产物。
- 将当前基于字符串距离的 handler 检查降为 advisory；最终产物中的 Import/Data handler 已证明其存在 false positive。优先用真实浏览器行为；若做静态 parity，采用 AST/DOM 索引并区分置信度。
- 修正 identity：`agent_source_commit` 从包内 build metadata 或显式环境取得，`product_workspace_head` 单独记录，禁止用生成产品 `self.head()` 冒充 Agent commit。
- 每个 smoke server 使用独立进程组并强制回收；记录 stray process 数，但无 OOM 时不得把它写成 OOM 根因。

### 18.5 明确延期，防止截止前失控

- 完整六 Skill 架构、change-impact 强阻断；
- 跨 Run 通用 resume 重构；
- 全量 AST/数据流分析器；
- 为全部 100 scenario 自动生成完整 Playwright suite；
- 大规模手工模块化和框架替换；
- 猜测或硬编码官方隐藏测试、旧题 locator、REQ ID 或领域实体。

### 18.6 代码修改地图与单写入边界

| 文件/模块 | 截止前改动 | 完成证据 |
| --- | --- | --- |
| `arc/main.py` | base 22 + continuation 12、truthful states、真实 time reserve、合同进度 checkpoint | cap-hit 不完成；合同完成/缺失项可追溯；能力优先调度仍待接入 |
| `arc/requirement_contract.py` | 高置信合同、不变量、能力聚合和逐节点验收合同 | Sheet/GitHub 计数、evidence/confidence、capability cluster 可解析；fixture variants 待完成 |
| `arc/acceptance.py` / `arc/semantic_smoke.py` | disposable workspace/data copy、只读 requirement surface smoke | 缺 grid role、错误 Formula bar 时稳定失败；无浏览器为 unknown |
| `arc/tests/test_main_helpers.py` | budget、contract、cap continuation、seed guard | 单元测试覆盖所有状态边界 |
| `arc/tests/test_acceptance.py` | 语义 locator、持久化、失败原子性、进程清理 | 浏览器/集成回归通过 |
| `arc/pack.sh`、`arc/pack.ps1`、`arc/package_shape.py`、`arc/package_gate.py` | 新模块入包、shape 与 smoke import | ZIP 离线 import、Skill、contract/smoke 模块可执行 |
| 本计划与 changelog | 决策、门禁、候选身份 | 与代码在同一逻辑提交更新 |

### 18.6.1 当前完成度（2026-10-02）

| 项目 | 当前状态 | 后续动作 |
| --- | --- | --- |
| Requirement compiler | ✅ 已完成基础版 | 补 fixture variants 与冲突 fixture 的运行时映射 |
| Invariants / capability map / acceptance contract | ✅ 已生成并落盘 | 接入稳定优先拓扑，但暂不合并多节点 turn |
| Budget / continuation / truthful state | ✅ 已完成基础版 | 补 run-level request ledger 与重复策略切换 |
| Capability-priority scheduler | ⚠️ 未完成 | 在保留依赖拓扑和现有 verdict 生命周期前提下实现 B-lite |
| Requirement-derived browser smoke | ❌ 未完成 | 新增只读高置信 surface smoke，结果标记 `inferred_non_official` |
| Seed/runtime 隔离 | ⚠️ helper 已完成，runtime 接入未完成 | `seed_isolation.py` 已提供 disposable copy/baseline hash/restore；仍需接入 Harness 并记录每轮 seed verdict |
| 完整 project-map/source-cache/change-impact | ⚠️ 部分已有 | Harness 主动生成 map，按 path+SHA+range 注入当前 capability |

仍维持单写入者：只有 Integrator 修改代码、提交和打包；代码风险、浏览器验收、包门禁可由子 Agent 只读并行审查。

### 18.7 本地验收与 go/no-go

下一包必须通过以下门禁：

1. `a7964e4411af` 继续作为一次性人工/本地负样本，必须检出缺 `role="grid"`、`Formula bar` 名称不符和高级可见路径缺失；持续 CI 的 seed guard 使用通用合成 fixture 验证前后 hash，不能假装从任意历史 JSON schema 自动推断正确业务 seed。
2. contract parser 对 Sheet YAML 稳定得到 24 atomic / 100 scenarios，并提取公开 role/name/error/refresh 合同；不得生成旧题专用硬编码。
3. capability plan 每个 node 恰好归属一个 cluster；稳定优先拓扑不违反 node 依赖，共享入口 node 优先，但首版仍一 node 一 turn。
4. cap-hit 即使 wrote/product delta 也只能 partial；一次 continuation 仍不通过 semantic smoke 时停止。
5. Agent smoke 在 disposable workspace/data copy 中运行，交付目录前后 hash 一致；strict `seed.json` 不得漂移。
6. build、canonical start、`/`、`/api/health` 和浏览器高置信 role/name surface smoke 全通过；浏览器不可用为 no-go，不能降级成静态通过。
7. 可见 mutation action 与 backend route 建立 parity；static finding 不得对现有外部 JS handler产生已知 false positive。
8. 记录 `requests / product delta / requirement_smoke_pass / cap-hit / repeated reads / seed restores / first runnable time / total cost`，不能只记录平台分数。
9. 全量测试相对冻结基线零新增失败；三个既知 Windows 路径/权限失败只能按测试 ID + 错误指纹 allowlist，指纹变化即失败。package shape、offline import、Skill smoke、binding 和 checksum 全通过。

建议 feature flags：`OCTOS_ARC_REQUIREMENT_CONTRACT=1`、`OCTOS_ARC_ADAPTIVE_BUDGET=1`、`OCTOS_ARC_BASE_REQUESTS=22`、`OCTOS_ARC_CONTINUATION_REQUESTS=12`、`OCTOS_ARC_MAX_REQUESTS=36`、`OCTOS_ARC_CAPABILITY_PLAN=priority|off`、`OCTOS_ARC_SEED_ISOLATION=1`、`OCTOS_ARC_SEED_STRICT=1|0`、`OCTOS_ARC_REQUIREMENT_SMOKE=surface|off`、`OCTOS_ARC_REQUIREMENT_SMOKE_STRICT=1|0`。contract/capability/smoke 异常可记录 checkpoint 后回退旧路径；只有显式 strict 的 seed 或 semantic gate 失败才 no-go，不得静默称 verified。

任何 P0 门禁失败即 no-go，不用平台预算验证半成品。只有本地 P0 全绿后才生成新 ZIP；第一轮仍只跑 Sheet 短探针，并保留至少 25% 预算作最终 Run reserve。

### 18.8 相对时间计划

硬截止：**北京时间 2026-10-03 23:59**。所有代码、包、平台探针和最终提交均以该时间倒排；任何阶段延误都只能裁剪低优先级工作，不得压缩最后一小时的上传与校验缓冲。

| 时间 | 工作 | 停止条件 |
| --- | --- | --- |
| T+0–1.5h | adaptive cap、真实 final reserve、状态边界与定向测试 | reserve 或 cap truth 不可信则停止 |
| T+1.5–4h | contract-lite 解析、JSON/Prompt 注入、24/100 纯解析测试 | 不能过滤占位场景或保留证据则回退 |
| T+4–6.5h | disposable seed/workspace 隔离与 hash 恢复 | 交付数据仍会被 smoke 污染则 no-go |
| T+6.5–9.5h | high-confidence semantic surface smoke | 无真实浏览器则 no-go；不扩展复杂动作生成 |
| T+9.5–11h | B-lite 稳定优先拓扑 | 时间不足先砍 B-lite，保留 A/C/D/E |
| T+11–14h | 集成、相对基线全量回归、包门禁、只读复核 | 新增回归、dirty binding 或身份不闭合则不打包 |

若剩余时间不足，按顺序保留 P0-D seed 隔离、P0-E 核心浏览器门禁、P0-C 状态/预算真实性，再保留最小 capability 聚合；先延期完整调度器和 P1，不以大重构换取不可验证的新风险。

绝对倒排门禁：

| 最晚时间（北京时间） | 必须完成 | 超时处置 |
| --- | --- | --- |
| 10月2日 13:00 | 功能范围冻结 | 砍完整 scheduler、任意动作生成和 P1，只保 A-lite/C/D-lite/E-surface |
| 10月2日 16:30 | 定向测试、负样本和核心浏览器 smoke go/no-go | 任何核心红项均不烧平台预算 |
| 10月2日 18:30 | 相对基线回归、package gate、候选 1 冻结 | 新增回归即退回最后全绿候选 |
| 10月2日 19:00 | 最晚启动第一轮 Sheet 探针 | 不等待到次日上午 |
| 10月2日 23:00 | Sheet 结果硬回收截止 | 未终态只存中态，不并发新代码或新 Run |
| 10月3日 00:30 | 唯一一次直接证据补丁/第二探针 go/no-go | 只修 90–120 分钟内可本地复核的问题 |
| 10月3日 04:30 | 最终源码冻结 | 禁止架构重构和非阻断修复 |
| 10月3日 05:30 | 候选 2 task-correct 打包完成 | ZIP/sidecar/binding 任一不一致即 no-go |
| 10月3日 06:00 | 最晚启动唯一第二探针 | Sheet 重跑与 GitHub 二选一，不并行 |
| 10月3日 11:00 | 第二探针结果硬回收截止 | 11:30 前完成原始附件与哈希归档 |
| 10月3日 12:30 | 停止全部探索 Run 和业务修复 | 之后仅处理包、身份、上传阻断 |
| 10月3日 15:00 | 最终包冻结并重跑 package gate | 不再改变 Agent 字节 |
| 10月3日 17:00 | 上传前 dry-run、本地复制/下载后哈希完成 | 下载链不闭合则使用已验证本地包 |
| 10月3日 20:59（D-3h） | 完成最终上传/提交 | 保留 3 小时应对网络、排队与手工回滚 |
| 10月3日 23:59 | 比赛提交截止 | 不接受任何最后一分钟重打包 |

平台预算门禁：先核算完整历史账本，`200–300 CNY` 是总预算而非新增预算。第一轮 Sheet soft/hard 为 `15–20 / 25 CNY`，硬墙 4h；可选 GitHub soft/hard 为 `20–25 / 35 CNY`，硬墙 5h。发现 quota/402、无 product delta 长循环、核心 semantic gate 未执行或同一 failure digest 重复三次时立即止损。若剩余预算 `<100 CNY`，取消第二探针；`<75 CNY`，取消全部探索探针，只保最终包与正式评估。无实时精确计费时以 requests、provider tokens、wall-clock 和 cap-hit 联合止损。

并行协作采用三个只读审查 lane，不扩大写入面：

- Lane A：requirement contract、seed 与状态真实性审查；
- Lane B：浏览器 semantic smoke、回归与平台结果诊断；
- Lane C：package/binding/checksum/下载链门禁；
- Integrator：唯一代码与文档写入者、合并者和最终 go/no-go 决策者。

子 Agent 任务必须使用最小上下文和明确输出格式，不重复读取全项目记忆；任何子 Agent quota/usage-limit 失败均降级为主会话只读复核，不得阻塞关键路径或触发重复派发。本次计划复核已实际观察到三个子 Agent 同时因额度不足失败，故多 Agent 只用于加速审查，不能成为正确性前提。

### 18.9 预期收益与不能承诺的事项

预期直接收益：防止测试前 seed 污染；在平台前捕获共享 ARIA/可见 UI 缺口；把预算集中到能端到端得分的核心能力；阻止 cap-hit/仅 API/模型口头自验被记录为完成；降低同分成本与重复读取。

不能承诺：隐藏 suite 逐项行为、分数必然上涨、所有 100 scenario 一次覆盖、Skill 必然降低 provider token。下一版的成功标准先是“本地合同真实性 + 核心浏览器能力 + 成本受控”，平台得分作为随后验证，而不是替代这些门禁。

## 17. 下一轮平台候选的三层联动实现（2026-10-02）

> **IMPLEMENTATION AUTHORIZED / PLATFORM RUN USER-OPERATED**：用户随后明确要求“根据建议修改一版，由用户提交平台测试”。本节取代前述各 Run 归档段落中的 analysis-only 限制，但授权仅覆盖 Agent 源码、回归测试、候选 ZIP 和协作记录；本会话不代替用户启动平台 Run。

本次切片坚持 `Runtime/Harness 强制控制 + 通用 Skill 结构化摘要 + Prompt 短规则`，不把六个候选 Skill 一次性重构为系统依赖：

- Runtime 状态真实性：节点前后计算 frontend/backend 产品指纹；无 product delta 不得发出 `implementation_done`。命中 request cap 或没有成功写工具证据时，即使源文件有变化，也只保留并提交 partial source，节点状态为 inconclusive。
- 无 spec 收敛：Harness 将已解析需求树压缩为有界 skeleton outline；requirement-only 节点禁止寻找不存在的 tests/report/history，并要求在第三个工具调用前产生产品写入。此路径保留 build/start/curl 所需 shell，避免 Prompt 与工具策略自相矛盾。
- 部署契约：rehearsal 先验证 canonical `GET /` 和严格 2xx 的 `GET /api/health`，再做未知路径健壮性检查。仅存活进程上的 favicon connection reset 可降级为 advisory；未知页面/API、timeout 或进程退出仍失败。
- 通用 Skill：复用仓库已有 `arc-project-context`，不新造缓存框架。候选 ZIP 强制携带 `SKILL.md`、manifest、实现和 Linux launcher；运行时复制到一次性 profile 的 `skills/` 并 `chmod`，设置 `OCTOS_SKILLS_PATH` 到父目录。Skill 失败不影响 quota/checkpoint/readiness 等硬约束。
- 打包身份：PowerShell 与 POSIX 打包链均拒绝 dirty Agent 源码；package shape 强制要求 Skill 四件套，offline gate 实际执行 `project_map`，防止再次出现“ZIP gate 通过但 Skill 未入包”。

明确不在本切片内：`change-impact` 强阻断、完整 repair strategy switch、跨 Run resume 重构、隐藏测试猜测、题目专用 locator/实体名。Skill 不会被逐节点强制调用；首轮只验证工具真实注册和可调用，收益仍需以后用 `project_map/source_read` 调用次数、返回字符、provider prompt tokens 与重复读取量衡量。

协作分支在实现期间出现远程提交 `65c381d2`，把多节点 implement request cap 从 18 提至 50。该变更必须通过正常合并保留其历史，不得覆盖；同时本切片把任何 cap-hit 明确传导为 inconclusive，且继续保留时间型 final reserve。平台 Run 需单独记录成本与 cap-hit，不能仅因分数上涨就认定全局抬高 cap 正确。

### 17.1 Sheet-first 候选包与身份门禁

- 候选包：`releases/arc-agent-hackathon-sheet-0d580c74.zip`（359,305 bytes）。
- Agent 源码提交：`0d580c748bf67d2425a49733e5a592ade21ebe4d`；Build ID：`arc-agent-v1-30a08860f96969acadc74e1f`。
- ZIP SHA-256：`3f18da678504e147ce3748f23a829a63fc055fb61c056e53b03c1b0b2e3f79db`；payload tree SHA-256：`9FC208DB0ADF47977F906233FF90CF2CF23EC346EAFB015BBCE98AD3E3151793`。
- requirements SHA-256 继续绑定现有已知值 `9884f23ea10c3dfeee170d1eed57966c8fce9a5ce18a0ac43b3d7942eba8c414`；平台未提供新 snapshot，因此此字段仅表示候选侧绑定，不能冒充平台侧 generation identity。
- package shape、offline import、Skill 行为烟测、placeholder identity 拒绝和侧车 checksum 均已通过。候选先用于 `hackathon--sheet` 探索性 Run；平台成绩、隐藏 suite 身份和当前 task snapshot 仍需用户上传后回填，不能提前宣称收益。
- 远程下载：`https://github.com/William-zwy/octos-p/raw/codex/hkt-round345-integration/releases/arc-agent-hackathon-sheet-0d580c74.zip`；绑定与 shape 侧车位于同一远程目录。

## 16. `877ac3bb19e7` 本地只读归档与阶段 3 结论（2026-10-01）

> **ANALYSIS-ONLY / REPOSITORY-SYNC AUTHORIZED（2026-10-01）**：用户已授权将本节及对应归一化证据同步到协作分支，并与 `f1ff68f69dac`、`b4e114e9c001` 的分析一并提交。

### 16.1 聚合得分与外部分析纠错

- 平台明确报告 `13/100`、feature `3/47`，三个 step 均 completed；这是当前已归档 GitHub Run 集合中的最高观测分和最强正向信号，但 tests 为空、hidden suite identity 缺失，不能外推为平台全部历史最高或严格归因于新包。
- 47 次 `implement ok` 不是 47 个实现完成：33 wrote / 14 no-write、11 verified / 36 unverified；至少 17 个摘要自述未完成，至少 8/11 verified 摘要仍有实质缺口。业务节点 46/47 命中 cap 18，系统性假收敛仍存在。
- rehearsal 不是 repair 后成功：三次均因 favicon ConnectionReset 失败，两个 repair 的摘要都不能证明有效产品修复，最终 giving up/submitting as-is。runner 后续独立 postflight build/start 成功并进入测试，部署成功不可归因于 rehearsal repair。
- Agent turn timeout 为 0；官方测试级 timeout unknown。有 1 次非致命 BrokenPipe，无 402/500 或 OOM。
- 本地物理附件 9 件但只有 8 份唯一内容：midrun logs 与 final logs 完全相同；仅有空的 midrun traceability，没有 final traceability。

### 16.2 横向比较和机制边界

相对 `effd5e7777ce`，本 Run 用约 `0.951×` Token、`0.904×` 成本和 `0.765×` run duration 获得 `6.5×` 通过项，成本/通过项从约 9.092 CNY 降至 1.265 CNY，构成显著观测改善。但早期 `451174abe760` 的绝对资源消耗更低，因此不能宣称全历史效率最佳。

相对部署失败的 `b4e114e9c001`，新拉取的提交差异证明本包强化的是 `ARCHITECTURE_CONTRACT`、`SKELETON_PROMPT` 与 `NODE_PREAMBLE_EXTEND` 中的 single-origin prompt 约束，而非 runtime harness 强制逻辑。最终产物 canonical `node server.js` 同时提供根页面、静态前端和 `/api`，而 b4e 的 canonical start 是不服务根页面的 API-only 入口。这是部署恢复的强关联候选机制；由于生成随机性和平台 readiness probe 不公开，仍不是唯一因果证明。

候选源码身份得到部分闭合：ZIP embedded commit `3d6713b1...` 已可从协作分支解析，父提交为 `7fc46206...`，下载 ZIP 的 `main.py` 与提交 Git blob 逐字节一致。完整 payload 未重建，且 platform generation identity/build ID/task snapshot/suite key 仍缺失，runtime workspace commit 也不能替代上传 Agent 身份。因此运行状态仍保持 `platform_identity_inconclusive`、`strict_ab=false`。

### 16.3 与远程源码合并后的结论更新

- `7fc46206`、`9ff7e750`、`3d6713b1` 三个历史包内提交现均可由 `codex/hkt-round345-integration` 解析；相关 Run manifest 已从“commit 不可达”更正为“archive source commit resolved”。
- `9ff7e750` 的仓库 release ZIP 与 `019c8cb3d590` 下载包 SHA-256 完全一致；`7fc46206`、`9ff7e750` 与 `3d6713b1` 的 ZIP `main.py` 均与对应提交 Git blob 逐字节一致。后两者尚未进行完整 payload 重建，不能宣称完全可复现。
- `3d6713b1` 的产品机制变化来自 prompt-level single-origin 契约，而不是新增 runtime harness；这提高了对“为什么 b4e 部署失败而 877 进入测试”的机制解释力，但仍不足以把 `13/100` 严格归因于该提交。
- 候选源码提交可达不等于平台身份闭合：平台仍未返回 generation identity、task snapshot、suite identity、逐测试明细或可核验的 submission binding。

### 16.4 优先级更新（仅建议，不实施）

P0 保留 single-origin canonical start；P0 让 runner-equivalent harness 外部验证取代模型 verified；P0 将三次 rehearsal 失败正确传导为 failure/inconclusive，并禁止无 product delta 的 repair 标完成；P0 延续 vertical slice、分预算槽和无进展止损。P1 闭合 task-correct binding，并在同一 snapshot 下重复短探针验证 13 分稳定性。P1 之后才正式打包/注册 Skill 并以 provider read requests、返回字符和 prompt token 下降验收。P2 持续降低 Token/通过项。

本节不授权任何 Agent/Skill 修改、重新打包、发布或平台 Run。Phase 4 仍为 pending，只允许只读诊断；本次授权仅覆盖分析与归一化证据的仓库同步。

## 15. `b4e114e9c001` 本地只读归档与阶段 3 结论（2026-10-01）

> **ANALYSIS-ONLY / REPOSITORY-SYNC AUTHORIZED（2026-10-01）**：用户已授权将本节及对应归一化证据同步到协作分支；原始 7 件附件仍仅位于用户本地归档。

### 15.1 对外部终态分析的纠错

- 平台不是“65 atomic nodes”：node-state 共 65 条，其中 18 design（含 ROOT）和 47 implement；Agent flow 明确遍历 47 个 atomic leaf nodes。
- 47 次 `implement ok` 不能称为“47 个节点全部实现”或“代码全部生成完毕”：11 verified / 36 unverified、44 wrote / 3 no-write；人工保守确认至少 19 个摘要自述未完成，至少 3 个 `verified=True` 节点直接承认未实现/无代码，另有 3 个 verified 节点保留启动、交互或验证缺口。最终 traceability 为空。
- 独立 request cap 为 48：skeleton 1、nudge 1、业务节点 46/47；唯一未命中的是 `REQ-1-1-3`。两个 same-error guard 是本地重复错误保护，不是网络故障。
- 官方测试没有执行：`start_agent=failed`、`run_tests=pending`、passed/failed=`0/0`。官方测试 timeout 应记 not reached，而不是 0；Agent turn timeout 才可明确为 0。

### 15.2 部署失败的强候选根因与边界

`backend/package.json` 的 canonical start 是 `node lib/server.js`。该真实入口只让 `/api/health` 返回 200，`/` 与 `/health` 返回 404，也不服务 frontend/dist；能服务根页面及两个 health 路径的 `backend/server.js` 没有被启动。frontend 又把 API 固定到 `127.0.0.1:3001`，平台实际 backend 监听 3000。

因此 `05:53:38` 的 listening callback 与平台 `05:55:39` 的 120 秒 not-ready 并不矛盾：bind 成功不等于 HTTP readiness 成功。最强候选是生成产物的启动入口漂移/HTTP readiness contract 违反，而不是“平台错误忽略已就绪服务”。但平台没有回流 probe 路径、期望状态、重试响应或进程退出状态，不能断言具体探针一定是 `/` 或只接受 200。

Agent 内部 rehearsal 只记录 `app builds and starts cleanly`，没有最终启动命令下的路径/状态码证据，不能反证平台失败，反而证明本地门禁没有复现平台契约。同需求的 `451174abe760`、`effd5e7777ce` 产物启动入口均显式处理根页面并进入测试，构成旁证，但 hidden suite identity 仍未知，不构成严格 A/B。

### 15.3 建议优先级更新（仅建议，不实施）

P0 统一唯一 canonical start 入口，使其同时满足 SPA root、health、host/port 与 API 同源；P0 让 rehearsal 使用平台同一 `npm start` 与环境，并审计 `/`、`/health`、`/api/health`；P0 用 product delta + harness 外部验证消除 verified 假收敛；P0 将 inspect/write/verify 分预算槽，并结合 vertical slice/无进展止损。P1 再补 traceability、task-correct GitHub binding 与 readiness 证据链。

本 Run 的 958 requests、26.139M tokens、18.864285 CNY 均在 deployment gate 前耗尽，没有产生官方测试信号；不能由 `0/0` 评价代码质量。Skill 未打包、未调用，prompt cache hit 不能作为 Skill 生效证据。

本节不授权任何 Agent/Skill 修改、重新打包、发布或平台 Run。Phase 4 仍为 pending，只允许只读诊断；本次授权仅覆盖分析与归一化证据的仓库同步。

## 17. 2026-10-02 两次负收益 Run 的修订结论

`6ad28fd0ab3d` 与 `7616a1cdbddd` 的 Stage 1 需求契约相同，但 template ZIP 与 agent commit 不同；因此两次结果不是纯 request budget A/B。应将结论写为：外层 cap 提升未带来收益，`7616` 出现 900 秒超时并从 5/30 退化到 0/30，但预算与代码版本同时变化，不能证明 cap 单变量造成退化。Sheet 的 `6e04e0ff14dc`（budget 30，0/100）与 `9fee9a825b32`（budget 12，0/100）进一步说明预算没有触及正确性瓶颈。

下一实验必须固定 canonical ZIP、requirements SHA、task/suite、模型和需求契约，只改变预算策略；优先比较 `12 + 一次 8` 与固定 12，并保留 final smoke/打包 reserve。P0 仍为需求合同驱动的 browser semantic smoke、product delta + live acceptance 的 truthful completion、无进展/重复 failure stop；P1 为 capability slice 与平台身份回传门禁。平台不回传 tests[] 时，不得推断具体隐藏断言。

## 18. `8fca1171db4b` 终态后的截止前收敛方案（2026-10-02）

### 18.1 证据更新

- `8fca1171db4b`（GitHub Stage 1）进入官方测试并取得 `5/30`、feature `1/12`，与 `6ad28fd0ab3d` 持平；这确认部署入口恢复，但未证明需求到用户旅程的转换已经解决。
- 拆分前完整 GitHub `877ac3bb19e7` 仍以 `13/100`、feature `3/47` 作为绝对通过数基线。Stage 1 与完整题目不可简单按百分比比较，但拆分后没有超过拆分前结果，统一领域模型和共享旅程必须保留。
- `8fca` 的 `implement ok`、无 Agent timeout、部署成功只是过程证据；官方未回传 `tests[]`、Playwright report、generation identity、task snapshot 和 suite identity，因此不能推断 25 个失败场景的具体断言，也不能声称某一 prompt 改动是唯一因果。
- `7cc1b2ba5b1f` 的 24/24 implement、36 次 budget guard、最终 `0/100` 进一步证明：节点过程状态不能替代真实浏览器行为验收；budget guard 是强风险信号，但不是已被单独证明的全部根因。

完整归一化记录见 `HKT/ARC_BENCH_RUN_8FCA_STAGE1_EVIDENCE_20261003.md`。

### 18.2 截止前第一步（P0）

只实施一个高收益切片，禁止同时开展大规模框架重构：

1. 将完成状态拆为 `source_changed`、`build_passed`、`health_passed`、`semantic_smoke_passed`、`persistence_passed`、`official_acceptance_unknown`；`implement ok`、`wrote=True`、`continuation ok` 不得自动升级为 `verified=True`。
2. 为 Stage 1 生成短验收合同，至少覆盖入口、session、列表/详情、创建/编辑、刷新恢复、实体作用域和错误原子性；合同字段固定为 fixture、route、role/name、action、mutation、visible result、refresh result。
3. 用需求派生浏览器 smoke 闭合一条完整链路：入口 → 资源打开 → 核心动作 → 可见结果 → refresh/reopen → 失败不污染。
4. 预算采用 `12 + 一次 8` 的受控 continuation；只有真实 product delta、build/start/health 和 smoke 进展同时存在时才允许继续。无文件变化、重复读取、相同 failure digest 或无 smoke 进展时停止并保存 checkpoint。
5. 最终验证和打包保留独立 reserve，不能被实现循环耗尽。

### 18.3 实验与交付门禁

下一次实验固定 canonical ZIP、requirements SHA、task/suite key、模型/prompt 版本和 seed/runtime 初始状态，只改变一个明确运行时变量。提交前必须输出并校验 source SHA、requirements SHA、package identity、ZIP SHA；身份不匹配时 fail-closed。

本阶段不引入完整 Spec Kit、全量工具 API 重构或多模型 Plan & Execute。`project-map`、`source-cache`、`acceptance-smoke` 可继续作为低风险辅助，但不能替代 Harness 的真实门禁。

### 2026-10-03 — P0 runtime compatibility correction

Run `3307814a18ea` exposed a higher-priority blocker than budget or requirement
compilation: after `REQ-1-1-1` returned successfully, the flow called
`EventClient.mark_implementation_ready`, which was absent from the bundled runtime.
The run therefore aborted after 1/24 nodes and scored 0/100 despite a healthy server.

First-step policy is now fixed:

1. runtime API compatibility preflight;
2. single-node flow smoke through the intermediate `ready` state;
3. only then requirement compilation, capability scheduling, and semantic/persistence smoke.

The compatibility method records `phase=implement,status=ready` and must never mark a
node `IMPLEMENTED`; only acceptance-backed `mark_implementation_done` may do that.
The repair is isolated on `codex/hkt-runtime-compat-3307814` until validated and
approved for the hackathon integration line. Do not infer hidden test IDs from this run.

### 2026-10-03 — agent-capability-analyst 接入决策

The supplied skill is useful as a diagnostic methodology, but not safe as a direct
hard gate: it is model-facing, asks for interactive dimension selection, and cannot
prove hidden acceptance. We retain its strongest parts (requirement compilation,
Given/When/Then evidence, boundary cases, traceability, and behavior-oriented
regression) and reject its weaker assumptions (full Spec Kit adoption before the
deadline, broad tool/framework rewrites, and model-controlled blocking).

A deterministic shadow module `arc/capability_judge.py` was added on the isolated
runtime-compat branch. It scores only observed source/build/readiness/semantic-smoke/
persistence evidence, remains fail-closed when official acceptance is unknown, and
never emits `verified` or changes `implemented_nodes`. Integration into the main loop
must wait for a fixture-backed evaluation; the runtime and acceptance harness remain
the sole hard gate.

Evidence-specific refinements: readiness is a first-class check after f9e8's HTTP
hang, and persistence/semantic smoke are separate checks after the 0/100 and 5/30
runs. This judge is shadow-only until it proves low false-positive behavior.

### 2026-10-03 — runtime branch requirement compiler integration

On `codex/hkt-runtime-compat-3307814`, the isolated requirement-compilation work was
selectively integrated without replacing the runtime compatibility patch or the shadow
capability judge.

Platform-run behavior is intentionally bounded:

- Run start calls `compile_requirement_compilation(tree)` and persists the contract;
- a shadow `capability_plan.json` is persisted for capability grouping;
- after each slice, `capability_judge` writes a scorecard only;
- no run-end analyst is invoked inside the Agent;
- `verified` and `implemented_nodes` remain controlled by acceptance/runtime gates.

The compiler now emits GWT scenarios, two examples, boundary cases, implicit
requirements, clarification assumptions, and bidirectional traceability. The HTTP
listener/readiness repair remains in the implementation prompt for this branch.

### 2026-10-03 — current capability boundary and release status

Current branch `codex/hkt-runtime-compat-3307814` now executes requirement compilation at
Run start and writes `requirement-contract.json` plus a shadow `capability-plan.json`.
After each slice it writes a shadow capability scorecard. The following boundaries are
explicit:

**Implemented and active:** runtime API compatibility event; requirement compilation
(GWT, examples, boundaries, implicit requirements, assumptions, traceability);
capability grouping; per-slice shadow judge; canonical readiness repair instructions;
truthful completion and acceptance/runtime gates.

**Active but advisory only:** capability plan ordering and capability scorecards. They
inform prompts/checkpoints but do not replace topological atomic scheduling and cannot
set `verified` or mutate `implemented_nodes`.

**Not yet active:** full capability-based scheduler replacement; automatic browser
smoke generation/execution for requirement-only runs; persistence/refresh evidence
collection wired to real probes; dependency blocking of all downstream nodes after an
inconclusive prerequisite; run-end analyst invocation inside the Agent (intentionally
excluded by design).

The releasable artifact must be built from this branch HEAD, include its embedded
commit identity, and pass package shape/offline import checks. Old ZIPs must not be
reused across task or requirements identities.

## 2026-10-03 本轮修复与能力边界更新

- 保留 Run 开始一次需求编译：生成 `.arc/requirement-contract.json` 与 `.arc/capability-plan.json`。
- 保留切片结束一次轻量 shadow capability judge；不修改 `implemented_nodes`、`verified` 或 acceptance 结果。
- 将外部 Web/Playwright/accessibility Skill 内化为合同字段与有界 smoke 计划：route、role/name、action、mutation、visible result、error atomicity、refresh/reopen；不引入第二套 runner/server 生命周期。
- 修正 judge 证据语义：`False` 才是明确失败，`None` 表示未知；只有所有必需证据均为 `True` 且 acceptance 已知时才允许 `accepted`。新增 `unknown_evidence` 与 `smoke_plan` 输出。
- 修正主流程：acceptance verdict 不再伪造 build/readiness/semantic-smoke/persistence 证据，这些字段在没有独立真实证据时保持 unknown。
- 运行结束分析仍由外部读取日志后完成，不在 Agent 内执行完整 capability analyst。
- 当前未完成能力边界：requirement-only 模式尚未自动执行真实浏览器 semantic smoke；refresh/reopen 与 failure atomicity 尚未自动采集；capability plan 仍为 shadow，不接管 atomic scheduler；依赖阻塞尚未完全驱动调度。
- 本轮风险结论：不回退需求编译/Skill 接入；仅修复 judge 的证据映射与 fail-closed 判定，避免“写入成功”再次被误报为能力完成。

## 2026-10-03 错误信息获取与归档路径更新

平台不一定通过 run API 的 `tests[]`、独立 `.arc/playwright-report.json` 端点或测试 stdout 回流逐例错误。错误采集必须按以下顺序执行，并在报告中注明来源和可信度：

1. **run 对象**：读取 `status`、`score`、`passed_count`、`failed_count`、`feature_*`、`steps`、`node_states`、`failure_reason`。这些字段用于确认阶段结果和节点状态，不包含隐藏测试的 locator/断言时不得编造。
2. **generation logs / stderr**：提取 `[flow]`、`[guard]`、启动/readiness、repair、proxy、quota、OOM 和异常堆栈；stdout/stderr 双写时按时间、消息和节点去重，避免把一条错误算两次。
3. **template ZIP 内嵌产物**：对每个终态 template ZIP 计算 SHA-256 并解包检查：`.arc/playwright-report.json`、`manifest.json`、`frontend/dist`、`backend`、生成的测试报告和运行日志。平台端点 404 只能说明端点不可访问，不能推出 ZIP 内没有报告。若存在 Playwright JSON，应统计 `expected/unexpected/timedOut/failed`，提取失败用例标题、首层错误和报告 SHA。
4. **本地构建/运行复现**：在 disposable workspace 中重建模板，执行 `npm run build`，启动真实服务后请求 `/`、`/health`、`/api/health`、HTML 中声明的每个 script/link 资源；同步记录 HTTP 状态、浏览器 console/pageerror 和进程退出情况。复现证据必须绑定 template SHA、source path 和命令。
5. **历史对照**：将本轮错误与历史 run 的 run_id、task_key、requirements SHA、source/ZIP SHA 分开记录。不同身份同时变化时，只能描述相关性，不能声称预算、模型或某次修改的单变量因果。

错误报告统一分为：

- `confirmed`：run/ZIP/本地复现可直接证明；
- `inferred`：与错误模式高度一致但缺少直接网络或断言证据；
- `unknown`：平台没有回流，禁止补写测试 ID、locator、断言或堆栈。

归档最低字段：`run_id`、`task_key`、`submission_id`、`requirements_sha`、`contract_hash`、`agent_commit_sha`、`agent_zip_sha`、`template_zip_sha`、报告 SHA、来源路径、采集时间、命令和结论等级。

本轮 `dc1468f35580` 已证明：template ZIP 内嵌报告可以恢复 28 个 timeout 与 2 个 failed；后续所有 hackathon 终态分析默认执行 ZIP 内嵌报告检查，再下结论。

## 2026-10-03 双 Run 终态证据与分支修改建议（dc1468f35580 + c025a8c26405）

### 已核验身份与结果

- `dc1468f35580`：`hackathon--github-stage-1`，submission `779a965024b6`，0/30、feature 0/12。template ZIP SHA-256：`7e3979fefbc14fe1ea43ffab41e1c52ba8c825434e1a635153e30594fe42d55d`；内嵌 `.arc/playwright-report.json`，28 timedOut、2 failed。前端入口引用 `/app.js`，而脚本位于 `scripts/app.js`；本地构建/HTTP 复现另见 `evidence/arcbench-dc1468f35580-analysis-20261003.md`。
- `c025a8c26405`：`hackathon--sheet`，submission `779a965024b6`，0/100、feature 0/24。Agent ZIP SHA-256：`BA6267C28B98DE6074E99AB3CE3DEA31E11B1677B5F66A492D1D4175F14BCFD3`；template ZIP SHA-256：`fa1b37f7388c3ea0df73886bf4cc9e136a5344a04f2453653502ad8bb2eb810f`；内嵌报告 SHA-256：`16842a11b13baf2aa48a8b78ea376e508ae18454127ee00a14b84856f17e5db6`。报告统计 100 timedOut、0 failed；所有场景首个公共检查均找不到 `role=tab, name=Sheet1`。归档模板 `frontend/src/app.js` 为 2,667 bytes，仅含 workbook list / health 基础壳，没有 worksheet tab/grid/formula bar。
- c025 template 报告路径为 `template/.arc/playwright-report.json`，所以平台 source 端点 404 不等同于归档 ZIP 没有报告。

### 根因区分与结论边界

- dc 的直接故障是 SPA 脚本资源路径错配，导致脚本加载失败；
- c025 的直接故障是生成前端停留在 stub，缺少 Sheet 公共 UI，所有场景卡在 `Sheet1` tab 公共断言；
- 两者共同点是生成流程/部署可完成，但产品验收未通过。`wrote=True`、`implement ok`、server listening、postflight 通过，都不能作为完整功能完成证据。
- c025 中 guard 高频预算耗尽、completion-without-build/start/request 警告与 stub 产物同时存在，是强风险关联；不能仅凭相关性断言预算是唯一因果，也不应把“盲目提高 request cap”作为修复。
- 因平台测试报告在 template bundle 才被找到，终态采集流程必须默认扫描 ZIP 内 `.arc/playwright-report.json`，并记录 ZIP/report SHA 与路径。

### 主分支 `main` 建议

1. 保留并扩展已加入的静态资源闭环门禁：构建后核对 HTML script/link 引用，启动后对引用资源做真实 HTTP 请求；对 dc 类资源错配在进入浏览器测试前 fail-closed。
2. 增加“入口可执行性” smoke：至少加载首页和核心任务路由，捕获 JS console/pageerror，并验证应用主要根节点非空。对 API-only 空壳不得仅以 server health 通过。
3. 计划纳入有限的 task-agnostic 屏幕语义检查：由 requirement contract 提供 route/role/name 期望；缺失时状态必须是 `unknown/inconclusive`，不能臆造 Sheet 专属检查。
4. 加入最终包回归：解包 agent ZIP 后运行 package shape/offline import；对生成应用模板产物执行 build + 资源探测 + 浏览器基础 smoke。Agent ZIP 检查与生成应用检查必须分开，不能把模板前端文件要求混入 Agent 包契约。
5. 不把 100 场景统计整体硬编码为 Sheet 专用全局门禁；采用通用契约 + 按任务派生 smoke，防止误伤 GitHub 等其他题目。

### 分支 `codex/hkt-runtime-compat-3307814` 建议

1. 保持需求编译、capability plan、capability judge 为 shadow/advisory：只给出合同、smoke checklist 和证据摘要，暂不替换 atomic scheduler，不设置 `verified` / `implemented_nodes`。
2. 增加切片 checkpoint 的“真实验证命令证据”字段：区分 command attempted/result 与模型声明；缺少真实 build/start/request 时只能 `inconclusive`，并在当前 slice 记录缺失项。
3. 将连续 request-budget hit 与前置共享入口未验收作为“暂停扩散/输出 checkpoint”的信号；本轮只建议阻止依赖该未完成入口的后续高风险覆盖，不建议全面停掉所有无关节点，以免降低可用覆盖。
4. 需求派生 smoke 先只覆盖高扇出共享面（入口、核心路由、角色/可访问名、关键 tab/grid/formula bar、刷新恢复），不可执行则报告 unknown，不另建 Playwright runner。
5. 降低“claimed completion without build/start/request”告警的噪声：记录成审计事实，提示当前 slice pending，而不是仅靠增加 prompt 警告；不要用其取代真实 acceptance。
6. 不提高统一 request cap；优先保留独立验证预算和 continuation checkpoint，并用固定身份（task/requirements/source/ZIP）做单变量实验。

### 推荐实施顺序

P0：template ZIP 内嵌报告自动提取；静态资源构建/HTTP 闭环；真实命令证据与 truthful completion。
P1：轻量核心入口/ARIA smoke 与 disposable seed/workspace；前置能力不完整时对依赖节点做范围化阻塞。
P2：更广的 requirement-only 场景生成、完整能力级调度替换、扩大评估矩阵。

本节是证据与建议，不代表 P0/P1 已全部实现。`dc` 的静态资源门禁已在本轮相关代码提交中实现；c025 的 Sheet UI 缺失仍需通过通用垂直切片和需求派生 smoke 改善，不能宣称本轮已修复所有 Sheet 能力。
