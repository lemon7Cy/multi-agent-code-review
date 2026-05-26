# 项目2学习导读

如果你是为了学习这个项目，建议不要一上来就看所有代码。

按下面顺序看会比较清楚。

---

## 1. 先看 Day1

文件：

```text
docs/notes/day1_notes.md
```

重点理解：

```text
为什么代码审查适合 Multi-Agent，而不是一个超级 Agent。
```

关键词：

- 单 Agent 的局限
- 角色专业化
- 上下文隔离
- 并行审查

---

## 2. 再看 Day2

文件：

```text
docs/notes/day2_notes.md
```

重点理解：

```text
Multi-Agent 怎么编排、怎么通信。
```

关键词：

- Orchestrator-Worker
- Sequential
- Hierarchical
- Network
- MessageBus
- Blackboard

---

## 3. 再看 Day3

文件：

```text
docs/notes/day3_notes.md
```

重点理解：

```text
如何从 demo 变成 FastAPI 后端服务。
```

关键词：

- Finding schema
- ReviewRequest
- ReviewReport
- Orchestrator
- 去重
- 冲突仲裁

---

## 4. 再看 Day4

文件：

```text
docs/notes/day4_notes.md
```

重点理解：

```text
如何从后端 API 变成可演示产品。
```

关键词：

- zip 项目上传
- 模型配置
- Claude / NewAPI 协议区别
- 流式输出
- 中文客户化报告

---

## 5. 最后看完结文档

文件：

```text
docs/notes/project2_final_notes.md
```

重点理解：

```text
整个项目最终长什么样，面试怎么讲。
```

---

## 6. 代码阅读顺序

```text
src/code_review_multiagent/models.py
  ↓
src/code_review_multiagent/agents/rule_agents.py
  ↓
src/code_review_multiagent/orchestrator.py
  ↓
src/code_review_multiagent/project_loader.py
  ↓
src/code_review_multiagent/llm_config.py
src/code_review_multiagent/llm_client.py
src/code_review_multiagent/agents/llm_agents.py
  ↓
src/code_review_multiagent/app.py
  ↓
src/code_review_multiagent/web/index.html
```

---

## 7. 最重要的理解

项目2不是为了证明“AI 能查代码”。

它是为了证明你理解：

```text
多 Agent 系统如何拆角色、定协议、做编排、处理冲突、形成最终结果。
```

如果你能把这句话讲清楚，项目2就算真正学明白了。
