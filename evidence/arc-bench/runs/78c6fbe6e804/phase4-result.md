# 阶段4只读诊断结果：arc-bench-lite--bookstack / Run 78c6fbe6e804

## 范围和结论

本报告只分析 Run `78c6fbe6e804`，不分析 d9 或任何其他 Run，不做历史合并。阶段4保持只读：没有创建或重跑平台 Run，没有上传，没有修改 Agent、官方测试、任务快照、ZIP 或运行配置，也没有执行阶段5修复。

最终平台结果是 `FAILED`，`20/34 = 58.8%`。14 个失败全部是最终 Playwright 的 `timedOut`，单测超时为 `10000ms`。从失败栈和 78c 模板快照看，14 个失败集中在 6 个共享 UI/可访问性角色名称契约上；这是强候选根因，不把缺少失败时最终 DOM 视为已完全确认。

## 已确认事实

### 平台最终结果和失败链路

| 失败节点 | 最终观察器 | 失败操作 | 耗时 |
| --- | --- | --- | ---: |
| REQ-1.2 | `button` named `BookStack` | `locator.click` | 10015ms |
| REQ-2.2 | label matching `Email address` | `locator.fill` | 10012ms |
| REQ-3.1 | label matching `Email address` | `locator.fill` | 10014ms |
| REQ-4.3.1 | form `button` named `Shelf Tags` | `locator.click` | 10013ms |
| REQ-4.5.1 | form `button` named `Shelf Tags` | `locator.click` | 10011ms |
| REQ-5.3.1 | form `button` named `Book Tags` | `locator.click` | 10012ms |
| REQ-5.4.1 | form `button` named `Book Tags` | `locator.click` | 10014ms |
| REQ-5.6.1 | `button` named `New Book` | `locator.click` | 10011ms |
| REQ-6.1.2 | label matching `Email address` | `locator.fill` | 10014ms |
| REQ-6.1.3 | `button` named `Edit` | `locator.click` | 10013ms |
| REQ-7.1 | label matching `Email address` | `locator.fill` | 10013ms |
| REQ-7.2 | label matching `Email address` | `locator.fill` | 10014ms |
| REQ-8.2 | label matching `Email address` | `locator.fill` | 10015ms |
| REQ-9.1 | `button` named `BookStack` | `locator.click` | 10013ms |

Playwright 报告确认：版本 `1.57.0`、`workers=1`、rootDir `/workspace/tests`、官方测试目录 `/workspace/submission/public-tests/arc-bench-web--bookstack`、套件时长约 `164.4s`、预期 `20`、异常 `14`。

### 配置、核验和计量

- 模型：`deepseek-v4-flash`；reasoning：`low`；time budget：`51000s`。
- Agent acceptance workers：`2`；最终 Playwright workers：`1`。
- 入口：`main.py`；测试目录：`/workspace/tests`；官方测试映射已核实。
- bundled fallback hits：`0`；明文 API key hits：`0`；raw chat/completions probe：HTTP 200。
- 平台 token count：`50,940,534`；provider total tokens：`50,940,422`；请求数：`1549`；费用：`25.942949 CNY`。
- Run 总时长：`14383s`，约 4 小时。

### 内部验收必须与平台最终结果分开

原始 stdout 记录 per-node 首轮为 `31/34`，full suite round 0 为 `34/34`，failing nodes 为空；其中 REQ-5.3.1 和 REQ-6.1.2 有后续修复轮次，REQ-6.1.1 记录了基础设施错误。它们都是内部验收事实，不能覆盖最终平台权威结果 `20/34`。

### 模板静态事实

模板 ZIP 是平台生成的 78c template snapshot；`frontend/build.js` 会把 `frontend/src` 原样复制到 `frontend/dist`，日志也记录 build/start rehearsal clean。因此以下源 HTML 角色/名称差异是强诊断证据：

- `frontend/src/index.html` 及各页面共享导航使用 `<a class="brand-link" href="/" aria-label="BookStack">`，不是 `button`。
- `frontend/src/login/index.html` 的邮箱标签文本是 `Email`，不是官方 locator 所需的 `Email address` 匹配文本；后端仍存在 POST `/login` 处理。
- `frontend/src/shelves/new/index.html` 和书架编辑模板将 `Shelf Tags` 放在 checkbox 的 `<label>` 上；创建/编辑书籍模板同理将 `Book Tags` 放在 checkbox label 上，而不是 button。
- `frontend/src/shelves/10/index.html`（seeded Shelf 5.6.1）提供的是名为 `Create New Book` 的 anchor，并携带 `/books/new?shelf=...` 路由上下文，不是名为 `New Book` 的 button。
- 共享 `frontend/src/books/_detail.html` 将 `Edit` 输出为 anchor `href="BOOK_EDIT_HREF"`；REQ-6.1.3 的失败发生在寻找 button `Edit` 时。
- 后端路由存在 login、create/edit shelf、create/edit book、delete draft 等处理；失败栈都停在前置 locator，尚未证明这些业务处理本身失败。

## 根因候选及证据等级：Strong Candidate

### 1. BookStack 首页控制的 role 不匹配

影响 REQ-1.2、REQ-9.1。官方等待 `button` named `BookStack`，模板实际是带 `aria-label` 的 link。最小候选解释是：导航动作可能存在，但可访问角色不满足官方契约。

### 2. 登录邮箱 accessible name 不匹配

影响 REQ-2.2、REQ-3.1、REQ-6.1.2、REQ-7.1、REQ-7.2、REQ-8.2。官方等待 `getByLabel(/Email address/i)`，模板 label 为 `Email`。这些失败发生在填充邮箱之前，因而不能归因于登录提交、session 或后续页面逻辑。

### 3. Shelf Tags role 不匹配

影响 REQ-4.3.1、REQ-4.5.1。官方等待 button `Shelf Tags`，模板使用 checkbox + label。失败发生在进入标签输入和提交前。

### 4. Book Tags role 不匹配

影响 REQ-5.3.1、REQ-5.4.1。官方等待 button `Book Tags`，模板使用 checkbox + label。失败发生在进入标签输入和提交前。

### 5. Shelf 5.6.1 的 New Book role/name 不匹配

影响 REQ-5.6.1。模板提供 anchor `Create New Book`，官方等待 button `New Book`。现有 href 体现了正确业务入口意图，但角色和名称不匹配。

### 6. Book detail 的 Edit role 不匹配

影响 REQ-6.1.3。模板提供 anchor `Edit`，官方等待 button `Edit`。失败发生在进入 draft editor 之前，因此没有证据表明 draft delete handler 本身失败。

以上均为 strong candidate 而不是运行时绝对确认：失败报告给出了 locator 和 timeout stack，但没有提供每个失败页面的最终 DOM/accessibility tree。

## Unknown：证据缺口

- 内部验收 `34/34` 与最终平台 `20/34` 的差异究竟来自状态、执行顺序、构建产物、测试版本还是 harness 环境，现有材料不能确定。
- 缺少失败时每个页面的最终 DOM、可访问树、HTTP response、redirect chain 和 browser console trace。
- `error-context.md` 原文件不可用，平台引用路径返回 404；当前只有报告中提取出的结构化错误。
- 平台没有把用户 submission ZIP 的 SHA 直接绑定到本次上传；不据此扩大身份结论。
- visual model 未在配置证据中找到。

## 已排除方向

- 不能把 14 个失败当作 14 个独立后端故障：它们在六个 locator 契约上重复聚类，并且都在业务动作前超时。
- 没有平台整体故障证据：raw probe 为 HTTP 200，构建/启动 rehearsal clean，另有 20 个最终测试通过。
- 不能把全局提高 timeout 作为主要修复：当前栈显示 role/name 不匹配，而不是已命中控件后的慢响应。
- 不能用内部 acceptance `34/34` 覆盖 final platform `20/34`。

## 最小只读复现实验建议

只在临时目录解压 78c template ZIP，不修改源 ZIP、代码或官方测试：

1. 执行模板 frontend build，比较 `src` 与 `dist` 中上述控件的 role/name 文本。
2. 检查代表性页面上 `BookStack` 的 button/link 数量。
3. 检查 `/login` 上 `getByLabel(/Email address/i)` 与实际邮箱控件 accessible name。
4. 检查 `/shelves/new`、`/books/new` 的 `Shelf Tags`/`Book Tags` button 与 checkbox 角色。
5. 检查 seeded Shelf 5.6.1 的 `New Book` role/name/href。
6. 检查 seeded Book 6.1.3 详情页的 `Edit` role/name/href。

记录 DOM/accessibility counts 和路由目标即可；不修改文件、不改官方 tests、不创建平台 Run。

## 阶段5建议及边界

建议：**有条件地建议阶段5**。如果最小只读检查复现上述六个契约差异，阶段5可优先做一个窄范围的共享语义修复切片，理论上覆盖全部 14 个失败。

允许边界：

1. 保持 BookStack 首页导航、login、Shelf Tags、Book Tags、Shelf New Book、Book Edit 的业务目标不变，只对官方要求的 role/name/accessibility contract 做最小对齐。
2. 保留现有 POST `/login`、书架/书籍 CRUD、draft delete 和已有通过功能。
3. 对六个失败簇及相邻已通过节点做本地验证，再决定是否平台重跑。

明确不做：修改官方 tests、全局增加 timeout、重写后端数据模型、重做无关页面、把本报告当作阶段5已批准或已执行结论。

## 完成率、Token、耗时影响预估

- 当前：`20/34 = 58.8%`。
- 14 个失败若都因上述六个 UI 契约修复并通过，理论目标为 `34/34 = 100%`，绝对提升 `41.2` 个百分点；这是条件性上限，不是保证。
- 最终 Playwright 套件约 `164.4s`，14 个失败的 timeout 预算合计约 `140s`；修复 locator 可能减少这部分等待，但不能直接推导整个 Run 时长。
- 整个 Run 为 `14383s`，主要成本来自 Agent 生成/编排；本阶段不估计生成阶段可节省的 token 或请求数。
- 当前计量基线：平台 token `50,940,534`、provider total `50,940,422`、`1549` requests、`25.942949 CNY`。任何平台重跑都应按新 Run 独立计量。

## 产物身份

- Handoff：`78c6fbe6e804-A3D14157292E`
- Manifest SHA-256：`A3D14157292E3BA5D7AB75872533F73D18973D2ED469828CFE7842DE9B83D806`
- 结果 JSON：`evidence/arc-bench/runs/78c6fbe6e804/phase4-result.json`
- 本文档：`evidence/arc-bench/runs/78c6fbe6e804/phase4-result.md`

PHASE4_RESULT: complete
