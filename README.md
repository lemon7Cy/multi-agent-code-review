<div align="center">

# 多 Agent 协作代码审查系统

**面向 Pull Request 和项目压缩包的多角色代码审查、证据收集与结果仲裁平台**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-Webhook-181717?logo=github&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-%E5%B7%A5%E5%85%B7%E8%B0%83%E7%94%A8-7C3AED)
![CI](https://img.shields.io/badge/CI-pytest-2563EB)

</div>

## 项目简介

这是一个面向代码审查场景的多 Agent 系统。它会解析 PR diff 或上传的项目压缩包，根据风险类型规划审查任务，再交给安全、性能、可维护性、测试覆盖等专职 Agent 处理。Orchestrator 负责汇总结果、去重、过滤低置信度建议，并生成结构化审查报告。

项目支持无模型 Key 的规则模式，便于本地稳定运行；配置模型后，LLM Agent 会通过受控工具收集证据，而不是直接生成不可追踪的自由文本。

## 核心能力

- 解析 unified diff，定位 changed files、hunks 和 changed lines。
- 按文件类型与风险信号规划 Security、Performance、Maintainability、Test Coverage 审查任务。
- 内置规则 Agent，无需 API Key 也能完成稳定演示。
- 支持 LLM 工具调用，通过 grep、函数分析、SQL 安全检查等工具收集证据。
- Critic 复核层负责 PR 范围校验、误报抑制、去重和冲突仲裁。
- 支持 GitHub PR webhook、签名校验和评论 payload 生成。
- 支持异步审查任务，记录 queued/running/completed/failed 状态和事件轨迹。
- Web 工作台支持上传项目、查看审查历史、Agent 轨迹和分组建议。
- 支持审查历史、Prometheus 指标、MySQL 持久化和 Docker Compose 部署。

## 项目结构

```text
src/
  code_review_multiagent/
    agents/                 专职规则 Agent 与 LLM Agent
    app.py                  FastAPI 应用入口
    blackboard.py           共享结果黑板
    commenter.py            GitHub summary / inline comment payload
    critic.py               Finding 复核、过滤和去重
    diff_parser.py          unified diff 解析
    github.py               webhook 解析与签名校验
    llm_client.py           Anthropic / OpenAI-compatible 客户端
    llm_config.py           运行时模型配置
    message_bus.py          Agent 消息总线
    models.py               请求、Finding、报告 schema
    orchestrator.py         任务分发、聚合和仲裁
    planner.py              风险感知任务规划
    project_loader.py       项目压缩包解析与安全限制
    review_context.py       diff 与文件上下文映射
  run_review.py             本地 CLI 入口
tests/                      单元测试与集成测试
```

## 快速开始

```bash
git clone https://github.com/lemon7Cy/multi-agent-code-review.git
cd multi-agent-code-review

python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

打开 Web 工作台：

```text
http://127.0.0.1:8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## Docker 运行

```bash
cp .env.example .env
docker compose up --build
```

## 模型配置

不配置模型时，系统会使用规则 Agent 完成稳定审查。配置模型后，LLM 工具调用 Agent 会加入审查流程。

```bash
cp .env.example .env
```

支持的 provider：

- `claude`：Anthropic Messages API。
- `deepseek`：OpenAI-compatible Chat Completions。
- `newapi`：OpenAI-compatible 网关。

运行时配置接口：

```text
GET  /llm-config
POST /llm-config
POST /llm-config/models
POST /llm-config/test
```

如果模型调用失败，Orchestrator 会保留规则 Agent 的结果，并在审查轨迹里记录降级原因。

## 项目压缩包审查

可以在 Web 工作台上传 `.zip`，也可以直接调用接口：

```text
POST /api/reviews/upload
form-data:
  file: project.zip
  repo: owner/repo
  title: Manual review
```

安全限制：

- 压缩包最大 50 MB。
- 单文件最大 300 KB。
- 最多纳入 200 个文件。
- 总文本最大 2 MB。
- 自动跳过 `.git`、`node_modules`、`.next`、`dist`、`build`、二进制文件和生成产物。

## 本地 CLI

```bash
python src/run_review.py path/to/file.py
```

CLI 会输出 Markdown 审查报告。

## GitHub Webhook

入口：

```text
POST /api/github/webhook
```

配置 `GITHUB_WEBHOOK_SECRET` 后，服务会校验 `X-Hub-Signature-256`。配置 `GITHUB_TOKEN` 后，服务可以拉取 PR changed files，并生成 summary comment。用于本地联调时，也可以在 payload 中直接传入 `review_files`。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 文档

- [架构设计](docs/ARCHITECTURE.md)
- [实现总结](docs/IMPLEMENTATION_SUMMARY.md)
- [工程升级计划](docs/engineering_upgrade_plan.md)

## 后续方向

- 将 MessageBus 替换为 Redis Streams，支持分布式 worker。
- 增加依赖安全、架构、许可证合规等 Agent。
- 从 summary comment 扩展到 inline review comment。
- 持久化更细粒度的工具调用轨迹，方便审计和复盘。
