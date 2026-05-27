import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.models import ReviewFile, ReviewRequest
from code_review_multiagent.review_context import build_review_context
from code_review_multiagent.planner import ReviewPlanner


class ReviewPlannerTests(unittest.TestCase):
    def test_planner_creates_role_tasks_and_risk_hints_for_changed_code(self):
        diff = '''diff --git a/src/users.py b/src/users.py
--- a/src/users.py
+++ b/src/users.py
@@ -1,2 +1,5 @@
 def get_user(db, user_id):
+    sql = "SELECT * FROM users WHERE id = " + user_id
+    for order_id in user.order_ids:
+        db.execute(f"SELECT * FROM orders WHERE id = {order_id}")
     return db.execute(sql)
'''
        request = ReviewRequest(
            repo="demo/repo",
            files=[ReviewFile(path="src/users.py", content='''def get_user(db, user_id):
    sql = "SELECT * FROM users WHERE id = " + user_id
    for order_id in user.order_ids:
        db.execute(f"SELECT * FROM orders WHERE id = {order_id}")
    return db.execute(sql)
''')],
            diff=diff,
        )
        context = build_review_context(request)

        tasks = ReviewPlanner().plan(context)
        by_role = {task.agent_role: task for task in tasks}

        self.assertIn("security", by_role)
        self.assertIn("performance", by_role)
        self.assertIn("maintainability", by_role)
        self.assertIn("test_coverage", by_role)
        self.assertIn("sql_injection_risk", by_role["security"].risk_hints)
        self.assertIn("n_plus_one_risk", by_role["performance"].risk_hints)
        self.assertIn("missing_test_risk", by_role["test_coverage"].risk_hints)

    def test_planner_does_not_create_test_coverage_task_when_tests_changed(self):
        request = ReviewRequest(
            repo="demo/repo",
            files=[
                ReviewFile(path="src/users.py", content="def get_user():\n    return 1\n"),
                ReviewFile(path="tests/test_users.py", content="def test_get_user():\n    assert True\n"),
            ],
            diff='''diff --git a/src/users.py b/src/users.py
--- a/src/users.py
+++ b/src/users.py
@@ -1 +1,2 @@
 def get_user():
+    return 1
diff --git a/tests/test_users.py b/tests/test_users.py
--- a/tests/test_users.py
+++ b/tests/test_users.py
@@ -0,0 +1,2 @@
+def test_get_user():
+    assert True
''',
        )

        tasks = ReviewPlanner().plan(build_review_context(request))

        self.assertNotIn("test_coverage", {task.agent_role for task in tasks})

    def test_planner_skips_non_code_files(self):
        request = ReviewRequest(
            repo="demo/repo",
            files=[ReviewFile(path="README.md", content="# docs\n")],
            diff='''diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # docs
+more docs
''',
        )

        tasks = ReviewPlanner().plan(build_review_context(request))

        self.assertEqual(tasks, [])


if __name__ == "__main__":
    unittest.main()
