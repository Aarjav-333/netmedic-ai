"""Topology and network status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.engine import SimulationEngine, get_engine
from app.models.network import AdminStatus, TopologyResponse

router = APIRouter(prefix="/network", tags=["network"])


class NetworkStatusResponse(BaseModel):
    node_count: int
    active_nodes: int
    link_count: int
    active_links: int
    flow_count: int
    rerouted_flows: int
    broken_flows: int
    tick: int


@router.get("/topology", response_model=TopologyResponse)
async def get_topology(engine: SimulationEngine = Depends(get_engine)) -> TopologyResponse:
    return engine.network.to_topology_response()


@router.get("/status", response_model=NetworkStatusResponse)
async def get_status(engine: SimulationEngine = Depends(get_engine)) -> NetworkStatusResponse:
    net = engine.network
    return NetworkStatusResponse(
        node_count=len(net.nodes),
        active_nodes=sum(1 for n in net.nodes.values() if n.status == AdminStatus.UP),
        link_count=len(net.links),
        active_links=sum(1 for l in net.links.values() if l.status == AdminStatus.UP),
        flow_count=len(net.flows),
        rerouted_flows=sum(1 for r in net.routes.values() if not r.is_primary and not r.is_broken),
        broken_flows=sum(1 for r in net.routes.values() if r.is_broken),
        tick=engine.tick_count,
    )
