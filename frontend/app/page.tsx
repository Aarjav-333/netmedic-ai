"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHealth, type HealthResponse } from "@/lib/api";

type BackendState =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "error"; message: string };

export default function Home() {
  const [backend, setBackend] = useState<BackendState>({ kind: "loading" });

  useEffect(() => {
    getHealth()
      .then((health) => setBackend({ kind: "ok", health }))
      .catch((err: Error) => setBackend({ kind: "error", message: err.message }));
  }, []);

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <div className="text-center">
        <h1 className="text-4xl font-semibold tracking-tight">NetMedic AI</h1>
        <p className="mt-2 text-muted-foreground">
          Autonomous Network Detection, Diagnosis &amp; Self-Healing Platform
        </p>
      </div>

      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Backend connection
            {backend.kind === "ok" && <Badge>connected</Badge>}
            {backend.kind === "error" && <Badge variant="destructive">offline</Badge>}
            {backend.kind === "loading" && <Badge variant="secondary">checking…</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {backend.kind === "ok" && (
            <p>
              {backend.health.service} v{backend.health.version} — {backend.health.status}
            </p>
          )}
          {backend.kind === "error" && <p>{backend.message}</p>}
          {backend.kind === "loading" && <p>Contacting API…</p>}
        </CardContent>
      </Card>
    </main>
  );
}
