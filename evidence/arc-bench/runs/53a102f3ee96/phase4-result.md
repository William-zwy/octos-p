# 阶段 4只读诊断：arc-bench-web--bookstack / Run 53a102f3ee96

PHASE4_RESULT: complete

## 身份与最终结果

- Run：`53a102f3ee96`
- Submission：`362bc0d7b112`
- Task：`arc-bench-web--bookstack`
- Handoff：`53a102f3ee96-E049C5C5C011`
- Manifest SHA-256：`E049C5C5C0119DF24C337D5914C9B92A24F4D05D7553AE4741D909D5762255FF`
- 平台终态：`PASSED`，score `100`，`34/34`

## 1. 五个 900s cap 的恢复链

| 节点 | 证据链 | 结论 |
| --- | --- | --- |
| `REQ-2.2` | cap 后 `wrote=True, verified=True`，立即验收 `4/4` | 可用的部分状态已经足够，无需 repair。 |
| `REQ-4.2.1` | cap 后 `6/7`；589s repair 仍失败并命中 guard；随后 `REQ-4.3.1` 的共享 repair 后 `8/8` | 共享 server/fixture 修复是 strong candidate，精确因果缺少最终 diff。 |
| `REQ-6.1.1` | Name 字段 fill 超时；两次 repair 补页面路由和 seed，仍 `12/13` | 后续共享路由实现使其最终恢复，单独 repair 的因果不能完全确认。 |
| `REQ-6.1.2` | 同样的 Name 字段超时；两次 repair 仍 `12/13` | 后续 draft-save handler 与 dashboard draft heading 修复后恢复。 |
| `REQ-6.1.3` | cap 后 round 0 为 `0/13`，实际是 `/favicon.ico` ConnectionResetError | rewrite/repair 后后续轮次通过；初始失败主要是验收基础设施触发。 |

## 2. Proxy 与应用问题

`REQ-5.5.2` 是确认的上游 proxy 失败：单个请求、HTTP 400、`api.taotoken.net`、`unexpected EOF`，没有对应应用断言失败证据。

应用/验收侧另有独立问题：未知路径 `/favicon.ico` 未稳定返回 404，而是连接重置；shelf/page/draft 节点还出现了 route、fixture 或 DOM 可观察性缺口。不能把这些问题与 proxy EOF 合并归因。

## 3. Guard、重复探索与进程清理

- 10-request repair guard 触发 8 次独立事件；它会强制结束 repair turn，并多次阻止未经 build/start/request 验证的完成声明。
- `REQ-5.6.1` 使用 106 tools，`REQ-6.1.3` 使用 86 tools，显示重复探索和工具循环是主要耗时来源。
- `REQ-6.1.3`、`REQ-7.2` 走了 full rewrite；其中 `REQ-6.1.3` rewrite 还触碰了受保护的 `.arc` 文件并被 guard 拦截。
- postflight 清理 196 个残留进程，主要为 defunct 的 Chrome、npm、Node 和 shell 子进程，说明进程回收存在明显债务。

## 4. 预算、内存与最终测试

- 全局预算 `51000s`，实际运行 `16537s`，约使用 32.4%，不是限制因素。
- cgroup 上限 2 GiB，峰值 `1,076,064,256` bytes，约 50.1%；`oom=0`、`oom_kill=0`，不是 OOM 瓶颈。
- provider stdout 统计为 1272 requests、40,033,246 tokens；run JSON 为 315,086,357 platform tokens，属于不同计量范围。
- 最终 Playwright 34 项全部通过，报告耗时约 19.3s，不是总耗时瓶颈。
- 费用单位存在冲突：run JSON 标为 `161.881459 CNY`，归档摘要写成 USD；保留该冲突，不做换算。

## 5. 边界与阶段 5

本阶段只完成单 Run 只读诊断。没有修改代码、测试或运行时配置，没有创建新 Run、没有重跑、没有上传，也没有触发阶段 5。平台 build ID、task snapshot、最终构建 SHA、完整 repair diff 和 favicon runtime trace 仍缺失。
