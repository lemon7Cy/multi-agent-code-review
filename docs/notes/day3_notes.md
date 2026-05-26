# Day 3 学习笔记：从 Demo 到可运行后端

> 这一节的目标：看懂项目2后端是怎么从 Day1/Day2 的教学 demo，升级成一个真正可调用的代码审查服务。

---

## 一、Day3 解决的问题

Day1 / Day2 主要还是“概念验证”：

```text
一段示例代码
  ↓
几个 Agent 模拟审查
  ↓
打印报告
```

这个阶段能说明 Multi-Agent 思路，但还不是一个完整项目。

Day3 做的是把它升级成后端服务：

```text
前端 / API 请求
  ↓
FastAPI
  ↓
ReviewRequest
  ↓
Orchestrator
  ↓
多个 Agent 审查
  ↓
ReviewReport(JSON + Markdown)
```

对应核心文件：

| 文件 | 作用 |
|------|------|
| `src/code_review_multiagent/app.py` | FastAPI 入口，暴露 API |
| `src/code_review_multiagent/models.py` | 请求、问题、报告的数据结构 |
| `src/code_review_multiagent/orchestrator.py` | 多 Agent 编排、汇总、去重、仲裁 |
| `src/code_review_multiagent/agents/rule_agents.py` | 本地规则版 Agent |
| `src/code_review_multiagent/message_bus.py` | Agent 消息总线 |
| `src/code_review_multiagent/blackboard.py` | Agent 结果共享黑板 |

---

## 二、为什么要先定义数据结构

多 Agent 系统最怕每个 Agent 输出格式不一致。

如果 Security Agent 输出：

```text
这里有 SQL 注入，很危险
```

Performance Agent 输出：

```json
{"risk": "N+1", "level": "medium"}
```

Orchestrator 就很难统一汇总。

所以 Day3 先定义统一 schema：

```python
class Finding(BaseModel):
    agent: str
    rule_id: str
    category: str
    severity: Severity
    file_path: str
    line_start: int | None
    evidence: str
    impact: str
    recommendation: str
    confidence: float
    fingerprint: str | None
```

这就是项目2的核心数据单元。

可以理解为：

```text
Finding = 一个 Agent 发现的一个具体问题
```

它必须回答：

- 谁发现的？
- 什么问题？
- 严重程度？
- 在哪个文件哪一行？
- 证据是什么？
- 影响是什么？
- 怎么修？

---

## 三、Orchestrator 在后端里做什么

`ReviewOrchestrator` 是项目2最核心的类。

它不是“又一个审查 Agent”，而是技术负责人 / 项目经理角色。

它做这些事：

```text
1. 根据 mode 选择 Agent
2. 把同一批文件分发给多个 Agent
3. 等待 Agent 返回 AgentReview
4. 从 Blackboard 读取所有 Finding
5. 去重
6. 按风险级别排序
7. 检测冲突并仲裁
8. 生成最终报告
```

简化流程：

```text
ReviewRequest
  ↓
_select_agents()
  ↓
ThreadPoolExecutor 并行执行 agent.review()
  ↓
Blackboard.write_review()
  ↓
_deduplicate()
  ↓
_detect_and_arbitrate()
  ↓
_render_markdown()
```

这里用 `ThreadPoolExecutor` 是为了表达：

> 安全、性能、可维护性审查互不依赖，可以并行跑。

---

## 四、为什么要有 MessageBus 和 Blackboard

Day3 里虽然 Agent 还是本地函数，但架构上已经预留生产形态。

### MessageBus

`MessageBus` 表示 Agent 之间通过消息通信。

现在是内存实现：

```text
Orchestrator -> review.request -> Security Agent
Security Agent -> review.done -> Orchestrator
```

以后可以替换成：

- Redis Stream
- Celery
- Kafka
- RabbitMQ

### Blackboard

`Blackboard` 是共享结果区。

每个 Agent 把自己的审查结果写进去：

```text
Security Agent findings
Performance Agent findings
Style Agent findings
        ↓
Blackboard
        ↓
Orchestrator 汇总
```

它的意义是：

> Orchestrator 不需要知道每个 Agent 内部怎么想，只需要读结构化产物。

---

## 五、本地规则 Agent 为什么有意义

项目2不是只有模型 API。

本地规则 Agent 有两个作用：

### 1. 保证项目不用 API Key 也能演示

没有 key 时，系统依然能发现：

- SQL 拼接
- 硬编码密钥
- 缺少鉴权
- N+1 查询
- 函数职责过多
- 异常处理缺失

### 2. 规则工具可以作为 LLM Agent 的工具边界

现在规则是直接执行。

后续如果改成真正 Tool Use，可以让模型调用这些工具：

```text
Security Agent 可调用：
  - scan_sql_injection
  - scan_hardcoded_secret
  - scan_missing_authz

Performance Agent 可调用：
  - detect_n_plus_one
  - detect_unbounded_query
```

这体现的是：

> Agent 不是随便聊天，而是带着明确工具边界工作。

---

## 六、去重和排序为什么重要

多个 Agent 可能报告同一个问题。

例如：

- Security Agent 说 SQL 拼接有注入风险
- Style Agent 说 SQL 拼接散落在 controller 里不易维护

这两个不完全一样，但如果多个 Agent 对同一行报同一个安全问题，就要合并。

项目里用 `fingerprint` 做稳定标识：

```text
rule_id + file_path + line_start + evidence
```

然后按严重程度排序：

```text
严重 > 高风险 > 中风险 > 低风险 > 提示
```

这样最终报告不会乱。

---

## 七、冲突仲裁是什么

项目2要体现 Multi-Agent 的价值，不能只是“多个 Agent 各说各话”。

所以 Orchestrator 加了冲突仲裁。

当前示例：

```text
Security Agent：SQL 必须参数化，不能拼接
Performance Agent：订单查询应该批量 IN 查询
```

这里可能产生冲突：

```text
如果为了性能把多个 id 拼成 IN 字符串，可能重新引入 SQL 注入。
```

Orchestrator 的裁决是：

```text
先保证安全参数化，再做批量查询优化。
安全 > 正确性 > 性能 > 风格
```

这就是项目2和普通“代码扫描器”的区别。

---

## 八、Day3 应该掌握的面试表达

可以这样说：

> Day3 我把多 Agent demo 重构成了 FastAPI 后端服务。核心是先定义统一的 Finding schema，让不同 Agent 输出可被 Orchestrator 消费。Orchestrator 负责并行调度 Security、Performance、Style Agent，并通过 Blackboard 收集结果，再做去重、优先级排序和冲突仲裁。这样系统不是简单地把多个模型输出拼在一起，而是有统一的数据协议和决策层。

更口语化：

> 多 Agent 系统不能只靠多个 prompt 硬拼，必须先把 Agent 的输入输出协议定清楚，否则后面汇总、去重、仲裁都会乱。

---

## 九、Day3 运行检查

```powershell
cd D:\Agent_project\project2_code_review_multiagent
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m unittest discover -s tests -v
```

启动后端：

```powershell
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

访问：

```text
http://127.0.0.1:8000/docs
```
