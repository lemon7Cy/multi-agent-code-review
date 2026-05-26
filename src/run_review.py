from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from code_review_multiagent.models import ReviewFile, ReviewRequest
from code_review_multiagent.orchestrator import ReviewOrchestrator


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run multi-agent code review locally.")
    parser.add_argument("files", nargs="+", help="Files to review")
    parser.add_argument("--repo", default="local/repo")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    args = parser.parse_args()

    review_files = []
    for item in args.files:
        path = Path(item)
        review_files.append(ReviewFile(path=str(path), content=path.read_text(encoding="utf-8")))

    report = ReviewOrchestrator().review(ReviewRequest(repo=args.repo, files=review_files))
    if args.json:
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(report.markdown)


if __name__ == "__main__":
    main()
