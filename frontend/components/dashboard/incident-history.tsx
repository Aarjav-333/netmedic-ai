"use client";

import { History } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/dashboard/status-pill";
import { formatTime } from "@/lib/status";
import type { HealthStatus, IncidentStatus, IncidentSummary } from "@/lib/types";

function pill(status: IncidentStatus): { health: HealthStatus; label: string } {
  switch (status) {
    case "resolved":
      return { health: "healthy", label: "Resolved" };
    case "partially_resolved":
      return { health: "warning", label: "Partial" };
    case "failed":
      return { health: "critical", label: "Failed" };
    case "cancelled":
      return { health: "offline", label: "Cancelled" };
    default:
      return { health: "warning", label: "In progress" };
  }
}

export function IncidentHistory({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: IncidentSummary[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <History className="size-4 text-muted-foreground" aria-hidden />
          Incident history
        </CardTitle>
        <span className="text-[11px] text-muted-foreground">{incidents.length} recorded</span>
      </CardHeader>
      <CardContent className="px-0">
        {incidents.length === 0 ? (
          <p className="px-4 text-xs text-muted-foreground">No incidents recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="px-4 py-1.5 font-medium">Detected</th>
                  <th className="px-2 py-1.5 font-medium">Component</th>
                  <th className="px-2 py-1.5 font-medium">Root cause</th>
                  <th className="px-2 py-1.5 font-medium">Confidence</th>
                  <th className="px-2 py-1.5 font-medium">Action</th>
                  <th className="px-2 py-1.5 font-medium">Recovery</th>
                  <th className="px-2 py-1.5 font-medium">Total</th>
                  <th className="px-4 py-1.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((i) => {
                  const p = pill(i.status);
                  const selected = i.id === selectedId;
                  return (
                    <tr
                      key={i.id}
                      className={`cursor-pointer border-b border-border/40 transition-colors hover:bg-muted/40 ${selected ? "bg-muted/50" : ""}`}
                      onClick={() => onSelect(selected ? null : i.id)}
                    >
                      <td className="px-4 py-1.5 tabular-nums">{formatTime(i.detected_at)}</td>
                      <td className="px-2 py-1.5 font-medium">{i.component_id}</td>
                      <td className="px-2 py-1.5">{i.root_cause_label ?? "—"}</td>
                      <td className="px-2 py-1.5 tabular-nums">{i.confidence === null ? "—" : `${Math.round(i.confidence * 100)}%`}</td>
                      <td className="px-2 py-1.5">{i.action ? i.action.replaceAll("_", " ") : "—"}</td>
                      <td className="px-2 py-1.5 tabular-nums">{i.recovery_time_s === null ? "—" : `${i.recovery_time_s.toFixed(1)} s`}</td>
                      <td className="px-2 py-1.5 tabular-nums">{i.total_duration_s === null ? "—" : `${i.total_duration_s.toFixed(1)} s`}</td>
                      <td className="px-4 py-1.5">
                        <StatusPill status={p.health} label={p.label} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
