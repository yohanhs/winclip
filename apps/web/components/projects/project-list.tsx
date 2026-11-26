"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  LayoutGrid,
  List,
  FolderOpen,
  RefreshCw,
  AlertCircle,
  Video,
  HardDrive,
  Play,
  Film,
} from "lucide-react";
import { ProjectCard } from "./project-card";
import { useProjects, useHealth } from "@/hooks/use-api-client";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "@winclip/api-client";

type ProjectItem = components["schemas"]["ProjectOut"];

// Helper to format date
function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Helper to calculate pipeline progress from jobs
function calculatePipelineProgress(
  activeJob: components["schemas"]["JobSummary"] | null | undefined,
  jobs?: components["schemas"]["JobOut"][]
): number {
  // Use active job progress if available
  if (activeJob?.progress !== null && activeJob?.progress !== undefined) {
    return activeJob.progress;
  }

  // Fallback: calculate from completed jobs
  if (jobs && jobs.length > 0) {
    const completedJobs = jobs.filter(
      (j) => j.status === "ready" || j.status === "done"
    ).length;
    const totalJobs = jobs.length;
    return totalJobs > 0 ? Math.round((completedJobs / totalJobs) * 100) : 0;
  }

  return 0;
}

export function ProjectList() {
  const { data: projects, isLoading, isError, refetch } = useProjects();
  const { data: health } = useHealth();
  const queryClient = useQueryClient();

  // Filter states
  const [statusFilter, setStatusFilter] = useState<"all" | "processing" | "ready">(
    "all"
  );
  const [langFilter, setLangFilter] = useState<"all" | "ES" | "EN">("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // Deleted project tracking for optimistic UI
  const [deletedProjectId, setDeletedProjectId] = useState<string | null>(null);

  // Calculate metrics from real API data
  const activeCount = useMemo(
    () =>
      projects?.filter((p) => p.status === "processing").length ?? 0,
    [projects]
  );

  const totalClips = useMemo(
    () => projects?.reduce((sum, p) => sum + (p.clips_count ?? 0), 0) ?? 0,
    [projects]
  );

  const scheduledToday = useMemo(() => {
    // Use health check data if available, otherwise estimate from projects
    if (health?.checks) {
      const storageCheck = health.checks.find((c) => c.name === "storage");
      return storageCheck ? 1 : 0;
    }
    return 0;
  }, [health]);

  // Filter projects
  const filtered = useMemo(() => {
    if (!projects) return [];
    return projects.filter((project) => {
      if (statusFilter !== "all" && project.status !== statusFilter) return false;
      if (langFilter !== "all" && project.language !== langFilter) return false;
      return true;
    });
  }, [projects, statusFilter, langFilter]);

  // Filter out deleted project from the list
  const activeProjects = filtered.filter(
    (project) => project.id !== deletedProjectId
  );

  // Handle SSE project updates (invalidate cache)
  const handleProjectUpdate = (projectId: string) => {
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  };

  // Handle project deletion completion
  const handleDeleteSuccess = (projectId: string) => {
    setDeletedProjectId(projectId);
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  };

  if (isLoading) {
    return (
      <div className="max-w-[1440px] mx-auto space-y-6">
        {/* Metrics skeleton */}
        <section className="grid grid-cols-1 sm:grid-cols-3 bg-[#111114] border border-white/[0.08] rounded-lg divide-y sm:divide-y-0 sm:divide-x divide-white/[0.08]">
          <div className="px-5 py-4">
            <p className="text-[12px] text-zinc-400">Proyectos activos</p>
            <div className="h-8 w-16 bg-white/[0.08] rounded mt-1" />
          </div>
          <div className="px-5 py-4">
            <p className="text-[12px] text-zinc-400">Clips generados</p>
            <div className="h-8 w-16 bg-white/[0.08] rounded mt-1" />
          </div>
          <div className="px-5 py-4">
            <p className="text-[12px] text-zinc-400">Programados hoy</p>
            <div className="h-8 w-16 bg-white/[0.08] rounded mt-1" />
          </div>
        </section>

        {/* Filter skeleton */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-20 h-8 bg-white/[0.08] rounded" />
            <div className="w-16 h-8 bg-white/[0.08] rounded" />
          </div>
          <div className="flex items-center gap-2">
            <div className="w-10 h-8 bg-white/[0.08] rounded" />
            <div className="w-10 h-8 bg-white/[0.08] rounded" />
          </div>
        </div>

        {/* Card skeletons */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="bg-[#111114] border border-white/[0.08] rounded-lg overflow-hidden animate-pulse"
            >
              <div className="aspect-video bg-zinc-800" />
              <div className="p-4 space-y-2">
                <div className="h-5 bg-white/[0.08] rounded" />
                <div className="h-3 bg-white/[0.08] rounded w-3/4" />
                <div className="h-3 bg-white/[0.08] rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="max-w-[1440px] mx-auto">
        <Alert variant="destructive" className="bg-[#111114] border border-white/[0.08]">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Error al cargar los proyectos.{" "}
            <Button
              variant="link"
              onClick={() => refetch()}
              className="p-0 h-auto"
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!activeProjects || activeProjects.length === 0) {
    return (
      <div className="max-w-[1440px] mx-auto">
        {/* Metrics bar for empty state */}
        <section className="grid grid-cols-1 sm:grid-cols-3 bg-[#111114] border border-white/[0.08] rounded-lg divide-y sm:divide-y-0 sm:divide-x divide-white/[0.08]">
          <div className="px-5 py-4 flex items-baseline justify-between gap-4">
            <div>
              <p className="text-[12px] text-zinc-400">Proyectos activos</p>
              <p className="text-2xl font-bold font-mono tabular-nums text-zinc-50 mt-1">
                0
              </p>
            </div>
          </div>
          <div className="px-5 py-4 flex items-baseline justify-between gap-4">
            <div>
              <p className="text-[12px] text-zinc-400">Clips generados</p>
              <p className="text-2xl font-bold font-mono tabular-nums text-zinc-50 mt-1">
                0
              </p>
            </div>
          </div>
          <div className="px-5 py-4 flex items-baseline justify-between gap-4">
            <div>
              <p className="text-[12px] text-zinc-400">Programados hoy</p>
              <p className="text-2xl font-bold font-mono tabular-nums text-zinc-50 mt-1">
                0
              </p>
            </div>
          </div>
        </section>

        {/* Empty state */}
        <div className="bg-[#111114] border border-white/[0.08] rounded-lg py-16 px-6 text-center space-y-3 mt-6">
          <div className="w-11 h-11 rounded-lg bg-white/[0.04] border border-white/[0.08] mx-auto flex items-center justify-center text-zinc-400">
            <FolderOpen className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h2 className="text-[15px] font-semibold text-zinc-100">
              No hay proyectos que coincidan
            </h2>
            <p className="text-[13px] text-zinc-400 max-w-md mx-auto">
              Ajusta los filtros activos o crea un nuevo proyecto pegando un
              enlace de YouTube o subiendo un archivo local.
            </p>
          </div>
          <Link href="/projects/new" className="mt-2 inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 h-9 px-4 py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950">
            <Play className="w-4 h-4" />
            <span>Nuevo proyecto</span>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1440px] mx-auto space-y-6">
      {/* Top Quick Stats Strip */}
      <section
        aria-label="Resumen del estudio"
        className="grid grid-cols-1 sm:grid-cols-3 bg-[#111114] border border-white/[0.08] rounded-lg divide-y sm:divide-y-0 sm:divide-x divide-white/[0.08]"
      >
        <div className="px-5 py-4 flex items-baseline justify-between gap-4">
          <div>
            <p className="text-[12px] text-zinc-400">Proyectos activos</p>
            <p className="text-2xl font-bold font-mono tabular-nums text-zinc-50 mt-1">
              {projects?.length ?? 0}
            </p>
          </div>
          <span className="text-[12px] font-mono tabular-nums text-amber-400">
            {activeCount > 0 ? `${activeCount} procesando` : "Cola libre"}
          </span>
        </div>

        <div className="px-5 py-4 flex items-baseline justify-between gap-4">
          <div>
            <p className="text-[12px] text-zinc-400">Clips generados</p>
            <p className="text-2xl font-bold font-mono tabular-nums text-zinc-50 mt-1">
              {totalClips}
            </p>
          </div>
          <span className="text-[12px] font-mono tabular-nums text-emerald-400">
            9:16 listos
          </span>
        </div>

        <div className="px-5 py-4 flex items-baseline justify-between gap-4">
          <div>
            <p className="text-[12px] text-zinc-400">Programados hoy</p>
            <p className="text-2xl font-bold font-mono tabular-nums text-zinc-50 mt-1">
              {scheduledToday}
            </p>
          </div>
          <Link
            href="/publications"
            className="text-[12px] text-zinc-400 hover:text-amber-300 inline-flex items-center gap-1 transition-colors whitespace-nowrap"
          >
            <span>Ver cola</span>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 8l4 4m0 0l-4 4m4-4H3"
              />
            </svg>
          </Link>
        </div>
      </section>

      {/* Filter & View Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Status filter tabs */}
          <div className="inline-flex items-center p-0.5 rounded-md bg-[#111114] border border-white/[0.08]">
            {(
              [
                { id: "all", label: "Todos" },
                { id: "processing", label: "En proceso" },
                { id: "ready", label: "Completados" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1.5 text-[12px] font-medium rounded-[5px] transition-colors whitespace-nowrap ${
                  statusFilter === tab.id
                    ? "bg-white/[0.1] text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Language filter tabs */}
          <div className="inline-flex items-center p-0.5 rounded-md bg-[#111114] border border-white/[0.08]">
            {(["all", "ES", "EN"] as const).map((lang) => (
              <button
                key={lang}
                type="button"
                onClick={() => setLangFilter(lang)}
                className={`px-2.5 py-1.5 text-[12px] font-mono rounded-[5px] transition-colors whitespace-nowrap ${
                  langFilter === lang
                    ? "bg-white/[0.1] text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {lang === "all" ? "ES/EN" : lang}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] text-zinc-500 font-mono tabular-nums mr-1">
            {activeProjects.length} {activeProjects.length === 1 ? "proyecto" : "proyectos"}
          </span>

          {/* View mode toggle */}
          <div className="inline-flex items-center p-0.5 rounded-md bg-[#111114] border border-white/[0.08]">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              aria-label="Vista cuadrícula"
              className={`p-1.5 rounded-[5px] transition-colors ${
                viewMode === "grid"
                  ? "bg-white/[0.1] text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-200"
              }`}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              aria-label="Vista lista"
              className={`p-1.5 rounded-[5px] transition-colors ${
                viewMode === "list"
                  ? "bg-white/[0.1] text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-200"
              }`}
            >
              <List className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Project grid or list */}
      {viewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {activeProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onDelete={handleDeleteSuccess}
              onUpdate={handleProjectUpdate}
            />
          ))}
        </div>
      ) : (
        <div className="bg-[#111114] border border-white/[0.08] rounded-lg divide-y divide-white/[0.06] overflow-hidden">
          {activeProjects.map((project) => (
            <div
              key={project.id}
              className="flex items-center gap-4 px-4 py-3 hover:bg-white/[0.03] transition-colors"
            >
              <div className="relative w-32 aspect-video rounded-md overflow-hidden bg-zinc-900 shrink-0 border border-white/[0.08]">
                {project.thumb_url ? (
                  <img
                    src={project.thumb_url}
                    alt={project.title}
                    referrerPolicy="no-referrer"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center">
                    <Film className="w-7 h-7 text-zinc-500" />
                  </div>
                )}
                <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/80 text-[10px] font-mono tabular-nums text-zinc-100">
                  {project.duration
                    ? `${Math.floor(project.duration / 60)}:${String(
                        project.duration % 60
                      ).padStart(2, "0")}`
                    : "--:--"}
                </span>
              </div>

              <div className="min-w-0 flex-1 space-y-1">
                <h3 className="text-[14px] font-semibold text-zinc-100">
                  {project.title}
                </h3>
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px] text-zinc-400">
                  <span className="inline-flex items-center gap-1 text-zinc-300">
                    {project.source_type === "url" ? (
                      <Video className="w-3.5 h-3.5 text-rose-400" />
                    ) : (
                      <HardDrive className="w-3.5 h-3.5 text-sky-400" />
                    )}
                    {project.source_type === "url"
                      ? "YouTube"
                      : "Archivo local"}
                  </span>
                  <span aria-hidden="true" className="text-zinc-600">
                    ·
                  </span>
                  <span className="font-mono text-zinc-300">
                    {project.language}
                  </span>
                  <span aria-hidden="true" className="text-zinc-600">
                    ·
                  </span>
                  <span>{project.campaign_id ?? "Sin campaña"}</span>
                  <span aria-hidden="true" className="text-zinc-600">
                    ·
                  </span>
                  <span className="text-zinc-500">
                    {formatDate(project.created_at)}
                  </span>
                </div>
              </div>

              <div className="shrink-0 w-44 text-right space-y-1.5">
                {project.status === "processing" ? (
                  <>
                    <div className="flex items-center justify-end gap-1.5 text-[12px] font-mono text-cyan-300">
                      <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      <span>Procesando</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-white/[0.08] overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-400 to-amber-400 rounded-full transition-all duration-300"
                        style={{
                          width: `${calculatePipelineProgress(
                            project.active_job,
                            project.jobs
                          )}%`,
                        }}
                      />
                    </div>
                  </>
                ) : (
                  <div className="flex items-center justify-end gap-3">
                    <span className="text-[12px] font-mono tabular-nums text-zinc-200">
                      {project.clips_count ?? 0} clips
                    </span>
                    <span className="text-[12px] text-emerald-400">Listo</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}