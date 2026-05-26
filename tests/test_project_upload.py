import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.project_loader import extract_review_files_from_zip_bytes


class ProjectUploadTests(unittest.TestCase):
    def test_extract_zip_filters_project_files(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("demo/app/users.py", 'sql = "SELECT * FROM users WHERE id = " + user_id')
            zf.writestr("demo/node_modules/lib/index.js", "ignored")
            zf.writestr("demo/.git/config", "ignored")
            zf.writestr("demo/assets/logo.png", b"\x00\x01")
        files, meta = extract_review_files_from_zip_bytes(buf.getvalue())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "demo/app/users.py")
        self.assertGreaterEqual(meta["skipped_files"], 3)


if __name__ == "__main__":
    unittest.main()
