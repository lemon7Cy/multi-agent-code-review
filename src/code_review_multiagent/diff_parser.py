from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ChangedLine:
    line_type: Literal["added", "removed"]
    content: str
    old_line: int | None
    new_line: int | None


@dataclass
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    changed_lines: list[ChangedLine] = field(default_factory=list)


@dataclass
class DiffFile:
    old_path: str | None
    path: str
    hunks: list[DiffHunk] = field(default_factory=list)


@dataclass
class ParsedDiff:
    files: list[DiffFile] = field(default_factory=list)


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(diff_text: str) -> ParsedDiff:
    """Parse a GitHub/unified diff into files, hunks, and changed line numbers."""
    parsed = ParsedDiff()
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    old_line: int | None = None
    new_line: int | None = None
    pending_old_path: str | None = None
    pending_new_path: str | None = None

    def finalize_pending_file() -> None:
        nonlocal current_file, current_hunk, old_line, new_line, pending_old_path, pending_new_path
        if pending_new_path is None:
            return
        current_file = DiffFile(old_path=pending_old_path, path=pending_new_path)
        parsed.files.append(current_file)
        current_hunk = None
        old_line = None
        new_line = None
        pending_old_path = None
        pending_new_path = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            finalize_pending_file()
            current_file = None
            current_hunk = None
            old_line = None
            new_line = None
            pending_old_path = None
            pending_new_path = None
            continue

        if raw_line.startswith("--- "):
            path = raw_line[4:].strip()
            pending_old_path = _normalize_diff_path(path)
            continue

        if raw_line.startswith("+++ "):
            path = raw_line[4:].strip()
            pending_new_path = _normalize_diff_path(path)
            finalize_pending_file()
            continue

        match = _HUNK_RE.match(raw_line)
        if match:
            if current_file is None:
                continue
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header=raw_line,
            )
            current_file.hunks.append(current_hunk)
            old_line = old_start
            new_line = new_start
            continue

        if current_hunk is None or old_line is None or new_line is None:
            continue

        if raw_line.startswith("\\ No newline at end of file"):
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_hunk.changed_lines.append(
                ChangedLine(
                    line_type="added",
                    content=raw_line[1:],
                    old_line=None,
                    new_line=new_line,
                )
            )
            new_line += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            current_hunk.changed_lines.append(
                ChangedLine(
                    line_type="removed",
                    content=raw_line[1:],
                    old_line=old_line,
                    new_line=None,
                )
            )
            old_line += 1
            continue

        # Context line, including the empty context line represented as " " in diffs.
        if raw_line.startswith(" ") or raw_line == "":
            old_line += 1
            new_line += 1

    finalize_pending_file()
    return parsed


def _normalize_diff_path(path: str) -> str | None:
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
