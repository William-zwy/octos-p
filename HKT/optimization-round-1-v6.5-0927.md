# Octos Agent v6.5 修复记录

日期：2026-09-27

## 1. 本轮目标

根据 `optimization-plan-reference-four-repos-0926.md`，针对 v4.5 的回归问题增强 repair 流程，重点覆盖：

- 多个测试共享同一个 UI 根因时，给模型完整的 Playwright 证据；
- repair 前后稳定比较测试集合，避免测试消失被误认为通过；
- 记录真实修改文件，避免模型在错误层面反复修复；
- 保留 best checkpoint 和 full-suite regression gate；
- 不让基础设施或启动问题污染普通行为修复判断。

v4.5 本地结果为 `25/32`，其中 7 项集中表现为 `locator.click` 的 `intercepts pointer events`。本轮不承诺直接达到 `32/32`，最终成功率必须在模拟器机器上验证。

## 2. 代码改动

### 2.1 新增 `arc/repair_context.py`

新增 `RepairContext`，统一承载：

- 当前失败集合；
- best checkpoint 失败集合；
- `fixed / new / known / missing`；
- failure kind 和 failure reason；
- 本轮真实 changed files；
- likely files；
- Playwright failure evidence；
- no-progress 次数。

Repair prompt 会收到结构化 JSON，并明确 acceptance 结果优先于模型自己的完成声明。

### 2.2 增强 `arc/acceptance.py`

新增或增强：

- 稳定测试 identity：`file + normalized title`；
- `check_results`、`failed_test_keys`；
- `failure_reason` 分类：
  - `pointer_interception`
  - `startup`
  - `timeout`
  - `assertion_mismatch`
  - `locator_mismatch`
  - `behavior`
  - `infrastructure`
- `failure_signature` 和 `group_failures`；
- `failure_evidence`：提取 locator、resolved element、attempting action、interceptor element 等 Playwright call-log 信息。

其中 `intercepts pointer events` 不再只被当作普通 timeout，而是聚类为共享 UI 命中问题。

### 2.3 增强 `arc/main.py`

#### Per-node acceptance

- 每轮记录 app digest 和 changed files；
- 比较当前失败集合与 best checkpoint；
- 把失败根因、测试 identity、Playwright evidence 注入 repair prompt；
- 在上一轮测试集合中存在、当前报告中消失时标记 `missing_checks`；
- 相同失败集合、签名和改动模式重复时停止无效 repair；
- pointer/locator 失败却只修改 backend 时恢复 best state；
- startup 失败却只修改 frontend 时恢复 best state；
- 保留原有的 passed 数、regression、stall 和 best checkpoint 逻辑。

#### Full-suite acceptance

- 保留 baseline/candidate 比较；
- 出现 `new_failures` 或 `missing_checks` 时拒绝 candidate；
- 失败集合漂移但通过数不增加时拒绝 candidate；
- full-suite 只接受严格更好的 best state；
- full-suite no-progress 时恢复 best state；
- 基础设施错误和空报告不再建立错误 baseline。

### 2.4 更新 `arc/pack.sh`

将新增的 `repair_context.py` 加入 bundle。否则 `main.py` 在模拟器环境导入时会缺少依赖。

## 3. 验证结果

通过：

```text
python -m py_compile arc/main.py arc/acceptance.py arc/repair_context.py arc/tests/test_acceptance.py
git diff --check
ReportTests: 13/13 passed
```

完整 unittest：

```text
Ran 91 tests
FAILED (failures=1, errors=13)
```

这些失败不是本轮新增逻辑导致：

- 多个旧测试在当前 Windows 环境下创建 `tempfile.TemporaryDirectory` 子目录时收到 `WinError 5`；
- 一个旧测试要求 POSIX `/private/x` 路径前缀，在 Windows 下不成立；
- 新增的 failure classification、pointer evidence、missing checks、changed files 测试均通过。

当前没有在本机运行完整模拟器，因为模拟器不在这台机器上。

## 4. 预期收益

本轮最直接的收益是降低 v4.5 类型回归：

1. 7 个相同 UI 命中失败会被聚类并共享 evidence，而不是拆成 7 个孤立业务问题；
2. 模型能看到具体被拦截元素，例如 `note-card`、`More options` 或目标 button；
3. 修复只改错层级时会被 scope guard 拒绝；
4. 测试结果缺失、失败集合漂移或 full-suite 变差时不会覆盖 best state；
5. 相同失败反复出现时会尽早停止，把时间留给不同修复策略；
6. 更适合云端复杂题，但不能仅凭静态检查保证 `32/32`。

## 5. 模拟器机器上的执行

打包：

```sh
cd D:/items/Hackathon/octos-p
sh arc/pack.sh
```

然后使用生成的：

```text
D:/items/Hackathon/octos-p/octos-arc-bundle.zip
```

在模拟器环境执行完整测试，并重点比较：

- v2：`31/32`
- v4.5：`25/32`
- v6.5：是否恢复到至少 v2 基线，并观察云端两类复杂题的修复稳定性。

