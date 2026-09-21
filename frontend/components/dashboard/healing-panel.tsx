"use client";

import { useState } from "react";
import { ArrowRight, CheckCircle2, Loader2, Play, Wrench, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/dashboard/status-pill";
import { outcomeColor } from "@/components/dashboard/incident-status";
import { ApiError, executeHealing } from "@/lib/api";
import { formatNumber, healthFromScore } from "@/lib/status";
import type { HealthStatus, Incident, IncidentStatus, MetricWindow } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = {
  reroute_around_node: "Reroute traffic around node",
  reroute_around_link: "Reroute traffic around link",
  isolate_link: "Isolate failed link",
  restart_node: "Restart node service",
  rate_limit_source: "Rate-limit source & rebalance",
  redistribute_load: "Redistribute load",
  escalate: "Escalate to operator",
  monitor: "Monitor",
};

const EXECUTION_LABEL: Partial<Record<IncidentStatus, string>> = {
  detected: "Waiting for diagnosis",
  analyzing: "Waiting for diagnosis",
  diagnosed: "Ready",
  remediating: "Executing",
  verifying: "Applied — verifying",
  resolved: "Applied — verified",
  partially_resolved: "Applied — partial recovery",
  failed: "Not applied / failed",
  cancelled: "Cancelled",
};

function recoveryStatus(status: IncidentStatus): { label: string; health: HealthStatus } {
  switch (status) {
    case "resolved":
      return { label: "VERIFIED", health: "healthy" };
    case "partially_resolved":
      return { label: "PARTIAL", health: "warning" };
    case "failed":
      return { label: "FAILED", health: "critical" };
    default:
      return { label: "PENDING", health: "offline" };
  }
}

function WindowColumn({ title, window: w }: { title: string; window: MetricWindow | null }) {
  const health = w ? healthFromScore(w.health_score) : null;
  return (
    <div className="rounded-md border border-border/60 p-2">
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      {w ? (
        <dl className="space-y-0.5 text-xs tabular-nums">
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Latency</dt>
            <dd className="font-medium">{formatNumber(w.avg_latency_ms)} ms</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Packet loss</dt>
            <dd className="font-medium">{formatNumber(w.avg_packet_loss_percent, 1)}%</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Health</dt>
            <dd className="font-medium" style={{ color: health ? `var(--status-${health === "healthy" ? "good" : health})` : undefined }}>
              {formatNumber(w.health_score)}%
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Flows OK</dt>
            <dd className="font-medium">
              {w.affected_flows_healthy}/{w.affected_flows_total}
            </dd>
          </div>
        </dl>
      ) : (
        <p className="text-xs text-muted-foreground">—</p>
      )}
    </div>
  );
}

export function HealingPanel({ incident, autoHeal }: { incident: Incident | null; autoHeal: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const plan = incident?.plan ?? null;
  const action = incident?.actions.find((a) => a.result === "applied" || a.result === "skipped" || a.result === "failed") ?? null;
  const recovery = incident?.recovery ?? null;
  const awaitingApproval = incident?.status === "diagnosed" && !incident.auto_heal;

  const approve = async () => {
    if (!incident) return;
    setBusy(true);
    setError(null);
    try {
      await executeHealing(incident.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Wrench className="size-4 text-muted-foreground" aria-hidden />
          Self-healing
        </CardTitle>
        <span className="text-[11px] text-muted-foreground">{autoHeal ? "automatic" : "manual approval"}</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {!incident && <p className="text-xs text-muted-foreground">Idle. Remediation actions run here once a root cause is identified.</p>}

        {incident && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Action selected</p>
                <p className="font-medium">{plan ? ACTION_LABEL[plan.action] ?? plan.action : "Pending diagnosis"}</p>
                {plan && <p className="text-[11px] text-muted-foreground">target {plan.target_id}</p>}
              </div>
              <div>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Execution state</p>
                <p className="flex items-center gap-1.5 font-medium" style={{ color: outcomeColor(incident.status) }}>
                  {incident.status === "remediating" || incident.status === "verifying" ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  ) : action?.result === "applied" ? (
                    <CheckCircle2 className="size-3.5" aria-hidden />
                  ) : action ? (
                    <XCircle className="size-3.5" aria-hidden />
                  ) : null}
                  {EXECUTION_LABEL[incident.status]}
                </p>
                {action && <p className="text-[11px] text-muted-foreground">{action.details}</p>}
              </div>
            </div>

            {awaitingApproval && (
              <div className="flex items-center justify-between gap-2 rounded-md border border-status-warning/50 bg-status-warning/10 px-3 py-2">
                <p className="text-xs">Auto-healing is off. Approve the recommended action to continue.</p>
                <Button size="sm" onClick={approve} disabled={busy}>
                  {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Play className="size-4" aria-hidden />}
                  Execute
                </Button>
              </div>
            )}
            {error && <p className="text-xs text-status-critical">{error}</p>}

            {action && action.route_changes.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Alternative routes</p>
                <ul className="space-y-1 text-xs">
                  {action.route_changes.map((c) => (
                    <li key={c.flow_id} className="flex flex-wrap items-center gap-1.5">
                      <span className="w-6 font-semibold">{c.flow_id}</span>
                      <span className="text-muted-foreground line-through">{c.before.join(" › ")}</span>
                      <ArrowRight className="size-3 text-muted-foreground" aria-hidden />
                      <span className="font-medium" style={{ color: "var(--series-3)" }}>
                        {c.after.length ? c.after.join(" › ") : "no path"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <div className="mb-1 flex items-center justify-between">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Recovery verification</p>
                <StatusPill status={recoveryStatus(incident.status).health} label={recoveryStatus(incident.status).label} />
              </div>
              {recovery ? (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <WindowColumn title="Before" window={recovery.before} />
                    <WindowColumn title="After" window={recovery.after} />
                  </div>
                  <ul className="mt-2 space-y-1 text-xs">
                    {recovery.checks.map((c) => (
                      <li key={c.name} className="flex items-start gap-2">
                        {c.passed ? (
                          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-status-good" aria-hidden />
                        ) : (
                          <XCircle className="mt-0.5 size-3.5 shrink-0 text-status-critical" aria-hidden />
                        )}
                        <span>
                          <span className="font-medium">{c.name}</span>
                          <span className="text-muted-foreground"> — {c.detail}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-muted-foreground">{recovery.summary}</p>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {incident.status === "verifying"
                    ? "Collecting post-remediation samples before comparing windows…"
                    : incident.status === "failed"
                      ? "No remediation was applied, so nothing to verify."
                      : "Verification starts after the remediation is applied."}
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
