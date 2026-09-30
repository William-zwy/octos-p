# ARC-Bench Run 06612411282d 分析报告

## 结论摘要

06612411282d 不应按“完整需求实现后的普通 FAILED”解读。更准确的分类是：

> interrupted_generation_quota_exhausted：生成阶段在 API provider 余额耗尽后被迫中断，随后平台对中断时留下的部分产物执行了最终测试。

因此，平台记录的 FAILED / score=24.4 是一个真实存在的测试快照，但不是完整需求实现的验收结果。它可以用于定位残留代码的问题，不能直接作为 Agent 完整实现能力的结论。

本报告只做证据整理，没有修改原始 Run 附件，也没有修改业务代码。

## 1. Run 基本信息

| 项目 | 值 |
| --- | --- |
| Run | 06612411282d |
| Task | arc-bench-web--12306 |
| Submission | 362bc0d7b112 |
| 模型 | deepseek-v4-flash |
| 平台终态 | FAILED |
| 平台 score | 24.4 |
| 原子需求节点 | 117 |
| 平台实现口径 | 32/117，27.4% |
| Playwright | 33 passed / 99 timedOut / 3 failed，共 135 |
| Run 时长 | 36398s，约 10.1h |
| Provider 请求数 | 3922 |
| Provider token | prompt 155,661,103；completion 2,179,115；reasoning 1,437,936 |

原始目录：

    C:\Users\dayuruozhi\Downloads\闻悦源代码-首轮测试-arc-bench-web-12306\

## 2. 直接中断原因：API 额度耗尽

三条轨迹对同一时间线形成闭环：

| 时间 | 事件 | 证据含义 |
| --- | --- | --- |
| 22:48:29 | REQ-6.2.2 返回 HTTP 402 insufficient_balance | 第一次明确的余额耗尽错误；该节点耗时 215s，日志仍显示 wrote=True verified=True |
| 22:48:30 | REQ-6.3.1 返回同一 402 | tools=0、wrote=False、verified=False，没有实际实现动作 |
| 22:48:32 | REQ-6.3.2 返回同一 402 | tools=0、wrote=False、verified=False |
| 22:48:33 | final check 返回同一 402 | 未能为大量没有 local verdict 的节点做最终核验 |

octos 事件流中的 5 个 turn/error 为：

- 1 个上游 proxy_error / unexpected EOF；
- 4 个 provider quota exhausted / HTTP 402，其中包括上述 3 个节点和 final check。

所以，任务被迫结束的直接原因是 provider 余额耗尽，而不是 Playwright 测试把生成进程杀掉。

主要证据：

- arcbench-06612411282d-stdout.log：约第 3334、3340、3344、3348 行；
- arcbench-06612411282d-octos-events.jsonl：约第 46770、46776、46782、46788 行；
- arcbench-06612411282d-runner-events.jsonl：约第 2351、2357、2363 行。

## 3. 额度耗尽前已经存在的风险

API 402 是最终硬终止，但不是这次运行中唯一的收敛问题。额度耗尽前已经出现：

### 3.1 900 秒 turn 超时

以下实现节点撞到约 900 秒 Octos turn 上限：

    REQ-3.1.5  REQ-3.2.1  REQ-3.3.1  REQ-4.1.2  REQ-4.2.11
    REQ-4.2.15 REQ-4.3.2  REQ-4.3.8  REQ-5.2.5  REQ-5.3.7

这些节点大多有写入动作，但不一定完成可靠验证。例如日志中既出现 wrote=True verified=False，也出现超时但 verified=True 的记录。因此，不能简单地把所有 timeout 节点都判定为“没有代码”，也不能把它们判定为“已完成”。正确状态是：代码可能部分存在，验证可信度不足。

### 3.2 上游 proxy 错误

REQ-3.1.2 在约 448 秒后收到 HTTP 400 proxy_error，错误信息为上游请求 unexpected EOF。这属于 provider/gateway 层故障，不是需求逻辑断言失败，但当时节点状态为 wrote=True verified=False，后续需要独立复核。

### 3.3 结构和流程信号

stdout 还记录了几个重要信号：

- /workspace/tests 没有 acceptance spec，Agent 明确进入“仅依据需求文本构建”的路径；
- skeleton 阶段曾误写受保护文件 requirements/assets/banner1.jpg，随后触发 guard；
- 多个后续节点反复出现 backend/server.js 缺失以及前端按钮 delegated handler 缺失的结构提示；
- 复杂节点经常使用几十次工具调用后才结束，最长达到 89 个工具调用并撞上 turn 上限。

这表明基础启动骨架和关键依赖尚未稳定时，流程仍在继续推进大量下游节点，放大了超时和部分实现风险。

## 4. 三条推理轨迹的职责与结论

### 4.1 octos-events

事件计数：

    turn/started       119
    turn/completed     104
    turn/error           5
    tool/started       4035
    tool/completed     4035

这些数字是事件流计数，不应直接当作“119 个需求 turn”。其中还包含 session/orchestration 事件，未闭合的 started/completed 差额也不能单独解释为全部失败。

它最有价值的证据是 provider 层：先出现一次 proxy EOF，最后连续出现四次余额耗尽。它证明失败发生在模型调用层，并能与 stdout、runner 的时间戳互相对齐。

### 4.2 runner-events

ROOT 事件显示：

- design：117 atomic children designed；
- implement：内部标记 113/117 atomic children implemented；
- test：children not verified；
- runner：completed; nodes not verified。

这里的 runner completed 只表示 runner 生命周期收尾，不表示任务成功。113/117 implemented 也只是 runner 内部的实现标记，不等价于测试通过。

它与 run JSON 的 32/117 = 27.4% 并不矛盾，因为二者统计口径不同：前者接近“实现动作/节点状态”，后者是平台最终采纳的实现完成度。

### 4.3 stdout.log

stdout 是最适合还原人类可读流程的证据源：

- 记录无 acceptance spec 的启动条件；
- 记录 protected-file guard；
- 记录每个节点的耗时、工具数、wrote、verified；
- 记录 proxy error、900 秒 timeout、402 quota exhausted 和 final check；
- 记录 postflight 资源状态。

资源方面，日志显示 cgroup memory peak 约 1.145 GB / 2 GB，oom=0、oom_kill=0。因此没有证据表明 OOM 是本次主因。postflight 虽然清理了 108 个 stray process，但这只能作为环境卫生风险，不能直接证明它导致了 API 或测试失败。

## 5. 最终 Playwright 结果的正确解释

平台最终确实执行了 135 个测试：

    33 passed
    99 timedOut
    3 failed

但测试对象是额度耗尽时留下的部分产物，因此应分成两类解读。

### 5.1 不能直接归因于代码的部分

99 个 timeout 大量集中在登录后流程、搜索结果、订单和支付链路。由于生成阶段已经中断，很多节点没有获得最终验证，无法仅凭 timeout 断言每一个都是独立业务 bug。

### 5.2 已经坐实的代码/可访问性问题

3 个非 timeout 失败都属于可重复的 locator 严格模式问题：

1. REQ-3.1.3：getByLabel('From') 同时匹配 From 输入框和隐藏 location dialog。
2. REQ-3.1.4：getByLabel('Date') 同时匹配 Date 输入框和隐藏 date picker。
3. REQ-3.2.14：结果页 Date 输入框与 date switching bar 产生同名 label 冲突。

修复方向是让隐藏弹层和辅助区域不再与业务输入框复用可访问名称，或让关闭状态的弹层彻底从可访问树中排除；修复后必须用 Playwright strict locator 重跑。

证据见 arcbench-06612411282d-failure-details.md 第 306～329、333～352、554～575 行。

### 5.3 关于“根路径 404”的边界

当前模板压缩包中的 backend/src/server.js 明确把 / 映射为 /index.html，frontend build script 也检查 dist/index.html 是否存在。因此，本次审计不把“根路径 404”列为已经闭环的根因；若其他附件或独立复现仍观察到 404，应单独提供启动命令、请求路径和响应证据后再确认。

## 6. 中间态文件不能当作终态

arcbench-run-06612411282d-midrun.json 当时仍为 RUNNING，不能提供可靠终态分数。中间态 traceability 只有：

    interfaces = 15
    tests      = 0

中间态 design snapshot 约有 99 条设计记录，但 codegen 命中为 0。这些文件的价值是还原“当时做到哪里”和“流程如何推进”，不是证明实现完成。

## 7. 优化建议

按优先级建议：

1. **额度保护**：启动前检查余额并预留 final check 配额；首次 402 后立即停止生成、保存 checkpoint，不要继续请求后续节点和 final check。
2. **先锁定基础骨架**：先验证 build、启动、/、/login、/register、/search 和健康接口，再放行下游依赖节点。
3. **缩短单 turn**：将“读取大量文件、实现多个页面、启动服务、全量验证”拆成短切片，每个切片完成写入和最小 smoke test 后落 checkpoint。
4. **减少重复探索**：为每个模块生成一次紧凑的文件/路由/数据摘要，后续节点复用摘要，避免几十次重复读取把 turn 推向 900 秒上限。
5. **代理错误退避**：对 unexpected EOF 只做有限次数重试；第二次失败后记录为 provider incident，继续执行不依赖该节点的任务或暂停，而不是让错误扩散。
6. **结构 guard 前置**：首次写入前锁定允许目录，只允许 frontend/ 和 backend/；发现核心文件缺失时暂停下游节点。
7. **可访问性契约检查**：在每个页面切片结束时运行 strict locator smoke test，特别检查隐藏 dialog、picker、tab bar 是否与输入框重名。
8. **进程清理前置**：每个 smoke test 结束立即确认端口和 server 进程释放，不要把 108 个 stray process 的清理推迟到 postflight。

## 8. 给后续分析会话的交接结论

后续会话应先读取本报告，再读取原始附件。建议使用以下状态标签：

    generation_status: interrupted
    interruption_reason: provider_balance_exhausted
    platform_result: failed_snapshot_only
    complete_implementation_claim: false
    confirmed_code_issues:
      - duplicate accessible label: From
      - duplicate accessible label: Date picker
      - duplicate accessible label: Date switching bar
    pre_quota_risks:
      - proxy_error
      - repeated 900s turn timeouts
      - protected-file guard
      - missing acceptance specs

本 Run 不应直接触发“业务代码全面修复”或“完整实现能力评分”。若要继续，最低闭环是：补足 API 额度或切换已验证 provider，恢复到最近可用 checkpoint，先修复三个确定性的 label 冲突，再对完整 117 节点进行一次独立生成/验收。
