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
  activeId,
  onSelect,
}: {
  incidents: IncidentSummary[];
  /** Explicitly chosen by the operator - drives the toggle state. */
  selectedId: string | null;
  /** Whatever the panels are currently showing, selected or defaulted to. */
  activeId: string | null;
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
                  // `selected` is an explicit choice; `active` is merely what is on screen.
                  // Conflating them made the toggle on the auto-shown row impossible to release.
                  const selected = i.id === selectedId;
                  const active = i.id === activeId;
                  return (
                    <tr
                      key={i.id}
                      className={`cursor-pointer border-b border-border/40 transition-colors hover:bg-muted/40 has-focus-visible:bg-muted/50 ${active ? "bg-muted/50" : ""}`}
                      onClick={() => onSelect(selected ? null : i.id)}
                    >
                      {/* The row stays clickable for the mouse, but selection lives on a real
                          button so it is reachable by keyboard and announced as pressed. */}
                      <td className="px-4 py-1.5 tabular-nums">
                        <button
                          type="button"
                          aria-pressed={selected}
                          aria-label={`Review incident on ${i.component_id} detected at ${formatTime(i.detected_at)}`}
                          className="cursor-pointer rounded-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                          onClick={(event) => {
                            event.stopPropagation();
                            onSelect(selected ? null : i.id);
                          }}
                        >
                          {formatTime(i.detected_at)}
                        </button>
                      </td>
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
