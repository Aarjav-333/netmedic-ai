import { Activity, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import { cn } from "cn";
import { StatusPill } from "@/components/dashboard/status-pill";
import type { ConnectionStatus } from "@/hooks/use-network-socket";
import { healthFromScore } from "@/lib/status";
import type { NetworkSummary } from "@/lib/types";

const CONNECTION_LABEL: Record<ConnectionStatus, string> = {
  connecting: "Connecting",
  connected: "Live",
  reconnecting: "Reconnecting",
  offline: "Backend offline",
};

export function TopBar({
  summary,
  connection,
  autoHealing,
  tick,
}: {
  summary: NetworkSummary | null;
  connection: ConnectionStatus;
  autoHealing: boolean;
  tick: number;
}) {
  const networkStatus = summary ? healthFromScore(summary.health_score) : "offline";
  const online = connection === "connected";

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-5 py-3">
      <div className="flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Activity className="size-5" aria-hidden />
        </div>
        <div>
          <h1 className="text-lg font-semibold leading-tight tracking-tight">NetMedic AI</h1>
          <p className="text-xs text-muted-foreground">
            Autonomous Network Detection, Diagnosis &amp; Self-Healing
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 rounded-full border border-border/60 px-3 py-1 text-xs">
          <span className="text-muted-foreground">Network</span>
          <StatusPill
            status={networkStatus}
            label={summary ? `${networkStatus === "healthy" ? "Healthy" : networkStatus === "warning" ? "Degraded" : networkStatus === "critical" ? "Critical" : "Unknown"}` : "Unknown"}
          />
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border/60 px-3 py-1 text-xs">
          <ShieldCheck
            className={cn("size-3.5", autoHealing ? "text-status-good" : "text-muted-foreground")}
            aria-hidden
          />
          <span className="text-muted-foreground">Auto-healing</span>
          <span className="font-medium">{autoHealing ? "Armed" : "Manual"}</span>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border/60 px-3 py-1 text-xs">
          {online ? (
            <Wifi className="size-3.5 text-status-good" aria-hidden />
          ) : (
            <WifiOff className="size-3.5 text-status-critical" aria-hidden />
          )}
          <span className="font-medium">{CONNECTION_LABEL[connection]}</span>
          {online && <span className="text-muted-foreground tabular-nums">tick {tick}</span>}
        </div>
      </div>
    </header>
  );
}
