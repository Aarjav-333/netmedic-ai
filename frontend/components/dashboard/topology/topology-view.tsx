"use client";

import { useEffect, useMemo } from "react";
import { Background, BackgroundVariant, Controls, ReactFlow, useNodesState, useEdgesState } from "@xyflow/react";
import { LinkEdge, type LinkFlowEdge } from "@/components/dashboard/topology/link-edge";
import { NetworkNode, type NetworkFlowNode } from "@/components/dashboard/topology/network-node";
import { STATUS_COLOR } from "@/lib/status";
import type { TelemetrySnapshot, Topology } from "@/lib/types";

const nodeTypes = { network: NetworkNode };
const edgeTypes = { link: LinkEdge };

function buildNodes(
  topology: Topology,
  telemetry: TelemetrySnapshot | null,
  affectedIds: Set<string>,
): NetworkFlowNode[] {
  const byId = new Map(telemetry?.nodes.map((n) => [n.node_id, n]) ?? []);
  return topology.nodes.map((n) => ({
    id: n.id,
    type: "network",
    position: { x: n.position.x, y: n.position.y },
    draggable: true,
    data: {
      label: n.id,
      name: n.name,
      nodeType: n.type,
      health: n.status === "down" ? "offline" : n.health,
      isolated: n.isolated,
      affected: affectedIds.has(n.id),
      telemetry: byId.get(n.id) ?? null,
    },
  }));
}

function buildEdges(topology: Topology, telemetry: TelemetrySnapshot | null): LinkFlowEdge[] {
  const linkTelemetry = new Map(telemetry?.links.map((l) => [l.link_id, l]) ?? []);
  const activeLinks = new Set<string>();
  const reroutedLinks = new Set<string>();
  for (const route of topology.routes) {
    for (const linkId of route.links) {
      activeLinks.add(linkId);
      if (!route.is_primary) reroutedLinks.add(linkId);
    }
  }
  return topology.links.map((l) => {
    const t = linkTelemetry.get(l.id);
    const down = l.status === "down";
    return {
      id: l.id,
      type: "link",
      source: l.source,
      target: l.target,
      data: {
        health: down ? "offline" : l.health,
        utilization: t?.utilization_percent ?? 0,
        active: activeLinks.has(l.id),
        rerouted: reroutedLinks.has(l.id),
        isolated: l.isolated,
        down,
      },
    };
  });
}

export function TopologyView({
  topology,
  telemetry,
  affectedIds,
}: {
  topology: Topology;
  telemetry: TelemetrySnapshot | null;
  affectedIds: Set<string>;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<NetworkFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<LinkFlowEdge>([]);

  const nextNodes = useMemo(() => buildNodes(topology, telemetry, affectedIds), [topology, telemetry, affectedIds]);
  const nextEdges = useMemo(() => buildEdges(topology, telemetry), [topology, telemetry]);

  // Keep user-dragged positions while refreshing data every tick.
  useEffect(() => {
    setNodes((current) => {
      const positions = new Map(current.map((n) => [n.id, n.position]));
      return nextNodes.map((n) => ({ ...n, position: positions.get(n.id) ?? n.position }));
    });
  }, [nextNodes, setNodes]);

  useEffect(() => {
    setEdges(nextEdges);
  }, [nextEdges, setEdges]);

  return (
    <div className="relative h-[560px] w-full overflow-hidden rounded-lg border border-border/60 bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.4}
        maxZoom={1.6}
        nodesConnectable={false}
        elementsSelectable
        deleteKeyCode={null}
        proOptions={{ hideAttribution: false }}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--chart-grid)" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
      <TopologyLegend />
    </div>
  );
}

function TopologyLegend() {
  const items: { label: string; color: string; kind: "dot" | "line" | "dash" }[] = [
    { label: "Healthy", color: STATUS_COLOR.healthy, kind: "dot" },
    { label: "Warning", color: STATUS_COLOR.warning, kind: "dot" },
    { label: "Critical", color: STATUS_COLOR.critical, kind: "dot" },
    { label: "Offline", color: STATUS_COLOR.offline, kind: "dot" },
    { label: "Active route", color: "var(--series-1)", kind: "dash" },
    { label: "Rerouted", color: "var(--series-3)", kind: "dash" },
  ];
  return (
    <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded-md border border-border/60 bg-background/90 px-2 py-1 text-[11px] text-muted-foreground">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          {item.kind === "dot" ? (
            <span className="inline-block size-2 rounded-full" style={{ backgroundColor: item.color }} />
          ) : (
            <span
              className="inline-block h-0 w-4 border-t-2"
              style={{ borderColor: item.color, borderStyle: "dashed" }}
            />
          )}
          {item.label}
        </span>
      ))}
    </div>
  );
}
