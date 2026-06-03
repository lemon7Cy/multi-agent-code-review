from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import AgentReview, ReviewFile


class ReviewAgent(Protocol):
    name: str
    role: str

    def review(self, files: list[ReviewFile]) -> AgentReview: ...


@dataclass(frozen=True)
class RuleContext:
    file: ReviewFile
    lines: list[str]


def infer_language(path: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower()
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "java": "java",
        "go": "go",
    }.get(suffix, suffix or "text")


def find_line(lines: list[str], needle: str) -> int | None:
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    return None
