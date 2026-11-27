"use client";

import { useState } from "react";
import { Loader2, RotateCcw, Scissors } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { useRerenderClip, useUpdateClip } from "@/hooks/use-clips";
import { errorMessage, mediaUrl } from "@/lib/api";
import { clamp, formatTimestamp } from "@/lib/format";
import { MiniTimeline } from "./mini-timeline";
import type { ClipOut } from "@winclip/api-client";

export interface ClipTrimDialogProps {
  clip: ClipOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Duración total del vídeo origen, para acotar los sliders. */
  maxDuration: number;
}

const MIN_CLIP_SECONDS = 0.5;

function ClipTrimForm({
  clip,
  total,
  onOpenChange,
}: {
  clip: ClipOut;
  total: number;
  onOpenChange: (open: boolean) => void;
}) {
  const [start, setStart] = useState(clip.start_sec);
  const [end, setEnd] = useState(Math.min(clip.end_sec, total));

  const updateClip = useUpdateClip(clip.project_id);
  const rerenderClip = useRerenderClip(clip.project_id);
  const saving = updateClip.isPending || rerenderClip.isPending;

  const invalid =
    Number.isNaN(start) ||
    Number.isNaN(end) ||
    start < 0 ||
    end <= start ||
    end > total;

  const videoSrc = mediaUrl(clip.video_url, clip.updated_at);
  const posterSrc = mediaUrl(clip.thumb_url, clip.updated_at);

  const handleSave = async () => {
    if (invalid) {
      toast.error("Rango no válido", {
        description:
          "El inicio debe ser menor que el fin y ambos deben estar dentro del vídeo.",
      });
      return;
    }

    try {
      await updateClip.mutateAsync({
        clipId: clip.id,
        data: {
          start_sec: Math.round(start * 100) / 100,
          end_sec: Math.round(end * 100) / 100,
        },
      });
      await rerenderClip.mutateAsync(clip.id);
      toast.success("Recorte guardado", {
        description: "El clip se está re-renderizando con los nuevos tiempos.",
      });
      onOpenChange(false);
    } catch (error) {
      toast.error("No se pudo recortar el clip", {
        description: errorMessage(error),
      });
    }
  };

  return (
    <>
      <div className="grid gap-5 md:grid-cols-[170px_1fr]">
        <div className="mx-auto w-[170px] overflow-hidden rounded-xl border border-white/10 bg-[#09090B]">
          <div className="aspect-[9/16]">
            {videoSrc ? (
              <video
                key={videoSrc}
                src={videoSrc}
                poster={posterSrc ?? undefined}
                controls
                muted
                playsInline
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full items-center justify-center p-3 text-center text-xs text-zinc-500">
                Vista previa 9:16
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <MiniTimeline
            duration={total}
            start={clamp(Number.isNaN(start) ? 0 : start, 0, total)}
            end={clamp(Number.isNaN(end) ? total : end, 0, total)}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="trim-start-input">Entrada (IN · s)</Label>
                <span className="font-mono text-xs tabular-nums text-amber-400">
                  {formatTimestamp(Math.max(0, start))}
                </span>
              </div>
              <Input
                id="trim-start-input"
                type="number"
                step={0.1}
                min={0}
                max={total}
                value={Number.isNaN(start) ? "" : start}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setStart(Number.isNaN(next) ? 0 : next);
                }}
                disabled={saving}
                className="font-mono tabular-nums"
              />
              <Slider
                value={[clamp(start, 0, Math.max(0, end - MIN_CLIP_SECONDS))]}
                min={0}
                max={Math.max(0, end - MIN_CLIP_SECONDS)}
                step={0.1}
                onValueChange={(values) =>
                  setStart(clamp(values[0] ?? 0, 0, end - MIN_CLIP_SECONDS))
                }
                aria-label="Punto de entrada"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="trim-end-input">Salida (OUT · s)</Label>
                <span className="font-mono text-xs tabular-nums text-amber-400">
                  {formatTimestamp(Math.max(0, end))}
                </span>
              </div>
              <Input
                id="trim-end-input"
                type="number"
                step={0.1}
                min={0}
                max={total}
                value={Number.isNaN(end) ? "" : end}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setEnd(Number.isNaN(next) ? 0 : next);
                }}
                disabled={saving}
                className="font-mono tabular-nums"
              />
              <Slider
                value={[
                  clamp(end, Math.min(total, start + MIN_CLIP_SECONDS), total),
                ]}
                min={Math.min(total, start + MIN_CLIP_SECONDS)}
                max={total}
                step={0.1}
                onValueChange={(values) =>
                  setEnd(
                    clamp(
                      values[0] ?? total,
                      start + MIN_CLIP_SECONDS,
                      total,
                    ),
                  )
                }
                aria-label="Punto de salida"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-[#0d0d10] px-3 py-2 text-xs">
            <span className="text-zinc-500">
              Duración resultante:{" "}
              <span className="font-mono tabular-nums text-zinc-200">
                {formatTimestamp(Math.max(0, end - start))}
              </span>
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setStart(clip.start_sec);
                setEnd(Math.min(clip.end_sec, total));
              }}
              disabled={saving}
            >
              <RotateCcw aria-hidden="true" />
              Restablecer
            </Button>
          </div>

          {invalid ? (
            <p role="alert" className="text-xs text-rose-400">
              El rango no es válido: 0 ≤ inicio &lt; fin ≤{" "}
              {formatTimestamp(total)}.
            </p>
          ) : null}
        </div>
      </div>

      <DialogFooter>
        <Button
          type="button"
          variant="ghost"
          onClick={() => onOpenChange(false)}
          disabled={saving}
        >
          Cancelar
        </Button>
        <Button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving || invalid}
        >
          {saving ? (
            <>
              <Loader2 className="animate-spin" aria-hidden="true" />
              Guardando y re-renderizando…
            </>
          ) : (
            "Guardar y re-renderizar"
          )}
        </Button>
      </DialogFooter>
    </>
  );
}

export function ClipTrimDialog({
  clip,
  open,
  onOpenChange,
  maxDuration,
}: ClipTrimDialogProps) {
  const total = Math.max(
    maxDuration,
    clip?.end_sec ?? 0,
    clip?.start_sec ?? 0,
    MIN_CLIP_SECONDS * 2,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Scissors className="size-4 text-amber-400" aria-hidden="true" />
            Recortar clip
          </DialogTitle>
          <DialogDescription>
            Ajusta los puntos de entrada y salida. Al guardar, el clip se
            re-renderiza y se actualiza automáticamente al estar listo.
          </DialogDescription>
        </DialogHeader>

        {clip ? (
          <ClipTrimForm
            key={`${clip.id}:${clip.updated_at}:${total}`}
            clip={clip}
            total={total}
            onOpenChange={onOpenChange}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
