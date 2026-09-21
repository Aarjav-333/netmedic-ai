"""Routing / rerouting behaviour of the NetworkSimulator."""

import math

import pytest

from app.models.network import AdminStatus
from app.simulation.network import NetworkSimulator
from app.simulation.routing import (
    LinkMetricsInput,
    congestion_penalty_ms,
    loss_penalty_ms,
)


@pytest.fixture
def sim() -> NetworkSimulator:
    return NetworkSimulator()


def test_default_topology_size(sim):
    assert len(sim.nodes) == 10
    assert len(sim.links) == 15
    assert len(sim.flows) == 6


def test_primary_routes_use_primary_uplinks(sim):
    assert sim.routes["F3"].path == ["SW3", "R4", "R1", "GW"]
    assert sim.routes["F1"].path == ["SW1", "R2", "R1", "GW"]
    assert all(r.is_primary for r in sim.routes.values())


def test_node_penalty_reroutes_transit_traffic(sim):
    sim.set_node_penalty("R4", 500.0, isolated=True)
    sim.recompute_routes(reason="avoid R4")
    assert sim.routes["F3"].path == ["SW3", "R3", "R1", "GW"]
    assert sim.routes["F4"].path == ["SW4", "R3", "R1", "GW"]
    assert not sim.routes["F3"].is_primary
    assert sim.routes["F3"].reason == "avoid R4"
    # Flows that never used R4 are untouched.
    assert sim.routes["F1"].is_primary
    assert sim.node_loads()["R4"] == 0.0


def test_clearing_penalty_restores_primary_paths(sim):
    sim.set_node_penalty("R4", 500.0, isolated=True)
    sim.recompute_routes(reason="avoid R4")
    sim.clear_healing_state()
    sim.recompute_routes(reason="restore")
    assert sim.routes["F3"].is_primary
    assert sim.routes["F3"].path == ["SW3", "R4", "R1", "GW"]


def test_link_down_is_excluded_from_routing(sim):
    sim.set_link_status("L-R1-R3", AdminStatus.DOWN)
    sim.recompute_routes(reason="isolate L-R1-R3")
    assert "L-R1-R3" not in sim.routes["F2"].links
    assert sim.routes["F2"].path == ["SW2", "R2", "R1", "GW"]


def test_node_down_is_excluded_from_routing(sim):
    sim.set_node_status("R4", AdminStatus.DOWN)
    sim.recompute_routes(reason="R4 offline")
    for route in sim.routes.values():
        assert "R4" not in route.path
        assert not route.is_broken


def test_unreachable_destination_yields_broken_route(sim):
    sim.set_node_status("R1", AdminStatus.DOWN)  # R1 is the only way to GW
    sim.recompute_routes(reason="R1 offline")
    assert sim.routes["F1"].is_broken
    assert math.isinf(sim.routes["F1"].cost)


def test_congestion_aware_routing_avoids_saturated_link(sim):
    metrics = {"L-R4-SW3": LinkMetricsInput(utilization=1.0, packet_loss_percent=15.0)}
    sim.recompute_routes(reason="congestion-aware", link_metrics=metrics)
    assert sim.routes["F3"].path == ["SW3", "R3", "R1", "GW"]


def test_penalty_formulas():
    assert congestion_penalty_ms(10.0, 0.5) == 0.0
    assert congestion_penalty_ms(10.0, 1.0) == pytest.approx(30.0)
    assert loss_penalty_ms(10.0) == pytest.approx(40.0)


def test_link_loads_follow_routes(sim):
    loads = sim.link_loads()
    assert loads["L-R4-SW3"] == 450.0  # F3 (300) + F5 (150)
    assert loads["L-GW-R1"] == 1000.0
