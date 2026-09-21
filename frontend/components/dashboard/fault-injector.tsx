"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, RotateCcw, Syringe, X, Zap } from "lucide-react";
import { DemoControl } from "@/components/dashboard/demo-control";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, clearFault, getFaults, injectFault, resetSimulation } from "@/lib/api";
import { formatTime } from "@/lib/status";
import type { ActiveFault, DemoState, FaultDefinition, FaultType, Severity, Topology } from "@/lib/types";

const SEVERITIES: { value: Severity; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

export function FaultInjector({
  topology,
  activeFaults,
  demo,
  onReset,
  disabled,
}: {
  topology: Topology | null;
  activeFaults: ActiveFault[];
  demo: DemoState | null;
  onReset?: () => void;
  disabled?: boolean;
}) {
  const [catalog, setCatalog] = useState<FaultDefinition[]>([]);
  const [target, setTarget] = useState("R4");
  const [faultType, setFaultType] = useState<FaultType>("router_congestion");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [busy, setBusy] = useState<"inject" | "reset" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFaults()
      .then((res) => setCatalog(res.catalog))
      .catch(() => setCatalog([]));
  }, []);

  const targetNode = topology?.nodes.find((n) => n.id === target) ?? null;
  const targetLink = topology?.links.find((l) => l.id === target) ?? null;

  const applicableFaults = useMemo(() => {
    if (targetLink) return catalog.filter((d) => d.target_kind === "link");
    if (targetNode)
      return catalog.filter(
        (d) => d.target_kind === "node" && (d.node_types.length === 0 || d.node_types.includes(targetNode.type)),
      );
    return catalog;
  }, [catalog, targetNode, targetLink]);

  // Keep the fault type valid for the chosen target.
  const effectiveFaultType: FaultType =
    applicableFaults.some((d) => d.type === faultType) ? faultType : (applicableFaults[0]?.type ?? faultType);
  const definition = applicableFaults.find((d) => d.type === effectiveFaultType);

  const handleInject = async () => {
    setBusy("inject");
    setError(null);
    try {
      await injectFault({ fault_type: effectiveFaultType, target_id: target, severity });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend");
    } finally {
      setBusy(null);
    }
  };

  const handleReset = async () => {
    setBusy("reset");
    setError(null);
    try {
      await resetSimulation();
      onReset?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend");
    } finally {
      setBusy(null);
    }
  };

  const handleClear = async (id: string) => {
    setError(null);
    try {
      await clearFault(id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend");
    }
  };

  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Syringe className="size-4 text-muted-foreground" aria-hidden />
          Fault injector
        </CardTitle>
        <span className="text-[11px] text-muted-foreground">{activeFaults.length} active</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <DemoControl demo={demo} disabled={disabled} />
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Target
          <Select value={target} onValueChange={setTarget} disabled={!topology || disabled}>
            <SelectTrigger size="sm" className="w-full">
              <SelectValue placeholder="Select target" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Nodes</SelectLabel>
                {topology?.nodes.map((n) => (
                  <SelectItem key={n.id} value={n.id}>
                    {n.id} · {n.name}
                  </SelectItem>
                ))}
              </SelectGroup>
              <SelectGroup>
                <SelectLabel>Links</SelectLabel>
                {topology?.links.map((l) => (
                  <SelectItem key={l.id} value={l.id}>
                    {l.id} · {l.source} ↔ {l.target}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Fault type
          <Select
            value={effectiveFaultType}
            onValueChange={(v) => setFaultType(v as FaultType)}
            disabled={applicableFaults.length === 0 || disabled}
          >
            <SelectTrigger size="sm" className="w-full">
              <SelectValue placeholder="Select fault" />
            </SelectTrigger>
            <SelectContent>
              {applicableFaults.map((d) => (
                <SelectItem key={d.type} value={d.type}>
                  {d.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {definition && <span className="text-[11px] leading-snug">{definition.description}</span>}
        </label>

        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Severity
          <Select value={severity} onValueChange={(v) => setSeverity(v as Severity)} disabled={disabled}>
            <SelectTrigger size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SEVERITIES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <div className="flex gap-2">
          <Button
            className="flex-1"
            onClick={handleInject}
            disabled={!topology || !definition || busy !== null || disabled}
          >
            {busy === "inject" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Zap className="size-4" aria-hidden />}
            Inject fault
          </Button>
          <Button variant="outline" onClick={handleReset} disabled={busy !== null || disabled}>
            {busy === "reset" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RotateCcw className="size-4" aria-hidden />}
            Reset
          </Button>
        </div>

        {error && <p className="text-xs text-status-critical">{error}</p>}

        {activeFaults.length > 0 && (
          <ul className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
            {activeFaults.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1.5 text-xs">
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    {f.label} <span className="text-muted-foreground">on</span> {f.target_id}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {f.severity} · injected {formatTime(f.injected_at)}
                    {f.expires_at ? ` · expires ${formatTime(f.expires_at)}` : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Clear ${f.label} on ${f.target_id}`}
                  onClick={() => handleClear(f.id)}
                  disabled={disabled}
                >
                  <X className="size-3.5" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
