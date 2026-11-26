"use client";

import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  Video,
} from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCancelJob, useProjectClips } from "@/hooks/use-clips";
import { useProject } from "@/hooks/use-projects";
import { useProjectEvents } from "@/hooks/use-project-events";
import { errorMessage } from "@/lib/api";
import { formatDate, formatDuration, statusLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ClipGrid } from "./clip-grid";
import { PipelineStepper } from "./pipeline-stepper";
import { StatusBadge } from "./project-card";

export function ProjectDetail({ projectId }: { projectId: string }) {
  const projectQuery = useProject(projectId);
  const clipsQuery = useProjectClips(projectId);
  const cancelJob = useCancelJob(projectId);
  const { connected } = useProjectEvents(projectId);

  const project = projectQuery.data;
  const job = project?.active_job ?? project?.latest_job ?? null;

  if (projectQuery.isLoading) {
    return (
      <div className="mx-auto w-full max-w-[1400px] space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-36 w-full rounded-xl" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="aspect-[9/16] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (projectQuery.isError || !project) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/projects">
            <ArrowLeft aria-hidden="true" />
            Volver a proyectos
          </Link>
        </Button>
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertDescription>
            <span className="block font-medium">
              No se pudo cargar el proyecto
            </span>
            {errorMessage(projectQuery.error)}
          </AlertDescription>
          <div className="mt-3 flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void projectQuery.refetch()}
            >
              <RefreshCw aria-hidden="true" />
              Reintentar
            </Button>
          </div>
        </Alert>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5">
      <div className="flex flex-col gap-3">
        <Button asChild variant="ghost" size="sm" className="w-fit -ml-2">
          <Link href="/projects">
            <ArrowLeft aria-hidden="true" />
            Proyectos
          </Link>
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-2xl font-semibold tracking-tight text-zinc-100">
                {project.title}
              </h1>
              <StatusBadge status={project.status} />
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

            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500">
              <span className="inline-flex items-center gap-1">
                <Video className="size-3.5" aria-hidden="true" />
                {project.source_type === "url" ? "URL" : "Archivo local"}
              </span>
              <span className="inline-flex items-center gap-1">
                <Globe className="size-3.5" aria-hidden="true" />
                {project.language === "auto"
                  ? "Detección automática"
                  : project.language.toUpperCase()}
              </span>
              <span className="inline-flex items-center gap-1">
                <Calendar className="size-3.5" aria-hidden="true" />
                {formatDate(project.created_at)}
              </span>
              <span>{formatDuration(project.duration)}</span>
              <span>{project.clips_count} clips</span>
              <span className="font-mono uppercase">{project.subtitle_preset}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void projectQuery.refetch();
                void clipsQuery.refetch();
              }}
              disabled={projectQuery.isFetching}
            >
              <RefreshCw
                className={projectQuery.isFetching ? "animate-spin" : undefined}
                aria-hidden="true"
              />
              Actualizar
            </Button>
            {project.source_url ? (
              <Button asChild variant="ghost" size="sm">
                <a
                  href={project.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  <ExternalLink aria-hidden="true" />
                  Origen
                </a>
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <PipelineStepper
        job={job}
        projectStatus={project.status}
        canceling={cancelJob.isPending}
        onCancel={() => {
          if (!job) return;
          cancelJob.mutate(job.id, {
            onSuccess: () => toast.success("Trabajo cancelado"),
            onError: (error) =>
              toast.error("No se pudo cancelar el trabajo", {
                description: errorMessage(error),
              }),
          });
        }}
      />

      {clipsQuery.isError ? (
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertDescription>
            <span className="block font-medium">
              No se pudieron cargar los clips
            </span>
            {errorMessage(clipsQuery.error)}
          </AlertDescription>
          <div className="mt-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void clipsQuery.refetch()}
            >
              <RefreshCw aria-hidden="true" />
              Reintentar
            </Button>
          </div>
        </Alert>
      ) : null}

      <ClipGrid
        projectId={project.id}
        clips={clipsQuery.data ?? []}
        projectDuration={project.duration}
        isLoading={clipsQuery.isLoading}
      />

      {clipsQuery.isFetching && !clipsQuery.isLoading ? (
        <p className="flex items-center justify-center gap-2 text-xs text-zinc-600">
          <Loader2 className="size-3 animate-spin" aria-hidden="true" />
          Actualizando clips…
        </p>
      ) : null}

      <p className="text-center text-[11px] text-zinc-600">
        Estado del proyecto: {statusLabel(project.status)}
      </p>
    </div>
  );
}
