# 阶段4只读诊断结果：arc-bench-lite--bookstack

## 结论范围

本结果只分析 Run `d9a97cb4c92d`，对应任务 `arc-bench-lite--bookstack`。本次分析来源为平台 run 附件、Playwright 报告、failure details、snapshots 和模板 ZIP；不合并旧 Run `6d41952769f7`，不分析 `32e08aaca2e4`，也不把用户提供的 submission ZIP 视为平台已绑定上传包。

本阶段保持只读：没有创建或重跑 Run，没有上传，没有修改 Agent、官方测试、任务快照、ZIP 或运行配置；没有执行阶段5决策。

## Confirmed：已确认事实

### 运行结果

- 最终状态：`FAILED`
- 成绩：`91.2`
- 通过：`31/34`
- 失败阶段：最终 Playwright 执行
- 总运行时间：`12207s`
- 平台 token 计数：`56757262`
- 费用：`29.912722 CNY`
- Playwright：`1.57.0`，`workers=1`，单测试超时 `10000ms`，测试目录 `/workspace/tests`
- 最终套件报告：预期 `31`，异常 `3`，套件约 `50.9s`

### 最终失败链

1. `REQ-4.3.1: Create Shelf`：约 `10014ms` 超时。官方观察器寻找 `Shelf Created 4.3.1` heading。
2. `REQ-6.1.1: Save Page`：约 `10013ms` 超时。官方观察器寻找 `Page Created 6.1.1` heading。
3. `REQ-8.1: Favorite Items`：约 `10013ms` 超时。官方观察器寻找名称为 `Unfavorite` 的 heading。

三个失败均为最终 Playwright 的单测超时，不是阶段4推断的失败类型。

### 静态代码事实

从 `d9a97cb4c92d-template.zip` 检查到：

- Shelf 创建 API 存在并返回 `201`；前端成功后跳转 `shelves.html`，检查到的路径没有输出 `Shelf Created 4.3.1` heading。
- Page 创建 API 存在并返回 `201`；前端成功后跳转 `book.html?id=...`，检查到的书籍页面没有输出 `Page Created 6.1.1` heading。
- Favorite API 和 toggle handler 存在；成功后把按钮文本改为 `Unfavorite` 并设置 `aria-pressed="true"`。官方 locator 却要求 `role=heading`，不是 button。

这些是模板代码中已确认的事实；它们本身不能替代失败时的最终 DOM、网络响应和跳转链。

### 日志与身份边界

d9 的 logs JSON 仅包含 `events=[]`、两个空 stdout 条目和 `pages=2`。因此 provider totals、请求数、视觉模型、推理级别、time budget、Agent 验收 workers、测试并发和 acceptance rounds 均没有被原始日志独立核实。

平台也没有提供 build ID、代码 SHA、payload tree SHA、upload-package SHA 或 task snapshot ID。用户提供的 submission ZIP SHA-256 为 `5871FB40AFB203A4554F0620FE6FBA9C7C3E3FD2D4AC62313F725F7FF4661655`，但平台没有绑定字段，只能作为候选身份对照。

## Strong Candidate：强候选根因

### SC-4.3.1：Shelf 创建成功反馈不满足观察契约

API 创建逻辑存在，但成功路径直接跳转到 `shelves.html`，静态检查没有发现官方等待的 `Shelf Created 4.3.1` heading。因此最强候选是：业务动作可能已经完成，但测试所需的成功反馈没有以官方 locator 能识别的语义呈现。

### SC-6.1.1：Page 创建成功反馈不满足观察契约

API 创建逻辑存在，但成功路径跳转到 `book.html`，静态检查没有发现官方等待的 `Page Created 6.1.1` heading。因此最强候选是：页面保存动作可能已经完成，但创建成功的可观察反馈与测试契约不一致。

### SC-8.1：Favorite 状态的可访问角色不匹配

代码将成功后的状态放在 button 文本 `Unfavorite` 和 `aria-pressed=true` 上，而官方 locator 寻找名称为 `Unfavorite` 的 heading。最强候选是：状态变化或 API 调用未必是问题，真正的阻塞点可能是可访问树中的角色/名称不匹配。

以上三项都必须保留为 `strong_candidate`，不能写成运行时已完全确认的根因，因为本次没有失败时最终 DOM、HTTP response、network trace 或 redirect chain。

## Unknown：证据缺口

- 无 provider input/output/cache token、请求数和可独立复核的模型调用链。
- 无 raw logs 支持的视觉模型、reasoning、time budget、Agent 验收并发、测试并发和 acceptance rounds。
- 无失败时的最终 DOM、网络响应、重定向链和原始 executor `error-context.md`。
- 无平台上传包与用户 submission ZIP 的 SHA 绑定。
- 无证据确认 API 是否在三个失败场景中实际返回成功，或前端是否在某个中间步骤抛出运行时异常。

## 已排除方向

- 不能判定整个应用不可用：已有 `31/34` 通过。
- 不能复用旧 Run 的失败结论；本结果只对 d9 生效。
- 不能把平台异常作为根因：当前证据没有支持平台整体故障。
- 不能把全局增加 timeout 当作主要修复：证据显示的是 locator 超时，未证明增加等待时间能够补足缺失的 UI 语义。

## 影响预估

当前为 `31/34 = 91.2%`。如果三个强候选都通过最小修复得到验证，理论目标是 `34/34 = 100%`，绝对提升 `8.8` 个百分点。最终 Playwright 套件约 `50.9s`，三个失败各自约占 `10s` 超时预算；但总 Run 时长为 `12207s`，现有证据不足以把主要耗时归因于这三个 Playwright 超时，也不对 token 或请求数节省做估算。

## 阶段5边界建议

阶段5如获授权，建议只做窄范围修复：

1. 为 Shelf 和 Page 的成功路径增加统一、可观察且满足官方 locator 的成功反馈，同时保留已有 API、路由和已通过功能。
2. 让 Favorite 状态反馈与官方可访问角色/名称契约一致，并尽量保留现有 button 语义和 API。
3. 先针对三个失败节点及相邻通过节点做本地验证，再考虑平台重跑。
4. 不修改官方 tests，不全局增加 timeout，不重写后端数据模型，不合并旧 BookStack Run。

这些是阶段5建议，不是本次阶段4的执行结果或批准结论。

## 产物身份

- Handoff：`d9a97cb4c92d-955B36FF6BA4`
- Manifest SHA-256：`955B36FF6BA46192010C247652D41D345D6669EF38D30AAD96C20D1A0BCA21CA`
- 结果 JSON：`evidence/arc-bench/runs/d9a97cb4c92d/phase4-result.json`
- 本文档：`evidence/arc-bench/runs/d9a97cb4c92d/phase4-result.md`
PHASE4_RESULT: complete
