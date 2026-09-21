"""NetworkSimulator: owns topology state, traffic flows and the routing table."""

from __future__ import annotations

from collections import defaultdict

from app.logging_config import get_logger
from app.models.network import AdminStatus, TopologyResponse
from app.simulation.routing import LinkMetricsInput, build_routing_graph, compute_route
from app.simulation.state import FlowState, LinkState, NodeState, Route
from app.simulation.topology import DEFAULT_FLOWS, DEFAULT_LINKS, DEFAULT_NODES

log = get_logger("netmedic.simulation")


class NetworkSimulator:
    """Holds the simulated network and performs real routing changes on it.

    Routes are *static* between recomputations: like a forwarding table, they
    only change when something (the healing engine) explicitly recomputes them.
    That is what makes rerouting a genuine remediation rather than a side-effect.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, NodeState] = {}
        self.links: dict[str, LinkState] = {}
        self.flows: dict[str, FlowState] = {}
        self.routes: dict[str, Route] = {}
        self._primary_paths: dict[str, list[str]] = {}
        self._link_index: dict[frozenset[str], str] = {}
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self) -> None:
        """Restore the default topology, clear penalties and recompute primary routes."""
        self.nodes = {
            n.id: NodeState(n.id, n.name, n.type, n.capacity_mbps, n.base_rtt_ms, n.x, n.y)
            for n in DEFAULT_NODES
        }
        self.links = {
            l.id: LinkState(l.id, l.source, l.target, l.base_latency_ms, l.capacity_mbps)
            for l in DEFAULT_LINKS
        }
        self.flows = {
            f.id: FlowState(f.id, f.name, f.source, f.destination, f.demand_mbps)
            for f in DEFAULT_FLOWS
        }
        self._link_index = {frozenset((l.source, l.target)): l.id for l in self.links.values()}
        # Primary paths are the shortest paths on a fully healthy, unpenalised graph.
        graph = build_routing_graph(self.nodes, self.links)
        self._primary_paths = {}
        for flow in self.flows.values():
            route = compute_route(flow.id, flow.source, flow.destination, graph, [], "primary")
            self._primary_paths[flow.id] = list(route.path)
        self.routes = {}
        self.recompute_routes(reason="primary")
        log.info(
            "[SIMULATION] Topology reset: %d nodes, %d links, %d flows",
            len(self.nodes),
            len(self.links),
            len(self.flows),
        )

    # --------------------------------------------------------------- lookups
    def link_between(self, a: str, b: str) -> LinkState | None:
        link_id = self._link_index.get(frozenset((a, b)))
        return self.links[link_id] if link_id else None

    def links_of(self, node_id: str) -> list[LinkState]:
        return [l for l in self.links.values() if node_id in l.endpoints()]

    def neighbors(self, node_id: str) -> list[str]:
        return [l.other_end(node_id) for l in self.links_of(node_id)]

    def primary_path(self, flow_id: str) -> list[str]:
        return list(self._primary_paths.get(flow_id, []))

    def flows_through_node(self, node_id: str) -> list[FlowState]:
        return [self.flows[r.flow_id] for r in self.routes.values() if node_id in r.path]

    def flows_through_link(self, link_id: str) -> list[FlowState]:
        return [self.flows[r.flow_id] for r in self.routes.values() if link_id in r.links]

    # --------------------------------------------------------------- routing
    def recompute_routes(
        self,
        reason: str,
        link_metrics: dict[str, LinkMetricsInput] | None = None,
    ) -> dict[str, Route]:
        """Recalculate every path with the current penalties/status and (optionally) telemetry."""
        graph = build_routing_graph(self.nodes, self.links, link_metrics)
        changed: list[str] = []
        new_routes: dict[str, Route] = {}
        for flow in self.flows.values():
            route = compute_route(
                flow.id,
                flow.source,
                flow.destination,
                graph,
                self._primary_paths.get(flow.id, []),
                reason,
            )
            previous = self.routes.get(flow.id)
            if previous is None or previous.path != route.path:
                changed.append(flow.id)
            new_routes[flow.id] = route
        self.routes = new_routes
        if changed and reason != "primary":
            for flow_id in changed:
                r = self.routes[flow_id]
                path = " > ".join(r.path) if r.path else "NO PATH"
                log.info("[ROUTING] %s now %s (%s)", flow_id, path, r.reason)
        return self.routes

    # -------------------------------------------------------------- mutators
    def set_node_status(self, node_id: str, status: AdminStatus) -> None:
        self._node(node_id).status = status

    def set_link_status(self, link_id: str, status: AdminStatus) -> None:
        self._link(link_id).status = status

    def set_node_penalty(self, node_id: str, penalty_ms: float, isolated: bool | None = None) -> None:
        node = self._node(node_id)
        node.penalty_ms = max(0.0, penalty_ms)
        if isolated is not None:
            node.isolated = isolated

    def set_link_penalty(self, link_id: str, penalty_ms: float, isolated: bool | None = None) -> None:
        link = self._link(link_id)
        link.penalty_ms = max(0.0, penalty_ms)
        if isolated is not None:
            link.isolated = isolated

    def set_flow_rate_limit(self, flow_id: str, rate_limit_mbps: float | None) -> None:
        self._flow(flow_id).rate_limit_mbps = rate_limit_mbps

    def clear_healing_state(self) -> None:
        """Remove every penalty / rate limit the healing engine applied."""
        for node in self.nodes.values():
            node.penalty_ms, node.isolated = 0.0, False
        for link in self.links.values():
            link.penalty_ms, link.isolated = 0.0, False
        for flow in self.flows.values():
            flow.rate_limit_mbps = None

    # ------------------------------------------------------------------ load
    def link_loads(self) -> dict[str, float]:
        """Offered load (Mbps) per link derived from the current routing table."""
        loads: dict[str, float] = defaultdict(float)
        for route in self.routes.values():
            demand = self.flows[route.flow_id].effective_demand_mbps
            for link_id in route.links:
                loads[link_id] += demand
        return {link_id: loads.get(link_id, 0.0) for link_id in self.links}

    def node_loads(self) -> dict[str, float]:
        """Forwarded traffic (Mbps) per node derived from the current routing table."""
        loads: dict[str, float] = defaultdict(float)
        for route in self.routes.values():
            demand = self.flows[route.flow_id].effective_demand_mbps
            for node_id in route.path:
                loads[node_id] += demand
        return {node_id: loads.get(node_id, 0.0) for node_id in self.nodes}

    # ------------------------------------------------------------- serialise
    def to_topology_response(self) -> TopologyResponse:
        return TopologyResponse(
            nodes=[n.to_schema() for n in self.nodes.values()],
            links=[l.to_schema() for l in self.links.values()],
            flows=[f.to_schema() for f in self.flows.values()],
            routes=[r.to_schema() for r in self.routes.values()],
        )

    # --------------------------------------------------------------- helpers
    def _node(self, node_id: str) -> NodeState:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise KeyError(f"Unknown node {node_id!r}") from None

    def _link(self, link_id: str) -> LinkState:
        try:
            return self.links[link_id]
        except KeyError:
            raise KeyError(f"Unknown link {link_id!r}") from None

    def _flow(self, flow_id: str) -> FlowState:
        try:
            return self.flows[flow_id]
        except KeyError:
            raise KeyError(f"Unknown flow {flow_id!r}") from None
