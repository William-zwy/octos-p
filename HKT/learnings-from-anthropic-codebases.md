# 从 Anthropic 代码库学到的关键原则

## 项目概览
- **claude-code**: TypeScript 实现的 Claude CLI 框架（D:\items\Hackathon\claude-code）
- **codex**: Rust 实现的 agent 运行时（D:\items\Hackathon\codex）
- **目标**: 将这些原则应用到 octos agent 优化，解决 ARC-Bench 并发测试失败问题

---

## 一、代码质量原则（claude-code/src/constants/prompts.ts）

### 1. 最小复杂度
**原文**（第 203 行）：
> "Don't add features, refactor code, or make "improvements" beyond what was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra configurability."

**应用到 octos v3**：
```python
# arc/main.py NODE_PROMPT 新增
CRITICAL - Keep implementations SIMPLE and DIRECT:
- Avoid complex event handling (stopPropagation, preventDefault) unless the test explicitly requires it
- Don't add features beyond what the test requires
- Don't over-engineer solutions with unnecessary abstractions
```

**解决的问题**：
- v2 的 REQ-2.4 失败：agent 用了 1586s 和 45 个工具调用，代码过于复杂
- stopPropagation() 导致并发测试时事件处理冲突

---

### 2. 先验证再完成
**原文**（第 211 行）：
> "Before reporting a task complete, verify it actually works: run the test, execute the script, check the output. Minimum complexity means no gold-plating, not skipping the finish line."

**应用到 octos v3**：
```python
# arc/main.py VERIFY_FULL 修改（第 807 行）
"Verify incrementally as you implement — test every major UI component or API endpoint 
immediately after writing it (every 5-10 minutes of work)"
```

**解决的问题**：
- 基线中 agent 等到最后才验证，发现问题时已接近超时
- 增量验证可以更早发现问题，留出修复时间

---

### 3. 诚实报告结果
**原文**（第 233 行）：
> "Report outcomes faithfully: if tests fail, say so with the relevant output; if you did not run a verification step, say that rather than implying it succeeded. Never claim 'all tests pass' when output shows failures."

**应用到 octos v3**：
- 这个原则已经隐含在 octos 的验证循环中
- REPAIR_PROMPT 强制 agent 分析失败原因而不是假装成功

---

## 二、并发测试原则（codex）

### 1. 避免并发冲突的关键警告
**原文**（codex/.codex/skills/babysit-pr/SKILL.md 第 149 行）：
> "Do not run multiple concurrent `--watch` processes for the same PR/state file; keep one watcher session active and reuse it until it stops or you intentionally restart it."

**核心教训**：
并发执行时的**共享状态**和**资源竞争**会导致：
- 单独测试通过
- 全局并发测试失败
- 竞态条件难以重现

**应用到 octos v3**：
```python
# arc/main.py NODE_PROMPT 新增
- The grader runs tests in PARALLEL - your code must work correctly when multiple 
  tests run simultaneously against the same server
- Avoid shared state and race conditions
- Don't use complex event handling that might conflict in concurrent scenarios
```

---

### 2. 并发测试的正确实现（codex/codex-rs/core/tests/suite/tool_parallelism.rs）

**Barrier 同步机制**（第 101-105 行）：
```json
{
  "barrier": {
    "id": "parallel-test-sync",
    "participants": 2,
    "timeout_ms": 1_000
  }
}
```
- 确保多个操作真正同时执行
- 暴露竞态条件和共享状态问题

**多线程测试**（第 92 行）：
```rust
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn read_file_tools_run_in_parallel()
```

**并发性能验证**（第 84-90 行）：
```rust
fn assert_parallel_duration(actual: Duration) {
    assert!(
        actual < Duration::from_millis(1_600),
        "expected parallel execution to finish quickly"
    );
}
```

**启示**：
ARC-Bench 的并发测试环境与此类似：
- 多个测试同时运行
- 共享同一个后端服务器
- 事件处理可能相互干扰

---

## 三、集成测试优先（codex/.codex/skills/code-review-testing/SKILL.md）

**原文**（第 6-8 行）：
> "For agent changes prefer integration tests over unit tests. Integration tests are under `core/suite` and use `test_codex` to set up a test instance of codex.
>
> Features that change the agent logic MUST add an integration test"

**应用到 octos v3**：
```python
# arc/main.py NODE_PROMPT 新增
CRITICAL - Before writing any code:
1. Read and analyze the test helper functions (like renameLabel, clickNamed, etc.) 
   to understand the EXACT DOM structure and accessibility labels expected
2. List all required HTML elements with their roles, names, and ARIA labels 
   that the test will query
3. Verify your understanding: describe what UI the test expects to see
```

**解决的问题**：
- 基线的 REQ-2.7.5 失败：agent 没有分析测试代码，误解了需求
- "Edit labels" 应该是编辑标签定义，agent 却实现了给笔记分配标签

---

## 四、v3 优化策略总结

### ✅ 已应用的原则

1. **简洁性** (claude-code)
   - "Keep implementations SIMPLE and DIRECT"
   - 避免不必要的事件处理复杂度

2. **并发意识** (codex)
   - "grader runs tests in PARALLEL"
   - 警告共享状态和竞态条件

3. **测试驱动理解** (codex)
   - 强制先分析测试代码再编写实现
   - 理解 DOM 结构和可访问性标签

4. **增量验证** (claude-code)
   - 每 5-10 分钟测试一次
   - 不要等到最后才验证

5. **失败模式检测** (原创)
   - 第二次修复时完全换方法
   - 避免重复同样的错误

### 📊 预期效果

| 问题 | 基线 | v1.1 | v2 | v3（目标） |
|------|------|------|-----|-----------|
| REQ-2.7.5 (Edit labels) | ❌ | ❌ | ❌ | ✅ (测试驱动理解) |
| REQ-2.4 (Update Note) | ✅ | ✅ | ❌ | ✅ (简洁性 + 并发) |
| REQ-2.3.3, 2.7.6.3 | ✅ | ❌ | ✅ | ✅ (基线超时) |
| **成功率** | 96.9% | 90.6% | 96.9% | **100%** |

---

## 五、关键代码对比

### NODE_PROMPT 优化

**基线**：
```python
NODE_PROMPT = """
You are an expert web developer...
[通用指导]
"""
```

**v3**：
```python
NODE_PROMPT = """
You are an expert web developer...

CRITICAL - Before writing any code:
1. Read and analyze the test helper functions...
2. List all required HTML elements...
3. Verify your understanding...

While implementing:
- Keep implementations SIMPLE and DIRECT
- The grader runs tests in PARALLEL
- Avoid complex event handling (stopPropagation, preventDefault)
"""
```

### VERIFY_FULL 优化

**基线**：
```python
VERIFY_FULL = "Verify briefly before you finish"
```

**v3**：
```python
VERIFY_FULL = "Verify incrementally as you implement — test every major UI component 
or API endpoint immediately after writing it (every 5-10 minutes of work)"
```

### REPAIR_PROMPT 优化

**v3 新增**：
```python
REPAIR_PROMPT = """
CRITICAL - Before attempting repairs:
1. If this is your second repair attempt and the error is similar to the first, 
   your approach is fundamentally wrong - read the test code carefully and 
   implement a COMPLETELY DIFFERENT solution
2. Analyze the test helper functions...
3. Check if you misunderstood the requirement...
"""
```

---

## 六、学习资源

### claude-code 关键文件
- `src/constants/prompts.ts`: 系统提示词和指导原则
- `src/constants/systemPromptSections.ts`: 提示词缓存和组装

### codex 关键文件
- `.codex/skills/babysit-pr/SKILL.md`: 并发监控警告
- `codex-rs/core/tests/suite/tool_parallelism.rs`: 并发测试实现
- `.codex/skills/code-review-testing/SKILL.md`: 集成测试优先

---

## 总结

从 Anthropic 的两个成熟项目中学到的核心原则：

1. **简洁胜过复杂** - 不要过度设计
2. **并发意识** - 警惕共享状态和竞态条件
3. **测试驱动** - 先理解测试，再写代码
4. **增量验证** - 早发现早修复
5. **诚实报告** - 失败就是失败，不要伪装

这些原则已全部应用到 octos v3，目标是将成功率从 96.9% (31/32) 提升到 100% (32/32)。
