"""Weighted shortest-path routing over the simulated topology.

Edge weight (milliseconds):

    weight = base_latency
           + congestion_penalty(utilisation)
           + packet_loss_penalty(loss %)
           + link.penalty_ms          (set by the healing engine)
           + target_node.penalty_ms   (set by the healing engine)

Links or nodes whose admin status is DOWN are excluded from the graph entirely.
Utilisation / packet-loss inputs are optional: at start-up routes are computed
from base latency only, which yields the "primary" paths.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from app.simulation.state import LinkState, NodeState, Route

# Tunables (documented so the demo explanation matches the maths).
CONGESTION_START_UTIL = 0.70  # utilisation above which queueing delay is penalised
CONGESTION_MAX_MULTIPLIER = 3.0  # +300 % of base latency at 100 % utilisation
LOSS_PENALTY_MS_PER_PERCENT = 4.0  # 10 % loss = +40 ms


@dataclass(frozen=True)
class LinkMetricsInput:
    """Telemetry-derived inputs used to make routing congestion-aware."""

    utilization: float  # 0.0 - 1.0+
    packet_loss_percent: float


def congestion_penalty_ms(base_latency_ms: float, utilization: float) -> float:
    if utilization <= CONGESTION_START_UTIL:
        return 0.0
    over = min(utilization - CONGESTION_START_UTIL, 1.0) / (1.0 - CONGESTION_START_UTIL)
    return base_latency_ms * CONGESTION_MAX_MULTIPLIER * over


def loss_penalty_ms(packet_loss_percent: float) -> float:
    return max(0.0, packet_loss_percent) * LOSS_PENALTY_MS_PER_PERCENT


def link_weight(
    link: LinkState,
    target: NodeState,
    metrics: LinkMetricsInput | None,
) -> float | None:
    """Routing weight of traversing the link into the target node, or None if unusable."""
    if not link.is_up or not target.is_up:
        return None
    weight = link.base_latency_ms + link.penalty_ms + target.penalty_ms
    if metrics is not None:
        weight += congestion_penalty_ms(link.base_latency_ms, metrics.utilization)
        weight += loss_penalty_ms(metrics.packet_loss_percent)
    return weight


def build_routing_graph(
    nodes: dict[str, NodeState],
    links: dict[str, LinkState],
    metrics: dict[str, LinkMetricsInput] | None = None,
) -> nx.DiGraph:
    """Build a directed graph whose edge weights follow the formula above."""
    graph = nx.DiGraph()
    for node in nodes.values():
        if node.is_up:
            graph.add_node(node.id)
    for link in links.values():
        src, dst = link.endpoints()
        if src not in graph or dst not in graph:
            continue
        link_metrics = metrics.get(link.id) if metrics else None
        for u, v in ((src, dst), (dst, src)):
            weight = link_weight(link, nodes[v], link_metrics)
            if weight is not None:
                graph.add_edge(u, v, weight=weight, link_id=link.id)
    return graph


def shortest_path(
    graph: nx.DiGraph, source: str, destination: str
) -> tuple[list[str], list[str], float] | None:
    """Dijkstra shortest path. Returns (node_path, link_ids, cost) or None if unreachable."""
    if source not in graph or destination not in graph:
        return None
    try:
        path = nx.dijkstra_path(graph, source, destination, weight="weight")
    except nx.NetworkXNoPath:
        return None
    link_ids: list[str] = []
    cost = 0.0
    for u, v in zip(path, path[1:]):
        data = graph.edges[u, v]
        link_ids.append(data["link_id"])
        cost += data["weight"]
    return path, link_ids, round(cost, 3)


def compute_route(
    flow_id: str,
    source: str,
    destination: str,
    graph: nx.DiGraph,
    primary_path: list[str],
    reason: str,
) -> Route:
    result = shortest_path(graph, source, destination)
    if result is None:
        return Route(
            flow_id=flow_id,
            path=[],
            links=[],
            cost=float("inf"),
            is_primary=False,
            reason="no path available",
            primary_path=list(primary_path),
        )
    path, link_ids, cost = result
    is_primary = path == primary_path
    return Route(
        flow_id=flow_id,
        path=path,
        links=link_ids,
        cost=cost,
        is_primary=is_primary,
        reason="primary" if is_primary else reason,
        primary_path=list(primary_path),
    )
