import { AlertTriangle, CheckCircle2, CircleOff, OctagonAlert } from "lucide-react";
import { cn } from "cn";
import { STATUS_COLOR, STATUS_LABEL } from "@/lib/status";
import type { HealthStatus } from "@/lib/types";

const ICONS = {
  healthy: CheckCircle2,
  warning: AlertTriangle,
  critical: OctagonAlert,
  offline: CircleOff,
} as const;

/** Status is always icon + label + colour, never colour alone. */
export function StatusPill({
  status,
  label,
  className,
  size = "sm",
}: {
  status: HealthStatus;
  label?: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const Icon = ICONS[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 font-medium whitespace-nowrap",
        size === "sm" ? "h-5 text-[11px]" : "h-7 px-3 text-xs",
        className,
      )}
      style={{
        color: STATUS_COLOR[status],
        borderColor: `color-mix(in oklab, ${STATUS_COLOR[status]} 45%, transparent)`,
        backgroundColor: `color-mix(in oklab, ${STATUS_COLOR[status]} 12%, transparent)`,
      }}
    >
      <Icon className={size === "sm" ? "size-3" : "size-3.5"} aria-hidden />
      {label ?? STATUS_LABEL[status]}
    </span>
  );
}
