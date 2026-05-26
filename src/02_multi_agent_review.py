"""
Day 1 - Step 2: Multi-Agent 代码审查 Demo
运行: python src/02_multi_agent_review.py

目标：演示 Security / Performance / Style 三个专职 Agent 并行审查同一段代码，
再由 Orchestrator 汇总结果。

和 01_single_agent_review.py 对比：
- 每个 Agent 有独立 system prompt
- 每个 Agent 有独立 messages，上下文互不污染
- 多个 Agent 可以并行执行
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from textwrap import dedent

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6-thinking")

sample_code = dedent(
    r'''
    def get_user_profile(db, request):
        user_id = request.args.get("id")
        sql = "SELECT * FROM users WHERE id = " + user_id
        user = db.execute(sql).fetchone()

        orders = []
        for order_id in user.order_ids:
            orders.append(db.execute(f"SELECT * FROM orders WHERE id = {order_id}").fetchone())

        return {
            "name": user.name,
            "email": user.email,
            "orders": orders,
            "debug_token": "demo-api-key-placeholder"
        }
    '''
).strip()


@dataclass
class ReviewAgent:
    name: str
    system_prompt: str
    mock_result: str

    def review(self, code: str) -> str:
        """每个 Agent 独立完成审查；无 API Key 时用本地模拟结果。"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            time.sleep(0.2)  # 模拟远程调用耗时，便于观察并行效果
            return dedent(self.mock_result).strip()

        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            temperature=1,
            system=self.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"请只从你的专业维度审查下面代码：\n\n```python\n{code}\n```",
                }
            ],
        )
        return "\n".join(block.text for block in response.content if block.type == "text")


security_agent = ReviewAgent(
    name="Security Agent",
    system_prompt="""你是 Security Agent，只关注代码安全问题：SQL 注入、XSS、鉴权、敏感信息泄露、硬编码密钥。
输出：问题、证据、严重级别、修复建议。不要评论性能和风格。""",
    mock_result="""
    - High：`sql = "SELECT * FROM users WHERE id = " + user_id` 存在 SQL 注入风险；改为参数化查询。
    - Medium：响应中返回 `debug_token`，且值疑似硬编码密钥；应删除并改用环境变量/密钥管理。
    - Medium：未看到鉴权/越权校验，用户可能读取他人 profile；应校验当前登录用户权限。
    """,
)

performance_agent = ReviewAgent(
    name="Performance Agent",
    system_prompt="""你是 Performance Agent，只关注性能问题：时间复杂度、N+1 查询、重复 IO、内存浪费。
输出：问题、触发场景、影响、优化建议。不要评论安全和风格。""",
    mock_result="""
    - Medium：循环内按 order_id 逐条查询订单，属于 N+1 查询；订单数量大时数据库往返次数过多。
    - Suggestion：一次性 `WHERE id IN (...)` 批量查询订单，并保留必要索引。
    - Note：输入校验本身开销很低，不应为了性能省略安全校验。
    """,
)

style_agent = ReviewAgent(
    name="Style Agent",
    system_prompt="""你是 Style Agent，只关注工程质量：命名、可读性、职责拆分、可维护性、测试友好性。
输出：问题、可维护性影响、重构建议。不要评论安全和性能。""",
    mock_result="""
    - Low：函数同时负责解析 request、访问数据库、组装响应，职责过多；建议拆成 service/repository/serializer。
    - Low：缺少异常处理，`user` 为空时会访问 `user.order_ids` 报错；建议显式处理未找到用户。
    - Low：返回字段建议定义 DTO/schema，避免接口结构散落在业务函数中。
    """,
)

agents = [security_agent, performance_agent, style_agent]


def orchestrate_review(code: str) -> dict[str, str]:
    """Orchestrator：分发任务，并行等待各 Agent 结果。"""
    results: dict[str, str] = {}

    print("Orchestrator: 分发代码审查任务给 3 个专职 Agent...\n")
    with ThreadPoolExecutor(max_workers=len(agents)) as executor:
        future_to_agent = {executor.submit(agent.review, code): agent for agent in agents}
        for future in as_completed(future_to_agent):
            agent = future_to_agent[future]
            results[agent.name] = future.result()
            print(f"[OK] {agent.name} 完成")

    return results


def generate_summary(results: dict[str, str]) -> str:
    """最小 Orchestrator 汇总：Day1 只做拼接，不做复杂冲突仲裁。"""
    sections = ["# Multi-Agent Code Review Report"]
    for agent_name in [agent.name for agent in agents]:
        sections.append(f"\n## {agent_name}\n{results[agent_name]}")

    sections.append(
        "\n## Orchestrator Summary\n"
        "- 最高优先级：先修复 SQL 注入和敏感信息泄露。\n"
        "- 其次优化 N+1 查询，避免订单数量增长后拖慢接口。\n"
        "- 最后做职责拆分和异常处理，提高可维护性。\n"
        "- Day1 重点：证明三个 Agent 拥有独立角色和独立上下文；冲突仲裁留到后续实现。"
    )
    return "\n".join(sections)


if __name__ == "__main__":
    print("=" * 60)
    print("Multi-Agent 代码审查：Security / Performance / Style 并行协作")
    print("=" * 60)
    print("\n待审查代码：\n")
    print(sample_code)
    print()

    started_at = time.perf_counter()
    review_results = orchestrate_review(sample_code)
    elapsed = time.perf_counter() - started_at

    print(f"\n全部 Agent 完成，用时: {elapsed:.2f}s")
    print("\n" + generate_summary(review_results))

