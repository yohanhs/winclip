"use client";

import { CheckSquare, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface SelectionActionBarProps {
  selectedCount: number;
  total: number;
  onSelectAll: () => void;
  onClear: () => void;
}

export function SelectionActionBar({
  selectedCount,
  total,
  onSelectAll,
  onClear,
}: SelectionActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div
      role="region"
      aria-label="Acciones de selección"
      className="fixed bottom-5 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-[#111114]/95 px-3 py-2 shadow-2xl shadow-black/60 backdrop-blur"
    >
      <span className="whitespace-nowrap px-2 text-xs text-zinc-300">
        <span className="font-mono font-semibold tabular-nums text-amber-400">
          {selectedCount}
        </span>{" "}
        de {total} seleccionados
      </span>

      {selectedCount < total ? (
        <Button type="button" variant="ghost" size="sm" onClick={onSelectAll}>
          <CheckSquare aria-hidden="true" />
          Todos
        </Button>
      ) : null}

      <Button type="button" variant="ghost" size="sm" onClick={onClear}>
        <X aria-hidden="true" />
        Limpiar
      </Button>

      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={0} className="inline-flex">
              <Button
                type="button"
                size="sm"
                disabled
                aria-disabled="true"
                className="pointer-events-none"
              >
                <Send aria-hidden="true" />
                Publicar en redes →
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            La publicación multi-red llega en el change 8, cuando existan cuentas
            conectadas y publishers.
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
