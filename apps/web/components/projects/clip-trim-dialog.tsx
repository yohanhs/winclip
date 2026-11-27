"use client";

import { useMemo, useState } from "react";
import { Loader2, RotateCcw, Scissors } from "lucide-react";
import { toast } from "sonner";
import type { ClipOut, ClipUpdate, ReframeMode } from "@winclip/api-client";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  useClipWords,
  useRerenderClip,
  useUpdateClip,
} from "@/hooks/use-clips";
import { usePresets } from "@/hooks/use-projects";
import { errorMessage, mediaUrl } from "@/lib/api";
import { clamp, formatTimestamp } from "@/lib/format";
import { CropControls } from "./crop-controls";
import { MiniTimeline } from "./mini-timeline";
import { SubtitleWordEditor } from "./subtitle-word-editor";

export interface ClipTrimDialogProps {
  clip: ClipOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Duración total del vídeo origen, para acotar los sliders. */
  maxDuration: number;
  /** Preset por defecto del proyecto (para mostrar herencia). */
  projectPreset?: string;
  /** Modo de reencuadre por defecto del proyecto (para mostrar herencia). */
  projectReframeMode?: ReframeMode;
}

const MIN_CLIP_SECONDS = 0.5;

function dictsEqual(a: Record<string, string>, b: Record<string, string>): boolean {
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => a[key] === b[key]);
}

function ClipTrimForm({
  clip,
  total,
  projectPreset,
  projectReframeMode,
  onOpenChange,
}: {
  clip: ClipOut;
  total: number;
  projectPreset: string;
  projectReframeMode: ReframeMode;
  onOpenChange: (open: boolean) => void;
}) {
  const [start, setStart] = useState(clip.start_sec);
  const [end, setEnd] = useState(Math.min(clip.end_sec, total));
  const [title, setTitle] = useState(clip.title);
  const [description, setDescription] = useState(clip.description);
  const [hashtags, setHashtags] = useState(clip.hashtags.join(" "));

  const initialSubOverrides = useMemo(
    () => ({ ...(clip.subtitle_overrides ?? {}) }),
    [clip.subtitle_overrides],
  );
  const [subtitleOverrides, setSubtitleOverrides] =
    useState<Record<string, string>>(initialSubOverrides);

  const [subtitlePreset, setSubtitlePreset] = useState<string | null>(
    clip.subtitle_preset ?? null,
  );
  const [reframeMode, setReframeMode] = useState<ReframeMode | null>(
    clip.reframe_mode ?? null,
  );
  const [cropXPct, setCropXPct] = useState<number>(clip.crop_x_pct ?? 50);
  const [cropYPct, setCropYPct] = useState<number>(clip.crop_y_pct ?? 50);
  const [zoomPct, setZoomPct] = useState<number>(clip.zoom_pct ?? 100);

  const wordsQuery = useClipWords(clip.id, { enabled: true });
  const presetsQuery = usePresets();
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

  const effectivePreset = subtitlePreset ?? projectPreset;
  const effectiveReframe: ReframeMode = reframeMode ?? projectReframeMode;
  const editedWordsCount = Object.keys(subtitleOverrides).length;
  const hasStyleOverride =
    subtitlePreset !== null ||
    reframeMode !== null ||
    cropXPct !== 50 ||
    cropYPct !== 50 ||
    zoomPct !== 100;

  const handleSave = async () => {
    if (invalid) {
      toast.error("Rango no válido", {
        description:
          "El inicio debe ser menor que el fin y ambos deben estar dentro del vídeo.",
      });
      return;
    }

    const data: ClipUpdate = {
      start_sec: Math.round(start * 100) / 100,
      end_sec: Math.round(end * 100) / 100,
    };

    const trimmedTitle = title.trim();
    if (trimmedTitle && trimmedTitle !== clip.title) {
      data.title = trimmedTitle;
    }
    const trimmedDescription = description.trim();
    if (trimmedDescription !== clip.description) {
      data.description = trimmedDescription;
    }
    const originalHashtags = clip.hashtags.join(" ");
    if (hashtags !== originalHashtags) {
      data.hashtags = hashtags
        .split(/[\s,]+/)
        .map((tag) => tag.trim().replace(/^#+/, ""))
        .filter((tag) => tag.length > 0);
    }

    if (!dictsEqual(subtitleOverrides, initialSubOverrides)) {
      data.subtitle_overrides = subtitleOverrides;
    }

    if (subtitlePreset !== (clip.subtitle_preset ?? null)) {
      data.subtitle_preset = subtitlePreset;
    }
    if (reframeMode !== (clip.reframe_mode ?? null)) {
      data.reframe_mode = reframeMode;
    }
    if (effectiveReframe === "center") {
      if (cropXPct !== (clip.crop_x_pct ?? 50) || clip.crop_x_pct !== null) {
        data.crop_x_pct = cropXPct;
      }
      if (cropYPct !== (clip.crop_y_pct ?? 50) || clip.crop_y_pct !== null) {
        data.crop_y_pct = cropYPct;
      }
      if (zoomPct !== (clip.zoom_pct ?? 100) || clip.zoom_pct !== null) {
        data.zoom_pct = zoomPct;
      }
    } else {
      if (clip.crop_x_pct != null) data.crop_x_pct = null;
      if (clip.crop_y_pct != null) data.crop_y_pct = null;
      if (clip.zoom_pct != null) data.zoom_pct = null;
    }

    try {
      await updateClip.mutateAsync({ clipId: clip.id, data });
      await rerenderClip.mutateAsync(clip.id);
      toast.success("Cambios guardados", {
        description: "El clip se está re-renderizando con los nuevos ajustes.",
      });
      onOpenChange(false);
    } catch (error) {
      toast.error("No se pudo guardar el clip", {
        description: errorMessage(error),
      });
    }
  };

  // Tamaño relativo del recuadro guía 9:16 aproximado según zoom_pct (50..200)
  const guideScale = clamp(100 / zoomPct, 0.5, 1);

  return (
    <>
      <div className="grid gap-5 md:grid-cols-[190px_1fr]">
        <div className="mx-auto flex w-[190px] flex-col gap-2">
          <div className="relative overflow-hidden rounded-xl border border-white/10 bg-[#09090B]">
            <div className="relative aspect-[9/16]">
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

              {effectiveReframe === "center" ? (
                <div
                  aria-label="Guía de recorte manual"
                  className="pointer-events-none absolute inset-0"
                >
                  <div
                    className="absolute rounded border border-dashed border-amber-400/80 bg-amber-400/10 transition-all"
                    style={{
                      width: `${Math.round(guideScale * 100)}%`,
                      height: `${Math.round(guideScale * 100)}%`,
                      left: `${Math.round((1 - guideScale) * cropXPct)}%`,
                      top: `${Math.round((1 - guideScale) * cropYPct)}%`,
                    }}
                  />
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-1.5 text-[10px] font-mono text-zinc-400">
            <span className="rounded border border-white/10 bg-[#0D0D10] px-1.5 py-0.5 uppercase">
              {effectivePreset}
            </span>
            <span className="rounded border border-white/10 bg-[#0D0D10] px-1.5 py-0.5">
              {effectiveReframe}
            </span>
          </div>
        </div>

        <Tabs defaultValue="trim" className="min-w-0">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="trim">Recorte y metadatos</TabsTrigger>
            <TabsTrigger value="subtitles" className="gap-1.5">
              Subtítulos
              {editedWordsCount > 0 ? (
                <span className="rounded bg-amber-400/20 px-1 font-mono text-[10px] tabular-nums text-amber-300">
                  {editedWordsCount}
                </span>
              ) : null}
            </TabsTrigger>
            <TabsTrigger value="style" className="gap-1.5">
              Cámara / Estilo
              {hasStyleOverride ? (
                <span
                  className="size-1.5 rounded-full bg-amber-400"
                  aria-hidden="true"
                />
              ) : null}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="trim" className="mt-3 space-y-4">
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

            <div className="space-y-3 border-t border-white/10 pt-3">
              <div className="space-y-1.5">
                <Label htmlFor="trim-clip-title">Título</Label>
                <Input
                  id="trim-clip-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  disabled={saving}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="trim-clip-description">Descripción</Label>
                  <Textarea
                    id="trim-clip-description"
                    rows={2}
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    disabled={saving}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="trim-clip-hashtags">Hashtags</Label>
                  <Input
                    id="trim-clip-hashtags"
                    value={hashtags}
                    onChange={(event) => setHashtags(event.target.value)}
                    placeholder="#shorts #finanzas"
                    disabled={saving}
                  />
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="subtitles" className="mt-3">
            <SubtitleWordEditor
              words={wordsQuery.data?.words ?? []}
              overrides={subtitleOverrides}
              onChange={setSubtitleOverrides}
              isLoading={wordsQuery.isLoading}
              errorMessage={
                wordsQuery.isError ? errorMessage(wordsQuery.error) : null
              }
              disabled={saving}
            />
          </TabsContent>

          <TabsContent value="style" className="mt-3">
            <CropControls
              presets={presetsQuery.data ?? []}
              projectPreset={projectPreset}
              projectReframeMode={projectReframeMode}
              subtitlePreset={subtitlePreset}
              reframeMode={reframeMode}
              cropXPct={cropXPct}
              cropYPct={cropYPct}
              zoomPct={zoomPct}
              onSubtitlePresetChange={setSubtitlePreset}
              onReframeModeChange={setReframeMode}
              onCropXChange={setCropXPct}
              onCropYChange={setCropYPct}
              onZoomChange={setZoomPct}
              onReset={() => {
                setSubtitlePreset(null);
                setReframeMode(null);
                setCropXPct(50);
                setCropYPct(50);
                setZoomPct(100);
              }}
              disabled={saving}
            />
          </TabsContent>
        </Tabs>
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
            "Guardar y Re-renderizar"
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
  projectPreset = "bold-yellow",
  projectReframeMode = "face",
}: ClipTrimDialogProps) {
  const total = Math.max(
    maxDuration,
    clip?.end_sec ?? 0,
    clip?.start_sec ?? 0,
    MIN_CLIP_SECONDS * 2,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Scissors className="size-4 text-amber-400" aria-hidden="true" />
            Editor de clip
          </DialogTitle>
          <DialogDescription>
            Ajusta recorte, subtítulos palabra por palabra, preset y encuadre.
            Al guardar, el clip se re-renderiza automáticamente.
          </DialogDescription>
        </DialogHeader>

        {clip ? (
          <ClipTrimForm
            key={`${clip.id}:${clip.updated_at}:${total}`}
            clip={clip}
            total={total}
            projectPreset={projectPreset}
            projectReframeMode={projectReframeMode}
            onOpenChange={onOpenChange}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
