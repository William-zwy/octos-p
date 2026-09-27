# Octos Agent 优化记录：Round 1 v3

日期：2026-09-26

## 1. 优化背景

本轮优化基于以下测试结果：

- 运行目录：`D:\items\Hackathon\hackathon-local-simulation\runs\octos-keep-0926-v2`
- 被测 Agent：`D:\items\Hackathon\octos-p`
- 最终结果：`31/32` 通过，成功率 `96.9%`
- 最终失败：`REQ-2.4`（Update Note）
- 失败现象：测试点击 `Project ideas` 后，无法找到 `Note editor` dialog 中的 `Note content` textbox

关键问题不是单个节点完全无法实现，而是：

1. `REQ-2.4` 在节点级测试中曾经通过。
2. Full-suite repair 修改共享代码后，已通过节点发生回归。
3. 原有 `final_acceptance()` 会直接提交每一次 full-suite repair，没有保存和恢复最佳状态。
4. 失败节点集合发生漂移时，Agent 可能继续在一个更差的代码状态上修复。

## 2. 代码改动

主要文件：

`D:\items\Hackathon\octos-p\arc\main.py`

### 2.1 Full-suite 最佳状态保护

在 `Flow.final_acceptance()` 中增加了全量测试 checkpoint：

- 第一次 full-suite 结果作为初始最佳状态。
- 记录：
  - `best_passed`
  - `best_sha`
  - `best_failures`
- 只有当后续修复的通过数严格增加时，才更新最佳状态。
- 如果修复后通过数下降，恢复到之前的最佳 commit。
- 如果通过数不变但失败集合发生漂移，也恢复最佳状态并停止继续修复。
- 所有 repair rounds 结束时，再次确认当前代码处于最佳状态。

这样可以避免出现以下情况：

```text
31/32
  -> repair
30/32
  -> repair
最终提交 30/32
```

现在应保持为：

```text
31/32
  -> repair
30/32
  -> restore best
最终提交 31/32
```

### 2.2 Traceability 状态同步

恢复最佳代码后，同步根据最佳失败集合更新 `test_verdict`。

避免代码已经恢复到较好版本，但最终 traceability 仍然记录最后一次失败结果的问题。

新增内部逻辑：

```python
def restore_best() -> None:
    ...
```

### 2.3 Full-suite repair 提示收紧

补充 full-suite repair prompt，要求 Agent：

- 先读取失败 spec。
- 只读取和修改直接相关的 frontend/backend 文件。
- 保留所有已通过测试覆盖的行为。
- 不要为了修复单个测试重写共享 UI、路由或事件处理。
- 只有在失败证明确实相关时，才修改共享逻辑。
- 优先做最小修改，并验证失败路径。

### 2.4 实现阶段 Prompt 加强

同时保留并强化以下通用约束：

- 先分析测试 helper、DOM 结构和 accessibility locator。
- 文本、按钮名、label、test id 必须严格匹配测试。
- 避免不必要的抽象和额外功能。
- 避免复杂的 `stopPropagation`、`preventDefault` 和全局事件处理。
- 考虑多个 Playwright 测试并行访问同一个 backend。
- 持久化写入使用同步原子写入：
  `writeFileSync` + `renameSync`
- 尽早执行 build、启动和接口 smoke check。

## 3. 为什么优先修复 Full-suite 状态管理

本次运行已经显示：

- 节点级测试通过不代表 full-suite 一定通过。
- Full-suite repair 修改的是共享应用代码，风险高于单节点修复。
- 单纯继续增加 prompt 约束，不能阻止错误修复覆盖掉之前的好状态。

因此本轮的核心策略是：

> 将 full-suite repair 从“每次修改都提交”改为“只接受严格改进，失败则恢复最佳状态”。

这属于 Agent 流程层面的可靠性优化，不依赖某个具体页面或测试用例。

## 4. 验证结果

已完成：

- `python -m py_compile`
  - `arc/main.py`
  - `arc/guard.py`
  - `arc/acceptance.py`
- `git diff --check`
- 新 bundle ZIP 完整性检查
- 确认 ZIP 根目录包含 `main.py`
- 确认 ZIP 包含 `arcbench_agent_runtime`

尚未完成：

- 尚未重新执行完整的 4 小时级别本地模拟。
- 因此目前不能宣称 `REQ-2.4` 已经在新版本中最终通过。

## 5. 新 Bundle

新生成的 bundle：

`D:\items\Hackathon\octos-p\octos-arc-bundle_v4.zip`

SHA256：

```text
A9BCC8F290F4F093AE9DDF9BF946CE0ABABEE169C02EDC69C86D5A344D5DFA24
```

旧的 `octos-arc-bundle_v3.zip` 保留未覆盖。

## 6. 下一步验证建议

使用 v4 bundle 重新运行与 v2 完全相同的模拟任务，重点观察：

1. `REQ-2.4` 是否仍在节点级测试后通过。
2. Full-suite repair 是否导致通过数下降。
3. 如果 repair 后从 `31/32` 下降，日志中是否出现：
   `restoring best state 31/32`
4. 最终提交状态是否保持最佳通过数。

