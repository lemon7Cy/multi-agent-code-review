# 面试讲法：多 Agent 代码审查系统

## 一句话

这是一个 PR 级多 Agent 代码审查系统：GitHub Webhook 触发后，系统拉取变更文件，分发给安全、性能、可维护性和模型工具调用 Agent，最终由 Orchestrator 合并、去重、排序和仲裁。

## 值得讲的工程点

- Agent 不是简单多 prompt，而是有统一 Finding schema、角色边界、工具边界和 Orchestrator 决策层。
- 规则 Agent 保证无模型 Key 时也可稳定演示，LLM Tool Use Agent 负责更深层语义审查。
- 冲突仲裁有明确优先级，例如安全修复优先于性能优化。
- MessageBus 默认内存实现，可通过 Redis Stream 替换，保留生产化扩展点。

## 生产化权衡

- Webhook 验签和 GitHub token 权限必须分开配置；PR 评论失败不应影响审查报告生成。
- LLM 结果只作为建议，最终报告保留文件、行号、证据和 confidence，方便人工复核。
