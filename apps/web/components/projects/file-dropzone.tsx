"use client";

import { useCallback, useState, useRef, useEffect } from "react";
import { FileVideo, Upload, X, AlertCircle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

interface FileDropzoneProps {
  accept?: string;
  maxSizeMB?: number;
  onFileSelected?: (file: File, previewUrl: string) => void;
  onUploadStart?: (file: File) => void;
  onProgress?: (loaded: number, total: number) => void;
  onUploadComplete?: (file: File, previewUrl: string) => void;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
}

const DEFAULT_ACCEPT = "video/*";
const DEFAULT_MAX_SIZE_MB = 4000; // 4GB in MB

export function FileDropzone({
  accept = DEFAULT_ACCEPT,
  maxSizeMB = DEFAULT_MAX_SIZE_MB,
  onFileSelected,
  onUploadStart,
  onProgress,
  onUploadComplete,
  disabled = false,
  className = "",
  placeholder = "Arrastra un archivo de video aquí o haz clic para seleccionar",
}: FileDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [progress, setProgress] = useState<number>(0);
  const [error, setError] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const maxSizeBytes = maxSizeMB * 1024 * 1024;

  // Clean up object URL on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const validateFile = (file: File): string | null => {
    // Check file type
    const acceptedTypes = accept.split(",").map((t) => t.trim());
    const isAccepted = acceptedTypes.some((type) => {
      if (type === "*/*") return true;
      if (type.endsWith("/*")) {
        const prefix = type.replace("/*", "");
        return file.type.startsWith(prefix);
      }
      return file.type === type || file.name.toLowerCase().endsWith(type.replace("video/", ""));
    });

    if (!isAccepted) {
      return `Tipo de archivo no admitido. Usa: ${accept}`;
    }

    // Check file size
    if (file.size > maxSizeBytes) {
      const sizeMB = Math.round(file.size / (1024 * 1024));
      return `Archivo demasiado grande: ${sizeMB}MB. Máximo admisible: ${maxSizeMB}MB.`;
    }

    return null;
  };

  const handleFile = useCallback(
    (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }

      setError("");
      setSelectedFile(file);

      // Create preview URL
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);

      // Notify parent
      onFileSelected?.(file, url);
    },
    [accept, maxSizeMB, onFileSelected, validateFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);

      if (disabled) return;

      const file = e.dataTransfer.files?.[0];
      if (file) {
        handleFile(file);
      }
    },
    [disabled, handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) {
      setDragOver(true);
    }
  }, [disabled]);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleSelectFile = useCallback(() => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [disabled]);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
      // Reset input value so same file can be selected again if needed
      e.target.value = "";
    },
    [handleFile]
  );

  const cancelUpload = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setUploading(false);
    setProgress(0);
  }, []);

  const clearFile = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl("");
    setProgress(0);
    setError("");
    setUploading(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [previewUrl]);

  // Calculate visual preview dimensions (16:9 aspect ratio)
  const previewWidth = 320;
  const previewHeight = 180;

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleSelectFile}
        className={`
          relative border-2 border-dashed rounded-lg p-6 text-center transition-all cursor-pointer
          ${disabled
            ? "border-white/[0.1] bg-[#09090B]/50 cursor-not-allowed"
            : dragOver
            ? "border-amber-400 bg-amber-400/[0.05] cursor-pointer"
            : "border-white/[0.15] hover:border-white/[0.28] bg-[#09090B] hover:bg-[#111114]"
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          onChange={handleFileInputChange}
          className="hidden"
          disabled={disabled}
        />

        <div className="flex flex-col items-center justify-center gap-2.5">
          <div className="w-12 h-12 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center">
            <Upload className="w-6 h-6 text-zinc-400" />
          </div>
          <p className="text-[13px] font-medium text-zinc-200">
            {placeholder}
          </p>
          <p className="text-[12px] text-zinc-500">
            Formatos admitidos: MP4, MOV, MKV, AVI • Tamaño máximo: {maxSizeMB}MB
          </p>
        </div>
      </div>

      {/* Selected file preview */}
      {selectedFile && !uploading && (
        <div className="flex items-center gap-3 p-3 rounded-md bg-[#09090B] border border-white/[0.08]">
          <div className="relative w-16 aspect-video rounded overflow-hidden bg-zinc-900 shrink-0">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt={selectedFile.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <FileVideo className="w-6 h-6 text-zinc-500" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-medium text-zinc-100 truncate">
              {selectedFile.name}
            </p>
            <p className="text-[11px] text-zinc-400 font-mono">
              {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              clearFile();
            }}
            disabled={disabled}
            className="h-7 w-7 p-0"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Upload progress */}
      {uploading && selectedFile && (
        <div className="flex items-center gap-3 p-3 rounded-md bg-[#09090B] border border-white/[0.08]">
          <div className="w-16 aspect-video rounded overflow-hidden bg-zinc-900 shrink-0 flex items-center justify-center">
            <FileVideo className="w-5 h-5 text-zinc-500" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[12px] font-medium text-zinc-100">
                Subiendo...
              </span>
              <span className="text-[12px] font-mono text-zinc-400">
                {progress}%
              </span>
            </div>
            <Progress value={progress} className="h-1.5" />
            <div className="flex gap-2 mt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={cancelUpload}
                disabled={disabled}
              >
                Cancelar
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="flex items-start gap-2 p-3 rounded-md bg-rose-900/20 border border-rose-500/30">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-rose-200">{error}</p>
        </div>
      )}
    </div>
  );
}