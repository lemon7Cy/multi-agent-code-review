# Day 4 学习笔记：项目级审查、模型配置、流式前端

> 这一节的目标：把项目2从“后端 API demo”升级成更像真实产品的可演示系统。

---

## 一、Day4 解决的问题

Day3 已经有后端 API，但还有三个明显问题：

```text
1. 只能审查一个或少量手动输入的文件
2. 模型 API 配置不够像正式项目
3. 前端一次性出结果，没有 Agent 工作过程
```

Day4 重点补齐：

- 项目 `.zip` 上传
- 自动解压并过滤代码文件
- 运行时模型配置保存
- 模型列表刷新和连接测试
- 前端流式展示 Agent 审查过程
- 报告中文化，减少英文术语

---

## 二、为什么要支持项目 zip 上传

真实代码审查一般不是只看一个文件。

一个风险往往跨文件出现：

```text
routes/users.py    接收 user_id
services/user.py   查询用户
models/user.py     数据结构
config.py          配置密钥
```

只审查一个文件，很难体现“项目级代码审查”。

所以 Day4 增加了：

```text
前端拖入 project.zip
  ↓
后端自动解压
  ↓
过滤无关文件
  ↓
生成 ReviewRequest(files=[多个文件])
  ↓
多 Agent 批量审查
```

核心文件：

```text
src/code_review_multiagent/project_loader.py
```

---

## 三、zip 解压为什么要做安全限制

上传 zip 不能直接无脑解压。

需要防几个问题：

### 1. Zip Slip 路径穿越

恶意 zip 里可能有：

```text
../../Windows/System32/xxx
```

虽然本项目没有落盘解压，但仍然做了路径检查。

### 2. 无关目录太大

真实项目里经常有：

```text
node_modules
.git
.next
dist
build
venv
__pycache__
```

这些不应该进入模型上下文。

### 3. 二进制文件和大文件

例如：

```text
.png
.pdf
.exe
.dll
.jar
.pyc
```

这些不是代码审查重点，也会浪费 token。

所以项目设置了限制：

```text
zip ≤ 50MB
单文件 ≤ 300KB
最多 200 个文件
总文本 ≤ 2MB
```

这体现的是工程意识：

> AI 应用不能只考虑“能不能分析”，还要控制输入边界和成本。

---

## 四、模型配置为什么参考项目1

项目1已经做过运行时模型配置：

```text
/llm-config
/llm-config/models
/llm-config/test
```

项目2也采用同样思路。

核心文件：

| 文件 | 作用 |
|------|------|
| `src/code_review_multiagent/llm_config.py` | 保存 provider、base_url、model、api_key、timeout |
| `src/code_review_multiagent/llm_client.py` | 负责真正调用模型或刷新模型列表 |
| `src/code_review_multiagent/agents/llm_agents.py` | LLM 版 Security / Performance / Style Agent |

配置会保存到：

```text
src/code_review_multiagent/llm_runtime_config.json
```

前端可以直接保存配置，不需要重启后端。

---

## 五、三种审查模式

项目2现在有三种模式：

| 模式 | 作用 |
|------|------|
| `rule` | 只跑本地规则 Agent，不调用模型，适合演示和快速测试 |
| `hybrid` | 本地规则 Agent + 模型 Agent，适合正式审查 |
| `llm` | 优先模型 Agent，没配置 key 时回退规则 Agent |

为什么保留本地规则？

```text
1. 没有 API Key 也能跑
2. 结果稳定，适合测试
3. 可作为模型工具边界
4. 可以和模型结果互相补充
```

---

## 六、Claude 和 NewAPI 的区别

这里踩过一个坑。

一开始把：

```text
provider=claude + base_url
```

误判成 OpenAI-compatible，于是请求到了：

```text
/v1/chat/completions
```

但 Claude / Anthropic 格式应该是：

```text
/v1/messages
```

现在修正为：

| provider | 协议 |
|----------|------|
| `claude` | Anthropic Messages API：`/v1/messages` |
| `deepseek` | OpenAI Chat API：`/v1/chat/completions` |
| `newapi` | OpenAI Chat API：`/v1/chat/completions` |

所以：

- 如果中转站是 Claude 兼容，选 `claude`
- 如果中转站是 OpenAI 兼容，选 `newapi`

---

## 七、为什么要做流式输出

一次性返回结果的问题是：

```text
用户点了按钮
  ↓
页面卡住等待
  ↓
最后突然出现报告
```

这不像 Agent 产品。

所以 Day4 增加了流式接口：

```text
POST /api/reviews/upload/stream
POST /api/reviews/stream
```

前端可以逐步显示：

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

这有两个好处：

1. 用户知道系统正在工作
2. 更像真正的 Agent 执行过程

---

## 八、为什么要中文化输出

最开始报告里有很多英文：

```text
Findings
High / SQL Injection
Conflict Arbitration
Agent Coverage
```

这对开发者能懂，但对客户不友好。

现在改成：

```text
风险概览
高风险：SQL 注入风险
详细问题
问题证据
可能影响
处理建议
冲突仲裁
审查覆盖范围
```

Agent 名称也改成：

```text
安全审查 Agent
性能审查 Agent
可维护性审查 Agent
模型安全审查 Agent
```

这体现的是产品意识：

> 技术系统给客户看的输出，不能只服务开发者，要让非技术客户也能理解问题严重性和处理建议。

---

## 九、Day4 对项目完整度的提升

Day4 之后，项目2从“能跑的 demo”变成了“能演示的产品”：

```text
拖入项目 zip
  ↓
流式展示审查过程
  ↓
多 Agent 并行分析
  ↓
中文报告展示
  ↓
支持模型配置和本地规则回退
```

这比单文件 demo 更像真实 Code Review 平台。

---

## 十、Day4 应该掌握的面试表达

可以这样说：

> Day4 我把系统从单文件审查扩展为项目级审查。用户可以直接上传 zip，后端会做安全解压、目录过滤、大小限制和代码文件提取，然后把多个文件交给 Orchestrator 做多 Agent 审查。同时我参考项目1实现了运行时模型配置，支持 Claude、DeepSeek、NewAPI 三类 provider，并加入流式输出，让前端能展示 Agent 的执行过程，而不是长时间空白等待。

更口语化：

> 这个阶段我主要解决产品化问题：用户怎么上传整个项目、模型怎么配置、审查过程怎么可视化、报告怎么让客户看懂。

---

## 十一、Day4 运行检查

启动：

```powershell
cd D:\Agent_project\project2_code_review_multiagent
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

访问：

```text
http://127.0.0.1:8000
```

测试：

```powershell
C:\Users\Administrator\.conda\envs\agent_env\python.exe -m unittest discover -s tests -v
```
