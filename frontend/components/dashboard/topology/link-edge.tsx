"use client";

import { memo } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { STATUS_COLOR } from "@/lib/status";
import type { HealthStatus } from "@/lib/types";

export type LinkEdgeData = {
  health: HealthStatus;
  utilization: number;
  active: boolean; // carries at least one flow
  rerouted: boolean; // carries a flow that is on a non-primary path
  isolated: boolean;
  down: boolean;
};

export type LinkFlowEdge = Edge<LinkEdgeData, "link">;

function LinkEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<LinkFlowEdge>) {
  const [path, labelX, labelY] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });
  const health = data?.health ?? "healthy";
  const down = data?.down ?? false;
  const active = data?.active ?? false;
  const rerouted = data?.rerouted ?? false;
  const utilization = data?.utilization ?? 0;

  // Recessive hairline when healthy; status colour only when the link itself is unhealthy.
  const baseColor =
    health === "healthy" ? "var(--chart-axis)" : STATUS_COLOR[health];
  const flowColor = rerouted ? "var(--series-3)" : "var(--series-1)";

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: baseColor,
          strokeWidth: health === "healthy" ? 1.5 : 2.5,
          strokeDasharray: down ? "6 4" : undefined,
          opacity: data?.isolated && !active ? 0.5 : 1,
        }}
      />
      {active && !down && (
        <path
          d={path}
          fill="none"
          stroke={flowColor}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeDasharray="8 8"
          className="netmedic-flow-edge"
          style={{ pointerEvents: "none" }}
        />
      )}
      {(active || down || health !== "healthy") && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none rounded-full border border-border/60 bg-background/90 px-1.5 text-[10px] leading-4 text-muted-foreground tabular-nums"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              borderColor: down
                ? STATUS_COLOR.critical
                : rerouted
                  ? "var(--series-3)"
                  : undefined,
            }}
          >
            {down ? "DOWN" : `${Math.round(utilization)}%`}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const LinkEdge = memo(LinkEdgeComponent);
