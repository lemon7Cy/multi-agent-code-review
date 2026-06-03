from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import AgentConfigCreate, AgentConfigRead, AgentConfigUpdate, ReviewEvent, ReviewReport

DEFAULT_DATABASE_URL = "mysql+pymysql://root:root@localhost:3306/code_review_multiagent?charset=utf8mb4"
DATABASE_URL = os.getenv("CODE_REVIEW_DATABASE_URL", DEFAULT_DATABASE_URL)


class StoreUnavailableError(RuntimeError):
    pass


class Base(DeclarativeBase):
    pass


class ReviewRecord(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="代码审查报告")
    repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="agent")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_priority: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    report_json: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class AgentConfigRecord(Base):
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tools_json: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


class ReviewEventRecord(Base):
    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    agent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


class ReviewRecordSummary(BaseModel):
    id: int
    title: str
    repo: str | None = None
    mode: str
    file_count: int
    total_findings: int
    top_priority: str | None = None
    created_at: str


class ReviewHistoryPage(BaseModel):
    items: list[ReviewRecordSummary]
    total: int
    limit: int
    offset: int


DEFAULT_AGENT_CONFIGS = [
    {
        "agent_key": "security",
        "name": "Security Agent",
        "role": "只关注 SQL 注入、鉴权、敏感信息泄露等安全问题。",
        "kind": "rule",
        "enabled": True,
        "tools": ["sql_injection_scanner", "secret_scanner", "authorization_checker"],
        "system_prompt": None,
    },
    {
        "agent_key": "performance",
        "name": "Performance Agent",
        "role": "只关注 N+1 查询、重复 IO、无界查询等性能问题。",
        "kind": "rule",
        "enabled": True,
        "tools": ["n_plus_one_detector", "unbounded_query_detector"],
        "system_prompt": None,
    },
    {
        "agent_key": "style",
        "name": "Style Agent",
        "role": "只关注职责拆分、可维护性、异常路径和测试友好性。",
        "kind": "rule",
        "enabled": True,
        "tools": ["responsibility_checker", "error_handling_checker"],
        "system_prompt": None,
    },
    {
        "agent_key": "llm_security",
        "name": "LLM Security Agent",
        "role": "使用配置的模型从安全角度审查 SQL 注入、XSS、鉴权、敏感信息泄露、供应链风险。",
        "kind": "llm",
        "enabled": True,
        "tools": ["semantic_security_review", "auth_boundary_review", "secret_exposure_review"],
        "system_prompt": "你是 Security Agent，只关注代码安全问题，不评价性能和代码风格。",
    },
    {
        "agent_key": "llm_performance",
        "name": "LLM Performance Agent",
        "role": "使用配置的模型从性能角度审查复杂度、N+1 查询、重复 IO、无界查询、缓存问题。",
        "kind": "llm",
        "enabled": True,
        "tools": ["semantic_performance_review", "query_pattern_review", "scalability_review"],
        "system_prompt": "你是 Performance Agent，只关注性能问题，不评价安全和代码风格。",
    },
    {
        "agent_key": "llm_style",
        "name": "LLM Style Agent",
        "role": "使用配置的模型从可维护性角度审查职责拆分、命名、异常处理、测试友好性。",
        "kind": "llm",
        "enabled": True,
        "tools": ["maintainability_review", "testability_review", "architecture_smell_review"],
        "system_prompt": "你是 Style Agent，只关注工程质量、可维护性和测试友好性，不评价安全和性能。",
    },
]


engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
_initialized = False


def init_store() -> None:
    global _initialized
    if _initialized:
        return
    try:
        _ensure_database_exists()
        Base.metadata.create_all(bind=engine)
        _seed_agent_configs()
        _initialized = True
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def save_review_record(report: ReviewReport, events: list[ReviewEvent] | None = None) -> int:
    init_store()
    payload = report.model_dump(mode="json")
    record = ReviewRecord(
        title=report.title or "代码审查报告",
        repo=report.repo,
        mode=str(report.metadata.get("mode") or "agent"),
        file_count=int(report.metadata.get("file_count") or 0),
        total_findings=report.summary.total_findings,
        top_priority=report.summary.top_priority,
        report_json=json.dumps(payload, ensure_ascii=False),
    )
    try:
        with SessionLocal() as db:
            db.add(record)
            db.commit()
            db.refresh(record)
            if events:
                _save_review_events(db, record.id, events)
            return record.id
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def list_review_records(limit: int = 30, offset: int = 0) -> ReviewHistoryPage:
    init_store()
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    try:
        with SessionLocal() as db:
            total = db.query(ReviewRecord).count()
            rows = (
                db.execute(
                    select(ReviewRecord)
                    .order_by(ReviewRecord.created_at.desc(), ReviewRecord.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
                .scalars()
                .all()
            )
            return ReviewHistoryPage(
                items=[_summary_from_record(row) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
            )
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def get_review_report(record_id: int) -> ReviewReport | None:
    init_store()
    try:
        with SessionLocal() as db:
            record = db.get(ReviewRecord, record_id)
            if record is None:
                return None
            data: dict[str, Any] = json.loads(record.report_json)
            data.setdefault("metadata", {})
            data["metadata"]["record_id"] = record.id
            return ReviewReport.model_validate(data)
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def delete_review_record(record_id: int) -> bool:
    init_store()
    try:
        with SessionLocal() as db:
            record = db.get(ReviewRecord, record_id)
            if record is None:
                return False
            for event in db.execute(
                select(ReviewEventRecord).where(ReviewEventRecord.review_id == record_id)
            ).scalars():
                db.delete(event)
            db.delete(record)
            db.commit()
            return True
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def _summary_from_record(record: ReviewRecord) -> ReviewRecordSummary:
    return ReviewRecordSummary(
        id=record.id,
        title=record.title,
        repo=record.repo,
        mode=record.mode,
        file_count=record.file_count,
        total_findings=record.total_findings,
        top_priority=record.top_priority,
        created_at=record.created_at.isoformat(timespec="seconds"),
    )


def list_review_events(review_id: int) -> list[ReviewEvent]:
    init_store()
    try:
        with SessionLocal() as db:
            rows = (
                db.execute(
                    select(ReviewEventRecord)
                    .where(ReviewEventRecord.review_id == review_id)
                    .order_by(ReviewEventRecord.event_index.asc(), ReviewEventRecord.id.asc())
                )
                .scalars()
                .all()
            )
            return [
                ReviewEvent(
                    type=row.event_type,
                    agent=row.agent,
                    stage=row.stage,
                    message=row.message,
                    metadata=json.loads(row.metadata_json or "{}"),
                )
                for row in rows
            ]
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def list_agent_configs() -> list[AgentConfigRead]:
    init_store()
    try:
        with SessionLocal() as db:
            rows = db.execute(select(AgentConfigRecord).order_by(AgentConfigRecord.id.asc())).scalars().all()
            return [_agent_config_from_record(row) for row in rows]
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def list_enabled_agent_configs() -> list[AgentConfigRead]:
    return [config for config in list_agent_configs() if config.enabled]


def update_agent_config(agent_id: int, update: AgentConfigUpdate) -> AgentConfigRead | None:
    init_store()
    try:
        with SessionLocal() as db:
            record = db.get(AgentConfigRecord, agent_id)
            if record is None:
                return None
            record.name = update.name.strip()
            record.role = update.role.strip()
            record.enabled = 1 if update.enabled else 0
            record.tools_json = json.dumps(update.tools, ensure_ascii=False)
            record.system_prompt = update.system_prompt.strip() if update.system_prompt else None
            record.updated_at = datetime.now()
            db.commit()
            db.refresh(record)
            return _agent_config_from_record(record)
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def create_agent_config(create: AgentConfigCreate) -> AgentConfigRead:
    init_store()
    now = datetime.now()
    record = AgentConfigRecord(
        agent_key=create.agent_key.strip(),
        name=create.name.strip(),
        role=create.role.strip(),
        kind=create.kind.strip(),
        enabled=1 if create.enabled else 0,
        tools_json=json.dumps(create.tools, ensure_ascii=False),
        system_prompt=create.system_prompt.strip() if create.system_prompt else None,
        created_at=now,
        updated_at=now,
    )
    try:
        with SessionLocal() as db:
            db.add(record)
            db.commit()
            db.refresh(record)
            return _agent_config_from_record(record)
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def delete_agent_config(agent_id: int) -> bool:
    init_store()
    try:
        with SessionLocal() as db:
            record = db.get(AgentConfigRecord, agent_id)
            if record is None:
                return False
            db.delete(record)
            db.commit()
            return True
    except SQLAlchemyError as exc:
        raise StoreUnavailableError(_store_error_message(exc)) from exc


def _save_review_events(db: Session, review_id: int, events: list[ReviewEvent]) -> None:
    for idx, event in enumerate(events):
        db.add(
            ReviewEventRecord(
                review_id=review_id,
                event_index=idx,
                event_type=event.type,
                agent=event.agent,
                stage=event.stage,
                message=event.message,
                metadata_json=json.dumps(event.metadata, ensure_ascii=False),
            )
        )
    db.commit()


def _seed_agent_configs() -> None:
    with SessionLocal() as db:
        existing = {row.agent_key for row in db.execute(select(AgentConfigRecord)).scalars().all()}
        changed = False
        for item in DEFAULT_AGENT_CONFIGS:
            if item["agent_key"] in existing:
                continue
            db.add(
                AgentConfigRecord(
                    agent_key=item["agent_key"],
                    name=item["name"],
                    role=item["role"],
                    kind=item["kind"],
                    enabled=1 if item["enabled"] else 0,
                    tools_json=json.dumps(item["tools"], ensure_ascii=False),
                    system_prompt=item["system_prompt"],
                )
            )
            changed = True
        if changed:
            db.commit()


def _agent_config_from_record(record: AgentConfigRecord) -> AgentConfigRead:
    return AgentConfigRead(
        id=record.id,
        agent_key=record.agent_key,
        name=record.name,
        role=record.role,
        kind=record.kind,
        enabled=bool(record.enabled),
        tools=json.loads(record.tools_json or "[]"),
        system_prompt=record.system_prompt,
        created_at=record.created_at.isoformat(timespec="seconds"),
        updated_at=record.updated_at.isoformat(timespec="seconds"),
    )


def _ensure_database_exists() -> None:
    url = make_url(DATABASE_URL)
    if url.get_backend_name() != "mysql" or not url.database:
        return
    server_url = url.set(database="")
    server_engine = create_engine(server_url, pool_pre_ping=True)
    quoted_database = f"`{url.database.replace('`', '``')}`"
    try:
        with server_engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS {quoted_database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        server_engine.dispose()


def _store_error_message(exc: Exception) -> str:
    return (
        "MySQL 审查记录库不可用。请确认已创建数据库并启动 MySQL："
        "CREATE DATABASE code_review_multiagent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; "
        f"连接地址：{DATABASE_URL}。原始错误：{exc}"
    )
