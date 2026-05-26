"""
Day 2: Multi-Agent 编排与通信 Demo
运行:
    python src/03_day2_orchestration_communication.py

目标：
1. 演示 Orchestrator-Worker 是项目2最适合的主流程。
2. 对比 Sequential / Hierarchical / Network 三种协作模式。
3. 用最小可运行代码说明 Agent 间通信的三种方式：
   - 直接传参 / shared messages
   - 消息队列 / message bus
   - 黑板模式 / blackboard
4. 强化“角色专业化”：不同 Agent 只有自己的 prompt 和工具边界。

说明：
Day2 仍然使用本地规则模拟 Agent 输出，不依赖 API Key。
后续接入 Claude 时，只需要把 ReviewAgent.review() 内部的本地规则替换成 LLM 调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from textwrap import dedent
from typing import Callable, Iterable


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


@dataclass(frozen=True)
class Finding:
    agent: str
    severity: str
    category: str
    evidence: str
    recommendation: str

    def to_markdown(self) -> str:
        return (
            f"- {self.severity} / {self.category}：{self.evidence}\n"
            f"  - 建议：{self.recommendation}"
        )


@dataclass(frozen=True)
class AgentMessage:
    sender: str
    receiver: str
    topic: str
    payload: object
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class MessageBus:
    """最小消息队列：用 topic + receiver 传递 Agent 间消息。"""

    def __init__(self) -> None:
        self._messages: list[AgentMessage] = []

    def publish(self, message: AgentMessage) -> None:
        self._messages.append(message)

    def consume(self, receiver: str, topic: str | None = None) -> list[AgentMessage]:
        matched = [
            msg
            for msg in self._messages
            if msg.receiver == receiver and (topic is None or msg.topic == topic)
        ]
        self._messages = [msg for msg in self._messages if msg not in matched]
        return matched


class Blackboard:
    """
    黑板模式：所有 Agent 把中间产物写到同一个共享空间。
    Orchestrator 不需要知道每个 Agent 的内部步骤，只读取最终 artifacts。
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, list[Finding]] = {}

    def write_findings(self, owner: str, findings: list[Finding]) -> None:
        self._artifacts[owner] = findings

    def read_all_findings(self) -> list[Finding]:
        results: list[Finding] = []
        for findings in self._artifacts.values():
            results.extend(findings)
        return results

    def read_by_owner(self, owner: str) -> list[Finding]:
        return self._artifacts.get(owner, [])


Tool = Callable[[str, str], Finding | None]


def scan_sql_injection(agent_name: str, code: str) -> Finding | None:
    if '"SELECT * FROM users WHERE id = " + user_id' not in code:
        return None
    return Finding(
        agent=agent_name,
        severity="High",
        category="SQL Injection",
        evidence="使用字符串拼接构造 users 查询，request.args 中的 id 可控。",
        recommendation="使用参数化查询，并对 id 做类型校验。",
    )


def scan_hardcoded_secret(agent_name: str, code: str) -> Finding | None:
    if "demo-api-key-placeholder" not in code:
        return None
    return Finding(
        agent=agent_name,
        severity="Medium",
        category="Secret Exposure",
        evidence="响应中返回 debug_token，且 token 值硬编码在代码里。",
        recommendation="删除 debug_token 字段；敏感配置改走环境变量或密钥管理服务。",
    )


def scan_missing_authz(agent_name: str, code: str) -> Finding | None:
    if "request.args.get(\"id\")" not in code:
        return None
    return Finding(
        agent=agent_name,
        severity="Medium",
        category="Authorization",
        evidence="接口直接按传入 id 查询用户资料，未看到当前登录用户与目标用户的权限校验。",
        recommendation="在查询前校验 current_user 是否有权访问目标 user_id。",
    )


def detect_n_plus_one(agent_name: str, code: str) -> Finding | None:
    if "for order_id in user.order_ids" not in code:
        return None
    return Finding(
        agent=agent_name,
        severity="Medium",
        category="N+1 Query",
        evidence="在订单循环里逐条执行 db.execute，订单数量增长会导致数据库往返次数线性增加。",
        recommendation="改为 WHERE id IN (...) 批量查询订单，并确认 order id 字段有索引。",
    )


def check_function_responsibility(agent_name: str, code: str) -> Finding | None:
    has_request = "request.args.get" in code
    has_db = "db.execute" in code
    has_response = "return {" in code
    if not (has_request and has_db and has_response):
        return None
    return Finding(
        agent=agent_name,
        severity="Low",
        category="Maintainability",
        evidence="同一个函数同时解析请求、访问数据库、组装响应，职责边界不清晰。",
        recommendation="拆分为 controller / service / repository / serializer，便于测试和维护。",
    )


def check_error_handling(agent_name: str, code: str) -> Finding | None:
    if "fetchone()" not in code:
        return None
    return Finding(
        agent=agent_name,
        severity="Low",
        category="Error Handling",
        evidence="user 可能为空，但后续直接访问 user.order_ids。",
        recommendation="显式处理用户不存在场景，例如返回 404 或业务错误码。",
    )


@dataclass
class ReviewAgent:
    name: str
    role_prompt: str
    tools: list[Tool]

    def review(self, code: str) -> list[Finding]:
        """只运行本角色被允许的工具，体现工具边界。"""
        findings: list[Finding] = []
        for tool in self.tools:
            finding = tool(self.name, code)
            if finding:
                findings.append(finding)
        return findings


security_agent = ReviewAgent(
    name="Security Agent",
    role_prompt="只关注 SQL 注入、鉴权、敏感信息泄露；不评价性能和风格。",
    tools=[scan_sql_injection, scan_hardcoded_secret, scan_missing_authz],
)

performance_agent = ReviewAgent(
    name="Performance Agent",
    role_prompt="只关注 N+1 查询、重复 IO、时间复杂度；不评价安全和风格。",
    tools=[detect_n_plus_one],
)

style_agent = ReviewAgent(
    name="Style Agent",
    role_prompt="只关注命名、职责拆分、可维护性、异常处理；不评价安全和性能。",
    tools=[check_function_responsibility, check_error_handling],
)

agents = [security_agent, performance_agent, style_agent]


class Orchestrator:
    def __init__(self, workers: Iterable[ReviewAgent]) -> None:
        self.workers = list(workers)
        self.bus = MessageBus()
        self.blackboard = Blackboard()

    def run_orchestrator_worker(self, code: str) -> list[Finding]:
        """
        项目2主模式：
        Orchestrator 分发同一份代码，Worker 独立审查，结果写入 blackboard。
        """
        for worker in self.workers:
            self.bus.publish(
                AgentMessage(
                    sender="Orchestrator",
                    receiver=worker.name,
                    topic="review.request",
                    payload={"code": code, "role_prompt": worker.role_prompt},
                )
            )

        for worker in self.workers:
            requests = self.bus.consume(worker.name, topic="review.request")
            if not requests:
                continue
            findings = worker.review(code)
            self.blackboard.write_findings(worker.name, findings)
            self.bus.publish(
                AgentMessage(
                    sender=worker.name,
                    receiver="Orchestrator",
                    topic="review.done",
                    payload=findings,
                )
            )

        done_messages = self.bus.consume("Orchestrator", topic="review.done")
        all_findings: list[Finding] = []
        for message in done_messages:
            all_findings.extend(message.payload)  # type: ignore[arg-type]
        return all_findings


def sequential_pipeline(code: str) -> list[Finding]:
    """
    Sequential 模式：上一步输出影响下一步。
    适合“代码解析 → 安全审查 → 修复建议生成”这类强依赖流程。
    缺点是慢，而且后续 Agent 容易被前序结论锚定。
    """
    ordered_agents = [style_agent, security_agent, performance_agent]
    findings: list[Finding] = []
    context = code
    for agent in ordered_agents:
        agent_findings = agent.review(context)
        findings.extend(agent_findings)
        context += "\n\n# previous_findings\n" + "\n".join(f.category for f in agent_findings)
    return findings


def hierarchical_review(code: str) -> dict[str, list[Finding]]:
    """
    Hierarchical 模式：Lead Agent 先分组，再把任务交给下级 Agent。
    适合大型仓库：例如 Backend Lead、Frontend Lead、Infra Lead 分别管自己的子团队。
    """
    backend_lead_children = [security_agent, performance_agent]
    quality_lead_children = [style_agent]
    return {
        "Backend Lead": [finding for agent in backend_lead_children for finding in agent.review(code)],
        "Quality Lead": [finding for agent in quality_lead_children for finding in agent.review(code)],
    }


def network_roundtable(code: str) -> list[str]:
    """
    Network 模式：Agent 之间可以互相评论。
    优点是讨论充分；缺点是容易循环、发散，需要限制轮次和终止条件。
    Day2 只演示一轮 roundtable，不做冲突仲裁。
    """
    first_pass = {
        agent.name: agent.review(code)
        for agent in agents
    }
    comments = [
        "Security Agent -> Performance Agent：参数化查询和鉴权校验优先级高，性能优化不能替代安全修复。",
        "Performance Agent -> Security Agent：批量查询订单时仍然要参数化 IN 查询，避免把性能修复变成注入点。",
        "Style Agent -> All：建议把安全校验、订单查询、响应序列化拆到不同层，降低后续修改冲突。",
    ]
    total_findings = sum(len(items) for items in first_pass.values())
    return [f"首轮共发现 {total_findings} 个问题。", *comments]


def print_findings(title: str, findings: list[Finding]) -> None:
    print(f"\n## {title}")
    for finding in findings:
        print(finding.to_markdown())


def main() -> None:
    print("=" * 72)
    print("Day2：Multi-Agent 编排模式与通信方式")
    print("=" * 72)

    print("\n待审查代码：\n")
    print(sample_code)

    print("\n\n# 1. Orchestrator-Worker + MessageBus + Blackboard")
    orchestrator = Orchestrator(agents)
    ow_findings = orchestrator.run_orchestrator_worker(sample_code)
    print_findings("Orchestrator 收到的 Worker 审查结果", ow_findings)

    print("\nBlackboard 当前内容：")
    for agent in agents:
        print(f"- {agent.name}: {len(orchestrator.blackboard.read_by_owner(agent.name))} finding(s)")

    print("\n\n# 2. Sequential Pipeline")
    seq_findings = sequential_pipeline(sample_code)
    print(f"按 Style -> Security -> Performance 串行执行，共 {len(seq_findings)} 个 finding。")
    print("适合强依赖流程；不适合本项目主审查流，因为三个维度本来可以并行。")

    print("\n\n# 3. Hierarchical Review")
    hierarchy = hierarchical_review(sample_code)
    for lead, findings in hierarchy.items():
        print(f"- {lead}: 管理 {len(findings)} 个 finding")
    print("适合大型仓库按领域分组；本项目初版可以先不引入多层 Lead。")

    print("\n\n# 4. Network Roundtable")
    for line in network_roundtable(sample_code):
        print(f"- {line}")
    print("适合需要讨论的场景；必须设置最大轮次和终止条件，避免 Agent 互相刷消息。")

    print("\n\n# Day2 结论")
    print("- 项目2 MVP 主流程采用 Orchestrator-Worker。")
    print("- Worker 之间默认隔离上下文，通过 message bus 和 blackboard 传递结构化结果。")
    print("- Day3 可以在 Orchestrator 层加入冲突检测与仲裁规则。")


if __name__ == "__main__":
    main()
