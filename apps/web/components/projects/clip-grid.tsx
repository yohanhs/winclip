"use client";

import { useEffect, useMemo, useState } from "react";
import { Film, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteClip } from "@/hooks/use-clips";
import { downloadClipFile } from "@/lib/download";
import { errorMessage } from "@/lib/api";
import type { ClipOut } from "@winclip/api-client";

import { ClipCard } from "./clip-card";
import { ClipEditDialog } from "./clip-edit-dialog";
import { ClipPlayerDialog } from "./clip-player-dialog";
import { ClipTrimDialog } from "./clip-trim-dialog";
import { SelectionActionBar } from "./selection-action-bar";

export interface ClipGridProps {
  projectId: string;
  clips: ClipOut[];
  projectDuration?: number | null;
  isLoading?: boolean;
}

export function ClipGrid({
  projectId,
  clips,
  projectDuration,
  isLoading = false,
}: ClipGridProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [playerClip, setPlayerClip] = useState<ClipOut | null>(null);
  const [editClip, setEditClip] = useState<ClipOut | null>(null);
  const [trimClip, setTrimClip] = useState<ClipOut | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const deleteClip = useDeleteClip(projectId);

  useEffect(() => {
    setSelectedIds((current) => {
      const available = new Set(clips.map((clip) => clip.id));
      const next = new Set(
        [...current].filter((id) => available.has(id)),
      );
      return next.size === current.size ? current : next;
    });
  }, [clips]);

  const maxDuration = useMemo(() => {
    if (projectDuration && projectDuration > 0) return projectDuration;
    return clips.reduce((max, clip) => Math.max(max, clip.end_sec), 0);
  }, [clips, projectDuration]);

  const toggleSelect = (clipId: string, selected: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (selected) next.add(clipId);
      else next.delete(clipId);
      return next;
    });
  };

  const selectAll = () => {
    setSelectedIds(new Set(clips.map((clip) => clip.id)));
  };

  const handleDownload = async (clip: ClipOut) => {
    setDownloadingId(clip.id);
    try {
      await downloadClipFile(clip);
      toast.success("Descarga iniciada", { description: clip.title });
    } catch (error) {
      toast.error("No se pudo descargar el clip", {
        description: errorMessage(error),
      });
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = (clip: ClipOut) => {
    deleteClip.mutate(clip.id, {
      onSuccess: () => toast.success("Clip eliminado"),
      onError: (error) =>
        toast.error("No se pudo eliminar el clip", {
          description: errorMessage(error),
        }),
    });
  };

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="aspect-[9/16] rounded-xl" />
        ))}
      </div>
    );
  }

  if (clips.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/10 bg-[#0d0d10] px-6 py-14 text-center">
        <div className="flex size-11 items-center justify-center rounded-full bg-white/5 text-zinc-500">
          <Film className="size-5" aria-hidden="true" />
        </div>
        <p className="text-sm font-medium text-zinc-200">
          Aún no hay clips en este proyecto
        </p>
        <p className="max-w-sm text-xs text-zinc-500">
          Los clips aparecerán aquí automáticamente en cuanto el pipeline termine
          cada render. También puedes seguir el progreso arriba.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-zinc-100">
            Clips generados
          </h2>
          <p className="text-xs text-zinc-500">
            {clips.length} {clips.length === 1 ? "short" : "shorts"} · selecciona
            varios para publicarlos juntos
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {deleteClip.isPending ? (
            <>
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
              Eliminando…
            </>
          ) : (
            <>
              <Sparkles className="size-3 text-amber-400" aria-hidden="true" />
              <span>Ordenados por score</span>
            </>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              if (selectedIds.size === clips.length) {
                setSelectedIds(new Set());
              } else {
                selectAll();
              }
            }}
          >
            {selectedIds.size === clips.length
              ? "Deseleccionar"
              : "Seleccionar todos"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {clips.map((clip) => (
          <ClipCard
            key={clip.id}
            clip={clip}
            selected={selectedIds.has(clip.id)}
            onToggleSelect={toggleSelect}
            onPlay={setPlayerClip}
            onEdit={setEditClip}
            onTrim={setTrimClip}
            onDelete={handleDelete}
            onDownload={(item) => void handleDownload(item)}
            downloading={downloadingId === clip.id}
          />
        ))}
      </div>

      <SelectionActionBar
        selectedCount={selectedIds.size}
        total={clips.length}
        onSelectAll={selectAll}
        onClear={() => setSelectedIds(new Set())}
      />

      <ClipPlayerDialog
        clip={playerClip}
        open={playerClip !== null}
        onOpenChange={(open) => {
          if (!open) setPlayerClip(null);
        }}
        onEdit={setEditClip}
        onTrim={setTrimClip}
        onDownload={(item) => void handleDownload(item)}
      />

      <ClipEditDialog
        clip={editClip}
        open={editClip !== null}
        onOpenChange={(open) => {
          if (!open) setEditClip(null);
        }}
      />

      <ClipTrimDialog
        clip={trimClip}
        open={trimClip !== null}
        onOpenChange={(open) => {
          if (!open) setTrimClip(null);
        }}
        maxDuration={maxDuration}
      />
    </div>
  );
}
