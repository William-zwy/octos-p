# Octos Agent v4.5 运行结果分析

日期：2026-09-27

## 1. 结论

v4.5 没有提升成功率，反而相对于 v2 发生了明显回归：

| 版本 | 通过 | 失败 | 通过率 | 说明 |
|---|---:|---:|---:|---|
| v2 | 31/32 | 1 | 96.9% | 当前本地基线 |
| v4.5 | 25/32 | 7 | 78.1% | 回退 6 项 |

因此 v4.5 不能作为下一版的成功基线。v4.5 的 regression gate 虽然阻止了继续接受更差的 candidate，但它只恢复到了本次运行内部的 best state `73979ee`，没有恢复到 v2 的 31/32 结果。

## 2. v4.5 失败项

最终 full-suite 失败的 7 项：

- `REQ-2.3.1` Delete
- `REQ-2.3.2` Notification and Undo
- `REQ-2.3.3` Trash list
- `REQ-2.5.1` Archive
- `REQ-2.5.2` Archive Undo
- `REQ-2.5.3` Show archived notes
- `REQ-2.8.1` Pin note

全部失败都发生在 Playwright `locator.click` 的 10 秒超时阶段。

典型证据：

```text
locator resolved to <button aria-label="Delete Note">
attempting click action
<button aria-label="More options">More options</button>
from <article class="note-card"> subtree intercepts pointer events
```

其他失败中被报告为拦截者的元素还包括：

- `.note-card` 自身
- 同一张卡片里的 `More options`
- 同一张卡片里的 `Change color`
- 卡片正文 `<p>`

这说明目标按钮存在、可见且启用，但实际鼠标命中点被其他元素覆盖或被错误的层级/布局/交互状态截获。当前证据更接近 `pointer_interception`，不是后端删除、归档或 pin API 逻辑缺失。

## 3. 与 v2 的结构差异

v2 的卡片交互结构包含独立的操作层：

- `.note-card` 使用相对定位；
- `.note-card-actions` 是单独的操作区域；
- 交互按钮以独立 action 元素渲染；
- 按钮的命中区域与卡片内容区域分离。

v4.5 最终模板的 `buildCard()` 使用了：

- `.note-card` 作为可点击容器；
- `.card-actions` 普通文档流布局；
- 多个 `.card-btn` 同时渲染；
- 卡片内部还包含标题链接、正文、颜色面板和其他操作。

v4.5 的 CSS 中，`.note-card` 和 `.card-actions` 没有明确的 `position`、`z-index`、`pointer-events` 和稳定操作层约束。这个结构很容易在 hover、按钮展开或网格布局变化后造成 pointer interception。

## 4. 为什么单项 acceptance 通过但 full-suite 失败

日志显示多项节点在单项运行时曾通过，例如：

```text
REQ-2.5.1 acceptance 1/1 passed
REQ-2.8.1 acceptance 1/1 passed
```

但最终连续 full-suite 失败。这暴露出验证流程的缺陷：

1. 单项测试只证明当前节点、当前初始状态下暂时可用。
2. 后续节点可能重写共享的 `app.js` 或 `style.css`。
3. full-suite 中 hover、卡片排列、页面状态和操作面板会暴露共享布局问题。
4. agent 没有在最终 full-suite 前后保存 DOM 命中信息，也没有把被拦截元素纳入根因分析。
5. agent 将多个相同类型的交互失败误判为普通 CSS 修复任务，repair 后仍保持 `26/32`。

因此后续不能把 `node acceptance passed` 直接等价为 `feature verified`。最终状态必须以 full-suite 和共享场景回归为准。

## 5. v4.5 暴露出的 agent 问题

### 5.1 失败诊断不够细

当前至少需要区分：

- `element_missing`
- `element_hidden`
- `element_disabled`
- `pointer_interception`
- `stale_state`
- `navigation_failure`
- `backend_request_failure`
- `startup_failure`
- `infrastructure_failure`

对于 Playwright 的 `intercepts pointer events`，必须提取：

- 目标 locator；
- 拦截元素；
- 目标所属容器；
- 测试步骤；
- 失败前是否执行过 hover；
- 相关页面和 CSS 文件。

### 5.2 没有共享根因聚类

7 个失败项中至少 6 个直接共享卡片操作层问题，不能按 7 个 feature 分别修复。正确的 repair unit 应该是：

```text
UI interaction root cause:
note-card action hit testing is unstable
affected:
REQ-2.3.*
REQ-2.5.*
REQ-2.8.1
```

### 5.3 完成声明缺少验证门禁

日志中出现过 agent 在没有实际完成 build/start/request 验证时宣称完成的情况。后续必须满足：

```text
build_started = true
server_started = true
target_request_or_acceptance_ran = true
verification_result_collected = true
```

否则不能记录 `verified=True`，也不能把该节点状态用于 best checkpoint。

### 5.4 full-suite baseline 不够稳定

v4.5 repair 使用的 full-suite baseline 曾是 `26/32`，但本地 v2 已有 `31/32`。这说明 baseline 不应只取当前运行的第一次失败结果，还需要：

- 与历史 best baseline 比较；
- 检查测试 identity 是否一致；
- 重复运行关键共享交互；
- 区分真实行为失败和环境/启动失败。

## 6. 下一版修改优先级

下一版建议命名为 `v6.5`，但优先级应调整为：

### P0：证据驱动的交互失败诊断

- 解析 Playwright click/fill/press 失败日志；
- 提取 obstruction element；
- 识别 `pointer_interception`；
- 把 locator、DOM、CSS 和测试步骤放入 `RepairContext`。

### P0：共享根因聚类

- 按错误类型、拦截元素、DOM 容器和修改文件聚类；
- 对同一根因只启动一次 repair；
- repair 目标写成受影响测试集合，而不是单个 test。

### P0：full-suite 稳定性门禁

- 单项通过后保留；
- 共享文件被修改后重新运行受影响测试；
- 最终 full-suite 失败时，full-suite 结果覆盖单项结果；
- candidate 出现 new failure、missing result 或 full-suite 下降时拒绝并恢复 best state。

### P1：验证结算

- 没有真实 build/start/request 不得标记 verified；
- 将行为、启动、超时、基础设施、无进展分别结算；
- 对相同错误连续重复尝试设置停止条件。

### P1：保留现有 regression gate

继续保留：

```text
new_failures
fixed_failures
known_failures
missing_checks
best_passed
best_sha
best_failures
```

但 `best` 应至少与历史本地 best 进行比较，不能只与当前 run 的临时 baseline 比较。

### P2：面向云端复杂题目的业务上下文

在 P0/P1 稳定后，再加入此前四仓库方案中的：

- `RepairContext`
- affected-files scope guard
- 跨页面状态 owner
- 持久化/刷新恢复检查
- 权限边界和 workflow 状态机
- 公式依赖和派生状态同步

## 7. 预期改进目标

下一版的第一目标不是增加 retry 次数，而是避免 v4.5 这种回归：

1. 本地简单题目至少恢复到 v2 的 `31/32`。
2. 出现共享 UI 根因时，agent 能识别为一个 repair group。
3. 单项 acceptance 与 full-suite 结果冲突时，以 full-suite 为准。
4. 修复声明必须有真实验证证据。
5. candidate 不得引入新的失败集合或丢失测试结果。

达到以上条件后，才适合继续针对云端的 GitHub-style ERP 和 Google Sheets-style workspace 增加跨页面状态、权限和派生数据能力。

## 8. 相关结果文件

- v4.5 结果：`hackathon-local-simulation/runs/octos-keep-0926-v4_5/local-result.json`
- v4.5 Playwright 报告：`hackathon-local-simulation/runs/octos-keep-0926-v4_5/template/.arc/playwright-report.json`
- v4.5 调试日志：`hackathon-local-simulation/runs/octos-keep-0926-v4_5/execution.debug.log`
- v2 结果：`hackathon-local-simulation/runs/octos-keep-0926-v2/local-result.json`
