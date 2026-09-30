# ARC-Bench Run e5cb3ca21874 分析报告

## 结论摘要

e5cb3ca21874 应归类为“生成阶段部分完成、随后因 provider 余额耗尽而无法完成 repair 的 FAILED 快照”，而不是完整需求实现后的普通 FAILED。

平台最终得到的 71/86 和 score=82.6 是有效的测试快照，但它运行在 full-suite repair 未完成的产物上。不能据此宣布 86 个需求都已经完整实现，也不能把 15 个 timeout 全部视为已经独立确认的业务代码缺陷。

本报告只整理证据，没有修改原始附件或业务代码。

## 1. Run 基本信息

| 项目 | 值 |
| --- | --- |
| Run | e5cb3ca21874 |
| Task | arc-bench-web--prestashop |
| Submission | 362bc0d7b112 |
| 模型 | deepseek-v4-flash |
| 平台终态 | FAILED |
| 平台 score | 82.6 |
| 原子需求节点 | 86 |
| 平台实现口径 | 71/86，82.6% |
| Playwright | 71 passed / 15 timedOut / 0 failed |
| Run 时长 | 36577s，约 10.2h |
| Provider 请求数 | 3394 |
| Provider token | prompt 128,235,387；completion 2,267,107；cache hit 118,573,312；reasoning 1,638,917；total 130,502,494 |
| Run 对象 token_count | 742,567,576 |
| 费用 | 346.572645 CNY |

原始目录：

    C:\Users\dayuruozhi\Downloads\闻悦源代码-首轮测试-arc-bench-web-prestashop\

## 2. 直接中断原因：API 额度耗尽

额度耗尽发生在生成阶段最后一组需求附近：

| 时间 | 事件 | 影响 |
| --- | --- | --- |
| 22:48:26 | REQ-8.6.1 返回 HTTP 402 insufficient_balance | 该节点耗时 236s，虽然有写入标记，但没有可靠完成后续收敛 |
| 22:48:27～22:48:35 | REQ-8.6.2 至 REQ-8.6.7、REQ-8.7 连续收到 402 | 多数为 tools=0、wrote=False、verified=False，基本没有实现动作 |
| 22:49:57 | full suite round 0 记录 71/86 | 15 个失败节点已存在 |
| 22:50:00 | full-suite repair 1/2 因同一 402 失败 | 没有机会修复 15 个失败节点 |
| 22:51:28 | full suite round 1 仍为 71/86 | 与上一轮相同，repair 停止 |

octos-events 的 11 个 turn/error 中：

- 2 个是 provider/gateway proxy_error；
- 9 个是 provider quota exhausted / HTTP 402。

因此，余额耗尽是 full-suite repair 未能启动和任务最终未完成的直接原因。它不是 Playwright 测试把生成进程杀掉，也不是单纯的测试超时。

主要证据：

- stdout.log 约第 3902～3939 行；
- octos-events.jsonl 约第 5881、6261、40963～41011 行；
- runner-events.jsonl 约第 2653～2662 行。

## 3. 额度耗尽前的生成质量和收敛风险

### 3.1 公开测试确实已加载

日志显示：

- candidate /workspace/tests 没有 spec；
- 随后成功加载 /workspace/submission/public-tests/arc-bench-web--prestashop 下的 86 个 spec；
- 公开测试与 86 个 atomic node 一一映射；
- 内部 acceptance 使用 workers=2，容器内存限制 2048 MiB。

因此本 Run 不能归类为“没有测试输入”。摘要中对 bundled 相关字段标记为存疑，但启动日志明确指向 public-tests 路径；目前没有足够证据证明发生了 ZIP 内 bundled tests 回退，应保留该字段为未完全核实而不是直接判定回退。

### 3.2 900 秒 turn 和 repair 超时

额度归零以前已经出现以下超时：

- REQ-1.3.1 implement：900s；
- REQ-1.3.1 rewrite repair 1：599s；
- REQ-3.4 implement：900s；
- REQ-6.2 implement：901s；
- REQ-6.5 implement：901s；
- REQ-6.7 implement：901s。

REQ-1.3.1 后来在 acceptance round 1 达到 4/4，说明 timeout 不一定等于代码完全缺失；但 REQ-3.4、REQ-6.5、REQ-6.7 的失败状态没有在额度耗尽前稳定收敛。

### 3.3 两次 proxy 错误

- REQ-2.3：约 389s 后出现 HTTP 400，连接被 ClientConn.Close；
- REQ-3.1：约 487s 后出现 HTTP 400 unexpected EOF。

这两次都记录了 wrote=True、verified=True，但它们仍是 provider 层异常，不能当作普通业务实现成功。应在独立复现中检查对应文件和行为。

### 3.4 Guard 和结构性告警反复出现

stdout 记录了多类流程问题：

- 反复触发“同一错误 3～4 次”的 guard；
- 多次触发 repair request budget=10；
- 修改了受保护的 public-tests 配置、测试结果文件以及 frontend/src/assets/app.js；
- frontend/src/index.html 多次被提示可见 input 缺少 id/label wiring；
- REQ-1.4 被提示缺少 Search results heading 和 product link；
- REQ-6.5 被提示缺少 Payment heading 和 Place order button；
- 多个 repair turn 声称完成，却没有执行 build/start/request 验证。

这些信号说明失败并非只由余额归零造成。流程在额度耗尽前已经有明显的重复探索、受保护文件触碰、验证不闭环和依赖页面缺失问题。

## 4. 三条推理轨迹的职责与结论

### 4.1 octos-events

事件计数如下：

    turn/started       127
    turn/completed     108
    turn/error          11
    tool/started       3516
    tool/completed     3516

turn/error 的结构化错误可以分为两类：

1. 早期 provider/gateway 不稳定：ClientConn.Close 和 unexpected EOF；
2. 后期余额耗尽：REQ-8.6 尾段和 full-suite repair 连续 HTTP 402。

它最有价值的作用是确认“模型调用层发生了什么”，而不是判断最终业务页面是否正确。started/completed 的差额还包含 session/orchestration 生命周期，不应直接解释成同等数量的需求失败。

### 4.2 runner-events

ROOT 事件显示：

- design：86 atomic children designed；
- implement：76/86 atomic children implemented；
- test：children not verified；
- runner：completed; nodes not verified。

最终叶子状态为 71 个 test passed、15 个 test failed。这里的 runner completed 只是 runner 生命周期结束，不代表任务成功；76/86 implemented 也不是最终 Playwright 通过率。

生成 agent 在 22:51:39 结束后，runner 才进入 evaluator 测试环境：安装前端依赖、构建、启动应用、部署 generated application，随后在 1 worker 环境执行 Playwright。这个 1 worker 与内部 acceptance 的 2 workers 不同，可能放大时序和超时差异，但目前不能单独认定为根因。

### 4.3 stdout.log

stdout 是还原执行节奏最有用的来源，包含：

- 测试来源和 86 个 spec 映射；
- 初始 raw probe HTTP 200，说明 provider 起初可用；
- 每个节点的实现耗时、工具数、wrote、verified；
- 900 秒 turn、repair request budget、proxy 错误和 402；
- full-suite round 0/1 的 71/86 结果；
- startup rehearsal 和 postflight 资源信息。

资源方面，cgroup memory peak 约 1.309 GB / 2 GB，memory.events 显示 oom=0、oom_kill=0。因此没有证据表明 OOM 是主因。postflight 清理了 643 个 stray process，这是严重的环境卫生信号，但不能直接证明它造成了 API 余额或 Playwright 失败。

## 5. 最终 Playwright 结果如何区分

最终 15 个失败全部是 timedOut，没有非 timeout 的 failed：

    71 passed
    15 timedOut
    0 failed

### 5.1 直接受额度耗尽影响的节点

REQ-8.6.2 至 REQ-8.6.7 在余额耗尽后以 tools=0、wrote=False、verified=False 结束；runner 还记录 REQ-8.6 为 no atomic child implemented。对应 Wishlist 的 6 个最终 timeout 不能用来判断“修复后仍然失败”，因为实现机会本身没有发生。

REQ-8.6.1 和 REQ-8.7 也受 402 影响，但不一定各自对应最终失败测试，应分别保留实现层失败和测试层失败两个口径。

### 5.2 额度耗尽前已经暴露的失败面

以下失败在额度归零前已经有节点 timeout、结构告警或 repair 无法收敛的证据：

- REQ-1.4 Search Function：搜索 suggestion 被找到但保持 hidden；
- REQ-3.4 Subcategory Navigation：Women 链接存在但不可见，click 持续等待；
- REQ-3.6.2 Filter by Color：Black mug 仍存在，颜色过滤行为没有达到预期；
- REQ-6.5 Payment Step：Payment/Place order 结构缺失，最终找不到 checked/agree 按钮；
- REQ-6.6、REQ-6.7：持续找不到 Place order；
- REQ-8.3：找不到 updated/saved/success 反馈；
- REQ-8.4.1、REQ-8.4.4：找不到 My Account 或 Delete 入口。

这些是测试层观察到的具体行为信号，但由于最终状态全部为 timeout，不能把每一项都写成已经完成根因闭环的代码 bug。后续应先在同一模板上做最小复现，再判断是页面缺失、认证状态、可见性、数据 fixture 还是点击链路问题。

证据见 arcbench-e5cb3ca21874-failure-details.md 第 1～55、28～85、103～151、224～470 行。

## 6. 中间态文件的特殊情况

这组附件中的 midrun 不能按普通“早期运行快照”处理：

- midrun JSON SHA-256 与终态 run JSON 完全相同：F30EF58818FAE6E8939B14F349253AB32C25B3FE4C306E7CC6721DBB5AA2236A；
- midrun JSON 已经是 FAILED、score=82.6、71/86，且结束时间与终态一致；
- midrun logs 与终态 logs SHA-256 不同，说明日志仍有独立的中间态版本；
- midrun traceability：interfaces=1、tests=71；
- design-midrun 只有 REQ-0、REQ-1.1、REQ-1.3.1、REQ-1.3.2、REQ-1.4 五个 design key。

因此，midrun JSON 实际上是终态对象的重复落盘，不可用于推断“当时仍在运行”。本次真正有分析价值的中间态线索主要来自 midrun logs、traceability 和 design-midrun；它们证明部分测试已产出，但不能证明剩余节点完成。

## 7. 优化建议

按优先级建议：

1. **额度保护**：开始前检查余额并为 full-suite repair 预留配额；第一次 402 后立即保存 checkpoint、停止后续请求，避免连续消耗 8.6.x 节点和 repair 请求。
2. **修复预算隔离**：为正常实现、单节点 repair 和 full-suite repair 设置独立预算，不允许前序节点耗尽最终 repair 配额。
3. **缩短长 turn**：将支付、订单、账户、wishlist 拆成页面骨架、路由/API、最小 smoke test 三个短切片，避免 30～76 次工具调用后才发现页面结构缺失。
4. **禁止验证前宣称完成**：guard 已提示多次“未执行 build/start/request 就声明完成”；应把 build、启动和最小请求设为节点完成的硬门槛。
5. **结构告警前置阻断**：Payment/Place order、Search results/product link、input label wiring 等基础结构缺失时，暂停下游节点，不继续堆叠依赖功能。
6. **provider 错误有限重试**：对 ClientConn.Close/unexpected EOF 只做有限退避重试，随后记录 provider incident，不让单次网络异常拖长 turn。
7. **保护路径门禁**：在第一次写入前固定允许目录，避免修改 public-tests、playwright 配置和应用保护资产。
8. **统一验收并发口径**：内部 acceptance 使用 2 workers、平台 evaluator 使用 1 worker，应在本地复现中分别跑一次，确认是否存在并发导致的可见性/时序差异。
9. **进程清理前置**：643 个 stray process 说明 cleanup 不能只放在 postflight；每个 smoke test 结束必须立即确认端口和子进程已释放。

## 8. 给后续分析会话的交接结论

建议后续会话使用以下状态标签：

    generation_status: partially_completed_then_quota_exhausted
    interruption_reason: provider_balance_exhausted_during_full_suite_repair
    platform_result: valid_partial_artifact_snapshot
    complete_implementation_claim: false
    confirmed_generation_risks:
      - two proxy errors before quota exhaustion
      - multiple 900s turn timeouts
      - repair request-budget exhaustion
      - protected-file guard triggers
      - repeated no-verification completion claims
    quota_gated_nodes:
      - REQ-8.6.2
      - REQ-8.6.3
      - REQ-8.6.4
      - REQ-8.6.5
      - REQ-8.6.6
      - REQ-8.6.7

本 Run 不应直接触发对全部 Prestashop 功能的全面修复或完整能力评分。最低后续闭环是：恢复 provider 配额或切换已验证 provider，保留当前 71/86 作为部分基线，先对 REQ-1.4、REQ-3.4、REQ-3.6.2、REQ-6.5～6.7、REQ-8.3/8.4.x 做独立复现，再单独验证 REQ-8.6.x 的实现是否因余额耗尽而缺失。
