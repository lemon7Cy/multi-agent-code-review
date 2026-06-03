import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.commenter import build_pr_comment_payload
from code_review_multiagent.models import Finding, ReviewReport, ReviewSummary, Severity


class CommenterTests(unittest.TestCase):
    def test_builds_issue_comment_and_inline_review_comments(self):
        finding = Finding(
            agent="Security Agent",
            rule_id="SEC-SQL-INJECTION",
            category="SQL 注入风险",
            severity=Severity.HIGH,
            file_path="app/users.py",
            line_start=12,
            evidence="sql concat",
            impact="bad",
            recommendation="use params",
        )
        report = ReviewReport(
            repo="demo/repo",
            pr_number=5,
            title="demo",
            summary=ReviewSummary(total_findings=1, by_severity={"High": 1}, by_agent={"Security Agent": 1}),
            findings=[finding],
            markdown="# report",
        )

        payload = build_pr_comment_payload(report)

        self.assertEqual(payload["issue_comment"]["body"], "# report")
        self.assertEqual(payload["review"]["event"], "COMMENT")
        self.assertEqual(payload["review"]["comments"][0]["path"], "app/users.py")
        self.assertEqual(payload["review"]["comments"][0]["line"], 12)
        self.assertIn("SEC-SQL-INJECTION", payload["review"]["comments"][0]["body"])

    def test_limits_inline_comments_and_skips_file_level_findings(self):
        findings = [
            Finding(
                agent="Test Agent",
                rule_id=f"R-{idx}",
                category="cat",
                severity=Severity.LOW,
                file_path="app.py",
                line_start=idx,
                evidence="e",
                impact="i",
                recommendation="r",
            )
            for idx in range(1, 8)
        ]
        findings.append(
            Finding(
                agent="Test Agent",
                rule_id="FILE-LEVEL",
                category="cat",
                severity=Severity.LOW,
                file_path="app.py",
                evidence="e",
                impact="i",
                recommendation="r",
            )
        )
        report = ReviewReport(
            summary=ReviewSummary(
                total_findings=len(findings), by_severity={"Low": len(findings)}, by_agent={"Test Agent": len(findings)}
            ),
            findings=findings,
            markdown="body",
        )

        payload = build_pr_comment_payload(report, max_inline_comments=3)

        self.assertEqual(len(payload["review"]["comments"]), 3)
        self.assertTrue(all("line" in item for item in payload["review"]["comments"]))


if __name__ == "__main__":
    unittest.main()
