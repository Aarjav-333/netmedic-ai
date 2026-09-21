"""Isolation Forest anomaly detection."""

import pandas as pd
import pytest

from app.detection.detector import CONFIRM_TICKS, AnomalyDetector, compute_deviations
from app.detection.features import FEATURE_NAMES, node_feature_vector
from app.detection.trainer import generate_normal_dataset, train_model
from app.engine import SimulationEngine
from app.models.detection import ComponentKind
from app.models.faults import FaultType, Severity


@pytest.fixture(scope="module")
def engine() -> SimulationEngine:
    return SimulationEngine()  # trains or loads the persisted model


def warm(engine: SimulationEngine, ticks: int = 8) -> None:
    engine.reset()
    for _ in range(ticks):
        engine.tick()


def test_training_dataset_and_model():
    dataset = generate_normal_dataset(ticks=40, seeds=(1, 2))
    assert isinstance(dataset, pd.DataFrame)
    assert len(dataset) == 40 * 2 * 10
    assert set(FEATURE_NAMES) <= set(dataset.columns)
    model, meta = train_model(dataset)
    assert meta.n_samples == len(dataset)
    assert meta.severity_span > 0
    # Healthy data must be mostly inside the threshold.
    decisions = model.decision_function(dataset[list(FEATURE_NAMES)].to_numpy())
    assert (decisions < meta.threshold).mean() < 0.02


def test_feature_vector_shape(engine):
    snap = engine.tick()
    vec = node_feature_vector(snap.nodes[0], engine.network.nodes[snap.nodes[0].node_id])
    assert vec.shape == (len(FEATURE_NAMES),)


def test_healthy_network_produces_no_confirmed_anomalies(engine):
    warm(engine, 2)
    confirmed = 0
    for _ in range(40):
        engine.tick()
        confirmed += len(engine.detection.confirmed_ids)
    assert confirmed == 0


def test_congestion_is_detected_with_evidence(engine):
    warm(engine)
    engine.faults.inject(FaultType.ROUTER_CONGESTION, "R4", Severity.MEDIUM)
    for _ in range(CONFIRM_TICKS):
        engine.tick()
    result = engine.detection
    anomaly = result.anomaly("R4")
    assert anomaly is not None and anomaly.confirmed
    assert anomaly.method == "isolation_forest"
    assert anomaly.severity >= 80
    assert anomaly.decision_score < 0
    assert result.node_scores["R4"] == anomaly.severity
    metrics = {d.metric for d in anomaly.deviations}
    assert {"latency_ms", "packet_loss_percent", "cpu_percent"} <= metrics
    # Nothing about the injected fault type is present in the detection output.
    dumped = result.model_dump_json()
    assert "router_congestion" not in dumped


def test_node_overload_is_detected_without_link_anomalies(engine):
    warm(engine)
    engine.faults.inject(FaultType.NODE_OVERLOAD, "R2", Severity.HIGH)
    for _ in range(CONFIRM_TICKS + 1):
        engine.tick()
    result = engine.detection
    assert result.anomaly("R2") is not None and result.anomaly("R2").confirmed
    assert not [a for a in result.anomalies if a.component_kind == ComponentKind.LINK]


def test_link_failure_is_detected_by_rules(engine):
    warm(engine)
    engine.faults.inject(FaultType.LINK_FAILURE, "L-R4-SW3")
    for _ in range(CONFIRM_TICKS):
        engine.tick()
    link = engine.detection.anomaly("L-R4-SW3")
    assert link is not None and link.confirmed and link.method == "rules"
    assert "link down" in link.reasons
    assert engine.detection.anomaly("F3") is not None


def test_offline_router_is_flagged(engine):
    warm(engine)
    engine.faults.inject(FaultType.ROUTER_FAILURE, "R4")
    for _ in range(CONFIRM_TICKS):
        engine.tick()
    assert engine.detection.anomaly("R4").severity == 100.0


def test_anomaly_clears_after_fault_is_removed(engine):
    warm(engine)
    fault = engine.faults.inject(FaultType.ROUTER_CONGESTION, "R4", Severity.HIGH)
    for _ in range(3):
        engine.tick()
    assert engine.detection.anomaly("R4") is not None
    engine.faults.clear(fault.id, reason="test")
    for _ in range(3):
        engine.tick()
    assert engine.detection.anomaly("R4") is None


def test_compute_deviations_filters_noise():
    baseline = {"latency_ms": 30.0, "cpu_percent": 30.0, "packet_loss_percent": 0.2}
    current = {"latency_ms": 33.0, "cpu_percent": 90.0, "packet_loss_percent": 0.3}
    devs = compute_deviations(baseline, current)
    assert [d.metric for d in devs] == ["cpu_percent"]
    assert devs[0].direction == "up" and devs[0].ratio == 3.0


def test_severity_scale_is_bounded(engine):
    det: AnomalyDetector = engine.detector
    assert det.severity_from_decision(det.metadata.threshold + 0.1) == 0.0
    assert det.severity_from_decision(det.metadata.threshold - 10) == 100.0
