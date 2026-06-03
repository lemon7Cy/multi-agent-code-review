import hashlib
import hmac
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.github import (
    _truncate_comment,
    build_review_request_from_webhook,
    github_api_available,
    verify_github_signature,
)


class GitHubWebhookTests(unittest.TestCase):
    def test_verify_github_signature(self):
        body = b'{"ok": true}'
        secret = "demo-secret"
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_github_signature(body, signature, secret))
        self.assertFalse(verify_github_signature(body, "sha256=bad", secret))

    def test_build_review_request_from_webhook(self):
        payload = {
            "repository": {"full_name": "demo/repo"},
            "pull_request": {"number": 3, "title": "demo pr"},
            "review_files": [{"path": "app.py", "content": "print('hello')"}],
        }
        request = build_review_request_from_webhook(payload)
        self.assertIsNotNone(request)
        self.assertEqual(request.repo, "demo/repo")
        self.assertEqual(request.pr_number, 3)
        self.assertEqual(request.files[0].path, "app.py")

    def test_github_api_available_requires_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            self.assertFalse(github_api_available())

    def test_truncate_comment_preserves_short_report(self):
        self.assertEqual(_truncate_comment("hello"), "hello")


if __name__ == "__main__":
    unittest.main()
