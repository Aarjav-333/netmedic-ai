"""Health classification and the 0-100 network health score.

Component score
---------------
Every node, link and flow gets a score in [0, 100]:

    excess(metric) = clamp((value - ok) / (bad - ok), 0, 1)
    score          = 100 * (1 - max(excess over the component's metrics))
    offline / down = 0

i.e. a component is perfect while every metric is inside its "ok" band and
degrades linearly towards 0 as its *worst* metric approaches the "bad" band.

Network health score
--------------------
    health = 0.45 * mean(flow scores)   (what users experience end-to-end)
           + 0.35 * mean(node scores)
           + 0.20 * mean(link scores)

The three sub-scores are exposed separately in the snapshot summary so the
number can always be explained.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.network import HealthStatus

FLOW_WEIGHT = 0.45
NODE_WEIGHT = 0.35
LINK_WEIGHT = 0.20


@dataclass(frozen=True)
class Band:
    ok: float
    bad: float

    def excess(self, value: float) -> float:
        if self.bad <= self.ok:
            return 0.0
        return max(0.0, min(1.0, (value - self.ok) / (self.bad - self.ok)))


# Thresholds. "ok" is the top of the healthy band, "bad" is fully degraded.
NODE_BANDS = {
    "latency_ms": Band(ok=50.0, bad=200.0),
    "packet_loss_percent": Band(ok=1.0, bad=10.0),
    "cpu_percent": Band(ok=70.0, bad=95.0),
    "memory_percent": Band(ok=80.0, bad=97.0),
    "bandwidth_utilization_percent": Band(ok=75.0, bad=100.0),
}
LINK_BANDS = {
    "packet_loss_percent": Band(ok=1.0, bad=10.0),
    "utilization_percent": Band(ok=75.0, bad=100.0),
    "latency_ratio": Band(ok=2.0, bad=6.0),  # measured / base latency
}
FLOW_BANDS = {
    "latency_ms": Band(ok=40.0, bad=150.0),
    "packet_loss_percent": Band(ok=1.0, bad=10.0),
    "delivery_shortfall_percent": Band(ok=5.0, bad=50.0),  # 100 * (1 - throughput/demand)
}

# Status boundaries on the component score.
WARNING_BELOW = 85.0
CRITICAL_BELOW = 50.0


def component_score(bands: dict[str, Band], values: dict[str, float]) -> float:
    worst = 0.0
    for key, band in bands.items():
        if key in values:
            worst = max(worst, band.excess(values[key]))
    return round(100.0 * (1.0 - worst), 2)


def status_from_score(score: float, offline: bool = False) -> HealthStatus:
    if offline:
        return HealthStatus.OFFLINE
    if score < CRITICAL_BELOW:
        return HealthStatus.CRITICAL
    if score < WARNING_BELOW:
        return HealthStatus.WARNING
    return HealthStatus.HEALTHY


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 100.0


def network_health_score(
    flow_scores: list[float], node_scores: list[float], link_scores: list[float]
) -> tuple[float, float, float, float]:
    """Return (health, flow_health, node_health, link_health)."""
    flow_health = _mean(flow_scores)
    node_health = _mean(node_scores)
    link_health = _mean(link_scores)
    health = FLOW_WEIGHT * flow_health + NODE_WEIGHT * node_health + LINK_WEIGHT * link_health
    return round(health, 1), round(flow_health, 1), round(node_health, 1), round(link_health, 1)
