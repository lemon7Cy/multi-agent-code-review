from __future__ import annotations

import re
from dataclasses import dataclass, field

from .review_context import ReviewContext

_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".sql",
}


@dataclass
class ReviewTask:
    task_id: str
    agent_role: str
    file_paths: list[str]
    risk_hints: list[str] = field(default_factory=list)


class ReviewPlanner:
    """Creates role-specific review tasks from diff-aware review context."""

    def plan(self, context: ReviewContext) -> list[ReviewTask]:
        changed_code_paths = [path for path in sorted(context.changed_file_paths()) if _is_code_path(path)]
        if not changed_code_paths:
            # Without a diff, review all code files for backwards-compatible API usage.
            changed_code_paths = [path for path in sorted(context.files) if _is_code_path(path)]
        if not changed_code_paths:
            return []

        hints = self._risk_hints(context, changed_code_paths)
        tasks = [
            ReviewTask(
                task_id="security-review",
                agent_role="security",
                file_paths=changed_code_paths,
                risk_hints=[hint for hint in hints if hint in {"sql_injection_risk", "secret_risk"}],
            ),
            ReviewTask(
                task_id="performance-review",
                agent_role="performance",
                file_paths=changed_code_paths,
                risk_hints=[hint for hint in hints if hint in {"n_plus_one_risk"}],
            ),
            ReviewTask(
                task_id="maintainability-review",
                agent_role="maintainability",
                file_paths=changed_code_paths,
                risk_hints=[],
            ),
        ]

        if context.changed_production_paths() and not context.changed_test_paths():
            tasks.append(
                ReviewTask(
                    task_id="test-coverage-review",
                    agent_role="test_coverage",
                    file_paths=sorted(context.changed_production_paths()),
                    risk_hints=["missing_test_risk"],
                )
            )

        return tasks

    def _risk_hints(self, context: ReviewContext, paths: list[str]) -> set[str]:
        hints: set[str] = set()
        for path in paths:
            file_context = context.files[path]
            changed_text = _changed_text(file_context.file.content, file_context.changed_new_lines)
            if _looks_like_sql_injection(changed_text):
                hints.add("sql_injection_risk")
            if _looks_like_n_plus_one(changed_text):
                hints.add("n_plus_one_risk")
            if _looks_like_secret(changed_text):
                hints.add("secret_risk")
        return hints


def _changed_text(content: str, changed_lines: set[int]) -> str:
    if not changed_lines:
        return content
    lines = content.splitlines()
    selected = [lines[index - 1] for index in sorted(changed_lines) if 1 <= index <= len(lines)]
    return "\n".join(selected)


def _is_code_path(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(ext) for ext in _CODE_EXTENSIONS)


def _looks_like_sql_injection(text: str) -> bool:
    lowered = text.lower()
    has_sql = any(keyword in lowered for keyword in ("select ", "insert ", "update ", "delete "))
    has_concat = " + " in text or 'f"' in text or "f'" in text or "%" in text or ".format(" in text
    return has_sql and has_concat


def _looks_like_n_plus_one(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\bfor\b", lowered) and any(token in lowered for token in ("execute(", "query(", "select ")))


def _looks_like_secret(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("api_key", "apikey", "secret", "token", "password"))
