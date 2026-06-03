import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.diff_parser import parse_unified_diff


class DiffParserTests(unittest.TestCase):
    def test_parse_unified_diff_tracks_added_and_removed_lines(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 def hello():
-    return "hi"
+    name = "world"
+    return f"hi {name}"
 """
        parsed = parse_unified_diff(diff)
        file = parsed.files[0]

        self.assertEqual(file.old_path, "src/app.py")
        self.assertEqual(file.path, "src/app.py")
        self.assertEqual(file.hunks[0].old_start, 1)
        self.assertEqual(file.hunks[0].old_count, 4)
        self.assertEqual(file.hunks[0].new_start, 1)
        self.assertEqual(file.hunks[0].new_count, 5)
        changed = file.hunks[0].changed_lines
        self.assertEqual(
            [(line.line_type, line.old_line, line.new_line, line.content) for line in changed],
            [
                ("removed", 2, None, '    return "hi"'),
                ("added", None, 2, '    name = "world"'),
                ("added", None, 3, '    return f"hi {name}"'),
            ],
        )

    def test_parse_multiple_files_and_new_file(self):
        diff = """diff --git a/src/old.py b/src/old.py
--- a/src/old.py
+++ b/src/old.py
@@ -10,2 +10,2 @@ def run():
-old_call()
+new_call()
diff --git a/tests/test_new.py b/tests/test_new.py
new file mode 100644
--- /dev/null
+++ b/tests/test_new.py
@@ -0,0 +1,2 @@
+def test_new_call():
+    assert True
"""
        parsed = parse_unified_diff(diff)

        self.assertEqual([file.path for file in parsed.files], ["src/old.py", "tests/test_new.py"])
        self.assertIsNone(parsed.files[1].old_path)
        self.assertEqual(parsed.files[1].hunks[0].old_start, 0)
        self.assertEqual(parsed.files[1].hunks[0].new_start, 1)
        self.assertEqual([line.new_line for line in parsed.files[1].hunks[0].changed_lines], [1, 2])

    def test_no_newline_marker_is_ignored(self):
        diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
\\ No newline at end of file
"""
        parsed = parse_unified_diff(diff)

        changed = parsed.files[0].hunks[0].changed_lines
        self.assertEqual(len(changed), 2)
        self.assertEqual(changed[1].content, "new")


if __name__ == "__main__":
    unittest.main()
