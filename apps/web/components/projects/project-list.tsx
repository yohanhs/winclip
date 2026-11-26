"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  FolderOpen,
  LayoutGrid,
  List,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/hooks/use-projects";
import { useProjectEvents } from "@/hooks/use-project-events";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ProjectCard } from "./project-card";

type StatusFilter = "all" | "processing" | "ready" | "failed";
type LanguageFilter = "all" | "es" | "en";

const STATUS_FILTERS: Array<{ id: StatusFilter; label: string }> = [
  { id: "all", label: "Todos" },
  { id: "processing", label: "Procesando" },
  { id: "ready", label: "Listos" },
  { id: "failed", label: "Con error" },
];

export function ProjectList() {
  const projectsQuery = useProjects();
  const { connected } = useProjectEvents(null);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [languageFilter, setLanguageFilter] = useState<LanguageFilter>("all");
  const [search, setSearch] = useState("");

  const projects = useMemo(
    () => projectsQuery.data ?? [],
    [projectsQuery.data],
  );

  const stats = useMemo(() => {
    const active = projects.filter(
      (project) => project.status === "processing" || project.status === "queued",
    ).length;
    const ready = projects.filter((project) => project.status === "ready").length;
    const failed = projects.filter((project) => project.status === "failed").length;
    const clips = projects.reduce(
      (total, project) => total + project.clips_count,
      0,
    );
    return { total: projects.length, active, ready, failed, clips };
  }, [projects]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return projects.filter((project) => {
      if (statusFilter !== "all") {
        const matchesStatus =
          statusFilter === "processing"
            ? project.status === "processing" || project.status === "queued"
            : project.status === statusFilter;
        if (!matchesStatus) return false;
      }
      if (languageFilter !== "all") {
        if (project.language.toLowerCase() !== languageFilter) return false;
      }
      if (term && !project.title.toLowerCase().includes(term)) return false;
      return true;
    });
  }, [projects, statusFilter, languageFilter, search]);

  if (projectsQuery.isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-[92px] rounded-xl" />
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-[320px] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (projectsQuery.isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle aria-hidden="true" />
        <AlertDescription>
          <span className="block font-medium">
            No se pudieron cargar los proyectos
          </span>
          {errorMessage(projectsQuery.error)}. Comprueba que la API esté levantada
          con <code>pnpm dev</code>.
        </AlertDescription>
        <div className="mt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void projectsQuery.refetch()}
          >
            <RefreshCw aria-hidden="true" />
            Reintentar
          </Button>
        </div>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <section
        aria-label="Resumen del estudio"
        className="grid grid-cols-1 divide-y divide-white/[0.08] rounded-xl border border-white/[0.08] bg-[#111114] sm:grid-cols-3 sm:divide-x sm:divide-y-0"
      >
        <div className="flex items-baseline justify-between gap-4 px-5 py-4">
          <div>
            <p className="text-xs text-zinc-400">Proyectos activos</p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-50">
              {stats.total}
            </p>
          </div>
          <span className="font-mono text-xs tabular-nums text-amber-400">
            {stats.active > 0 ? `${stats.active} procesando` : "Cola libre"}
          </span>
        </div>

        <div className="flex items-baseline justify-between gap-4 px-5 py-4">
          <div>
            <p className="text-xs text-zinc-400">Clips generados</p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-50">
              {stats.clips}
            </p>
          </div>
          <span className="font-mono text-xs tabular-nums text-emerald-400">
            9:16 listos
          </span>
        </div>

        <div className="flex items-baseline justify-between gap-4 px-5 py-4">
          <div>
            <p className="text-xs text-zinc-400">Completados</p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-50">
              {stats.ready}
            </p>
          </div>
          <span
            className={cn(
              "font-mono text-xs tabular-nums",
              stats.failed > 0 ? "text-rose-400" : "text-zinc-400",
            )}
          >
            {stats.failed > 0
              ? `${stats.failed} con error`
              : "Listos para revisar"}
          </span>
        </div>
      </section>

      <div className="flex flex-col gap-3 rounded-xl border border-white/10 bg-[#0d0d10] p-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[180px] flex-1 lg:max-w-xs">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-zinc-500"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar proyectos…"
              aria-label="Buscar proyectos"
              className="pl-8"
            />
          </div>

          <div className="flex rounded-lg border border-white/10 p-0.5">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() => setStatusFilter(filter.id)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  statusFilter === filter.id
                    ? "bg-white/10 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-300",
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <div className="flex rounded-lg border border-white/10 p-0.5">
            {(["all", "es", "en"] as const).map((language) => (
              <button
                key={language}
                type="button"
                onClick={() => setLanguageFilter(language)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium uppercase transition-colors",
                  languageFilter === language
                    ? "bg-white/10 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-300",
                )}
              >
                {language === "all" ? "Todos" : language.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-xs",
              connected ? "text-emerald-400" : "text-zinc-500",
            )}
            title={
              connected
                ? "Eventos en vivo conectados"
                : "Sin conexión SSE; reintentando"
            }
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

          <div className="flex rounded-lg border border-white/10 p-0.5">
            <button
              type="button"
              aria-label="Vista de cuadrícula"
              onClick={() => setViewMode("grid")}
              className={cn(
                "rounded-md p-1.5",
                viewMode === "grid"
                  ? "bg-white/10 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              <LayoutGrid className="size-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              aria-label="Vista de lista"
              onClick={() => setViewMode("list")}
              className={cn(
                "rounded-md p-1.5",
                viewMode === "list"
                  ? "bg-white/10 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              <List className="size-4" aria-hidden="true" />
            </button>
          </div>

          <Button asChild size="sm">
            <Link href="/projects/new">
              <Plus aria-hidden="true" />
              Nuevo proyecto
            </Link>
          </Button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/10 bg-[#0d0d10] px-6 py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-amber-500/10 text-amber-400">
            <FolderOpen className="size-6" aria-hidden="true" />
          </div>
          <div>
            <p className="text-base font-semibold text-zinc-100">
              Aún no hay proyectos
            </p>
            <p className="mt-1 max-w-md text-sm text-zinc-500">
              Pega una URL de YouTube o sube un archivo para generar tus primeros
              shorts verticales con subtítulos.
            </p>
          </div>
          <Button asChild className="mt-1">
            <Link href="/projects/new">
              <Sparkles aria-hidden="true" />
              Crear el primero
            </Link>
          </Button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-white/10 bg-[#0d0d10] px-6 py-14 text-center">
          <p className="text-sm font-medium text-zinc-200">
            Ningún proyecto coincide con los filtros
          </p>
          <p className="text-xs text-zinc-500">
            Prueba a cambiar el estado, el idioma o la búsqueda.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => {
              setStatusFilter("all");
              setLanguageFilter("all");
              setSearch("");
            }}
          >
            Limpiar filtros
          </Button>
        </div>
      ) : (
        <div
          className={cn(
            viewMode === "grid"
              ? "grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
              : "flex flex-col gap-2",
          )}
        >
          {filtered.map((project) => (
            <ProjectCard key={project.id} project={project} variant={viewMode} />
          ))}
        </div>
      )}

      {projectsQuery.isFetching && !projectsQuery.isLoading ? (
        <p className="flex items-center justify-center gap-2 text-xs text-zinc-600">
          <Loader2 className="size-3 animate-spin" aria-hidden="true" />
          Actualizando…
        </p>
      ) : null}
    </div>
  );
}
