# HKT 目录文档更新日志

## 2026-10-02：接入证据驱动计划版本与短探针重试

- 每轮 `collect/analyze` 会比较上一版优化执行计划，生成带 `plan_version`、父计划 SHA 和 `plan_comparison` 的新计划，并在 Run 私有目录保存历史版本。worker request 绑定当前计划版本；计划决策不是 `modify` 时拒绝代码修改。
- Campaign 任务增加短探针门禁：失败会保留证据并返回同一阶段重试，只有达到状态、分数和尝试次数条件后才开放下一阶段；达到上限后进入 blocked。
- Campaign 状态命令现在能区分 `completed`、`probe_failed`、`retryable` 和 `blocked`，阶段依赖不会因一次失败提前放行。

## 2026-10-02：补齐多任务预算与阶段状态门禁

- Controller 为每个 campaign 任务继续使用 `state_dir/tasks/<task_key>/`，并新增仓库外的 `campaigns/<campaign_id>/budget.json` 账本；已记录 Run 的消费不会在其他任务重复计入。
- `guard()` 在启动付费动作前同时检查任务本地预算和 campaign 共享预算，保留 25% reserve；五阶段估算合计 450 CNY，而 300 CNY campaign 的可用额度为 225 CNY，因此 E2 之后会按账本安全停止，不能误跑完整 E2→E6。
- Hackathon 的 `suite_key` 仍不猜测；`suite_provenance` 允许明确说明平台未提供 suite。打包门禁现在支持 `task_requirements_only` 身份模式，打包环境变量改用任务级 requirements SHA，不再把整个需求归档 SHA 当作任务身份。
- 新增只读 `campaign-status` 命令，输出各阶段状态、下一可启动阶段、任务命名空间和共享账本；它不登录 ARC、不调用 Codex、不上传、不创建 Run。
- CLI 预算与状态单元测试共 `69` 项通过；完整 Agent 测试仍有 Windows 临时 Git 工作树权限和路径分隔符兼容失败，未将这些环境问题归因于本轮 CLI 改动。

## 2026-10-02：增加多任务 Campaign 编排骨架

- 新增 task-aware campaign registry：为 E2 Sheet、E3/E4/E5 GitHub Stage 和 E6 完整 GitHub 分别保存任务级 requirements SHA、归档 SHA、阶段依赖、独立状态命名空间和端口范围。
- 控制器在提供 `campaign_file` 时把状态放入 `state_dir/tasks/<task_key>/`；远程 Run、代码生成和上传仍分别受并发和单写入门禁约束。
- 增加 `campaign-validate` 只读命令和 5 阶段注册表测试；默认远程并发为 1、只读采集并发上限为 2、代码生成并发固定为 1。
- 预算按任务和阶段隔离；当前 300 CNY 预算与五阶段各 90 CNY 的估算不足以覆盖完整 E2→E6 计划，预算门禁会安全停止。

## 2026-10-02：将需求 v4 Agent 资产合入 CLI 自动化分支

- 从 `codex/hkt-round345-integration` @ `087423e60e5500147aab3225937a442038fd33eb` 合入需求契约、seed isolation、垂直切片、打包门禁和对应测试；保留 `codex/hkt-cli-automation` 的控制器、运行手册、自动化证据和授权门禁。
- CLI 示例配置切换到需求 v4 归档：`evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.zip`，SHA-256 为 `8F07E80BE1DB82F68F7AB373ACBD3AF28B735D719B83751D0A378C1043960BF9`；suite 身份继续保持未猜测状态。
- 只保留发布绑定、形状和 SHA 元数据，未把源分支的原始 Agent release ZIP 复制到目标分支；需求 v4 输入 ZIP 作为后续 CLI 编译所需的受控输入保留。
- 合并后需重新执行候选验收、打包门禁和远程 Run 身份核验，不能把历史发布 sidecar 当作新 Run 证明。
## 2026-10-02：控制器续改与 CI 认证核验

- 增加受显式授权保护的 CLI 代码生成编排：Codex worker 仅在 disposable Git worktree 中运行，父提交、plan/analysis SHA、TTL 和 `execution_policy=agent_edit` 绑定；真实 diff、结果 `changed_files`、diff SHA、测试/构建记录均由控制器复核。候选结果只写仓库外 state 并停在 `candidate_review`，不自动应用、打包或启动 Run。
- 增加外部 `monitor-doc.json` / `monitor-runtime.json` 的保守 reconcile 输入；缺失、冲突或未知统一为 `NEEDS-EVIDENCE`。worker schema 升级为 v2，记录 parent/plan/analysis/diff identity、tests、build、Skill 调用和停止原因；本轮禁止 Skill 调用。
- 控制器测试覆盖监控冲突、授权 hash/TTL、禁止路径和 Python 3.12 `unittest.mock` API 兼容性。
- 增加显式 `approve` 入口：Integrator 审查 `candidate.patch` 后才可应用并进入 `candidate_sync`；父提交、patch SHA、变更路径和应用后 diff 均会再次核验，`start.ps1` 同步暴露 `reconcile`/`approve`。

- 修复控制器 GitHub 分支 SHA 查询：只在内存中读取既有 Git credential manager 的 HTTPS 凭据，Git fetch/push 仍使用固定 SSH 远程；token 不写状态、日志或仓库。
- `doctor` 在 GitHub、ARC 或本地工具检查失败时返回退出码 2，并保留私有错误证据；只读状态/日志/下载传输失败最多重读一次，上传和创建 Run 仍不重试。
- 新增 credential-manager、失败 Run 结果和只读重试测试。续改前后控制器模拟测试 `24` 项通过，退出码 0；CI 对提交 `5c304ef9b4e58a40a0f0a3b45a4b997398ab4901` 已成功。
- 新增远程结果的确定性分析层：`collect` 现在同时落盘 `analysis.json`，合并平台状态、去重后的全量日志、下载 ZIP、仓库 Run manifest 和本地文件 SHA；显式区分官方事实、日志观察和本地声明，未知不补全，并向 Codex 实现 Agent 注入优先级、验收门禁和禁止过度结论。对 `f1ff68f69dac` 只读复采成功，29 项控制器测试通过；未创建、启动或取消新 Run。
- CLI 扩展为 `ingest → collect → analyze → plan → context` 工作流：外部证据仅写 metadata 索引，旧格式 Run 可断点重建取证，`optimization-plan.json` 默认停在 `plan_only`，不会自动修改 Agent、打包或启动 Run。`a7964e4411af` 演练已完成，原始文件未复制。

## 2026-10-01：部署 ARC CLI / Codex 云端优化控制器

- 授权来源：用户“请开始部署”，范围为 CLI 取证与云端优化控制器；父/基线 SHA `8f2af28713a336e90a61996dff21661ea3f30c70`，分支 `codex/hkt-cli-automation`，独立工作区 `235e` 单写入。
- 新增 `scripts/arc_optimizer/`、专用 CI 和[操作手册](ARC_CLI_AUTOMATION_RUNBOOK_20261001.md)，复用现有打包/构建身份，保护官方测试、需求包、Rust 和历史证据。
- 更新总体计划、根 CHANGELOG、阶段 5 决策台账及协同索引的独立部署条目；不开放历史多会话自动派发。
- ARC 登录与 Codex 结构化 exec 联通验证通过；已有 GitHub `877ac3bb19e7`、Sheet `12b3dea74607` 终态、完整分页日志、workspace 和提交 ZIP 采集成功，逐测试明细保持 unknown。原始证据与凭据存仓库外。
- 验证：`python -m unittest discover -s scripts/arc_optimizer/tests -q`，23 项通过、退出 0；`python -m compileall -q scripts/arc_optimizer` 和 `git diff --check` 退出 0。Agent helper checks 由云端 CI 执行，不在本地跑题。
- 未修改 Agent、未上传或创建新 Run。付费循环等待当前预算/绝对截止时间/平台 suite 绑定；原 aeb0 工作区尚待停止及交接后集成。最终提交 SHA/CI 结果记录在交付回执与 Git 历史中。

> 最后更新：2026-09-24

---

## 2026-10-02：官方需求包 v4 归档与计划更新

- 镜像用户提供的 `arcbench-hackathon-requirements (4).zip` 到 `evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.zip`，SHA-256 为 `8F07E80BE1DB82F68F7AB373ACBD3AF28B735D719B83751D0A378C1043960BF9`，并新增机器可读 manifest。
- 归一化比较确认 `hackathon--sheet` 仍为 `24/100` 且 YAML 与 v3 完全一致；`hackathon--github` 仍为 `47/100`，但 `46/47` 个 atomic 的描述或 scenario 已变化，不能复用 v3 需求身份、fixture 叙事或 contract cache。
- 记录新增官方阶段输入：GitHub Stage 1=`12/30`、Stage 2=`14/29`、Stage 3=`21/41`；计划改为支持 stage-specific task identity、scenario fixture variant、阶段优先级和单独 exploratory 结果。
- 更新项目记忆和 Round 3/4/5 终版计划：优先重新编译 v4 requirement contract，隔离场景 seed，先用 Stage 1 做短探针；Sheet 仅作为相同需求哈希的兼容性回归，不把阶段结果与主任务分数混算。
- 本次只更新官方需求证据、项目记忆、计划和变更日志；未修改 Agent 源码、官方测试或平台 Run。

## 2026-10-02：截止前下一版 Agent 有效性最大化计划

- 基于 `a7964e4411af` 只读审计，裁决 cap `18 → 50` 仅改善过程吞吐，未证明完成率收益；相对历史同分 Run 成本约扩大四倍，不再作为全局默认提分策略。
- 纠正 `65c381d2` 提交依据中的计数口径：`92` 是 stdout/stderr 重复行，去重后为 49 个 cap 事件，不是 92 个节点。
- 将下一版 P0 收敛为：高置信 requirement contract、capability vertical slice、自适应预算与 continuation、seed 隔离、requirements-derived browser smoke。
- 明确现有 `0d580c74` 解决状态真实性/readiness/Skill 入包，但仍保留 cap 50 且未闭合 seed 与语义浏览器门禁；`c01437c9` 发布物保留为可追溯基线，不作为下一次最终提交的默认推荐包。
- 新增截止前代码修改地图、8 小时相对计划、go/no-go 门禁和降级顺序；完整六 Skill、跨 Run resume、全量 AST 和大规模模块化明确延期。
- 将硬截止固定为北京时间 `2026-10-03 23:59`，增加 D-18h 代码冻结、D-16h 包门禁、Sheet-first 探针、唯一一次证据驱动补丁、D-3h 停止新 Run 和 D-1h 最终上传缓冲。
- 增加平台软/硬成本止损和三条只读子 Agent 审查 lane；子 Agent quota/usage-limit 失败不得阻塞 Integrator，不能把多 Agent 可用性作为系统正确性的前提。
- 两个恢复额度后的子 Agent 完成截止倒排与源码可实施性复核：将完整 capability executor、双文件 seed 强协议和任意动作测试生成器裁为 A-lite/C/D-lite/E-surface/B-lite；默认预算改为 22 + 单次续作 12、上限 36，并增加 feature flags 与回退边界。
- 第一轮 Sheet 前移至 `2026-10-02 19:00` 前，唯一第二探针前移至 `2026-10-03 06:00` 前；`12:30` 停止探索、`15:00` 冻结最终包、`20:59` 完成最终上传，保留 3 小时灾备。
- seed 隔离首版改为 disposable workspace/data copy 与前后 hash，生成应用的 `seed.json/runtime.json + ARC_DATA_FILE` 强协议延期；semantic smoke 首版只做高置信只读 surface，完整动作/失败/refresh 生成延期。
- 本次只修改协作计划与变更日志，不修改 Agent、Skill、ZIP 或平台测试；远程推送继续暂停。

## 2026-09-30

- 归档 Web Keep Run `c68bef1a6343` 的阶段 3输入、终态/中间态指标、原始证据 SHA-256 和阶段 4待闭合状态。
- 新增 `ARC_BENCH_WEB_KEEP_RUN_C68BEF1A6343_HANDOFF_20260930.md` 与 `evidence/arc-bench/web-keep-run-c68bef1a6343.json`。
- 阶段 4已通过 canonical thread filesystem fallback 闭合；确认 DB seed 污染和初始视图 accessible label 两项 Run-local 根因，保留三项 strong candidate，不派发 Agent 修改、不触发平台 Run。

## 📁 文档列表

| 文件名 | 类型 | 创建/更新日期 | 摘要 |
|--------|------|--------------|------|
| `SUMMARY.md` | 总览 | 2026-09-24 | HKT 目录所有文档的总览与核心发现 |
| `ARC_BENCH_RECENT_RUNS_TEAM_HANDOFF_20260924.md` | 交接 | 2026-09-24 | 最新 Run 交接文档 |
| `ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md` | 台账 | - | 阶段 5 决策台账 |
| `ARC_BENCH_HACKATHON_EXECUTION_PLAN.md` | 计划 | - | 完整执行计划 |
| `ARC_BENCH_HACKATHON_PROJECT_MEMORY.md` | 记忆 | - | 项目记忆 |
| `ARC_BENCH_HACKATHON_PHASE4_THREAD_WORKFLOW.md` | 工作流 | - | 阶段 4 工作流 |
| `ARC_BENCH_HACKATHON_PHASE5_COLLABORATION_WORKFLOW.md` | 工作流 | - | 阶段 5 协作流程 |
| `ARC_BENCH_HACKATHON_PHASE5_CONTEXT_HANDOFF.md` | 交接 | - | 阶段 5 上下文交接 |
| **`ARC_BENCH_OPTIMIZATION_IMPLEMENTATION_20260924.md`** | **实施** | **2026-09-24** | **优化实施详细文档（新增）** |
| **`QUICK_REFERENCE_OPTIMIZATION_20260924.md`** | **参考** | **2026-09-24** | **优化快速参考（新增）** |

---

## 🆕 2026-09-24 更新内容

### 新增文档（2 个）

#### 1. ARC_BENCH_OPTIMIZATION_IMPLEMENTATION_20260924.md

**内容：** 完整的优化实施文档，包含三个新脚本的详细说明

**章节：**
- 📋 实施概览
- 🎯 脚本 1：arc-bench-gate.sh（四种模式：quick/preflight/canary/full）
- 🎯 脚本 2：arc-bench-milestone.sh（三个命令：upload-and-bind/validate-ab-pair/generate-frozen-seed）
- 🎯 脚本 3：arc-bench-repro-matrix.sh（噪声隔离与统计判定）
- 📊 预期收益对比
- 🚀 下一步工作（P0/P1/P2）
- 📚 参考文档
- ⚠️ 重要提示

**适用场景：** 需要了解完整技术细节、使用方法、借鉴来源

---

#### 2. QUICK_REFERENCE_OPTIMIZATION_20260924.md

**内容：** 优化方案的快速参考卡片

**章节：**
- 🎯 创建了什么（三个脚本的一句话描述）
- 💰 预期收益（成本对比表）
- 📋 当前状态（已完成/待实现/待授权）
- 🔗 相关文档
- 🚀 立即开始
- ⚠️ 关键限制

**适用场景：** 快速查阅、向他人解释、记忆关键点

---

### 新增脚本（3 个）

**路径：** `../scripts/`（上级目录的 scripts/）

| 脚本文件 | 行数 | 功能 |
|---------|------|------|
| `arc-bench-gate.sh` | ~250 | 多层验证门槛（quick/preflight/canary/full） |
| `arc-bench-milestone.sh` | ~280 | A/B 身份绑定（upload-and-bind/validate-ab-pair/generate-frozen-seed） |
| `arc-bench-repro-matrix.sh` | ~200 | 噪声隔离矩阵（10 次独立运行 + 统计判定） |

**当前状态：** ✅ 框架完成，🚧 核心执行逻辑待实现

---

## 🎯 优化目标

基于 `SUMMARY.md` 识别的三大瓶颈：

### 1. 成本控制（解决：每次改动¥18-37）

**方案：** `arc-bench-gate.sh` 的四层门槛

| 层级 | 成本 | 时长 | 过滤内容 |
|------|------|------|---------|
| quick | ¥0 | 5分钟 | Lint/格式/单元测试错误 |
| preflight | ¥0 | 1分钟 | 环境/认证/包结构问题 |
| canary | ~¥6 | 1小时 | 单任务早期失败 |
| full | ¥36-74 | 5-10小时 | 完整 A/B |

**预期：** 每 5 次迭代节省 ¥200-400

---

### 2. A/B 身份链（解决：P5-005）

**问题：** 多个 Run 缺 `task_snapshot_id`，无法反向构成严格 A/B

**方案：** `arc-bench-milestone.sh` 的身份绑定

**输出：**
- `upload-receipt.json`（含 agent_sha + snapshot_id）
- `ab-validation.json`（含 strict_comparable: true/false）

**效果：** 每个对比都有可追溯的 Git SHA → snapshot ID → Run ID 链

---

### 3. 噪声隔离（解决：P5-002/008/009）

**问题：** REQ-8.1 等 strong_candidate 无法确认是否为真实问题

**方案：** `arc-bench-repro-matrix.sh` 的统计判定

**逻辑：** 10 次独立运行 → 丢弃最快/最慢各 1 次 → 保留 8 次中 ≥6 次一致 → confirmed

**效果：** 
- 可区分 confirmed / false_alarm / timing_sensitive
- 节省 ¥120-250/问题（vs 10 次完整 Run）

---

## 📊 借鉴来源

### minimax-code

**文件：** `docs/performance-ci.md`

**借鉴内容：**
- 三级裁决：PASS / REGRESSION / INCONCLUSIVE（49-60 行）
- basic/full 模式分层（13-14 行）
- 噪声限制：丢弃极端样本（44 行）
- 回归预算：duration +25%+1s, CPU +20%+0.5s（40-42 行）

**应用：**
- `arc-bench-gate.sh` 的模式分层
- `arc-bench-repro-matrix.sh` 的极端值丢弃

---

### octos-p

**文件：** `docs/TESTING.md`, `scripts/ci.sh`

**借鉴内容：**
- 规范的里程碑命令（25-36 行）
- 脚本结构：section/pass/fail 标记（40-42 行）
- 多层门槛：静态检查 → 本地测试 → 平台集成

**应用：**
- 所有三个脚本的框架结构
- `arc-bench-milestone.sh` 的命令设计

---

## 🔄 与现有文档的关系

### SUMMARY.md（总览）

- **引用：** 四类失败机制、近期 Run 总表、跨 Run 问题索引
- **扩展：** 提供具体解决方案和工具

### ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md（决策台账）

- **依赖：** P5-005（A/B 身份链）的解决方案
- **输入：** `arc-bench-repro-matrix.sh` 的 verdict 更新台账

### ARC_BENCH_HACKATHON_EXECUTION_PLAN.md（执行计划）

- **补充：** 阶段 3 增加 quick/preflight gate
- **补充：** 阶段 4 增加 canary 验证
- **补充：** 阶段 5 增加 A/B 身份验证

---

## 🚦 下一步行动

### P0 - 已完成 ✅

- [x] 创建三个脚本框架
- [x] 编写完整实施文档
- [x] 编写快速参考文档
- [x] 更新 HKT 目录清单

### P1 - 待代码集成 🚧

1. **arc-bench-gate.sh：**
   - 实现 `canary` 和 `full` 模式的实际执行
   - 集成技能调用和分数读取

2. **arc-bench-milestone.sh：**
   - 实现平台 API 调用（上传/查询）
   - 实现 frozen seed 提取逻辑

3. **arc-bench-repro-matrix.sh：**
   - 集成技能调用（从 frozen seed 运行）
   - 实现 duration 排序和噪声计算

### P2 - 待授权验证 ⏸️

4. **REQ-4.3.1、REQ-6.1.1：**
   - 提取 frozen seed
   - 验证本地可重放

5. **REQ-8.1：**
   - 运行 10 次隔离复现矩阵
   - 更新决策台账

6. **首次 A/B：**
   - 上传带 receipt
   - 验证 strict_comparable: true

---

## 📝 使用建议

### 对于开发者

1. **日常迭代：** 每次改动先跑 `./scripts/arc-bench-gate.sh quick`
2. **上传前：** 必跑 `./scripts/arc-bench-gate.sh preflight`
3. **发布前：** 必跑 `./scripts/arc-bench-gate.sh full --base main --head feature`

### 对于决策者

1. **查阅：** 先看 `QUICK_REFERENCE_OPTIMIZATION_20260924.md`（快速了解）
2. **详细：** 再看 `ARC_BENCH_OPTIMIZATION_IMPLEMENTATION_20260924.md`（完整方案）
3. **追溯：** 结合 `SUMMARY.md`（问题来源和证据）

### 对于实施者

1. **框架：** 三个脚本已可执行，有 `--help`
2. **集成：** 按 P1 清单逐项实现核心逻辑
3. **验证：** 按 P2 清单逐项验证实际效果

---

## ⚠️ 关键注意事项

1. **三个脚本当前为框架模板**，核心执行逻辑（平台 API、技能集成）待实现
2. **预期收益基于假设**，实际节省需在 P2 验证后确认
3. **不授权直接改 Agent**，必须先完成隔离复现和决策台账更新
4. **不授权直接上传/Run**，必须先通过 preflight 和身份验证

---

## 🔗 快速导航

| 需求 | 文档 |
|------|------|
| 快速了解优化内容 | `QUICK_REFERENCE_OPTIMIZATION_20260924.md` |
| 完整技术细节 | `ARC_BENCH_OPTIMIZATION_IMPLEMENTATION_20260924.md` |
| 问题来源和证据 | `SUMMARY.md` |
| 跨 Run 问题状态 | `ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md` |
| 脚本源码 | `../scripts/arc-bench-*.sh` |

---

*本更新日志记录 2026-09-24 的优化实施工作，包含 2 个新文档和 3 个新脚本。*

## 2026-09-30：归档 Web Stack Overflow `ca67b1d8ee97`

- 新增阶段 3/4 交接、归一化 manifest、失败分析和阶段 4 handoff。
- 记录平台 `60/66`、6 个官方超时、实现/修复不收敛证据及 Run JSON/Playwright stats 口径冲突。
- 未修改 Agent、官方测试或打包器；未创建平台 Run；等待更多 Run 后再作最大适用化修改。

## 2026-09-30：复盘修复候选双 Run `2b6a1f545c37` / `0564f5955f16`

- 在 `ARC_BENCH_ROUND345_FINAL_PLAN_20260930.md` 追加两次 requirement-only Run 的阶段 3纠错、跨 Run 成绩/成本波动、Agent/Skill 分层候选和单探针 Go/No-Go。
- 纠正 stdout/stderr 镜像造成的重复计数：Sheet request-budget hit 为 29 个逻辑事件、rehearsal 独立失败 2 次；GitHub 分别为 51 和 1。两次最终 rehearsal、平台部署和官方 evaluation 均已到达。
- 记录所有 24/47 节点均命中 cap 8、`.arc/design` 写入会污染 `wrote=True`、当前 implementation 状态缺少 product-source delta 证据，以及 `arc-project-context` 尚未进入上传 ZIP/运行工具链的事实。
- 后续复核收窄 verification regime 的因果表述，拆分 `candidate_identity_closed` 与 `platform_identity_inconclusive`，并标记未镜像原始附件时本节仅为 analysis-only、不能作为阶段 5最终裁决。
- 本次只修改协作文档，没有修改 Agent、Skill、ZIP、requirements 或官方测试，也没有启动平台 Run。

## 2026-10-01：归档 GitHub Run `effd5e7777ce`

- 新增 `evidence/arc-bench/runs/effd5e7777ce/manifest.json` 和 `phase3-analysis.md`，记录 7 件本地附件的 provenance、大小、SHA-256、平台结果、ZIP 内归档身份、missing evidence 与 Phase 4 pending 门禁。
- 纠正 stdout/stderr 镜像口径：98 条 request-budget 日志为 49 个逻辑事件，92 条 implement-ok 为 46 次，rehearsal 失败为 1 次并在 repair 后恢复。
- 记录 `2/100`、47/47 节点 cap 16、0/47 verified、`REQ-1-1-3` 一次 900s timeout、2 次本地 proxy BrokenPipe，并保留官方 98 项失败类型与 timeout 为 unknown。
- 将该 Run 与 `451174abe760` 和 `0564f5955f16` 对比，明确 score `2/100` 并非系列首次非零，成本和耗时大幅增加仍不构成严格 A/B 收益。
- 更新 Agent/Skill 建议：产品 delta 与外部验证门禁、vertical slice、分阶段预算和止损；Skill 必须真实打包、可见调用且实际减少 provider 读取后才能评价。
- 本次只修改证据与协作文档，未修改 Agent、Skill、ZIP、requirements 或官方测试，未打包、发布或启动平台 Run。

## 2026-10-01：归档 Sheet Run `12b3dea74607`

- 新增 `evidence/arc-bench/runs/12b3dea74607/manifest.json` 和 `phase3-analysis.md`，记录 7 件本地附件的 provenance、大小、SHA-256、平台结果、ZIP 内归档身份、missing evidence 与 Phase 4 pending 门禁。
- 纠正 stdout/stderr 镜像口径：46 条 implement-ok 日志为 23 次，48 条 request-budget 日志为 24 个逻辑事件；24 个业务节点全部有写入，但只有 3 个 verified，`REQ-3-1-1` 一次 900s timeout。
- 记录 startup rehearsal 一次通过、官方 `1/100`、1 次本地 proxy BrokenPipe，并保留官方 99 项失败类型与 timeout 为 unknown。
- 明确历史 `002c882794af` 已是 `1/100`；本轮只构成弱正向探索信号，不能称首次得分或严格 A/B，也不能据此继续全局提高 request cap。
- 更新 Agent/Skill 建议：产品 delta 与外部验证门禁、vertical slice、分阶段预算和止损；Skill 必须真实打包、可见调用且实际减少 provider 读取后才能评价。
- 本次只修改证据与协作文档，未修改 Agent、Skill、ZIP、requirements 或官方测试，未打包、发布或启动平台 Run。

## 2026-10-01：归档 Sheet Run `f1ff68f69dac`（证据同步）

- 最初以 local-only 方式新增 `evidence/arc-bench/runs/f1ff68f69dac/manifest.json` 和 `phase3-analysis.md`；用户于 2026-10-01 授权将分析与归一化证据同步到协作分支，仍不授权 Agent/Skill 修改、打包或发布。
- 记录 7 件本地附件的 provenance、大小和 SHA-256，不复制大型原始附件；平台官方测试已完成，但逐测试明细和 timeout 类型仍为 unknown。
- 纠正 stdout/stderr 镜像和语义口径：24 次内部 `implement ok` 标签不等于全部实现；27 个独立 cap 包括 skeleton、nudge、24 个业务节点和 rehearsal repair；至少 11 个 ok 摘要明确自述未完成。
- 记录 skeleton/业务节点的 wrote/verified 假阳性、空 traceability、无写入 repair 后重试恢复，以及 `1/100 → 0/100` 只能作为 observed regression、不能归因为新包。
- 更新只读建议优先级：product delta 与 harness 外部验证、vertical slice、分预算槽、requirement-derived probes；Skill 未打包且无调用证据，不能评价收益。
- 未修改 Agent、Skill、ZIP、requirements 或官方测试，未重新打包、发布或启动平台 Run。

## 2026-10-02：下一轮平台候选的 Runtime / Skill / Prompt 联动

- 依据 `877ac3bb19e7` 等 requirement-only Run 的假完成、重复探索和 rehearsal 信号，增加产品源码 delta 门禁；无 delta、request cap-hit 或缺少成功写工具证据均不得记录为实现完成。
- requirement-only 路径改用 Harness 解析的有界需求摘要，禁止搜索不存在的测试和历史，并修正小任务 shell 被移除却要求 npm/curl 的契约冲突。
- rehearsal 增加 `/` 与 `/api/health` readiness；仅 favicon reset 可在核心路径健康且进程存活时降级，其他连接错误仍失败。
- 将现成 `skills/arc-project-context` 真正纳入 ZIP 和运行时 profile，增加 Linux launcher、父级 `OCTOS_SKILLS_PATH`、shape 强制项与行为烟测；不把 Skill 作为正确性前提。
- PowerShell 打包链新增 dirty-source 拒绝，与 POSIX 打包链共同防止工作树字节伪绑定旧 HEAD。
- 子 Agent 分别完成代码风险、测试覆盖和打包门禁的只读审查；本会话保持唯一写入者。
- 发布 Sheet-first 候选 `releases/arc-agent-hackathon-sheet-0d580c74.zip`：绑定源码 `0d580c748bf67d2425a49733e5a592ade21ebe4d`，ZIP SHA-256 `3f18da678504e147ce3748f23a829a63fc055fb61c056e53b03c1b0b2e3f79db`，Build ID `arc-agent-v1-30a08860f96969acadc74e1f`；package gate、offline import 和 Skill 行为烟测通过，平台 Run 仍由用户执行。

## 2026-10-01：归档 GitHub Run `877ac3bb19e7`（证据同步）

- 最初以 local-only 方式新增 `evidence/arc-bench/runs/877ac3bb19e7/manifest.json` 和 `phase3-analysis.md`；用户于 2026-10-01 授权与 `f1ff68f69dac`、`b4e114e9c001` 的分析一并同步，仍不授权 Agent/Skill 修改、打包或发布。
- 记录 9 个物理附件的 provenance、大小和 SHA-256，不复制大型原始附件；midrun/final logs 字节相同，实际只有 8 份唯一内容，且缺少 final traceability。
- 确认平台聚合结果 `13/100`、feature `3/47`、三个 step completed；该分数是当前已归档 GitHub Run 中最高观测值，但测试 ID、断言、timeout、hidden suite identity 与平台 Agent binding 均不可得，因此不构成严格 A/B。
- 纠正 rehearsal 口径：三次均因 favicon ConnectionReset 失败，两个 repair 均未证明有效产品修复，最终 submitting as-is；runner 后续独立 build/start 并进入测试，部署成功不能归因于 repair。
- 去重后为 47 次 implement-ok、33 wrote、11 verified、49 个独立 cap；至少 17 个摘要自述未完成，至少 8/11 verified 仍有实质缺口，继续确认内部完成状态假收敛。
- 记录 single-origin canonical entrypoint 是相对 b4e 部署恢复的强关联候选机制，以及相对 effd 通过项/成本显著改善；保留生成随机性与隐藏测试身份造成的因果边界。
- Skill 未打包、未调用；内联读取缓存与 provider cache hit 不得冒充 Skill 收益。
- 未修改 Agent、Skill、ZIP、requirements 或官方测试，未重新打包、发布或启动平台 Run。
- 拉取协作分支 `3d6713b1` 后复核身份链：`7fc46206`、`9ff7e750`、`3d6713b1` 均已可解析；对应 ZIP 的 `main.py` 与提交 Git blob 逐字节一致，`9ff7e750` release ZIP 还与下载包 SHA-256 完全一致。
- 纠正机制表述：`3d6713b1` 修改的是三处 prompt/architecture contract 与测试，没有新增 runtime harness 强制门禁；因此 single-origin 只作为更强的 prompt-level 关联机制，不升级为严格因果。
- 保留平台边界：候选源码提交可达不等于平台 generation identity、task snapshot、suite 或 submission binding 已闭合，相关 Run 仍为 `platform_identity_inconclusive`。

## 2026-10-01：归档 GitHub Run `b4e114e9c001`（证据同步）

- 最初以 local-only 方式新增 `evidence/arc-bench/runs/b4e114e9c001/manifest.json` 和 `phase3-analysis.md`；用户于 2026-10-01 授权将分析与归一化证据同步到协作分支，仍不授权 Agent/Skill 修改、打包或发布。
- 记录 7 件本地附件的 provenance、大小和 SHA-256，不复制大型原始附件；平台在 start_agent readiness gate 失败，官方测试未执行。
- 纠正口径：65 个 node-state 不是 65 atomic nodes；Agent 实际遍历 47 个叶子。47 次内部 ok 标签不等于全部实现；11 verified / 36 unverified、44 wrote / 3 no-write，人工保守确认至少 19 个摘要自我否定。
- 记录 48 个独立 cap（skeleton 1、nudge 1、feature 46/47）、空 traceability、无 Agent turn timeout/BrokenPipe/402/500/OOM，以及官方测试 timeout 应记 not reached。
- 将部署最强候选收窄为最终产物 canonical entrypoint/HTTP readiness contract 漂移：实际 `npm start` 的 API-only 入口不服务 `/` 或 frontend，另一个可服务根页面的入口未被启动；平台 probe 细节缺失，故不把候选写成已证实探针路径。
- 更新只读建议：唯一启动入口、runner-equivalent rehearsal、product-delta/外部验证门禁、分槽预算/vertical slice、task-correct identity；Skill 未打包且无调用证据，不能评价收益。
- 未修改 Agent、Skill、ZIP、requirements 或官方测试，未重新打包、发布或启动平台 Run。

### 2026-10-02

- CLI 自动化：为代码生成 worker 增加外部配置 `codex_auth_mode`、`codex_env_allowlist` 与一次性 `monitor_reconciliation_override`。provider 模式不再把 OAuth 登录状态误判为阻断；默认继续清理所有 API key，只有显式列出的中转 provider key（如 `RELAY_API_KEY`）会传入 `codex exec`，平台 ARC、Cookie、Token、Password、Secret 变量被拒绝，缺失凭据在启动前停止。监控例外精确绑定一个 Run、带 TTL、写入外部 marker，下一轮恢复双监控门禁。新增安全回归测试和运行手册说明。
- 新增 `run-with-provider.ps1`，在同一父进程中注入并清理 `RELAY_API_KEY`，确保前台 worker 和后台 loop 继承同一凭据来源；Key 文件必须位于仓库外。

- 完成首轮 Codex provider 隔离代码生成（诊断 Run `12b3dea74607`、父 SHA `6964fc817d96d2a62230e6d2ee2d5ea7acdc39c4`）；worker 返回 `needs_evidence`，Integrator 为 `NO-GO`，Agent 草稿未合入。记录观测到的预算触顶假通过、零额度语义和连续账本缺口，不把 worker 自报测试通过视为机制已验收。
- 修复 CLI 输出 schema 的 strict object 契约；修复全局必需 `reliable-git-sync` 与 blanket Skill 禁令冲突，仅允许只读加载该技能，不授权 worker 提交/同步。拒绝、超时或 needs-evidence 后保留源码、未知文件、diff 和停止原因，移除强制清理路径；源码父 SHA 不允许被 worker 改变。
- 为 package/upload/run 补显式布尔权限门禁；关闭权限时在打包或 mutation journal/API 请求前停止。53 项模拟控制器测试通过（exit 0），涵盖 strict schema、Skill 范围、拒绝/超时保全、干净清理与权限阶段。
- 归档 [代码生成审查元数据](../evidence/arc-bench/automation/codegen-12b3dea74607-20261002.json)，只提交文件大小、SHA 和分析。旧清理已移除该次工作树；日志取回的观测 diff 未匹配 worker 声称的最终 SHA，保持未验证，不使用它集成。控制器停为 `stopped`，短期授权关闭，一次性监控例外已消费；未创建候选包、上传或新平台 Run。
- CI `36970601177` 的控制器、Agent helper、语法和 schema 均通过，合成包门禁失败原因是工作流未加引号的 64 位全零 requirements SHA 被 YAML 解析为数字 `0`。仅给该 CI fixture 加引号，保留真实身份校验门禁；本地 YAML 类型/长度检查通过（exit 0）。新提交的远程 CI 结果由交付回执核验，不改变 Agent 或恢复付费循环。
- 连续性修复：新增显式 resume-codegen，归档旧 journal 原始字节/哈希与新授权/双监控身份；不重置 round/成本，尝试目录排他分配并保留旧 rounds/001。worker 使用与绑定 SHA 一致的实时 plan/analysis，不读取 summary 过期副本。59 项合成控制器测试、Python/PowerShell 语法和 diff 检查 exit 0；旧修复 CI 36971414191 全部成功。新 Agent 切片待双监控/生成/审查；无候选打包、上传或新 Run。
- 第二次代码生成 `001-attempt-002` 已实际完成：中转 provider、父e4a84c8、双新监控/plan/analysis/TTL绑定、独立attempt、旧journal原始字节及六件证据保全，连续性GO；实际候选diff SHA6982e8224be185444da0ab300d4391419d9b5a3536b5580d2853f0972a473e2a。helper50项通过；独立完整性5项4次失败、预算4项2项失败，源码NO-GO。缺口为遗漏节点假通过、codegen写后旧验收残留、verify预留被终结开销侵占、显式0/默认cap/阶段scope传播不完整。停止并关闭授权，保留源码/原始证据及下一版修复清单；仅提交[元数据与分析](../evidence/arc-bench/automation/codegen-12b3dea74607-attempt002-20261002.json)，正式Agent未合入、无候选包/上传/新Run。provider CNY费用未提供，token usage与平台费用分开记录。
