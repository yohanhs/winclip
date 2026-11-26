"use client";

import { useEffect, useState } from "react";
import {
  Bookmark,
  Heart,
  MessageCircle,
  Pause,
  Play,
  Share2,
} from "lucide-react";
import type { SubtitlePreset } from "@winclip/api-client";

import { cn } from "@/lib/utils";

interface PresetStyle {
  name: string;
  subtitle: string;
  swatch: string;
  lines: string[][];
  captionClassName: string;
  activeClassName: string;
  uppercase?: boolean;
  boxed?: boolean;
}

export const PRESET_STYLES: Record<string, PresetStyle> = {
  "bold-yellow": {
    name: "Bold Yellow",
    subtitle: "Karaoke blanco · palabra activa amarilla",
    swatch: "#FFD600",
    lines: [
      ["EL ERROR", "QUE TE CUESTA", "$500 AL MES"],
      ["NO ES", "EL CAFÉ,", "ES TU"],
      ["PILOTO", "AUTOMÁTICO", "BANCARIO."],
    ],
    captionClassName: "text-white",
    activeClassName: "text-[#FFD600]",
  },
  hormozi: {
    name: "Hormozi",
    subtitle: "Alto impacto · palabra activa verde",
    swatch: "#10B981",
    lines: [
      ["ESTO", "CAMBIA", "TODO"],
      ["NADIE TE", "LO CUENTA", "POR ESTO"],
      ["HAZLO", "HOY", "MISMO"],
    ],
    captionClassName: "text-white uppercase",
    activeClassName: "text-[#10B981]",
    uppercase: true,
  },
  "clean-white": {
    name: "Clean White",
    subtitle: "Caja limpia · palabra activa azul",
    swatch: "#38BDF8",
    lines: [
      ["Un sistema", "simple para", "crecer"],
      ["Menos ruido,", "más foco", "cada día"],
      ["Empieza", "por lo", "importante"],
    ],
    captionClassName: "text-white",
    activeClassName: "text-[#38BDF8]",
    boxed: true,
  },
  mrbeast: {
    name: "MrBeast",
    subtitle: "Mayúsculas extremas · contorno grueso",
    swatch: "#F97316",
    lines: [
      ["GANÉ", "$10,000", "EN 24H"],
      ["ESTO ES", "UNA", "LOCURA"],
      ["NO TE LO", "PUEDES", "PERDER"],
    ],
    captionClassName: "text-white uppercase",
    activeClassName: "text-[#FACC15]",
    uppercase: true,
  },
};


const FALLBACK_PRESET: PresetStyle = {
  name: "Bold Yellow",
  subtitle: "Karaoke blanco · palabra activa amarilla",
  swatch: "#FFD600",
  lines: [
    ["EL ERROR", "QUE TE CUESTA", "$500 AL MES"],
    ["NO ES", "EL CAFÉ,", "ES TU"],
    ["PILOTO", "AUTOMÁTICO", "BANCARIO."],
  ],
  captionClassName: "text-white",
  activeClassName: "text-[#FFD600]",
};

function presetStyle(preset: string): PresetStyle {
  return PRESET_STYLES[preset] ?? FALLBACK_PRESET;
}

export interface SubtitlePresetPreviewProps {
  preset: string;
  presetData?: SubtitlePreset | null;
  reframeMode?: string;
  isPlaying?: boolean;
  onTogglePlay?: (playing: boolean) => void;
  className?: string;
}

export function SubtitlePresetPreview({
  preset,
  presetData,
  reframeMode = "face",
  isPlaying = true,
  onTogglePlay,
  className,
}: SubtitlePresetPreviewProps) {
  const style = presetStyle(preset);
  const [playing, setPlaying] = useState(isPlaying);
  const [lineIndex, setLineIndex] = useState(0);
  const [wordIndex, setWordIndex] = useState(1);

  useEffect(() => {
    setPlaying(isPlaying);
  }, [isPlaying]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setWordIndex((current) => {
        const line = style.lines[lineIndex] ?? [];
        if (current + 1 >= line.length) {
          setLineIndex((index) => (index + 1) % style.lines.length);
          return 0;
        }
        return current + 1;
      });
    }, 650);
    return () => window.clearInterval(timer);
  }, [playing, lineIndex, style.lines]);

  const lines = style.lines[lineIndex] ?? style.lines[0] ?? [];
  const displayName = presetData?.name ?? style.name;
  const highlight = presetData?.highlight_color ?? style.swatch;

  return (
    <div className={cn("flex flex-col items-center gap-3", className)}>
      <div className="relative w-full max-w-[286px]">
        <div className="relative aspect-[9/16] overflow-hidden rounded-[2rem] border-[5px] border-zinc-800 bg-black shadow-2xl shadow-black/60">
          {/* Fondo simulado del clip según el modo de encuadre */}
          {reframeMode === "blur" ? (
            <>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,#52525b_0%,#27272a_48%,#09090b_100%)] blur-xl opacity-75" />
              <div className="absolute inset-0 flex items-center justify-center px-2">
                <div className="aspect-video w-full rounded-md border border-white/15 bg-[radial-gradient(circle_at_50%_35%,#3f3f46_0%,#18181b_70%,#09090b_100%)] shadow-2xl" />
              </div>
            </>
          ) : (
            <>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,#3f3f46_0%,#18181b_45%,#09090b_100%)]" />
              <div className="absolute inset-x-0 top-1/3 mx-auto h-40 w-40 rounded-full bg-zinc-700/30 blur-2xl" />
              <div className="absolute bottom-0 left-1/2 h-[55%] w-[70%] -translate-x-1/2 rounded-t-[45%] bg-gradient-to-t from-zinc-800/80 to-zinc-600/20" />
            </>
          )}

          {reframeMode === "face" ? (
            <div className="pointer-events-none absolute left-1/2 top-[17%] aspect-square w-[42%] -translate-x-1/2 rounded-lg border border-amber-400/45">
              <span className="absolute -top-5 left-0 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] text-amber-300/90">
                OpenCV YuNet
              </span>
            </div>
          ) : null}

          {/* Notch */}
          <div className="absolute left-1/2 top-2 z-20 h-5 w-20 -translate-x-1/2 rounded-full bg-black" />

          {/* Cabecera estilo red social */}
          <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-3 pt-9 text-[10px] text-white/90">
            <div className="flex items-center gap-1.5">
              <span className="flex size-5 items-center justify-center rounded-full bg-amber-500 font-bold text-black">
                W
              </span>
              <span className="font-semibold">winclip.studio</span>
            </div>
            <span className="rounded bg-red-500 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide">
              Live
            </span>
          </div>

          {/* Rail de acciones */}
          <div className="absolute bottom-24 right-2 z-10 flex flex-col items-center gap-3 text-white">
            <div className="flex flex-col items-center gap-0.5">
              <Heart className="size-5" aria-hidden="true" />
              <span className="text-[8px]">12.4k</span>
            </div>
            <div className="flex flex-col items-center gap-0.5">
              <MessageCircle className="size-5" aria-hidden="true" />
              <span className="text-[8px]">318</span>
            </div>
            <div className="flex flex-col items-center gap-0.5">
              <Share2 className="size-5" aria-hidden="true" />
              <span className="text-[8px]">1.2k</span>
            </div>
            <Bookmark className="size-5" aria-hidden="true" />
          </div>

          {/* Zona segura superior/inferior */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-12 border-b border-dashed border-white/10" />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-16 border-t border-dashed border-white/10" />

          {/* Subtítulos */}
          <div className="absolute inset-x-0 bottom-[19%] z-20 flex flex-col items-center gap-0.5 px-4 text-center">
            {lines.map((line, index) => (
              <p
                key={`${line}-${index}`}
                className={cn(
                  "max-w-full text-balance font-extrabold leading-tight",
                  preset === "mrbeast" || preset === "hormozi"
                    ? "caption-stroke-heavy"
                    : "caption-stroke",
                  style.boxed && "rounded bg-black/55 px-1.5 py-0.5",
                  style.captionClassName,
                )}
                style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: preset === "mrbeast" ? "1.35rem" : "1.05rem",
                  WebkitTextStroke:
                    preset === "mrbeast" ? "1px rgba(0,0,0,0.9)" : undefined,
                }}
              >
                {line.split(" ").map((word, wordPosition) => (
                  <span
                    key={`${word}-${wordPosition}`}
                    className={cn(
                      "transition-colors duration-150",
                      lineIndex >= 0 &&
                        wordPosition === wordIndex &&
                        style.activeClassName,
                    )}
                    style={
                      wordPosition === wordIndex
                        ? { color: highlight }
                        : undefined
                    }
                  >
                    {word}
                    {wordPosition < line.split(" ").length - 1 ? " " : ""}
                  </span>
                ))}
              </p>
            ))}
          </div>

          {/* Barra de reproducción */}
          <div className="absolute inset-x-0 bottom-0 z-20 px-3 pb-2">
            <div className="mb-2 flex items-center gap-2 text-[8px] text-white/70">
              <span className="font-mono tabular-nums">0:12</span>
              <div className="h-0.5 flex-1 overflow-hidden rounded-full bg-white/20">
                <div className="h-full w-1/3 rounded-full bg-white/80" />
              </div>
              <span className="font-mono tabular-nums">0:38</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="rounded bg-black/50 px-1.5 py-0.5 text-[8px] uppercase tracking-wide text-white/70">
                {reframeMode === "face"
                  ? "Cara centrada"
                  : reframeMode === "center"
                    ? "Centrado"
                    : reframeMode === "blur"
                      ? "Fondo desenfocado"
                      : "Sin recorte"}
              </span>
              <button
                type="button"
                aria-label={playing ? "Pausar previsualización" : "Reproducir previsualización"}
                onClick={() => {
                  const next = !playing;
                  setPlaying(next);
                  onTogglePlay?.(next);
                }}
                className="flex size-7 items-center justify-center rounded-full bg-white/15 text-white backdrop-blur transition hover:bg-white/25"
              >
                {playing ? (
                  <Pause className="size-3.5" aria-hidden="true" />
                ) : (
                  <Play className="size-3.5 translate-x-px" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="w-full max-w-[286px] text-center">
        <p className="flex items-center justify-center gap-2 text-sm font-medium text-zinc-200">
          <span
            className="size-2.5 rounded-full"
            style={{ backgroundColor: style.swatch }}
            aria-hidden="true"
          />
          {displayName}
        </p>
        <p className="mt-0.5 text-xs text-zinc-500">
          {presetData?.description ?? style.subtitle}
        </p>
        <p className="mt-2 font-mono text-[11px] tabular-nums text-zinc-500">
          1080 × 1920 · ≤30fps · H.264 VideoToolbox
        </p>
      </div>
    </div>
  );
}
