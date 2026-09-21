"use client";

import { useEffect, useMemo, useState } from "react";
import { DiagnosisPanel } from "@/components/dashboard/diagnosis-panel";
import { FaultInjector } from "@/components/dashboard/fault-injector";
import { HealingPanel } from "@/components/dashboard/healing-panel";
import { IncidentHistory } from "@/components/dashboard/incident-history";
import { IncidentStatusCard } from "@/components/dashboard/incident-status";
import { IncidentTimeline } from "@/components/dashboard/incident-timeline";
import { MetricsPanel } from "@/components/dashboard/metrics-panel";
import { SummaryCards } from "@/components/dashboard/summary-cards";
import { TopBar } from "@/components/dashboard/top-bar";
import { TopologyView } from "@/components/dashboard/topology/topology-view";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useNetworkSocket } from "@/hooks/use-network-socket";
import { getIncident } from "@/lib/api";
import type { Incident } from "@/lib/types";

const DEFAULT_NODE = "R4";

export function Dashboard() {
  const { state, history, status, clearHistory } = useNetworkSocket();
  const [selectedNode, setSelectedNode] = useState(DEFAULT_NODE);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [historicIncident, setHistoricIncident] = useState<Incident | null>(null);

  const topology = state?.topology ?? null;
  const telemetry = state?.telemetry ?? null;
  const summary = telemetry?.summary ?? null;
  const activeIncident = state?.incident ?? null;
  const incidents = useMemo(() => state?.incidents ?? [], [state?.incidents]);
  const autoHeal = state?.auto_heal ?? true;

  // With no active incident, show the selected (or most recent) historical one in the panels.
  const fallbackId = selectedIncidentId ?? incidents.find((i) => i.status !== "cancelled")?.id ?? null;
  useEffect(() => {
    if (activeIncident || !fallbackId) return;
    let cancelled = false;
    getIncident(fallbackId)
      .then((incident) => {
        if (!cancelled) setHistoricIncident(incident);
      })
      .catch(() => {
        if (!cancelled) setHistoricIncident(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeIncident, fallbackId, incidents]);

  const displayedIncident =
    activeIncident ?? (fallbackId && historicIncident?.id === fallbackId ? historicIncident : null);
  const openIncidentCount = activeIncident ? 1 : 0;

  // Fall back to the first node if the selection is not part of the topology.
  const effectiveNode =
    !topology || topology.nodes.some((n) => n.id === selectedNode)
      ? selectedNode
      : (topology.nodes[0]?.id ?? DEFAULT_NODE);

  // Highlight the component the active incident is about.
  const affectedIds = useMemo(
    () => new Set<string>(activeIncident ? [activeIncident.component_id] : []),
    [activeIncident],
  );

  const handleReset = () => {
    clearHistory();
    setSelectedIncidentId(null);
  };

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar summary={summary} connection={status} autoHealing={autoHeal} tick={state?.tick ?? 0} />

      <main className="flex flex-1 flex-col gap-4 p-4 md:p-5">
        <SummaryCards summary={summary} incidentCount={openIncidentCount} />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]">
          <Card size="sm" className="gap-2">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-sm">Network topology</CardTitle>
              <span className="text-[11px] text-muted-foreground">
                {topology
                  ? `${topology.nodes.length} nodes · ${topology.links.length} links · ${topology.flows.length} flows${
                      state?.quarantined.length ? ` · isolated: ${state.quarantined.join(", ")}` : ""
                    }`
                  : "waiting for backend…"}
              </span>
            </CardHeader>
            <CardContent className="px-3 pb-1">
              {topology ? (
                <TopologyView topology={topology} telemetry={telemetry} affectedIds={affectedIds} />
              ) : (
                <div className="flex h-[560px] items-center justify-center rounded-lg border border-dashed border-border/60 text-sm text-muted-foreground">
                  {status === "offline"
                    ? "Backend is offline — start the API on port 8000."
                    : "Connecting to telemetry stream…"}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-col gap-4">
            <IncidentStatusCard incident={activeIncident} lastIncident={incidents[0] ?? null} />
            <FaultInjector
              topology={topology}
              activeFaults={state?.faults ?? []}
              demo={state?.demo ?? null}
              onReset={handleReset}
              disabled={status !== "connected"}
            />
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <DiagnosisPanel incident={displayedIncident} />
          <HealingPanel incident={displayedIncident} autoHeal={autoHeal} />
          <IncidentTimeline incident={displayedIncident} />
        </div>

        <MetricsPanel
          history={history}
          nodes={topology?.nodes ?? []}
          selectedNode={effectiveNode}
          onSelectNode={setSelectedNode}
        />

        <IncidentHistory incidents={incidents} selectedId={fallbackId} onSelect={setSelectedIncidentId} />
      </main>
    </div>
  );
}
