import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import HTTPException  # noqa: E402

from code_review_multiagent.app import _store_unavailable_detail, safe_persist_report  # noqa: E402
from code_review_multiagent.models import ReviewFile, ReviewRequest  # noqa: E402
from code_review_multiagent.orchestrator import ReviewOrchestrator  # noqa: E402


SAMPLE = """def get_user_profile(db, request):
    user_id = request.args.get("id")
    sql = "SELECT * FROM users WHERE id = " + user_id
    user = db.execute(sql).fetchone()
    return {"debug_token": "demo-api-key-placeholder"}
"""


class StoreUnavailableFallbackTests(unittest.TestCase):
    def test_store_error_message_is_sanitized_for_browser_users(self):
        raw = "mysql+pymysql://root:secret@localhost:3306/code_review_multiagent (pymysql.err.OperationalError)"
        detail = _store_unavailable_detail(raw)
        self.assertIn("审查记录服务暂不可用", detail)
        self.assertIn("项目审查仍可继续", detail)
        self.assertNotIn("secret", detail)
        self.assertNotIn("mysql+pymysql", detail)
        self.assertNotIn("root", detail)

    def test_safe_persist_marks_report_unsaved_when_store_is_unavailable(self):
        run = ReviewOrchestrator().review_with_events(
            ReviewRequest(
                repo="demo/repo",
                title="demo",
                files=[ReviewFile(path="app/users.py", content=SAMPLE, language="python")],
            )
        )

        def failing_save(report, events):
            raise HTTPException(status_code=503, detail="raw database password secret")

        persisted = safe_persist_report(run.report, run.events, persist_func=failing_save)

        self.assertFalse(persisted)
        self.assertEqual(run.report.metadata["record_status"], "unavailable")
        self.assertIn("审查记录服务暂不可用", run.report.metadata["record_warning"])
        self.assertNotIn("secret", run.report.metadata["record_warning"])


if __name__ == "__main__":
    unittest.main()
