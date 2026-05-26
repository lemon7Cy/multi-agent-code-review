import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.models import ReviewFile, ReviewRequest
from code_review_multiagent.orchestrator import ReviewOrchestrator


SAMPLE = '''def get_user_profile(db, request):
    user_id = request.args.get("id")
    sql = "SELECT * FROM users WHERE id = " + user_id
    user = db.execute(sql).fetchone()

    orders = []
    for order_id in user.order_ids:
        orders.append(db.execute(f"SELECT * FROM orders WHERE id = {order_id}").fetchone())

    return {"debug_token": "demo-api-key-placeholder", "orders": orders}
'''


class OrchestratorTests(unittest.TestCase):
    def test_orchestrator_finds_core_issues(self):
        report = ReviewOrchestrator().review(
            ReviewRequest(repo="test/repo", files=[ReviewFile(path="app/users.py", content=SAMPLE)])
        )
        rule_ids = {finding.rule_id for finding in report.findings}
        self.assertIn("SEC-SQL-INJECTION", rule_ids)
        self.assertIn("SEC-HARDCODED-SECRET", rule_ids)
        self.assertIn("PERF-N-PLUS-ONE", rule_ids)
        self.assertGreaterEqual(report.summary.total_findings, 5)
        self.assertTrue(report.conflicts, "SQL injection + batch query should produce an arbitration note")
        self.assertIn("Security Agent", report.summary.by_agent)
        self.assertIn("## 三、每个身份的审查建议", report.markdown)
        self.assertIn("### 安全审查 Agent", report.markdown)
        self.assertIn("### 性能审查 Agent", report.markdown)
        self.assertIn("### 可维护性审查 Agent", report.markdown)

    def test_clean_code_has_no_high_findings(self):
        clean = '''def get_user(db, current_user, user_id):
    if current_user.id != user_id:
        raise PermissionError()
    return db.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
'''
        report = ReviewOrchestrator().review(
            ReviewRequest(repo="test/repo", files=[ReviewFile(path="app/users.py", content=clean)])
        )
        self.assertTrue(all(f.severity.value != "High" for f in report.findings))


if __name__ == "__main__":
    unittest.main()
