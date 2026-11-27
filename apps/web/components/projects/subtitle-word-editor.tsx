"use client";

import { useState } from "react";
import { AlertCircle, Loader2, RotateCcw, Subtitles } from "lucide-react";
import type { ClipWordOut } from "@winclip/api-client";

import { Button } from "@/components/ui/button";
import { formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";

const MAX_WORD_LENGTH = 64;

export interface SubtitleWordEditorProps {
  words: ClipWordOut[];
  overrides: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  isLoading?: boolean;
  errorMessage?: string | null;
  disabled?: boolean;
}

export function SubtitleWordEditor({
  words,
  overrides,
  onChange,
  isLoading = false,
  errorMessage = null,
  disabled = false,
}: SubtitleWordEditorProps) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const editedCount = words.filter((word) => {
    const value = overrides[word.key];
    return typeof value === "string" && value.trim().length > 0 && value.trim() !== word.original;
  }).length;

  const startEditing = (word: ClipWordOut) => {
    if (disabled) return;
    setEditingKey(word.key);
    setDraft(overrides[word.key] ?? word.text);
  };

  const commitEditing = (word: ClipWordOut) => {
    const cleaned = draft.trim().slice(0, MAX_WORD_LENGTH);
    const next = { ...overrides };
    if (!cleaned || cleaned === word.original) {
      delete next[word.key];
    } else {
      next[word.key] = cleaned;
    }
    onChange(next);
    setEditingKey(null);
  };

  const cancelEditing = () => {
    setEditingKey(null);
    setDraft("");
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-[#0D0D10] py-12 text-xs text-zinc-400">
        <Loader2 className="size-4 animate-spin text-amber-400" aria-hidden="true" />
        Cargando palabras del clip…
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-xl border border-rose-500/35 bg-rose-500/10 p-4 text-xs text-rose-300"
      >
        <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{errorMessage}</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-[#0D0D10] px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <Subtitles className="size-3.5 text-amber-400" aria-hidden="true" />
          <span className="font-mono tabular-nums text-zinc-300">
            {words.length} {words.length === 1 ? "palabra" : "palabras"}
          </span>
          {editedCount > 0 ? (
            <span className="rounded bg-amber-400/15 px-1.5 py-0.5 font-mono text-[11px] font-medium tabular-nums text-amber-300">
              {editedCount} {editedCount === 1 ? "editada" : "editadas"}
            </span>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setEditingKey(null);
            onChange({});
          }}
          disabled={disabled || Object.keys(overrides).length === 0}
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
          Restablecer texto
        </Button>
      </div>

      {words.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-[#0D0D10] px-4 py-8 text-center text-xs text-zinc-500">
          No hay palabras transcritas en este tramo del vídeo.
        </div>
      ) : (
        <div
          className="max-h-[250px] overflow-y-auto rounded-xl border border-white/10 bg-[#0D0D10] p-3"
          aria-label="Palabras de subtítulos del clip"
        >
          <div className="flex flex-wrap gap-1.5">
            {words.map((word) => {
              const overrideValue = overrides[word.key];
              const effective =
                typeof overrideValue === "string" && overrideValue.trim().length > 0
                  ? overrideValue.trim()
                  : word.original;
              const isEdited = effective !== word.original;
              const isEditing = editingKey === word.key;

              if (isEditing) {
                return (
                  <input
                    key={word.key}
                    type="text"
                    value={draft}
                    maxLength={MAX_WORD_LENGTH}
                    autoFocus
                    aria-label={`Editar palabra ${word.original}`}
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={() => commitEditing(word)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        commitEditing(word);
                      } else if (event.key === "Escape") {
                        event.preventDefault();
                        cancelEditing();
                      }
                    }}
                    className="h-7 min-w-[72px] rounded-md border border-amber-400/70 bg-[#18181B] px-2 text-xs text-zinc-100 outline-none focus:ring-1 focus:ring-amber-400"
                    style={{
                      width: `${Math.max(6, Math.min(24, draft.length + 2))}ch`,
                    }}
                  />
                );
              }

              return (
                <button
                  key={word.key}
                  type="button"
                  disabled={disabled}
                  onClick={() => startEditing(word)}
                  data-edited={isEdited ? "true" : "false"}
                  title={
                    isEdited
                      ? `Original: "${word.original}" (${formatTimestamp(word.start)}–${formatTimestamp(word.end)})`
                      : `${formatTimestamp(word.start)}–${formatTimestamp(word.end)} · Haz clic para corregir`
                  }
                  className={cn(
                    "inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md border px-2 text-xs transition-colors",
                    isEdited
                      ? "border-amber-400/50 bg-amber-400/15 font-medium text-amber-200 hover:bg-amber-400/25"
                      : "border-white/10 bg-[#141418] text-zinc-200 hover:border-white/20 hover:bg-[#18181B]",
                    disabled && "cursor-not-allowed opacity-60",
                  )}
                >
                  <span>{effective}</span>
                  {isEdited ? (
                    <span
                      className="size-1.5 rounded-full bg-amber-400"
                      aria-label="Palabra editada"
                    />
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-[11px] text-zinc-500">
        Haz clic en cualquier palabra para corregir errores de transcripción sin
        alterar sus marcas temporales ni el archivo original del proyecto.
      </p>
    </div>
  );
}
