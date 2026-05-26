# Day 2 学习笔记（2026-05-23）

今天继续项目二：「多 Agent 协作代码审查系统」。

Day2 目标不是做 GitHub Webhook，也不是做冲突仲裁，而是先把多 Agent 的 **编排模式** 和 **通信方式** 想清楚，并写一个可运行 demo。

今日新增文件：

| 文件 | 作用 |
|------|------|
| `src/03_day2_orchestration_communication.py` | 演示 Orchestrator-Worker、Sequential、Hierarchical、Network 四种模式，以及 message bus / blackboard 通信 |
| `docs/dev/day2_multi_agent_patterns.md` | Day2 架构设计说明 |
| `docs/notes/day2_notes.md` | 今日学习笔记 |

---

## 一、项目2最适合的主模式：Orchestrator-Worker

代码审查天然可以拆成多个并行维度：

```text
同一份代码
  ├─ Security Agent 审查安全问题
  ├─ Performance Agent 审查性能问题
  └─ Style Agent 审查可维护性问题
        ↓
   Orchestrator 汇总结果
```

所以项目2 MVP 的主流程选择：

```text
Orchestrator-Worker
```

Orchestrator 负责：

1. 接收审查任务。
2. 把任务分发给不同 Worker Agent。
3. 收集结构化 finding。
4. 后续做去重、排序、冲突仲裁。

Worker Agent 负责：

1. 按自己的角色审查代码。
2. 只调用自己允许的工具。
3. 输出结构化 finding。

---

## 二、四种 Multi-Agent 编排模式

### 1. Orchestrator-Worker

特点：

- 一个中心 Orchestrator 统一分发任务。
- 多个 Worker 并行完成子任务。
- 最后由 Orchestrator 汇总。

适合项目2，因为安全、性能、风格审查可以并行。

### 2. Sequential

特点：

```text
Agent A → Agent B → Agent C
```

上一步输出会影响下一步。

适合强依赖流程，例如：

```text
代码解析 → 修复生成 → 测试验证
```

但它不适合作为项目2的主审查流，因为安全、性能、风格不一定有先后依赖。

### 3. Hierarchical

特点：

```text
总 Orchestrator
  ├─ Backend Lead
  │   ├─ Security Agent
  │   └─ Performance Agent
  └─ Quality Lead
      └─ Style Agent
```

适合大型仓库、多语言、多模块项目。

当前 MVP 暂时不需要，但后续可以扩展。

### 4. Network

特点：

```text
Agent 之间可以互相讨论、互相评论
```

优点是讨论充分；缺点是容易发散、循环。

所以如果后续引入 Network 模式，必须限制：

- 最大讨论轮次
- 终止条件
- 消息格式
- 仲裁策略

---

## 三、Agent 间通信方式

### 1. Shared messages

直接把一个 Agent 的上下文传给另一个 Agent。

优点：简单。

缺点：上下文污染严重，和 Day1 讨论的 Multi-Agent 目标冲突。

### 2. Message bus

Agent 之间通过消息队列通信。

```text
Orchestrator -> review.request -> Security Agent
Security Agent -> review.done -> Orchestrator
```

优点：

- 解耦
- 接近生产架构
- 后续可以换成 Redis / Celery / Kafka

### 3. Blackboard

Agent 把中间产物写入共享黑板。

```text
Security findings
Performance findings
Style findings
        ↓
Blackboard
        ↓
Orchestrator 汇总
```

优点：

- 适合汇总
- 适合去重
- 适合冲突仲裁

---

## 四、今天 demo 里的角色边界

Day2 demo 中每个 Agent 都有自己的工具边界：

```text
Security Agent
  - scan_sql_injection
  - scan_hardcoded_secret
  - scan_missing_authz

Performance Agent
  - detect_n_plus_one

Style Agent
  - check_function_responsibility
  - check_error_handling
```

这个设计很重要。

因为后续接入 LLM 后，工具边界就变成：

```text
不同 Agent 能调用不同工具
```

这比“一个 Agent 拿到所有工具”更容易控制行为。

---

## 五、今天应该掌握的面试表达

可以这样说：

> 在项目2中，我采用 Orchestrator-Worker 作为主架构。Orchestrator 负责任务分发和结果汇总，Security / Performance / Style 等 Worker Agent 独立完成专业审查。Agent 之间不共享完整上下文，而是通过结构化消息和 blackboard 传递结果，这样可以避免上下文污染，也方便后续做去重和冲突仲裁。

更口语化一点：

> 我没有让所有 Agent 混在一个聊天记录里讨论，而是让它们像团队成员一样独立工作，最后把结构化结果交给技术负责人统一汇总。

---

## 六、运行方式

```powershell
cd D:\Agent_project\project2_code_review_multiagent
C:\Users\Administrator\.conda\envs\agent_env\python.exe src\03_day2_orchestration_communication.py
```

不依赖 API Key，可以本地直接运行。

---

## 七、Day2 总结

今天完成的是项目2架构层的第二块基础：

```text
Day1：为什么需要 Multi-Agent
Day2：Multi-Agent 怎么编排、怎么通信
```

今天最重要的一句话：

> 项目2的核心不是让多个 Agent 随便聊天，而是用 Orchestrator-Worker 把复杂审查任务拆成多个可控角色，并通过结构化消息和 blackboard 汇总结果。

---

## 八、Day3 计划

明天重点做冲突检测与仲裁：

| 主题 | 目标 |
|------|------|
| Finding schema | 统一每个 Agent 的输出结构 |
| 去重逻辑 | 合并多个 Agent 对同一问题的重复报告 |
| 冲突检测 | 识别安全建议与性能建议之间的冲突 |
| 仲裁策略 | 实现“安全 > 正确性 > 性能 > 风格”的优先级规则 |

Day3 完成后，项目2的核心多 Agent 闭环就基本成型了。
