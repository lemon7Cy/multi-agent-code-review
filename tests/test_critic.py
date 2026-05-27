import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.critic import Critic
from code_review_multiagent.models import Finding, ReviewFile, ReviewRequest, Severity
from code_review_multiagent.orchestrator import ReviewOrchestrator


class CriticTests(unittest.TestCase):
    def test_suppresses_finding_outside_changed_lines_when_diff_exists(self):
        finding = Finding(
            agent="Security Agent",
            rule_id="SEC-SQL-INJECTION",
            category="SQL 注入风险",
            severity=Severity.HIGH,
            file_path="app/users.py",
            line_start=2,
            evidence='sql = "SELECT * FROM users WHERE id = " + user_id',
            impact="bad",
            recommendation="fix",
        )
        request = ReviewRequest(
            files=[ReviewFile(path="app/users.py", content="a\nb\nc\n")],
            diff="""diff --git a/app/users.py b/app/users.py
--- a/app/users.py
+++ b/app/users.py
@@ -3 +3 @@
-old
+new
""",
        )

        reviewed = Critic().review_findings(request, [finding])

        self.assertEqual(reviewed, [])

    def test_keeps_finding_on_changed_line_and_annotates_metadata(self):
        finding = Finding(
            agent="Security Agent",
            rule_id="SEC-SQL-INJECTION",
            category="SQL 注入风险",
            severity=Severity.HIGH,
            file_path="app/users.py",
            line_start=3,
            evidence='sql = "SELECT * FROM users WHERE id = " + user_id',
            impact="bad",
            recommendation="fix",
        )
        request = ReviewRequest(
            files=[ReviewFile(path="app/users.py", content="a\nb\nc\n")],
            diff="""diff --git a/app/users.py b/app/users.py
--- a/app/users.py
+++ b/app/users.py
@@ -3 +3 @@
-old
+new
""",
        )

        reviewed = Critic().review_findings(request, [finding])

        self.assertEqual(len(reviewed), 1)
        self.assertIn("Critic", reviewed[0].recommendation)

    def test_orchestrator_metadata_contains_critic_summary(self):
        content = """def get_user(db, request):
    user_id = request.args.get("id")
    sql = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(sql).fetchone()
"""
        diff = """diff --git a/app/users.py b/app/users.py
--- a/app/users.py
+++ b/app/users.py
@@ -3 +3 @@
-old
+    sql = "SELECT * FROM users WHERE id = " + user_id
"""
        report = ReviewOrchestrator().review(
            ReviewRequest(files=[ReviewFile(path="app/users.py", content=content)], diff=diff)
        )

        self.assertIn("critic", report.metadata)
        self.assertGreaterEqual(report.metadata["critic"]["kept_findings"], 1)


if __name__ == "__main__":
    unittest.main()
