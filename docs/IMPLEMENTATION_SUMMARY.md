# Implementation Summary / Multi-Agent Code Review

> 面向工程复盘的实现总结，记录项目价值、核心架构和主要取舍。

---

## 项目概览

Multi-Agent Code Review 是一个多 Agent 协作代码审查系统：用户上传项目 zip 或提交代码片段后，后端提取代码文件，由 Orchestrator 分发给安全、性能、可维护性等专职 Agent 并行审查，最后统一做去重、风险排序、冲突仲裁，生成中文代码审查报告。

**技术栈**：FastAPI / Pydantic / ThreadPoolExecutor / SSE / HTML + React CDN / Claude Anthropic API / OpenAI-compatible API / unittest

**核心关键词**：Multi-Agent、Orchestrator-Worker、MessageBus、Blackboard、Finding Schema、冲突仲裁、项目级 zip 审查、LLM Tool Use、运行时模型配置、流式输出。

---

## 1. Implementation Milestones

| 阶段 | 主题 | 产出 |
|---|---|---|
| Stage 1 | 为什么代码审查适合 Multi-Agent | 单 Agent 与 Multi-Agent 对比 demo，明确角色专业化和上下文隔离 |
| Stage 2 | 编排模式与通信方式 | Orchestrator-Worker、Sequential、Hierarchical、Network 模式 demo，以及 MessageBus / Blackboard 设计 |
| Stage 3 | 从 demo 升级为后端服务 | FastAPI、统一 Finding schema、Orchestrator 并行调度、去重、排序、冲突仲裁 |
| Stage 4 | 产品化演示能力 | 项目 zip 上传、模型配置、连接测试、流式前端、中文报告 |

对应文档：

```text
docs/notes/day1_notes.md
docs/notes/day2_notes.md
docs/notes/day3_notes.md
docs/notes/day4_notes.md
docs/notes/final_notes.md
```

---

## 2. 学到了什么

### 2.1 Multi-Agent 不是多调几个模型

本系统 的重点不是把同一个 prompt 跑三遍，而是把复杂任务拆成多个有职责边界的角色：

```text
Security Agent      只关注安全风险
Performance Agent   只关注性能问题
Style Agent         只关注可维护性问题
Orchestrator        负责任务分发、结果汇总和最终裁决
```

每个 Agent 有独立的职责、输入输出协议和工具边界。这样可以避免一个“超级 Agent”在同一份上下文里同时处理安全、性能、风格问题导致注意力被稀释。

### 2.2 多 Agent 系统必须先定数据协议

如果每个 Agent 随便输出自然语言，Orchestrator 就很难做汇总、排序和仲裁。所以项目中先定义统一的 `Finding`：

```text
agent / rule_id / category / severity / file_path / line_start
evidence / impact / recommendation / confidence / fingerprint
```

这让所有 Agent 的结果都能被代码消费，而不是只能人工阅读。

### 2.3 Orchestrator 是决策层，不是普通 Agent

Orchestrator 不负责亲自审查代码，而是负责：

```text
选择 Agent
并行调度
收集结果
去重
排序
冲突检测
冲突仲裁
生成最终报告
```

这也是本系统 和普通代码扫描脚本的区别：多个 Agent 不是各说各话，而是由一个统一决策层组织成最终结论。

### 2.4 本地规则 Agent 仍然有价值

项目保留 `rule` 模式，不依赖 API Key 也能演示 SQL 注入、硬编码密钥、缺少鉴权、N+1 查询等问题。

本地规则 Agent 的价值：

- 结果稳定，适合测试和演示。
- 无模型配置时也能运行。
- 可作为未来 LLM Tool Use 的工具边界。
- 可与 LLM Agent 互相补充。

### 2.6 LLM Tool Use 适合作为“深度审查层”

配置模型后，LLM Security / Performance / Style Agent 会通过工具调用多轮收集证据，而不是一次性让模型读完整个项目后自由发挥。当前工具包括模式搜索、文件摘要、函数分析、导入检查和 SQL 安全检查。这样可以把模型能力限制在明确的代码证据上，同时保留规则 Agent 的稳定兜底。

### 2.5 AI 产品要考虑输入边界和成本

Stage 4 的 zip 上传不是简单解压，而是做了工程限制：

```text
zip 最大 50MB
单文件最大 300KB
最多纳入 200 个文件
总文本最大 2MB
跳过 .git / node_modules / dist / build / 二进制文件
防 Zip Slip 路径穿越
```

这体现的是 AI 工程化意识：模型上下文、成本、安全边界都要被代码控制。

---

## 3. 解决了哪些核心问题

### 问题 1：单 Agent 容易角色混乱

代码审查天然包含安全、性能、可维护性、测试等多个维度。项目通过专职 Agent 拆分角色，让每个 Agent 只关注自己负责的问题，降低上下文污染。

### 问题 2：多个 Agent 输出难以统一

项目定义了统一的 `Finding` / `AgentReview` / `ReviewReport` schema，让不同 Agent 的输出可以被 Orchestrator 统一汇总、去重和排序。

### 问题 3：多个建议之间可能冲突

例如性能 Agent 建议批量查询，安全 Agent 要求 SQL 参数化。Orchestrator 通过优先级策略裁决：

```text
安全 > 正确性 > 性能 > 风格
```

最终结论是：可以做批量查询优化，但不能牺牲参数化安全边界。

### 问题 4：只能审查单个文件，不像真实项目

Stage 4 增加项目 zip 上传能力，后端自动过滤并提取代码文件，实现项目级代码审查，更接近真实 PR / 仓库审查场景。

### 问题 5：模型配置写死，不方便演示

项目增加运行时模型配置接口：

```text
GET  /llm-config
POST /llm-config
POST /llm-config/models
POST /llm-config/test
```

支持 Claude、DeepSeek、NewAPI 等 provider，并可在前端保存、刷新模型列表、测试连接。

模型不可用时不会拖垮审查任务：Orchestrator 保留规则 Agent 输出，模型 Agent 在 notes 中记录降级原因，适合现场演示。

### 问题 6：用户等待过程不可见

项目增加流式接口：

```text
POST /api/reviews/stream
POST /api/reviews/upload/stream
```

前端可以逐步展示“收到项目、解压、筛选文件、各 Agent 审查、生成报告”等过程，让 Agent 工作过程可视化。

---

## 4. 当前系统架构

```text
前端页面
  ├─ 输入代码
  ├─ 上传项目 zip
  ├─ 配置模型
  └─ 查看中文报告
        ↓
FastAPI
  ├─ /api/reviews
  ├─ /api/reviews/stream
  ├─ /api/reviews/upload
  ├─ /api/reviews/upload/stream
  ├─ /api/github/webhook
  └─ /llm-config
        ↓
project_loader
  └─ 解压 zip、过滤代码文件、限制大小
        ↓
ReviewOrchestrator
  ├─ Security Agent
  ├─ Performance Agent
  ├─ Style Agent
  └─ LLM Tool Use Agents
        ↓
Blackboard
  └─ 统一收集 Finding
        ↓
Orchestrator
  └─ 去重、排序、冲突仲裁、生成中文报告
```

---

## 5. 核心文件

```text
src/code_review_multiagent/models.py
```

定义 `ReviewRequest`、`ReviewFile`、`Finding`、`AgentReview`、`Conflict`、`ReviewReport`，是多 Agent 协作的数据协议。

```text
src/code_review_multiagent/orchestrator.py
```

项目核心。负责选择 Agent、并行执行、写入 Blackboard、去重、排序、冲突仲裁和报告生成。

```text
src/code_review_multiagent/agents/rule_agents.py
```

本地规则 Agent，包括安全、性能、可维护性检查。

```text
src/code_review_multiagent/agents/llm_agents.py
```

LLM 版专职 Agent，按不同角色生成结构化审查结果。

```text
src/code_review_multiagent/agents/llm_tooluse_agent.py
```

LLM 多轮工具调用 Agent，使用代码分析工具收集证据后输出结构化 Finding。

```text
src/code_review_multiagent/project_loader.py
```

项目 zip 上传解析、路径安全检查、目录过滤、大小限制、代码文件提取。

```text
src/code_review_multiagent/llm_config.py
src/code_review_multiagent/llm_client.py
```

运行时模型配置和不同 provider 的调用适配。

```text
src/code_review_multiagent/app.py
```

FastAPI 入口，提供审查接口、流式接口、上传接口、GitHub Webhook 和模型配置接口。

---

## 6. 当前功能清单

- 单文件代码审查
- 项目 zip 上传审查
- Security / Performance / Style 专职 Agent
- 本地规则模式 `rule`
- 本地规则 + 模型混合模式 `hybrid`
- 模型优先模式 `llm`
- Orchestrator 并行调度
- MessageBus 和 Blackboard 内存实现
- Finding 去重和风险排序
- 安全优先的冲突仲裁
- 中文 Markdown 报告
- FastAPI 接口
- GitHub Webhook 演示入口
- 前端模型配置
- 模型列表刷新和连接测试
- SSE 风格流式进度展示
- unittest 测试覆盖核心逻辑

---

## 7. 运行方式

启动服务：

```powershell
python -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

打开页面：

```text
http://127.0.0.1:8000
```

查看 API 文档：

```text
http://127.0.0.1:8000/docs
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

---

## 8. Design Rationale

### Summary

> Multi-Agent Code Review 是一个多 Agent 协作代码审查系统。我没有让一个大模型同时审查所有问题，而是用 Orchestrator-Worker 架构，把任务拆给安全、性能、可维护性三个专职 Agent。每个 Agent 输出统一的 Finding schema，Orchestrator 再做去重、风险排序和冲突仲裁。系统支持项目 zip 上传、模型运行时配置、GitHub Webhook 入口和流式中文报告展示。

### Architecture rationale

> 这个项目主要体现 Multi-Agent 编排能力。代码审查天然有多个维度，如果用一个超级 Agent，安全、性能、风格问题会混在同一份上下文里，容易漏问题，也很难控制工具边界。所以我设计了 Security、Performance、Style 三类专职 Agent，由 Orchestrator 统一分发任务并并行执行。为了让多 Agent 结果可被代码消费，我定义了统一的 Finding schema，所有 Agent 都输出结构化问题。Orchestrator 收到结果后会写入 Blackboard，再做去重、风险排序和冲突仲裁。例如性能 Agent 建议批量查询，安全 Agent 要求 SQL 参数化时，Orchestrator 会裁决安全优先，性能优化不能破坏参数化约束。

### Further discussion

1. 为什么代码审查适合 Multi-Agent，而合同审查更适合单 Agent + RAG。
2. 为什么要先定义 `Finding` schema，再做 Agent 实现。
3. Orchestrator 如何做去重、排序和冲突仲裁。
4. zip 上传如何过滤无关文件并控制模型成本。
5. 为什么保留本地规则 Agent，而不是完全依赖模型。
6. Claude 原生 API 与 OpenAI-compatible 中转 API 的适配差异。

---

## 9. 后续可扩展方向

1. 调用 GitHub API 拉取真实 PR changed files / patch。
2. 把审查报告自动评论回 GitHub PR。
3. 增加 Test Agent，检查测试缺失和边界用例。
4. 增加 Dependency Agent，检查依赖漏洞。
5. 增加 Architecture Agent，检查模块边界和设计问题。
6. 将内存 MessageBus 替换为 Redis Stream / Celery / Kafka。
7. 保存审查历史记录，支持任务回放。
8. 支持增量审查，只分析本次 diff 而不是全量项目。

---

## 10. 最终总结

本系统 最重要的价值不是“AI 能不能发现代码问题”，而是展示一个复杂 Agent 系统如何工程化：

```text
拆角色 → 定协议 → 并行调度 → 汇总结果 → 去重排序 → 冲突仲裁 → 产品化展示
```

它证明的是：多 Agent 的价值不在于 Agent 数量变多，而在于每个角色有清晰职责边界，并且最终能被 Orchestrator 组织成可执行、可解释、可交付的审查结论。
