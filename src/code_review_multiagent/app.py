from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Callable
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .github import (
    build_review_request_from_github_api,
    build_review_request_from_webhook,
    parse_json_body,
    post_pull_request_comment,
    verify_github_signature,
)
from .llm_client import list_models, test_model
from .llm_config import LLMConfig, LLMConfigUpdate, LLMModelsRequest, get_llm_config, public_config, save_llm_config
from .metrics import collector as metrics_collector
from .models import AgentConfigCreate, AgentConfigUpdate, ReviewFile, ReviewReport, ReviewRequest
from .orchestrator import ReviewOrchestrator
from .project_loader import extract_review_files_from_upload
from .review_store import (
    StoreUnavailableError,
    create_agent_config,
    delete_agent_config,
    delete_review_record,
    get_review_report,
    init_store,
    list_agent_configs,
    list_review_events,
    list_review_records,
    save_review_record,
    update_agent_config,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web"

from .config import get_settings
from .log import get_logger, setup_logging

_settings = get_settings()
setup_logging(_settings.log_level, _settings.log_format)
logger = get_logger(__name__)

app = FastAPI(
    title="Multi-Agent Code Review System",
    description="Security / Performance / Style agents coordinated by an Orchestrator.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

orchestrator = ReviewOrchestrator()
_review_jobs: dict[str, dict] = {}
_review_jobs_lock = Lock()

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup() -> None:
    try:
        init_store()
        app.state.review_store_error = None
    except StoreUnavailableError as exc:
        app.state.review_store_error = str(exc)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
def health() -> dict:
    from sqlalchemy import text

    from .review_store import _engine

    db_ok = True
    try:
        if _engine:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "service": "multi-agent-code-review"}


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    """Prometheus 格式的 Agent 执行指标。"""
    return metrics_collector.get_prometheus_metrics()


@app.get("/api/metrics")
def api_metrics():
    """结构化的 Agent 执行指标摘要。"""
    return metrics_collector.get_summary()


@app.get("/api/reviews/history")
def review_history(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    try:
        return list_review_records(limit=limit, offset=offset)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/reviews/history/{record_id}", response_model=ReviewReport)
def review_history_detail(record_id: int) -> ReviewReport:
    try:
        report = get_review_report(record_id)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if report is None:
        raise HTTPException(status_code=404, detail="review record not found")
    return report


@app.delete("/api/reviews/history/{record_id}")
def delete_review_history(record_id: int) -> dict[str, bool]:
    try:
        deleted = delete_review_record(record_id)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="review record not found")
    return {"deleted": True}


@app.get("/api/reviews/history/{record_id}/events")
def review_history_events(record_id: int):
    try:
        if get_review_report(record_id) is None:
            raise HTTPException(status_code=404, detail="review record not found")
        events = list_review_events(record_id)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"items": [event.model_dump(mode="json") for event in events]}


@app.get("/api/agents")
def agent_configs():
    try:
        return {"items": [item.model_dump(mode="json") for item in list_agent_configs()]}
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/agents")
def create_agent(create: AgentConfigCreate):
    try:
        config = create_agent_config(create)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return config


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, update: AgentConfigUpdate):
    try:
        config = update_agent_config(agent_id, update)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if config is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return config


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int) -> dict[str, bool]:
    try:
        deleted = delete_agent_config(agent_id)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"deleted": True}


@app.post("/api/reviews", response_model=ReviewReport)
def create_review(request: ReviewRequest) -> ReviewReport:
    if not request.files:
        raise HTTPException(status_code=400, detail="files is required")
    run = orchestrator.review_with_events(request)
    report = run.report
    _persist_report(report, run.events)
    return report


@app.post("/api/reviews/jobs", status_code=202)
def create_review_job(request: ReviewRequest) -> dict[str, str]:
    if not request.files:
        raise HTTPException(status_code=400, detail="files is required")
    job_id = uuid4().hex
    with _review_jobs_lock:
        _review_jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "events": [],
            "report": None,
            "error": None,
        }
    Thread(target=_run_review_job, args=(job_id, request), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/reviews/jobs/{job_id}")
def get_review_job(job_id: str) -> dict:
    with _review_jobs_lock:
        job = _review_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="review job not found")
        return dict(job)


@app.post("/api/reviews/upload", response_model=ReviewReport)
async def upload_project_review(
    file: UploadFile = File(...),
    repo: str = Form(default="uploaded/project"),
    title: str = Form(default="Uploaded project review"),
) -> ReviewReport:
    files, meta = await extract_review_files_from_upload(file)
    run = orchestrator.review_with_events(ReviewRequest(repo=repo, title=title, files=files))
    report = run.report
    report.metadata["upload"] = meta
    report.metadata["source_filename"] = file.filename
    _persist_report(report, run.events)
    return report


@app.post("/api/reviews/upload/stream")
async def upload_project_review_stream(
    file: UploadFile = File(...),
    repo: str = Form(default="uploaded/project"),
    title: str = Form(default="项目代码审查报告"),
) -> StreamingResponse:
    async def event_stream():
        def sse(event: dict) -> str:
            return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        try:
            yield sse({"type": "start", "message": "已收到项目压缩包，开始准备审查。"})
            yield sse({"type": "progress", "stage": "解压项目", "message": "正在解压 zip，并检查文件路径安全性。"})
            files, meta = await extract_review_files_from_upload(file)
            yield sse(
                {
                    "type": "progress",
                    "stage": "筛选代码文件",
                    "message": f"已纳入 {meta['included_files']} 个代码/配置文件，跳过 {meta['skipped_files']} 个无关或过大的文件。",
                    "metadata": meta,
                }
            )

            def enrich_report(report: ReviewReport) -> None:
                report.metadata["upload"] = meta
                report.metadata["source_filename"] = file.filename

            async for chunk in _stream_review_run(
                ReviewRequest(repo=repo, title=title, files=files), sse, enrich_report
            ):
                yield chunk
        except Exception as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/reviews/stream")
async def create_review_stream(request: ReviewRequest) -> StreamingResponse:
    async def event_stream():
        def sse(event: dict) -> str:
            return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        try:
            async for chunk in _stream_review_run(request, sse):
                yield chunk
        except Exception as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/demo", response_model=ReviewReport)
def demo_review() -> ReviewReport:
    sample = """def get_user_profile(db, request):
    user_id = request.args.get("id")
    sql = "SELECT * FROM users WHERE id = " + user_id
    user = db.execute(sql).fetchone()

    orders = []
    for order_id in user.order_ids:
        orders.append(db.execute(f"SELECT * FROM orders WHERE id = {order_id}").fetchone())

    return {
        "name": user.name,
        "email": user.email,
        "orders": orders,
        "debug_token": "demo-api-key-placeholder"
    }
"""
    return orchestrator.review(
        ReviewRequest(
            repo="demo/multi-agent-review",
            pr_number=7,
            title="Demo PR: user profile endpoint",
            files=[ReviewFile(path="app/users.py", content=sample, language="python")],
        )
    )


@app.get("/api/demo/markdown", response_class=PlainTextResponse)
def demo_markdown() -> str:
    return demo_review().markdown


@app.get("/llm-config")
async def get_runtime_llm_config():
    return public_config()


@app.post("/llm-config")
async def update_runtime_llm_config(req: LLMConfigUpdate):
    if not req.model.strip():
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    config = save_llm_config(req)
    return public_config(config)


@app.post("/llm-config/models")
async def list_runtime_llm_models(req: LLMModelsRequest):
    current = get_llm_config()
    api_key = req.api_key.strip() if req.api_key else current.api_key
    base_url = req.base_url.strip()
    if req.provider == "deepseek" and not base_url:
        base_url = "https://api.deepseek.com"
    config = LLMConfig(
        provider=req.provider,
        api_key=api_key,
        base_url=base_url,
        model=req.model or current.model,
        timeout=req.timeout,
    )
    try:
        return {"models": await list_models(config)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"刷新模型列表失败: {e}")


@app.post("/llm-config/test")
async def test_runtime_llm_config(req: LLMModelsRequest):
    current = get_llm_config()
    api_key = req.api_key.strip() if req.api_key else current.api_key
    base_url = req.base_url.strip()
    if req.provider == "deepseek" and not base_url:
        base_url = "https://api.deepseek.com"
    config = LLMConfig(
        provider=req.provider,
        api_key=api_key,
        base_url=base_url,
        model=req.model or current.model,
        timeout=req.timeout,
    )
    try:
        message = await test_model(config)
        return {"ok": True, "message": message or "OK"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"模型连通性测试失败: {e}")


@app.post("/api/github/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    raw_body = await request.body()
    if not verify_github_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid GitHub signature")

    payload = parse_json_body(raw_body)
    if x_github_event not in {None, "pull_request", "push"}:
        return JSONResponse({"status": "ignored", "reason": f"unsupported event: {x_github_event}"})

    review_request = build_review_request_from_webhook(payload)
    source = "payload"
    if review_request is None:
        review_request = await build_review_request_from_github_api(payload)
        source = "github_api"
    if review_request is None:
        return JSONResponse(
            {
                "status": "accepted",
                "review_created": False,
                "reason": "webhook payload has no review_files/files content and GitHub API fetch is not available",
            }
        )

    run = orchestrator.review_with_events(review_request)
    report = run.report
    _persist_report(report, run.events)
    comment_result = await post_pull_request_comment(report.repo, report.pr_number, report.markdown)
    report.metadata["github_comment"] = comment_result
    return JSONResponse(
        {
            "status": "completed",
            "review_created": True,
            "source": source,
            "summary": report.summary.model_dump(),
            "conflicts": [item.model_dump() for item in report.conflicts],
            "markdown": report.markdown,
            "record_id": report.metadata.get("record_id"),
            "github_comment": comment_result,
        }
    )


def _store_unavailable_detail(error: Exception | str | None = None) -> str:
    """Return a browser-safe message when the optional review store is unavailable."""
    return "审查记录服务暂不可用，项目审查仍可继续；本次结果将只在当前页面展示，不会写入历史记录。"


def safe_persist_report(report: ReviewReport, events=None, persist_func=save_review_record) -> bool:
    """Best-effort persistence: keep review UX usable even when MySQL is down."""
    try:
        record_id = persist_func(report, events)
    except (StoreUnavailableError, HTTPException):
        report.metadata["record_status"] = "unavailable"
        report.metadata["record_warning"] = _store_unavailable_detail()
        return False
    report.metadata["record_id"] = record_id
    report.metadata["record_status"] = "saved"
    return True


def _persist_report(report: ReviewReport, events=None) -> None:
    safe_persist_report(report, events)


def _update_review_job(job_id: str, **updates) -> None:
    with _review_jobs_lock:
        job = _review_jobs.get(job_id)
        if job is None:
            return
        job.update(updates)
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")


def _run_review_job(job_id: str, request: ReviewRequest) -> None:
    events: list[dict] = []

    def on_event(event):
        payload = event.model_dump(mode="json")
        events.append(payload)
        _update_review_job(job_id, status="running", events=list(events))

    try:
        _update_review_job(job_id, status="running")
        run = orchestrator.review_with_events(request, on_event=on_event)
        report = run.report
        _persist_report(report, run.events)
        _update_review_job(
            job_id,
            status="completed",
            report=report.model_dump(mode="json"),
            events=[event.model_dump(mode="json") for event in run.events] or events,
        )
    except Exception as exc:
        _update_review_job(job_id, status="failed", error=str(exc), events=events)


async def _stream_review_run(
    request: ReviewRequest,
    sse: Callable[[dict], str],
    before_persist: Callable[[ReviewReport], None] | None = None,
):
    queue: Queue = Queue()
    done = object()

    def on_event(event):
        queue.put(("event", event.model_dump(mode="json")))

    def worker() -> None:
        try:
            run = orchestrator.review_with_events(request, on_event=on_event)
            report = run.report
            if before_persist:
                before_persist(report)
            _persist_report(report, run.events)
            queue.put(("report", report.model_dump()))
        except Exception as exc:
            queue.put(("error", str(exc)))
        finally:
            queue.put(done)

    Thread(target=worker, daemon=True).start()

    while True:
        try:
            item = queue.get(timeout=0.1)
        except Empty:
            continue
        if item is done:
            break
        kind, payload = item
        if kind == "event":
            yield sse(payload)
        elif kind == "report":
            summary = payload.get("summary", {})
            total = summary.get("total_findings", 0)
            yield sse({"type": "report", "report": payload})
            if payload.get("metadata", {}).get("record_status") == "unavailable":
                yield sse(
                    {
                        "type": "complete",
                        "message": f"审查完成：共发现 {total} 个问题。审查记录服务暂不可用，本次结果仅在当前页面展示。",
                    }
                )
            else:
                yield sse({"type": "complete", "message": f"审查完成：共发现 {total} 个问题，记录已写入 MySQL。"})
        else:
            yield sse({"type": "error", "message": payload})
