"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { useProjectClips } from "@/hooks/use-api-client";
import { useDeleteProject } from "@/hooks/use-projects";
import type { components } from "@winclip/api-client";

type ProjectCardProps = {
  project: components["schemas"]["ProjectOut"];
  onDelete?: (projectId: string) => void;
};

export function ProjectCard({ project, onDelete }: ProjectCardProps) {
  const { status, thumb_url, title, id, active_job, latest_job } =
    project;

  const deleteMutation = useDeleteProject();
  const clipsQuery = useProjectClips(id);

  const handleDelete = async () => {
    if (window.confirm(`¿Estás seguro de que quieres eliminar el proyecto "${title}"?`)) {
      await deleteMutation.mutateAsync(id);
      onDelete?.(id);
    }
  };

  // Estado del job activo
  const isActiveJob = active_job || latest_job;
  const jobProgress = isActiveJob?.progress ?? 0;

  return (
    <Card className="group relative overflow-hidden border-border bg-card text-card-foreground">
      {/* Miniatura o placeholder */}
      <div className="aspect-video w-full overflow-hidden bg-muted">
        {thumb_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb_url}
            alt={title}
            className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-8 w-8 text-muted-foreground"
            >
              <path d="M21 12V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v5h16z" />
              <path d="M3 12v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5H3z" />
              <line x1="12" y1="17" x2="12" y2="12" />
              <line x1="12" y1="12" x2="15" y2="9" />
            </svg>
          </div>
        )}
      </div>

      <CardHeader className="flex flex-row items-start justify-between p-4">
        <div className="space-y-1">
          <h3 className="text-sm font-medium leading-none">{title}</h3>
          <p className="text-xs text-muted-foreground">
            {clipsQuery.data?.length ?? project.clips_count} clips
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <MoreHorizontal className="h-4 w-4" />
              <span className="sr-only">Abrir menú</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleDelete} disabled={deleteMutation.isPending}>
              <Trash2 className="mr-2 h-4 w-4" />
              Eliminar proyecto
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>

      <CardContent className="p-4 pt-0">
        {/* Barra de progreso en vivo vía SSE */}
        {isActiveJob && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{isActiveJob.stage}</span>
              <span className="font-mono text-foreground">{jobProgress}%</span>
            </div>
            <Progress value={jobProgress} className="h-2" />
            {isActiveJob.error && (
              <p className="text-xs text-destructive">{isActiveJob.error}</p>
            )}
          </div>
        )}

        {/* Badges de estado */}
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge
            variant={
              status === "ready"
                ? "default"
                : status === "failed"
                  ? "destructive"
                  : "outline"
            }
          >
            {status === "ready"
              ? "Listo"
              : status === "failed"
                ? "Error"
                : status === "processing"
                  ? "Procesando"
                  : "Pendiente"}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}