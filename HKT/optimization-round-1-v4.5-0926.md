# Octos Agent 优化记录：Round 1 v4.5

日期：2026-09-26

## 1. 本轮目标

本轮执行此前方案中的 v5：

- 借鉴 Codex 的 baseline regression gate。
- 保留 v4 已有的 full-suite best checkpoint。
- 区分代码行为失败和基础设施失败。
- 防止 repair 后出现“通过数不变但失败测试换了一批”的情况。

本轮命名为 **v4.5**，因为这是在 v4 acceptance rollback 基础上的增量 runtime 优化，不是完整架构重写。

## 2. 修改文件

### `arc/acceptance.py`

新增：

```python
test_identity(outcome)
check_results(summary)
failed_test_keys(summary)
failure_kind(summary)
```

功能：

- 将测试稳定标识为 `(spec_file, test_title)`。
- 生成每轮测试的通过/失败映射。
- 生成失败测试集合。
- 将运行结果分类为：
  - `behavior`
  - `timeout`
  - `startup`
  - `infrastructure`

### `arc/main.py`

在 `Flow.final_acceptance()` 中新增：

1. 首轮 full-suite 结果作为 baseline。
2. 后续 repair 计算：

```text
new_failures
fixed_failures
known_failures
missing_checks
```

3. 出现基础设施错误时：
   - 不建立错误 baseline。
   - 不继续消耗 repair round。
   - 保留最佳状态。

4. full-suite 没有产生测试结果时：
   - 不把 `0/0` 当作成功。
   - 恢复最佳状态并停止。

5. repair 引入新的失败测试或缺失原有测试时：
   - 拒绝 candidate。
   - 恢复 best checkpoint。

6. 原有策略继续保留：

- `best_passed`
- `best_sha`
- `best_failures`
- 严格通过数改进
- 失败集合漂移检测
- traceability verdict 同步

### `arc/tests/test_acceptance.py`

新增单元测试覆盖：

- 稳定测试 identity。
- 失败集合生成。
- timeout 分类。
- infrastructure error 分类。

## 3. Full-suite 决策逻辑

首轮运行：

```text
baseline_checks = {
    (spec_file, test_title): passed
}
```

后续运行：

```text
new_failures   = candidate_failed - baseline_failed
fixed_failures = baseline_failed - candidate_failed
known_failures = candidate_failed ∩ baseline_failed
missing_checks = baseline_checks - candidate_checks
```

接受条件：

- 所有测试通过，立即接受。
- 没有新增失败，并且通过数严格增加，更新 best state。
- 通过数相同但失败集合变化，拒绝。
- 出现新增失败，拒绝。
- 出现缺失测试结果，拒绝。
- build/start/runner 错误，视为基础设施失败，不进入普通 repair。

预期日志：

```text
[acceptance] full suite baseline established: 31/32, kind=behavior
[acceptance] full suite delta: fixed=1 new=0 known=0 missing=0 kind=behavior
[acceptance] full suite: new failures introduced; restoring best state
```

## 4. 验证结果

已通过：

- `python -m py_compile arc/main.py arc/acceptance.py arc/tests/test_acceptance.py`
- `git diff --check`
- v4.5 新增相关 acceptance 单元测试：
  - `ReportTests`
  - `FailureGroupingTests`
  - `HelperLocationTests`
  - 共 `10` 项通过

完整 acceptance 测试未能在当前 Windows 沙箱中全部完成，原因是：

1. 测试默认使用 `C:\Users\16062\AppData\Local\Temp` 创建临时目录，当前环境返回 `WinError 5`。
2. 一个既有的 `isolated_install_env` 测试受当前 Windows 环境变量行为影响。

这些失败发生在临时目录和环境隔离测试阶段，不涉及本轮新增的 baseline、失败集合或 full-suite 决策逻辑。

## 5. Bundle

本轮生成：

`D:\items\Hackathon\octos-p\octos-arc-bundle_v4_5.zip`

该 bundle 保留 v4 的目录结构，并包含更新后的：

- `main.py`
- `acceptance.py`
- `requirements.txt`
- `public-tests`
- `hooks`
- `arcbench_agent_runtime`

## 6. 尚未完成的验证

以下验证需要使用完整本地模拟环境执行，当前没有在本轮自动启动：

- 使用 `hackathon-local-simulation/runs/octos-keep-0926-v2` 重跑完整任务。
- 确认原有 `31/32` 基线不下降。
- 确认 repair 日志出现 baseline/delta 统计。
- 人为制造失败漂移，确认 candidate 会恢复 best state。
- 确认 build/start/OOM 情况不会触发无意义 repair。

## 7. 下一步建议

先运行 v4.5 bundle 的完整本地模拟。

如果结果不低于 v4，再执行下一阶段 v6：

```text
affected-files scope guard
```

限制 repair 只能修改应用代码，避免修改测试、需求文件、runner 或其他不相关文件。
## Packaging Verification Addendum

The v4.5 bundle was produced from the file list in `arc/pack.sh`.

Bundle: `D:\items\Hackathon\octos-p\octos-arc-bundle_v4_5.zip`

SHA256: `DA00EAE2184258C6C153ED1005072175008579AE950E4C476B7880313562998D`

The local simulator is not installed on this Windows host, so the full simulation remains pending on the simulator machine. The ZIP structure was verified locally. `sh arc/pack.sh` could not be invoked directly because this host has no usable `sh` command; an equivalent PowerShell packaging step used the same file list and exclusions.
