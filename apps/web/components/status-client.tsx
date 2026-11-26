"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_URL, fetchHealth, type CheckStatus } from "@/lib/api";

const STATUS_META: Record<CheckStatus, { label: string; className: string; Icon: LucideIcon }> = {
  ok: {
    label: "ok",
    className: "border-success/30 bg-success/10 text-success",
    Icon: CheckCircle2,
  },
  warn: {
    label: "aviso",
    className: "border-warning/40 bg-warning/10 text-warning",
    Icon: TriangleAlert,
  },
  error: {
    label: "error",
    className: "border-destructive/40 bg-destructive/10 text-destructive",
    Icon: AlertCircle,
  },
};

function ApiUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <AlertCircle className="size-4" aria-hidden />
          API no disponible
        </CardTitle>
        <CardDescription>
          No se pudo consultar <code>{API_URL}/api/health</code>. Arranca la API desde la raíz del
          repo:
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
          <code>pnpm dev</code>
        </pre>
        <p className="text-muted-foreground">o solo la API:</p>
        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
          <code>uv run --project apps/api uvicorn winclip.main:app --reload --port 8000</code>
        </pre>
        <div>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="size-3.5" aria-hidden />
            Reintentar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function StatusClient() {
  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  const counts = data
    ? {
        ok: data.checks.filter((check) => check.status === "ok").length,
        warn: data.checks.filter((check) => check.status === "warn").length,
        error: data.checks.filter((check) => check.status === "error").length,
      }
    : null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Estado del sistema</h1>
          <p className="text-sm text-muted-foreground">
            Diagnóstico de las dependencias locales. La API se consulta en{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">{API_URL}</code>.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={isFetching ? "size-3.5 animate-spin" : "size-3.5"} aria-hidden />
          Actualizar
        </Button>
      </header>

      {isPending ? <p className="text-sm text-muted-foreground">Consultando la API…</p> : null}

      {isError ? <ApiUnavailable onRetry={() => refetch()} /> : null}

      {data ? (
        <>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium">
              {data.app} {data.version}
            </span>
            <Badge variant="outline" className="border-success/30 bg-success/10 text-success">
              {counts?.ok} ok
            </Badge>
            <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning">
              {counts?.warn} aviso(s)
            </Badge>
            <Badge
              variant="outline"
              className="border-destructive/40 bg-destructive/10 text-destructive"
            >
              {counts?.error} error(es)
            </Badge>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Comprobaciones</CardTitle>
              <CardDescription>
                Un aviso no impide usar WinClip; un error sí debe corregirse antes del pipeline.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col divide-y">
              {data.checks.map((check) => {
                const meta = STATUS_META[check.status];
                const Icon = meta.Icon;
                return (
                  <div
                    key={check.name}
                    className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:gap-4"
                  >
                    <div className="flex min-w-44 items-center gap-2">
                      <Icon className="size-4" aria-hidden />
                      <span className="font-medium">{check.name}</span>
                    </div>
                    <div className="flex flex-1 flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className={meta.className}>
                          {meta.label}
                        </Badge>
                        <span className="text-sm text-muted-foreground">{check.detail}</span>
                      </div>
                      {check.hint ? (
                        <p className="text-xs text-muted-foreground">
                          <span className="font-medium">Sugerencia:</span> {check.hint}
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
