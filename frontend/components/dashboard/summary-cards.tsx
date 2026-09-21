import { Card } from "@/components/ui/card";
import { StatusPill } from "@/components/dashboard/status-pill";
import { STATUS_COLOR, formatMbps, formatNumber, healthFromScore } from "@/lib/status";
import type { NetworkSummary } from "@/lib/types";

function StatTile({
  label,
  value,
  unit,
  hint,
  hero = false,
  accent,
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
  hero?: boolean;
  accent?: string;
}) {
  return (
    <Card size="sm" className="justify-between gap-1 px-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="flex items-baseline gap-1">
        <span
          className={hero ? "text-4xl font-semibold leading-none" : "text-2xl font-semibold leading-none"}
          style={accent ? { color: accent } : undefined}
        >
          {value}
        </span>
        {unit && <span className="text-xs text-muted-foreground">{unit}</span>}
      </p>
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </Card>
  );
}

export function SummaryCards({
  summary,
  incidentCount,
}: {
  summary: NetworkSummary | null;
  incidentCount: number;
}) {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} size="sm" className="h-[92px] animate-pulse bg-muted/40" />
        ))}
      </div>
    );
  }

  const health = healthFromScore(summary.health_score);

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Card size="sm" className="justify-between gap-1 px-4">
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">Network health</p>
          <StatusPill status={health} />
        </div>
        <p className="flex items-baseline gap-1">
          <span className="text-4xl font-semibold leading-none" style={{ color: STATUS_COLOR[health] }}>
            {formatNumber(summary.health_score)}
          </span>
          <span className="text-xs text-muted-foreground">/ 100</span>
        </p>
        <p className="text-[11px] text-muted-foreground">
          flows {formatNumber(summary.flow_health)} · nodes {formatNumber(summary.node_health)} · links{" "}
          {formatNumber(summary.link_health)}
        </p>
      </Card>
      <StatTile
        label="Active nodes"
        value={`${summary.active_nodes}`}
        unit={`/ ${summary.total_nodes}`}
        hint={`${summary.active_links} / ${summary.total_links} links up`}
      />
      <StatTile
        label="Current incidents"
        value={`${incidentCount}`}
        hint={incidentCount === 0 ? "No open incidents" : "Under investigation"}
        accent={incidentCount > 0 ? STATUS_COLOR.critical : undefined}
      />
      <StatTile
        label="Avg latency"
        value={formatNumber(summary.avg_latency_ms, 1)}
        unit="ms"
        hint={`end-to-end · nodes ${formatNumber(summary.avg_node_latency_ms, 1)} ms`}
      />
      <StatTile
        label="Packet loss"
        value={formatNumber(summary.avg_packet_loss_percent, 2)}
        unit="%"
        hint={summary.broken_flows > 0 ? `${summary.broken_flows} flow(s) down` : "end-to-end average"}
      />
      <StatTile
        label="Throughput"
        value={formatMbps(summary.total_throughput_mbps)}
        hint={`of ${formatMbps(summary.total_demand_mbps)} demand${summary.rerouted_flows ? ` · ${summary.rerouted_flows} rerouted` : ""}`}
      />
    </div>
  );
}
