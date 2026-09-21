"use client";

import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatNumber, formatTime } from "@/lib/status";
import type { MetricPoint, NetworkNode } from "@/lib/types";

type Row = { tick: number; time: string; node: number | null; avg: number };

function meanOf(values: Record<string, number>): number {
  const nums = Object.values(values);
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : 0;
}

function buildRows(history: MetricPoint[], nodeId: string, key: keyof MetricPoint): Row[] {
  return history.map((p) => {
    const values = p[key] as Record<string, number>;
    return {
      tick: p.tick,
      time: formatTime(p.timestamp),
      node: values[nodeId] ?? null,
      avg: meanOf(values),
    };
  });
}

const CHART_MARGIN = { top: 8, right: 8, bottom: 0, left: -12 };

function ChartTooltip({
  active,
  payload,
  label,
  unit,
  nodeId,
}: {
  active?: boolean;
  payload?: { dataKey: string; value: number | null }[];
  label?: string;
  unit: string;
  nodeId: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border/60 bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 text-muted-foreground">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex items-center gap-2 tabular-nums">
          <span
            className="inline-block size-2 rounded-full"
            style={{ backgroundColor: entry.dataKey === "node" ? "var(--series-1)" : "var(--chart-muted)" }}
          />
          <span className="text-muted-foreground">{entry.dataKey === "node" ? nodeId : "Network avg"}</span>
          <span className="ml-auto font-medium">
            {entry.value === null ? "—" : `${formatNumber(entry.value, unit === "%" ? 1 : 0)} ${unit}`}
          </span>
        </p>
      ))}
    </div>
  );
}

function NodeMetricChart({
  title,
  unit,
  rows,
  nodeId,
  domain,
}: {
  title: string;
  unit: string;
  rows: Row[];
  nodeId: string;
  domain?: [number, number | "auto"];
}) {
  return (
    <Card size="sm" className="gap-2">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">{title}</CardTitle>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: "var(--series-1)" }} />
            {nodeId}
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: "var(--chart-muted)" }} />
            Network avg
          </span>
        </div>
      </CardHeader>
      <CardContent className="h-[150px] px-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={CHART_MARGIN}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="0" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fill: "var(--chart-muted)", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "var(--chart-axis)" }}
              minTickGap={48}
            />
            <YAxis
              tick={{ fill: "var(--chart-muted)", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={44}
              domain={domain ?? [0, "auto"]}
              allowDecimals={false}
            />
            <Tooltip content={<ChartTooltip unit={unit} nodeId={nodeId} />} cursor={{ stroke: "var(--chart-axis)" }} />
            <Line
              type="monotone"
              dataKey="avg"
              stroke="var(--chart-muted)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="node"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function ThroughputChart({ history }: { history: MetricPoint[] }) {
  const rows = history.map((p) => ({ tick: p.tick, time: formatTime(p.timestamp), total: p.total_throughput_mbps }));
  return (
    <Card size="sm" className="gap-2">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">Network throughput</CardTitle>
        <span className="text-[11px] text-muted-foreground">delivered, all flows</span>
      </CardHeader>
      <CardContent className="h-[150px] px-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={CHART_MARGIN}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="0" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fill: "var(--chart-muted)", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "var(--chart-axis)" }}
              minTickGap={48}
            />
            <YAxis
              tick={{ fill: "var(--chart-muted)", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={44}
              domain={[0, "auto"]}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ stroke: "var(--chart-axis)" }}
              formatter={(value) => [`${formatNumber(Number(value))} Mbps`, "Throughput"]}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: 12,
              }}
            />
            <Area
              type="monotone"
              dataKey="total"
              stroke="var(--series-1)"
              strokeWidth={2}
              fill="var(--series-1)"
              fillOpacity={0.1}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function MetricsPanel({
  history,
  nodes,
  selectedNode,
  onSelectNode,
}: {
  history: MetricPoint[];
  nodes: NetworkNode[];
  selectedNode: string;
  onSelectNode: (id: string) => void;
}) {
  const latency = useMemo(() => buildRows(history, selectedNode, "node_latency_ms"), [history, selectedNode]);
  const loss = useMemo(() => buildRows(history, selectedNode, "node_packet_loss_percent"), [history, selectedNode]);
  const util = useMemo(() => buildRows(history, selectedNode, "node_utilization_percent"), [history, selectedNode]);
  const cpu = useMemo(() => buildRows(history, selectedNode, "node_cpu_percent"), [history, selectedNode]);

  return (
    <section className="flex flex-col gap-3">
      {/* Single filter row scoping every chart below. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Live metrics</h2>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Node</span>
          <Select value={selectedNode} onValueChange={onSelectNode}>
            <SelectTrigger size="sm" className="w-[190px]">
              <SelectValue placeholder="Select node" />
            </SelectTrigger>
            <SelectContent>
              {nodes.map((n) => (
                <SelectItem key={n.id} value={n.id}>
                  {n.id} · {n.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="hidden sm:inline">· last {history.length} samples</span>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <NodeMetricChart title="Latency (ms)" unit="ms" rows={latency} nodeId={selectedNode} />
        <NodeMetricChart title="Packet loss (%)" unit="%" rows={loss} nodeId={selectedNode} />
        <ThroughputChart history={history} />
        <NodeMetricChart title="Bandwidth utilisation (%)" unit="%" rows={util} nodeId={selectedNode} domain={[0, 120]} />
        <NodeMetricChart title="CPU (%)" unit="%" rows={cpu} nodeId={selectedNode} domain={[0, 100]} />
      </div>
    </section>
  );
}
