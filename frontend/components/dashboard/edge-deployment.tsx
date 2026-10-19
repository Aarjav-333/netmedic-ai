"use client";

import { useCallback } from "react";
import { Cpu, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBackendResource } from "@/hooks/use-backend-resource";
import { getEdgeProfile } from "@/lib/api";
import { formatNumber } from "@/lib/status";
import type { EdgeProfile } from "@/lib/types";

/**
 * The on-device variant of the detector, compiled and profiled on real Qualcomm
 * hardware via AI Hub. Every figure here comes from a recorded job - nothing is
 * measured or estimated in the browser.
 */
export function EdgeDeployment({ ready }: { ready: boolean }) {
  // The hook expects a list; wrap the single profile so one retry policy covers both.
  const load = useCallback(
    () => getEdgeProfile().then((p) => (p ? [p] : [])),
    [],
  );
  const { items } = useBackendResource<EdgeProfile>(load, ready);
  const profile = items[0] ?? null;
  const d = profile?.deployment ?? null;

  if (!profile) return null;

  const npuLayers = d ? (d.layers_by_compute_unit.NPU ?? 0) : 0;
  const totalLayers = d ? Object.values(d.layers_by_compute_unit).reduce((a, b) => a + b, 0) : 0;

  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Cpu className="size-4 text-muted-foreground" aria-hidden />
          Edge deployment
        </CardTitle>
        <span className="text-[11px] text-muted-foreground">Qualcomm AI Hub</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {d ? (
          <>
            <div>
              <p className="font-medium">{d.device}</p>
              <p className="text-[11px] text-muted-foreground">
                {profile.model.architecture} · {formatNumber(profile.model.parameters)} params · {d.runtime}
              </p>
            </div>

            <dl className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md border border-border/60 py-1.5">
                <dt className="text-[11px] text-muted-foreground">Inference</dt>
                <dd className="text-base font-semibold tabular-nums" style={{ color: "var(--status-good)" }}>
                  {d.inference_time_us === null ? "—" : `${formatNumber(d.inference_time_us)} µs`}
                </dd>
              </div>
              <div className="rounded-md border border-border/60 py-1.5">
                <dt className="text-[11px] text-muted-foreground">On NPU</dt>
                <dd className="text-base font-semibold tabular-nums">
                  {npuLayers}/{totalLayers}
                </dd>
              </div>
              <div className="rounded-md border border-border/60 py-1.5">
                <dt className="text-[11px] text-muted-foreground">Cold start</dt>
                <dd className="text-base font-semibold tabular-nums">
                  {d.first_load_time_us === null ? "—" : `${formatNumber(d.first_load_time_us / 1000)} ms`}
                </dd>
              </div>
            </dl>

            <p className="text-[11px] leading-snug text-muted-foreground">
              Detects every injected fault with a{" "}
              {formatNumber(profile.validation.healthy_false_positive_rate * 100, 1)}% false-positive rate on{" "}
              {formatNumber(profile.validation.healthy_samples)} healthy samples, and agrees with the Isolation
              Forest on every case.
            </p>

            <div className="flex gap-3 text-[11px]">
              <a
                className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                href={d.compile_job_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                Compile job <ExternalLink className="size-3" aria-hidden />
              </a>
              <a
                className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                href={d.profile_job_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                Profile job <ExternalLink className="size-3" aria-hidden />
              </a>
            </div>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            Trained and validated locally; not yet deployed. Run{" "}
            <code className="rounded bg-muted px-1">scripts/edge_detector.py</code> to compile and profile it on a
            Qualcomm device.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
