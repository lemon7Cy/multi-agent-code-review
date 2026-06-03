<div align="center">

# Multi-Agent Code Review

**A multi-agent pull request review system with diff awareness, tool use, review orchestration, and GitHub webhook support.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-review%20API-009688?logo=fastapi&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-PR%20webhook-181717?logo=github&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-tool%20use-7C3AED)
![CI](https://img.shields.io/badge/CI-pytest%20%2B%20build-2563EB)

</div>

## Overview

Multi-Agent Code Review is an engineering-focused review service for pull requests and uploaded project archives. It parses diffs, plans review work by risk area, routes tasks to specialized agents, filters low-confidence findings, and returns a structured report that can be surfaced in a web console or posted back to GitHub.

The system is designed to run without an LLM key for deterministic demos. When a model provider is configured, LLM tool-use agents join the same workflow and collect evidence through bounded tools instead of producing unconstrained free-form review text.

## Core Capabilities

- Diff-aware review that maps findings back to changed files, hunks, and line numbers.
- Planner-driven orchestration across Security, Performance, Maintainability, and Test Coverage agents.
- Rule-based fallback agents for stable local execution without API credentials.
- Optional LLM tool-use review with grep, function analysis, and SQL safety checks.
- Critic layer for PR-scope validation, duplicate suppression, confidence filtering, and conflict arbitration.
- GitHub pull request webhook endpoint with signature verification and comment payload generation.
- Async review jobs with queued/running/completed/failed states and event tracing.
- Web console for uploading project archives, viewing agent traces, and reading grouped findings.
- Review history, Prometheus metrics, MySQL persistence, and Docker Compose deployment.

## Architecture

```text
src/
  code_review_multiagent/
    agents/                 Specialized rule and LLM agents
    app.py                  FastAPI application
    blackboard.py           Shared artifact store
    commenter.py            GitHub summary and inline comment payloads
    critic.py               Finding validation and deduplication
    diff_parser.py          Unified diff parser
    github.py               Webhook parsing and signature verification
    llm_client.py           Anthropic and OpenAI-compatible clients
    llm_config.py           Runtime model configuration
    message_bus.py          Agent message bus
    models.py               Request, finding, and report schemas
    orchestrator.py         Task dispatch, aggregation, and arbitration
    planner.py              Risk-aware task planner
    project_loader.py       Project archive parsing and safety limits
    review_context.py       Diff-to-file context mapping
  run_review.py             Local CLI entry point
tests/                      Unit and integration tests
```

## Quick Start

```bash
git clone https://github.com/lemon7Cy/multi-agent-code-review.git
cd multi-agent-code-review

python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000
```

Open the web console:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Model Configuration

The project works without API credentials by using deterministic rule agents. To enable LLM tool-use review, configure a provider through `.env` or the model settings panel in the web console.

```bash
cp .env.example .env
```

Supported providers:

- `claude`: Anthropic Messages API.
- `deepseek`: OpenAI-compatible chat completions.
- `newapi`: OpenAI-compatible gateway.

Runtime configuration endpoints:

```text
GET  /llm-config
POST /llm-config
POST /llm-config/models
POST /llm-config/test
```

If a model call fails, the orchestrator keeps rule-agent findings and records the fallback reason in the review trace.

## Archive Review

Upload a project archive from the web console or call the API directly:

```text
POST /api/reviews/upload
form-data:
  file: project.zip
  repo: owner/repo
  title: Manual review
```

Safety limits:

- Maximum archive size: 50 MB.
- Maximum single file size: 300 KB.
- Maximum included files: 200.
- Maximum total text: 2 MB.
- Skips `.git`, `node_modules`, `.next`, `dist`, `build`, binary files, and other generated artifacts.

## CLI Usage

```bash
python src/run_review.py path/to/file.py
```

The CLI prints a Markdown review report for local inspection.

## GitHub Webhook

Endpoint:

```text
POST /api/github/webhook
```

When `GITHUB_WEBHOOK_SECRET` is configured, the service validates `X-Hub-Signature-256`. When `GITHUB_TOKEN` is configured, it can fetch pull request changed files and generate summary comments. For local integration tests, payloads may include `review_files` directly.

## Testing

```bash
python -m unittest discover -s tests -v
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation summary](docs/IMPLEMENTATION_SUMMARY.md)
- [Engineering upgrade plan](docs/engineering_upgrade_plan.md)

## Roadmap

- Move the message bus to Redis Streams for distributed workers.
- Add dependency, architecture, and license-compliance agents.
- Expand GitHub integration from summary comments to inline review comments.
- Persist more granular tool traces for auditability.
