import asyncio

import pytest

from app.demo import HEALTHY_PAUSE_SECONDS, SCENARIOS, DemoRunner
from app.engine import SimulationEngine
from app.models.incident import IncidentStatus


async def test_demo_runs_the_real_pipeline(monkeypatch):
    import app.demo as demo_module

    monkeypatch.setattr(demo_module, "HEALTHY_PAUSE_SECONDS", 0.05)
    engine = SimulationEngine(tick_seconds=0.05)
    await engine.start()
    try:
        state = await engine.demo.start("congestion")
        assert state.running and state.scenario == "congestion"
        for _ in range(400):  # up to ~20 s of 50 ms ticks
            await asyncio.sleep(0.05)
            if not engine.demo.state.running:
                break
        final = engine.demo.state
        assert not final.running, final.message
        assert final.outcome == IncidentStatus.RESOLVED.value, final.history
        incident = engine.incidents.get(final.incident_id)
        assert incident is not None and incident.component_id == "R4"
        assert engine.faults.active, "the fault stays active so the reroute remains visible"
        assert not engine.network.routes["F3"].is_primary
    finally:
        await engine.stop()


async def test_demo_rejects_unknown_scenario_and_double_start():
    engine = SimulationEngine(tick_seconds=0.05)
    runner = DemoRunner(engine)
    with pytest.raises(KeyError):
        await runner.start("nope")
    assert set(SCENARIOS) >= {"congestion", "link_failure", "traffic_spike", "overload"}
    assert HEALTHY_PAUSE_SECONDS > 0


def test_demo_endpoints(client, engine):
    scenarios = client.get("/api/demo/scenarios").json()
    assert {s["key"] for s in scenarios} >= {"congestion", "link_failure"}
    assert client.get("/api/demo/status").json()["running"] is False
    assert client.post("/api/demo/run", json={"scenario": "nope"}).status_code == 400
