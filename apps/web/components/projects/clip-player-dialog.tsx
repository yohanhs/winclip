"use client";

import { Download, Pencil, Scissors } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { mediaUrl } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type { ClipOut } from "@winclip/api-client";

export interface ClipPlayerDialogProps {
  clip: ClipOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit?: (clip: ClipOut) => void;
  onTrim?: (clip: ClipOut) => void;
  onDownload?: (clip: ClipOut) => void;
}

export function ClipPlayerDialog({
  clip,
  open,
  onOpenChange,
  onEdit,
  onTrim,
  onDownload,
}: ClipPlayerDialogProps) {
  const video = clip ? mediaUrl(clip.video_url, clip.updated_at) : null;
  const poster = clip ? mediaUrl(clip.thumb_url, clip.updated_at) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        {clip ? (
          <>
            <DialogHeader>
              <DialogTitle className="pr-8">{clip.title}</DialogTitle>
              <DialogDescription>
                {formatTimestamp(clip.start_sec)} → {formatTimestamp(clip.end_sec)} ·{" "}
                {formatTimestamp(clip.duration)} · score {Math.round(clip.score)}
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-4 sm:grid-cols-[minmax(0,300px)_1fr]">
              <div className="mx-auto w-full max-w-[300px] overflow-hidden rounded-xl border border-white/10 bg-black">
                <div className="aspect-[9/16]">
                  {video ? (
                    <video
                      key={video}
                      src={video}
                      poster={poster ?? undefined}
                      controls
                      autoPlay
                      playsInline
                      className="h-full w-full object-contain"
                    >
                      Tu navegador no soporta vídeo HTML5.
                    </video>
                  ) : (
                    <div className="flex h-full items-center justify-center p-6 text-center text-xs text-zinc-500">
                      El vídeo aún no está disponible.
                    </div>
                  )}
                </div>
              </div>

              <div className="flex min-w-0 flex-col gap-3">
                {clip.hook ? (
                  <p className="rounded-lg border border-white/10 bg-[#0d0d10] p-3 text-sm text-zinc-300">
                    {clip.hook}
                  </p>
                ) : null}
                {clip.description ? (
                  <p className="text-sm leading-relaxed text-zinc-400">
                    {clip.description}
                  </p>
                ) : null}
                {clip.hashtags.length > 0 ? (
                  <p className="text-xs text-amber-400/80">
                    {clip.hashtags
                      .map((tag) => (tag.startsWith("#") ? tag : `#${tag}`))
                      .join(" ")}
                  </p>
                ) : null}

                <div className="mt-auto flex flex-wrap gap-2 pt-2">
                  {onEdit ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        onOpenChange(false);
                        onEdit(clip);
                      }}
                    >
                      <Pencil aria-hidden="true" />
                      Editar
                    </Button>
                  ) : null}
                  {onTrim ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        onOpenChange(false);
                        onTrim(clip);
                      }}
                    >
                      <Scissors aria-hidden="true" />
                      Recortar
                    </Button>
                  ) : null}
                  {onDownload ? (
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => onDownload(clip)}
                    >
                      <Download aria-hidden="true" />
                      Descargar MP4
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
