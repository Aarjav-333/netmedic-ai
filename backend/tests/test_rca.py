"""Root-cause analysis: every fault signature must map to the right cause and target."""

import pytest

from app.diagnosis.planner import simulate_avoidance
from app.diagnosis.rules import soft
from app.engine import SimulationEngine
from app.models.detection import ComponentKind
from app.models.diagnosis import ActionType, RiskLevel, RootCause
from app.models.faults import FaultType, Severity


@pytest.fixture(scope="module")
def engine() -> SimulationEngine:
    return SimulationEngine()


def diagnose_after(engine: SimulationEngine, fault_type: FaultType, target: str, severity=Severity.MEDIUM, ticks: int = 3):
    engine.reset()
    for _ in range(8):
        engine.tick()
    engine.faults.inject(fault_type, target, severity)
    for _ in range(ticks):
        engine.tick()
    return engine.diagnosis


@pytest.mark.parametrize(
    ("fault", "target", "expected_cause", "expected_action"),
    [
        (FaultType.ROUTER_CONGESTION, "R4", RootCause.ROUTER_CONGESTION, ActionType.REROUTE_AROUND_NODE),
        (FaultType.NODE_OVERLOAD, "R2", RootCause.NODE_OVERLOAD, ActionType.RESTART_NODE),
        (FaultType.TRAFFIC_SPIKE, "SW3", RootCause.TRAFFIC_SPIKE, ActionType.RATE_LIMIT_SOURCE),
        (FaultType.BANDWIDTH_DEGRADATION, "L-R4-SW3", RootCause.BANDWIDTH_SATURATION, ActionType.REROUTE_AROUND_LINK),
        (FaultType.PACKET_LOSS_SPIKE, "L-R1-R3", RootCause.PACKET_LOSS_SPIKE, ActionType.REROUTE_AROUND_LINK),
        (FaultType.LINK_FAILURE, "L-R4-SW3", RootCause.LINK_FAILURE, ActionType.ISOLATE_LINK),
        (FaultType.ROUTER_FAILURE, "R4", RootCause.NODE_FAILURE, ActionType.REROUTE_AROUND_NODE),
    ],
)
def test_root_cause_matches_injected_fault(engine, fault, target, expected_cause, expected_action):
    diagnosis = diagnose_after(engine, fault, target)
    assert diagnosis is not None
    assert diagnosis.target_id == target
    assert diagnosis.root_cause == expected_cause
    assert diagnosis.plan.action == expected_action
    assert 0.3 <= diagnosis.confidence <= 1.0
    assert diagnosis.evidence, "evidence must never be empty"
    assert diagnosis.hypotheses[0].root_cause == expected_cause


def test_congestion_diagnosis_is_explainable(engine):
    d = diagnose_after(engine, FaultType.ROUTER_CONGESTION, "R4")
    assert d.confidence >= 0.6
    assert "confidence = " in d.confidence_explanation
    joined = " ".join(d.evidence).lower()
    assert "latency increased" in joined
    assert "cpu increased" in joined
    assert "neighbouring nodes" in joined
    assert set(d.affected_flows) == {"F3", "F4", "F5"}
    assert d.plan.risk == RiskLevel.LOW
    assert d.plan.parameters["penalty_ms"] > 0
    # No fault-injector vocabulary leaks (the RCA has its own root-cause names).
    assert "fault" not in d.model_dump_json().lower().replace("default", "")


def test_traffic_spike_prefers_source_over_downstream_router(engine):
    d = diagnose_after(engine, FaultType.TRAFFIC_SPIKE, "SW3")
    scores = {(h.root_cause, h.target_id): h.score for h in d.hypotheses}
    assert d.target_id == "SW3"
    assert scores[(RootCause.TRAFFIC_SPIKE, "SW3")] > scores.get((RootCause.BANDWIDTH_SATURATION, "L-R4-SW3"), 0)
    assert scores[(RootCause.TRAFFIC_SPIKE, "SW3")] > scores.get((RootCause.ROUTER_CONGESTION, "R4"), 0)


def test_core_router_without_alternative_escalates(engine):
    d = diagnose_after(engine, FaultType.ROUTER_CONGESTION, "R1", Severity.HIGH)
    assert d.root_cause == RootCause.ROUTER_CONGESTION
    assert d.plan.action == ActionType.ESCALATE
    assert d.plan.risk == RiskLevel.HIGH


def test_healthy_network_has_no_diagnosis(engine):
    engine.reset()
    for _ in range(10):
        engine.tick()
    assert engine.diagnosis is None


def test_simulate_avoidance_does_not_mutate_network(engine):
    engine.reset()
    before = {k: v.penalty_ms for k, v in engine.network.nodes.items()}
    paths = simulate_avoidance(engine.network, "R4", ComponentKind.NODE, ["F3", "F1"])
    assert paths["F3"] == ["SW3", "R3", "R1", "GW"]
    assert paths["F1"] == ["SW1", "R2", "R1", "GW"]
    assert {k: v.penalty_ms for k, v in engine.network.nodes.items()} == before


def test_soft_threshold():
    assert soft(50, 75, 100) == 0.0
    assert soft(87.5, 75, 100) == 0.5
    assert soft(200, 75, 100) == 1.0
