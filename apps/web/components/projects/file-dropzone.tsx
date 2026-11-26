"use client";

import { useRef, useState } from "react";
import { AlertCircle, FileVideo, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export interface FileDropzoneProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
  onCancelUpload?: () => void;
  progress?: number;
  uploading?: boolean;
  disabled?: boolean;
  accept?: string;
  maxSizeMB?: number;
  className?: string;
}

const DEFAULT_ACCEPT = "video/*";
const DEFAULT_MAX_SIZE_MB = 4000;

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function FileDropzone({
  file,
  onFileChange,
  onCancelUpload,
  progress = 0,
  uploading = false,
  disabled = false,
  accept = DEFAULT_ACCEPT,
  maxSizeMB = DEFAULT_MAX_SIZE_MB,
  className,
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validate = (candidate: File): boolean => {
    if (!candidate.type.startsWith("video/")) {
      setError("El archivo debe ser un vídeo (mp4, mov, mkv…).");
      return false;
    }
    if (candidate.size > maxSizeMB * 1024 * 1024) {
      setError(`El archivo supera el límite de ${maxSizeMB} MB.`);
      return false;
    }
    setError(null);
    return true;
  };

  const handleFiles = (files: FileList | null) => {
    const candidate = files?.[0];
    if (!candidate) return;
    if (!validate(candidate)) return;
    onFileChange(candidate);
  };

  if (file) {
    return (
      <div className={cn("rounded-xl border border-white/10 bg-[#111114] p-4", className)}>
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400">
            <FileVideo className="size-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-zinc-100">{file.name}</p>
            <p className="text-xs text-zinc-500">
              {formatBytes(file.size)} · {uploading ? "Subiendo…" : "Listo para subir"}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Quitar archivo"
            disabled={disabled || uploading}
            onClick={() => {
              onFileChange(null);
              setError(null);
            }}
          >
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

        {uploading ? (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between font-mono text-xs tabular-nums text-zinc-400">
              <span>Subiendo archivo</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} className="h-1.5" />
            {onCancelUpload ? (
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onCancelUpload}
                  className="h-7 px-2 text-xs text-rose-400 hover:bg-rose-500/10 hover:text-rose-300"
                >
                  <X className="size-3.5" aria-hidden="true" />
                  Cancelar subida
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={className}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        aria-label="Seleccionar archivo de vídeo"
        disabled={disabled}
        onChange={(event) => handleFiles(event.target.files)}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) handleFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center transition-colors",
          dragging
            ? "border-amber-500/60 bg-amber-500/5"
            : "border-white/15 bg-[#0d0d10] hover:border-white/25 hover:bg-[#111114]",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <span className="flex size-11 items-center justify-center rounded-full bg-white/5 text-zinc-400">
          <Upload className="size-5" aria-hidden="true" />
        </span>
        <span className="text-sm font-medium text-zinc-200">
          Arrastra un archivo de video aquí o haz clic para seleccionar
        </span>
        <span className="text-xs text-zinc-500">
          MP4, MOV o MKV · hasta {maxSizeMB} MB
        </span>
      </button>

      {error ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-rose-400">
          <AlertCircle className="size-3.5" aria-hidden="true" />
          {error}
        </p>
      ) : null}
    </div>
  );
}
