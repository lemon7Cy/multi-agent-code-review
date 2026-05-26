# Day2 设计说明：Multi-Agent 编排与通信

项目2的主流程采用 **Orchestrator-Worker**：

```text
代码输入
  ↓
Orchestrator
  ├─ Security Agent
  ├─ Performance Agent
  └─ Style Agent
  ↓
Blackboard / Results Store
  ↓
结构化 Review Report
```

## 为什么主流程选 Orchestrator-Worker

- 代码审查的安全、性能、风格三个维度可以并行。
- 每个 Worker 有独立 `role_prompt` 和工具边界，避免上下文污染。
- Orchestrator 可以集中处理汇总、排序、去重、冲突仲裁。
- 后续接 GitHub Webhook 时，请求入口天然对应一个 Orchestrator 任务。

## 其他编排模式

| 模式 | 特点 | 适合场景 | 本项目取舍 |
|------|------|----------|------------|
| Orchestrator-Worker | 中央分发，Worker 并行处理 | PR 多维审查 | MVP 主模式 |
| Sequential | 上一步输出影响下一步 | 解析 → 修复 → 验证 | 作为辅助流程 |
| Hierarchical | 多层 Lead 分组管理 Worker | 大型仓库、多语言项目 | 后续扩展 |
| Network | Agent 互相讨论 | 复杂争议、方案评审 | Day3 仲裁后再引入 |

## Agent 通信方式

| 通信方式 | 含义 | 优点 | 风险 |
|----------|------|------|------|
| Shared messages | 直接把上一步 messages 传给下一个 Agent | 简单 | 上下文容易污染 |
| Message bus | Agent 通过队列发送结构化消息 | 解耦，接近生产架构 | 需要消息协议 |
| Blackboard | Agent 把产物写入共享空间 | 适合汇总和仲裁 | 需要定义 artifact schema |

本项目建议：

```text
Agent 输入：ReviewTask
Agent 输出：Finding[]
中间通信：MessageBus
结果汇总：Blackboard
```

## 角色与工具边界

```text
Security Agent
  tools: scan_sql_injection, scan_hardcoded_secret, scan_missing_authz

Performance Agent
  tools: detect_n_plus_one

Style Agent
  tools: check_function_responsibility, check_error_handling
```

这种设计的重点不是“规则扫描器”，而是给后续 LLM Agent 接入留下清晰边界：

- 每个 Agent 只拿到自己的 system prompt。
- 每个 Agent 只暴露自己的工具。
- Orchestrator 只处理结构化产物，不干预 Worker 内部推理。

## Day3 预留点

Day3 可以在 Orchestrator 层实现：

1. finding 归一化：统一 severity、category、file、line、evidence。
2. 去重：多个 Agent 报告同一问题时合并。
3. 冲突检测：例如安全要求更严格校验，性能担心额外开销。
4. 仲裁策略：安全 > 正确性 > 性能 > 风格。
