"use client";

import { Camera, RotateCcw, Sparkles } from "lucide-react";
import type { ReframeMode, SubtitlePreset } from "@winclip/api-client";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";

const REFRAME_OPTIONS: Array<{
  value: ReframeMode | null;
  label: string;
  hint: string;
}> = [
  { value: null, label: "Heredar", hint: "Usa el modo del proyecto" },
  { value: "face", label: "Rostro IA", hint: "Seguimiento OpenCV YuNet" },
  { value: "center", label: "Manual", hint: "Encuadre y zoom manual" },
  { value: "blur", label: "Blur", hint: "Vídeo 16:9 con fondo difuminado" },
  { value: "passthrough", label: "Original 9:16", hint: "Sin recorte horizontal" },
];

export interface CropControlsProps {
  presets: SubtitlePreset[];
  projectPreset: string;
  projectReframeMode: ReframeMode;
  subtitlePreset: string | null;
  reframeMode: ReframeMode | null;
  cropXPct: number;
  cropYPct: number;
  zoomPct: number;
  onSubtitlePresetChange: (value: string | null) => void;
  onReframeModeChange: (value: ReframeMode | null) => void;
  onCropXChange: (value: number) => void;
  onCropYChange: (value: number) => void;
  onZoomChange: (value: number) => void;
  onReset: () => void;
  disabled?: boolean;
}

export function CropControls({
  presets,
  projectPreset,
  projectReframeMode,
  subtitlePreset,
  reframeMode,
  cropXPct,
  cropYPct,
  zoomPct,
  onSubtitlePresetChange,
  onReframeModeChange,
  onCropXChange,
  onCropYChange,
  onZoomChange,
  onReset,
  disabled = false,
}: CropControlsProps) {
  const effectiveReframe: ReframeMode = reframeMode ?? projectReframeMode;
  const showManualCrop = effectiveReframe === "center";
  const hasAnyOverride =
    subtitlePreset !== null ||
    reframeMode !== null ||
    cropXPct !== 50 ||
    cropYPct !== 50 ||
    zoomPct !== 100;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="clip-subtitle-preset" className="flex items-center gap-1.5">
            <Sparkles className="size-3.5 text-amber-400" aria-hidden="true" />
            Preset de subtítulos
          </Label>
          <span className="font-mono text-[11px] text-zinc-500">
            Proyecto: {projectPreset}
          </span>
        </div>
        <select
          id="clip-subtitle-preset"
          aria-label="Preset de subtítulos"
          value={subtitlePreset ?? ""}
          disabled={disabled}
          onChange={(event) => {
            const val = event.target.value;
            onSubtitlePresetChange(val === "" ? null : val);
          }}
          className="h-9 w-full rounded-md border border-white/10 bg-[#0D0D10] px-3 text-xs text-zinc-100 outline-none focus:border-amber-400/60 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="">Heredar del proyecto ({projectPreset})</option>
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.name} ({preset.id})
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Label className="flex items-center gap-1.5">
            <Camera className="size-3.5 text-amber-400" aria-hidden="true" />
            Modo de reencuadre
          </Label>
          <span className="font-mono text-[11px] text-zinc-500">
            Efectivo: {effectiveReframe}
          </span>
        </div>
        <div
          role="group"
          aria-label="Modo de reencuadre"
          className="grid grid-cols-2 gap-1.5 sm:grid-cols-3"
        >
          {REFRAME_OPTIONS.map((option) => {
            const active = reframeMode === option.value;
            return (
              <button
                key={option.value ?? "inherit"}
                type="button"
                disabled={disabled}
                aria-pressed={active}
                onClick={() => onReframeModeChange(option.value)}
                className={cn(
                  "flex cursor-pointer flex-col items-start rounded-lg border px-2.5 py-2 text-left transition-colors",
                  active
                    ? "border-amber-400/60 bg-amber-400/12 text-amber-200"
                    : "border-white/10 bg-[#0D0D10] text-zinc-300 hover:border-white/20 hover:bg-[#141418]",
                  disabled && "cursor-not-allowed opacity-60",
                )}
              >
                <span className="text-xs font-medium">{option.label}</span>
                <span className="text-[10px] text-zinc-500">{option.hint}</span>
              </button>
            );
          })}
        </div>
      </div>

      {showManualCrop ? (
        <div className="space-y-3 rounded-xl border border-white/10 bg-[#0D0D10] p-3">
          <p className="text-[11px] font-medium text-zinc-300">
            Encuadre manual (modo center)
          </p>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <Label htmlFor="crop-x-slider">Posición horizontal (Crop X)</Label>
              <span className="font-mono tabular-nums text-amber-400">
                {cropXPct}%
              </span>
            </div>
            <Slider
              id="crop-x-slider"
              aria-label="Posición horizontal (Crop X)"
              value={[cropXPct]}
              min={0}
              max={100}
              step={1}
              disabled={disabled}
              onValueChange={(values) => onCropXChange(values[0] ?? 50)}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <Label htmlFor="crop-y-slider">Posición vertical (Crop Y)</Label>
              <span className="font-mono tabular-nums text-amber-400">
                {cropYPct}%
              </span>
            </div>
            <Slider
              id="crop-y-slider"
              aria-label="Posición vertical (Crop Y)"
              value={[cropYPct]}
              min={0}
              max={100}
              step={1}
              disabled={disabled}
              onValueChange={(values) => onCropYChange(values[0] ?? 50)}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <Label htmlFor="crop-zoom-slider">Zoom</Label>
              <span className="font-mono tabular-nums text-amber-400">
                {zoomPct}%
              </span>
            </div>
            <Slider
              id="crop-zoom-slider"
              aria-label="Zoom"
              value={[zoomPct]}
              min={50}
              max={200}
              step={5}
              disabled={disabled}
              onValueChange={(values) => onZoomChange(values[0] ?? 100)}
            />
          </div>
        </div>
      ) : (
        <p className="rounded-lg border border-white/10 bg-[#0D0D10] px-3 py-2 text-[11px] text-zinc-500">
          Selecciona el modo <span className="font-mono text-zinc-300">Manual (center)</span>{" "}
          para ajustar manualmente Crop X, Crop Y y Zoom.
        </p>
      )}

      <div className="flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onReset}
          disabled={disabled || !hasAnyOverride}
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
          Restablecer estilo
        </Button>
      </div>
    </div>
  );
}
