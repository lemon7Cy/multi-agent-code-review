# 多 Agent 协作代码审查系统

项目2完成版 MVP：多个专职 Agent 从不同维度审查代码，Orchestrator 负责任务分发、结果汇总、去重和冲突仲裁，并提供 FastAPI 接口、GitHub Webhook 入口和可视化页面。

## 核心能力

- **Multi-Agent 编排**：Security / Performance / Style 三个专职 Agent 并行审查。
- **角色专业化**：每个 Agent 有独立职责和工具边界。
- **消息通信**：内置 MessageBus，MVP 使用内存实现，后续可替换 Redis Stream / Celery / Kafka。
- **Blackboard 汇总**：Agent 输出写入共享 artifact store，由 Orchestrator 统一汇总。
- **冲突仲裁**：实现安全优先的仲裁策略，例如“批量查询优化必须服从 SQL 参数化约束”。
- **GitHub Webhook**：提供 `/api/github/webhook` 入口，支持签名校验和 PR payload 演示。
- **Web 工作台**：浏览器打开根路径即可上传项目、查看审查记录和按 Agent 身份拆分的建议。
- **模型 API 接入**：配置模型后，模型 Agent 会自动参与同一次多 Agent 审查；未配置时仍由基础专职 Agent 完成审查。
- **LLM Tool Use 审查**：模型 Agent 可调用 grep、函数分析、SQL 安全检查等工具，多轮收集证据后输出结构化 Finding。
- **项目压缩包审查**：支持上传 `.zip`，后端自动解压、过滤代码文件、批量审查整个项目。

## 目录结构

```text
src/
  code_review_multiagent/
    agents/                 # 专职 Agent 和规则工具
      llm_tooluse_agent.py  # LLM 多轮 tool_use 审查 Agent
    app.py                  # FastAPI 应用
    blackboard.py           # 共享结果黑板
    github.py               # GitHub Webhook 解析与签名校验
    llm_config.py           # 运行时模型配置，持久化到 llm_runtime_config.json
    llm_client.py           # Claude Anthropic API / OpenAI-compatible 中转调用
    message_bus.py          # Agent 消息总线
    models.py               # ReviewRequest / Finding / ReviewReport schema
    orchestrator.py         # Orchestrator 汇总、去重、仲裁
    project_loader.py       # zip 项目包解析、过滤、安全限制
    web/index.html          # React CDN 前端面板
  run_review.py             # 本地 CLI 审查入口
tests/                      # unittest 测试
```

## 快速运行

```powershell
cd D:\Agent_project\project2_code_review_multiagent
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m pip install -r requirements.txt
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

然后打开：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

Docker Compose：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## 模型配置

不配置 API Key 时，系统仍会使用规则 Agent 完整演示；配置模型 API 后，LLM Tool Use Agent 会自动加入 Security / Performance / Style 等专职 Agent 的协作审查。

```powershell
Copy-Item .env.example .env
notepad .env
```

填写：

```text
ANTHROPIC_API_KEY=你的 Claude API Key
ANTHROPIC_MODEL=claude-opus-4-6-thinking
```

也可以在前端点击右上角 **模型配置**，运行时保存：

- provider：`claude` / `deepseek` / `newapi`
- base_url：官方 Claude 可留空；Claude 兼容中转需支持 Anthropic `/v1/messages`
- model：模型名，可刷新 `/v1/models`
- api_key：留空则不覆盖已保存 key
- timeout：请求超时秒数

说明：

- `provider=claude` 走 Anthropic Messages API：`/v1/messages`
- `provider=deepseek` / `provider=newapi` 走 OpenAI-compatible Chat API：`/v1/chat/completions`
- 如果模型调用失败，Orchestrator 保留规则 Agent 输出，并在对应模型 Agent notes 中记录降级原因，避免一次模型故障拖垮整次审查。

后端接口：

```text
GET  /llm-config
POST /llm-config
POST /llm-config/models
POST /llm-config/test
```

## 项目压缩包审查

前端首页默认就是项目上传区：把 `.zip` 拖进去，或者点击选择文件，再点“开始 Agent 审查”。

后端接口：

```text
POST /api/reviews/upload
form-data:
  file: project.zip
  repo: my/project
  title: Project review
```

安全与性能限制：

- zip 最大 50MB
- 单文件最大 300KB
- 最多纳入 200 个文件
- 总文本最大 2MB
- 自动跳过 `.git`、`node_modules`、`.next`、`dist`、`build`、二进制文件等

## 本地 CLI

```powershell
C:\Users\Administrator\.conda\envs\agent_env\python.exe src\run_review.py src\03_day2_orchestration_communication.py
```

输出 markdown 审查报告。

## API 示例

```powershell
$body = @{
  repo = "demo/repo"
  title = "manual review"
  files = @(
    @{
      path = "app/users.py"
      content = 'def f(db, request):
    user_id = request.args.get("id")
    sql = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(sql).fetchone()'
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/reviews -ContentType application/json -Body $body
```

## GitHub Webhook 本地演示

真实 GitHub `pull_request` webhook 默认不携带完整文件内容。生产环境需要用 GitHub API 拉 changed files / patch。MVP 为方便演示，支持在 payload 中传 `review_files`：

```json
{
  "repository": {"full_name": "demo/repo"},
  "pull_request": {"number": 3, "title": "demo pr"},
  "review_files": [
    {"path": "app/users.py", "content": "def f(db, request):\n    user_id = request.args.get(\"id\")\n    sql = \"SELECT * FROM users WHERE id = \" + user_id\n    return db.execute(sql).fetchone()"}
  ]
}
```

入口：

```text
POST /api/github/webhook
```

如果设置了 `GITHUB_WEBHOOK_SECRET`，服务会校验 `X-Hub-Signature-256`。

配置 `GITHUB_TOKEN` 后，系统会在真实 `pull_request` webhook 中调用 GitHub API 拉取 changed files / patch，并把审查 Markdown 评论回 PR。未配置 token 时仍支持 payload 中传 `review_files`，用于本地联调。

## 测试

```powershell
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m unittest discover -s tests -v
```

## 面试表达

> 我在项目2中采用 Orchestrator-Worker 多 Agent 架构。Orchestrator 负责接收 PR 审查任务、分发给 Security / Performance / Style 等专职 Agent，并通过 MessageBus 和 Blackboard 收集结构化 Finding。无模型 Key 时规则 Agent 保证演示稳定；配置模型后，LLM Tool Use Agent 会调用 grep、函数分析、SQL 安全检查等工具做多轮证据收集。最后 Orchestrator 对所有 Agent 的 Finding 做去重、优先级排序和冲突仲裁，例如安全修复优先于性能优化，批量查询方案必须保留 SQL 参数化约束。

## 后续可扩展点

- 把 MessageBus 换成 Redis Stream。
- 增加 Dependency Agent / Test Coverage Agent / Architecture Agent。
- 调用 GitHub API 拉取 PR changed files，并把 markdown 报告评论回 PR。
- 把 LLM 工具执行轨迹更细粒度地存入审查事件，便于面试演示 Agent 思考过程。
