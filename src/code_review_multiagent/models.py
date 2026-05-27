from __future__ import annotations

from enum import Enum
from hashlib import sha1
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


SEVERITY_RANK = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

SEVERITY_ZH = {
    Severity.CRITICAL: "严重",
    Severity.HIGH: "高风险",
    Severity.MEDIUM: "中风险",
    Severity.LOW: "低风险",
    Severity.INFO: "提示",
}


class ReviewFile(BaseModel):
    path: str = Field(..., examples=["app/users.py"])
    content: str
    language: str | None = Field(default=None, examples=["python"])


class ReviewRequest(BaseModel):
    repo: str | None = Field(default=None, examples=["demo/repo"])
    pr_number: int | None = None
    title: str | None = None
    files: list[ReviewFile]
    diff: str | None = Field(default=None, description="Optional unified diff for PR-aware review.")


class ReviewEvent(BaseModel):
    type: str
    message: str
    agent: str | None = None
    stage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    agent: str
    rule_id: str
    category: str
    severity: Severity
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    evidence: str
    impact: str
    recommendation: str
    confidence: float = Field(default=0.8, ge=0, le=1)
    fingerprint: str | None = None

    def stable_fingerprint(self) -> str:
        raw = "|".join(
            [
                self.rule_id,
                self.file_path,
                str(self.line_start or ""),
                self.evidence[:120],
            ]
        )
        return sha1(raw.encode("utf-8")).hexdigest()[:16]


class AgentReview(BaseModel):
    agent: str
    role: str
    findings: list[Finding]
    notes: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    conflict_id: str
    title: str
    involved_agents: list[str]
    related_fingerprints: list[str]
    risk: str
    decision: str
    rationale: str
    priority_order: list[str]


class ReviewSummary(BaseModel):
    total_findings: int
    by_severity: dict[str, int]
    by_agent: dict[str, int]
    top_priority: str | None = None


class ReviewReport(BaseModel):
    repo: str | None = None
    pr_number: int | None = None
    title: str | None = None
    summary: ReviewSummary
    findings: list[Finding]
    conflicts: list[Conflict] = Field(default_factory=list)
    agent_reviews: list[AgentReview] = Field(default_factory=list)
    markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConfigRead(BaseModel):
    id: int
    agent_key: str
    name: str
    role: str
    kind: str
    enabled: bool
    tools: list[str]
    system_prompt: str | None = None
    created_at: str
    updated_at: str


class AgentConfigUpdate(BaseModel):
    name: str
    role: str
    enabled: bool = True
    tools: list[str] = Field(default_factory=list)
    system_prompt: str | None = None


class AgentConfigCreate(AgentConfigUpdate):
    agent_key: str
    kind: str = Field(default="llm", pattern="^(rule|llm)$")
