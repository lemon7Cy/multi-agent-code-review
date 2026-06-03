import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from code_review_multiagent.app import app
from code_review_multiagent.review_store import StoreUnavailableError, init_store

SAMPLE = """def get_user_profile(db, request):
    user_id = request.args.get("id")
    sql = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(sql).fetchone()
"""


def mysql_available() -> bool:
    try:
        init_store()
        return True
    except StoreUnavailableError:
        return False


@unittest.skipUnless(mysql_available(), "MySQL review store is not available")
class ReviewHistoryMySQLTests(unittest.TestCase):
    def test_review_is_persisted_and_can_be_deleted(self):
        client = TestClient(app)
        payload = {
            "repo": "test/history",
            "title": "history api test",
            "files": [{"path": "app/users.py", "content": SAMPLE, "language": "python"}],
        }

        created = client.post("/api/reviews", json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        report = created.json()
        record_id = report["metadata"].get("record_id")
        self.assertIsInstance(record_id, int)

        detail = client.get(f"/api/reviews/history/{record_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["metadata"]["record_id"], record_id)

        events = client.get(f"/api/reviews/history/{record_id}/events")
        self.assertEqual(events.status_code, 200, events.text)
        event_items = events.json()["items"]
        self.assertTrue(any(item["type"] == "agent_trace" for item in event_items))
        self.assertTrue(any(item["type"] == "summary" for item in event_items))

        history = client.get("/api/reviews/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertTrue(any(item["id"] == record_id for item in history.json()["items"]))

        deleted = client.delete(f"/api/reviews/history/{record_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)

        missing = client.get(f"/api/reviews/history/{record_id}")
        self.assertEqual(missing.status_code, 404)

        missing_events = client.get(f"/api/reviews/history/{record_id}/events")
        self.assertEqual(missing_events.status_code, 404)

    def test_agent_configs_can_be_managed(self):
        client = TestClient(app)

        configs = client.get("/api/agents")
        self.assertEqual(configs.status_code, 200, configs.text)
        security = next(item for item in configs.json()["items"] if item["agent_key"] == "security")

        payload = {
            "name": security["name"],
            "role": security["role"],
            "enabled": security["enabled"],
            "tools": ["secret_scanner"],
            "system_prompt": security.get("system_prompt"),
        }
        updated = client.put(f"/api/agents/{security['id']}", json=payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["tools"], ["secret_scanner"])

        restore = client.put(
            f"/api/agents/{security['id']}",
            json={
                "name": security["name"],
                "role": security["role"],
                "enabled": security["enabled"],
                "tools": security["tools"],
                "system_prompt": security.get("system_prompt"),
            },
        )
        self.assertEqual(restore.status_code, 200, restore.text)

    def test_agent_configs_can_be_created_and_deleted(self):
        client = TestClient(app)
        key = "test_llm_agent_crud"

        existing = client.get("/api/agents")
        self.assertEqual(existing.status_code, 200, existing.text)
        for item in existing.json()["items"]:
            if item["agent_key"] == key:
                client.delete(f"/api/agents/{item['id']}")

        created = client.post(
            "/api/agents",
            json={
                "agent_key": key,
                "name": "Test LLM Agent",
                "role": "Only used by CRUD tests.",
                "kind": "llm",
                "enabled": True,
                "tools": ["test_review_tool"],
                "system_prompt": "Only review test fixtures.",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        agent = created.json()
        self.assertEqual(agent["agent_key"], key)
        self.assertEqual(agent["kind"], "llm")
        self.assertEqual(agent["tools"], ["test_review_tool"])

        listed = client.get("/api/agents")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(any(item["agent_key"] == key for item in listed.json()["items"]))

        deleted = client.delete(f"/api/agents/{agent['id']}")
        self.assertEqual(deleted.status_code, 200, deleted.text)

        listed_after_delete = client.get("/api/agents")
        self.assertFalse(any(item["agent_key"] == key for item in listed_after_delete.json()["items"]))


if __name__ == "__main__":
    unittest.main()
