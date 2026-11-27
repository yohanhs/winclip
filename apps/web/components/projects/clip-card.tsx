"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Download,
  Loader2,
  Pencil,
  Play,
  Scissors,
  Send,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { mediaUrl } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ClipOut } from "@winclip/api-client";

export interface ClipCardProps {
  clip: ClipOut;
  selected: boolean;
  onToggleSelect: (clipId: string, selected: boolean) => void;
  onPlay: (clip: ClipOut) => void;
  onEdit: (clip: ClipOut) => void;
  onTrim: (clip: ClipOut) => void;
  onDelete: (clip: ClipOut) => void;
  onDownload: (clip: ClipOut) => void;
  onPublish?: (clip: ClipOut) => void;
  downloading?: boolean;
}

function scoreClasses(score: number): string {
  if (score >= 90) return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
  if (score >= 75) return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  return "border-zinc-500/40 bg-zinc-500/15 text-zinc-300";
}

export function ClipCard({
  clip,
  selected,
  onToggleSelect,
  onPlay,
  onEdit,
  onTrim,
  onDelete,
  onDownload,
  onPublish,
  downloading = false,
}: ClipCardProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [hovering, setHovering] = useState(false);

  const thumb = mediaUrl(clip.thumb_url, clip.updated_at);
  const video = mediaUrl(clip.video_url, clip.updated_at);
  const isRendering = clip.status === "rendering" || clip.status === "pending";
  const isReady = clip.status === "rendered" || clip.status === "ready";
  const violations = clip.rule_violations ?? [];
  const hasErrorViolation = violations.some((v) => v.severity === "error");

  const startHover = () => {
    setHovering(true);
  };

  const stopHover = () => {
    const element = videoRef.current;
    if (element) {
      element.pause();
      element.currentTime = 0;
    }
    setHovering(false);
  };

  useEffect(() => {
    if (!hovering || !video || !isReady) return;
    const element = videoRef.current;
    if (!element) return;
    element.currentTime = 0;
    void element.play()?.catch(() => undefined);
    return () => {
      element.pause();
      element.currentTime = 0;
    };
  }, [hovering, video, isReady]);

  return (
    <article
      data-testid={`clip-card-${clip.id}`}
      className={cn(
        "group flex flex-col overflow-hidden rounded-xl border bg-[#111114] transition-colors",
        selected
          ? "border-amber-500/60 ring-1 ring-amber-500/30"
          : "border-white/10 hover:border-white/25",
      )}
    >
      <div
        className="relative aspect-[9/16] overflow-hidden bg-black"
        onMouseEnter={startHover}
        onMouseLeave={stopHover}
      >
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-zinc-900 to-zinc-950" />
        )}

        {video && hovering && isReady ? (
          <video
            ref={videoRef}
            src={video}
            muted
            loop
            playsInline
            preload="none"
            className="absolute inset-0 h-full w-full object-cover"
            aria-hidden="true"
          />
        ) : null}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/30" />

        {isRendering ? (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-black/60 text-center backdrop-blur-[2px]">
            <Loader2 className="size-6 animate-spin text-amber-400" aria-hidden="true" />
            <p className="text-xs font-medium text-zinc-200">Re-renderizando…</p>
            <p className="max-w-[80%] text-[10px] text-zinc-400">
              El clip se actualizará automáticamente al terminar.
            </p>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => onPlay(clip)}
            disabled={!isReady}
            aria-label={`Reproducir ${clip.title}`}
            className="absolute inset-0 z-10 flex items-center justify-center opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 disabled:cursor-not-allowed"
          >
            <span className="flex size-12 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur transition-transform hover:scale-105">
              <Play className="size-5 translate-x-0.5" aria-hidden="true" />
            </span>
          </button>
        )}

        <div className="pointer-events-none absolute left-2 top-2 z-20 flex items-center gap-1.5">
          <Badge
            variant="outline"
            className={cn("font-mono text-[11px] tabular-nums", scoreClasses(clip.score))}
          >
            {Math.round(clip.score)}/100
          </Badge>
          {violations.length > 0 ? (
            <Badge
              variant="outline"
              data-testid={`clip-violations-badge-${clip.id}`}
              className={cn(
                "gap-1 font-mono text-[10px] tabular-nums",
                hasErrorViolation
                  ? "border-rose-500/45 bg-rose-500/20 text-rose-200"
                  : "border-amber-400/45 bg-amber-500/20 text-amber-200",
              )}
            >
              <AlertTriangle className="size-3" aria-hidden="true" />
              {violations.length}{" "}
              {violations.length === 1 ? "alerta" : "alertas"}
            </Badge>
          ) : null}
        </div>

        <div className="absolute right-2 top-2 z-20">
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) =>
              onToggleSelect(clip.id, checked === true)
            }
            aria-label={`Seleccionar ${clip.title}`}
            className="size-5 border-white/50 bg-black/40 data-[state=checked]:border-amber-400 data-[state=checked]:bg-amber-500 data-[state=checked]:text-black"
          />
        </div>

        <span className="pointer-events-none absolute bottom-2 right-2 z-20 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-zinc-200">
          {formatTimestamp(clip.duration)}
        </span>
        <span className="pointer-events-none absolute bottom-2 left-2 z-20 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-zinc-300">
          {formatTimestamp(clip.start_sec)} → {formatTimestamp(clip.end_sec)}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-zinc-100">
          {clip.title}
        </h3>
        {clip.hook ? (
          <p className="line-clamp-2 text-xs italic text-zinc-400">{clip.hook}</p>
        ) : null}
        {clip.hashtags.length > 0 ? (
          <p className="line-clamp-1 font-mono text-[11px] text-amber-400/80">
            {clip.hashtags
              .slice(0, 4)
              .map((tag) => (tag.startsWith("#") ? tag : `#${tag}`))
              .join(" ")}
          </p>
        ) : null}

        {violations.length > 0 ? (
          <div
            data-testid={`clip-violations-${clip.id}`}
            className={cn(
              "space-y-1 rounded-md border px-2.5 py-2 text-[11px]",
              hasErrorViolation
                ? "border-rose-500/35 bg-rose-500/10 text-rose-200"
                : "border-amber-400/30 bg-amber-500/10 text-amber-200",
            )}
          >
            {violations.map((violation, index) => (
              <div
                key={`${violation.code}-${index}`}
                className="flex items-start gap-1.5 leading-snug"
              >
                <AlertTriangle
                  className={cn(
                    "mt-0.5 size-3 shrink-0",
                    violation.severity === "error"
                      ? "text-rose-400"
                      : "text-amber-400",
                  )}
                  aria-hidden="true"
                />
                <span>{violation.message}</span>
              </div>
            ))}
          </div>
        ) : null}

        <div className="mt-auto flex items-center justify-between gap-1 border-t border-white/5 pt-2">
          <div className="flex items-center gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Editar ${clip.title}`}
              onClick={() => onEdit(clip)}
              disabled={!isReady}
            >
              <Pencil className="size-4" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Recortar ${clip.title}`}
              onClick={() => onTrim(clip)}
              disabled={!isReady}
            >
              <Scissors className="size-4" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Descargar ${clip.title}`}
              onClick={() => onDownload(clip)}
              disabled={!isReady || downloading}
            >
              {downloading ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Download className="size-4" aria-hidden="true" />
              )}
            </Button>
            {onPublish ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Publicar ${clip.title}`}
                className="text-amber-400 hover:text-amber-300"
                onClick={() => onPublish(clip)}
                disabled={!isReady}
              >
                <Send className="size-4" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Eliminar ${clip.title}`}
            className="text-zinc-500 hover:text-rose-400"
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar este clip?</AlertDialogTitle>
            <AlertDialogDescription>
              Se borrará «{clip.title}» y su vídeo renderizado. Esta acción no se
              puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => onDelete(clip)}
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </article>
  );
}
