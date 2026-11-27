"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Ban,
  Camera,
  CheckCircle2,
  Clock,
  ExternalLink,
  Inbox,
  Loader2,
  RefreshCw,
  Search,
  Send,
  X,
} from "lucide-react";
import { toast } from "sonner";
import type {
  AccountPlatform,
  PublicationOut,
  PublicationStatus,
} from "@winclip/api-client";

import { PlatformIcon, platformTitle } from "@/components/accounts/platform-icon";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAccounts } from "@/hooks/use-accounts";
import { useProjectEvents } from "@/hooks/use-project-events";
import { useProjects } from "@/hooks/use-projects";
import {
  useCancelPublication,
  usePublications,
  usePublicationsQuota,
  useRetryPublication,
} from "@/hooks/use-publications";
import { errorMessage, mediaUrl } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type FilterStatus = "all" | PublicationStatus;

function errorResolutionHint(code: string | null | undefined): string {
  switch (code) {
    case "challenge_required":
      return "Abre la cuenta en un navegador normal para completar la verificación manual y reintenta o cambia a la API oficial.";
    case "session_expired":
      return "Ve a /accounts y reconecta la cuenta antes de reintentar.";
    case "quota_exceeded":
      return "YouTube Data API v3 alcanzó el límite diario de 10 000 unidades (~6 subidas/día). Espera al reinicio diario de cuota.";
    case "daily_limit_exceeded":
      return "La cuenta alcanzó su límite diario configurado en WinClip.";
    case "missed_schedule_window":
      return "WinClip estuvo apagado durante la ventana programada. Pulsa Reintentar para publicar ahora.";
    default:
      return "Revisa el mensaje y la captura diagnóstica antes de lanzar un reintento.";
  }
}

export function PublicationsWorkspace() {
  const [statusFilter, setStatusFilter] = useState<FilterStatus>("all");
  const [platformFilter, setPlatformFilter] = useState<"all" | AccountPlatform>("all");
  const [accountFilter, setAccountFilter] = useState<string>("all");
  const [projectFilter, setProjectFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [inspecting, setInspecting] = useState<PublicationOut | null>(null);

  const publicationsQuery = usePublications();
  const quotaQuery = usePublicationsQuota();
  const accountsQuery = useAccounts();
  const projectsQuery = useProjects();
  const retryMutation = useRetryPublication();
  const cancelMutation = useCancelPublication();

  const { connected } = useProjectEvents(null, { silent: true });

  const publications = useMemo(
    () => publicationsQuery.data ?? [],
    [publicationsQuery.data],
  );
  const accounts = useMemo(() => accountsQuery.data ?? [], [accountsQuery.data]);
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);

  const counts = useMemo(
    () => ({
      all: publications.length,
      scheduled: publications.filter((p) => p.status === "scheduled").length,
      publishing: publications.filter((p) => p.status === "publishing").length,
      published: publications.filter((p) => p.status === "published").length,
      failed: publications.filter((p) => p.status === "failed").length,
      cancelled: publications.filter((p) => p.status === "cancelled").length,
    }),
    [publications],
  );

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return publications.filter((pub) => {
      if (statusFilter !== "all" && pub.status !== statusFilter) return false;
      if (platformFilter !== "all" && pub.account_platform !== platformFilter) return false;
      if (accountFilter !== "all" && pub.account_id !== accountFilter) return false;
      if (projectFilter !== "all" && pub.project_id !== projectFilter) return false;
      if (!q) return true;
      return (
        pub.clip_title.toLowerCase().includes(q) ||
        (pub.account_alias ?? "").toLowerCase().includes(q) ||
        pub.account_display_name.toLowerCase().includes(q) ||
        pub.account_handle.toLowerCase().includes(q) ||
        (pub.project_title ?? "").toLowerCase().includes(q)
      );
    });
  }, [
    publications,
    statusFilter,
    platformFilter,
    accountFilter,
    projectFilter,
    searchQuery,
  ]);

  const filterTabs: { id: FilterStatus; label: string; count: number }[] = [
    { id: "all", label: "Todas", count: counts.all },
    { id: "scheduled", label: "Programadas", count: counts.scheduled },
    { id: "publishing", label: "Publicando", count: counts.publishing },
    { id: "published", label: "Publicadas", count: counts.published },
    { id: "failed", label: "Con error", count: counts.failed },
    { id: "cancelled", label: "Canceladas", count: counts.cancelled },
  ];

  const handleRetry = (pub: PublicationOut) => {
    retryMutation.mutate(pub.id, {
      onSuccess: () => {
        toast.success("Publicación reencolada", {
          description: pub.clip_title || pub.id,
        });
      },
      onError: (err) => {
        toast.error("No se pudo reintentar la publicación", {
          description: errorMessage(err),
        });
      },
    });
  };

  const handleCancel = (pub: PublicationOut) => {
    cancelMutation.mutate(
      { publicationId: pub.id, body: { delete_remote: false } },
      {
        onSuccess: () => {
          toast.success("Publicación cancelada", {
            description: pub.clip_title || pub.id,
          });
        },
        onError: (err) => {
          toast.error("No se pudo cancelar la publicación", {
            description: errorMessage(err),
          });
        },
      },
    );
  };

  const quota = quotaQuery.data;

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
              Publicaciones
            </h1>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-xs",
                connected ? "text-emerald-400" : "text-zinc-500",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  connected ? "bg-emerald-400" : "bg-zinc-600",
                )}
                aria-hidden="true"
              />
              {connected ? "En vivo" : "Sin conexión"}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-zinc-400">
            Historial multi-cuenta, programación diferida, diagnósticos Playwright y cuotas diarias.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {quota ? (
            <div className="rounded-md border border-white/[0.08] bg-[#111114] px-3 py-1.5 text-xs text-zinc-300">
              YouTube hoy:{" "}
              <span className="font-mono tabular-nums text-amber-300">
                {quota.youtube_units_used.toLocaleString()} /{" "}
                {quota.youtube_units_limit.toLocaleString()}
              </span>{" "}
              uds
            </div>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              void publicationsQuery.refetch();
              void quotaQuery.refetch();
            }}
            disabled={publicationsQuery.isFetching}
          >
            <RefreshCw
              className={publicationsQuery.isFetching ? "animate-spin" : undefined}
              aria-hidden="true"
            />
            Actualizar
          </Button>
        </div>
      </div>

      {/* Status tabs & Secondary filters */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            role="tablist"
            aria-label="Filtrar por estado"
            className="inline-flex flex-wrap items-center rounded-md border border-white/[0.08] bg-[#111114] p-0.5"
          >
            {filterTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={statusFilter === tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={cn(
                  "inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[5px] px-3 py-1.5 text-xs font-medium transition-colors",
                  statusFilter === tab.id
                    ? "bg-white/[0.1] text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-200",
                )}
              >
                <span>{tab.label}</span>
                <span
                  className={cn(
                    "font-mono text-[11px] tabular-nums",
                    tab.id === "failed" && tab.count > 0 ? "text-rose-400" : "text-zinc-500",
                  )}
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          <span className="font-mono text-xs tabular-nums text-zinc-500">
            Mostrando {filtered.length} de {publications.length} envíos
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative min-w-[200px] flex-1 max-w-xs">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-500"
              aria-hidden="true"
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar clip, cuenta o proyecto…"
              aria-label="Buscar publicaciones"
              className="h-9 w-full rounded-md border border-white/[0.08] bg-[#111114] pl-8 pr-3 text-xs text-zinc-100 placeholder:text-zinc-500 focus:border-amber-400/60 focus:outline-none"
            />
          </div>

          <select
            aria-label="Filtrar por plataforma"
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value as "all" | AccountPlatform)}
            className="h-9 rounded-md border border-white/[0.08] bg-[#111114] px-3 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
          >
            <option value="all">Todas las plataformas</option>
            <option value="youtube">YouTube</option>
            <option value="tiktok">TikTok</option>
            <option value="instagram">Instagram</option>
          </select>

          <select
            aria-label="Filtrar por cuenta"
            value={accountFilter}
            onChange={(e) => setAccountFilter(e.target.value)}
            className="h-9 rounded-md border border-white/[0.08] bg-[#111114] px-3 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
          >
            <option value="all">Todas las cuentas</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.alias || acc.display_name} ({platformTitle(acc.platform)})
              </option>
            ))}
          </select>

          <select
            aria-label="Filtrar por proyecto"
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            className="h-9 rounded-md border border-white/[0.08] bg-[#111114] px-3 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
          >
            <option value="all">Todos los proyectos</option>
            {projects.map((proj) => (
              <option key={proj.id} value={proj.id}>
                {proj.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#111114]">
        {publicationsQuery.isLoading ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="space-y-1.5 px-6 py-16 text-center">
            <p className="text-sm font-medium text-zinc-200">
              No hay publicaciones en esta categoría
            </p>
            <p className="text-xs text-zinc-500">
              Selecciona uno o más clips renderizados en un proyecto para publicarlos o
              programarlos.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/[0.08] bg-[#0D0D10] text-[11px] font-medium text-zinc-400">
                  <th className="px-4 py-3 font-medium">Clip</th>
                  <th className="px-4 py-3 font-medium">Cuenta destino</th>
                  <th className="px-4 py-3 font-medium">Modo</th>
                  <th className="px-4 py-3 font-medium">Programado / Publicado</th>
                  <th className="px-4 py-3 font-medium">Estado</th>
                  <th className="px-4 py-3 text-right font-medium">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06] text-[13px]">
                {filtered.map((pub) => {
                  const thumb = mediaUrl(pub.clip_thumb_url);
                  const dateLabel = pub.published_at
                    ? formatDate(pub.published_at)
                    : pub.scheduled_at
                      ? formatDate(pub.scheduled_at)
                      : formatDate(pub.created_at);
                  return (
                    <tr
                      key={pub.id}
                      data-testid={`publication-row-${pub.id}`}
                      className="transition-colors hover:bg-white/[0.025]"
                    >
                      {/* Clip */}
                      <td className="max-w-[320px] px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="relative aspect-[9/16] w-9 shrink-0 overflow-hidden rounded border border-white/[0.08] bg-zinc-900">
                            {thumb ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={thumb}
                                alt=""
                                className="h-full w-full object-cover"
                              />
                            ) : null}
                          </div>
                          <div className="min-w-0">
                            <p className="truncate font-medium text-zinc-100">
                              {pub.clip_title || pub.clip_id}
                            </p>
                            {pub.project_title ? (
                              <p className="truncate text-[11px] text-zinc-500">
                                {pub.project_title}
                              </p>
                            ) : null}
                          </div>
                        </div>
                      </td>

                      {/* Account */}
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="flex items-center gap-2">
                          <PlatformIcon
                            platform={pub.account_platform}
                            className="size-4 shrink-0"
                          />
                          <div>
                            <div className="flex items-center gap-1.5">
                              <p className="text-[13px] font-medium leading-tight text-zinc-200">
                                {pub.account_alias || pub.account_display_name}
                              </p>
                              <span
                                className={cn(
                                  "rounded px-1 py-0.5 font-mono text-[10px]",
                                  pub.account_auth_method === "playwright"
                                    ? "bg-violet-500/15 text-violet-300"
                                    : "bg-sky-500/15 text-sky-300",
                                )}
                              >
                                {pub.account_auth_method === "playwright" ? "Playwright" : "API"}
                              </span>
                            </div>
                            <p className="font-mono text-[11px] text-zinc-500">
                              {pub.account_handle}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Delivery Mode */}
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-300">
                          {pub.delivery_mode === "direct" ? (
                            <Send className="size-3.5 text-zinc-500" aria-hidden="true" />
                          ) : (
                            <Inbox className="size-3.5 text-violet-400" aria-hidden="true" />
                          )}
                          <span>
                            {pub.delivery_mode === "direct" ? "Directo" : "Borrador Inbox"}
                          </span>
                        </span>
                      </td>

                      {/* Time */}
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs tabular-nums text-zinc-300">
                        {dateLabel}
                      </td>

                      {/* Status */}
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <PublicationStatusBadge
                            status={pub.status}
                            progress={pub.job_progress}
                          />
                          {(pub.warnings ?? []).length > 0 ? (
                            <span
                              title={(pub.warnings ?? []).join(" · ")}
                              className="max-w-[200px] truncate text-[10px] text-amber-300/90"
                            >
                              {(pub.warnings ?? [])[0]}
                            </span>
                          ) : null}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {pub.status === "failed" ? (
                          <div className="inline-flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => setInspecting(pub)}
                              className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-rose-500/30 bg-rose-500/12 px-2.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-500/20"
                            >
                              <Camera className="size-3.5" aria-hidden="true" />
                              <span>Ver captura</span>
                            </button>
                            <button
                              type="button"
                              disabled={retryMutation.isPending}
                              onClick={() => handleRetry(pub)}
                              className="inline-flex h-8 cursor-pointer items-center gap-1 rounded-md border border-white/[0.1] bg-[#18181B] px-2.5 text-xs font-medium text-zinc-100 transition-colors hover:bg-zinc-800 disabled:opacity-50"
                            >
                              <RefreshCw
                                className="size-3.5 text-amber-400"
                                aria-hidden="true"
                              />
                              <span>Reintentar</span>
                            </button>
                          </div>
                        ) : pub.status === "scheduled" ? (
                          <button
                            type="button"
                            disabled={cancelMutation.isPending}
                            onClick={() => handleCancel(pub)}
                            className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-white/[0.1] bg-[#18181B] px-2.5 text-xs font-medium text-zinc-200 transition-colors hover:border-rose-500/40 hover:text-rose-300 disabled:opacity-50"
                          >
                            <Ban className="size-3.5" aria-hidden="true" />
                            <span>Cancelar</span>
                          </button>
                        ) : pub.status === "published" && pub.external_url ? (
                          <a
                            href={pub.external_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-zinc-300 transition-colors hover:bg-white/[0.06] hover:text-amber-300"
                          >
                            <span>Ver enlace</span>
                            <ExternalLink className="size-3.5" aria-hidden="true" />
                          </a>
                        ) : pub.status === "publishing" ? (
                          <span className="font-mono text-xs tabular-nums text-cyan-300">
                            {Math.round(pub.job_progress)}%
                          </span>
                        ) : (
                          <span className="text-xs text-zinc-500">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Ver captura / Diagnóstico de error */}
      {inspecting ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          onClick={() => setInspecting(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Diagnóstico y captura de error"
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xl overflow-hidden rounded-xl border border-white/[0.12] bg-[#111114] shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-white/[0.08] px-5 py-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="size-4 text-rose-400" aria-hidden="true" />
                <h3 className="text-[15px] font-semibold text-zinc-100">
                  Captura de error · {inspecting.account_alias || inspecting.account_display_name}
                </h3>
              </div>
              <button
                type="button"
                aria-label="Cerrar captura"
                onClick={() => setInspecting(null)}
                className="rounded-md p-1.5 text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-100"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-4 p-5">
              {inspecting.has_screenshot && inspecting.screenshot_url ? (
                <div className="overflow-hidden rounded-lg border border-white/[0.1] bg-[#09090B]">
                  <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-2 font-mono text-[11px] text-zinc-500">
                    <span>screenshot_{inspecting.id}.png</span>
                    <span>{inspecting.error_code ?? "error"}</span>
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={mediaUrl(inspecting.screenshot_url) ?? ""}
                    alt={`Captura de error para ${inspecting.clip_title}`}
                    className="max-h-[340px] w-full bg-black object-contain"
                  />
                </div>
              ) : null}

              <div className="space-y-1 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs">
                <p className="font-mono text-rose-300">
                  {inspecting.error_code || "publish_error"}
                </p>
                <p className="text-zinc-100">
                  {inspecting.error || "La publicación falló sin detalle adicional."}
                </p>
              </div>

              <div className="rounded-lg border border-amber-400/25 bg-amber-400/[0.06] p-3 text-xs text-amber-200">
                <strong className="font-semibold">Solución recomendada:</strong>{" "}
                {errorResolutionHint(inspecting.error_code)}
              </div>

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setInspecting(null)}
                  className="h-9 cursor-pointer rounded-md px-3.5 text-[13px] text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
                >
                  Cerrar
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleRetry(inspecting);
                    setInspecting(null);
                  }}
                  className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md bg-amber-400 px-4 text-[13px] font-semibold text-zinc-950 hover:bg-amber-300"
                >
                  <RefreshCw className="size-3.5" aria-hidden="true" />
                  <span>Reintentar envío</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PublicationStatusBadge({
  status,
  progress,
}: {
  status: PublicationStatus;
  progress: number;
}) {
  if (status === "scheduled") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/[0.1] bg-zinc-800 px-2.5 py-0.5 text-[11px] font-medium text-zinc-200">
        <Clock className="size-3 text-amber-400" aria-hidden="true" />
        <span>Programada</span>
      </span>
    );
  }
  if (status === "publishing") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-cyan-400/30 bg-cyan-500/12 px-2.5 py-0.5 text-[11px] font-medium text-cyan-300">
        <Loader2 className="size-3 animate-spin" aria-hidden="true" />
        <span>Publicando {progress > 0 ? `${Math.round(progress)}%` : ""}</span>
      </span>
    );
  }
  if (status === "published") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-500/12 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">
        <CheckCircle2 className="size-3" aria-hidden="true" />
        <span>Publicada</span>
      </span>
    );
  }
  if (status === "cancelled") {
    return (
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/[0.1] bg-zinc-900 px-2.5 py-0.5 text-[11px] font-medium text-zinc-400">
        <Ban className="size-3" aria-hidden="true" />
        <span>Cancelada</span>
      </span>
    );
  }
  return (
    <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-rose-400/30 bg-rose-500/12 px-2.5 py-0.5 text-[11px] font-medium text-rose-300">
      <AlertTriangle className="size-3" aria-hidden="true" />
      <span>Con error</span>
    </span>
  );
}
