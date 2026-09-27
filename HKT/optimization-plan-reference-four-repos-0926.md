# Octos Agent 四仓库综合优化方案

日期：2026-09-26

参考仓库：

- `D:\items\Hackathon\ZCode`
- `D:\items\Hackathon\minimax-code`
- `D:\items\Hackathon\claude-code`
- `D:\items\Hackathon\codex`

目标仓库：

- `D:\items\Hackathon\octos-p`

## 1. 结论

四个仓库中，最适合 `octos-p` 的不是某一个完整框架，而是四类机制的组合：

1. **Codex：regression gate**
   - 稳定测试 identity。
   - 对比 baseline 和 candidate 的失败集合。
   - 区分 `new / fixed / known / missing`。
   - 新增失败或检查缺失时拒绝 candidate，并恢复 best checkpoint。

2. **minimax-code：结构化验证和修复原因**
   - 把失败映射为明确的 repair reason。
   - 将“测试失败”“启动失败”“环境失败”“没有进展”分开处理。
   - 记录 evidence、changed files、失败数量和当前 decision。
   - 检测重复修改和无进展循环。

3. **Claude Code：只读分析并发，写入串行**
   - 读取 spec、源码、失败日志等分析任务可以并发。
   - 修改源码、启动服务、运行 acceptance、commit 和 restore 必须串行。
   - 每一轮 repair 使用独立的 turn 状态、预算和结束条件。

4. **ZCode：有界恢复**
   - 区分永久失败和暂时失败。
   - retry 必须有次数、时间和 backoff 上限。
   - 保留状态 snapshot，并在恢复时输出可诊断状态。

推荐实现为：

```text
v6.5：structured repair context
     + affected-files scope guard
     + verification settlement
     + no-progress/runaway guard
     + v4.5 regression gate 和 best checkpoint
```

这套方案比直接复制 Claude Code 或 minimax-code 的完整运行时更适合当前 Python + Flow + acceptance runner 架构。

## 2. 四个仓库的可借鉴内容

### 2.1 ZCode

重点参考：

- `packages/desktop/src/scheduler/offPeakDispatchSettlement.ts`
- `packages/zcode-server-cli/src/supervisor/crashBudget.ts`
- `apps/zcode-cli/tools/prompt-trajectory/src/derive.ts`
- `AGENTS.md`

可以迁移：

- transient/permanent failure 分类。
- retry 次数、deadline、指数退避和上限。
- crash/restart budget。
- request snapshot 和上下文轨迹。
- reconnect、fallback、验证状态的显式记录。

不建议当前直接迁移：

- ZCode 的完整调度器。
- 与桌面端队列和服务进程绑定的 supervisor。

### 2.2 minimax-code

重点参考：

- `packages/agent-core/src/pi-turn-runner/llm-retry.ts`
- `packages/local-runtime-v2/src/service/turn-system/runtime-error-retry-policy.ts`
- `packages/local-runtime/src/thread-goal/verification-failure-reason.ts`
- `packages/local-runtime/src/thread-goal/verification-settlement.ts`
- `packages/agent-modules/context-manager/src/manager.ts`
- `packages/agent-modules/runaway-guard/src/guard.ts`
- workspace snapshot/diff 相关实现

可以迁移：

- logical call 与 physical attempt 分离。
- 只对明确可重试的 runtime error 重试。
- structured repair reason。
- verification settlement。
- changed files、insertions/deletions、scope 记录。
- fingerprint 和 repeated no-progress 检测。
- context token budget 和安全 compaction cut point。

这是四个仓库中对“困难云端题目修复质量”最有直接帮助的一组机制。

### 2.3 Claude Code

重点参考：

- `src/services/tools/toolOrchestration.ts`
- `src/QueryEngine.ts`

可以迁移：

- 连续只读工具并发。
- 写入工具和非 concurrency-safe 操作串行。
- run/session/turn 状态边界。
- 每轮 repair 的 max turns、max budget 和 timeout。
- structured output retry 上限。
- compaction boundary，防止上下文无限增长。

不建议当前直接迁移：

- 完整 TypeScript async generator 架构。
- 整个 QueryEngine/session 生命周期。
- 多 session bridge 和完整工具编排层。

原因是这些机制和 Claude Code 的消息协议、工具模型、TypeScript runtime 强绑定，直接搬运会扩大回归面。

### 2.4 Codex

重点参考：

- `scripts/mcp_conformance/review_regressions.py`
- `codex-rs/core/src/responses_retry.rs`
- `codex-rs/apply-patch/src/lib.rs`

可以迁移：

- 稳定 check identity。
- baseline/candidate regression comparison。
- bounded retry 和 retry reason。
- affected paths。
- add/modify/delete/move change summary。
- malformed 或 partial result 不得静默当作成功。

Codex 的 regression gate 已经在 v4.5 中成为 `octos-p` 的核心基础，应继续保留。

## 3. 推荐的 v6.5 设计

### 3.1 RepairContext

建议新增：

```text
octos-p/arc/repair_context.py
```

建议数据结构：

```python
@dataclass
class RepairContext:
    node_id: str
    repair_round: int
    failure_kind: str
    failure_reason: str
    current_failures: set[tuple[str, str]]
    best_failures: set[tuple[str, str]]
    fixed_failures: set[tuple[str, str]]
    new_failures: set[tuple[str, str]]
    missing_checks: set[tuple[str, str]]
    changed_files: set[str]
    likely_files: set[str]
    no_progress_count: int
```

它的作用是让 repair prompt、acceptance decision、rollback 和日志使用同一份结构化事实，避免每个流程分别推断状态。

### 3.2 Structured repair reason

至少支持以下 reason：

```text
same_failure
failure_set_drift
no_improvement
startup_failure
timeout
shared_state_regression
locator_mismatch
scope_violation
infrastructure_failure
```

推荐策略：

| reason | 下一步策略 |
|---|---|
| `same_failure` | 重新读取失败 spec、helper 和相关源文件；禁止重复上一轮相同改法 |
| `failure_set_drift` | 恢复 best checkpoint，缩小修改范围 |
| `no_improvement` | 停止扩大 repair 范围，切换策略或结束 |
| `startup_failure` | 只修 build、启动、端口和健康检查 |
| `timeout` | 检查死循环、进程泄漏、锁和并发；不要盲目增加 timeout |
| `shared_state_regression` | 检查全局状态、持久化、事件传播和共享组件 |
| `locator_mismatch` | 优先检查 role、name、label、test id 和渲染条件 |
| `scope_violation` | 拒绝本轮结果并恢复 checkpoint |
| `infrastructure_failure` | 标记为环境问题，不消耗普通代码 repair 轮次 |

### 3.3 Affected-files scope guard

repair 前后记录 workspace 文件集合和 tree digest：

```text
before_files
before_digest
repair turn
after_files
changed_files
```

初始策略：

```text
允许：
  frontend/**
  backend/**
  .arc/**

保护：
  tests/**
  requirements/**
  arc/main.py
  arc/acceptance.py
  arcbench_agent_runtime/**
```

建议阈值：

```text
单 node repair：最多 8 个应用文件
full-suite repair：最多 12 个应用文件
```

第一版不建议因为文件数量超限就无条件拒绝，而是：

1. 记录 warning。
2. 运行一次 acceptance。
3. 如果没有严格改善或引入新失败，则恢复 best checkpoint。

如果修改 protected path，应直接标记 `scope_violation`，拒绝并恢复。

### 3.4 Verification settlement

每轮 repair 都记录：

```text
baseline
candidate
fixed
new
known
missing
failure_kind
repair_reason
decision
restore_best
changed_files
```

candidate 只有在以下条件满足时才接受：

1. 所有检查通过。
2. passed 数严格增加，且没有 `new_failures`。
3. 失败集合变化符合当前明确的修复目标，且没有回归。

以下情况拒绝 candidate：

- 出现新的 behavior failure。
- 出现 missing checks。
- 通过数不变但失败集合发生漂移。
- 只修复一个测试却破坏另一个已通过测试。
- build/start/runner 失败且无法确认是应用行为问题。

### 3.5 No-progress/runaway guard

为每轮生成两个 fingerprint：

```text
failure_fingerprint = stable(current_failures)
change_fingerprint = stable(changed_files + diff summary)
```

停止条件：

- 相同失败集合和相同 changed files 连续出现。
- 连续两轮 passed 数没有增加。
- 连续两轮生成相同或高度相似的修复。
- repair 已达到 round、时间或 request budget 上限。

停止后保留 best checkpoint，不再继续生成无效 codegen turn。

## 4. 执行顺序

### 第一阶段：v6.5 核心成功率改进

修改：

```text
arc/main.py
arc/acceptance.py
必要时新增 arc/repair_context.py
必要时新增 arc/tests/test_repair_context.py
```

内容：

1. 将当前 acceptance 结果统一转换为 RepairContext。
2. 增加 repair reason 映射。
3. 增加 changed-files scope guard。
4. 增加 no-progress fingerprint。
5. 保留 v4.5 regression gate 和 best checkpoint。
6. 将 startup、timeout、infrastructure 从普通 behavior repair 中分离。

### 第二阶段：上下文和重试稳定性

在 v6.5 稳定后再做：

1. context token budget。
2. 安全 compaction cut point。
3. logical call / physical attempt 记录。
4. retry-after、指数退避和 jitter。
5. 只对明确可重试的 LLM/runtime error 重试。

### 第三阶段：有限并发

最后再考虑：

1. 并发读取 spec、源码和失败日志。
2. 统一收集分析结果。
3. 按稳定顺序合并 context modifier。
4. 所有写入、启动、测试和 rollback 继续串行。

不建议为了提速而并发写文件、并发启动多个服务或降低 acceptance 检查强度。

## 5. 验证方案

代码级验证：

```text
python -m py_compile arc/main.py arc/acceptance.py arc/repair_context.py
git diff --check
```

单元测试至少覆盖：

- stable test identity。
- new/fixed/known/missing 集合。
- behavior/startup/timeout/infrastructure 分类。
- scope violation。
- changed files 统计。
- 相同 failure fingerprint 的停止条件。
- candidate rollback。
- malformed 或空 acceptance 结果不被判定为成功。

模拟验证：

1. candidate 修复一个失败且不引入新失败：接受。
2. candidate 修复一个失败但引入一个新失败：恢复 best。
3. candidate 通过数不变但失败集合漂移：拒绝。
4. acceptance 启动失败：不进入普通 repair。
5. 连续两轮没有进展：停止。
6. 修改 protected path：拒绝并恢复。

完整模拟器不在当前机器，因此 `octos-keep-0926-v2` 的完整运行应在模拟器所在环境执行。当前机器只做静态检查和最小单元模拟。

## 6. 预期效果

不能承诺四个仓库的机制会让 32 个测试项必然全部通过，尤其云端题目难度和模型输出存在不确定性。

比较现实的收益是：

- 降低 repair 把已通过测试改坏的概率。
- 降低相同错误重复尝试的次数。
- 更快区分代码问题、启动问题、超时问题和基础设施问题。
- 减少 full-suite repair 的无关文件改动。
- 给困难题目提供更完整、结构化的失败上下文。
- 在保留 v4.5 的 `31/32` 能力基础上，提高最终修复成功率。

最重要的优化点不是“让 agent 更激进地改更多代码”，而是让它在每轮修复后能够可靠回答：

```text
这轮修复修好了什么？
引入了什么新问题？
改了哪些文件？
是否真的有进展？
下一轮应该继续、换策略，还是回滚？
```

## 7. 最终建议

下一次执行建议命名为：

```text
v6.5
```

优先级：

```text
P0  RepairContext + verification settlement
P0  affected-files scope guard
P0  no-progress/runaway guard
P1  context budget + safe compaction
P1  bounded LLM/runtime retry
P2  read-only analysis concurrency
```

不建议：

- 直接复制四个仓库的完整架构。
- 立即引入复杂并发框架。
- 用 prompt 单独代替 scope 和 regression 检查。
- 为了速度降低 timeout、测试覆盖或 rollback 保护。
- 在没有完成 v6.5 验证前同时大规模修改 v6、v7、v8 的所有目标。

## 8. 根据云端题目调整后的重点

已知云端题目为两个产品型工作区：

1. **Software engineering · GitHub-style ERP**
   - accounts、organizations、teams。
   - repositories、branches、issues、pull requests。
   - permissions。

2. **Data workspace · Google Sheets-style**
   - workbooks、worksheets、cells。
   - formulas、data operations、filters、validation。
   - pivot summaries。

这两个题目的难点不是单页面视觉还原，而是**跨页面共享状态和业务不变量**。因此 v6.5 需要增加领域感知的 repair context。

### 8.1 GitHub-style ERP 的主要风险

优先关注：

- organization、team、repository、user 之间的关系是否一致。
- repository、branch、issue、pull request 的状态转换是否正确。
- 权限是否同时影响页面可见性和后端操作。
- 创建、编辑、关闭、合并等操作后，列表、详情页和计数是否同步。
- 刷新或重新进入页面后，状态是否从持久化数据恢复。
- PR merge、branch 更新、issue 状态变化是否产生正确的关联结果。

该题更容易出现以下跨层失败：

```text
按钮显示正确，但后端拒绝或错误放行
详情页修改成功，但列表页仍显示旧状态
刷新页面后数据丢失
权限只在前端隐藏，没有后端校验
状态更新了，但关联计数、活动记录或筛选结果没有更新
```

### 8.2 Google Sheets-style workspace 的主要风险

优先关注：

- workbook、worksheet、cell 的层级和持久化关系。
- 单元格编辑、批量操作、筛选和验证之间的数据一致性。
- 公式解析、依赖单元格变化后的重新计算和错误值传播。
- 行列增删后公式引用、筛选结果和选区是否保持合理。
- pivot summary 是否基于当前数据，而不是旧快照。
- 计算结果、显示格式和底层存储值是否混淆。

该题更容易出现以下失败：

```text
输入值保存了，但公式没有重新计算
公式结果正确，但刷新后恢复为旧值
筛选只改变视觉显示，没有改变操作目标
批量操作越过 validation
pivot summary 没有随源数据更新
单元格坐标变化后引用关系错误
```

### 8.3 对 scope guard 的具体调整

不能简单规定“一个失败测试只能修改一个页面文件”。对于这两个题目，允许的修改范围应按业务闭环声明：

```text
允许：
  失败页面组件
  该页面直接使用的 API/handler
  对应的持久化模型或 store
  该功能必需的共享类型和 selector

默认保护：
  官方 tests/specs
  requirements
  acceptance runner
  与当前业务闭环无关的模块
```

每次 repair prompt 应先要求 agent 输出：

```text
business_flow:
state_owner:
read_path:
write_path:
persistence_path:
permission_boundary:
files_to_change:
invariants_to_preserve:
```

这样可以允许 GitHub-style ERP 的“权限 + API + UI”跨层修复，也允许 Sheets-style 的“cell store + formula engine + grid UI”跨层修复，同时避免无理由重写整个应用。

### 8.4 针对这两个题目的新 repair reason

在原有 reason 之外，建议增加：

```text
state_persistence_mismatch
derived_state_stale
permission_boundary_mismatch
workflow_transition_invalid
formula_dependency_stale
validation_bypass
```

对应策略：

| reason | 优先检查 |
|---|---|
| `state_persistence_mismatch` | store、API 写入、刷新恢复和序列化格式 |
| `derived_state_stale` | selector、缓存、计数、列表/详情同步 |
| `permission_boundary_mismatch` | 前端可见性、后端授权和资源归属 |
| `workflow_transition_invalid` | 状态机、前置条件、关联资源和操作幂等性 |
| `formula_dependency_stale` | 依赖图、重算触发点、错误传播和持久化 |
| `validation_bypass` | UI validation、批量入口、API handler 和最终写入层 |

### 8.5 新的验证优先级

针对云端题目，建议把验证优先级调整为：

```text
P0  持久化和刷新恢复
P0  共享状态在列表/详情/编辑视图之间同步
P0  权限边界和后端拒绝逻辑
P0  关键 workflow 状态转换
P1  公式重算、筛选、validation、pivot 派生状态
P1  regression gate 和 best checkpoint
P2  只读分析并发和上下文 compaction
```

因此，v6.5 的成功标准不应只看“修复了某个 locator”，还要检查：

```text
刷新后是否仍然正确？
换页面后是否仍然正确？
换用户或权限后是否仍然正确？
关联列表和派生数据是否同步？
失败是否来自真正的业务根因，而不是只修复当前页面表象？
```

### 8.6 对最终方案的影响

这两个云端题目使得以下机制的重要性明显上升：

1. **structured repair context**：必须描述数据流、状态 owner 和业务不变量。
2. **verification settlement**：不能只比较单个测试，要比较跨模块回归。
3. **scope guard**：从“文件数量限制”升级为“业务闭环范围限制”。
4. **no-progress guard**：避免 agent 反复修 UI 表象，却不修持久化或共享状态。
5. **Claude 风格的分析/写入分离**：先并发读取相关模块，再串行修改共享状态。

这也说明 v6.5 比单纯增加 retry 更可能提升云端成功率。对于这两类产品题，失败后多尝试几次相同的局部修改通常收益很低，真正需要的是让 agent 找到跨层状态根因。
