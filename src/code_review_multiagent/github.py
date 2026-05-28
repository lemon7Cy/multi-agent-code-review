from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import httpx

from .models import ReviewFile, ReviewRequest


def verify_github_signature(raw_body: bytes, signature_header: str | None, secret: str | None = None) -> bool:
    """Verify X-Hub-Signature-256. Rejects if no secret is configured in production."""
    webhook_secret = secret if secret is not None else os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not webhook_secret:
        from .log import get_logger
        get_logger(__name__).warning("github_webhook_no_secret_configured")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def parse_json_body(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    return json.loads(raw_body.decode("utf-8"))


def build_review_request_from_webhook(payload: dict[str, Any]) -> ReviewRequest | None:
    """
    Build a ReviewRequest from GitHub webhook-like payload.

    真正 GitHub pull_request webhook 默认不携带完整 patch 内容；生产环境需要再调用
    GitHub API 拉取 changed files。MVP 为了可本地演示，支持 payload.review_files：

    {
      "repository": {"full_name": "demo/repo"},
      "pull_request": {"number": 1, "title": "demo"},
      "review_files": [{"path": "app.py", "content": "..."}]
    }
    """
    repo = (payload.get("repository") or {}).get("full_name")
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    title = pr.get("title") or payload.get("title")

    raw_files = payload.get("review_files") or payload.get("files") or []
    files: list[ReviewFile] = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("filename") or item.get("name")
        content = item.get("content") or item.get("patch") or ""
        if path and content:
            files.append(ReviewFile(path=path, content=content, language=item.get("language")))

    if not files:
        return None
    return ReviewRequest(repo=repo, pr_number=pr_number, title=title, files=files)


def github_api_available() -> bool:
    return bool(os.getenv("GITHUB_TOKEN"))


async def build_review_request_from_github_api(payload: dict[str, Any]) -> ReviewRequest | None:
    """Fetch changed PR files from GitHub API when webhook payload has no file content."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = (payload.get("repository") or {}).get("full_name")
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    title = pr.get("title") or payload.get("title")

    if not token or not repo or not pr_number:
        return None

    headers = _github_headers(token)
    api_base = os.getenv("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
    files: list[ReviewFile] = []

    async with httpx.AsyncClient(timeout=float(os.getenv("GITHUB_API_TIMEOUT", "30"))) as client:
        changed_files = await _fetch_pull_files(client, api_base, headers, repo, pr_number)
        for item in changed_files:
            filename = item.get("filename")
            status = item.get("status")
            if not filename or status == "removed":
                continue
            patch = item.get("patch") or ""
            raw_url = item.get("raw_url")
            content = patch
            if raw_url and _should_fetch_raw(filename):
                content = await _fetch_raw_file(client, raw_url, headers) or patch
            if content:
                files.append(ReviewFile(path=filename, content=content))

    if not files:
        return None
    return ReviewRequest(repo=repo, pr_number=int(pr_number), title=title, files=files)


async def post_pull_request_comment(repo: str | None, pr_number: int | None, markdown: str) -> dict[str, Any]:
    """Post review markdown back to a GitHub PR. Returns a structured status dict."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token or not repo or not pr_number:
        return {"posted": False, "reason": "GITHUB_TOKEN, repo or pr_number is missing"}

    api_base = os.getenv("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
    body = _truncate_comment(markdown)
    async with httpx.AsyncClient(timeout=float(os.getenv("GITHUB_API_TIMEOUT", "30"))) as client:
        response = await client.post(
            f"{api_base}/repos/{repo}/issues/{pr_number}/comments",
            headers=_github_headers(token),
            json={"body": body},
        )
        response.raise_for_status()
        payload = response.json()
        return {"posted": True, "url": payload.get("html_url"), "id": payload.get("id")}


async def _fetch_pull_files(client: httpx.AsyncClient, api_base: str, headers: dict[str, str], repo: str, pr_number: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        response = await client.get(
            f"{api_base}/repos/{repo}/pulls/{pr_number}/files",
            headers=headers,
            params={"per_page": 100, "page": page},
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


async def _fetch_raw_file(client: httpx.AsyncClient, raw_url: str, headers: dict[str, str]) -> str:
    response = await client.get(raw_url, headers=headers)
    response.raise_for_status()
    return response.text[: int(os.getenv("GITHUB_RAW_FILE_MAX_CHARS", "120000"))]


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "multi-agent-code-review",
    }


def _should_fetch_raw(filename: str) -> bool:
    suffix = os.path.splitext(filename.lower())[1]
    return suffix in {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".php",
        ".cs", ".cpp", ".c", ".h", ".sql", ".yaml", ".yml", ".json", ".toml",
        ".md", ".html", ".css",
    }


def _truncate_comment(markdown: str) -> str:
    max_chars = int(os.getenv("GITHUB_COMMENT_MAX_CHARS", "60000"))
    if len(markdown) <= max_chars:
        return markdown
    return markdown[: max_chars - 120].rstrip() + "\n\n_报告过长，已截断；完整报告请在审查系统中查看。_"
