from __future__ import annotations

from dataclasses import dataclass, field

from .diff_parser import parse_unified_diff
from .models import ReviewFile, ReviewRequest


@dataclass
class ReviewFileContext:
    file: ReviewFile
    changed_new_lines: set[int] = field(default_factory=set)
    changed_old_lines: set[int] = field(default_factory=set)

    @property
    def path(self) -> str:
        return self.file.path

    @property
    def is_changed(self) -> bool:
        return bool(self.changed_new_lines or self.changed_old_lines)

    @property
    def is_reviewable(self) -> bool:
        return True

    @property
    def is_test_file(self) -> bool:
        return is_test_path(self.path)


@dataclass
class ReviewContext:
    repo: str | None
    pr_number: int | None
    title: str | None
    files: dict[str, ReviewFileContext]

    def is_line_changed(self, path: str, line: int) -> bool:
        file_context = self.files.get(path)
        return bool(file_context and line in file_context.changed_new_lines)

    def changed_file_paths(self) -> set[str]:
        return {path for path, file_context in self.files.items() if file_context.is_changed}

    def changed_test_paths(self) -> set[str]:
        return {path for path in self.changed_file_paths() if is_test_path(path)}

    def changed_production_paths(self) -> set[str]:
        return {path for path in self.changed_file_paths() if not is_test_path(path)}


def build_review_context(request: ReviewRequest) -> ReviewContext:
    contexts = {
        file.path: ReviewFileContext(file=file)
        for file in request.files
    }

    if request.diff:
        parsed = parse_unified_diff(request.diff)
        for diff_file in parsed.files:
            file_context = contexts.get(diff_file.path)
            if file_context is None:
                continue
            for hunk in diff_file.hunks:
                for line in hunk.changed_lines:
                    if line.line_type == "added" and line.new_line is not None:
                        file_context.changed_new_lines.add(line.new_line)
                    elif line.line_type == "removed" and line.old_line is not None:
                        file_context.changed_old_lines.add(line.old_line)

    return ReviewContext(
        repo=request.repo,
        pr_number=request.pr_number,
        title=request.title,
        files=contexts,
    )


def is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    name = parts[-1]
    return (
        "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
    )
