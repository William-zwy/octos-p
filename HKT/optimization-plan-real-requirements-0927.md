# Octos Agent 真实云端需求校正版优化方案

日期：2026-09-27

## 1. 结论

需要修改优化方案，但不需要推翻 v6.5。

真实云端题目证明，v6.5 的方向是正确的：

- 保留 stable test identity、baseline/candidate regression gate。
- 保留 `new / fixed / known / missing` 比较。
- 保留 behavior、startup、timeout、infrastructure 分类。
- 保留 best checkpoint、rollback 和 no-progress guard。
- 保留 affected-files scope guard。

需要增加的是**领域感知的 repair context 和业务不变量验证**。真实题目不是单纯的页面按钮修复，而是两个跨页面、跨状态、跨模块的产品工作区：

- GitHub：身份、组织、团队、仓库、分支、Issue、Pull Request、Review、权限和 merge。
- Sheet：Workbook、Worksheet、Cell、公式、依赖重算、筛选、验证、排序和 Pivot。

因此建议把下一阶段命名为：

```text
v6.6-real
```

也可以在内部称为 `v6.5-real-requirements`。它是 v6.5 的真实题目适配版，不是重新设计一套 runtime。

## 2. 真实题目规模

### 2.1 GitHub 题目

文件：

```text
req/hackathon--github/requirements.yaml
```

规模：

- 47 个原子需求。
- 100 个场景。
- 包含账户、会话、组织、团队、仓库、分支、提交、文件、Issue、里程碑、Pull Request、Review 和 Branch Protection。
- 每个写操作都要求服务端持久化、当前 session 校验、目标对象权限校验和原子完成。
- 权限不是简单的累计等级，需要按照具体操作区分 Owner、Admin、Read、Triage、Write、Maintain 等角色。

最容易影响成功率的复杂闭环：

```text
登录 session
  -> 组织/团队成员关系
  -> 仓库有效权限
  -> 分支与提交状态
  -> PR 当前 compare commit
  -> review 是否仍然有效
  -> branch protection
  -> merge 时重新校验并原子更新多个对象
```

尤其是 PR merge，不能只把 PR 状态改成 `Merged`。真实要求包括：

- 重新读取目标分支 head。
- 重新读取当前 compare commit。
- 检查冲突、草稿状态、审批、Request changes 和 status check。
- 创建 merge commit。
- 更新目标分支 head。
- 更新 PR 状态、merger、时间和结果 commit。
- 任一步失败时，目标分支和 PR 都保持原状态。

### 2.2 Sheet 题目

文件：

```text
req/hackathon--sheet/requirements.yaml
```

规模：

- 24 个原子需求。
- 100 个场景。
- 包含 Workbook、Worksheet、行列结构、Cell 编辑、公式、复制粘贴、Undo/Redo、排序、筛选、Validation 和 Pivot。
- 编辑器必须支持直接 URL 恢复同一个 workbook 状态。
- Workbook、Worksheet、Cell、公式、规则和派生结果必须互相隔离并持久化。
- UI 还包含明确的 ARIA contract，例如 `tab`、`grid`、`gridcell`、`aria-selected` 和可访问名称。

最容易影响成功率的复杂闭环：

```text
cell/store
  -> formula dependency graph
  -> calculated result
  -> formula bar
  -> filter/validation/pivot derived state
  -> refresh/reopen persistence
```

尤其要注意：

- 公式栏显示原始公式，网格显示计算结果。
- 源单元格变化后，直接和间接依赖都要按依赖顺序重算。
- 行列插入、删除、复制和粘贴要调整相对引用，保留绝对引用。
- 公式错误只能影响相关依赖，不能污染无关单元格。
- 过滤只影响可见性，CSV 导出和 Pivot 仍按题目要求读取完整源数据。
- Pivot 刷新失败时，要保留上一次成功结果。
- 批量粘贴、行列操作和 validation 失败时不能留下半完成状态。

## 3. v6.5 已经足够的部分

以下能力不应删除或弱化：

### 3.1 Regression gate

每轮 acceptance 都要稳定比较：

```text
baseline_checks
candidate_checks
fixed_failures
new_failures
known_failures
missing_checks
```

candidate 不能只因为 passed 数增加就接受。以下情况必须拒绝并恢复 best checkpoint：

- 引入新的 behavior failure。
- 原有测试结果缺失。
- 通过数不变但失败集合发生漂移。
- 只修好一个页面，却破坏已通过的跨页面流程。
- acceptance、build 或启动结果不完整。

### 3.2 Failure 分类

仍然需要区分：

```text
behavior
startup
timeout
infrastructure
pointer_interception
locator_mismatch
```

不要把 Playwright 的基础设施异常、服务启动失败或 OOM 当成普通产品行为问题交给模型重复修复。

### 3.3 Best checkpoint 和 no-progress

以下机制对云端复杂题目更加重要：

- 每轮保留最佳通过状态。
- 记录 changed files 和 app digest。
- 检测相同失败、相同修改文件和相似修复。
- 连续无进展时停止当前策略。
- 回滚候选修改时不破坏最佳状态。

## 4. 必须升级的部分

### 4.1 RepairContext 从通用失败上下文升级为业务闭环上下文

当前 `RepairContext` 已能记录失败集合、失败原因、证据和 changed files，但还不能清楚告诉模型“这条数据由谁拥有、从哪里读、写到哪里、刷新后由谁恢复”。

建议新增字段：

```text
product_domain:
business_flow:
state_owner:
read_path:
write_path:
persistence_path:
permission_boundary:
derived_state:
workflow_transition:
invariants_to_preserve:
files_to_change:
seed_entities:
session_context:
```

字段含义：

- `product_domain`：`github` 或 `sheet`。
- `business_flow`：当前失败属于登录、创建仓库、PR merge、公式编辑、Pivot 刷新等哪条闭环。
- `state_owner`：状态的权威来源，例如 server store、repository model、workbook store、cell store。
- `read_path`：页面或测试读取结果经过的 selector/API/store。
- `write_path`：用户操作写入的 handler、action、store 或 API。
- `persistence_path`：刷新、直接 URL 或重新登录后恢复数据的路径。
- `permission_boundary`：当前 session、对象归属和操作角色。
- `derived_state`：列表、计数、筛选、公式结果、Pivot 结果等派生数据。
- `workflow_transition`：允许的状态迁移，例如 `Open -> Closed` 或 `Draft -> Open`。
- `invariants_to_preserve`：修复后必须保持的跨模块不变量。
- `files_to_change`：按业务闭环列出可修改文件，而不是只按单个页面限制。
- `seed_entities`：当前场景依赖的 seed 账号、仓库、分支、workbook 或 worksheet。
- `session_context`：当前浏览器 session 和用户身份。

### 4.2 新增 failure reason

在已有 reason 之外，建议增加：

```text
state_persistence_mismatch
derived_state_stale
permission_boundary_mismatch
workflow_transition_invalid
formula_dependency_stale
validation_bypass
accessibility_contract_mismatch
atomic_write_violation
seed_or_session_isolation_failure
```

推荐的 repair 顺序：

| reason | 优先检查 |
|---|---|
| `state_persistence_mismatch` | server store、写入 handler、序列化、刷新恢复、直接 URL |
| `derived_state_stale` | selector、缓存、列表/详情同步、计数、筛选结果 |
| `permission_boundary_mismatch` | 当前 session、资源归属、有效角色、前端隐藏和后端拒绝 |
| `workflow_transition_invalid` | 状态机、前置条件、关联对象、终态限制 |
| `formula_dependency_stale` | 依赖图、重算触发点、相对/绝对引用、错误传播 |
| `validation_bypass` | grid、formula bar、paste、row/column 操作和最终写入层 |
| `accessibility_contract_mismatch` | role、accessible name、`aria-selected`、菜单和 option |
| `atomic_write_violation` | 事务边界、失败回滚、旧快照保留 |
| `seed_or_session_isolation_failure` | seed reset、浏览器 session、跨场景数据污染 |

### 4.3 Scope guard 从文件数量限制升级为业务闭环限制

真实题目中，跨层修复是合理的。不能简单规定“一个失败只能改一个页面文件”。

GitHub 允许的 repair 闭环：

```text
失败页面组件
  + 直接使用的 handler/API
  + 对应的 server persistence model/store
  + 对应的 permission helper
  + 必要的共享 selector/type
```

Sheet 允许的 repair 闭环：

```text
失败 grid/editor 组件
  + cell/workbook store
  + formula engine 或 dependency selector
  + filter/validation/pivot derived-state helper
  + 必要的共享类型
```

仍然保护：

```text
requirements/**
官方 tests/**
acceptance runner
arc/main.py
arc/acceptance.py
arcbench_agent_runtime/**
```

除非任务明确要求修改这些路径，否则修改 protected path 必须记录 `scope_violation`、拒绝 candidate 并回滚。

文件数量只作为 warning 和异常信号，不作为唯一拒绝条件。应该优先判断：

1. 修改是否属于当前业务闭环。
2. 是否影响无关业务。
3. 是否引入新的失败。
4. 是否保留已有不变量。

### 4.4 Verification settlement 增加业务不变量

每轮 repair 除了比较测试集合，还应记录：

```text
business_invariants_checked:
business_invariants_failed:
cross_page_consistency:
refresh_consistency:
permission_consistency:
derived_state_consistency:
atomicity_consistency:
```

示例：

GitHub：

```text
repository.visibility == list_visibility == detail_visibility
effective_permission(session, repository) == backend_write_decision
pr.compare_commit == review.commit_scope
merge_failure => target_branch_head unchanged and pr.status unchanged
```

Sheet：

```text
formula_bar_formula == persisted_formula
grid_result == calculate(persisted_formula, current_cells)
refresh(reopen(workbook)) == last_successful_workbook_state
failed_paste => source_and_target_ranges_unchanged
pivot_refresh_failure => previous_pivot_result_preserved
```

如果只修复了页面显示，但这些不变量仍失败，不能把 candidate 标记为成功。

## 5. 两个真实题目的专用 repair 策略

### 5.1 GitHub repair context

每次 GitHub 失败尽量生成以下结构：

```json
{
  "product_domain": "github",
  "business_flow": "pull_request_merge",
  "seed_entities": ["repository", "base_branch", "compare_branch", "pull_request"],
  "session_context": "signed_in_account_and_role",
  "state_owner": ["repository_store", "branch_store", "pull_request_store", "review_store"],
  "read_path": ["pr_detail", "checks", "branch_overview"],
  "write_path": ["merge_handler"],
  "persistence_path": ["server_store", "reload", "direct_pr_url"],
  "permission_boundary": ["current_session", "repository_role", "organization_owner"],
  "workflow_transition": "Open -> Merged",
  "derived_state": ["merge_eligibility", "checks", "review_validity"],
  "invariants_to_preserve": [
    "merge_is_atomic",
    "review_is_for_current_compare_commit",
    "target_branch_head_changes_only_after_success"
  ]
}
```

优先修复顺序：

1. 先确认 session、对象归属和后端权限。
2. 再确认状态迁移和前置条件。
3. 再确认多个对象的原子写入。
4. 最后修复列表、详情、计数和可见控件。

### 5.2 Sheet repair context

每次 Sheet 失败尽量生成以下结构：

```json
{
  "product_domain": "sheet",
  "business_flow": "edit_formula_and_recalculate",
  "seed_entities": ["workbook", "worksheet", "source_cells", "formula_cells"],
  "state_owner": ["workbook_store", "worksheet_store", "cell_store"],
  "read_path": ["grid", "formula_bar", "filter_view", "pivot_view"],
  "write_path": ["cell_commit", "paste_handler", "row_column_operation"],
  "persistence_path": ["server_store", "direct_workbook_url", "refresh"],
  "permission_boundary": ["active_workbook", "active_worksheet", "selected_range"],
  "derived_state": ["formula_results", "dependency_graph", "validation", "pivot_result"],
  "workflow_transition": "source_cell_change -> dependent_recalculation",
  "invariants_to_preserve": [
    "formula_bar_keeps_original_formula",
    "grid_shows_current_result",
    "failed_operation_keeps_last_successful_state",
    "unrelated_cells_are_unchanged"
  ]
}
```

优先修复顺序：

1. 先确认 workbook/worksheet/cell 的权威状态来源。
2. 再确认单次操作的事务边界。
3. 再确认公式依赖或派生状态是否重新计算。
4. 再确认 refresh、reopen、切换 worksheet 后恢复一致。
5. 最后修复 ARIA 和视觉层 locator。

## 6. 新的执行顺序

### 阶段 A：v6.5 验证和稳定

先确认现有 v6.5 没有降低 v4.5 的已通过能力：

- `python -m py_compile`
- `git diff --check`
- acceptance 单元测试。
- 在模拟器机器上运行完整本地模拟。
- 检查 baseline、delta、rollback 和 no-progress 日志。

### 阶段 B：v6.6-real 领域感知上下文

修改范围建议：

```text
arc/repair_context.py
arc/acceptance.py
arc/main.py
arc/tests/test_repair_context.py
```

实现：

1. 从 requirement node 和失败标题推断产品领域。
2. 将失败映射到业务 flow 和 failure reason。
3. 将 repair prompt 扩展为 state owner、read/write path、persistence path。
4. 增加业务不变量清单。
5. 将 scope guard 改成业务闭环 scope。
6. 保留 v4.5 regression gate 和 best checkpoint。

### 阶段 C：领域专项验证

增加最小模拟，不依赖完整云端题目：

GitHub：

- 无权限用户的后端写入被拒绝。
- PR review 针对旧 commit 时不能满足当前保护规则。
- merge 失败时 PR 和目标分支都不改变。
- 列表和详情读取同一个持久化状态。

Sheet：

- 公式源值变化后依赖结果更新。
- 相对引用复制后调整，绝对引用不变。
- validation 失败时整批粘贴回滚。
- Pivot 刷新失败时保留旧结果。
- 刷新或直接 URL 重新打开后状态一致。

### 阶段 D：再考虑速度

只有在领域上下文稳定后，再引入：

- 只读的 spec、源码、日志并发分析。
- context budget 和安全 compaction。
- 对明确可重试的 runtime/LLM 错误做 bounded retry。

所有写入、服务启动、acceptance、checkpoint 和 rollback 继续串行。

## 7. 验收标准

### 代码级

```text
python -m py_compile arc/main.py arc/acceptance.py arc/repair_context.py
git diff --check
```

### RepairContext 单元测试

至少覆盖：

- GitHub 和 Sheet domain 推断。
- business flow 映射。
- `state_persistence_mismatch`。
- `permission_boundary_mismatch`。
- `workflow_transition_invalid`。
- `formula_dependency_stale`。
- `validation_bypass`。
- `accessibility_contract_mismatch`。
- 业务闭环 scope 判断。
- 新失败、缺失检查和回滚。

### 完整 acceptance

必须确认：

- 现有通过测试没有回归。
- 失败集合没有无意义漂移。
- 测试结果缺失不会被当成成功。
- infrastructure failure 不会触发普通业务 repair。
- 跨页面修复可以修改必要的 handler/store，但不会扩散到无关模块。
- repair prompt 中包含可执行的业务不变量。

## 8. 现实预期

真实题目共有：

```text
GitHub: 47 个原子需求 / 100 个场景
Sheet:  24 个原子需求 / 100 个场景
```

本地的 32 项测试不能代表云端的全部覆盖，也不能据此承诺云端全部通过。

这次修改方案最可能提升的不是“模型多写代码的数量”，而是：

- 减少只修 UI、不修持久化的假成功。
- 减少只修前端可见性、不修后端权限的假成功。
- 减少修复公式显示却留下旧派生结果的假成功。
- 减少修复当前页面后刷新或换页面又丢状态的回归。
- 减少跨层失败时反复修改错误文件。
- 让复杂失败能在下一轮得到更准确的 repair prompt。

不能承诺 `100/100` 场景或所有云端测试必然通过。更合理的目标是：在 v4.5/v6.5 的回归保护基础上，让 agent 更容易找到真正的状态、权限、事务和依赖根因。

## 9. 最终建议

方案需要修改，但修改方向是增量升级：

```text
v4.5 regression gate
  + v6.5 checkpoint / scope / no-progress
  + v6.6-real domain-aware repair context
  + business invariant verification
  + GitHub permission/workflow transaction checks
  + Sheet formula/derived-state consistency checks
```

当前不建议直接把 v6、v7、v8 的所有目标一次性合并，也不建议为了速度降低 acceptance 强度。先做 v6.6-real 的领域上下文和不变量，再根据真实模拟日志决定是否加入并发分析或 retry。
