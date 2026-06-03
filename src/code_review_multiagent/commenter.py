from __future__ import annotations

from typing import Any

from .models import SEVERITY_ZH, ReviewReport


def build_pr_comment_payload(report: ReviewReport, max_inline_comments: int = 20) -> dict[str, Any]:
    """Build GitHub-friendly PR comment payloads without performing network I/O."""
    inline_comments: list[dict[str, Any]] = []
    for finding in report.findings:
        if finding.line_start is None:
            continue
        inline_comments.append(
            {
                "path": finding.file_path,
                "line": finding.line_start,
                "body": _inline_comment_body(finding),
            }
        )
        if len(inline_comments) >= max_inline_comments:
            break

    return {
        "issue_comment": {"body": report.markdown},
        "review": {
            "event": "COMMENT",
            "body": _review_body(report, len(inline_comments)),
            "comments": inline_comments,
        },
    }


def _inline_comment_body(finding) -> str:
    severity = SEVERITY_ZH.get(finding.severity, finding.severity.value)
    return "\n".join(
        [
            f"**{severity}：{finding.category}**",
            f"规则：`{finding.rule_id}`",
            f"证据：{finding.evidence}",
            f"建议：{finding.recommendation}",
        ]
    )


def _review_body(report: ReviewReport, inline_count: int) -> str:
    return (
        f"Multi-Agent Code Review 完成：共发现 {report.summary.total_findings} 个问题，"
        f"已生成 {inline_count} 条行级评论。完整报告见 PR 总评论。"
    )
