from __future__ import annotations

from .models import AgentReview, Finding


class Blackboard:
    """Shared artifact store for multi-agent review results."""

    def __init__(self) -> None:
        self._reviews: dict[str, AgentReview] = {}

    def write_review(self, review: AgentReview) -> None:
        self._reviews[review.agent] = review

    def read_review(self, agent: str) -> AgentReview | None:
        return self._reviews.get(agent)

    def read_all_reviews(self) -> list[AgentReview]:
        return list(self._reviews.values())

    def read_all_findings(self) -> list[Finding]:
        findings: list[Finding] = []
        for review in self._reviews.values():
            findings.extend(review.findings)
        return findings
