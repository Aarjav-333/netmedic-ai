"""Fault injection: each fault type must produce the expected physical symptoms."""

import pytest

from app.engine import SimulationEngine
from app.models.faults import FaultType, Severity
from app.models.network import AdminStatus, HealthStatus
from app.models.telemetry import FlowStatus
from app.simulation.faults import FaultInjectionError


@pytest.fixture
def eng() -> SimulationEngine:
    engine = SimulationEngine()
    engine.reset()
    return engine


def settle(engine: SimulationEngine, ticks: int = 4):
    snap = None
    for _ in range(ticks):
        snap = engine.tick()
    return snap


def test_router_congestion_symptoms(eng):
    eng.faults.inject(FaultType.ROUTER_CONGESTION, "R4", Severity.MEDIUM)
    snap = settle(eng)
    r4 = snap.node("R4")
    assert r4.health == HealthStatus.CRITICAL
    assert r4.bandwidth_utilization_percent > 95
    assert r4.cpu_percent > 85
    assert r4.latency_ms > 120
    assert r4.packet_loss_percent > 5
    # Neighbours stay healthy - the signature RCA will rely on.
    assert snap.node("R1").health == HealthStatus.HEALTHY
    assert snap.node("R3").health == HealthStatus.HEALTHY
    assert snap.flow("F3").health == HealthStatus.CRITICAL


def test_node_overload_keeps_links_healthy(eng):
    eng.faults.inject(FaultType.NODE_OVERLOAD, "R2", Severity.HIGH)
    snap = settle(eng)
    r2 = snap.node("R2")
    assert r2.cpu_percent > 90
    assert r2.memory_percent > 80
    assert r2.bandwidth_utilization_percent < 60  # links are not the problem
    assert all(l.health == HealthStatus.HEALTHY for l in snap.links if "R2" in (l.source, l.target))


def test_link_failure_cuts_flows(eng):
    eng.faults.inject(FaultType.LINK_FAILURE, "L-R4-SW3")
    snap = settle(eng, 2)
    assert eng.network.links["L-R4-SW3"].status == AdminStatus.DOWN
    assert snap.link("L-R4-SW3").status == AdminStatus.DOWN
    assert snap.flow("F3").status == FlowStatus.DOWN
    assert snap.flow("F5").status == FlowStatus.DOWN
    assert snap.summary.broken_flows == 2


def test_packet_loss_spike_on_link(eng):
    eng.faults.inject(FaultType.PACKET_LOSS_SPIKE, "L-R1-R3", Severity.MEDIUM)
    snap = settle(eng)
    assert snap.link("L-R1-R3").packet_loss_percent > 8
    assert snap.flow("F2").packet_loss_percent > 8  # SW2 -> R3 -> R1 -> GW
    assert snap.flow("F1").packet_loss_percent < 2


def test_bandwidth_degradation_saturates_link(eng):
    eng.faults.inject(FaultType.BANDWIDTH_DEGRADATION, "L-R4-SW3", Severity.MEDIUM)
    snap = settle(eng)
    link = snap.link("L-R4-SW3")
    assert link.capacity_mbps < 500
    assert link.utilization_percent > 100
    assert link.health == HealthStatus.CRITICAL
    assert snap.flow("F3").health != HealthStatus.HEALTHY


def test_traffic_spike_multiplies_source_demand(eng):
    eng.faults.inject(FaultType.TRAFFIC_SPIKE, "SW3", Severity.MEDIUM)
    snap = settle(eng)
    sw3 = snap.node("SW3")
    assert sw3.bandwidth_utilization_percent > 100
    assert sw3.active_connections > 300
    assert snap.link("L-R4-SW3").utilization_percent > 100


def test_router_failure_takes_node_offline(eng):
    eng.faults.inject(FaultType.ROUTER_FAILURE, "R4")
    snap = settle(eng, 2)
    assert snap.node("R4").health == HealthStatus.OFFLINE
    assert snap.summary.active_nodes == 9
    assert snap.flow("F3").status == FlowStatus.DOWN


def test_invalid_targets_are_rejected(eng):
    with pytest.raises(FaultInjectionError):
        eng.faults.inject(FaultType.LINK_FAILURE, "R4")
    with pytest.raises(FaultInjectionError):
        eng.faults.inject(FaultType.ROUTER_CONGESTION, "L-R4-SW3")
    with pytest.raises(FaultInjectionError):
        eng.faults.inject(FaultType.TRAFFIC_SPIKE, "R4")  # only switches
    eng.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    with pytest.raises(FaultInjectionError):
        eng.faults.inject(FaultType.ROUTER_CONGESTION, "R4")  # duplicate


def test_clear_restores_admin_status_and_reset_clears_everything(eng):
    fault = eng.faults.inject(FaultType.LINK_FAILURE, "L-R1-R3")
    eng.faults.clear(fault.id, reason="operator")
    assert eng.network.links["L-R1-R3"].status == AdminStatus.UP
    eng.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    eng.faults.inject(FaultType.ROUTER_FAILURE, "R2")
    cleared = eng.reset()
    assert cleared == 2
    assert eng.network.nodes["R2"].status == AdminStatus.UP
    assert not eng.faults.active
    assert eng.latest.summary.health_score > 95


def test_fault_expiry(eng):
    from datetime import datetime, timedelta, timezone

    fault = eng.faults.inject(FaultType.ROUTER_CONGESTION, "R4", duration_seconds=5)
    assert eng.faults.expire(datetime.now(timezone.utc)) == []
    expired = eng.faults.expire(datetime.now(timezone.utc) + timedelta(seconds=6))
    assert [f.id for f in expired] == [fault.id]
    assert not eng.faults.active


def test_effects_never_expose_fault_labels(eng):
    eng.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    fx = eng.faults.effects()
    # The effects structure carries physics only - no fault type, no label.
    assert not hasattr(fx.node("R4"), "fault_type")
    assert fx.node("R4").extra_load_mbps > 0
