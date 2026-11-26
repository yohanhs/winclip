"use client";

import { useMemo } from "react";

import { clamp, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface MiniTimelineProps {
  duration: number;
  start: number;
  end: number;
  bars?: number;
  className?: string;
}

/** Waveform decorativa con la región seleccionada resaltada. */
export function MiniTimeline({
  duration,
  start,
  end,
  bars = 64,
  className,
}: MiniTimelineProps) {
  const heights = useMemo(
    () =>
      Array.from({ length: bars }, (_, index) => {
        const wave =
          Math.sin(index * 0.55) * 0.35 +
          Math.sin(index * 1.7 + 0.8) * 0.25 +
          Math.sin(index * 0.13) * 0.2;
        return clamp(28 + Math.abs(wave) * 60, 12, 100);
      }),
    [bars],
  );

  const total = Math.max(duration, 0.001);
  const startPct = clamp((start / total) * 100, 0, 100);
  const endPct = clamp((end / total) * 100, 0, 100);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="relative h-20 overflow-hidden rounded-lg border border-white/10 bg-[#0d0d10] px-2">
        <div className="flex h-full items-center gap-[2px]">
          {heights.map((height, index) => {
            const position = (index / heights.length) * 100;
            const inside = position >= startPct && position <= endPct;
            return (
              <span
                key={index}
                className={cn(
                  "flex-1 rounded-full transition-colors",
                  inside ? "bg-amber-400/80" : "bg-zinc-700/60",
                )}
                style={{ height: `${height}%` }}
              />
            );
          })}
        </div>

        <div
          className="pointer-events-none absolute inset-y-0 border-l-2 border-amber-300"
          style={{ left: `${startPct}%` }}
        >
          <span className="absolute -top-0.5 left-1 rounded bg-amber-400 px-1 font-mono text-[9px] font-semibold tabular-nums text-black">
            IN
          </span>
        </div>
        <div
          className="pointer-events-none absolute inset-y-0 border-l-2 border-amber-300"
          style={{ left: `${endPct}%` }}
        >
          <span className="absolute -top-0.5 left-1 rounded bg-amber-400 px-1 font-mono text-[9px] font-semibold tabular-nums text-black">
            OUT
          </span>
        </div>
      </div>

      <div className="flex justify-between font-mono text-[10px] tabular-nums text-zinc-500">
        <span>{formatTimestamp(start)}</span>
        <span className="text-amber-400">
          {formatTimestamp(Math.max(0, end - start))} seleccionados
        </span>
        <span>{formatTimestamp(duration)}</span>
      </div>
    </div>
  );
}
