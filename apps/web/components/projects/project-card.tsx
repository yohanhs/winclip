"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Film,
  Loader2,
  MoreHorizontal,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
} from "@/components/ui/alert-dialog";
import { Progress } from "@/components/ui/progress";
import { useDeleteProject } from "@/hooks/use-projects";
import { errorMessage, mediaUrl } from "@/lib/api";
import { formatDate, formatDuration, stageLabel, statusLabel } from "@/lib/format";
import type { ProjectOut } from "@winclip/api-client";

const STATUS_STYLES: Record<
  string,
  { className: string; icon: typeof CheckCircle2 }
> = {
  ready: {
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    icon: CheckCircle2,
  },
  processing: {
    className: "border-amber-500/30 bg-amber-500/10 text-amber-400",
    icon: Loader2,
  },
  queued: {
    className: "border-zinc-500/30 bg-zinc-500/10 text-zinc-300",
    icon: Clock,
  },
  failed: {
    className: "border-rose-500/30 bg-rose-500/10 text-rose-400",
    icon: AlertCircle,
  },
};

const QUEUED_STYLE = {
  className: "border-zinc-500/30 bg-zinc-500/10 text-zinc-300",
  icon: Clock,
};

export function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_STYLES[status] ?? QUEUED_STYLE;
  const Icon = meta.icon;
  return (
    <Badge variant="outline" className={meta.className}>
      <Icon
        className={status === "processing" ? "animate-spin" : undefined}
        aria-hidden="true"
      />
      {statusLabel(status)}
    </Badge>
  );
}

export interface ProjectCardProps {
  project: ProjectOut;
  variant?: "grid" | "list";
}

export function ProjectCard({ project, variant = "grid" }: ProjectCardProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const deleteProject = useDeleteProject();
  const thumb = mediaUrl(project.thumb_url, project.updated_at);
  const activeJob = project.active_job;
  const progress = activeJob?.progress ?? project.latest_job?.progress ?? 0;
  const isBusy = project.status === "processing" || project.status === "queued";

  const handleDelete = () => {
    deleteProject.mutate(project.id, {
      onSuccess: () => {
        setConfirmOpen(false);
        toast.success("Proyecto eliminado");
      },
      onError: (error) => {
        toast.error("No se pudo eliminar el proyecto", {
          description: errorMessage(error),
        });
      },
    });
  };

  if (variant === "list") {
    return (
      <Card className="flex flex-row items-center gap-4 p-3">
        <Link
          href={`/projects/${project.id}`}
          className="relative h-16 w-28 shrink-0 overflow-hidden rounded-md border border-white/10 bg-black/40"
        >
          {thumb ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumb}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-zinc-600">
              <Film className="size-5" aria-hidden="true" />
            </div>
          )}
        </Link>

        <div className="min-w-0 flex-1">
          <Link
            href={`/projects/${project.id}`}
            className="truncate text-sm font-semibold text-zinc-100 hover:text-amber-400"
          >
            {project.title}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            <StatusBadge status={project.status} />
            <span>{project.clips_count} clips</span>
            <span aria-hidden="true">·</span>
            <span>{formatDuration(project.duration)}</span>
            <span aria-hidden="true">·</span>
            <span>{formatDate(project.created_at)}</span>
          </div>
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Eliminar ${project.title}`}
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2 className="size-4 text-zinc-500" aria-hidden="true" />
        </Button>

        {renderDeleteDialog()}
      </Card>
    );
  }

  function renderDeleteDialog() {
    return (
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar este proyecto?</AlertDialogTitle>
            <AlertDialogDescription>
              Se borrarán «{project.title}», sus clips y los archivos generados. Esta
              acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteProject.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteProject.isPending}
              onClick={(event) => {
                event.preventDefault();
                handleDelete();
              }}
            >
              {deleteProject.isPending ? "Eliminando…" : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  return (
    <Card className="group flex h-full flex-col overflow-hidden transition-colors hover:border-white/20">
      <Link
        href={`/projects/${project.id}`}
        className="relative block aspect-video overflow-hidden bg-gradient-to-br from-zinc-900 to-zinc-950"
      >
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt=""
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Film className="size-10 text-zinc-700" aria-hidden="true" />
          </div>
        )}
        <div className="absolute left-3 top-3">
          <StatusBadge status={project.status} />
        </div>
        {project.duration ? (
          <span className="absolute bottom-3 right-3 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-zinc-200">
            {formatDuration(project.duration)}
          </span>
        ) : null}
      </Link>

      <CardHeader className="gap-1 pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="min-w-0">
            <Link
              href={`/projects/${project.id}`}
              className="line-clamp-2 text-base leading-snug hover:text-amber-400"
            >
              {project.title}
            </Link>
          </CardTitle>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Acciones de ${project.title}`}
              >
                <MoreHorizontal className="size-4" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                className="text-rose-400 focus:text-rose-300"
                onSelect={() => setConfirmOpen(true)}
              >
                <Trash2 className="size-4" aria-hidden="true" />
                Eliminar proyecto
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-3 pb-2">
        {isBusy ? (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span className="truncate">
                {activeJob?.stage ? stageLabel(activeJob.stage) : "En cola"}
              </span>
              <span className="font-mono tabular-nums">
                {Math.round(progress)}%
              </span>
            </div>
            <Progress value={progress} className="h-1.5" />
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
          <span className="inline-flex items-center gap-1">
            <Film className="size-3.5" aria-hidden="true" />
            {project.clips_count} clips
          </span>
          <span className="uppercase">{project.language}</span>
          <span>{project.source_type === "url" ? "URL" : "Archivo"}</span>
        </div>
      </CardContent>

      <CardFooter className="justify-between border-t border-white/5 pt-3 text-xs text-zinc-500">
        <span>{formatDate(project.created_at)}</span>
        <Link
          href={`/projects/${project.id}`}
          className="font-medium text-amber-400 hover:text-amber-300"
        >
          Abrir →
        </Link>
      </CardFooter>

      {renderDeleteDialog()}
    </Card>
  );
}
