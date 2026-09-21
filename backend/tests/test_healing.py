"""Self-healing engine, recovery verification and the incident state machine."""

import pytest

from app.engine import SimulationEngine
from app.healing.engine import RESTORE_CLEAN_TICKS
from app.healing.verifier import MetricWindow, verify
from app.models.diagnosis import ActionType
from app.models.faults import FaultType, Severity
from app.models.incident import IncidentStatus
from app.models.network import AdminStatus


@pytest.fixture(scope="module")
def engine() -> SimulationEngine:
    return SimulationEngine()


def run_incident(engine: SimulationEngine, fault: FaultType, target: str, severity=Severity.MEDIUM, max_ticks: int = 30):
    engine.reset()
    engine.incidents.auto_heal = True
    for _ in range(8):
        engine.tick()
    engine.faults.inject(fault, target, severity)
    closed_before = len(engine.incidents.closed)
    statuses: list[IncidentStatus] = []
    for _ in range(max_ticks):
        engine.tick()
        if engine.incidents.active and (not statuses or statuses[-1] != engine.incidents.active.status):
            statuses.append(engine.incidents.active.status)
        if len(engine.incidents.closed) > closed_before and engine.incidents.active is None:
            incident = engine.incidents.closed[0]
            statuses.append(incident.status)
            return incident, statuses
    raise AssertionError(f"incident did not close; statuses={statuses}")


def test_congestion_incident_walks_the_full_state_machine(engine):
    incident, statuses = run_incident(engine, FaultType.ROUTER_CONGESTION, "R4")
    assert statuses == [
        IncidentStatus.DETECTED,
        IncidentStatus.ANALYZING,
        IncidentStatus.DIAGNOSED,
        IncidentStatus.REMEDIATING,
        IncidentStatus.VERIFYING,
        IncidentStatus.RESOLVED,
    ]
    assert incident.component_id == "R4"
    assert incident.plan.action == ActionType.REROUTE_AROUND_NODE
    action = incident.actions[0]
    assert action.result == "applied"
    assert {c.flow_id for c in action.route_changes} == {"F3", "F4", "F5"}
    assert all("R4" not in c.after for c in action.route_changes)
    # Rerouting is real: the simulator's routing table changed.
    assert engine.network.routes["F3"].path == ["SW3", "R3", "R1", "GW"]
    assert engine.network.nodes["R4"].isolated
    # Verification compares windows and every check passed.
    assert incident.recovery.status == IncidentStatus.RESOLVED
    assert all(c.passed for c in incident.recovery.checks)
    assert incident.recovery.before.avg_latency_ms > 100
    assert incident.recovery.after.avg_latency_ms < 40
    assert incident.recovery.after.health_score > 90
    assert incident.recovery.baseline is not None and incident.recovery.baseline.samples == 5
    # Timing metrics are populated.
    m = incident.metrics
    assert m.time_to_detect_s is not None and m.recovery_time_s is not None and m.total_duration_s is not None
    stages = [e.stage for e in incident.timeline]
    assert stages[0] == IncidentStatus.DETECTED and stages[-1] == IncidentStatus.RESOLVED
    assert any("Traffic rerouted: F3" in e.message for e in incident.timeline)


@pytest.mark.parametrize(
    ("fault", "target", "action"),
    [
        (FaultType.TRAFFIC_SPIKE, "SW3", ActionType.RATE_LIMIT_SOURCE),
        (FaultType.LINK_FAILURE, "L-R4-SW3", ActionType.ISOLATE_LINK),
        (FaultType.BANDWIDTH_DEGRADATION, "L-R4-SW3", ActionType.REROUTE_AROUND_LINK),
        (FaultType.PACKET_LOSS_SPIKE, "L-R1-R3", ActionType.REROUTE_AROUND_LINK),
        (FaultType.ROUTER_FAILURE, "R4", ActionType.REROUTE_AROUND_NODE),
    ],
)
def test_other_faults_are_healed_and_verified(engine, fault, target, action):
    incident, _ = run_incident(engine, fault, target)
    assert incident.plan.action == action
    assert incident.status == IncidentStatus.RESOLVED, incident.recovery.summary
    assert incident.recovery.after.health_score >= 85


def test_rate_limit_actually_caps_flows(engine):
    incident, _ = run_incident(engine, FaultType.TRAFFIC_SPIKE, "SW3")
    assert engine.network.flows["F3"].rate_limit_mbps is not None
    assert engine.latest.node("SW3").bandwidth_utilization_percent < 85


def test_node_overload_restart_clears_condition_and_restores(engine):
    incident, _ = run_incident(engine, FaultType.NODE_OVERLOAD, "R2", Severity.HIGH)
    assert incident.plan.action == ActionType.RESTART_NODE
    assert incident.status == IncidentStatus.RESOLVED
    assert engine.network.nodes["R2"].status == AdminStatus.UP
    # The restart cleared the runaway process; quarantine lifts once telemetry stays clean.
    for _ in range(RESTORE_CLEAN_TICKS + 12):
        engine.tick()
    assert not engine.healing.is_quarantined("R2")
    assert engine.network.routes["F1"].is_primary
    assert any(a.result == "restored" for a in incident.actions)
    assert any("primary routes restored" in e.message for e in incident.timeline)


def test_no_alternative_path_escalates_and_fails_honestly(engine):
    incident, statuses = run_incident(engine, FaultType.ROUTER_CONGESTION, "R1", Severity.HIGH)
    assert incident.plan.action == ActionType.ESCALATE
    assert incident.status == IncidentStatus.FAILED
    assert incident.recovery is None
    assert incident.actions[0].result == "skipped"


def test_manual_mode_waits_for_operator(engine):
    engine.reset()
    engine.incidents.auto_heal = False
    for _ in range(8):
        engine.tick()
    engine.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    for _ in range(6):
        engine.tick()
    incident = engine.incidents.active
    assert incident is not None and incident.status == IncidentStatus.DIAGNOSED
    with pytest.raises(KeyError):
        engine.incidents.request_healing("nope")
    # Approve and let it run.
    engine.incidents.request_healing(incident.id)
    for _ in range(12):
        engine.tick()
    assert engine.incidents.closed[0].status == IncidentStatus.RESOLVED
    engine.incidents.auto_heal = True


def test_quarantined_component_does_not_reopen_incidents(engine):
    incident, _ = run_incident(engine, FaultType.ROUTER_CONGESTION, "R4")
    closed = len(engine.incidents.closed)
    for _ in range(10):
        engine.tick()
    assert engine.incidents.active is None
    assert len(engine.incidents.closed) == closed
    assert engine.healing.is_quarantined("R4")


def test_reset_cancels_active_incident_and_clears_healing(engine):
    engine.reset()
    for _ in range(8):
        engine.tick()
    engine.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    for _ in range(3):
        engine.tick()
    assert engine.incidents.active is not None
    engine.reset()
    assert engine.incidents.active is None
    assert engine.incidents.closed[0].status == IncidentStatus.CANCELLED
    assert not engine.healing.quarantined_ids()
    assert all(r.is_primary for r in engine.network.routes.values())


def test_verify_classifies_outcomes():
    base = MetricWindow(samples=5, health_score=100, avg_latency_ms=12, avg_packet_loss_percent=0.6, affected_flows_healthy=3, affected_flows_total=3)
    before = MetricWindow(samples=3, health_score=74, avg_latency_ms=210, avg_packet_loss_percent=15, affected_flows_healthy=0, affected_flows_total=3)
    good = MetricWindow(samples=3, health_score=98, avg_latency_ms=22, avg_packet_loss_percent=0.5, affected_flows_healthy=3, affected_flows_total=3)
    partial = MetricWindow(samples=3, health_score=88, avg_latency_ms=60, avg_packet_loss_percent=3.0, affected_flows_healthy=2, affected_flows_total=3)
    bad = MetricWindow(samples=3, health_score=75, avg_latency_ms=200, avg_packet_loss_percent=14, affected_flows_healthy=0, affected_flows_total=3)
    assert verify(base, before, good).status == IncidentStatus.RESOLVED
    assert verify(base, before, partial).status == IncidentStatus.PARTIALLY_RESOLVED
    assert verify(base, before, bad).status == IncidentStatus.FAILED
    report = verify(None, before, good)
    assert report.status == IncidentStatus.RESOLVED and len(report.checks) == 4
