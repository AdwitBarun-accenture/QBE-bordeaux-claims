"""Application database tables.

Raw files and row-level datasets live in blob storage (immutable); the DB holds
metadata, pipeline state, HITL decisions, memory and the audit trail.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str] = mapped_column(String(4))
    role: Mapped[str] = mapped_column(String(32))  # analyst | underwriter | admin
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Coverholder(Base):
    __tablename__ = "coverholders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)        # filename prefixes, sender domains
    class_of_business: Mapped[str] = mapped_column(String(64), default="")
    da_limit_gbp: Mapped[float] = mapped_column(Float, default=0)
    date_order: Mapped[str] = mapped_column(String(3), default="dmy")  # dmy | mdy
    has_password: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_emails: Mapped[list] = mapped_column(JSON, default=list)


class BdxFile(Base):
    """One received bordereaux file = one row in the BDX Inbox."""
    __tablename__ = "bdx_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    coverholder_id: Mapped[str | None] = mapped_column(ForeignKey("coverholders.id"), nullable=True)
    coverholder_name: Mapped[str] = mapped_column(String(200), default="Unknown")
    filename: Mapped[str] = mapped_column(String(400))
    file_type: Mapped[str] = mapped_column(String(16), default="premium")   # premium | claims
    source: Mapped[str] = mapped_column(String(16), default="upload")       # email | sftp | upload
    source_ref: Mapped[str] = mapped_column(String(400), default="")        # message id / sftp path
    raw_uri: Mapped[str] = mapped_column(String(600), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    sla_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # received | running | awaiting-password | awaiting-mapping | awaiting-exceptions
    # awaiting-load | processed | rejected | failed | duplicate
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    hitl_gate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    quality: Mapped[int] = mapped_column(Integer, default=0)
    password_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    latest_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="file", cascade="all, delete-orphan")


class PipelineRun(Base):
    """State of one pass of the 6-stage pipeline over a file. Each stage's output
    is stored as JSON so the UI can render any stage and the audit is complete."""
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    file_id: Mapped[str] = mapped_column(ForeignKey("bdx_files.id"), index=True)
    correlation_id: Mapped[str] = mapped_column(String(32), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default="ingest")   # last completed stage
    status: Mapped[str] = mapped_column(String(32), default="running")

    ingestion: Mapped[dict] = mapped_column(JSON, default=dict)        # metadata, sheet, headers, memory recall
    mappings: Mapped[list] = mapped_column(JSON, default=list)
    structural_change: Mapped[dict] = mapped_column(JSON, default=dict)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)       # checks, scores, ai_findings
    enrichment: Mapped[dict] = mapped_column(JSON, default=dict)       # steps + lineage summary
    freetext: Mapped[dict] = mapped_column(JSON, default=dict)
    reconciliation: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    resolution_guidance: Mapped[str] = mapped_column(Text, default="")
    load_result: Mapped[dict] = mapped_column(JSON, default=dict)

    file: Mapped[BdxFile] = relationship(back_populates="runs")
    exceptions: Mapped[list["DataException"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class DataException(Base):
    __tablename__ = "data_exceptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(10))       # high | medium | low
    count: Mapped[int] = mapped_column(Integer, default=0)
    row_indexes: Mapped[list] = mapped_column(JSON, default=list)
    suggestion: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="rule")  # rule | ai
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved | waived
    resolved_by: Mapped[str] = mapped_column(String(120), default="")
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[PipelineRun] = relationship(back_populates="exceptions")


class HitlDecision(Base):
    __tablename__ = "hitl_decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    gate: Mapped[int] = mapped_column(Integer)                # 1 mapping, 2 exceptions, 3 load
    decision: Mapped[str] = mapped_column(String(16))         # approved | rejected | auto
    user_email: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------- Memory layer ----------------
class SemanticMapping(Base):
    """Human-approved source-column -> LCRS pairs per coverholder (auto-applied next run)."""
    __tablename__ = "semantic_mappings"
    __table_args__ = (UniqueConstraint("coverholder_name", "file_type", "source_column"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    coverholder_name: Mapped[str] = mapped_column(String(200), index=True)
    file_type: Mapped[str] = mapped_column(String(16))
    source_column: Mapped[str] = mapped_column(String(200))
    canonical: Mapped[str] = mapped_column(String(100))
    origin: Mapped[str] = mapped_column(String(16))           # auto | human | formula
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    formula: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved_by: Mapped[str] = mapped_column(String(255), default="")
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EpisodicMemory(Base):
    """One record per completed run: what happened last time for this coverholder."""
    __tablename__ = "episodic_memory"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    coverholder_name: Mapped[str] = mapped_column(String(200), index=True)
    file_type: Mapped[str] = mapped_column(String(16))
    file_id: Mapped[str] = mapped_column(String(32))
    run_id: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(400))
    headers: Mapped[list] = mapped_column(JSON, default=list)
    headers_signature: Mapped[str] = mapped_column(String(16), default="")
    quality: Mapped[int] = mapped_column(Integer, default=0)
    exception_count: Mapped[int] = mapped_column(Integer, default=0)
    exception_titles: Mapped[list] = mapped_column(JSON, default=list)
    hitl: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(16), default="loaded")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OperationalLog(Base):
    """Every agent action: timing, tokens, model, correlation id (audit + cost governance)."""
    __tablename__ = "operational_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    correlation_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    run_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    file_id: Mapped[str] = mapped_column(String(32), default="")
    agent: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(10), default="info")   # info | warn | error | hitl
    model: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class ConnectorState(Base):
    """Remembers what has already been pulled from email/SFTP (idempotent polling)."""
    __tablename__ = "connector_state"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    connector: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(500), index=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
