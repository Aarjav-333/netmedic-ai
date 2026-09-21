"""Default campus topology used by the simulator.

Layout (approximate):

                 GW (Internet Gateway)
                  |
                 R1 (Core Router) --- SRV (Campus Server)
              /    |    \
            R2     R3     R4          distribution routers (lateral links R2-R3, R3-R4)
            |  \  / | \  /  \
           SW1   SW2   SW3   SW4      access switches, each dual-homed (primary + backup)

Every access switch has a low-latency primary uplink and a higher-latency backup
uplink so the healing engine always has a real alternative path to choose.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.network import NodeType


@dataclass(frozen=True)
class NodeDef:
    id: str
    name: str
    type: NodeType
    capacity_mbps: float
    base_rtt_ms: float  # healthy monitoring round-trip time to the node
    x: float
    y: float


@dataclass(frozen=True)
class LinkDef:
    id: str
    source: str
    target: str
    base_latency_ms: float
    capacity_mbps: float


@dataclass(frozen=True)
class FlowDef:
    id: str
    name: str
    source: str
    destination: str
    demand_mbps: float


DEFAULT_NODES: tuple[NodeDef, ...] = (
    NodeDef("GW", "Internet Gateway", NodeType.GATEWAY, 10_000, 18, 450, 40),
    NodeDef("R1", "Core Router", NodeType.ROUTER, 10_000, 22, 450, 180),
    NodeDef("SRV", "Campus Server", NodeType.SERVER, 2_000, 20, 760, 180),
    NodeDef("R2", "Academic Router", NodeType.ROUTER, 2_000, 26, 150, 330),
    NodeDef("R3", "Library Router", NodeType.ROUTER, 2_000, 26, 450, 330),
    NodeDef("R4", "Hostel Router", NodeType.ROUTER, 2_000, 26, 760, 330),
    NodeDef("SW1", "Academic Switch", NodeType.SWITCH, 1_000, 30, 60, 490),
    NodeDef("SW2", "Library Switch", NodeType.SWITCH, 1_000, 30, 340, 490),
    NodeDef("SW3", "Hostel Switch", NodeType.SWITCH, 1_000, 30, 640, 490),
    NodeDef("SW4", "Admin Switch", NodeType.SWITCH, 1_000, 30, 900, 490),
)

DEFAULT_LINKS: tuple[LinkDef, ...] = (
    LinkDef("L-GW-R1", "GW", "R1", 5.0, 10_000),
    LinkDef("L-R1-R2", "R1", "R2", 4.0, 10_000),
    LinkDef("L-R1-R3", "R1", "R3", 4.0, 10_000),
    LinkDef("L-R1-R4", "R1", "R4", 4.0, 10_000),
    LinkDef("L-R1-SRV", "R1", "SRV", 2.0, 2_000),
    LinkDef("L-R2-R3", "R2", "R3", 6.0, 2_000),
    LinkDef("L-R3-R4", "R3", "R4", 6.0, 2_000),
    # Access uplinks: primary (3 ms) + backup (8-9 ms)
    LinkDef("L-R2-SW1", "R2", "SW1", 3.0, 1_000),
    LinkDef("L-R3-SW1", "R3", "SW1", 8.0, 1_000),
    LinkDef("L-R3-SW2", "R3", "SW2", 3.0, 1_000),
    LinkDef("L-R2-SW2", "R2", "SW2", 8.0, 1_000),
    LinkDef("L-R4-SW3", "R4", "SW3", 3.0, 1_000),
    LinkDef("L-R3-SW3", "R3", "SW3", 8.0, 1_000),
    LinkDef("L-R4-SW4", "R4", "SW4", 3.0, 1_000),
    LinkDef("L-R3-SW4", "R3", "SW4", 9.0, 1_000),
)

DEFAULT_FLOWS: tuple[FlowDef, ...] = (
    FlowDef("F1", "Academic → Internet", "SW1", "GW", 350),
    FlowDef("F2", "Library → Internet", "SW2", "GW", 250),
    FlowDef("F3", "Hostel → Internet", "SW3", "GW", 400),
    FlowDef("F4", "Admin → Internet", "SW4", "GW", 150),
    FlowDef("F5", "Hostel → Campus Server", "SW3", "SRV", 200),
    FlowDef("F6", "Academic → Campus Server", "SW1", "SRV", 150),
)
