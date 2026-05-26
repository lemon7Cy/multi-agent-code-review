"""
Day 1 - Step 1: 单 Agent 代码审查 Demo
运行: python src/01_single_agent_review.py

目标：演示「一个超级 Reviewer」同时看安全、性能、风格三个维度。
缺点：所有维度共享同一份上下文，system prompt 只能写成泛化角色。
"""
import os
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

system_prompt = """你是一个资深代码审查专家，需要同时从以下维度审查代码：
1. Security：SQL 注入、XSS、鉴权、硬编码密钥等安全问题
2. Performance：时间复杂度、N+1 查询、内存浪费等性能问题
3. Style：命名、可读性、重复代码、可维护性等工程风格问题

请输出结构化审查结果：维度、问题、严重级别、建议。"""


def call_claude(prompt: str) -> str:
    """调用 Claude；如果没有配置 API Key，则输出本地模拟结果，保证 demo 可运行。"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return dedent(
            """
            【本地模拟结果：未配置 ANTHROPIC_API_KEY】
            - Security / High：拼接 user_id 生成 SQL，存在 SQL 注入风险；建议使用参数化查询。
            - Security / Medium：返回 debug_token 且疑似硬编码敏感信息；建议移除并使用密钥管理。
            - Performance / Medium：循环内逐条查询 orders，存在 N+1 查询；建议批量查询。
            - Style / Low：函数同时处理请求解析、查询、响应组装；建议拆分职责。
            """
        ).strip()

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        temperature=1,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n".join(block.text for block in response.content if block.type == "text")


if __name__ == "__main__":
    print("=" * 60)
    print("单 Agent 代码审查：一个 prompt 同时覆盖安全 / 性能 / 风格")
    print("=" * 60)
    print("\n待审查代码：\n")
    print(sample_code)

    result = call_claude(f"请审查下面这段代码：\n\n```python\n{sample_code}\n```")

    print("\n审查结果：\n")
    print(result)
    print("\n关键理解：单 Agent 能做多维审查，但所有维度共享同一份上下文，角色边界不清晰。")
