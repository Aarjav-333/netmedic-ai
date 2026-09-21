"""SQLite persistence for incidents, healing actions, events and telemetry snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import BACKEND_DIR
from app.database.models import Base, HealingActionRow, IncidentEventRow, IncidentRow, TelemetrySnapshotRow
from app.logging_config import get_logger
from app.models.incident import Incident
from app.models.telemetry import TelemetrySnapshot

log = get_logger("netmedic.db")

SNAPSHOT_EVERY_TICKS = 10  # ~15 s at the default tick rate
SNAPSHOT_KEEP = 2000  # rows kept (~8 h of history)


def resolve_database_url(url: str) -> str:
    """Anchor relative SQLite paths to the backend directory regardless of CWD."""
    prefix = "sqlite:///./"
    if url.startswith(prefix):
        path = (BACKEND_DIR / url[len(prefix):]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"
    return url


class Database:
    def __init__(self, url: str) -> None:
        self.url = resolve_database_url(url)
        self.engine: Engine = create_engine(self.url, future=True, connect_args={"check_same_thread": False})
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        log.info("[DB] SQLite ready at %s", self.url)

    def session(self) -> Session:
        return self.session_factory()

    # ---------------------------------------------------------- incidents
    def upsert_incident(self, incident: Incident) -> None:
        with self.session() as db:
            row = db.get(IncidentRow, incident.id)
            if row is None:
                row = IncidentRow(id=incident.id, started_at=incident.detected_at)
                db.add(row)
            row.status = incident.status.value
            row.component_id = incident.component_id
            row.component_kind = incident.component_kind.value
            row.anomaly_score = incident.anomaly_severity
            row.root_cause = incident.root_cause.value if incident.root_cause else None
            row.confidence = incident.confidence
            row.remediation = incident.plan.action.value if incident.plan else None
            row.diagnosed_at = incident.diagnosed_at
            row.remediated_at = incident.remediated_at
            row.resolved_at = incident.resolved_at
            row.recovery_status = incident.recovery.status.value if incident.recovery else None
            row.recovery_time_s = incident.metrics.recovery_time_s
            row.total_duration_s = incident.metrics.total_duration_s
            row.payload = incident.model_dump(mode="json")
            # Replace child rows wholesale; they are small and always derived from the payload.
            db.execute(delete(HealingActionRow).where(HealingActionRow.incident_id == incident.id))
            db.execute(delete(IncidentEventRow).where(IncidentEventRow.incident_id == incident.id))
            for action in incident.actions:
                db.add(
                    HealingActionRow(
                        id=action.id,
                        incident_id=incident.id,
                        action=action.action.value,
                        target_id=action.target_id,
                        timestamp=action.started_at,
                        result=action.result,
                        details=action.details,
                        route_changes=[c.model_dump() for c in action.route_changes],
                    )
                )
            for event in incident.timeline:
                db.add(
                    IncidentEventRow(
                        incident_id=incident.id,
                        timestamp=event.timestamp,
                        tick=event.tick,
                        stage=event.stage.value,
                        message=event.message,
                    )
                )
            db.commit()

    def load_incidents(self, limit: int = 100) -> list[Incident]:
        """Most recent incidents first, rebuilt from the stored payload."""
        with self.session() as db:
            rows = db.execute(select(IncidentRow).order_by(IncidentRow.started_at.desc()).limit(limit)).scalars().all()
        incidents: list[Incident] = []
        for row in rows:
            try:
                incidents.append(Incident.model_validate(row.payload))
            except Exception:  # noqa: BLE001 - schema drift in old rows must not break boot
                log.warning("[DB] Skipping incident %s: payload incompatible with current schema", row.id)
        return incidents

    def count_incidents(self) -> int:
        with self.session() as db:
            return len(db.execute(select(IncidentRow.id)).all())

    # ---------------------------------------------------------- telemetry
    def record_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        with self.session() as db:
            db.add(
                TelemetrySnapshotRow(
                    tick=snapshot.tick,
                    timestamp=snapshot.timestamp,
                    health_score=snapshot.summary.health_score,
                    avg_latency_ms=snapshot.summary.avg_latency_ms,
                    avg_packet_loss_percent=snapshot.summary.avg_packet_loss_percent,
                    total_throughput_mbps=snapshot.summary.total_throughput_mbps,
                    active_nodes=snapshot.summary.active_nodes,
                    summary=snapshot.summary.model_dump(mode="json"),
                )
            )
            db.commit()

    def prune_snapshots(self, keep: int = SNAPSHOT_KEEP) -> int:
        with self.session() as db:
            ids = db.execute(select(TelemetrySnapshotRow.id).order_by(TelemetrySnapshotRow.id.desc())).scalars().all()
            stale = ids[keep:]
            if stale:
                db.execute(delete(TelemetrySnapshotRow).where(TelemetrySnapshotRow.id.in_(stale)))
                db.commit()
            return len(stale)

    def recent_snapshots(self, limit: int = 100) -> list[TelemetrySnapshotRow]:
        with self.session() as db:
            rows = db.execute(
                select(TelemetrySnapshotRow).order_by(TelemetrySnapshotRow.id.desc()).limit(limit)
            ).scalars().all()
        return list(reversed(rows))

    # ---------------------------------------------------------------- misc
    def clear_all(self) -> None:
        with self.session() as db:
            for table in (IncidentEventRow, HealingActionRow, IncidentRow, TelemetrySnapshotRow):
                db.execute(delete(table))
            db.commit()

    @property
    def path(self) -> Path | None:
        if self.url.startswith("sqlite:///"):
            return Path(self.url[len("sqlite:///"):])
        return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
