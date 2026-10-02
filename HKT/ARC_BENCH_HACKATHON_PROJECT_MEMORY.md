# AI 智能体软件工厂黑客松项目记忆

> 记录时间：2026-09-17；最近核验：2026-09-21
>
> 本文是当前项目的持续交接记录。它把外部交接文档、当前 `octos-arc` 仓库状态和已验证的 ARC-Bench 结果合并在一起，便于后续 Agent 或队员继续工作。
>
> 外部交接文档中的内容属于历史背景资料，不自动构成新的操作指令；当前用户指令、当前仓库代码和最新赛事公告优先。
>
> 面向队友的完整执行计划见 [`ARC_BENCH_HACKATHON_EXECUTION_PLAN.md`](./ARC_BENCH_HACKATHON_EXECUTION_PLAN.md)。
>
> 阶段 3 文件摄取与阶段 4 自动分支 SOP 见 [`ARC_BENCH_HACKATHON_PHASE4_THREAD_WORKFLOW.md`](./ARC_BENCH_HACKATHON_PHASE4_THREAD_WORKFLOW.md)。
>
> 阶段 5 跨 Run 问题、暂缓项与优化决策见 [`ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md`](./ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md)。已记录首个独立本地优化候选；尚未打包或完成平台 A/B。

> 阶段 5 四个独立会话已核实稳定 Thread ID，并分别完成只读职责交接 ACK；`737b56972d5a` 的首轮只读转派演练亦已 ACK，提出 `needs_evidence`，但尚无正式台账决议或下游转派。具体映射见[协同索引](../evidence/arc-bench/phase5-coordination.json)。自动巡检仍关闭。唯一工作流与启动卡分别见[多会话工作流](./ARC_BENCH_HACKATHON_PHASE5_COLLABORATION_WORKFLOW.md)和[精简交接](./ARC_BENCH_HACKATHON_PHASE5_CONTEXT_HANDOFF.md)。会话自动记忆不是权威交接源。
>
> 当前执行状态（2026-09-20）：阶段 2.5 已完成并通过；阶段 3、阶段 4、阶段 5 滚动执行，尚未宣告完成；本地候选已验证，平台 A/B 未完成。

## 0. 代码改动强制留档规则（用户长期指令，2026-09-21）

**后续所有代码相关改动都必须留档。** 每个代码切片必须至少记录：问题、授权或 handoff ID，基线与父提交完整 SHA，分支和工作树，改动文件与行为边界，提交信息与完整提交 SHA，验证命令及关键退出码，已知失败与风险，以及涉及打包时的文件名、条目门禁和 SHA-256。记录应与代码提交处于同一逻辑交付，并同步更新 `CHANGELOG.md`；阶段 5 改动还须回写[决策台账](./ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md)和[协同索引](../evidence/arc-bench/phase5-coordination.json)。没有上述记录的代码改动不得宣称完成、已验证或可进入平台运行。

### 0.1 最近一次代码交付

2026-09-21 已按上述规则归档 V3.1/V4 控制面切片：候选分支 `codex/arc-bench-v4-control-plane-gates`，基线 `d2fe4dbc7601242896b61b3a790a912732bc5d57`，最终 HEAD `13173bb50e556c78bcd9cfdcc25c5449eee37f65`。下一次受控平台测试包为 `octos-arc-bundle-13173bb50e55.zip`，SHA-256 `FDFA6090FDCCB18553ABEF07C6B5429AAB9B0979FB69A9A5D0053730A159EE1A`；Agent 根层级门禁通过，抽样入口文件与提交 blob 原字节一致。完整提交链、测试、已知 Windows 基线失败与平台边界见[阶段 5 决策台账第 20 节](./ARC_BENCH_HACKATHON_PHASE5_DECISION_REGISTER.md)。本轮未推送、未上传、未启动平台 Run。

### 0.2 阶段 5 会话写入边界（用户长期指令，2026-09-21）

当前“项目阶段5｜跨 Run 决策台账”会话（Thread `01a0bd66-5680-7e72-9e8a-24290780525e`）今后只做证据读取、事实核对、判断、信息收敛和决策/协同记录维护，**不得直接修改 Agent、业务代码、测试代码或打包实现**。任何需要代码写入的决定，必须先在本会话形成清楚的 issue、证据边界、授权状态、验收标准和 handoff，再交给“项目阶段5｜Agent 实现”会话（Thread `01a0bd66-75bd-7801-97fc-b3d1e136c112`）执行；实现结果通过提交 SHA、验证命令与产物哈希回交本会话归档。没有明确代码任务时不创建空转派。

### 0.3 近期阶段 3/4/5 队友交接（2026-09-24）

已新增[近期 Run 与阶段 3/4/5 队友协作交接](./ARC_BENCH_RECENT_RUNS_TEAM_HANDOFF_20260924.md)，统一收录 `1b0eaf914e94`、`88c08161c4d3`、`4bab82404c52`、`6d41952769f7`、`d9a97cb4c92d`、`32e08aaca2e4` 及本地 e04 实验的身份、分数、失败、证据 SHA、阶段结论、已解决问题、隐患和下一门禁；机器可读索引为 [`recent-runs-team-handoff-20260924.json`](../evidence/arc-bench/recent-runs-team-handoff-20260924.json)。当前 `d9a97cb4c92d / P5-017` 中 `REQ-4.3.1`、`REQ-6.1.1` 已由隔离复现确认为创建成功后 link/heading 语义与异步 fallback 机制，进入待用户授权的通用最小 Agent 切片；`REQ-8.1` 仍为时序敏感 strong candidate，必须单独闭合评分前 seed 和多轮时序。`4bab82404c52` 的模板单次替换和草稿路由遮蔽已经确定性复现，但只证明该次生成应用缺陷，不等于 Agent 已修复。Keep `88c08161c4d3` 与 `32e08aaca2e4` 仍须阶段 4完成后才能进入阶段 5。业务 GO 与严格 A/B 均为 false，未授权上传或新平台 Run。

## 1. 项目身份与范围

- 当前工作区是 `William-zwy/octos-arc`，远程为 `git@github.com:William-zwy/octos-arc.git`。
- 该仓库不是课程仓库 `code-philia/agentic-software-engineering-hackathon`；后者用于课程 Lab 和学习验证。
- 当前项目的核心目标是：用 Octos Agent Harness 驱动 ARC/ARC-Bench 的需求编译、代码生成、验收、修复和提交。
- 当前仓库更像“已经完成 ARC-Bench 验证的通用参赛 Harness”，还不是已经针对正式黑客松初赛题目冻结的最终提交包。

## 2. 资料来源的区分

本轮交接使用了三份外部资料：

1. `CODEX_CONTEXT.md（会话交接上下文文档） (1).md`：ARC-Bench 平台探索、Octos 适配层、Counter/Dice/Ticket Booking 实战记录。
2. `CODEX_SESSION_CONTEXT.md（Codex 上下文交接文档）.md`：课程、视频、学习指南和 ARC 方法论记录。
3. `codex-session-context.md`：课程仓库 Lab02 的 Windows 修复和实验记录，描述的是另一个仓库，不能直接当作当前 `octos-arc` 的代码状态。

资料中记录的赛事信息包括：研习营、线上初赛、决赛和深圳现场活动，以及“正式初赛可能围绕 GitHub + Lark 复刻”的判断。正式题目、提交入口、联网限制、截止时间和计分规则仍需以最新官网、赛事讨论区和提交页面为准。

## 3. 已完成工作

### 3.1 学习与课程准备

- 已整理官网、课程视频和课程仓库，形成学习指南、学习地图和费曼式解释。
- 课程仓库的 7 个 Lab 已经获取。
- Lab02 的 GUI TDD 离线演练已通过：最终验证 36/36。
- 已掌握比赛需要的核心方法：Harness Engineering、需求树编译、TDD、Training Test 与 Validation Test 的边界、Traceability、受限修复循环和成本/耗时度量。

### 3.2 ARC-Bench 平台探索

- 已探明平台是 SPA，需求、提交和运行数据通过登录态 API 获取。
- 已找到并分析官方 Agent Template。
- 已跑通上传、创建提交、配置模型、运行任务和读取成绩的流程。
- Ticket Booking 必须区分两个 catalog：历史 Playground 资料曾记录 6 个原子需求节点、30 个测试场景；当前 Competition 官方快照是 2 个模块、10 个公开测试。后续竞赛基线只使用 Competition 数据，不能混用 Playground 数据。
- 官网当前历史成绩使用的是官方 Demo，不是本队队友 Agent。Smoke、Smoke Evolution、Ticket Booking 等历史分数只能作为平台参考，不能作为本项目基线；包括 Smoke 在内的所有已发布子任务都必须用冻结的队友 Agent 重新运行。

### 3.3 当前仓库的 Harness 能力

主要入口和职责：

- `arc/main.py`：骨架、需求节点编排、设计/实现/修复、Evolution 和最终演练。
- `arc/requirement_order.py`：原子节点展开、依赖拓扑排序、祖先摘要和 Evolution 指纹。
- `arc/acceptance.py`：平台同款 Playwright 验收、应用启动、端口检查、失败摘要和 Playwright 隔离安装。
- `arc/codegen.py`：文件块解析、HTML charset 修复、扁平化 JavaScript 修复、导航去重等确定性修复。
- `arc/guard.py`：防止未验证宣称完成、连续重复错误和修改官方测试/需求文件。
- `arc/metrics.py` 与 `arc/arcbench_agent_runtime/`：Token、费用、耗时、节点状态、事件和 Traceability 记录。
- `crates/`：Rust 实现的 Octos Harness 内核；`arc/` 是 ARC-Bench 的 Python 适配层。
- `arc/pack.sh`：将适配层和公开测试打包为平台提交包；平台运行时通过 `OCTOS_RELEASE_URL` 获取 Octos 二进制。

已经完成多轮工程优化，包括：

- 单节点紧凑 codegen、Prompt 压缩、推理和请求数量控制。
- 多节点设计→实现→验收→修复流程。
- Evolution 增量编译和回归验收。
- Ticket Booking 双端口、CommonJS、服务端初始 HTML、无外部资源和性能契约。
- 官方测试目录写保护、测试数据还原、空测试报告识别和异常终态补齐。
- Playwright 预装探测、私有安装和浏览器路径隔离。
- 失败代码快照、最佳提交回滚和节点级 Traceability。

### 3.4 官网历史参考数据（非队友 Agent 基线）

仓库 `docs/results.md` 的成绩看板最后生成于 2026-09-13，属于官网官方 Demo/历史参考快照，不代表队友 Agent 的真实成绩，也不代表当前实时排行榜：

| 赛道 | 官网历史参考结果 | 成本 | 耗时 | 使用方式 |
|---|---:|---:|---:|---|
| Smoke | 100%，功能率 100% | ¥0.0095 | 24 秒 | 仅作官方 Demo 参考，必须重跑 |
| Smoke Evolution | 100%，功能率 100% | ¥0.0086 | 30 秒 | 仅作官方 Demo 参考，必须重跑 |
| Ticket Booking | 90%，功能率 50% | ¥0.25 | 3 分 18 秒 | 仅作历史参考，必须用 Competition 任务重跑 |
| ARC-Bench Web | 未上榜 | — | — | 不能据此判断队友 Agent 能力，必须重跑 |

仓库中的旧 evidence 可用于理解 Harness 的历史故障模式，但不能自动归因于本次冻结的队友 Agent。任何本地通过也不能等同于官网平台通过。

### 3.5 2026-09-17 冻结产出

- 官方 Competition 快照：`20260917-150121Z`，覆盖 6 个赛道、13 个当前可运行子任务、566 个官方测试计数和 821 个清单文件；821 个文件的大小与 SHA-256 均已校验通过。
- Ticket Booking Evolution 当前为 0 个已发布子任务，暂时只能记录发布状态，不能运行。
- 官方快照存在 5 个官方 404 图片引用：Ctrip 的 `index.jpg`，以及 Web/Lite Keep 各自引用的 `label_filtered_list.png`、`search_keyword.png`。这是官方资产缺口，不是本地下载失败；后续多模态处理必须允许缺图降级。
- 原始队友 Agent 构建：`teammate-baseline-20260917-ea503546`。
- 原始代码 SHA：`ea503546aad31b2e3b887235e3b35cc0a8b9cfe8`。
- 冻结 ZIP SHA-256：`812af3d15de93ce2955c6f2a0de7c6351d205b81e9fdf33f36fcd41387162ef0`，共 492 个条目，平台入口为 ZIP 根目录的 `main.py`。
- 原始 Agent 冻结提交：`3467e44286a81cf0d5d3cda7826429b215573c1e`；官方快照冻结提交：`28cce073a54638f1b6a31be6d196ea70887757ac`。两者均仅在本地证据分支，尚未推送远程。
- 原始字节哈希曾因 LF/CRLF 差异把 13 份本地 requirement 全部标记为不匹配；规范化和 YAML 语义比较确认 Web、Smoke、Smoke Evolution、Ticket Booking 共 11 题与官方语义一致，只有 Lite Keep 和 Lite BookStack 与 Web 同名版本存在真实差异。
- Ctrip 官方 YAML 与本地 YAML 都有 125 个 ATOMIC、101 个 FOLDER；API 的 `module_count=133` 是不同统计口径，不代表本地缺少 8 个原子需求。
- 公开测试规范化比较显示：Web、Smoke、Smoke Evolution 一致；Ticket Booking 只有辅助文件默认端口从 3301 更新为 3000；Lite BookStack 有 21/35 个文件发生真实变化，Lite Keep 有 29/33 个文件发生真实变化。

### 3.6 2026-09-18 至 2026-09-19 执行进展

- 阶段 2.5 平台汇合门禁已经完成并通过。Smoke Counter 与 Smoke Dice 均使用 A0 构建、官方快照 `20260917-150121Z` 和同一配置哈希完成独立绑定。
- Smoke Counter：run ID `a26913c7e4cf`，1781 tokens，21 秒，1/1 通过；Smoke Dice：run ID `1e9d8704a273`，856 tokens，39 秒，1/1 通过。
- 两次 Smoke 运行共用 submission ID `3ac91524402b`，模型为 `deepseek-v4-flash`，视觉模型为 `deepseek-vl-flash-vision-exp`，推理级别为 `reasoning-none`，配置哈希为 `3976454af8e94f17b3725f2dc8aaba1bbdd8a1cd9d48ca7a46525411b7edfcc9`。
- 平台入口已确认是 ZIP 根目录 `main.py`，测试来源已确认是 `/workspace/tests`，没有回退到 ZIP bundled tests；仓库不保存平台 API Key 值和原始平台日志。
- 阶段 3（原始证据收集与冻结）、阶段 4（单任务只读诊断）和阶段 5（共性问题汇总、通用优化与 A/B 验证）现已按第 6 节闭环并行执行。这里的“正在执行”不等于阶段完成，仍需逐项满足各阶段门禁。
- Lite Keep `0cef369cc925` 的补充证据已完成阶段 3 归一化登记：最终平台结果为 `31/32`、score `96.9`、`FAILED`，最终权威失败是 `REQ-2.5.4 Unarchive` 的 10 秒 Playwright 超时；Agent 内部全量验收为 round 0 `31/32`（`REQ-2.8.2`）→ round 1 `32/32`。两者是不同验收层，不能合并成一个“修复后全过”的结论。
- Lite Keep 的本次运行耗时 `13576s`（约 3.77 小时），平台 Token `58278570`，Provider `total_tokens=25433365`，请求数 `1004`，费用 `31.453807 CNY`，推理级别 `low`，时间预算 `48000s`。入口、`/workspace/tests`、未回退 bundled tests、run 归属和密钥脱敏均已核验通过。
- Lite Keep 补充证据 manifest：[`evidence/arc-bench/runs/0cef369cc925/manifest.json`](../evidence/arc-bench/runs/0cef369cc925/manifest.json)。manifest 记录了 7 个外部附件的大小和 SHA-256；原始附件仍由操作人保存在外部下载目录，未将原始日志、模板 ZIP 或任何密钥复制进仓库。
- 补充摘要中的“round 0: 26/32”与原始日志、run 对象和 Playwright 报告中的 `31/32` 冲突；按证据优先级保留该冲突并采用原始结构化字段，不静默改写摘要来源。
- Lite BookStack `00c59e0762fb` 已完成阶段 3 归一化登记，manifest 为 [`evidence/arc-bench/runs/00c59e0762fb/manifest.json`](../evidence/arc-bench/runs/00c59e0762fb/manifest.json)；最终平台结果为 `32/34`、`FAILED`，两项失败为 `REQ-4.5.1` 与 `REQ-6.1.3`。最终生成应用与 `.arc` 快照支持“处理函数存在但路由未接入”的判断，跨 Run 优化决策见阶段 5 台账。更细的 meter 请求明细及 BookStack 的独立构建/快照绑定仍待补齐。

## 4. 当前仓库状态

- 当前代码基线：`ea503546aad31b2e3b887235e3b35cc0a8b9cfe8`。
- 远程 `origin/main` 当前仍为上述代码基线；本地证据分支在该基线上保存 Agent 冻结、官方快照、Smoke 门禁证据、执行计划和阶段 3–5 协作记录。
- 当前证据分支为 `codex/arc-bench-official-snapshot-20260917`。后续优化代码应从原始代码基线建立独立分支/工作树，避免把约 95 MB 官方资产历史带入最终代码分支。
- 首个阶段 5 路由诊断切片位于独立分支 `codex/arc-bench-phase5-route-contract` 的提交 `c53c333d5205fb98bf168c1f4fc670c0eec7432f`；其后同分支加入 Keep 交互/种子契约，当前已核对完整 HEAD 为 `dddc94312d4cd26babdbfb9d7df2a17f08f0a51d`。两者是先后本地候选，不能混为同一构建或平台 A/B；该最新提交尚无可比的新平台验证。工作树 `.worktrees/phase5-route-contract/arc/` 中另有用户未跟踪 ZIP，不自动暂存或覆盖。
- 当前本地环境没有 Octos、Cargo 和 ARC-Bench API Key，但既定执行方式是把 ZIP 上传到官网，由平台注入运行时、模型服务、任务和公开测试，因此这些本地缺口不阻塞官网基线；它们只限制本地端到端复现。
- 仓库内没有复制外部资料中的 API Key；任何 Key 都必须通过环境变量或平台密钥管理，不得写入代码、日志、提交信息或公开文档。
- 阶段 2.5 已完成并通过；阶段 3、阶段 4、阶段 5 正常并行执行中。后续状态以 run 绑定、阶段 3 原始证据、阶段 4 诊断和阶段 5 A/B 结果为准。

## 5. 尚未完成的关键事项

### P0：正式参赛闭环

1. 继续用同一个冻结 A0 Agent、官方快照和已确认的平台配置完成全部 13 个已发布子任务的基线运行与阶段 3 证据冻结；官网历史 Demo 不参与基线比较。
2. 对已完成 run 持续执行阶段 4 滚动诊断，区分输入理解、规划、代码生成、修复循环和平台资源故障。
3. 阶段 5 仅根据阶段 3 原始证据和阶段 4 诊断实施通用 Agent 优化，并为每项修改建立同任务、同快照、同模型的 A/B 验证。
4. 将优化版新 run 重新交回阶段 3 和阶段 4，最终使用相同官方快照全量复跑 13 个子任务，比较完成率、Token、耗时、请求数和修复轮数。
5. Ticket Booking Evolution 发布子任务后，再补充原始基线与优化版复跑。

### P1：针对性提升

- 阶段 2.5 已确认平台提供 `/workspace/tests`；后续每个 run 仍要记录测试来源。如果未来发生 bundled tests 回退，保留 A0 原始构建，暂停该 run，并另建只同步官方公开输入的 A1 可运行基线。
- 优先补齐 Lite/Web 任务身份隔离、图片发现与哈希缓存、测试上下文压缩、Evolution 指纹、无进展停止和模型预算路由。
- Ticket Booking 需要重点观察官方辅助文件默认端口 3000 与旧包 3301 的差异，但不能再引用官网历史 9/10 作为队友 Agent 的当前成绩。
- 建立最终候选版本的单次隔离计量窗口，避免并发运行污染 Token、耗时和费用统计。

### P2：暂缓事项

- 暂不为了本地复现安装或编译 Octos/Cargo；官网运行不依赖这些本地组件。
- 不把官方 Demo 历史结果当作队友 Agent 成绩，也不据此跳过 Smoke 或其他任务。
- 不在缺乏真实基线证据时进行任务名称硬编码或大范围重构。
- 不因阶段 3、阶段 4、阶段 5 已经启动就提前宣告完成；必须分别以证据冻结、诊断复核和平台 A/B 结果通过各自门禁。

## 6. 阶段 3、阶段 4、阶段 5 协作工作流

> 当前状态（2026-09-19）：三个阶段均已启动并按本节流程正常运行；它们是流水并行关系，不是互相替代关系。

阶段 3 至阶段 5 固定采用“原始证据冻结 → 单任务诊断 → 通用优化与 A/B 验证”的闭环。原始材料只上传一次，后续阶段通过 `run_id` 和证据路径引用，不在不同会话中反复复制日志。优化版产生的新 run 必须重新回到阶段 3，不得直接以阶段 5 的运行摘要替代证据冻结。

### 6.1 阶段 3：收集、绑定并冻结原始证据

每个 ARC-Bench run 结束后，先进入阶段 3。阶段 3 只负责保存事实、核对来源和生成标准化指标，不解释根因、不修改 Agent 代码。

每个 run 应尽量收集：

- 平台 `run.json` 与完整 `logs.json`；
- Playwright `error-context.md`、失败截图、trace、video 和测试报告；
- 最终生成的 `frontend/`、`backend/`；
- `.arc/design/`、`.arc/codegen/`、Traceability、修复和回滚快照；
- 平台 meter 请求明细；
- 构建 ID、代码 SHA、ZIP SHA-256、任务快照 ID、submission ID 与 run ID。

阶段 3 必须从原始数据提取并记录：任务、模型、Reasoning、请求数、输入/输出/缓存/推理 Token、Provider 总 Token、平台 Token、费用、耗时、通过率、功能率、失败测试和运行终态。缓存 Token 是输入 Token 的子集，推理 Token 通常是输出 Token 的子集，均不得重复加到 Provider 总 Token 中。

阶段 3 的完成门禁是：run 身份没有混绑；原始文件清单和缺失项明确；敏感信息已脱敏；标准化记录能够回溯到原始证据。阶段 3 不因缺失部分附件而伪造完整状态，应明确标记 `missing` 或待补录项。

### 6.1.1 阶段 3 证据摄取的分层读取与冲突处理（2026-09-19 优化）

为了提高准确性并避免在每个会话反复消耗完整日志，阶段 3 固定使用“先索引、后定点”的读取顺序：

1. 先生成附件 manifest：文件名、角色、字节数、SHA-256、是否已入库；不先把原始日志全文放入上下文。
2. 读取 `run.json` 的最终状态、score、通过/失败数、失败测试、平台 Token、费用、总耗时、模型和 run/submission ID。
3. 只对 `logs.json` 做定点提取：入口、`tests_dir`、bundled 回退、代理配置、provider totals、内部 acceptance round、最终结果和敏感信息扫描。
4. 只有存在失败时，才读取 `playwright-report.json` 和 `failure-details.md`，提取失败测试、locator、超时、调用栈和 error-context 路径。
5. 只有阶段 4 需要追溯生成状态时，才读取与失败节点及其直接依赖相关的 `.arc` snapshots；不默认展开全部 design/codegen 内容。
6. 只有需要复现打包内容时，才读取 template ZIP 的文件清单、根目录和 SHA-256；不默认解压或把整包写入上下文。

不同文件承担不同事实职责：`run.json` 负责最终平台结果，`logs.json` 负责运行过程和内部验收，Playwright 报告负责最终测试细节，failure details 负责可读定位，snapshots 负责生成状态，template ZIP 负责包内容身份。人工 summary 只作为导航和补充，发生冲突时不能覆盖结构化原始字段。

每条记录必须拆开保存三类指标：

- `internal_acceptance`：Agent 自己的节点验收、round 和修复状态；
- `platform_final`：官网最终 Playwright 结果和 score；
- `metering`：Provider Token、平台 Token、费用和请求数等计量口径。

本次 Lite Keep 已验证该规则的必要性：Agent 内部 round 1 为 `32/32`，但最终平台仍因 `REQ-2.5.4` 超时而为 `31/32`；补充 summary 的 round 0 数字也与原始日志不同。后续不能使用“修复后全过”替代最终平台状态。

为节省 Token，阶段 3 的对外汇总只输出一页归一化记录、失败节点和证据路径；原始日志不复制到聊天，不重复粘贴同一条 stdout/stderr，不把缓存 Token 或 reasoning Token重复加到 Provider 总 Token。所有未解决的字段冲突进入 `conflicts`，不得通过猜测填平。

### 6.2 阶段 4：基于单个 run 做只读诊断

阶段 4 通过任务名和 `run_id` 读取对应的阶段 3 记录及原始附件，只做诊断，不创建新 run、不修改代码。会话标题和历史摘要只能用作索引，最终判断必须回到日志、测试产物、最终生成代码和平台权威结果。

阶段 4 的最省上下文入口是先读 manifest 和归一化记录，再只读最终失败用例的报告与快照；只有当根因仍不明确时，才扩大到相邻节点或完整日志。阶段 4 必须分别报告内部 acceptance 结果和平台最终结果，不能用其中一个推断另一个。

每个阶段 4 分析固定输出：

1. 已确认事实；
2. 根因判断及其证据位置；
3. 已排除原因；
4. 尚未确认的疑问；
5. 需要补充的证据；
6. 最小复现实验；
7. 是否建议进入阶段 5；
8. 建议修改位置，但不实际修改。

新增证据应先补录到阶段 3，再回到原阶段 4 会话复核，不为同一任务重复创建互相冲突的分析记录。阶段 4 应区分“平台故障、测试时序、生成应用缺陷、Agent 编排缺陷和计量口径差异”，不得把推测写成确认事实。

### 6.3 阶段 5：汇总共性问题、修改 Agent 并验证

阶段 5 读取阶段 3 的原始证据和标准化指标，再读取阶段 4 的诊断结论，最后对照当前代码确定跨任务共性问题。阶段 5 不要求用户重复上传已有材料；只有在原始附件不可读取或证据链断裂时，才请求重新提供具体缺失文件。

阶段 5 负责：

- 按完成率优先、Token 次之、耗时再次的顺序确定优化目标；
- 区分可复用的通用改进与任务名称硬编码；
- 选择最小维护变动，一次只改变一个主要变量；
- 修改 Agent、补充相应测试和计量；
- 生成新的可识别构建，并制定同任务、同快照、同模型条件下的 A/B 复跑；
- 比较完成率、首轮通过率、请求数、输入/输出/缓存/推理 Token、平台 Token、费用、耗时和修复轮数；
- 将优化版新 run 交回阶段 3，开始下一轮证据冻结与阶段 4 复核。

阶段 5 的修改不能仅以本地测试通过作为完成条件；平台结果仍是最终判定依据。Smoke 和小型 Evolution 的高效路径应单独保护，复杂 Lite/Web 任务的预算、上下文和修复策略不得无验证地影响简单任务。

### 6.4 阶段交接与证据优先级

阶段之间以 `run_id` 为主键，以 submission ID、代码 SHA、ZIP SHA-256 和任务快照 ID 补充绑定。出现冲突时，采用以下优先级：

1. 平台 `run.json` 的最终状态和测试结果；
2. 原始日志、Playwright 产物、最终生成代码和 `.arc` 快照；
3. 阶段 3 标准化汇总；
4. 阶段 4 分析结论；
5. 历史项目记忆和旧会话摘要。

当前 Lite Keep `0cef369cc925` 和 Lite BookStack `00c59e0762fb` 的后续 `error-context.md`、截图/trace、最终代码、`.arc` 快照和 meter 明细，统一作为阶段 3 证据补录；补录后先由阶段 4 复核，再由阶段 5 决定修改和验证方案。

### 6.5 文件夹上传后的阶段 4 会话分支

后续每个单 run 文件夹解析完成后，父会话只完成阶段 3 证据登记，然后按 [`ARC_BENCH_HACKATHON_PHASE4_THREAD_WORKFLOW.md`](./ARC_BENCH_HACKATHON_PHASE4_THREAD_WORKFLOW.md) 优先复用已有的同任务阶段 4 会话；找不到时才 fork 一个独立阶段 4 会话。父会话不在同一轮继续分析；阶段 4 会话只接收当前 run 的阶段 3 关键卡片、证据 manifest、冲突项和阶段 4 输出约束。

阶段 4 标题统一为 `NN 项目阶段4 + <competition-task>`，例如 `05 项目阶段4 + arc-bench-lite--keep`。`<competition-task>` 是会话定位键；`run_id` 不进入标题，而是写入 manifest、持久化 handoff/ACK/result 文件和分析正文。标题不是幂等依据，任务映射以 `evidence/arc-bench/phase4-thread-registry.json` 为准。同一任务后续收到新 Run 时只能复用唯一且已验证的会话，并用新的 `handoff_id`、manifest 和持久化结果文件切换当前分析对象；重复标题、空输出或映射不一致时先进入 `needs_reconciliation`，不得继续 fork。阶段 4 会话不得创建新 run、修改 Agent 代码、实施阶段 5 优化或把其他 run 的诊断结论混入当前事实判断。

### 6.6 阶段 5 多会话与记忆交接（2026-09-20）

阶段 5 固定区分“跨 Run 决策台账、隔离复现、Agent 实现、指标与 A/B 验收”四项职责。阶段 4 经持久化字段和注册表核验后，**先进入决策台账**，不直接修改代码；台账需要复现才转给隔离复现，复现结果必须返回台账裁决，获授权的 Agent 切片才进入实现。指标会话独立审计构建、任务快照、模型/配置、功能率及 Token/耗时可比性；平台新 Run 仍从阶段 3→4 回流。具体状态、幂等保护和自动化边界见[阶段 5 多会话工作流](./ARC_BENCH_HACKATHON_PHASE5_COLLABORATION_WORKFLOW.md)。

新会话只接收[精简上下文交接](./ARC_BENCH_HACKATHON_PHASE5_CONTEXT_HANDOFF.md)及其职责相关的证据路径；旧会话长历史可回读但不整段复制，更不能把聊天摘要当权威。用户提供的本地隔离复现交给复现会话，新的平台 Run 交给阶段 3。当前 `737b56972d5a` 已有已核验的阶段 4 结果，尚待新决策会话正式纳入；`4b792b72d7dd` 的阶段 4 路由仍在隔离状态，不自动分流。当前继续遵守“暂不推送远程、未经授权不启动新平台 Run”。

### 6.7 Web Keep `c68bef1a6343` intake (2026-09-30)

Run `c68bef1a6343` is now recorded as a separate `arc-bench-web--keep` evidence item: final `21/32`, score `65.6`, with ten official 10-second timeouts and one screenshot clipping failure. Its internal suite identity matches the Run task, so it must not inherit the Lite/Web suite mismatch from `8ea6503bfa95`. Phase 4 is now closed through the canonical-thread filesystem fallback, with all identity fields and manifest SHA matching. It confirmed generated-run DB contamination of delete fixtures and the initial view-toggle accessible-label mismatch; async refresh, Settings naming, and color screenshot timing remain strong candidates. Do not dispatch maximum-applicability Agent changes from this Run alone. Preserve the BookStack `53a102f3ee96` 34/34 baseline.

The durable record is [`ARC_BENCH_WEB_KEEP_RUN_C68BEF1A6343_HANDOFF_20260930.md`](./ARC_BENCH_WEB_KEEP_RUN_C68BEF1A6343_HANDOFF_20260930.md), with machine-readable index [`web-keep-run-c68bef1a6343.json`](../evidence/arc-bench/web-keep-run-c68bef1a6343.json).

## 7. 后续工作原则

- 当前仓库代码、最新平台结果和正式赛事公告优先于历史交接文档。
- 数据必须标明来源：官方 Demo 历史、队友原始 Agent 基线、优化 Agent 结果三者不得混用。
- Competition 与 Playground 是不同 catalog；Ticket Booking 等同名任务的数据不得跨 catalog 合并。
- 每次实验都记录：代码 SHA、任务、模型、环境变量、请求数、Token、费用、耗时、通过率和功能率。
- 一次只改一个影响变量，至少保留改前/改后可比较结果。
- 不修改官方 Validation Test、需求文件或平台保护路径。
- 不把平台偶发崩溃误判为业务代码缺陷，也不把本地通过误判为云端通过。
- 快照差异判断优先使用规范化文本哈希和 YAML 语义比较；原始字节哈希只能证明文件字节不同，不能单独证明需求变化。
- 远程同步完成前，不声称“已同步”；若网络或凭据不可用，应明确报告本地提交和远程同步状态。

### 7.1 官方需求包更新（2026-10-02）

官方新需求包已从用户提供的 `arcbench-hackathon-requirements (4).zip` 镜像到仓库：

- [需求包 v4（远程镜像）](https://github.com/William-zwy/octos-p/raw/codex/hkt-round345-integration/evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.zip)
- [需求包 v4 机器清单](https://github.com/William-zwy/octos-p/blob/codex/hkt-round345-integration/evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.manifest.json)
- ZIP SHA-256：`8F07E80BE1DB82F68F7AB373ACBD3AF28B735D719B83751D0A378C1043960BF9`

归一化比较结论：

- `hackathon--sheet` 仍为 `24` 个 atomic、`100` 个 scenario；与 v3 的 YAML 字节和规范化语义均一致，只有新包归档资产随 ZIP 一并更新。
- `hackathon--github` 仍为 `47` 个 atomic、`100` 个 scenario，但 `46/47` 个 atomic 的描述或 scenario 发生变化，不能继续使用 v3 的需求 SHA 或共享旧 fixture 叙事。
- 新包新增渐进式 GitHub 阶段：Stage 1=`12/30`（REQ-1/2），Stage 2=`14/29`（REQ-3/4），Stage 3=`21/41`（REQ-5/6）。三阶段合计仍为 `47/100`，但 stage task key 是独立输入，不能与主任务身份混用。
- GitHub 新文本更明确要求按场景隔离预置账号、组织、仓库、PR 和权限关系；生成应用必须按当前场景恢复 fixture，不能把历史 run 的 `alice-dev`、`Improve onboarding` 等共享状态当成稳定官方数据。
- 新文本继续把精确 accessible name/role、实体作用域、session/permission、服务端原子持久化和 reload 状态作为权威契约。官方测试细节仍不随 ZIP 提供，需求场景可以用于本地 contract/smoke，不得冒充官方测试结果。

机器可读哈希、节点/场景计数和比较方法见 `evidence/arc-bench/inputs/arcbench-hackathon-requirements-4.manifest.json`。v3 保留为历史输入，不删除、不覆盖。

## 8. 安全记录

外部交接资料曾包含明文 API Key。本项目记忆不复制该 Key，也不记录其值。应确认它没有进入 Git、日志、截图或公开文档；如曾暴露到不可信位置，应在平台轮换，并继续使用环境变量管理。

## 9. Web Stack Overflow `ca67b1d8ee97` 基础归档（2026-09-30）

本 Run 已完成阶段 3归一化，阶段 4尚待结构化结果。平台最终为 `60/66`、score `90.9`，6 项均为官方 10 秒 Playwright 超时；应用生成、部署和测试均实际到达。中间过程有 7 个 implement timeout、4 个 proxy error、两次未验证 full-suite repair 和 465 个残留进程清理，但没有 OOM 或已证实全局预算耗尽。Run JSON 与 Playwright 内部 stats 存在 `60/66` 对 `expected=60/unexpected=6` 的口径差异，按项目规则保留并以 Run JSON 为权威。

当前只记录三组待复核方向：Profile/Filter/Reply 可访问语义或页面状态，Answer 编辑/删除的 mutation 读回，Badge 的隐藏/seed/name 契约。它们都是本 Run 的 strong candidate，不是已确认的通用 Agent 根因。用户要求先收集多个 Run，再进行最大适用化修改；因此本 Run 不触发 Agent 实现、不启动平台 Run、不改变官方测试。完整事实、证据 SHA 和阶段 4边界见 `HKT/ARC_BENCH_WEB_STACKOVERFLOW_RUN_CA67B1D8EE97_HANDOFF_20260930.md`。
