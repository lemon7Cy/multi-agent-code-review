# 工程升级计划

## 目标

将当前系统从可运行的多 Agent 审查服务，继续增强为更完整的 PR 审查平台。升级重点不在堆功能，而在让审查链路更可解释、更可测试、更适合接入真实 GitHub Pull Request。

核心方向：

- 在 Orchestrator 前增加 diff-aware 审查上下文。
- 用 Planner 根据改动文件和风险信号分配审查任务。
- 增加测试覆盖 Agent 和 Critic 复核层。
- 将 findings 映射为 GitHub summary comment 或 inline comment。
- 为长耗时审查增加异步 job 状态。

## 阶段范围

第一阶段优先补齐最影响工程可信度的能力：

1. `diff_parser.py`：解析 unified diff，得到 changed files、hunks 和 changed lines。
2. `review_context.py`：把完整文件内容和 diff 合并成审查上下文。
3. `planner.py`：根据文件类型、扩展名和风险信号生成专职 Agent 任务。
4. `test_coverage_agent.py`：识别生产代码改动但缺少测试改动的情况。
5. `critic.py`：对 finding 做二次校验、置信度标注、去重和冲突处理。
6. 为新增能力补测试。
7. 更新 README 和架构文档。

## 任务 1：Diff 解析器

**目标：** 将 GitHub 风格 unified diff 解析为结构化对象。

**文件：**

- 新增：`src/code_review_multiagent/diff_parser.py`
- 新增：`tests/test_diff_parser.py`

**行为要求：**

- 识别 `diff --git a/x b/x` 文件边界。
- 使用 `+++ b/path` 作为新文件路径。
- 解析 hunk header：`@@ -old_start,old_count +new_start,new_count @@`。
- 跟踪新增行的新行号。
- 跟踪删除行的旧行号。
- 正确处理 context line，保证行号递增准确。
- 忽略 `\ No newline at end of file` 标记。
- 支持 old path 为 `/dev/null` 的新文件。

## 任务 2：审查上下文构建

**目标：** 将 `ReviewRequest.files` 和可选 diff 合并成审查上下文，标记每个文件的 changed line 范围。

**文件：**

- 新增：`src/code_review_multiagent/review_context.py`
- 新增：`tests/test_review_context.py`
- 如有需要，扩展 `src/code_review_multiagent/models.py`，为 `ReviewRequest` 增加可选 `diff` 字段。

**行为要求：**

- 没有 diff 时，所有文件仍可审查，但 changed line 集合为空。
- 有 diff 时，将 changed line 映射到对应 `ReviewFile.path`。
- 提供 `is_line_changed(path, line)` 辅助方法。
- 保留完整文件内容，兼容现有 Agent。

## 任务 3：审查任务规划器

**目标：** 根据改动文件、扩展名和风险信号生成不同角色的审查任务。

**文件：**

- 新增：`src/code_review_multiagent/planner.py`
- 新增：`tests/test_planner.py`

**行为要求：**

- 对代码文件默认生成安全、性能、可维护性任务。
- 生产代码发生变更时生成测试覆盖任务。
- 标记常见风险信号：
  - SQL 字符串拼接：`sql_injection_risk`
  - 循环中查询数据库：`n_plus_one_risk`
  - 新增接口或函数但没有测试：`missing_test_risk`
  - 配置、环境变量、疑似密钥字符串：`secret_risk`
- 跳过二进制文件和不支持的文件类型。

## 任务 4：测试覆盖 Agent

**目标：** 识别生产代码改动但缺少相关测试改动的情况。

**文件：**

- 新增：`src/code_review_multiagent/agents/test_coverage_agent.py`
- 修改：`src/code_review_multiagent/agents/__init__.py`
- 修改：默认 Agent builder 或规则 Agent 装配逻辑
- 新增：`tests/test_test_coverage_agent.py`

**行为要求：**

- `src/`、`app/` 或包目录下的生产代码改动，且 `tests/` 没有对应变更时，输出 medium finding。
- 如果匹配测试也发生变更，不输出 finding。
- 建议中给出可能的测试文件路径。
- finding category 为 `Test Coverage`。
- rule id 为 `TEST-MISSING-COVERAGE`。

## 任务 5：Critic 复核层

**目标：** 在所有专职 Agent 完成后，对 findings 做统一校验和整理。

**文件：**

- 新增：`src/code_review_multiagent/critic.py`
- 新增：`tests/test_critic.py`
- 修改：`src/code_review_multiagent/orchestrator.py`
- 如需要，扩展 `src/code_review_multiagent/models.py`，增加 `confidence` 或 `critic_note` 字段。

**行为要求：**

- 对同一文件、同一行、同一 rule id 的 finding 去重。
- 根据证据强度标注置信度。
- 将纯样式类 critical/high finding 降级为 medium。
- 当安全建议与性能建议冲突时，保留安全优先级。
- 将 critic note 写入报告元信息或 finding 字段。

## 任务 6：GitHub 评论 payload 生成器

**目标：** 将 findings 转换为 GitHub review comment payload。

**文件：**

- 新增：`src/code_review_multiagent/pr_commenter.py`
- 新增：`tests/test_pr_commenter.py`
- 测试通过后再修改 `src/code_review_multiagent/github.py`

**行为要求：**

- 只有当 finding line 落在 parsed changed new lines 中时，才生成 inline comment。
- 不能映射到 changed line 的 finding 放入 summary markdown。
- 评论正文包含 severity、agent、evidence 和 recommendation。
- 不在评论中泄露原始密钥，复用或新增 secret masking helper。

## 任务 7：异步审查任务

**目标：** 让长耗时 LLM 审查不再绑定单个 HTTP 请求生命周期。

**文件：**

- 新增：`src/code_review_multiagent/jobs.py`
- 新增：`tests/test_jobs.py`
- 修改：`src/code_review_multiagent/app.py`

**行为要求：**

- `POST /api/reviews/jobs` 返回 `job_id` 和 `queued` 状态。
- 后台 worker 将状态从 `queued` 推进到 `running`、`completed` 或 `failed`。
- `GET /api/reviews/jobs/{job_id}` 返回状态、时间戳、错误信息和结果 id。
- 支持按 job id 查询事件。
- 先使用内存 store，文档中说明 Redis/Celery 升级路径。

## 任务 8：文档与项目呈现

**目标：** 让项目更容易理解、运行和评估。

**文件：**

- 修改：`README.md`
- 修改：`docs/ARCHITECTURE.md`
- 修改：`docs/IMPLEMENTATION_SUMMARY.md`
- 新增：`docs/demo_script.md`

**内容要求：**

- 架构图展示 Webhook、Diff Parser、Planner、Agents、Critic、PR Comments、Metrics/History 的关系。
- 提供本地运行命令。
- 给出 PR 审查样例流程。
- 说明关键工程取舍。
- 说明运行限制和后续扩展点。
