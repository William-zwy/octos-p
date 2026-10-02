# ARC CLI 云端优化闭环部署

用户于 2026-10-01 授权部署。范围：Codex 修改 Agent，Git 同步、CI 验证、既有打包门禁、CLI 上传/云端评测、完整分页取证、回写现有 HKT 计划和日志。所有业务题目生成及官方评测在云端进行。

基线：`codex/hkt-round345-integration` @ `8f2af28713a336e90a61996dff21661ea3f30c70`。部署分支：`codex/hkt-cli-automation`，远程 `git@github.com:William-zwy/octos-p.git`。独立工作区 `235e` 为唯一部署写入者；原 `aeb0` Integrator 工作区保持只读，须停止并交接后才能集成。

## 已部署内容

- [`controller.py`](../scripts/arc_optimizer/controller.py)：单写入锁、原子状态、独立状态机，`doctor / ingest / collect / analyze / plan / context / step / loop` 入口。
- `collect` 的取证分析层：在原始 `status.json`、全分页日志、workspace/submission ZIP 和仓库 Run manifest 之上生成 `analysis.json`；按平台事实、日志观察、本地声明分层，保留 `unknown`，并给下一轮 Codex worker 提供 findings/actions/验收门禁。
- `ingest` 只建立外部证据目录的文件名、大小、SHA-256 和类型索引；不复制原始日志、ZIP、截图或凭据。`context` 通过 `git show`/`ls-tree` 记录另一分支的计划与 manifest blob 身份，不合并分支。
- `analyze` 可从新格式 `summary.json` 运行，也可从旧版 `status.json`、`collection.json`、日志页和 ZIP 断点重建取证；`plan` 输出 `optimization-plan.json`，默认 `plan_only`，不会修改 Agent。
- [`config.example.json`](../scripts/arc_optimizer/config.example.json)：配置模板；实际配置、凭据、日志、ZIP 均放仓库外。付费循环默认关闭，预算和截止时间不继承历史 36 小时窗口。
- [`login.py`](../scripts/arc_optimizer/login.py)：读取仓库外账号密码文件，按官网当前 `/api/auth/login` 契约换取 Cookie，既不打印也不提交凭据。会话过期后使用新输出文件重新登录并更新外部配置。
- [`install.ps1`](../scripts/arc_optimizer/install.ps1)、[`start.ps1`](../scripts/arc_optimizer/start.ps1)：外部 Python 环境安装、Windows 私有目录 ACL、前台/隐藏后台启动。固定 CLI 源提交 `15b0b27da4a4a0d412c79cbfaa318c59da5c3689`（0.4.0），PyYAML 6.0.3，Python 3.10+。
- [`worker.schema.json`](../scripts/arc_optimizer/worker.schema.json)：Codex 必须返回假设、证据、改动文件、风险和 candidate/stop/needs_evidence；控制器核对真实 Git diff 和允许路径。
- [CI 工作流](../.github/workflows/arc-optimizer-check.yml)：只运行模拟控制器测试、Agent helper tests、语法/空白检查；不跑题、不调用 ARC、不接触凭据。

## 本机操作

部署使用独立工作区中的脚本。实际配置在 `D:/DataMove/codex/runtimes/arc-optimizer/private/config.json`，Python 在同目录运行环境的 `Scripts/python.exe`。这些个人路径只供本次部署交接；跨机器应通过 install.ps1 和配置模板生成新路径。

在部署仓库根目录执行：

```powershell
# 登录、依赖、分支和三方 SHA 检查；不创建提交或运行。
./scripts/arc_optimizer/start.ps1 -Config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' -Mode doctor

# 采集已有 Run；不创建新的平台运行。
./scripts/arc_optimizer/start.ps1 -Config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' -Mode collect -RunId 877ac3bb19e7

# 索引仓库外的本地证据；只写 metadata，不复制原始文件。
python scripts/arc_optimizer/controller.py --config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' `
  ingest --run-id a7964e4411af `
  --source-dir 'C:/Users/dayuruozhi/Downloads/闻悦源代码-首轮测试-hackathon-sheet' `
  --metadata-only

# 读取已有采集结果，生成 analysis.json 和 optimization-plan.json；无 ARC 调用。
./scripts/arc_optimizer/start.ps1 -Config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' -Mode analyze -RunId a7964e4411af
./scripts/arc_optimizer/start.ps1 -Config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' -Mode plan -RunId a7964e4411af

# 记录 integration 分支上下文身份，不合并它。
python scripts/arc_optimizer/controller.py --config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' `
  context --branch codex/hkt-round345-integration

# 条件齐全后，每次推进一个状态，或启动有限轮数循环。
./scripts/arc_optimizer/start.ps1 -Config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' -Mode step
./scripts/arc_optimizer/start.ps1 -Config 'D:/DataMove/codex/runtimes/arc-optimizer/private/config.json' -Mode loop -Background
```

新机器安装时，显式传入现代 Python、固定 Git、已登录的 Codex 和仓库外 Runtime；Credentials 参数只是文件路径，不能传密码值。安装不会开启付费循环。

## 启动条件与止损

开启 `enabled` 前填写本轮 `budget_cny`、带时区的绝对 `deadline`、`max_rounds`、保守单轮估算 `estimated_run_cny`，并确认 `suite_key` 及平台来源 `suite_provenance`。官方隐藏 suite 不公开时不能猜测身份；原人工归档的 `platform_identity_inconclusive` 仍然成立，打包候选绑定不等于隐藏官方身份已闭合。

控制器每次优化/打包/上传/创建运行前检查截止时间、本轮累积成本和实时官方余额。至少保留 25%；默认最多两轮、一次无改善停止。官方预算与个人自费余额不混用；V1 仅支持 `--official-evaluation`。单轮估算是准入控制，平台计费可能超过估算，不能当作平台强制费用上限。已有云端运行会继续采集；本机等待超时或预算门禁不代表运行已取消。

身份未知、没有逐测试明细、无法下载 workspace、日志游标异常、CI 失败、未知工作区改动或分支分叉时，保存现场并停止下一次优化。当前实现不自动撤销差的候选；保留所有提交，依据结果追加通用修复。不同任务/未知基线不声称改善或严格 A/B。

## 如何接入现有资料

1. 每轮 Codex 读取总体计划、HKT 日志、决策台账和五份既有 Run manifest；以同任务最新采集结果为诊断入口。默认 Sheet 基线 `12b3dea74607`，不拿 GitHub `13/100` 与 Sheet 比较。
2. 一轮一个有证据的机制假设，限定 Python Agent 和对应单元测试；同时更新总体计划、HKT 日志、根 CHANGELOG 和决策台账。V1 不修改 Rust、官方测试、需求包或打包器。
3. 控制器提交、推送、核对本地/跟踪/GitHub 三方完整 SHA；候选必须通过对应源码 SHA 的 CI。
4. 复用 `arc/pack.ps1` / `arc/pack.sh`，进行结构、离线导入、构建身份及 SHA 绑定。只允许上传已同步的源码对应包。
5. 保存上传/创建运行意图后才调用 CLI。上传结果核对下载回来的提交包 SHA；run 响应按数组解析并持久化 ID。
6. 状态使用完整 JSON；日志必须保存 `--out` 的完整 payload，按 `log_offset` 续读，每个游标单独目录，不能用控制台 tail 冒充完整日志。终态另取 workspace 与 submission ZIP。
7. `analysis.json` 是实现 Agent 的工作入口：先处理 P0 findings，再只选一个 vertical slice；必须提交 source delta、build/start、行为 probe 和 requirement-to-file traceability。`official_test_ids` 为空时，`log_observed_test_ids` 只能作为日志观察，不能写成官方失败测试；身份未闭合时不能声称严格 A/B 或因果改善。
8. 原始证据留在外部目录；归一化 manifest 发布到 `evidence/arc-bench/automation/<run-id>.json`，同步更新上述 HKT 文件、根 CHANGELOG、`phase5-coordination.json` 的独立运行索引。历史人工 manifest 和线程分工不覆盖。

### 自动化阶段与执行闸门

```text
ingest/context -> collect -> analyze -> plan -> [explicit agent_edit] -> CI/package -> [explicit cloud_run]
```

默认执行策略为 `plan_only`。`optimization-plan.json` 会记录 objective、P0/P1 findings、capability slice、验收合同、预算策略、停止条件和授权状态。未显式授权前，Agent 修改、Harness/测试修改、打包和云端 Run 都保持 `false`；已有 Run 的采集和分析可以继续执行。

### 代码生成编排闸门

代码生成阶段由控制器在仓库外创建 disposable Git worktree，并以集成工作区的精确父 SHA checkout。Codex 只接收 `request.json`、分析结果和监控汇总，集成工作区不会被 worker 写入。worker 的 `result.json` 必须绑定 `parent_sha`、`plan_sha256`、`analysis_sha256` 和真实 `diff_sha256`，并列出 `changed_files`、`tests`、`build`、`skill_invocations` 与 `stop_reason`；控制器会重新计算 worktree diff 并拒绝未声明或被禁止的路径。

代码生成必须同时满足外部配置中的 `execution_policy=agent_edit`、`allow_agent_edit=true`、`codegen_authorization.enabled=true`，且授权绑定当前父提交、plan/analysis 文件 SHA 和带时区 TTL。`allow_harness_edit`、`allow_tests_edit`、`allow_package`、`allow_cloud_run` 在此阶段必须为 `false`。缺少或冲突的 `monitor-doc.json`、`monitor-runtime.json` 会被汇总为 `NEEDS-EVIDENCE`；控制器不启动监控子进程，也不会在该状态下生成代码。

候选只落盘到外部 state 的 `rounds/<n>/request.json`、`result.json`、`candidate.patch` 和 `reconciled-plan.json`，状态停在 `candidate_review`，等待 Integrator 审查和最终提交。该阶段不会自动应用 patch、打包、上传或创建 ARC Run。执行 `reconcile --run-id <id>` 可在已有两份监控报告时生成保守汇总。

CLI 下载的 workspace 未必包含完整 screenshots/traces/逐测试明细，缺失如实列出。stdout/stderr 镜像不可双计；内部 implemented/wrote/verified 不等于官方通过。CLI 的 `token_cost_usd` 必须与实际返回的 currency 配对，不能按字段名猜美元。

## 中断恢复

- `controller.json` 是当前控制器状态，`runs/<id>/collection.json` 是日志游标；进程退出后锁由系统释放。
- 状态/日志只读传输错误最多两次，第二次失败保留错误并停止。上传和 run 创建不自动重试。
- `worker_pending / upload_pending / run_pending` 表示结果可能不确定。先核对工作区、上传回执、平台现有 submission/run，不能直接把状态改回 ready。
- `run_pending` 如已有 run ID，只能对原 ID 检查/显式 `arcbench start`；不能重新 `run`。无 ID 时依据平台列表与提交/任务/时间核对，无法唯一确定则保持停止。
- `candidate_sync / evidence_publish` 可识别相同父 SHA 和提交信息的已完成提交，普通 push 后重新核对三方 SHA；未知提交或远程推进必须人工比较，禁止强推、reset 或丢弃文件。
- 停止后台控制器只停止本机循环，不等于取消远程 Run。需要取消时明确操作原 Run ID，并验证平台实际状态。

## 部署验证记录

- 模拟测试覆盖全量分页、断点恢复、末尾增量、未知/倒退游标、日志页数上限、错 Run、缺失 ZIP、身份不确定、CNY 计费口径、上传不确定、run 无 ID、预算/截止门禁、保护官方文件、文档门禁、单写入锁与密钥脱敏。
- 实际只读采集 `877ac3bb19e7`：状态 FAILED，13/100；日志游标 151868，完整 API 日志 payload 已排空；workspace 与 submission ZIP 下载成功。提交包 SHA `7649D9E925D6F29C9FF1CA009DFC134BD1283AD57FD44B76C871CAE028DD5649`，与已有人工归档一致。逐测试明细未公开，保持缺失。
- 实际只读采集 Sheet 基线 `12b3dea74607`：FAILED，1/100；日志游标 113673，workspace/提交 ZIP 均已取得。Codex `exec --sandbox read-only --output-schema` 联通检查退出 0，结构化输出通过，未执行工具或修改 Agent。
- 实际只读复采 Sheet Run `f1ff68f69dac`：FAILED，0/100；日志游标 110124，workspace/提交 ZIP 和仓库 manifest 均已取得。分析层确认 24 个生成节点、27 次预算触顶、部署与评测阶段到达；官方逐测试明细和身份绑定保持 unknown，生成的 `analysis.json` 供后续实现 Agent 读取。
- CLI 流程演练：`a7964e4411af` 外部目录索引 59 个文件、原始文件未复制；从旧格式 summary 断点重建取证并生成 `optimization-plan.json`，默认授权状态为 `agent_edit=false/package=false/cloud_run=false`。
- 付费循环未启动。最终 Git 提交 SHA 和 CI 结果以交付回执及 Git 记录为准，不在同一提交内制造自引用 SHA。
