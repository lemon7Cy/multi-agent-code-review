"""Agent 执行可观测性：记录每个 Agent 的执行时间、token 消耗和发现数量。

暴露 Prometheus 格式的 /metrics 接口数据。
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentExecution:
    agent_name: str
    start_time: float
    end_time: float = 0.0
    finding_count: int = 0
    tool_calls: int = 0
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


@dataclass
class ReviewMetrics:
    """单次审查的指标集合。"""
    review_id: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    agent_executions: list[AgentExecution] = field(default_factory=list)
    total_findings: int = 0
    file_count: int = 0

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


class MetricsCollector:
    """全局指标收集器。线程安全地收集 Agent 执行指标。"""

    def __init__(self) -> None:
        self._reviews: list[ReviewMetrics] = []
        self._agent_totals: dict[str, dict[str, float]] = defaultdict(
            lambda: {"executions": 0, "total_ms": 0, "total_findings": 0, "errors": 0, "tool_calls": 0}
        )

    def start_review(self, review_id: str, file_count: int) -> ReviewMetrics:
        metrics = ReviewMetrics(review_id=review_id, file_count=file_count)
        self._reviews.append(metrics)
        # 只保留最近 100 条
        if len(self._reviews) > 100:
            self._reviews = self._reviews[-100:]
        return metrics

    def record_agent(self, metrics: ReviewMetrics, agent_name: str, duration: float, finding_count: int, tool_calls: int = 0, error: str | None = None) -> None:
        execution = AgentExecution(
            agent_name=agent_name,
            start_time=metrics.start_time,
            end_time=metrics.start_time + duration,
            finding_count=finding_count,
            tool_calls=tool_calls,
            error=error,
        )
        metrics.agent_executions.append(execution)

        totals = self._agent_totals[agent_name]
        totals["executions"] += 1
        totals["total_ms"] += duration * 1000
        totals["total_findings"] += finding_count
        totals["tool_calls"] += tool_calls
        if error:
            totals["errors"] += 1

    def finish_review(self, metrics: ReviewMetrics, total_findings: int) -> None:
        metrics.end_time = time.time()
        metrics.total_findings = total_findings

    def get_prometheus_metrics(self) -> str:
        """输出 Prometheus 格式的指标文本。"""
        lines: list[str] = []
        lines.append("# HELP code_review_total Total number of code reviews")
        lines.append("# TYPE code_review_total counter")
        lines.append(f"code_review_total {len(self._reviews)}")
        lines.append("")

        lines.append("# HELP code_review_agent_executions_total Total agent executions by agent name")
        lines.append("# TYPE code_review_agent_executions_total counter")
        for agent, totals in self._agent_totals.items():
            safe_name = agent.replace(" ", "_").lower()
            lines.append(f'code_review_agent_executions_total{{agent="{safe_name}"}} {int(totals["executions"])}')
        lines.append("")

        lines.append("# HELP code_review_agent_duration_ms_total Total execution time in ms by agent")
        lines.append("# TYPE code_review_agent_duration_ms_total counter")
        for agent, totals in self._agent_totals.items():
            safe_name = agent.replace(" ", "_").lower()
            lines.append(f'code_review_agent_duration_ms_total{{agent="{safe_name}"}} {totals["total_ms"]:.1f}')
        lines.append("")

        lines.append("# HELP code_review_agent_findings_total Total findings by agent")
        lines.append("# TYPE code_review_agent_findings_total counter")
        for agent, totals in self._agent_totals.items():
            safe_name = agent.replace(" ", "_").lower()
            lines.append(f'code_review_agent_findings_total{{agent="{safe_name}"}} {int(totals["total_findings"])}')
        lines.append("")

        lines.append("# HELP code_review_agent_errors_total Total errors by agent")
        lines.append("# TYPE code_review_agent_errors_total counter")
        for agent, totals in self._agent_totals.items():
            safe_name = agent.replace(" ", "_").lower()
            lines.append(f'code_review_agent_errors_total{{agent="{safe_name}"}} {int(totals["errors"])}')
        lines.append("")

        lines.append("# HELP code_review_agent_tool_calls_total Total tool calls by agent")
        lines.append("# TYPE code_review_agent_tool_calls_total counter")
        for agent, totals in self._agent_totals.items():
            safe_name = agent.replace(" ", "_").lower()
            lines.append(f'code_review_agent_tool_calls_total{{agent="{safe_name}"}} {int(totals["tool_calls"])}')

        return "\n".join(lines) + "\n"

    def get_summary(self) -> dict[str, Any]:
        """返回结构化摘要（供 admin API 使用）。"""
        return {
            "total_reviews": len(self._reviews),
            "agents": {
                agent: {
                    "executions": int(totals["executions"]),
                    "avg_duration_ms": round(totals["total_ms"] / max(totals["executions"], 1), 1),
                    "total_findings": int(totals["total_findings"]),
                    "error_rate": round(totals["errors"] / max(totals["executions"], 1), 3),
                    "total_tool_calls": int(totals["tool_calls"]),
                }
                for agent, totals in self._agent_totals.items()
            },
            "recent_reviews": [
                {
                    "review_id": r.review_id,
                    "duration_ms": round(r.duration_ms, 1) if r.end_time else None,
                    "file_count": r.file_count,
                    "total_findings": r.total_findings,
                    "agent_count": len(r.agent_executions),
                }
                for r in self._reviews[-10:]
            ],
        }


# 全局单例
collector = MetricsCollector()
