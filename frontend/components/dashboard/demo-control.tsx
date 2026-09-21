"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, getDemoScenarios, runDemo, stopDemo, type DemoScenario } from "@/lib/api";
import type { DemoState } from "@/lib/types";

export function DemoControl({ demo, disabled }: { demo: DemoState | null; disabled?: boolean }) {
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [scenario, setScenario] = useState("congestion");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = demo?.running ?? false;

  useEffect(() => {
    getDemoScenarios()
      .then(setScenarios)
      .catch(() => setScenarios([]));
  }, []);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await runDemo(scenario);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await stopDemo();
    } catch {
      /* state message will reflect the outcome */
    } finally {
      setBusy(false);
    }
  };

  const selected = scenarios.find((s) => s.key === scenario);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-muted/20 p-3">
      <div className="flex items-center gap-2">
        <Select value={scenario} onValueChange={setScenario} disabled={running || disabled || scenarios.length === 0}>
          <SelectTrigger size="sm" className="flex-1">
            <SelectValue placeholder="Scenario" />
          </SelectTrigger>
          <SelectContent>
            {scenarios.map((s) => (
              <SelectItem key={s.key} value={s.key}>
                {s.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {running ? (
          <Button variant="outline" size="sm" onClick={stop} disabled={busy}>
            <Square className="size-3.5" aria-hidden /> Stop
          </Button>
        ) : (
          <Button size="sm" onClick={start} disabled={busy || disabled}>
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Play className="size-4" aria-hidden />}
            Run demo
          </Button>
        )}
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        {running && demo
          ? `Step ${demo.step}/${demo.total_steps} · ${demo.message}`
          : demo?.outcome
            ? demo.message
            : (selected?.description ?? "Scripted scenario that drives the real detect → diagnose → heal → verify pipeline.")}
      </p>
      {error && <p className="text-[11px] text-status-critical">{error}</p>}
    </div>
  );
}
