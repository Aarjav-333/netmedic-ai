"""Recovery verification: compare telemetry windows before and after remediation.

Windows are averages over several samples (never a single tick). The checks are
explicit and each one is reported, so RESOLVED / PARTIALLY_RESOLVED / FAILED is
always traceable to numbers:

    1. affected flows healthy   - every flow the incident impacted is OK again
    2. network health           - score >= HEALTH_TARGET (or back to baseline - 3)
    3. latency recovered        - affected-flow latency <= baseline * 1.5 + 10 ms
    4. packet loss recovered    - affected-flow loss <= baseline + 1 %

RESOLVED            all checks pass
PARTIALLY_RESOLVED  health improved by >= PARTIAL_GAIN points or >= half the checks pass
FAILED              otherwise
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.logging_config import get_logger
from app.models.incident import IncidentStatus, MetricWindow, RecoveryCheck, RecoveryReport
from app.models.network import HealthStatus
from app.models.telemetry import TelemetrySnapshot

log = get_logger("netmedic.verify")

SETTLE_TICKS = 2  # samples to wait after remediation before measuring
WINDOW_TICKS = 3  # samples averaged for the "after" window
HEALTH_TARGET = 85.0
PARTIAL_GAIN = 10.0
FLOW_HEALTHY_SCORE = 85.0


def summarise_window(snapshots: list[TelemetrySnapshot], affected_flows: list[str], target_id: str | None) -> MetricWindow:
    """Average the metrics that matter over a list of snapshots."""
    if not snapshots:
        return MetricWindow(
            samples=0, health_score=0.0, avg_latency_ms=0.0, avg_packet_loss_percent=0.0,
            affected_flows_healthy=0, affected_flows_total=len(affected_flows),
        )
    health = sum(s.summary.health_score for s in snapshots) / len(snapshots)
    latencies: list[float] = []
    losses: list[float] = []
    healthy_counts: list[int] = []
    for s in snapshots:
        flows = [f for f in s.flows if f.flow_id in affected_flows] or list(s.flows)
        live = [f for f in flows if f.status.value != "down"]
        latencies.append(sum(f.latency_ms for f in live) / len(live) if live else 0.0)
        losses.append(sum(f.packet_loss_percent for f in flows) / len(flows) if flows else 0.0)
        healthy_counts.append(sum(1 for f in flows if f.health_score >= FLOW_HEALTHY_SCORE))
    window = MetricWindow(
        samples=len(snapshots),
        health_score=round(health, 1),
        avg_latency_ms=round(sum(latencies) / len(latencies), 1),
        avg_packet_loss_percent=round(sum(losses) / len(losses), 2),
        affected_flows_healthy=round(sum(healthy_counts) / len(healthy_counts)),
        affected_flows_total=len(affected_flows) if affected_flows else len(snapshots[-1].flows),
    )
    if target_id:
        node_samples = [n for s in snapshots for n in s.nodes if n.node_id == target_id]
        if node_samples:
            window.target_latency_ms = round(sum(n.latency_ms for n in node_samples) / len(node_samples), 1)
            window.target_packet_loss_percent = round(sum(n.packet_loss_percent for n in node_samples) / len(node_samples), 2)
            window.target_cpu_percent = round(sum(n.cpu_percent for n in node_samples) / len(node_samples), 1)
            window.target_utilization_percent = round(
                sum(n.bandwidth_utilization_percent for n in node_samples) / len(node_samples), 1
            )
        link_samples = [l for s in snapshots for l in s.links if l.link_id == target_id]
        if link_samples:
            window.target_latency_ms = round(sum(l.latency_ms for l in link_samples) / len(link_samples), 2)
            window.target_packet_loss_percent = round(sum(l.packet_loss_percent for l in link_samples) / len(link_samples), 2)
            window.target_utilization_percent = round(sum(l.utilization_percent for l in link_samples) / len(link_samples), 1)
    return window


def verify(baseline: MetricWindow | None, before: MetricWindow, after: MetricWindow) -> RecoveryReport:
    checks: list[RecoveryCheck] = []

    flows_ok = after.affected_flows_healthy >= after.affected_flows_total
    checks.append(
        RecoveryCheck(
            name="Affected flows healthy",
            passed=flows_ok,
            detail=f"{after.affected_flows_healthy} of {after.affected_flows_total} affected flows healthy (was {before.affected_flows_healthy})",
        )
    )

    health_goal = HEALTH_TARGET if baseline is None else min(HEALTH_TARGET, baseline.health_score - 3)
    health_ok = after.health_score >= health_goal
    checks.append(
        RecoveryCheck(
            name="Network health restored",
            passed=health_ok,
            detail=f"health {before.health_score:.0f} -> {after.health_score:.0f} (target >= {health_goal:.0f})",
        )
    )

    latency_goal = (baseline.avg_latency_ms * 1.5 + 10) if baseline else 60.0
    latency_ok = after.avg_latency_ms <= latency_goal
    checks.append(
        RecoveryCheck(
            name="Latency recovered",
            passed=latency_ok,
            detail=f"{before.avg_latency_ms:.0f} ms -> {after.avg_latency_ms:.0f} ms (target <= {latency_goal:.0f} ms)",
        )
    )

    loss_goal = (baseline.avg_packet_loss_percent + 1.0) if baseline else 1.5
    loss_ok = after.avg_packet_loss_percent <= loss_goal
    checks.append(
        RecoveryCheck(
            name="Packet loss recovered",
            passed=loss_ok,
            detail=f"{before.avg_packet_loss_percent:.1f}% -> {after.avg_packet_loss_percent:.1f}% (target <= {loss_goal:.1f}%)",
        )
    )

    passed = sum(1 for c in checks if c.passed)
    gain = after.health_score - before.health_score
    if passed == len(checks):
        status = IncidentStatus.RESOLVED
        summary = f"All {len(checks)} recovery checks passed; network health {before.health_score:.0f} -> {after.health_score:.0f}."
    elif gain >= PARTIAL_GAIN or passed >= len(checks) / 2:
        status = IncidentStatus.PARTIALLY_RESOLVED
        summary = f"{passed} of {len(checks)} checks passed; health improved by {gain:+.0f} points but service is not fully restored."
    else:
        status = IncidentStatus.FAILED
        summary = f"Only {passed} of {len(checks)} checks passed and health changed by {gain:+.0f} points; remediation did not restore service."
    log.info("[VERIFY] %s - %s", status.value.upper(), summary)
    return RecoveryReport(
        status=status,
        baseline=baseline,
        before=before,
        after=after,
        checks=checks,
        verified_at=datetime.now(timezone.utc),
        summary=summary,
    )


def status_word(status: HealthStatus) -> str:
    return status.value
