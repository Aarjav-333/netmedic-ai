"""Anomaly detection over telemetry snapshots.

Nodes  -> Isolation Forest on normalised features (see features.py).
Links  -> deterministic rules (down, loss, saturation, latency inflation).
Flows  -> deterministic rules (down / critical end-to-end health).

A rolling baseline per component (updated only while that component is
normal) provides the "what changed" evidence: latency 31 ms -> 182 ms (5.9x).
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.detection.features import EVIDENCE_METRICS, node_feature_vector, raw_metrics
from app.detection.trainer import ModelMetadata, load_model, train_and_save
from app.logging_config import get_logger
from app.models.detection import ComponentAnomaly, ComponentKind, DetectionResult, MetricDeviation
from app.models.network import AdminStatus, HealthStatus
from app.models.telemetry import FlowStatus, TelemetrySnapshot
from app.simulation.network import NetworkSimulator

log = get_logger("netmedic.detection")

CONFIRM_TICKS = 2  # consecutive anomalous ticks before an anomaly is "confirmed"
BASELINE_ALPHA = 0.15  # EMA weight for baseline updates
BASELINE_WARMUP_TICKS = 3
DEVIATION_RATIO = 1.6  # a metric is "changed significantly" beyond this ratio (either way)
DEVIATION_MIN_ABS = {  # ...and beyond this absolute delta, to ignore noise on tiny values
    "latency_ms": 8.0,
    "packet_loss_percent": 0.8,
    "throughput_mbps": 60.0,
    "bandwidth_utilization_percent": 10.0,
    "cpu_percent": 10.0,
    "memory_percent": 8.0,
    "active_connections": 40.0,
}

# Link rules
LINK_LOSS_PERCENT = 3.0
LINK_UTIL_PERCENT = 92.0
LINK_LATENCY_RATIO = 3.0


class BaselineTracker:
    """Exponential moving average of raw metrics per component, frozen while anomalous."""

    def __init__(self) -> None:
        self._values: dict[str, dict[str, float]] = {}
        self._samples: dict[str, int] = defaultdict(int)

    def get(self, component_id: str) -> dict[str, float] | None:
        return self._values.get(component_id)

    def ready(self, component_id: str) -> bool:
        return self._samples[component_id] >= BASELINE_WARMUP_TICKS

    def update(self, component_id: str, metrics: dict[str, float]) -> None:
        current = self._values.get(component_id)
        if current is None:
            self._values[component_id] = dict(metrics)
        else:
            for key, value in metrics.items():
                current[key] = (1 - BASELINE_ALPHA) * current[key] + BASELINE_ALPHA * value
        self._samples[component_id] += 1

    def reset(self) -> None:
        self._values.clear()
        self._samples.clear()


def compute_deviations(baseline: dict[str, float], current: dict[str, float]) -> list[MetricDeviation]:
    deviations: list[MetricDeviation] = []
    for metric, unit in EVIDENCE_METRICS.items():
        base = baseline.get(metric)
        now = current.get(metric)
        if base is None or now is None:
            continue
        delta = abs(now - base)
        if delta < DEVIATION_MIN_ABS.get(metric, 0.0):
            continue
        ratio = now / base if base > 1e-9 else float("inf") if now > 0 else 1.0
        if ratio >= DEVIATION_RATIO or (ratio > 0 and 1 / ratio >= DEVIATION_RATIO):
            deviations.append(
                MetricDeviation(
                    metric=metric,
                    unit=unit,
                    baseline=round(base, 2),
                    current=round(now, 2),
                    ratio=round(min(ratio, 999.0), 2),
                    direction="up" if now > base else "down",
                )
            )
    # Most dramatic change first.
    deviations.sort(key=lambda d: max(d.ratio, 1 / d.ratio if d.ratio else 1), reverse=True)
    return deviations


class AnomalyDetector:
    def __init__(self, network: NetworkSimulator, auto_train: bool = True) -> None:
        self.network = network
        self.baselines = BaselineTracker()
        self._streak: dict[str, int] = defaultdict(int)
        self.model = None
        self.metadata: ModelMetadata | None = None
        if auto_train:
            self.ensure_model()

    # -------------------------------------------------------------- model
    def ensure_model(self) -> None:
        loaded = load_model()
        if loaded is None:
            loaded = train_and_save()
        self.model, self.metadata = loaded
        log.info("[DETECTION] Isolation Forest ready (threshold=%.4f)", self.metadata.threshold)

    def severity_from_decision(self, decision: float) -> float:
        assert self.metadata is not None
        below = self.metadata.threshold - decision
        if below <= 0:
            return 0.0
        return round(min(100.0, 100.0 * below / self.metadata.severity_span), 1)

    def reset(self) -> None:
        self.baselines.reset()
        self._streak.clear()

    # ------------------------------------------------------------- detect
    def detect(self, snapshot: TelemetrySnapshot) -> DetectionResult:
        anomalies: list[ComponentAnomaly] = []
        node_scores: dict[str, float] = {}

        anomalies.extend(self._detect_nodes(snapshot, node_scores))
        anomalies.extend(self._detect_links(snapshot))
        anomalies.extend(self._detect_flows(snapshot))

        confirmed = [a.component_id for a in anomalies if a.confirmed]
        for a in anomalies:
            if a.confirmed and self._streak[a.component_id] == CONFIRM_TICKS:
                log.info(
                    "[DETECTION] Anomaly confirmed on %s (%s, severity=%.0f)",
                    a.component_id,
                    a.method,
                    a.severity,
                )
        return DetectionResult(
            tick=snapshot.tick,
            timestamp=snapshot.timestamp,
            anomalies=anomalies,
            node_scores=node_scores,
            confirmed_ids=confirmed,
        )

    def _bump(self, component_id: str, anomalous: bool) -> int:
        if anomalous:
            self._streak[component_id] += 1
        else:
            self._streak[component_id] = 0
        return self._streak[component_id]

    def _detect_nodes(self, snapshot: TelemetrySnapshot, node_scores: dict[str, float]) -> list[ComponentAnomaly]:
        assert self.model is not None and self.metadata is not None
        results: list[ComponentAnomaly] = []
        up_samples = [s for s in snapshot.nodes if s.status == AdminStatus.UP]
        if up_samples:
            matrix = np.vstack([node_feature_vector(s, self.network.nodes[s.node_id]) for s in up_samples])
            decisions = self.model.decision_function(matrix)
        else:
            decisions = np.array([])

        for sample, decision in zip(up_samples, decisions):
            severity = self.severity_from_decision(float(decision))
            is_anomaly = float(decision) < self.metadata.threshold
            node_scores[sample.node_id] = severity
            metrics = raw_metrics(sample)
            streak = self._bump(sample.node_id, is_anomaly)
            if not is_anomaly:
                # Only learn "normal" from samples the model considers normal.
                self.baselines.update(sample.node_id, metrics)
                continue
            baseline = self.baselines.get(sample.node_id) if self.baselines.ready(sample.node_id) else None
            deviations = compute_deviations(baseline, metrics) if baseline else []
            results.append(
                ComponentAnomaly(
                    component_id=sample.node_id,
                    component_kind=ComponentKind.NODE,
                    method="isolation_forest",
                    decision_score=round(float(decision), 4),
                    severity=severity,
                    is_anomaly=True,
                    confirmed=streak >= CONFIRM_TICKS,
                    consecutive_ticks=streak,
                    deviations=deviations,
                )
            )

        # Offline nodes are anomalies by definition (no telemetry to score).
        for sample in snapshot.nodes:
            if sample.status == AdminStatus.DOWN:
                node_scores[sample.node_id] = 100.0
                streak = self._bump(sample.node_id, True)
                results.append(
                    ComponentAnomaly(
                        component_id=sample.node_id,
                        component_kind=ComponentKind.NODE,
                        method="rules",
                        severity=100.0,
                        is_anomaly=True,
                        confirmed=streak >= CONFIRM_TICKS,
                        consecutive_ticks=streak,
                        reasons=["node unreachable (no telemetry)"],
                    )
                )
        return results

    def _detect_links(self, snapshot: TelemetrySnapshot) -> list[ComponentAnomaly]:
        results: list[ComponentAnomaly] = []
        for sample in snapshot.links:
            link = self.network.links[sample.link_id]
            reasons: list[str] = []
            severity = 0.0
            if sample.status == AdminStatus.DOWN:
                reasons.append("link down")
                severity = 100.0
            else:
                if sample.packet_loss_percent >= LINK_LOSS_PERCENT:
                    reasons.append(f"packet loss {sample.packet_loss_percent:.1f}%")
                    severity = max(severity, min(100.0, sample.packet_loss_percent * 4))
                if sample.utilization_percent >= LINK_UTIL_PERCENT:
                    reasons.append(f"utilisation {sample.utilization_percent:.0f}%")
                    severity = max(severity, min(100.0, (sample.utilization_percent - 70) * 2))
                ratio = sample.latency_ms / link.base_latency_ms if link.base_latency_ms else 1.0
                if ratio >= LINK_LATENCY_RATIO:
                    reasons.append(f"latency {ratio:.1f}× baseline")
                    severity = max(severity, min(100.0, ratio * 12))
            anomalous = bool(reasons)
            streak = self._bump(sample.link_id, anomalous)
            if anomalous:
                results.append(
                    ComponentAnomaly(
                        component_id=sample.link_id,
                        component_kind=ComponentKind.LINK,
                        method="rules",
                        severity=round(severity, 1),
                        is_anomaly=True,
                        confirmed=streak >= CONFIRM_TICKS,
                        consecutive_ticks=streak,
                        reasons=reasons,
                    )
                )
        return results

    def _detect_flows(self, snapshot: TelemetrySnapshot) -> list[ComponentAnomaly]:
        results: list[ComponentAnomaly] = []
        for sample in snapshot.flows:
            reasons: list[str] = []
            if sample.status == FlowStatus.DOWN:
                reasons.append("flow has no working path")
            elif sample.health == HealthStatus.CRITICAL:
                reasons.append(
                    f"end-to-end latency {sample.latency_ms:.0f} ms, loss {sample.packet_loss_percent:.1f}%"
                )
            anomalous = bool(reasons)
            streak = self._bump(sample.flow_id, anomalous)
            if anomalous:
                results.append(
                    ComponentAnomaly(
                        component_id=sample.flow_id,
                        component_kind=ComponentKind.FLOW,
                        method="rules",
                        severity=100.0 if sample.status == FlowStatus.DOWN else round(100 - sample.health_score, 1),
                        is_anomaly=True,
                        confirmed=streak >= CONFIRM_TICKS,
                        consecutive_ticks=streak,
                        reasons=reasons,
                    )
                )
        return results
