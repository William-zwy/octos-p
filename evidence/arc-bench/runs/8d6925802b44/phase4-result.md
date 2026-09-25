# 阶段4只读诊断结果：`arc-bench-lite--bookstack`

## 范围与结论

本记录只分析 Run `8d6925802b44`，对应任务 `arc-bench-lite--bookstack`。没有合并、比较或分析 `b985ae04f3cd`、`977a8ae04117` 或任何其他 Run；没有创建或重跑 Run，没有上传，也没有修改 Agent、官方测试、资产、任务快照、ZIP 或运行配置。阶段5未执行。

结论是：本次失败发生在验收套件身份解析阶段，早于应用生成和业务测试。平台结果为 `FAILED`、score `0`、`0/0`，测试未到达；不能把任何 BookStack 功能或 Playwright 行为列为已证实根因。

## Confirmed：已确认事实

- 运行状态：`FAILED`；score `0`；`passed_count=0`、`failed_count=0`、`total_count=0`；`tests_reached=false`。
- 失败阶段：`generation_agent`。总时长 4 秒，平台 token count 为 `109`，费用为 `0.000453 CNY`。
- 生命周期为：`deploy_agent` 完成 → `start_agent` 失败 → `run_tests` 保持 pending，未执行。
- 失败命令为：

  ```text
  python3 /workspace/submission/main.py /tmp/arcbench/requirements-source --output-dir /workspace/template
  ```

  命令返回退出码 `1`。
- 原始日志链为：依赖安装成功；身份与环境输出；raw chat/completions probe 返回 HTTP 200；流程列出 34 个原子节点和 51000 秒 time budget；随后记录：

  ```text
  [tests] acceptance_identity_ambiguous {"matching_suites": [], "requirements_fingerprint": "5DD4F3C4...", "task_key": null, "task_key_input": "unavailable"}
  [flow] aborted: AcceptanceIdentityError('acceptance_identity_ambiguous: expected one exact suite, found 0')
  ```

- 提交包内存在 `arc-bench-lite--bookstack` 的 bundled suite，其登记 fingerprint 为 `4DC5389C...`，snapshot 为 `official-snapshot:20260917-150121Z`；但运行时 fingerprint 为 `5DD4F3C4...`，没有匹配套件。
- 失败后工作区只看到 `requirements/` 与 `.arc/`；package-shape 检查显示 44 个条目，但缺少 `frontend/`、`backend/`。
- `main.py` 在原始日志中出现；原始日志没有 `/workspace/tests`，测试目录为空，官方测试没有执行；bundled fallback 命中为 0，明文 API key 命中为 0。
- 原始 logs payload 的 `events=[]`，stdout 有 2 页；没有可用的 acceptance 结果。提交包 SHA 已记录，但平台没有提供上传包绑定 SHA。

## Strong candidate：强候选根因

### 1. Requirements 到官方套件的身份契约不匹配

提交包的 `acceptance_identity.py` 会先读取 requirements 中的 `task_key/taskKey`，再尝试从 requirements 路径推导任务键；若仍无法得到任务键，则按 canonical requirements fingerprint 选择唯一套件。两条路径都未成功：日志明确给出 `task_key_input=unavailable`、`task_key=null`、`matching_suites=[]`。

因此最强候选是：运行时 requirements 输入缺少可用任务身份，且其 canonical fingerprint `5DD4F3C4...` 与 bundled BookStack 套件登记的 `4DC5389C...` 不一致。代码按 fail-closed 规则抛出 `AcceptanceIdentityError`，这是生成中止的直接机制。

### 2. Metadata 丢失或 requirements snapshot 不一致

当前证据无法区分两种来源：一是 requirements 输入本应携带 `arc-bench-lite--bookstack` 但字段/路径元数据丢失；二是输入内容来自不同 snapshot，导致 fingerprint 与 `official-snapshot:20260917-150121Z` 不一致。两者都能解释 `task_key=null` 和零匹配，但实际 requirements tree 未随附件交付，所以仍属于强候选而非完全确认的底层归因。

### 3. 应用输出不完整是生成失败的后果

身份解析失败后只产生 `requirements/` 与 `.arc/`，并且缺失 `frontend/`、`backend/`。这足以阻止后续部署和测试，是确定的阻断后果；它不是身份 fingerprint 不匹配的底层原因。

## Unknown：未知项与证据边界

- 实际 requirements tree、其生产方以及 fingerprint `5DD4F3C4...` 的具体差异未知。
- 尚不能区分平台提供了错误 requirements source、提交包与任务 snapshot 不同，还是执行前发生了输入转换/元数据丢失。
- 没有生成后的 template ZIP、Playwright 报告、截图、network trace 或 error-context 正文。
- provider token 分解、请求数、visual model、reasoning level、worker counts 和 acceptance rounds 均未被原始 logs 独立提供。
- summary 声称使用 `/workspace/tests`，但这与原始 logs（没有该路径）和 run 生命周期（测试未到达）冲突；本记录以 run lifecycle/raw logs 为准。
- `node_states` 全部显示 `test-failed`，但这不是已执行的业务测试结果；run 的 tests 数组为空，且 `run_tests` 为 pending。

## 已排除或不支持的判断

- 不是已证实的 BookStack 业务功能或 Playwright locator 失败：测试未执行。
- 不能将 `node_states=test-failed` 解释为 56 个需求实际失败；它与生命周期和空 tests 数组冲突，只保留为平台元数据。
- 没有证据支持平台整体模型/API 故障：raw probe 返回 HTTP 200；这不等于整次运行完全健康，但不支持将平台宕机作为主因。
- 没有证据支持 OOM 或资源耗尽：日志显示内存使用远低于 cgroup 上限、OOM 事件为 0；仅清理了 2 个 stray Chrome 进程。
- 不是 bundled test fallback，也没有明文 API key 暴露：两项命中数均为 0。

## 阶段5边界与建议

当前状态为“未就绪”。本 Run 在应用生成前的验收套件身份解析阶段失败，直接修改 UI 或业务逻辑无法解决该问题。后续应先在独立授权的诊断上下文中取得实际 requirements tree，使用提交包中的 canonical fingerprint 逻辑核对：

1. requirements 是否携带 `task_key=arc-bench-lite--bookstack`；
2. 若没有 task key，其 fingerprint 是否等于官方套件登记的 `4DC5389C...`；
3. 任务输入是否确实来自 `official-snapshot:20260917-150121Z`。

不得通过修改官方 manifest、官方测试或强行放宽匹配规则来“修复”身份问题。只有在 exact suite selection、输出包含 `frontend/` 和 `backend/`、package-shape 与 `main.py` 预检均通过后，才考虑新的授权平台 Run。本阶段不重跑、不上传、不实施阶段5。

## 影响估计

本 Run 的有效完成度为 `0/0`，没有可解释的 feature completion rate。当前已知成本为 109 个平台 token、约 4 秒、`0.000453 CNY`；provider token 和请求数未知。身份路由修复后的收益必须由全新的独立 Run 评估，本次 Run 不支持任何通过率、token 节省或运行时改善幅度预测。

## 身份与校验标识

- Run：`8d6925802b44`
- Task：`arc-bench-lite--bookstack`
- Handoff：`8d6925802b44-A4C3B3E7FF9B`
- Manifest SHA-256：`A4C3B3E7FF9B7C2C1A96ADD43D3E09B7EE69551A1229CA10F8FD0FBDFC626A40`
- 远程推送：未执行

PHASE4_RESULT: complete
