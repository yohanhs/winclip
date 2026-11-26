"use client";

import { useMemo, useState, useEffect } from "react";
import { Play, Pause } from "lucide-react";
import { Badge } from "@/components/ui/badge";

type CaptionPreset = "bold_yellow" | "hormozi" | "clean_white" | "mrbeast";

interface SubtitlePresetPreviewProps {
  preset: CaptionPreset;
  presetData: {
    id: string;
    name: string;
    description: string;
    font: string;
    highlight_color: string;
    primary_color: string;
    box_bg_color?: string | null;
  };
  isPlaying?: boolean;
  onPlayToggle?: (playing: boolean) => void;
  className?: string;
}

// Preset styling metadata
const PRESET_STYLES: Record<
  CaptionPreset,
  { name: string; subtitle: string; swatch: string }
> = {
  bold_yellow: {
    name: "Bold Yellow",
    subtitle: "Karaoke amarillo eléctrico · trazo negro",
    swatch: "#FFD600",
  },
  hormozi: {
    name: "Hormozi",
    subtitle: "Alto impacto · palabra activa verde/ámbar",
    swatch: "#10B981",
  },
  clean_white: {
    name: "Clean White",
    subtitle: "Editorial minimalista · pastilla translúcida",
    swatch: "#F4F4F5",
  },
  mrbeast: {
    name: "MrBeast",
    subtitle: "Display condensado · rebote pop en acento",
    swatch: "#F59E0B",
  },
};

// Default lines for preview
const DEFAULT_EN_LINES = [
  ["CLOUD GPU", "BILLS ATE", "62% OF"],
  ["OUR REVENUE", "UNTIL WE", "MOVED"],
  ["RENDERING", "LOCALLY TO", "APPLE M1."],
];

const DEFAULT_ES_LINES = [
  ["EL ERROR", "QUE TE CUESTA", "$500 AL MES"],
  ["NO ES", "EL CAFÉ,", "ES TU"],
  ["PILOTO", "AUTOMÁTICO", "BANCARIO."],
];

export function SubtitlePresetPreview({
  preset,
  presetData,
  isPlaying = true,
  onPlayToggle,
  className = "",
}: SubtitlePresetPreviewProps) {
  const [tick, setTick] = useState(0);

  const meta = PRESET_STYLES[preset];
  const lines = DEFAULT_ES_LINES;

  // Animation effect
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setTick((prev) => prev + 1);
    }, 440);
    return () => clearInterval(interval);
  }, [isPlaying]);

  // Calculate current word being highlighted
  const totalWords = lines.flat().length;
  const currentWordGlobal = tick % totalWords;

  let activeLineIdx = 0;
  let activeWordIdx = 0;
  let cursor = 0;
  for (let i = 0; i < lines.length; i++) {
    const rowLen = lines[i]?.length ?? 0;
    if (currentWordGlobal < cursor + rowLen) {
      activeLineIdx = i;
      activeWordIdx = currentWordGlobal - cursor;
      break;
    }
    cursor += rowLen;
  }

  const currentLine = lines[activeLineIdx]!;

  // Calculate progress percentage for scrub bar
  const progressPct = ((tick % 24) / 23) * 100;

  // Render captions based on preset style
  const renderCaptions = () => {
    switch (preset) {
      case "bold_yellow":
        return (
          <div
            className={`flex flex-wrap justify-center gap-x-1.5 gap-y-0.5 leading-tight tracking-tight font-extrabold uppercase ${
              isPlaying ? "text-[19px]" : "text-[13px]"
            }`}
          >
            {currentLine.map((word, idx) => {
              const isActive = idx === activeWordIdx;
              return (
                <span
                  key={`${activeLineIdx}-${idx}`}
                  className={`inline-block transition-transform duration-150 ${
                    isActive
                      ? "text-[#FFD600] scale-[1.08] caption-stroke"
                      : "text-white/95 scale-100"
                  }`}
                >
                  {word}
                </span>
              );
            })}
          </div>
        );

      case "hormozi":
        return (
          <div
            className={`flex flex-wrap justify-center gap-x-1.5 gap-y-1 leading-none uppercase font-extrabold ${
              isPlaying ? "text-[22px]" : "text-[15px]"
            }`}
            style={{ fontFamily: "var(--font-display, 'Inter', sans-serif)" }}
          >
            {currentLine.map((word, idx) => {
              const isActive = idx === activeWordIdx;
              const isHighlightAlt = idx % 2 === 1;
              return (
                <span
                  key={`${activeLineIdx}-${idx}`}
                  className={`inline-block px-1.5 py-0.5 rounded-[3px] transition-transform duration-150 ${
                    isActive
                      ? isHighlightAlt
                        ? "bg-[#10B981] text-zinc-950 scale-[1.08] -rotate-1"
                        : "bg-[#FFD600] text-zinc-950 scale-[1.08] rotate-1"
                      : "text-white"
                  }`}
                >
                  {word}
                </span>
              );
            })}
          </div>
        );

      case "clean_white":
        return (
          <div
            className={`inline-flex flex-wrap justify-center gap-x-1.5 px-2.5 py-1.5 rounded-md bg-black/72 backdrop-blur-sm border border-white/10 leading-snug font-semibold ${
              isPlaying ? "text-[14px]" : "text-[11px]"
            }`}
          >
            {currentLine.map((word, idx) => {
              const isActive = idx === activeWordIdx;
              return (
                <span
                  key={`${activeLineIdx}-${idx}`}
                  className={`transition-colors duration-150 ${
                    isActive ? "text-white font-bold" : "text-zinc-400"
                  }`}
                >
                  {word.charAt(0) + word.slice(1).toLowerCase()}
                </span>
              );
            })}
          </div>
        );

      case "mrbeast":
      default:
        return (
          <div
            className={`flex flex-wrap justify-center gap-x-1.5 gap-y-0.5 leading-none uppercase italic font-extrabold ${
              isPlaying ? "text-[24px]" : "text-[16px]"
            }`}
            style={{ fontFamily: "var(--font-display, 'Inter', sans-serif)" }}
          >
            {currentLine.map((word, idx) => {
              const isActive = idx === activeWordIdx;
              return (
                <span
                  key={`${activeLineIdx}-${idx}`}
                  className={`inline-block transition-transform duration-150 ${
                    isActive
                      ? "text-[#F59E0B] scale-[1.15] -translate-y-0.5"
                      : "text-white"
                  }`}
                >
                  {word}
                </span>
              );
            })}
          </div>
        );
    }
  };

  return (
    <div
      className={`relative overflow-hidden bg-zinc-950 rounded-lg ${className}`}
    >
      {/* Background placeholder - in real app would be video thumbnail */}
      <img
        src="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=1080&h=1920&fit=crop"
        alt="Video preview"
        className="absolute inset-0 w-full h-full object-cover opacity-30"
      />

      {/* Gradient overlay for subtitle legibility */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/15 to-black/35 pointer-events-none" />

      {/* Subtitles positioned in safe zone */}
      <div className="absolute inset-x-3 flex justify-center text-center pointer-events-none bottom-12">
        {renderCaptions()}
      </div>

      {/* Playback scrub bar */}
      {isPlaying && (
        <div className="absolute inset-x-0 bottom-0 h-[2.5px] bg-white/15 pointer-events-none">
          <div
            className="h-full bg-amber-400 transition-all duration-300"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      )}

      {/* Play/pause overlay when not playing */}
      {!isPlaying && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-9 h-9 rounded-full bg-black/60 border border-white/15 backdrop-blur-sm flex items-center justify-center text-white/90">
            <Play className="w-4 h-4 ml-0.5 fill-current" />
          </div>
        </div>
      )}
    </div>
  );
}