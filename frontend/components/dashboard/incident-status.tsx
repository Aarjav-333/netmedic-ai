"use client";

import { Activity, CheckCircle2, Loader2, OctagonAlert, Radar, Route, Stethoscope, Wrench } from "lucide-react";
import { cn } from "cn";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_COLOR, formatTime } from "@/lib/status";
import type { Incident, IncidentStatus, IncidentSummary } from "@/lib/types";

const STAGES: { key: string; label: string; icon: typeof Radar; statuses: IncidentStatus[] }[] = [
  { key: "detect", label: "Detect", icon: Radar, statuses: ["detected"] },
  { key: "diagnose", label: "Diagnose", icon: Stethoscope, statuses: ["analyzing", "diagnosed"] },
  { key: "heal", label: "Heal", icon: Wrench, statuses: ["remediating"] },
  { key: "verify", label: "Verify", icon: Route, statuses: ["verifying"] },
];

const TERMINAL: IncidentStatus[] = ["resolved", "partially_resolved", "failed", "cancelled"];

function stageIndex(status: IncidentStatus): number {
  if (TERMINAL.includes(status)) return STAGES.length;
  return STAGES.findIndex((s) => s.statuses.includes(status));
}

export function outcomeColor(status: IncidentStatus): string {
  switch (status) {
    case "resolved":
      return STATUS_COLOR.healthy;
    case "partially_resolved":
      return STATUS_COLOR.warning;
    case "failed":
      return STATUS_COLOR.critical;
    case "cancelled":
      return STATUS_COLOR.offline;
    case "detected":
    case "analyzing":
      return STATUS_COLOR.critical;
    case "diagnosed":
    case "remediating":
      return STATUS_COLOR.warning;
    default:
      return "var(--series-1)";
  }
}

/** Big, judge-readable label for the current stage. */
export function headline(incident: Incident): string {
  if (incident.status === "remediating" && incident.actions.some((a) => a.route_changes.length > 0)) {
    return "TRAFFIC REROUTED";
  }
  return incident.status_label;
}

export function IncidentStatusCard({
  incident,
  lastIncident,
}: {
  incident: Incident | null;
  lastIncident: IncidentSummary | null;
}) {
  const current = incident ? stageIndex(incident.status) : -1;
  const terminal = incident ? TERMINAL.includes(incident.status) : false;
  const color = incident ? outcomeColor(incident.status) : STATUS_COLOR.healthy;

  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Activity className="size-4 text-muted-foreground" aria-hidden />
          Incident pipeline
        </CardTitle>
        {incident && <span className="text-[11px] text-muted-foreground tabular-nums">{incident.id}</span>}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div
          className="rounded-lg border px-3 py-2.5"
          style={{
            borderColor: `color-mix(in oklab, ${color} 50%, transparent)`,
            backgroundColor: `color-mix(in oklab, ${color} 10%, transparent)`,
          }}
        >
          <p className="flex items-center gap-2 text-sm font-semibold tracking-wide" style={{ color }}>
            {incident ? (
              terminal ? (
                incident.status === "resolved" ? (
                  <CheckCircle2 className="size-4" aria-hidden />
                ) : (
                  <OctagonAlert className="size-4" aria-hidden />
                )
              ) : (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              )
            ) : (
              <CheckCircle2 className="size-4" aria-hidden />
            )}
            {incident ? headline(incident) : "MONITORING — NO INCIDENTS"}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {incident
              ? `${incident.component_id} · ${incident.root_cause_label ?? "root cause pending"} · since ${formatTime(incident.detected_at)}`
              : lastIncident
                ? `Last incident: ${lastIncident.component_id} ${lastIncident.status_label.toLowerCase()} at ${formatTime(lastIncident.resolved_at ?? lastIncident.detected_at)}`
                : "Telemetry within healthy bands on every component."}
          </p>
        </div>

        <ol className="grid grid-cols-4 gap-1">
          {STAGES.map((stage, i) => {
            const Icon = stage.icon;
            const done = incident ? i < current || terminal : false;
            const active = incident ? i === current && !terminal : false;
            return (
              <li key={stage.key} className="flex flex-col items-center gap-1 text-center">
                <span
                  className={cn(
                    "flex size-8 items-center justify-center rounded-full border transition-colors",
                    done && "border-transparent bg-status-good/20 text-status-good",
                    active && "border-transparent text-background",
                    !done && !active && "border-border/60 text-muted-foreground",
                  )}
                  style={active ? { backgroundColor: color } : undefined}
                >
                  {done ? <CheckCircle2 className="size-4" aria-hidden /> : <Icon className={cn("size-4", active && "animate-pulse")} aria-hidden />}
                </span>
                <span className={cn("text-[11px]", active ? "font-semibold text-foreground" : "text-muted-foreground")}>{stage.label}</span>
              </li>
            );
          })}
        </ol>

        {incident && (
          <dl className="grid grid-cols-4 gap-1 text-center text-[11px] text-muted-foreground">
            <Timing label="detect" value={incident.metrics.time_to_detect_s} />
            <Timing label="diagnose" value={incident.metrics.time_to_diagnose_s} />
            <Timing label="remediate" value={incident.metrics.time_to_remediate_s} />
            <Timing label="recover" value={incident.metrics.recovery_time_s} />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function Timing({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="font-medium text-foreground tabular-nums">{value === null ? "—" : `${value.toFixed(1)} s`}</dd>
    </div>
  );
}
