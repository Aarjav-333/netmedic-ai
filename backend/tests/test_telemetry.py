"""Telemetry generator behaviour."""

import pytest

from app.models.network import AdminStatus, HealthStatus
from app.models.telemetry import FlowStatus
from app.simulation.effects import NodeEffects, SimulationEffects
from app.simulation.network import NetworkSimulator
from app.telemetry.generator import TelemetryGenerator, queue_factor, saturation_loss
from app.telemetry.health import NODE_BANDS, Band, component_score


def make_generator(seed: int = 7) -> tuple[NetworkSimulator, TelemetryGenerator]:
    net = NetworkSimulator()
    return net, TelemetryGenerator(net, seed=seed)


def test_healthy_network_has_healthy_telemetry():
    net, gen = make_generator()
    for tick in range(5):
        snap = gen.generate(tick)
    assert snap.summary.health_score >= 95
    for n in snap.nodes:
        assert n.health == HealthStatus.HEALTHY
        assert 10 <= n.latency_ms <= 50
        assert n.packet_loss_percent <= 1.0
        assert 10 <= n.cpu_percent <= 65
        assert 10 <= n.bandwidth_utilization_percent <= 75
    assert all(f.status == FlowStatus.OK for f in snap.flows)


def test_telemetry_fluctuates_between_samples():
    net, gen = make_generator()
    values = {gen.generate(t).node("R1").latency_ms for t in range(1, 12)}
    assert len(values) > 3


def test_congestion_effects_degrade_node_and_flows():
    net, gen = make_generator()
    fx = SimulationEffects()
    fx.add_node("R4", NodeEffects(extra_load_mbps=1400, cpu_add_percent=25))
    for tick in range(4):
        snap = gen.generate(tick, fx)
    r4 = snap.node("R4")
    assert r4.health == HealthStatus.CRITICAL
    assert r4.latency_ms > 120
    assert r4.packet_loss_percent > 5
    assert r4.cpu_percent > 85
    assert snap.flow("F3").health == HealthStatus.CRITICAL
    assert snap.flow("F1").health == HealthStatus.HEALTHY  # not routed via R4
    assert snap.summary.health_score < 85


def test_reroute_recovers_flows_under_congestion():
    net, gen = make_generator()
    fx = SimulationEffects()
    fx.add_node("R4", NodeEffects(extra_load_mbps=1400, cpu_add_percent=25))
    for tick in range(3):
        gen.generate(tick, fx)
    net.set_node_penalty("R4", 500, isolated=True)
    net.recompute_routes("avoid R4")
    for tick in range(3, 6):
        snap = gen.generate(tick, fx)
    assert all(f.health == HealthStatus.HEALTHY for f in snap.flows)
    assert snap.summary.rerouted_flows == 3
    assert snap.summary.health_score > 90


def test_down_link_breaks_flows_until_rerouted():
    net, gen = make_generator()
    net.set_link_status("L-R4-SW3", AdminStatus.DOWN)
    snap = gen.generate(1)
    assert snap.link("L-R4-SW3").status == AdminStatus.DOWN
    assert snap.flow("F3").status == FlowStatus.DOWN
    assert snap.summary.broken_flows == 2  # F3 and F5 both used the link
    net.recompute_routes("isolate L-R4-SW3")
    snap = gen.generate(2)
    assert snap.flow("F3").status == FlowStatus.OK
    assert snap.summary.broken_flows == 0


def test_offline_node_reports_offline():
    net, gen = make_generator()
    net.set_node_status("R2", AdminStatus.DOWN)
    snap = gen.generate(1)
    assert snap.node("R2").health == HealthStatus.OFFLINE
    assert snap.summary.active_nodes == 9


def test_queue_and_loss_curves():
    assert queue_factor(0.5) == 0.0
    assert queue_factor(1.0) == 5.0
    assert queue_factor(2.0) == 8.0  # capped
    assert saturation_loss(0.8) == 0.0
    assert saturation_loss(1.0) == pytest.approx(9.0)


def test_component_score_uses_worst_metric():
    healthy = {
        "latency_ms": 30,
        "packet_loss_percent": 0.2,
        "cpu_percent": 40,
        "memory_percent": 50,
        "bandwidth_utilization_percent": 40,
    }
    assert component_score(NODE_BANDS, healthy) == 100.0
    degraded = dict(healthy, cpu_percent=82.5)  # halfway between ok=70 and bad=95
    assert component_score(NODE_BANDS, degraded) == 50.0
    assert Band(ok=10, bad=20).excess(25) == 1.0
