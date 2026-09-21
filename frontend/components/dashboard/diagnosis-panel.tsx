"use client";

import { Brain, Loader2, Sparkles, Stethoscope } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { STATUS_COLOR } from "@/lib/status";
import type { Incident, RiskLevel } from "@/lib/types";

const RISK_COLOR: Record<RiskLevel, string> = {
  low: STATUS_COLOR.healthy,
  medium: STATUS_COLOR.warning,
  high: STATUS_COLOR.critical,
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

export function DiagnosisPanel({ incident }: { incident: Incident | null }) {
  const diagnosis = incident?.diagnosis ?? null;
  const ai = incident?.ai_explanation ?? null;
  const analysing = incident !== null && diagnosis === null && (incident.status === "detected" || incident.status === "analyzing");

  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Stethoscope className="size-4 text-muted-foreground" aria-hidden />
          AI diagnosis
        </CardTitle>
        {ai && (
          <Badge variant="outline" className="gap-1">
            <Sparkles className="size-3" aria-hidden />
            {ai.provider === "qualcomm" ? `Qualcomm · ${ai.model ?? "cloud"}` : "Mock provider"}
            {ai.fallback && " · fallback"}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {!incident && <p className="text-xs text-muted-foreground">No incidents detected. Diagnosis appears here as soon as an anomaly is confirmed.</p>}

        {analysing && (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            Scoring root-cause hypotheses for {incident.component_id}…
          </p>
        )}

        {diagnosis && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Section title="Affected component">
                <p className="text-base font-semibold">{diagnosis.target_id}</p>
                <p className="text-[11px] text-muted-foreground">
                  {diagnosis.target_kind} · anomaly severity {Math.round(diagnosis.anomaly_severity)}/100
                </p>
              </Section>
              <Section title="Probable root cause">
                <p className="text-base font-semibold">{diagnosis.root_cause_label}</p>
                <p className="text-[11px] text-muted-foreground">
                  {diagnosis.affected_flows.length ? `impacts ${diagnosis.affected_flows.join(", ")}` : "no flows impacted yet"}
                </p>
              </Section>
            </div>

            <Section title="Confidence (rule-match score)">
              <div className="flex items-center gap-3">
                <Progress value={diagnosis.confidence * 100} className="h-2 flex-1" />
                <span className="text-sm font-semibold tabular-nums">{Math.round(diagnosis.confidence * 100)}%</span>
              </div>
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground" title={diagnosis.confidence_explanation}>
                {diagnosis.confidence_explanation}
              </p>
            </Section>

            <Section title="Evidence">
              <ul className="space-y-1 text-xs">
                {diagnosis.evidence.map((line) => (
                  <li key={line} className="flex gap-2">
                    <span className="text-muted-foreground">•</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </Section>

            <Section title="Recommended remediation">
              <p className="text-sm font-medium">{diagnosis.plan.summary}</p>
              <p className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                <span
                  className="inline-flex items-center gap-1 rounded-full border px-1.5 font-medium"
                  style={{ color: RISK_COLOR[diagnosis.plan.risk], borderColor: `color-mix(in oklab, ${RISK_COLOR[diagnosis.plan.risk]} 45%, transparent)` }}
                >
                  risk {diagnosis.plan.risk}
                </span>
                <span>{diagnosis.plan.action.replaceAll("_", " ")}</span>
              </p>
            </Section>

            {ai ? (
              <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
                <p className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <Brain className="size-3.5" aria-hidden /> AI explanation
                </p>
                <p className="font-medium">{ai.diagnosis}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{ai.explanation}</p>
                <dl className="mt-2 grid gap-1.5 text-xs">
                  <div>
                    <dt className="font-medium">Why this remediation</dt>
                    <dd className="text-muted-foreground">{ai.remediation_justification}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">Operational risk</dt>
                    <dd className="text-muted-foreground">{ai.operational_risk}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">Expected result</dt>
                    <dd className="text-muted-foreground">{ai.recovery_expectation}</dd>
                  </div>
                </dl>
                {ai.error && <p className="mt-2 text-[11px] text-status-warning">Provider error: {ai.error}</p>}
              </div>
            ) : (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
                Generating explanation…
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
