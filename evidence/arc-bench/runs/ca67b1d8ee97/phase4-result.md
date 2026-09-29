# 阶段 4 只读诊断报告：arc-bench-web--stackoverflow

PHASE4_RESULT: complete

- run_id: `ca67b1d8ee97`
- submission_id: `362bc0d7b112`
- handoff_id: `ca67b1d8ee97-EC05DCA490A7`
- thread_id: `01a0ef22-e88a-7c42-a856-f9c084f42fd4`
- manifest_sha256: `EC05DCA490A71A61CBC7AE6E6EB17ECAB76FBCAEF1B7DD93056832E42DF5C512`

## 结论

平台最终结果为 **FAILED，60/66，90.9%**，6 个最终用例均为约 10 秒超时：REQ-2.7、REQ-4.5.1、REQ-4.6、REQ-7.3、REQ-8.2.1、REQ-9.6。

已确认的模板问题：

1. `REQ-2.7` 的提交模板没有 Edit Profile 控件、编辑表单、profile update API 或对应路由；失败发生在进入 Profile 后寻找 Profile 按钮的阶段，精确浏览器轨迹缺失，因此登录/header 状态仍作为未知项保留。
2. `REQ-7.3` 所需的 Filter 按钮、筛选面板、自定义筛选持久化和保存后标题渲染均不存在。Questions 页面只有五个固定 feed tabs，后端也没有 custom-filter 路由或字段。
3. `REQ-8.2.1` 的 `badge_user` 确实有 `Teacher` 徽章，后端也渲染通知，但 Profile 的 badges section 没有 `active` 类，而 CSS 隐藏所有非 active section，所以通知和 Teacher 文本不可见。
4. `REQ-4.6` 的页面同时保留原始 `Delete` 和弹窗 `Confirm deletion`。公共 helper 对 `/confirm deletion|delete/i` 先解析 button 并取第一个可见匹配，可能再次点击原始 Delete，不能保证发送 DELETE 请求；这与删除后正文仍存在的报告一致。

强候选但未宣称 confirmed：

- `REQ-4.5.1` 的 PUT、重定向和 `edited` 渲染链路存在，但修复阶段多次未验证且无浏览器网络轨迹，无法区分 PUT/重定向失败与 stale render。
- `REQ-9.6` 的 Responses 内容是 server-rendered 文本/链接，不是 Reply 按钮；activity_user 的种子数据也只有普通 comment。公共 helper 专门寻找 `button[name=/reply/i]`，因此可能在可见文本存在时仍失败。

## 执行链路边界

阶段 3 记录了 7 个 900 秒 implementation turn cap、2 个 provider `proxy_error`、16 个 request-budget guard 和 465 个 postflight 进程回收；没有 OOM 或全局时间预算耗尽证据。这些是运行/修复收敛问题，不能替代模板根因判断。

## 阶段 5 建议

只建议在新的阶段 5 工作流中处理：补齐 profile edit 和 custom filter 合同、修正 badges 激活状态、让删除确认具有唯一定位，并以 workers=1 的 clean-seed 回放验证答案编辑和 Responses。阶段 4 未修改 Agent、官方测试或任务资产，也未创建平台 Run、上传 ZIP 或触发阶段 5。

## 回退说明

Codex app 线程路由在发送前返回 `-32602 Invalid app tool request`。本次使用当前线程身份作为手工文件回退锚点，写入并校验了同一 `handoff_id`、`run_id`、`task_key`、`thread_id` 和 manifest SHA；没有创建重复线程。
