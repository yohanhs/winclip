"use client";

import {
  AlertCircle,
  CircleCheck,
  RefreshCw,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/hooks/use-api-client";
import { API_URL, errorMessage, type HealthCheck } from "@/lib/api";

const STATUS_META: Record<
  HealthCheck["status"],
  { label: string; className: string; Icon: LucideIcon }
> = {
  ok: {
    label: "ok",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    Icon: CircleCheck,
  },
  warn: {
    label: "aviso",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-400",
    Icon: TriangleAlert,
  },
  error: {
    label: "error",
    className: "border-rose-500/40 bg-rose-500/10 text-rose-400",
    Icon: AlertCircle,
  },
};

export function StatusClient() {
  const health = useHealth();
  const checks = health.data?.checks ?? [];
  const counts = checks.reduce(
    (acc, check) => {
      acc[check.status] += 1;
      return acc;
    },
    { ok: 0, warn: 0, error: 0 },
  );

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
            Estado del sistema
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Comprobaciones reales de <code className="text-zinc-400">GET /api/health</code>{" "}
            sobre binarios, modelos y almacenamiento local.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void health.refetch()}
          disabled={health.isFetching}
        >
          <RefreshCw
            className={health.isFetching ? "animate-spin" : undefined}
            aria-hidden="true"
          />
          Volver a comprobar
        </Button>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-[#111114] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">OK</p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-emerald-400">
            {counts.ok}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-[#111114] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            Avisos
          </p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-amber-400">
            {counts.warn}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-[#111114] px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            Errores
          </p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-rose-400">
            {counts.error}
          </p>
        </div>
      </div>

      {health.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : health.isError ? (
        <Card className="border-rose-500/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-rose-400">
              <AlertCircle className="size-4" aria-hidden="true" />
              La API no responde
            </CardTitle>
            <CardDescription>
              {errorMessage(health.error)}. Arranca el backend con{" "}
              <code>pnpm dev</code> y vuelve a comprobar.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-xs text-zinc-500">
            URL configurada:{" "}
            <span className="font-mono text-zinc-400">{API_URL}</span>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {checks.map((check) => {
            const meta = STATUS_META[check.status];
            const Icon = meta.Icon;
            return (
              <div
                key={check.name}
                className="flex flex-col gap-2 rounded-xl border border-white/10 bg-[#111114] px-4 py-3 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <Icon
                    className="mt-0.5 size-4 shrink-0 text-zinc-400"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium capitalize text-zinc-100">
                      {check.name}
                    </p>
                    <p className="text-xs text-zinc-400">{check.detail}</p>
                    {check.hint ? (
                      <p className="mt-0.5 text-xs text-zinc-500">{check.hint}</p>
                    ) : null}
                  </div>
                </div>
                <Badge variant="outline" className={meta.className}>
                  {meta.label}
                </Badge>
              </div>
            );
          })}
        </div>
      )}

      {health.data ? (
        <p className="text-center text-[11px] text-zinc-600">
          {health.data.app} v{health.data.version} · {API_URL}
        </p>
      ) : null}
    </div>
  );
}
