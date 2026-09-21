"""Feature engineering for anomaly detection.

Raw node metrics have very different healthy baselines (a gateway serves ~2200
connections, an access switch ~140; capacities span 1-10 Gbps). To train one
Isolation Forest for every node we normalise each metric by a *configuration*
fact of the node (its healthy RTT, capacity, expected connection count). These
are topology facts, not fault labels, so nothing about injected faults leaks in.
"""

from __future__ import annotations

import numpy as np

from app.models.telemetry import NodeTelemetry
from app.simulation.state import NodeState
from app.telemetry.generator import BASE_CONNECTIONS, CORE_CONNECTIONS

FEATURE_NAMES: tuple[str, ...] = (
    "latency_ratio",  # latency_ms / healthy base RTT
    "packet_loss_percent",
    "throughput_ratio",  # throughput_mbps / capacity
    "bandwidth_utilization_percent",
    "cpu_percent",
    "memory_percent",
    "connections_ratio",  # active_connections / expected for the node type
)

# Raw metrics surfaced as "what changed" evidence, with their display units.
EVIDENCE_METRICS: dict[str, str] = {
    "latency_ms": "ms",
    "packet_loss_percent": "%",
    "throughput_mbps": "Mbps",
    "bandwidth_utilization_percent": "%",
    "cpu_percent": "%",
    "memory_percent": "%",
    "active_connections": "",
}


def expected_connections(node: NodeState) -> float:
    if node.id == "R1":
        return float(CORE_CONNECTIONS)
    return float(BASE_CONNECTIONS[node.type.value])


def node_feature_vector(sample: NodeTelemetry, node: NodeState) -> np.ndarray:
    return np.array(
        [
            sample.latency_ms / node.base_rtt_ms,
            sample.packet_loss_percent,
            sample.throughput_mbps / node.capacity_mbps,
            sample.bandwidth_utilization_percent,
            sample.cpu_percent,
            sample.memory_percent,
            sample.active_connections / expected_connections(node),
        ],
        dtype=float,
    )


def raw_metrics(sample: NodeTelemetry) -> dict[str, float]:
    return {name: float(getattr(sample, name)) for name in EVIDENCE_METRICS}
