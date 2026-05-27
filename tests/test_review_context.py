import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.models import ReviewFile, ReviewRequest
from code_review_multiagent.review_context import build_review_context


class ReviewContextTests(unittest.TestCase):
    def test_build_context_maps_diff_changed_lines_to_review_files(self):
        diff = '''diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 def handler():
-    return "ok"
+    token = "demo"
+    return token
'''
        request = ReviewRequest(
            repo="demo/repo",
            files=[ReviewFile(path="src/app.py", content='def handler():\n    token = "demo"\n    return token\n')],
            diff=diff,
        )

        context = build_review_context(request)
        file_context = context.files["src/app.py"]

        self.assertTrue(file_context.is_changed)
        self.assertEqual(file_context.changed_new_lines, {2, 3})
        self.assertEqual(file_context.changed_old_lines, {2})
        self.assertTrue(context.is_line_changed("src/app.py", 2))
        self.assertFalse(context.is_line_changed("src/app.py", 1))

    def test_build_context_without_diff_keeps_files_reviewable(self):
        request = ReviewRequest(
            repo="demo/repo",
            files=[ReviewFile(path="src/app.py", content="print('hello')\n")],
        )

        context = build_review_context(request)
        file_context = context.files["src/app.py"]

        self.assertTrue(file_context.is_reviewable)
        self.assertFalse(file_context.is_changed)
        self.assertEqual(file_context.changed_new_lines, set())

    def test_build_context_exposes_changed_test_files(self):
        diff = '''diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -0,0 +1,2 @@
+def test_handler():
+    assert True
'''
        request = ReviewRequest(
            repo="demo/repo",
            files=[ReviewFile(path="tests/test_app.py", content="def test_handler():\n    assert True\n")],
            diff=diff,
        )

        context = build_review_context(request)

        self.assertEqual(context.changed_file_paths(), {"tests/test_app.py"})
        self.assertEqual(context.changed_test_paths(), {"tests/test_app.py"})
        self.assertEqual(context.changed_production_paths(), set())


if __name__ == "__main__":
    unittest.main()
