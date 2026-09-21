"""SQLAlchemy ORM tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    component_id: Mapped[str] = mapped_column(String(32), index=True)
    component_kind: Mapped[str] = mapped_column(String(16))
    anomaly_score: Mapped[float] = mapped_column(Float)
    root_cause: Mapped[str | None] = mapped_column(String(48), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    remediation: Mapped[str | None] = mapped_column(String(48), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    diagnosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remediated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recovery_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)  # full Incident schema for exact restoration

    actions: Mapped[list["HealingActionRow"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    events: Mapped[list["IncidentEventRow"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class HealingActionRow(Base):
    __tablename__ = "healing_actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(48))
    target_id: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[str] = mapped_column(String(16))
    details: Mapped[str] = mapped_column(Text, default="")
    route_changes: Mapped[list] = mapped_column(JSON, default=list)

    incident: Mapped[IncidentRow] = relationship(back_populates="actions")


class IncidentEventRow(Base):
    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tick: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)

    incident: Mapped[IncidentRow] = relationship(back_populates="events")


class TelemetrySnapshotRow(Base):
    """Periodic network-level summary (not every sample) to keep the database small."""

    __tablename__ = "telemetry_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    health_score: Mapped[float] = mapped_column(Float)
    avg_latency_ms: Mapped[float] = mapped_column(Float)
    avg_packet_loss_percent: Mapped[float] = mapped_column(Float)
    total_throughput_mbps: Mapped[float] = mapped_column(Float)
    active_nodes: Mapped[int] = mapped_column(Integer)
    summary: Mapped[dict] = mapped_column(JSON)
