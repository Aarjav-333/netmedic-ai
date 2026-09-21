"use client";

import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Cloud, Router, Server, ShieldOff, Network } from "lucide-react";
import { cn } from "cn";
import { StatusPill } from "@/components/dashboard/status-pill";
import { NODE_TYPE_LABEL, STATUS_COLOR, formatNumber } from "@/lib/status";
import type { HealthStatus, NodeTelemetry, NodeType } from "@/lib/types";

export type NetworkNodeData = {
  label: string;
  name: string;
  nodeType: NodeType;
  health: HealthStatus;
  isolated: boolean;
  affected: boolean;
  telemetry: NodeTelemetry | null;
};

export type NetworkFlowNode = Node<NetworkNodeData, "network">;

const ICONS: Record<NodeType, typeof Router> = {
  gateway: Cloud,
  router: Router,
  switch: Network,
  server: Server,
};

const HIDDEN_HANDLE = {
  opacity: 0,
  width: 1,
  height: 1,
  minWidth: 1,
  minHeight: 1,
  left: "50%",
  top: "50%",
  transform: "translate(-50%, -50%)",
  border: "none",
  pointerEvents: "none" as const,
};

function NetworkNodeComponent({ data, selected }: NodeProps<NetworkFlowNode>) {
  const Icon = ICONS[data.nodeType];
  const color = STATUS_COLOR[data.health];
  const t = data.telemetry;
  const offline = data.health === "offline";

  return (
    <div
      className={cn(
        "w-[164px] rounded-lg border bg-card/95 px-3 py-2 text-card-foreground shadow-md backdrop-blur transition-all",
        offline && "opacity-60",
        data.affected && "animate-pulse-ring",
        selected && "ring-2 ring-ring",
      )}
      style={{
        borderColor: color,
        boxShadow: data.affected
          ? `0 0 0 4px color-mix(in oklab, ${color} 30%, transparent)`
          : undefined,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={HIDDEN_HANDLE}
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={HIDDEN_HANDLE}
        isConnectable={false}
      />

      <div className="flex items-center gap-2">
        <span
          className="flex size-7 shrink-0 items-center justify-center rounded-md"
          style={{
            backgroundColor: `color-mix(in oklab, ${color} 18%, transparent)`,
            color,
          }}
        >
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-tight">{data.label}</p>
          <p
            className="truncate text-[11px] leading-tight text-muted-foreground"
            title={NODE_TYPE_LABEL[data.nodeType]}
          >
            {data.name}
          </p>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between gap-1">
        <StatusPill status={data.health} />
        {data.isolated && (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">
            <ShieldOff className="size-3" aria-hidden /> Isolated
          </span>
        )}
      </div>

      {t && !offline && (
        <div className="mt-1.5 grid grid-cols-3 gap-1 text-[10px] leading-tight text-muted-foreground tabular-nums">
          <span>
            <span className="block text-foreground">
              {formatNumber(t.latency_ms)} ms
            </span>
            latency
          </span>
          <span>
            <span className="block text-foreground">
              {formatNumber(t.cpu_percent)}%
            </span>
            cpu
          </span>
          <span>
            <span className="block text-foreground">
              {formatNumber(t.packet_loss_percent, 1)}%
            </span>
            loss
          </span>
        </div>
      )}
      {offline && (
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          No telemetry — node unreachable
        </p>
      )}
    </div>
  );
}

export const NetworkNode = memo(NetworkNodeComponent);
