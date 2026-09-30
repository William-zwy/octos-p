# ARC-Bench Run fb4903ecef12 额度中断分析报告

## 结论摘要

fb4903ecef12 应归类为“前半程已完成大量需求，后段因 provider 余额耗尽而无法继续实现和 repair 的部分完成快照”，不能按普通的“完整实现后测试失败”处理。

平台最终得到的 83/125 和 score=66.4 是有效的终态测试结果，但它只证明当前产物在 125 个 Playwright 场景中有 83 个通过。它不能证明剩余 42 个需求都已获得过实现机会，更不能把 42 个 timeout 全部归结为业务代码缺陷。

本报告只整理和解释附件证据，不修改生成产物、测试文件或业务代码。

## 1. Run 基本信息

| 项目 | 值 |
| --- | --- |
| Run | fb4903ecef12 |
| Task | arc-bench-web--ctrip |
| Submission | 362bc0d7b112 |
| Agent 包 | octos-arc-bundle_urgent-bookstack-contract-fix-r2-platform-unverified.zip |
| 模型 | deepseek-v4-flash |
| 推理档位 | low |
| 时间预算 | 187500s，来源于 stdout |
| 平台终态 | FAILED |
| 平台 score | 66.4 |
| 原子测试节点 | 125 |
| Playwright | 83 passed / 42 timedOut / 0 failed |
| Run 时长 | 36947s，约 10.3h |
| 开始 / 结束 | 2026-09-29 12:41:58 / 2026-09-29 23:06:24 |
| Provider 请求数 | 3699 |
| Provider token | prompt 141410684；completion 2114972；cache hit 131731200；reasoning 1446208；total 143525656 |
| Run 对象 token_count | 742567576 |
| 费用 | 346.572645 CNY |

原始附件目录：

    C:\Users\dayuruozhi\Downloads\闻悦源代码-首轮测试-arc-bench-web-ctrip\

## 2. API 额度耗尽的直接证据

### 2.1 时间线

| 时间 | 事件 | 结论 |
| --- | --- | --- |
| 22:47:58 | REQ-5.4.3.1 repair 结束，结构告警仍在 | 额度耗尽前已经存在未收敛问题 |
| 22:47:58 | REQ-5.4.3.2，node 89/125 开始 | 这是第一个受额度耗尽直接影响的节点 |
| 22:48:28 | REQ-5.4.3.2 返回 HTTP 402 insufficient_balance | 30s、tools=9、wrote=True、verified=False；不能视为完成 |
| 22:48:29～22:49:10 | REQ-5.5.x、REQ-5.6.x 连续 402 | 多数 tools=0、wrote=False、verified=False，基本没有实现动作 |
| 22:49:11～22:49:55 | REQ-6.x、REQ-7.x 连续 402 | 下游 profile、flight status 等节点没有实现机会 |
| 22:50:00～22:51:36 | driver 对 billing error 进行 2/3、3/3 重试，REQ-7.2.3.2 最终耗时 101s | 重试延长了退出窗口，但没有产生代码进展 |
| 22:51:53 | REQ-10.2.1 402，node 125/125 | 125 个节点的生成遍历结束 |
| 22:54:44 | full suite round 0：83/125 | 42 个失败已形成 |
| 22:54:49 | full-suite repair 1/2 直接因同一 402 失败 | 没有修复机会 |
| 22:57:36 | full suite round 1 仍为 83/125 | 结果未改善 |
| 22:57:39 | 记录 same failures，停止 repairs | 额度门控使 repair 无法启动 |

stdout 中第 3849 行是第一个 402 节点；第 3853～4011 行是连续 quota failure；第 4013～4023 行记录 full suite 和 repair 结果。

### 2.2 三条轨迹的错误计数

octos-events.jsonl 的结构化统计：

    turn/started       159
    turn/completed     109
    turn/error         43
    tool/started       3853
    tool/completed     3853
    message/reasoning  2500
    message/delta      2308

43 个 turn/error 中：

- 1 个是 provider/gateway proxy_error，发生在 REQ-2.5.1；
- 42 个是 provider quota exhausted / HTTP 402；
- 这 42 个 402 包含节点失败和后续 driver/full-suite repair 重试，不能简单按 42 个需求节点计算。

这组证据说明：任务不是被 Playwright 测试突然杀死，也不是因为生成进程自身 OOM 而结束。直接中断原因是 provider 余额耗尽，且平台没有在第一次 billing error 后立即停止请求。

## 3. 额度耗尽前，任务已经暴露的风险

额度耗尽解释了后段大面积缺口，但不是全部风险的来源。

### 3.1 长 turn 超时

stdout 在 402 之前记录了 7 个 octos turn timeout：

- REQ-2.2：900s，tools=30，wrote=True，verified=True；
- REQ-2.4.1：900s，tools=28，wrote=True，verified=False；
- REQ-2.5.5：900s，tools=18，wrote=True，verified=False；
- REQ-2.6.2.1：900s，tools=45，wrote=True，verified=True；
- REQ-3.5.4.1：901s，tools=91，wrote=True，verified=True；
- REQ-4.2.5.2：901s，tools=53，wrote=True，verified=True；
- REQ-5.3.3.2：901s，tools=40，wrote=True，verified=True。

其中部分节点在 acceptance round 0 或 round 1 仍然通过，说明“turn timeout”不等于代码一定缺失；但 verified=False 的节点必须单独复现，不能依赖实现日志中的声明。

### 3.2 Provider proxy error

REQ-2.5.1 在 22:13:52 左右经历约 365s 的 HTTP 400 proxy_error：

    Post https://api.taotoken.net/v1/chat/completions: unexpected EOF

它不是余额错误，但会使节点实现状态不可靠。最终 REQ-2.5.1 仍在测试阶段 timeout，说明该节点没有在后续修复中稳定收敛。

### 3.3 Repair budget 和验证闭环问题

stdout 多次出现以下流程信号：

- REQ-5.3.3.1 repair 1/5、2/5 命中 request budget 10；
- REQ-5.3.3.2 repair 1/5、2/5 命中 request budget 10；
- REQ-5.4.3.1 repair 1/5、2/5 命中 request budget 10；
- harness 提示曾经在未运行 build、启动和 request 命令前就声明完成；
- 同一组结构告警在多个 repair 轮重复出现，没有形成收敛证据。

这些问题发生在额度归零前，说明 agent 的主要瓶颈不只是 token 总量，还包括单节点 turn 过长、工具预算被重复探索消耗、验证动作排在最后以及失败后没有及时缩小范围。

### 3.4 结构性告警

在 quota failure 之前和 full suite 前，结构扫描反复提示以下按钮没有显式 handler：

- booking.html：保险套餐、购买贵宾休息室；
- order-detail.html：取消、确定；
- orders.html：搜索、取消、确定；
- payment.html：支付宝。

这类告警不能单独证明对应 Playwright 场景必然失败，但它们是明确的未闭环线索，尤其与订单、支付、个人中心下游功能相关。

### 3.5 资源与进程

stdout 的 postflight 记录：

- cgroup memory.max 为 2 GiB；
- memory.peak 约 1.479 GiB；
- oom=0、oom_kill=0；
- postflight 清理 757 个 stray process。

因此没有 OOM 主因证据。757 个残留进程则是严重的环境卫生和时序风险，可能增加后续 smoke test、端口复用和浏览器流程的不稳定性，但不能把它直接等同于本次 402 原因。

## 4. 三条推理轨迹分别说明什么

### 4.1 octos-events：模型调用和工具生命周期

octos-events 是确认 provider 层状态的主证据：

- 159 个 turn/started 中，109 个正常完成，43 个进入 error；
- 1 个 proxy_error 发生在额度耗尽前；
- 42 个 402 从 REQ-5.4.3.2 开始持续出现，并延伸到 full-suite repair；
- 3853 个 tool/started 与 3853 个 tool/completed 相等，说明没有出现大量未配对的工具生命周期事件；
- 但 turn error 仍然可以发生在已写文件或 partial output 之后，不能用 tool completed 数量推断需求完成。

重要行索引：

- 约第 6819 行：REQ-2.5.1 proxy_error；
- 约第 43896 行开始：连续 turn/error 402；
- 约第 44151 行：后段 402 仍在继续。

### 4.2 runner-events：需求树状态，不是最终测试真相

runner-events.jsonl 的事件类型计数：

- requirement_state：1134；
- runner_state：2；
- signal：1385。

ROOT 最终记录：

- design：125 个 atomic children designed；
- implement：87/125 atomic children implemented；
- test：children not verified，列出 42 个失败节点；
- runner：completed。

这里的“runner completed”只表示 runner 生命周期结束；“87/125 implemented”也不是 Playwright 通过率。最终 evaluator 的结果是 83/125 passed，二者差异正是“实现节点状态”和“外部测试行为”不能混用的证据。

runner-events 还显示：

- REQ-5.4.3.2 在 22:48:28 implement failed，随后在 22:57:41 test failed；
- REQ-5.5.1.1 同样从 quota-gated implement failed 进入 test failed；
- ROOT 在 22:57:41 结束，记录 87/125 implemented，但 test failed。

### 4.3 stdout.log：执行节奏和因果顺序

stdout 是最适合还原工作节奏的轨迹，包含：

- 125 个 atomic nodes 的顺序；
- 使用的测试路径和 125 个 spec 映射；
- 内部 acceptance 使用 workers=2，容器 memory limit 为 2048 MiB；
- 每个节点的耗时、工具数、wrote、verified；
- 7 个 900s turn timeout、1 个 proxy error；
- 402 的首次出现、连续节点失败和 billing retry；
- full-suite round 0/1、repair 失败和停止原因；
- startup rehearsal、内存峰值和进程清理。

stdout 的执行顺序支持以下因果链：

    长 turn / proxy / 结构告警
        -> REQ-5.4.3.2 首次 402
        -> 下游 37 个节点无实现机会
        -> full-suite repair 再次 402
        -> 83/125 测试结果保持不变

## 5. 最终测试结果应如何拆分

最终 Playwright report 的统计是：

    83 passed
    42 timedOut
    0 failed

全部 42 个失败都是 10s 测试 timeout，没有独立 assertion failure。因此下述分类是“证据强度分类”，不是对所有业务根因的最终确认。

### 5.1 直接受额度耗尽门控的 37 个失败

以下节点在 quota 归零后没有实现机会，均出现 tools=0 或写入未验证：

- REQ-5.4.3.2；
- REQ-5.5.1.1、REQ-5.5.1.2、REQ-5.5.2.1、REQ-5.5.3.1、REQ-5.5.3.2；
- REQ-5.6.1.1、REQ-5.6.2.1、REQ-5.6.2.2、REQ-5.6.3.1、REQ-5.6.3.2；
- REQ-6.1.1、REQ-6.2.1、REQ-6.3.1、REQ-6.4.1、REQ-6.5.1、REQ-6.6.1；
- REQ-7.1、REQ-7.2.1.1、REQ-7.2.2.1、REQ-7.2.2.2、REQ-7.2.3.1、REQ-7.2.3.2、REQ-7.3.1.1、REQ-7.3.2.1；
- REQ-8.1.1.1、REQ-8.2.1、REQ-8.2.2；
- REQ-9.1、REQ-9.2.1.1、REQ-9.2.1.2、REQ-9.2.2.1、REQ-9.3.1.1、REQ-9.3.2.1、REQ-9.3.3.1；
- REQ-10.1.1、REQ-10.2.1。

这 37 个不应写成“已实现但测试失败”，而应标记为 quota-gated / implementation opportunity missing。

### 5.2 额度耗尽前已暴露的 5 个失败

以下 5 个在 402 之前已经出现在内部 acceptance 失败或 repair 未收敛中：

| 节点 | 测试层线索 | 证据强度 |
| --- | --- | --- |
| REQ-2.5.1 | 找不到可见的“倒计时”按钮；节点还经历 proxy_error | 高，需独立复现认证验证码流程 |
| REQ-2.6.4.1 | 找不到可见的“注册成功”按钮 | 高，REQ repair 后仍为 12/13 |
| REQ-5.3.3.1 | 删除旅客记录后找不到“成功”反馈 | 高，repair 1/5、2/5 都命中 budget |
| REQ-5.3.3.2 | 打开个人中心入口的 click 超时 | 中高，节点自身曾经历 901s implement timeout |
| REQ-5.4.3.1 | 删除单个地址后找不到可见成功反馈 | 高，repair 两轮后仍无 improvement |

这些线索足以说明 quota 不是全部根因，但仍不等于完成源码级根因闭环。后续应在同一模板上以单节点复现确认是路由、可见性、认证状态、持久化反馈还是 fixture 依赖问题。

## 6. 中间态附件如何解释

这组文件不能简单把 midrun JSON 当作最终结果：

- midrun JSON SHA-256：6D1601FC88345ED101376C549FFD44B6EA764AA6B7AAF7A90E2B9F726E9FD2BC；
- midrun JSON 状态为 RUNNING，score、passed_count、failed_count、feature count 均为空或 0；
- final run JSON SHA-256：5D1C7F01FF92947BF8709A5E02947C99DDF4E0B60BDCC915198CFAE7A8BE47C3；
- final run JSON 才包含 FAILED、83/125、score=66.4 和最终测试列表；
- midrun logs SHA-256 与 final logs SHA-256 不同；
- midrun traceability 有 82 个 test records，其中 79 passed、3 failed，interfaces=2；
- design-midrun 只有 6 个设计键：REQ-0、REQ-1.1、REQ-2.1、REQ-2.3.1、REQ-2.3.2、REQ-2.3.3；
- midrun logs 尾部已经到 22:57:43，包含 generation postflight，但 midrun run object 仍显示 RUNNING。

因此，中间态的正确用途是：

1. 证明额度耗尽前已经存在部分 acceptance 结果和设计快照；
2. 观察生成阶段的执行节奏、工具预算和错误；
3. 不能用 midrun JSON 的 0/0 推断“没有任何实现”；
4. 不能用 midrun traceability 的 79/82 代替最终 evaluator 的 83/125；
5. 不能把 midrun logs 中接近生成结束的内容误标为平台终态。

## 7. 优化建议

按优先级：

1. **第一次 402 即进入硬停止状态**：billing error 不应按普通 transient error 继续 2/3、3/3 重试；应保存 checkpoint、标记 quota-gated，并跳过剩余节点和 full-suite repair。
2. **预留 repair 配额**：正常实现、单节点 repair、full-suite repair 使用隔离预算，至少为最后一轮保留可用余额。
3. **拆短 turn**：将 profile、flight、order、airport 等长链路拆成页面骨架、路由/API、最小 smoke test 三段，避免 40～91 个工具调用后才到达 timeout。
4. **验证设为完成门槛**：没有 build、启动、健康检查和最小 request 的节点不能标记 completed；避免 harness 已指出的“先声明完成后补验证”。
5. **结构告警阻断下游**：重复出现无 handler 的支付、订单按钮时，先修复基础交互，再继续依赖这些入口的下游节点。
6. **缩小 repair 范围**：request budget=10 时优先读取失败上下文和现有页面，只做一个可验证改动，不重复全仓探索。
7. **分离实现状态与测试状态**：runner 的 implemented、内部 acceptance、最终 Playwright evaluator 必须分别记录，报告不能把它们压成一个通过率。
8. **统一并发口径**：内部 acceptance 是 workers=2，最终 evaluator 是 workers=1；同一产物应在两个口径分别跑 smoke，排除时序差异。
9. **进程清理前置**：757 个 stray processes 说明每个节点和 smoke test 后都应立即回收端口、浏览器和 npm 子进程，不能只依赖 postflight。

## 8. 给后续会话的交接标签

~~~text
run_id: fb4903ecef12
generation_status: partially_completed_then_quota_exhausted
interruption_reason: provider_balance_exhausted_at_REQ-5.4.3.2
platform_result: valid_final_partial_artifact
final_test_result: 83_passed_42_timedOut_0_failed
complete_implementation_claim: false
quota_gated_final_failures: 37
pre_quota_failure_candidates: 5
provider_turn_errors: 43
provider_error_breakdown: 1_proxy_error_42_quota_402
runner_root_implementation: 87_of_125
midrun_json_is_final: false
next_action:
  - restore provider quota or switch to a verified provider
  - reproduce the five pre-quota failures independently
  - keep the 37 quota-gated nodes separate from confirmed code defects
  - run evaluator again only after repair budget is reserved
~~~

最低限度的后续闭环是：先恢复有效 provider 或配额，保留 83/125 作为当前基线；再独立复现 REQ-2.5.1、REQ-2.6.4.1、REQ-5.3.3.1、REQ-5.3.3.2、REQ-5.4.3.1；最后再处理 37 个没有实现机会的 quota-gated 节点。
