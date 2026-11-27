"use client";

import { CheckSquare, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface SelectionActionBarProps {
  selectedCount: number;
  total: number;
  onSelectAll: () => void;
  onClear: () => void;
  onPublish: () => void;
  publishDisabled?: boolean;
}

export function SelectionActionBar({
  selectedCount,
  total,
  onSelectAll,
  onClear,
  onPublish,
  publishDisabled = false,
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

      <Button
        type="button"
        size="sm"
        disabled={publishDisabled}
        onClick={onPublish}
        className="bg-amber-400 font-semibold text-zinc-950 hover:bg-amber-300"
      >
        <Send aria-hidden="true" />
        Publicar en redes →
      </Button>
    </div>
  );
}
