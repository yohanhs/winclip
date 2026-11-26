"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import {
  Play,
  Video,
  HardDrive,
  Trash2,
  MoreHorizontal,
  Loader2,
  AlertCircle,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardFooter,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useProjectClips, useProjectEvents } from "@/hooks/use-api-client";
import { useDeleteProject } from "@/hooks/use-projects";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "@winclip/api-client";

type ProjectCardProps = {
  project: components["schemas"]["ProjectOut"];
  onDelete?: (projectId: string) => void;
  onUpdate?: (projectId: string) => void;
};

export function ProjectCard({
  project,
  onDelete,
  onUpdate,
}: ProjectCardProps) {
  const { status, thumb_url, title, id, active_job, latest_job, language, clips_count } =
    project;

  const deleteMutation = useDeleteProject();
  const clipsQuery = useProjectClips(id);
  const queryClient = useQueryClient();

  // Track deletion state for optimistic UI
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  // SSE event handling for project updates
  interface ProjectEvent {
    type: string;
    data?: Record<string, unknown>;
    error?: string | null;
  }
  const [projectEvents, setProjectEvents] = useState<
    Map<string, ProjectEvent>
  >(new Map());

  const handleEvent = (event: ProjectEvent) => {
    setProjectEvents((prev) => {
      const next = new Map(prev);
      next.set(id, event);
      return next;
    });
    onUpdate?.(id);
  };

  // Initialize SSE connection for project-specific events
  useProjectEvents(
    status === "processing" ? id : null,
    handleEvent
  );

  // Merge SSE data with project data
  const eventData = projectEvents.get(id);
  const effectiveProgress = eventData?.type === "job.progress"
    ? typeof eventData.data?.progress === "number" ? eventData.data.progress : 0
    : (active_job?.progress ?? 0);

  const effectiveStage = eventData?.type === "job.progress"
    ? (eventData.data?.stage as string | undefined)
    : (active_job?.stage);

  // Get source type display
  const sourceType = project.source_type || "local";
  const isYouTube = sourceType === "url";
  const sourceLabel = isYouTube ? "YouTube" : "Archivo local";

  // Get clip count
  const clipCount = clipsQuery.data?.length ?? project.clips_count ?? 0;

  // Determine if project is processing
  const isActiveJob = active_job || latest_job;
  const isProcessing = status === "processing" || eventData?.type === "job.progress";

  // Handle delete
  const handleDelete = async () => {
    setPendingDeleteId(id);
    try {
      await deleteMutation.mutateAsync(id);
      onDelete?.(id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    } finally {
      setPendingDeleteId(null);
    }
  };

  // Error state from SSE or job
  const hasError = isActiveJob?.error || eventData?.type === "job.failed";
  const errorMessage = eventData?.error || isActiveJob?.error;

  // Format duration
  const duration = project.duration;
  const durationLabel =
    duration !== undefined && duration !== null && duration > 0
      ? `${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, "0")}`
      : "--:--";

  return (
    <Card className="group relative overflow-hidden border-border bg-card text-card-foreground">
      {/* Error state overlay */}
      {hasError && (
        <div className="absolute inset-0 bg-black/80 z-10 flex items-center justify-center">
          <div className="text-center space-y-2 p-4">
            <AlertCircle className="w-8 h-8 text-rose-400 mx-auto" />
            <p className="text-sm text-rose-300">Error de procesamiento</p>
            <p className="text-xs text-zinc-400">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Thumbnail */}
      <div className="relative aspect-video w-full overflow-hidden bg-zinc-900">
        {thumb_url && !hasError ? (
          <img
            src={thumb_url}
            alt={title}
            className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
          />
        ) : hasError ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <AlertCircle className="w-8 h-8 text-rose-400" />
          </div>
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <HardDrive className="w-7 h-7 text-zinc-500" />
          </div>
        )}

        {/* Top row: Source badge + Language pill */}
        {!hasError && (
          <div className="absolute top-2.5 inset-x-2.5 flex items-center justify-between gap-2 pointer-events-none">
            {/* Source badge */}
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/72 backdrop-blur-sm border border-white/10 text-[11px] font-medium text-zinc-100">
              {isYouTube ? (
                <Video className="w-3.5 h-3.5 text-rose-400" />
              ) : (
                <HardDrive className="w-3.5 h-3.5 text-sky-400" />
              )}
              <span>{sourceLabel}</span>
            </span>

            {/* Language pill */}
            <span className="px-1.5 py-0.5 rounded bg-black/72 backdrop-blur-sm border border-white/10 text-[11px] font-mono font-semibold text-zinc-200">
              {language}
            </span>
          </div>
        )}

        {/* Bottom row: Clip count + Duration */}
        {!hasError && (
          <div className="absolute bottom-2.5 inset-x-2.5 flex items-center justify-between gap-2 pointer-events-none">
            {/* Clip count with Play icon */}
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/75 backdrop-blur-sm text-[11px] font-mono tabular-nums text-amber-300">
              <Play className="w-3 h-3 fill-current" />
              <span>{clipCount} clips</span>
            </span>
            {/* Duration */}
            <span className="px-1.5 py-0.5 rounded bg-black/80 text-[11px] font-mono tabular-nums text-zinc-100">
              {durationLabel}
            </span>
          </div>
        )}
      </div>

      {/* Card body */}
      <CardHeader className="flex flex-row items-start justify-between p-4">
        <div className="space-y-1">
          <h3 className="text-sm font-medium leading-none">
            <Link
              href={`/projects/${id}`}
              className="hover:text-amber-300 transition-colors"
            >
              {title}
            </Link>
          </h3>
          <p className="text-xs text-muted-foreground line-clamp-2">
            {project.campaign_id ?? "Sin campaña"}
          </p>
        </div>

        <AlertDialog
          open={pendingDeleteId === id}
          onOpenChange={(open) => {
            if (!open) setPendingDeleteId(null);
          }}
        >
          <AlertDialogTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <MoreHorizontal className="h-4 w-4" />
              <span className="sr-only">Abrir menú</span>
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent className="bg-[#111114] border border-white/[0.08]">
            <AlertDialogHeader>
              <AlertDialogTitle>Eliminar proyecto</AlertDialogTitle>
              <AlertDialogDescription>
                ¿Estás seguro de que quieres eliminar el proyecto &quot;
                {title}&quot;? Esta acción no se puede deshacer.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
                className="bg-rose-500 hover:bg-rose-600 text-white"
              >
                {deleteMutation.isPending ? "Eliminando..." : "Eliminar"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardHeader>

      <CardContent className="p-4 pt-0">
        {/* Progress bar for processing projects */}
        {isProcessing && !hasError && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-cyan-300 font-medium">
                {effectiveStage ?? "Procesando..."}
              </span>
              <span className="font-mono text-foreground">
                {effectiveProgress}%
              </span>
            </div>
            <Progress value={effectiveProgress} className="h-1.5" />
          </div>
        )}

        {/* Status badge */}
        <div className="mt-3">
          <Badge
            variant={
              status === "ready"
                ? "default"
                : status === "failed"
                  ? "destructive"
                  : "outline"
            }
            className={
              status === "ready"
                ? "bg-emerald-400/10 text-emerald-400 border-emerald-400/20"
                : status === "failed"
                  ? "bg-rose-500/10 text-rose-400 border-rose-400/20"
                  : "bg-cyan-400/10 text-cyan-400 border-cyan-400/20"
            }
          >
            {status === "ready"
              ? "Listo"
              : status === "failed"
                ? "Error"
                : status === "processing"
                  ? "Procesando"
                  : "Pendiente"}
            {hasError && (
              <AlertCircle className="w-3 h-3 ml-1" />
            )}
          </Badge>
        </div>
      </CardContent>

      {/* Footer for ready projects */}
      {!isProcessing && !hasError && (
        <CardFooter className="border-t border-white/[0.06] p-4 pt-0">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span className="font-mono truncate max-w-[60%]">
              {project.source_url || project.thumb_url || "Sin contenido"}
            </span>
            <Link
              href={`/projects/${id}`}
              className="text-emerald-400 hover:text-emerald-300 font-medium"
            >
              Ver detalles →
            </Link>
          </div>
        </CardFooter>
      )}
    </Card>
  );
}