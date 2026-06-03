from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from typing import Callable

from .agents import build_default_agents
from .agents.base import ReviewAgent
from .agents.llm_agents import build_llm_agents
from .agents.llm_tooluse_agent import build_tooluse_agents
from .blackboard import Blackboard
from .critic import Critic
from .message_bus import AgentMessage, MessageBus
from .metrics import collector as metrics_collector
from .models import (
    SEVERITY_RANK,
    SEVERITY_ZH,
    AgentReview,
    Conflict,
    Finding,
    ReviewEvent,
    ReviewReport,
    ReviewRequest,
    ReviewSummary,
    Severity,
)
from .review_store import StoreUnavailableError, list_enabled_agent_configs


@dataclass
class ReviewRun:
    report: ReviewReport
    events: list[ReviewEvent]


class ReviewOrchestrator:
    """Coordinates specialist agents and turns their outputs into a final report."""

    def __init__(self, agents: list[ReviewAgent] | None = None) -> None:
        self.agents = agents or build_default_agents()

    def review(self, request: ReviewRequest) -> ReviewReport:
        return self.review_with_events(request).report

    def review_with_events(
        self, request: ReviewRequest, on_event: Callable[[ReviewEvent], None] | None = None
    ) -> ReviewRun:
        active_agents = self._select_agents()
        bus = MessageBus()
        blackboard = Blackboard()
        events: list[ReviewEvent] = []
        review_metrics = metrics_collector.start_review(
            review_id=datetime.now().strftime("%Y%m%d%H%M%S"),
            file_count=len(request.files),
        )

        def emit(event: ReviewEvent) -> None:
            events.append(event)
            if on_event:
                on_event(event)

        emit(
            ReviewEvent(
                type="start", stage="接收任务", message=f"已收到 {len(request.files)} 个文件，开始多 Agent 协作审查。"
            )
        )
        emit(
            ReviewEvent(
                type="progress",
                stage="选择身份",
                message=f"本次启用 {len(active_agents)} 个 Agent 身份。",
                metadata={"agent_count": len(active_agents)},
            )
        )

        for agent in active_agents:
            emit(
                ReviewEvent(
                    type="agent_trace",
                    agent=agent.name,
                    stage="领取任务",
                    message=f"{agent.name} 已领取任务。职责：{agent.role}",
                )
            )
            bus.publish(
                AgentMessage(
                    sender="Orchestrator",
                    receiver=agent.name,
                    topic="review.request",
                    payload={"repo": request.repo, "pr_number": request.pr_number, "files": len(request.files)},
                )
            )

        with ThreadPoolExecutor(max_workers=max(1, len(active_agents))) as executor:
            future_to_agent = {
                executor.submit(self._timed_review, agent, request.files): agent for agent in active_agents
            }
            for future in as_completed(future_to_agent):
                agent = future_to_agent[future]
                emit(
                    ReviewEvent(
                        type="agent_trace",
                        agent=agent.name,
                        stage="分析中",
                        message=f"{agent.name} 正在结合自身职责检查证据、影响和修复建议。",
                    )
                )
                review, duration, error = future.result()
                if error:
                    metrics_collector.record_agent(review_metrics, agent.name, duration, 0, error=error)
                    emit(
                        ReviewEvent(
                            type="agent_error",
                            agent=agent.name,
                            stage="异常",
                            message=f"{agent.name} 执行出错: {error}",
                        )
                    )
                    continue
                review.findings = [self._calibrate_finding(finding) for finding in review.findings]
                metrics_collector.record_agent(review_metrics, agent.name, duration, len(review.findings))
                blackboard.write_review(review)
                for event in self._events_for_agent_review(review):
                    emit(event)
                bus.publish(
                    AgentMessage(
                        sender=agent.name,
                        receiver="Orchestrator",
                        topic="review.done",
                        payload=review,
                    )
                )

        # Consume done messages to model the production flow; blackboard remains source of truth.
        bus.consume("Orchestrator", topic="review.done")
        agent_reviews = blackboard.read_all_reviews()
        findings = self._deduplicate(blackboard.read_all_findings())
        critic_result = Critic().review(request, findings)
        findings = self._sort_findings(critic_result.findings)
        conflicts = self._detect_and_arbitrate(findings)
        summary = self._build_summary(findings)
        markdown = self._render_markdown(request, summary, findings, conflicts, agent_reviews)
        emit(
            ReviewEvent(
                type="summary",
                stage="汇总仲裁",
                message=f"Orchestrator 已合并 {len(agent_reviews)} 个身份输出，去重后保留 {summary.total_findings} 个问题。",
                metadata={"total_findings": summary.total_findings, "by_severity": summary.by_severity},
            )
        )

        report = ReviewReport(
            repo=request.repo,
            pr_number=request.pr_number,
            title=request.title,
            summary=summary,
            findings=findings,
            conflicts=conflicts,
            agent_reviews=agent_reviews,
            markdown=markdown,
            metadata={
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "mode": "agent",
                "agent_count": len(active_agents),
                "llm_enabled": any(review.agent.startswith("LLM ") for review in agent_reviews),
                "file_count": len(request.files),
                "critic": critic_result.metadata,
            },
        )
        metrics_collector.finish_review(review_metrics, summary.total_findings)
        report.metadata["events"] = [event.model_dump(mode="json") for event in events]
        report.metadata["metrics"] = {
            "duration_ms": round(review_metrics.duration_ms, 1),
            "agents": [
                {"name": ex.agent_name, "duration_ms": round(ex.duration_ms, 1), "findings": ex.finding_count}
                for ex in review_metrics.agent_executions
            ],
        }
        return ReviewRun(report=report, events=events)

    @staticmethod
    def _timed_review(agent, files) -> tuple[AgentReview | None, float, str | None]:
        """执行 agent.review 并计时，捕获异常。"""
        start = time.time()
        try:
            review = agent.review(files)
            return review, time.time() - start, None
        except Exception as e:
            return None, time.time() - start, str(e)

    def _select_agents(self) -> list[ReviewAgent]:
        try:
            configs = list_enabled_agent_configs()
        except StoreUnavailableError:
            configs = []
        rule_agents = build_default_agents(configs) if configs else self.agents
        # 优先使用 Tool Use Agent（多轮推理），fallback 到旧版单次调用
        tooluse_agents = build_tooluse_agents(configs) if configs else build_tooluse_agents()
        if tooluse_agents:
            return [*rule_agents, *tooluse_agents]
        llm_agents = build_llm_agents(configs) if configs else build_llm_agents()
        return [*rule_agents, *llm_agents] if llm_agents else rule_agents

    def _events_for_agent_review(self, review: AgentReview) -> list[ReviewEvent]:
        events = [
            ReviewEvent(
                type="agent_done",
                agent=review.agent,
                stage="输出结论",
                message=f"{review.agent} 输出 {len(review.findings)} 个问题。",
                metadata={"finding_count": len(review.findings), "role": review.role},
            )
        ]
        for finding in self._sort_findings(review.findings)[:5]:
            location = finding.file_path
            if finding.line_start:
                location += f":{finding.line_start}"
            events.append(
                ReviewEvent(
                    type="agent_finding",
                    agent=review.agent,
                    stage=finding.category,
                    message=f"{SEVERITY_ZH[finding.severity]}：{finding.recommendation}",
                    metadata={
                        "severity": finding.severity.value,
                        "file_path": finding.file_path,
                        "line_start": finding.line_start,
                        "location": location,
                        "rule_id": finding.rule_id,
                    },
                )
            )
        return events

    def _calibrate_finding(self, finding: Finding) -> Finding:
        rule = finding.rule_id.upper()
        category = finding.category
        agent = finding.agent

        if rule == "SEC-MISSING-AUTHZ" and finding.severity == Severity.MEDIUM:
            finding.severity = Severity.LOW
            finding.impact = f"{finding.impact} 该规则为静态线索，需要结合具体接口鉴权逻辑复核。"
            return finding

        if agent.startswith("LLM Style") and finding.severity in {Severity.CRITICAL, Severity.HIGH}:
            finding.severity = Severity.MEDIUM
            return finding

        if agent.startswith("LLM Performance") and finding.severity == Severity.HIGH:
            finding.severity = Severity.MEDIUM
            return finding

        critical_security_rules = {
            "SEC-PLAINTEXT-PASSWORD",
            "SEC-PRIVILEGE-ESCALATION",
            "SEC-MISSING-ROLE-CHECK",
        }
        if rule in critical_security_rules:
            finding.severity = Severity.CRITICAL
            return finding

        if "敏感信息" in category and finding.severity == Severity.CRITICAL:
            finding.severity = Severity.HIGH

        return finding

    def _deduplicate(self, findings: list[Finding]) -> list[Finding]:
        merged: dict[str, Finding] = {}
        for finding in findings:
            fp = finding.fingerprint or finding.stable_fingerprint()
            finding.fingerprint = fp
            existing = merged.get(fp)
            if not existing or SEVERITY_RANK[finding.severity] > SEVERITY_RANK[existing.severity]:
                merged[fp] = finding
        return list(merged.values())

    def _sort_findings(self, findings: list[Finding]) -> list[Finding]:
        return sorted(
            findings,
            key=lambda item: (
                -SEVERITY_RANK[item.severity],
                item.file_path,
                item.line_start or 0,
                item.rule_id,
            ),
        )

    def _build_summary(self, findings: list[Finding]) -> ReviewSummary:
        by_severity = Counter(f.severity.value for f in findings)
        by_agent = Counter(f.agent for f in findings)
        top = None
        if findings:
            top_finding = findings[0]
            top = f"{SEVERITY_ZH[top_finding.severity]}：{top_finding.category}，位置 {top_finding.file_path}"
        return ReviewSummary(
            total_findings=len(findings),
            by_severity=dict(by_severity),
            by_agent=dict(by_agent),
            top_priority=top,
        )

    def _detect_and_arbitrate(self, findings: list[Finding]) -> list[Conflict]:
        conflicts: list[Conflict] = []
        has_sql = [f for f in findings if f.rule_id == "SEC-SQL-INJECTION"]
        has_n1 = [f for f in findings if f.rule_id == "PERF-N-PLUS-ONE"]
        if has_sql and has_n1:
            related = [(f.fingerprint or f.stable_fingerprint()) for f in [*has_sql, *has_n1]]
            conflicts.append(
                Conflict(
                    conflict_id=self._conflict_id("sql-vs-batch", related),
                    title="批量查询优化必须服从 SQL 注入修复约束",
                    involved_agents=["Security Agent", "Performance Agent"],
                    related_fingerprints=related,
                    risk="如果只追求批量查询性能，可能把多个 id 拼成 IN 字符串，重新引入 SQL 注入。",
                    decision="先落地参数化查询与权限校验，再做批量查询；批量 IN 条件也必须使用绑定参数。",
                    rationale="安全问题优先级高于性能优化；性能方案不能破坏安全边界。",
                    priority_order=["Security", "Correctness", "Performance", "Style"],
                )
            )
        return conflicts

    def _conflict_id(self, title: str, related: list[str]) -> str:
        return sha1((title + "|" + "|".join(sorted(related))).encode("utf-8")).hexdigest()[:12]

    def _render_markdown(
        self,
        request: ReviewRequest,
        summary: ReviewSummary,
        findings: list[Finding],
        conflicts: list[Conflict],
        agent_reviews: list[AgentReview],
    ) -> str:
        title = request.title or "代码审查报告"
        lines = [f"# {title}", ""]
        if request.repo:
            lines.append(f"- 项目：`{request.repo}`")
        if request.pr_number:
            lines.append(f"- PR 编号：`#{request.pr_number}`")
        lines.extend(
            [
                f"- 发现问题总数：**{summary.total_findings}**",
                f"- 优先处理：{summary.top_priority or '暂无'}",
                "",
                "## 一、风险概览",
            ]
        )
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            count = summary.by_severity.get(sev.value, 0)
            if count:
                lines.append(f"- {SEVERITY_ZH[sev]}：{count} 个")

        lines.append("\n## 二、详细问题")
        if not findings:
            lines.append("暂未发现明显问题。")
        for finding in findings:
            location = finding.file_path
            if finding.line_start:
                location += f":{finding.line_start}"
            lines.extend(
                [
                    f"### {SEVERITY_ZH[finding.severity]}：{finding.category}",
                    f"- 审查角色：{_agent_name_zh(finding.agent)}",
                    f"- 位置：`{location}`",
                    f"- 证据：{finding.evidence}",
                    f"- 影响：{finding.impact}",
                    f"- 建议：{finding.recommendation}",
                    f"- 内部规则：`{finding.rule_id}`",
                    "",
                ]
            )

        lines.append("## 三、每个身份的审查建议")
        for review in sorted(agent_reviews, key=lambda r: r.agent):
            lines.extend(
                [
                    f"### {_agent_name_zh(review.agent)}",
                    f"- 身份职责：{review.role}",
                    f"- 输出问题：{len(review.findings)} 个",
                ]
            )
            if review.notes:
                lines.append(f"- 补充说明：{'；'.join(review.notes)}")
            if not review.findings:
                lines.extend(["- 建议：该身份暂未发现明确问题。", ""])
                continue
            lines.append("")
            for idx, finding in enumerate(
                self._sort_findings(review.findings),
                start=1,
            ):
                location = finding.file_path
                if finding.line_start:
                    location += f":{finding.line_start}"
                lines.extend(
                    [
                        f"{idx}. **{SEVERITY_ZH[finding.severity]}：{finding.category}**",
                        f"   - 位置：`{location}`",
                        f"   - 证据：{finding.evidence}",
                        f"   - 影响：{finding.impact}",
                        f"   - 建议：{finding.recommendation}",
                        f"   - 内部规则：`{finding.rule_id}`",
                        "",
                    ]
                )

        lines.append("## 四、冲突仲裁")
        if not conflicts:
            lines.append("暂未发现需要仲裁的冲突。")
        for conflict in conflicts:
            lines.extend(
                [
                    f"### {conflict.title}",
                    f"- 涉及角色：{', '.join(_agent_name_zh(agent) for agent in conflict.involved_agents)}",
                    f"- 风险：{conflict.risk}",
                    f"- 裁决：{conflict.decision}",
                    f"- 原因：{conflict.rationale}",
                    "",
                ]
            )

        lines.append("## 五、审查覆盖范围")
        for review in sorted(agent_reviews, key=lambda r: r.agent):
            lines.append(f"- {_agent_name_zh(review.agent)}：发现 {len(review.findings)} 个问题。{review.role}")
        return "\n".join(lines).strip() + "\n"


def _agent_name_zh(agent: str) -> str:
    mapping = {
        "Security Agent": "安全审查 Agent",
        "Performance Agent": "性能审查 Agent",
        "Style Agent": "可维护性审查 Agent",
        "LLM Security Agent": "模型安全审查 Agent",
        "LLM Performance Agent": "模型性能审查 Agent",
        "LLM Style Agent": "模型可维护性审查 Agent",
    }
    return mapping.get(agent, agent)
