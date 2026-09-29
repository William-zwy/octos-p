# 阶段 3职责分析：8ea6503bfa95

## 结论

本 Run 的最终失败不是单一的“测试执行太慢”。责任链分为三层：

1. **测试身份路由先失真（已确认）**：Run 任务是 `arc-bench-lite--keep`，但 `stdout.log` 显示 agent 在 `/workspace/tests` 找不到 spec 后，选择了 `/workspace/submission/public-tests/arc-bench-web--keep`。中间态的 `29/32` 是另一任务身份的自验结果，不能作为本 Run 的有效通过预测。
2. **生成/修复执行再被 turn 上限切断（已确认）**：5 个实现 turn 命中 900 秒上限；`REQ-2.7.1`、`REQ-2.7.4` 的修复又在 584/599 秒中断，另有一次 `REQ-2.6.2` 修复遭遇代理 `unexpected EOF`。request budget guard 多次触发，导致 late-stage repair 没有足够窗口收敛。
3. **最终官方测试暴露真实 UI/状态契约缺口（症状已确认，代码根因待阶段 4）**：14 个测试全部是 10 秒 timeout，等待的不是慢响应，而是不存在的 action control、label/pin 状态或 Settings/Reminders 控件。

因此，当前最重要的优化不是简单放宽 Playwright 10 秒阈值，而是先让内部验收严格绑定 `arc-bench-lite--keep`，再在同一套 spec 上修复 UI 语义和状态持久化。

## 三条推理轨迹

| 轨迹 | 规模与量化结果 | 责任证据 |
| --- | --- | --- |
| `octos-events.jsonl` | 15,198 行；56 started、48 completed、1 error、7 个未闭合 turn；1,289 tool started / 1,288 completed；9,511 progress；751 reasoning delta、718 message delta | 900 秒 turn timeout 的未闭合生命周期与一次 `REQ-2.6.2` proxy error 可直接核对 |
| `runner-events.jsonl` | 1,324 行；257 requirement state、345 signal；最终 runner `completed`，但 `REQ-2.6.1/2.7.4/2.7.5` 未验证 | runner 把“implemented/verified”与最终平台测试分开记录，不能用 runner completed 推导通过 |
| `stdout.log` | 446,723 bytes；provider 1,180 requests / 34,526,353 provider total tokens；5 次 900 秒 cap；13 次 request-budget-10 guard；内部 suite 明确为 `arc-bench-web--keep` | 直接揭示测试套件身份错配、repair 预算耗尽和 full-suite repair 未收敛 |

`stdout.log` 还记录了 6 次去重后的 `ConnectionResetError`、一次 `proxy_error`，以及 postflight 回收 402 个 stray processes。它们是运行卫生和网关稳定性的风险信号，但没有证据证明它们单独造成最终 14 个 Playwright timeout。

## 最终失败面

最终报告是 `18/32`，14 个 `timedOut`、0 个断言状态为 `failed`。失败可按观察到的契约症状分组：

- `REQ-2.3.1`、`REQ-2.5.1`–`REQ-2.5.4`、`REQ-2.6.1`：匹配 note article 内的 Trash/Archive/Change color 操作或结果状态不可见。
- `REQ-2.7.1`、`REQ-2.7.2`、`REQ-2.7.4`：Note editor 的 `Work` checkbox 或创建后的 `Reminders` 状态不可见。
- `REQ-2.8.1`、`REQ-2.8.3`：pin 结果状态不可见。
- `REQ-3.1`、`REQ-4.1`、`REQ-4.2`：初始 Reminders filter 或 Settings button 不可见。

这些是 Playwright 报告确认的最终症状，不在阶段 3把它们擅自升级为具体源码 bug。阶段 4应在最终 template 上逐项确认：是 DOM 语义缺失、数据 seed/状态持久化错误、错误 suite 产生的修复偏移，还是交互层遮挡/加载竞态。

## 超时责任链

`node -> self-acceptance -> repair -> final test` 的链条如下：

- 早期节点按依赖串行执行，复杂节点在大量读取、构建、自测和修复中逼近单 turn 900 秒上限；5 个实现节点明确以 `octos turn timed out` 结束。
- `REQ-2.6.2` 修复在 359 秒发生上游 `proxy_error`，后续 tool-mode 修复虽把内部结果从 7/11 推到 9/11，但仍保留失败；日志还显示重复文件路径错误和“previous turn claimed completion without running build” guard。
- `REQ-2.7.1`、`REQ-2.7.4` 的修复分别在 584/599 秒中止；`REQ-2.7.5` 修复虽写盘但剩余预算只有 154 秒，多个节点进入 request budget guard。
- full-suite round 0 与 round 1 都是 `29/32`，失败节点固定为 `REQ-2.6.1`、`REQ-2.7.4`、`REQ-2.7.5`，随后停止修复。这一结论只对错误的 `arc-bench-web--keep` 内部 suite 成立。
- 官方最终 suite 运行到应用并给出 14 个 locator/state timeout；所以“启动崩溃”不是本 Run 的失败机制，“全局预算耗尽”也不是。

## 已排除与待证

- **已排除启动崩溃**：main.py、前端 build、后端启动和 generated application reachability 均有日志证据；runner 完成了 final Playwright parse。
- **未见 OOM/cgroup kill**：日志有 2 GiB acceptance container memory 配置和 postflight process cleanup，但没有 OOM、SIGKILL 或 cgroup kill 证据；不能把 402 stray processes 当成已证实根因。
- **未见全局 time budget 耗尽**：agent 自报 48,000 秒预算，Run 实际 20,611 秒结束；真正瓶颈是单 turn cap、request guard、suite mismatch 和修复未收敛。
- **代理故障是局部扰动**：一次 `REQ-2.6.2` repair 的 upstream EOF 已确认，但不足以解释 14 个最终失败。
- **平台上传身份仍不闭合**：本地 Agent ZIP SHA 已记录，平台没有 build/task snapshot/upload checksum binding；阶段 4不得宣称严格构建归因或 A/B。

## 优化建议

1. **P0：suite identity fail-closed**。把 `competition_id--task_id` 写入内部验收 contract；`arc-bench-lite--keep` 只能选择同 task suite。找不到 `/workspace/tests` spec 时应直接报告“无法验收”，不能自动选 `arc-bench-web--keep`。
2. **P1：自验参数与官方一致**。使用官方 suite、`workers=1` 和 10 秒测试 timeout；先做单节点定点 smoke，再跑累计 suite，避免用另一 suite 的绿灯判断修复收敛。
3. **P1：缩小单 turn**。每个节点固定“读必要文件 -> 单批 patch -> build/定点 test -> 写 design”，减少重复 read、重复错误命令和全量 rewrite；给 repair 预留硬预算，预算不足时停止新节点并保留明确未验证状态。
4. **P1：修复基于最终 locator**。针对 note action、label checkbox、pin/default-label、Reminders/Settings 控件逐项做 DOM contract check；不要只依据自验文本声称功能完成。
5. **P2：运行卫生**。每轮 smoke 后确认 server/browser 子进程归零，记录真实 cgroup memory；402 个 postflight stray processes 说明清理路径需要单独审计，但当前仅列为风险。

## 阶段 4输入边界

阶段 4只读取本 Run 的最终 template、snapshots、Playwright report、run/logs 和三条轨迹；不得把其他 Keep/BookStack Run 的诊断结论合并进本卡。阶段 4应输出每个失败 cluster 的 `confirmed / strong_candidate / unknown`，并明确区分：

- 测试 suite 路由错误（平台/agent harness责任）；
- 最终模板的 DOM/状态实现缺口（生成应用责任，需源码核验）；
- 单 turn/proxy/cleanup 运行时问题（生成过程责任）。

阶段 3不触发 Stage 5、不修改 Agent 或官方测试，也不启动新平台 Run。
