"use client";

import { ListOrdered } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { outcomeColor } from "@/components/dashboard/incident-status";
import { formatTime } from "@/lib/status";
import type { Incident } from "@/lib/types";

export function IncidentTimeline({ incident }: { incident: Incident | null }) {
  return (
    <Card size="sm" className="gap-3">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ListOrdered className="size-4 text-muted-foreground" aria-hidden />
          Incident timeline
        </CardTitle>
        {incident && <span className="text-[11px] text-muted-foreground">{incident.timeline.length} events</span>}
      </CardHeader>
      <CardContent>
        {!incident ? (
          <p className="text-xs text-muted-foreground">Events appear here as the pipeline runs.</p>
        ) : (
          <ScrollArea className="h-[300px] pr-3">
            <ol className="relative ml-2 border-l border-border/60 pl-4">
              {incident.timeline.map((event, i) => {
                const color = outcomeColor(event.stage);
                const last = i === incident.timeline.length - 1;
                return (
                  <li key={`${event.tick}-${i}`} className="relative pb-3 last:pb-0">
                    <span
                      className="absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-background"
                      style={{ backgroundColor: color, boxShadow: last ? `0 0 0 3px color-mix(in oklab, ${color} 30%, transparent)` : undefined }}
                    />
                    <p className="text-[11px] text-muted-foreground tabular-nums">
                      {formatTime(event.timestamp)} · tick {event.tick} · <span style={{ color }}>{event.stage.replaceAll("_", " ")}</span>
                    </p>
                    <p className="text-xs leading-snug">{event.message}</p>
                  </li>
                );
              })}
            </ol>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
