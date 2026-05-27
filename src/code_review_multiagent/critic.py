from __future__ import annotations

from dataclasses import dataclass, field

from .models import Finding, ReviewRequest
from .review_context import build_review_context


@dataclass
class CriticResult:
    findings: list[Finding]
    suppressed_findings: list[Finding] = field(default_factory=list)

    @property
    def metadata(self) -> dict[str, int]:
        return {
            "kept_findings": len(self.findings),
            "suppressed_findings": len(self.suppressed_findings),
        }


class Critic:
    """Lightweight critic layer for PR-aware validation of agent findings."""

    def review(self, request: ReviewRequest, findings: list[Finding]) -> CriticResult:
        if not request.diff:
            return CriticResult(findings=list(findings))

        context = build_review_context(request)
        changed_paths = context.changed_file_paths()
        kept: list[Finding] = []
        suppressed: list[Finding] = []

        for finding in findings:
            file_context = context.files.get(finding.file_path)
            if not file_context or finding.file_path not in changed_paths:
                suppressed.append(finding)
                continue
            if finding.line_start and not context.is_line_changed(finding.file_path, finding.line_start):
                suppressed.append(finding)
                continue
            finding.recommendation = f"{finding.recommendation}（Critic：已确认问题位于本次 PR 变更范围内。）"
            kept.append(finding)

        return CriticResult(findings=kept, suppressed_findings=suppressed)

    def review_findings(self, request: ReviewRequest, findings: list[Finding]) -> list[Finding]:
        return self.review(request, findings).findings
