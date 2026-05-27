import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from code_review_multiagent.app import app
from code_review_multiagent.models import ReviewReport, ReviewSummary


class AsyncReviewJobsTests(unittest.TestCase):
    def test_async_review_job_lifecycle(self):
        client = TestClient(app)
        report = ReviewReport(
            repo="demo/repo",
            summary=ReviewSummary(total_findings=0, by_severity={}, by_agent={}),
            findings=[],
            markdown="ok",
        )

        class FakeOrchestrator:
            def review_with_events(self, request, on_event=None):
                if on_event:
                    from code_review_multiagent.models import ReviewEvent
                    on_event(ReviewEvent(type="start", message="started"))
                from code_review_multiagent.orchestrator import ReviewRun
                return ReviewRun(report=report, events=[])

        with patch("code_review_multiagent.app.orchestrator", FakeOrchestrator()), patch("code_review_multiagent.app._persist_report", lambda report, events=None: None):
            created = client.post(
                "/api/reviews/jobs",
                json={"repo": "demo/repo", "files": [{"path": "app.py", "content": "print(1)"}]},
            )
            self.assertEqual(created.status_code, 202, created.text)
            job_id = created.json()["job_id"]

            for _ in range(20):
                status = client.get(f"/api/reviews/jobs/{job_id}")
                self.assertEqual(status.status_code, 200, status.text)
                if status.json()["status"] == "completed":
                    break
            else:
                self.fail("job did not complete")

            payload = status.json()
            self.assertEqual(payload["report"]["markdown"], "ok")
            self.assertGreaterEqual(len(payload["events"]), 1)

    def test_unknown_job_returns_404(self):
        client = TestClient(app)
        response = client.get("/api/reviews/jobs/not-found")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
