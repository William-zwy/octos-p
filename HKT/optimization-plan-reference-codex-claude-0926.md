# Octos Agent 修改方案：借鉴 Codex 与 Claude Code

日期：2026-09-26

## 1. 方案目标

本方案基于以下两个仓库的实现进行设计：

- `D:\items\Hackathon\codex`
- `D:\items\Hackathon\claude-code`

目标不是复制两个仓库的代码，而是将其中适合 `octos-p` 当前架构的工程机制迁移到 agent 的执行闭环中：

1. 减少 full-suite repair 引入回归的概率。
2. 限制 repair 对无关文件和共享逻辑的破坏。
3. 区分可并行的分析任务和必须串行的写入任务。
4. 让 retry/repair 原因可记录、可比较、可调参。
5. 保持当前已经验证有效的 prompt、超时和 checkpoint 策略。

当前基础：

- `octos-p/arc/main.py` 已经有 full-suite 最佳状态保存和恢复。
- 已经有 `best_passed`、`best_sha`、`best_failures`。
- 已经有相同失败检测、失败漂移检测、repair rounds 和时间预算。
- 已经加入测试 helper 分析、ARIA locator、并发安全和简单实现提示。

因此下一步应以“小范围增强执行可靠性”为主，不应大规模重写 agent 架构。

## 2. 参考实现与可迁移程度

### 2.1 Claude Code：并发工具编排

参考文件：

`D:\items\Hackathon\claude-code\src\services\tools\toolOrchestration.ts`

核心模式：

```text
识别工具是否并发安全
    -> 只读工具组成并发批次
    -> 并发执行并收集 context modifier
    -> 批次结束后按稳定顺序合并共享状态
    -> 写入类工具保持串行
```

可以迁移到 `octos-p` 的思想：

- 读取 spec、读取源码、分析失败日志属于只读分析。
- 写代码、写 `.arc` 状态、commit、restore、启动和停止 server 属于串行操作。
- 并发分析任务不要直接修改 `Flow`。
- 结果统一收集后，再由主流程更新 `pending_corrections`、`test_verdict` 等状态。

不能直接复制的部分：

- Claude Code 使用 TypeScript async generator 和 `ToolUseContext`。
- `octos-p` 当前是 Python + `Flow` + 本地 acceptance runner。
- 应迁移控制逻辑，不迁移具体类型和调用框架。

### 2.2 Codex：结构化回归门禁

参考文件：

`D:\items\Hackathon\codex\scripts\mcp_conformance\review_regressions.py`

核心模式：

```text
为每个检查建立稳定 identity
    -> 保存 baseline
    -> 运行 candidate
    -> 比较 new / fixed / known / missing
    -> 新增失败或缺失检查时拒绝
```

这是本方案的最高优先级，因为 `octos-p` 当前已经在比较失败集合，距离结构化 regression gate 很近。

建议将测试 identity 统一为：

```text
(spec_file, test_title)
```

如果 `test_title` 不稳定，可以退化为：

```text
(spec_file, test_index, normalized_title)
```

### 2.3 Codex：有界 retry 和 fallback

参考文件：

`D:\items\Hackathon\codex\codex-rs\core\src\responses_retry.rs`

可以借鉴：

- 每类失败有明确 retry 上限。
- retry 原因结构化记录。
- 区分基础设施失败和代码行为失败。
- retry 耗尽后不再无限循环。

`octos-p` 已经有 repair rounds，因此不需要新增一套复杂重试框架。重点是把现有退出原因明确化。

### 2.4 Codex：patch 解析和修改范围检查

参考文件：

`D:\items\Hackathon\codex\codex-rs\apply-patch\src\lib.rs`

可以借鉴：

- 先解析和验证变更计划，再实际写文件。
- 检查路径、文件类型和变更范围。
- 对无关文件修改进行拒绝或告警。

`octos-p` 当前仍以完整文件 block 为主，因此第一阶段只增加 scope guard，不立即替换整个 codegen 协议。

### 2.5 Claude Code：turn/session 生命周期

参考文件：

`D:\items\Hackathon\claude-code\src\QueryEngine.ts`

可以借鉴：

- 明确 run、node、turn 三层状态范围。
- 每个 node 开始时清理 node-scoped 状态。
- 每轮 repair 都有明确预算和中止条件。

这是中长期重构项，不作为第一轮的核心改动。

## 3. 第一阶段：结构化 full-suite regression gate

### 3.1 修改位置

主要文件：

`D:\items\Hackathon\octos-p\arc\main.py`

必要时新增辅助模块：

`D:\items\Hackathon\octos-p\arc\acceptance.py`

### 3.2 新增数据结构

建议增加一个内部结果结构：

```python
{
    "spec": "requirements/REQ-2.4/update-note.spec.ts",
    "title": "updates note content",
    "passed": False,
    "error_kind": "behavior",
}
```

其中 `error_kind` 至少区分：

- `behavior`：页面行为、断言、locator、业务逻辑失败。
- `startup`：build、启动 server、端口或健康检查失败。
- `timeout`：测试或 server 超时。
- `infrastructure`：进程被 kill、内存不足、runner 无法完成。
- `unknown`：无法归类。

### 3.3 baseline 比较逻辑

首次 full-suite 运行结果作为当前 node repair 的 baseline：

```python
baseline_failures = {
    (result.file, result.title)
    for result in baseline_results
    if not result.passed
}
```

repair 后计算：

```python
candidate_failures = {
    (result.file, result.title)
    for result in candidate_results
    if not result.passed
}

new_failures = candidate_failures - baseline_failures
fixed_failures = baseline_failures - candidate_failures
known_failures = candidate_failures & baseline_failures
```

### 3.4 接受规则

建议使用以下规则：

1. `infrastructure` 或 `timeout` 导致整轮无法完成：
   - 不把这轮当作代码质量结果。
   - 不进行 repair。
   - 保留之前的最佳代码状态。

2. `new_failures` 非空且通过数没有严格增加：
   - 拒绝本轮 repair。
   - 恢复最佳 checkpoint。

3. 通过数增加且没有新增失败：
   - 接受本轮结果。
   - 更新 `best_sha`、`best_passed`、`best_failures`。

4. 通过数相同但失败集合变化：
   - 默认拒绝。
   - 视为失败转移，而不是有效改进。

5. 所有测试通过：
   - 立即 commit。
   - 结束 full-suite repair。

### 3.5 对现有逻辑的改动原则

当前 `best_passed` 和 `best_failures` 逻辑保留，不做删除。

新增内容主要是：

- 将失败结果规范化为稳定 identity。
- 记录 `new_failures` 和 `fixed_failures`。
- 将基础设施失败从普通测试失败中分离。
- 日志中输出结构化统计。

建议日志格式：

```text
[acceptance] baseline: 31/32
[acceptance] candidate: 31/32
[acceptance] fixed: 1
[acceptance] new: 1
[acceptance] known: 1
[acceptance] decision: restore-best
```

## 4. 第二阶段：affected-files scope guard

### 4.1 目标

防止 agent 为修复一个失败测试而重写：

- 无关页面
- 共享导航
- 全局事件处理
- 其他 node 已经验证通过的逻辑
- 测试文件和 runner 文件

### 4.2 允许修改范围

默认允许：

```text
frontend/**
backend/**
.arc/**
```

默认禁止：

```text
tests/**
requirements/**
arc/main.py
arc/acceptance.py
arcbench_agent_runtime/**
```

如果某些项目的目录结构不同，应通过配置或现有 workspace 检测动态确定，而不是写死单一项目路径。

### 4.3 repair 前后文件集合

在 repair turn 前记录：

```python
before_files = tracked_or_workspace_files(output_dir)
before_digest = tree_digest(output_dir)
```

repair turn 完成后记录：

```python
after_files = tracked_or_workspace_files(output_dir)
changed_files = changed_files_between(before_files, after_files)
```

然后检查：

1. 是否修改了禁止目录。
2. 是否新增了不允许的文件。
3. 是否修改了与失败 node 完全无关的区域。
4. 是否发生异常大范围改写。

### 4.4 处理策略

第一版不建议直接删除 agent 的修改，而是分级处理：

- 禁止目录被修改：
  - 记录 guard error。
  - 不接受本轮 commit。
  - 恢复到 repair 前 checkpoint。

- 修改文件数量明显过多：
  - 写入 correction。
  - 允许继续测试一次。
  - 如果没有严格改进，则恢复最佳状态。

- 只修改允许目录且范围合理：
  - 正常进入 acceptance。

建议初始阈值：

```text
单次 node repair：最多 8 个应用文件
full-suite repair：最多 12 个应用文件
```

阈值应通过本地模拟结果再调整，不要一开始设置得过低。

### 4.5 与 prompt 的配合

scope guard 不能只依赖 prompt，但 prompt 仍应明确告诉 agent：

```text
Only modify files directly related to the failing behavior.
Do not rewrite shared UI, routes, tests, requirements, or the runner.
Before editing, list the files you intend to change.
```

如果 codegen 输出支持文件 block，可以在应用前先解析文件路径并做预检查。

## 5. 第三阶段：并发分析与串行写入

### 5.1 当前问题

当前 agent 的关键状态集中在 `Flow` 中：

- `pending_corrections`
- `test_verdict`
- 当前 repair 状态
- checkpoint 和 commit
- 时间预算

如果未来增加并发分析，很容易出现多个任务同时修改这些共享属性。

### 5.2 建议结构

将 repair 流程拆成两个阶段：

```text
阶段 A：只读分析
    - 读取失败 spec
    - 读取测试 helper
    - 读取相关源码
    - 分析日志和 DOM/ARIA 线索
    - 输出 RepairAnalysis

阶段 B：主线程执行
    - 合并 RepairAnalysis
    - 生成 repair prompt
    - 调用 agent
    - 写文件
    - commit
    - 运行测试
    - 更新 Flow
```

建议 `RepairAnalysis` 至少包含：

```python
{
    "node_id": "...",
    "failure_keys": [...],
    "likely_files": [...],
    "failure_kind": "behavior",
    "shared_state_risk": True,
    "recommended_strategy": "targeted-event-handler-fix",
}
```

### 5.3 并发安全边界

可并行：

- 读取多个失败 spec。
- 读取多个相关源码文件。
- 对不同失败日志做独立归类。
- 生成只读分析结果。

必须串行：

- 写代码。
- 更新 `.arc`。
- 启动或停止 server。
- git commit。
- restore checkpoint。
- 更新 `test_verdict`。

## 6. 第四阶段：repair reason 和 retry budget

### 6.1 失败类型

建议在每次 repair 前生成结构化原因：

```text
same_failure
failure_set_drift
no_improvement
startup_failure
timeout
shared_state_regression
locator_mismatch
```

### 6.2 策略映射

| 原因 | 下一步策略 |
|---|---|
| `same_failure` | 强制重新阅读 helper、DOM 和相关源码，禁止重复上一轮修改 |
| `failure_set_drift` | 恢复最佳状态，缩小修改范围 |
| `no_improvement` | 不再扩大 repair 范围，优先保留最佳 checkpoint |
| `startup_failure` | 先修复启动/build，不进入普通行为 repair |
| `timeout` | 检查死循环、进程泄漏、共享锁和测试并发 |
| `shared_state_regression` | 检查全局内存状态、持久化数据和事件传播 |
| `locator_mismatch` | 重新对照 role/name/label/test id，不要重写业务逻辑 |

### 6.3 建议预算

保留现有总体 repair round 配置，同时增加每类失败的软上限：

```text
同一失败模式：最多 2 次
failure set drift：最多 1 次
基础设施失败：最多重试 1 次
无改进：立即停止当前 repair 分支
```

## 7. 第五阶段：Node/turn context 整理

这部分优先级较低，不建议在下一轮和 regression gate 同时大改。

建议未来引入：

```python
@dataclass
class NodeExecutionContext:
    node_id: str
    repair_round: int
    baseline_failures: set[tuple[str, str]]
    best_failures: set[tuple[str, str]]
    best_sha: str | None
    test_verdict: bool | None
    pending_corrections: list[str]
    last_failure_kind: str | None
```

作用：

- 明确哪些状态只属于一个 node。
- 防止上一个 node 的 repair 信息污染下一个 node。
- 方便输出每个 node 的完整执行摘要。
- 后续可以单独测试状态机。

## 8. 推荐实施顺序

### v5：先做 regression gate

修改：

- `arc/main.py`
- 必要时 `arc/acceptance.py`

内容：

1. 稳定化测试 identity。
2. baseline/candidate 失败集合比较。
3. 区分 new/fixed/known/missing。
4. 区分 behavior/startup/timeout/infrastructure。
5. 保留现有 best checkpoint 机制。

验证：

- `python -m py_compile`
- `git diff --check`
- acceptance 单元测试或最小模拟
- 使用已有 `octos-keep-0926-v2` 运行一次完整本地模拟

### v6：增加 scope guard

修改：

- `arc/main.py`
- `arc/codegen.py` 或相关文件应用逻辑

内容：

1. repair 前记录 workspace 文件状态。
2. repair 后计算 affected files。
3. 拦截禁止路径。
4. 输出变更范围日志。

验证：

- 正常 frontend/backend 修改应放行。
- 修改测试或 runner 应被拒绝。
- full-suite repair 的大范围修改应产生 guard warning。

### v7：并发分析和串行写入

修改：

- `arc/main.py`
- 必要时新增 `arc/repair_analysis.py`

内容：

1. 分离只读分析和写入执行。
2. 禁止分析 worker 直接更新 `Flow`。
3. 主线程统一合并结果。

验证：

- 多个失败 spec 同时存在时，日志和状态不应互相覆盖。
- `test_verdict`、checkpoint、commit 顺序保持稳定。

### v8：repair reason 和 context 整理

修改：

- `arc/main.py`
- 可能新增 `arc/models.py`

内容：

1. 引入结构化 repair reason。
2. 增加失败模式预算。
3. 将 node-scoped 状态集中到 dataclass。

## 9. 不建议当前阶段做的事情

暂不建议：

1. 直接把 Claude Code 的整个工具系统移植到 Python。
2. 立即把完整文件 block codegen 替换成复杂 patch 协议。
3. 同时大幅缩短 node timeout 或 repair timeout。
4. 仅依赖 prompt 解决并发和回归问题。
5. 因为某次模拟失败就重写现有稳定的 acceptance 流程。
6. 直接删除用户已有的 dirty worktree 改动。

原因是当前主要风险在 repair 后的状态判断和修改范围，而不是 agent 缺少完整的工具框架。

## 10. 最终验收指标

下一轮至少记录以下指标：

```text
总通过数 / 总测试数
full-suite 初始通过数
full-suite 最终通过数
fixed_failures 数量
new_failures 数量
failure_set_drift 次数
restore_best 次数
scope guard 拦截次数
每个 node 的 repair 次数
总运行时间
```

重点判断：

1. 是否仍保持原有 `31/32` 基线能力。
2. repair 后是否不再出现通过数下降却提交较差版本。
3. 是否能识别“失败数量没变但失败对象发生变化”。
4. 是否减少 full-suite repair 对共享代码的破坏。
5. 是否没有因为 guard 和额外分析显著超过时间预算。

## 11. 结论

建议下一步只实施 v5：

```text
结构化 baseline regression gate
    + 现有 best checkpoint 保留
    + 基础设施失败分类
```

确认 v5 不降低当前结果后，再实施 v6 scope guard。

这条路径风险最低，也最贴近 `codex` 和 `claude-code` 中真正适合 `octos-p` 的部分：把 agent 的“修复判断”从 prompt 层逐步提升到 runtime 层。
