# Stage 1 / Sheet 同包回归分析（2026-10-02）

## 结论

本轮收益为负，但不能把全部回归归因于 request budget 30。`6ad28fd0ab3d` 与 `7616a1cdbddd` 的 Stage 1 需求契约相同（12 atomic、30 scenarios、contract hash `59760e1800806118978418ecea8e02010e38a4786a3a592089f4c667ba9875ac`），但 template ZIP 和 agent commit 不同，因此预算与代码版本同时变化。

可确认的结论是：提高外层 cap 没有带来收益；`7616` 还出现 REQ-2-1-2 的 900 秒超时并从 `5/30` 退化为 `0/30`。这足以否定“继续扩大 cap 就能提分”，但不足以证明 cap 单变量导致分数下降。

## 证据对照

| Run | 任务 | budget 口径 | 生成过程 | 平台结果 |
|---|---|---:|---|---:|
| `6ad28fd0ab3d` | github-stage-1 | 22 + continuation 12 | 12/12 implement ok；0 timeout；18 个独立 cap-hit | 5/30，16.7%，feature 1/12 |
| `7616a1cdbddd` | github-stage-1 | 外层记为 30；日志仍显示节点 22 + continuation 12 | 8/12 有 implement ok；REQ-2-1-2 900s timeout；38 个独立 cap-hit | 0/30，feature 0/12 |
| `9fee9a825b32` | sheet | 12 | 24/24 implement ok；0 timeout | 0/100，feature 0/24 |
| `6e04e0ff14dc` | sheet | 30 | 24/24 implement ok；0 timeout；64 个独立 cap-hit | 0/100，feature 0/24 |

两次 Stage 1 平台均没有返回 `tests[]`、Playwright report 或测试 stdout，不能推断具体隐藏测试名称和断言。`implement ok`、`wrote=True`、`continuation ok` 都只是过程状态，不是功能验收。

## 根因排序

1. **P0 需求到行为的转换失败。** Agent 按 atomic node 推进，没有优先锁定共享入口、资源作用域、错误原子性、刷新恢复和可访问语义。写文件不等于形成完整的 UI → handler → API → storage → visible result 链。
2. **P0 完成状态不真实。** 缺少需求派生的浏览器 smoke 时，模型自报完成无法发现“页面不可操作、结果不持久化、刷新丢失”等问题。
3. **P0 预算控制失配。** cap-hit 后仍可能继续长循环；缺少无进展停止、重复 failure digest 切换和独立 final reserve。提高上限增加了消耗机会，没有增加收敛能力。
4. **P1 实验变量未隔离。** Stage 1 两次 Run 的需求相同，但 template ZIP 与 agent commit 不同，不能作为纯 budget A/B。下一次必须固定 ZIP、需求 hash、task/suite 和模型，只改变预算策略。
5. **P1 平台身份证据不完整。** 平台未回传 generation identity、submission SHA、task/suite key。当前可确认任务相同，但本地 ZIP 与平台实际执行包只能由人工归档关联，不能升级为严格可复现 A/B。

## 下一版执行方案

先固定一个 canonical Agent ZIP 和同一 requirements SHA，做一次 baseline。然后只改变预算策略：

```text
需求编译 4–6
共享入口/骨架 6–8
核心能力切片 12–16
定向修复 6–8
最终 smoke / 打包 reserve 6–8
单节点默认上限 22–24
```

默认采用 `12 + 一次 8` 的受控 continuation；只有真实 product delta、build/start/health 和需求派生 browser smoke 都通过时才允许 continuation。连续无文件变化、重复读取、同一 failure digest 或没有 smoke 进展时立即停止并保存 checkpoint。

Stage 1 优先做入口、session、列表/详情、创建/编辑、刷新恢复；Sheet 优先做 workbook/editor/grid/tab/cell/公式/CSV，再做 filter/sort/validation/pivot。两题可以并行分析，但平台实验必须固定身份并分别记录结果。

## 不可宣称的内容

- 不能把 `0/100` 或 `0/30` 拆成具体隐藏测试失败原因。
- 不能把 `tests[]` 为空解释为所有测试都失败于某个 locator。
- 不能把 `implement ok` 解释为业务功能正确。
- 不能把 7616 的回归严格归因于 budget 30，因为代码版本也变化。
- 不能把本地 requirements-derived smoke 当成官方平台成绩。
