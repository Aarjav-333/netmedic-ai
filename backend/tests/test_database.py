"""SQLite persistence of incidents and telemetry snapshots."""

from pathlib import Path

import pytest

from app.database.repository import Database
from app.engine import SimulationEngine
from app.models.faults import FaultType
from app.models.incident import IncidentStatus


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


def test_incident_round_trip_and_reload(db_url):
    engine = SimulationEngine(database_url=db_url)
    assert engine.db is not None and engine.db.count_incidents() == 0
    for _ in range(8):
        engine.tick()
    engine.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    for _ in range(16):
        engine.tick()
    incident = engine.incidents.closed[0]
    assert incident.status == IncidentStatus.RESOLVED
    assert engine.db.count_incidents() == 1

    # A fresh engine on the same database reloads the history with full detail.
    reloaded = SimulationEngine(database_url=db_url)
    assert [i.id for i in reloaded.incidents.closed] == [incident.id]
    restored = reloaded.incidents.closed[0]
    assert restored.status == IncidentStatus.RESOLVED
    assert restored.recovery.after.health_score == incident.recovery.after.health_score
    assert len(restored.timeline) == len(incident.timeline)
    assert restored.actions[0].route_changes[0].flow_id == incident.actions[0].route_changes[0].flow_id
    assert restored.ai_explanation is not None

    # Child tables are populated too.
    with reloaded.db.session() as session:
        from app.database.models import HealingActionRow, IncidentEventRow

        assert session.query(HealingActionRow).count() >= 1
        assert session.query(IncidentEventRow).count() == len(incident.timeline)


def test_snapshots_are_recorded_periodically_and_pruned(db_url):
    db = Database(db_url)
    engine = SimulationEngine(database_url=db_url)
    for _ in range(25):
        engine.tick()
    rows = db.recent_snapshots()
    assert [r.tick for r in rows] == [10, 20]
    assert rows[-1].health_score > 0
    assert db.prune_snapshots(keep=1) == 1
    assert len(db.recent_snapshots()) == 1


def test_relative_sqlite_url_is_anchored_to_backend_dir():
    from app.config import BACKEND_DIR
    from app.database.repository import resolve_database_url

    resolved = resolve_database_url("sqlite:///./data/x.db")
    assert resolved.startswith("sqlite:///")
    assert Path(resolved[len("sqlite:///"):]).resolve().parent == (BACKEND_DIR / "data").resolve()
    assert resolve_database_url("sqlite:////tmp/abs.db") == "sqlite:////tmp/abs.db"
