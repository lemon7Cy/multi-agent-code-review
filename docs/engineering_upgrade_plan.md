# Project 2 Engineering Upgrade Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Upgrade `multi-agent-code-review` from an MVP demo into a portfolio-ready, engineering-grade Multi-Agent PR Review platform.

**Architecture:** Add a diff-aware review pipeline before the existing Orchestrator. The pipeline parses PR unified diffs, creates structured review context, routes tasks to specialist Agents, adds a Test Coverage Agent, and uses a Critic layer to validate/highlight conflicts before producing GitHub inline/summary comments.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, GitHub Webhook/API, unittest/pytest-compatible tests, Docker Compose, optional MySQL/Redis, LLM Tool Use agents.

---

## Phase 1 Scope

Phase 1 should make the project immediately more credible on a resume without overbuilding infrastructure.

Deliverables:

1. `diff_parser.py` — parse unified diff into changed files, hunks, and changed lines.
2. `review_context.py` — combine full files + diff into review-ready context.
3. `planner.py` — generate role-specific review tasks from diff risk hints.
4. `test_coverage_agent.py` — identify changed production code without matching test changes.
5. `critic.py` — second-pass finding validation, confidence, duplicate/conflict handling.
6. Tests for every new behavior.
7. README / architecture updates after implementation.

---

## Task 1: Add Diff Parser

**Objective:** Parse GitHub-style unified diffs into structured changed files, hunks, and added/removed lines.

**Files:**
- Create: `src/code_review_multiagent/diff_parser.py`
- Create: `tests/test_diff_parser.py`

**Expected API:**

```python
from code_review_multiagent.diff_parser import parse_unified_diff

parsed = parse_unified_diff(diff_text)
parsed.files[0].path                 # "src/app.py"
parsed.files[0].hunks[0].new_start   # 10
parsed.files[0].hunks[0].changed_lines[0].line_type  # "added"
```

**Behavior requirements:**

- Parse `diff --git a/x b/x` file boundaries.
- Use `+++ b/path` as canonical new path.
- Parse hunk header: `@@ -old_start,old_count +new_start,new_count @@`.
- Track added lines with new line numbers.
- Track removed lines with old line numbers.
- Track context lines to keep line counters accurate.
- Ignore `\ No newline at end of file` marker.
- Support new files where old path is `/dev/null`.

**RED test examples:**

```python
def test_parse_unified_diff_tracks_added_and_removed_lines():
    diff = '''diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 def hello():
-    return "hi"
+    name = "world"
+    return f"hi {name}"
 '''
    parsed = parse_unified_diff(diff)
    file = parsed.files[0]
    assert file.path == "src/app.py"
    assert file.hunks[0].old_start == 1
    assert file.hunks[0].new_start == 1
    changed = file.hunks[0].changed_lines
    assert [(line.line_type, line.old_line, line.new_line) for line in changed] == [
        ("removed", 2, None),
        ("added", None, 2),
        ("added", None, 3),
    ]
```

**Verify RED:**

```bash
python -m pytest tests/test_diff_parser.py -q
```

Expected: fail because module does not exist.

**GREEN implementation:**

Implement dataclasses:

```python
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
    changed_lines: list[ChangedLine]

@dataclass
class DiffFile:
    old_path: str | None
    path: str
    hunks: list[DiffHunk]

@dataclass
class ParsedDiff:
    files: list[DiffFile]
```

**Verify GREEN:**

```bash
python -m pytest tests/test_diff_parser.py -q
python -m pytest tests/ -q
```

---

## Task 2: Add Review Context Builder

**Objective:** Convert `ReviewRequest.files` + optional unified diff into context objects that identify changed files and changed line ranges.

**Files:**
- Create: `src/code_review_multiagent/review_context.py`
- Create: `tests/test_review_context.py`
- Modify: `src/code_review_multiagent/models.py` only if `ReviewRequest` needs an optional `diff` field.

**Expected API:**

```python
context = build_review_context(request)
context.files["src/app.py"].changed_new_lines == {2, 3}
context.files["src/app.py"].is_changed is True
```

**Behavior requirements:**

- If request has no diff, mark all files as reviewable but with empty changed line sets.
- If diff exists, map changed line numbers to matching `ReviewFile.path`.
- Include helper `is_line_changed(path, line)`.
- Preserve full file content for existing agents.

---

## Task 3: Add Review Planner

**Objective:** Generate role-specific review tasks based on changed files, extensions, and diff risk hints.

**Files:**
- Create: `src/code_review_multiagent/planner.py`
- Create: `tests/test_planner.py`

**Expected API:**

```python
tasks = ReviewPlanner().plan(context)
security_task = next(t for t in tasks if t.agent_role == "security")
```

**Behavior requirements:**

- Always create security, performance, maintainability tasks for code files.
- Create test coverage task when production code changed.
- Add risk hints:
  - SQL/string concat -> `sql_injection_risk`
  - loop with db/query -> `n_plus_one_risk`
  - new endpoint/function without tests -> `missing_test_risk`
  - config/env/secrets-looking strings -> `secret_risk`
- Skip binary/unsupported files.

---

## Task 4: Add Test Coverage Agent

**Objective:** Add a specialist Agent that flags changed production code with no related test changes.

**Files:**
- Create: `src/code_review_multiagent/agents/test_coverage_agent.py`
- Modify: `src/code_review_multiagent/agents/__init__.py`
- Modify: `src/code_review_multiagent/agents/rule_agents.py` or default agent builder
- Create: `tests/test_test_coverage_agent.py`

**Behavior requirements:**

- If files under `src/`, `app/`, or package directories changed and no files under `tests/` changed, emit a medium finding.
- If matching tests changed, emit no finding.
- Recommendation should name likely test path.
- Finding category should be `Test Coverage`.
- Rule id should be `TEST-MISSING-COVERAGE`.

---

## Task 5: Add Critic Layer

**Objective:** Validate and annotate findings after all specialist Agents finish.

**Files:**
- Create: `src/code_review_multiagent/critic.py`
- Create: `tests/test_critic.py`
- Modify: `src/code_review_multiagent/orchestrator.py`
- Modify: `src/code_review_multiagent/models.py` if adding `confidence` / `critic_note` fields.

**Behavior requirements:**

- Deduplicate same file + line + rule_id findings.
- Add confidence level based on evidence strength.
- Downgrade style-only critical/high findings to medium.
- Preserve security finding priority when security and performance recommendations conflict.
- Add critic notes into report metadata or finding fields.

---

## Task 6: GitHub Inline Comment Payload Builder

**Objective:** Convert findings into GitHub review comment payloads when they map to changed lines.

**Files:**
- Create: `src/code_review_multiagent/pr_commenter.py`
- Create: `tests/test_pr_commenter.py`
- Modify: `src/code_review_multiagent/github.py` only after tests pass.

**Behavior requirements:**

- Inline comment only if finding line exists in parsed changed new lines.
- Otherwise include finding in summary markdown.
- Generate body with severity, agent, evidence, recommendation.
- Never include raw secrets in comments; use existing/new secret masking helper.

---

## Task 7: Async Review Jobs

**Objective:** Add job state so long-running LLM review is not tied to request lifecycle.

**Files:**
- Create: `src/code_review_multiagent/jobs.py`
- Create: `tests/test_jobs.py`
- Modify: `src/code_review_multiagent/app.py`

**Behavior requirements:**

- `POST /api/reviews/jobs` returns `job_id` and status `queued`.
- Background worker transitions `queued -> running -> completed/failed`.
- `GET /api/reviews/jobs/{job_id}` returns status, timestamps, error, result id.
- Events can be queried by job id.
- Start with in-memory store; document Redis/Celery upgrade path.

---

## Task 8: Documentation and Project Presentation

**Objective:** Make the project easier to understand, run, and evaluate as an engineering artifact.

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/IMPLEMENTATION_SUMMARY.md`
- Create: `docs/demo_script.md`

**Content requirements:**

- Architecture diagram showing: Webhook -> Diff Parser -> Planner -> Agents -> Critic -> PR Comments -> Metrics/History.
- Local run commands.
- Sample PR review flow.
- Engineering tradeoffs.
- Operational limits and extension points.
- Clear explanation of design choices.

---

## Verification Commands

Run from project root:

```bash
python -m pytest tests/ -q
python -m uvicorn code_review_multiagent.app:app --app-dir src --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/metrics
```

If dependencies are missing:

```bash
python -m pip install -r requirements.txt
```

---

## Commit Strategy

Commit after each task:

```bash
git add <changed files>
git commit -m "feat: add diff parser for PR review context"
git commit -m "feat: build diff-aware review context"
git commit -m "feat: plan role-specific review tasks"
git commit -m "feat: add test coverage review agent"
git commit -m "feat: add critic layer for finding validation"
git commit -m "feat: generate GitHub inline review comments"
git commit -m "feat: add async review jobs"
git commit -m "docs: document engineering-grade multi-agent review flow"
```
