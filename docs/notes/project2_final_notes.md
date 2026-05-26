# 项目2完结文档：多 Agent 协作代码审查系统

完成日期：2026-05-23

项目名称：多 Agent 协作代码审查系统

---

## 一、这个项目到底做了什么

项目2不是简单“让 AI 看代码”。

它做的是一个多 Agent 协作式代码审查平台：

```text
用户上传项目 zip / 输入代码
  ↓
后端提取代码文件
  ↓
Orchestrator 分发任务
  ├─ 安全审查 Agent
  ├─ 性能审查 Agent
  └─ 可维护性审查 Agent
  ↓
Blackboard 汇总结果
  ↓
去重、排序、冲突仲裁
  ↓
生成中文审查报告
```

它的重点不是“代码风险分析”这一个功能，而是展示：

```text
复杂任务如何拆给多个 Agent 协作完成。
```

---

## 二、和项目1有什么区别

项目1是合同审查 Agent。

项目2是代码审查 Multi-Agent。

表面看都是：

```text
上传文件 → 分析风险 → 输出报告
```

但核心能力完全不同。

| 维度 | 项目1 | 项目2 |
|------|------|------|
| 核心模式 | 单 Agent + RAG | Multi-Agent + Orchestrator |
| 主要难点 | 长文档、法规检索、条款分析 | 多角色协作、上下文隔离、冲突仲裁 |
| 输入 | 合同文本 / PDF / Word | 项目 zip / 代码文件 / PR payload |
| 工具 | 法规检索、条款分析、报告生成 | 安全扫描、性能分析、可维护性分析 |
| 输出 | 合同风险审查报告 | 代码审查报告 / PR 审查意见 |
| 面试关键词 | RAG、长文档、垂直领域 | 多 Agent、编排、通信、仲裁 |

所以项目1证明：

> 我会做垂直领域 RAG Agent。

项目2证明：

> 我会做多 Agent 协作系统。

---

## 三、项目最终功能清单

### 1. 后端服务

使用 FastAPI。

主要接口：

```text
GET  /
GET  /health
POST /api/reviews
POST /api/reviews/stream
POST /api/reviews/upload
POST /api/reviews/upload/stream
POST /api/github/webhook
GET  /llm-config
POST /llm-config
POST /llm-config/models
POST /llm-config/test
```

### 2. 多 Agent 审查

当前有三类 Agent：

```text
安全审查 Agent
  - SQL 注入风险
  - 敏感信息泄露
  - 越权访问风险

性能审查 Agent
  - N+1 查询
  - 无界查询
  - 重复 IO

可维护性审查 Agent
  - 函数职责过多
  - 异常处理缺失
  - 测试友好性差
```

### 3. 项目 zip 上传

支持上传整个项目压缩包：

```text
project.zip
  ↓
自动解压
  ↓
过滤 .git / node_modules / dist / build / 二进制文件
  ↓
提取代码文件
  ↓
批量审查
```

限制：

```text
zip 最大 50MB
单文件最大 300KB
最多纳入 200 个文件
总文本最大 2MB
```

### 4. 模型配置

参考项目1实现运行时模型配置。

支持：

```text
Claude / Anthropic Messages API
DeepSeek / OpenAI Chat API
NewAPI / OpenAI Chat API 中转
```

前端可以：

- 保存 API Key
- 修改 base_url
- 修改 model
- 刷新模型列表
- 测试连接

### 5. 审查模式

```text
rule    本地规则 Agent，不调用模型
hybrid  本地规则 Agent + 模型 Agent
llm     优先模型 Agent，没配置 key 时回退规则
```

### 6. 流式输出

前端不是一次性等结果，而是逐步显示：

```text
已收到项目压缩包
正在解压 zip
正在筛选代码文件
安全审查 Agent 正在检查
性能审查 Agent 正在检查
可维护性审查 Agent 正在检查
生成中文审查报告
全部完成
```

### 7. 中文客户化报告

报告避免大量英文术语，改成客户更容易理解的表达：

```text
风险概览
详细问题
问题证据
可能影响
处理建议
冲突仲裁
审查覆盖范围
```

---

## 四、最终目录结构

```text
project2_code_review_multiagent/
  README.md
  requirements.txt
  .env.example

  src/
    01_single_agent_review.py
    02_multi_agent_review.py
    03_day2_orchestration_communication.py
    run_review.py

    code_review_multiagent/
      app.py
      models.py
      orchestrator.py
      message_bus.py
      blackboard.py
      github.py
      project_loader.py
      llm_config.py
      llm_client.py
      llm_runtime_config.json

      agents/
        base.py
        rule_agents.py
        llm_agents.py

      web/
        index.html

  tests/
    test_orchestrator.py
    test_github.py
    test_project_upload.py
    test_llm_config.py

  docs/
    notes/
      day1_notes.md
      day2_notes.md
      day3_notes.md
      day4_notes.md
      project2_final_notes.md
```

---

## 五、核心代码怎么读

建议按这个顺序看：

### 第一步：看数据结构

```text
src/code_review_multiagent/models.py
```

先理解：

- `ReviewRequest`
- `ReviewFile`
- `Finding`
- `AgentReview`
- `Conflict`
- `ReviewReport`

这是整个项目的数据协议。

### 第二步：看本地 Agent

```text
src/code_review_multiagent/agents/rule_agents.py
```

理解每个 Agent 负责什么：

```text
Security Agent 只看安全
Performance Agent 只看性能
Style Agent 只看可维护性
```

### 第三步：看 Orchestrator

```text
src/code_review_multiagent/orchestrator.py
```

重点看：

- `_select_agents`
- `review`
- `_deduplicate`
- `_detect_and_arbitrate`
- `_render_markdown`

这是项目2的核心。

### 第四步：看上传项目

```text
src/code_review_multiagent/project_loader.py
```

理解 zip 如何被过滤成代码文件。

### 第五步：看模型配置

```text
src/code_review_multiagent/llm_config.py
src/code_review_multiagent/llm_client.py
src/code_review_multiagent/agents/llm_agents.py
```

理解如何把模型从“写死环境变量”变成“前端可配置”。

### 第六步：看 FastAPI

```text
src/code_review_multiagent/app.py
```

看每个 API 如何调用前面的能力。

### 第七步：看前端

```text
src/code_review_multiagent/web/index.html
```

理解：

- 拖拽上传 zip
- 模型配置弹窗
- 流式读取 SSE
- 中文报告展示

---

## 六、关键架构图

```text
┌────────────────────────────┐
│          前端页面           │
│  上传 zip / 模型配置 / 报告  │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│          FastAPI            │
│ /api/reviews/upload/stream  │
│ /llm-config                 │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│       project_loader        │
│ 解压 zip + 过滤代码文件      │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│       Orchestrator          │
│ 分发 / 汇总 / 去重 / 仲裁     │
└──────┬────────┬────────┬────┘
       │        │        │
       ▼        ▼        ▼
┌──────────┐┌──────────┐┌──────────┐
│安全 Agent││性能 Agent││质量 Agent│
└────┬─────┘└────┬─────┘└────┬─────┘
     │           │           │
     └───────────▼───────────┘
              Blackboard
                  │
                  ▼
          中文 ReviewReport
```

---

## 七、这个项目体现的能力

### 1. Multi-Agent 架构设计

不是一个 Agent 干所有事情，而是拆成不同角色：

```text
安全、性能、可维护性
```

每个角色有自己的职责边界。

### 2. Orchestrator 编排能力

Orchestrator 不负责具体审查，而是负责：

```text
调度、汇总、去重、排序、仲裁
```

### 3. 结构化输出设计

所有 Agent 都必须输出统一的 `Finding`。

这让后续展示、排序、统计、仲裁变得可控。

### 4. 工程化能力

项目不是一个脚本，而是有：

- API
- 前端
- zip 上传
- 模型配置
- 流式输出
- 单元测试
- README

### 5. 产品意识

后期把英文技术输出改成中文客户化表达，说明不仅考虑技术，也考虑用户理解成本。

---

## 八、如何运行

启动后端和前端：

```powershell
cd D:\Agent_project\project2_code_review_multiagent
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

运行测试：

```powershell
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m unittest discover -s tests -v
```

---

## 九、面试怎么讲

可以这样讲：

> 我做了一个多 Agent 协作代码审查系统。它不是让一个大模型同时看所有问题，而是通过 Orchestrator 把审查任务拆给安全、性能、可维护性三个专职 Agent。每个 Agent 输出统一的 Finding schema，Orchestrator 再做去重、风险排序和冲突仲裁。比如安全 Agent 要求 SQL 参数化，性能 Agent 建议批量查询，Orchestrator 会裁决性能优化不能破坏安全边界。系统还支持项目 zip 上传、运行时模型配置、GitHub Webhook 和流式中文报告展示。

更短版：

> 项目2重点体现 Multi-Agent 编排能力。它把代码审查拆成多个专家角色，由 Orchestrator 统一调度和仲裁，解决单 Agent 上下文污染和多维审查结果难以统一的问题。

---

## 十、还能继续优化什么

如果后续继续完善，可以做：

1. 真正接 GitHub API 拉取 PR diff。
2. 把审查报告评论回 GitHub PR。
3. 增加 Test Agent，检查测试缺失。
4. 增加 Dependency Agent，检查依赖漏洞。
5. 增加 Architecture Agent，检查模块设计问题。
6. 把 MessageBus 换成 Redis Stream。
7. 保存审查历史记录。
8. 支持项目级增量审查，而不是每次全量审查。

---

## 十一、最终总结

项目2最终想表达的一句话：

> 多 Agent 的价值不是“多调用几个模型”，而是把复杂任务拆成多个有职责边界的角色，并通过 Orchestrator 把它们的结果组织成可执行、可解释、可仲裁的最终决策。
