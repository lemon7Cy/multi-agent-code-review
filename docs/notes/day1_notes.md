# Day 1 学习笔记（2026-05-21）

项目二：「多 Agent 协作代码审查系统」正式开始。

Day1 的目标不是马上做完整系统，而是先搞清楚一个核心问题：

> 为什么代码审查这种任务，适合用 Multi-Agent，而不是一个单 Agent 加很多工具硬做？

今天已经完成两个最小 demo：

| 文件 | 作用 |
|------|------|
| `src/01_single_agent_review.py` | 演示一个 Agent 同时做安全、性能、风格审查 |
| `src/02_multi_agent_review.py` | 演示 Security / Performance / Style 三个专职 Agent 并行审查，再由 Orchestrator 汇总 |

---

## 一、从项目1回顾：单 Agent + Tool Loop

项目1「合同审查 Agent」主要是单 Agent 模式：

```text
用户上传合同
  → 一个 Agent 理解任务
  → Agent 自己决定调用什么工具
  → 工具返回结果
  → Agent 继续分析
  → 最后生成报告
```

对应代码里，本质是：

```text
一个 LLM
一个 system prompt
一组 tools
一个 messages 上下文
一个 while loop
```

这个模式适合项目1，因为合同审查流程比较线性：

```text
识别合同类型 → 提取条款 → 评估风险 → 检索法规 → 生成报告
```

它更像一个专家按照固定流程一步步工作。

---

## 二、为什么项目2不能只用一个“超级 Agent”

代码审查和合同审查不太一样。

代码审查天然有多个维度：

- 安全问题：SQL 注入、XSS、鉴权、硬编码密钥
- 性能问题：N+1 查询、时间复杂度、重复 IO
- 风格问题：命名、可读性、职责拆分、可维护性
- 测试问题：边界条件、覆盖率、异常路径

如果只用一个 Agent 同时负责所有维度，会有三个问题。

### 1. 上下文污染

单 Agent 只有一份 `messages`。

安全分析、性能分析、风格分析都会混在同一份上下文里。

```text
安全 Agent 的思路：这里可能有 SQL 注入
性能 Agent 的思路：这里可能有 N+1 查询
风格 Agent 的思路：这里函数职责太多
```

如果全部塞给同一个 Agent，后续推理时注意力会被稀释，模型容易漏问题或者串角色。

Multi-Agent 的做法是：

```text
Security Agent 有自己的上下文
Performance Agent 有自己的上下文
Style Agent 有自己的上下文
```

每个 Agent 只关注自己的专业问题。

---

### 2. system prompt 无法分裂

“你是安全专家”和“你是性能专家”不是两个工具，而是两种不同的思维方式。

单 Agent 只能有一个 system prompt：

```text
你既是安全专家，又是性能专家，又是代码风格专家……
```

这样 prompt 会越来越泛，角色边界不清晰。

Multi-Agent 可以让每个 Agent 有独立 system prompt：

```text
Security Agent：只关注安全问题
Performance Agent：只关注性能问题
Style Agent：只关注可维护性和代码风格
```

这就是角色专业化。

---

### 3. 单 Agent 天然串行，Multi-Agent 可以并行

代码审查的很多维度互不依赖。

安全审查不一定要等性能审查结束，风格审查也不一定要等安全审查结束。

所以可以这样做：

```text
同一份代码
  ├─ Security Agent 并行审查
  ├─ Performance Agent 并行审查
  └─ Style Agent 并行审查
        ↓
   Orchestrator 汇总结果
```

这就是项目2 Day1 demo 的核心。

---

## 三、今天写的 Demo 1：单 Agent 代码审查

文件：`src/01_single_agent_review.py`

这个 demo 做的事情：

```text
一个 Agent 同时从安全、性能、风格三个维度审查代码
```

它可以发现问题，例如：

- SQL 拼接导致 SQL 注入
- 循环里查数据库导致 N+1 查询
- 函数职责太多，代码可维护性差

但是它的问题也很明显：

```text
一个 Agent 承担所有角色
一个 prompt 覆盖所有维度
一个上下文承载所有分析过程
```

这个 demo 的目的不是说单 Agent 完全不能做，而是用来对比：

> 当任务维度很多、角色差异明显时，单 Agent 会变得不够清晰。

---

## 四、今天写的 Demo 2：Multi-Agent 代码审查

文件：`src/02_multi_agent_review.py`

这个 demo 里有四类角色：

```text
Orchestrator
Security Agent
Performance Agent
Style Agent
```

运行流程：

```text
用户提交代码
  ↓
Orchestrator 接收任务
  ↓
Orchestrator 把同一份代码分发给三个专职 Agent
  ↓
Security / Performance / Style 并行审查
  ↓
Orchestrator 收集结果
  ↓
生成最终审查报告
```

Day1 这里的 Orchestrator 还很简单，只做三件事：

1. 分发任务
2. 等待结果
3. 汇总报告

后面 Day2 / Day3 会继续加强：

- 更复杂的编排模式
- Agent 间通信
- 冲突检测
- 冲突仲裁

---

## 五、我对 Multi-Agent 的理解

今天可以用一个公司协作的例子来理解 Multi-Agent。

```text
Orchestrator Agent ≈ 项目经理 / 技术负责人
Worker Agents ≈ 不同岗位的工程师
```

比如在真实公司里：

```text
项目经理 / 技术负责人
  ├─ 把前端任务分给前端工程师
  ├─ 把后端任务分给后端工程师
  ├─ 把测试任务分给测试工程师
  └─ 最后收集大家结果，协调冲突，推动交付
```

对应到 Multi-Agent：

```text
Orchestrator Agent
  ├─ 把安全审查分给 Security Agent
  ├─ 把性能审查分给 Performance Agent
  ├─ 把风格审查分给 Style Agent
  └─ 最后汇总所有 Agent 的输出
```

每个专职 Agent 都有自己的：

- system prompt
- 上下文 messages
- 工具集 tools
- 输出格式
- 判断标准

所以 Multi-Agent 不是简单“多开几个模型”，而是：

> 把复杂任务拆成多个角色，让每个 Agent 像团队成员一样专注完成自己的部分。

---

## 六、核心对比

| 维度 | 单 Agent | Multi-Agent |
|------|----------|-------------|
| 类比 | 一个全栈工程师干所有事 | 一个团队分工协作 |
| 角色 | 一个泛化角色 | 多个专职角色 |
| system prompt | 一份，容易变长变泛 | 每个 Agent 独立 |
| 上下文 | 所有信息混在一起 | 每个 Agent 上下文隔离 |
| 执行方式 | 多数是串行 | 可以并行 |
| 适合任务 | 流程明确、维度单一 | 维度多、可拆分、角色差异明显 |

---

## 七、今天应该掌握的面试表达

可以这样说：

> 在项目2里，我没有直接使用一个超级 Agent 去审查所有问题，而是采用 Multi-Agent 架构。原因是代码审查天然包含安全、性能、风格等多个维度，不同维度需要不同的专家视角。Multi-Agent 可以让每个 Agent 拥有独立的 system prompt、上下文和工具集，避免上下文污染，同时还能并行执行。Orchestrator 则负责任务分发、结果汇总和后续的冲突仲裁。

更口语化一点：

> 单 Agent 像一个人干所有活；Multi-Agent 像一个团队协作。Orchestrator 像项目经理，Security / Performance / Style Agent 像不同岗位的工程师。

---

## 八、今日代码文件

| 文件 | 内容 |
|------|------|
| `src/01_single_agent_review.py` | 单 Agent 同时做安全 / 性能 / 风格审查，用来展示单 Agent 的局限 |
| `src/02_multi_agent_review.py` | 三个专职 Agent 并行审查，Orchestrator 汇总报告 |
| `requirements.txt` | Day1 demo 依赖：`anthropic`、`python-dotenv` |
| `.env.example` | Claude API 环境变量示例 |

运行方式：

```powershell
cd D:\Agent_project\project2_code_review_multiagent
conda activate agent_env
python src\01_single_agent_review.py
python src\02_multi_agent_review.py
```

如果当前 shell 没有激活 conda，也可以直接运行：

```powershell
C:\Users\Administrator\.conda\envs\agent_env\python.exe src\01_single_agent_review.py
C:\Users\Administrator\.conda\envs\agent_env\python.exe src\02_multi_agent_review.py
```

环境确认：

- conda 环境：`agent_env`
- Python：`3.11.15`
- Python 路径：`C:\Users\Administrator\.conda\envs\agent_env\python.exe`
- 已安装依赖：`anthropic`、`python-dotenv`

未配置 `ANTHROPIC_API_KEY` 时，demo 会走本地模拟输出，方便先验证 Multi-Agent 编排结构。

---

## 九、Day1 总结

今天真正完成的是项目2的基础认知：

```text
项目1：一个 Agent 通过工具循环完成一条流程
项目2：多个 Agent 通过角色分工完成一个复杂任务
```

今天最重要的一句话：

> Multi-Agent 的核心不是 Agent 数量变多，而是复杂任务被拆成多个专业角色，每个角色有独立上下文和职责边界，最后由 Orchestrator 统一协调。

---

## 十、Day2 计划

明天继续学习 Multi-Agent 的编排和通信：

| 主题 | 目标 |
|------|------|
| Orchestrator-Worker 编排模式 | 理解最常见的多 Agent 架构 |
| Sequential / Hierarchical / Network 模式 | 知道不同协作方式适合什么场景 |
| Agent 间通信方式 | 理解共享 messages、消息队列、黑板模式的区别 |
| 角色专业化 demo | 继续完善不同 Agent 的 prompt 和工具边界 |

冲突仲裁先不急，等 Day2 把编排和通信理解清楚后，Day3 再重点做。
