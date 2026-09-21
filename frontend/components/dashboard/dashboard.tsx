"use client";

import { useMemo, useState } from "react";
import { MetricsPanel } from "@/components/dashboard/metrics-panel";
import { SummaryCards } from "@/components/dashboard/summary-cards";
import { TopBar } from "@/components/dashboard/top-bar";
import { TopologyView } from "@/components/dashboard/topology/topology-view";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useNetworkSocket } from "@/hooks/use-network-socket";

const DEFAULT_NODE = "R4";

export function Dashboard() {
  const { state, history, status } = useNetworkSocket();
  const [selectedNode, setSelectedNode] = useState(DEFAULT_NODE);

  const topology = state?.topology ?? null;
  const telemetry = state?.telemetry ?? null;
  const summary = telemetry?.summary ?? null;

  // Fall back to the first node if the selection is not part of the topology.
  const effectiveNode =
    !topology || topology.nodes.some((n) => n.id === selectedNode)
      ? selectedNode
      : (topology.nodes[0]?.id ?? DEFAULT_NODE);

  // Nodes the pipeline currently flags (populated by incidents in later phases).
  const affectedIds = useMemo(() => new Set<string>(), []);

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar summary={summary} connection={status} autoHealing tick={state?.tick ?? 0} />

      <main className="flex flex-1 flex-col gap-4 p-4 md:p-5">
        <SummaryCards summary={summary} incidentCount={0} />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
          <Card size="sm" className="gap-2">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-sm">Network topology</CardTitle>
              <span className="text-[11px] text-muted-foreground">
                {topology
                  ? `${topology.nodes.length} nodes · ${topology.links.length} links · ${topology.flows.length} flows`
                  : "waiting for backend…"}
              </span>
            </CardHeader>
            <CardContent className="px-3 pb-1">
              {topology ? (
                <TopologyView topology={topology} telemetry={telemetry} affectedIds={affectedIds} />
              ) : (
                <div className="flex h-[560px] items-center justify-center rounded-lg border border-dashed border-border/60 text-sm text-muted-foreground">
                  {status === "offline" ? "Backend is offline — start the API on port 8000." : "Connecting to telemetry stream…"}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-col gap-4">
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-sm">Fault injector</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">Available in the next phase.</CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-sm">AI diagnosis</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">No incidents detected.</CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-sm">Self-healing</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">Idle.</CardContent>
            </Card>
          </div>
        </div>

        <MetricsPanel
          history={history}
          nodes={topology?.nodes ?? []}
          selectedNode={effectiveNode}
          onSelectNode={setSelectedNode}
        />
      </main>
    </div>
  );
}
