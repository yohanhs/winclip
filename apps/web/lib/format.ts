/** Utilidades de formato compartidas por la UI. */

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "—";
  }
  return formatTimestamp(seconds);
}

/** `mm:ss` o `h:mm:ss` para duraciones y marcas de tiempo. */
export function formatTimestamp(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

/** Fecha corta en español (`26 nov, 18:30`). */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STAGE_LABELS: Record<string, string> = {
  ingest: "Descarga",
  transcribe: "Transcripción",
  select: "Selección",
  render: "Render",
  done: "Completado",
  failed: "Error",
  retry: "Reintentando",
  queued: "En cola",
  cancelled: "Cancelado",
  canceled: "Cancelado",
};

/** Etiqueta humana de la etapa del pipeline. */
export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "En cola";
  return STAGE_LABELS[stage] ?? stage;
}

const STATUS_LABELS: Record<string, string> = {
  queued: "En cola",
  processing: "Procesando",
  ready: "Listo",
  failed: "Error",
  cancelled: "Cancelado",
  canceled: "Cancelado",
  rendered: "Listo",
  rendering: "Renderizando",
  pending: "Pendiente",
};

/** Etiqueta humana del estado de proyecto o clip. */
export function statusLabel(status: string | null | undefined): string {
  if (!status) return "Desconocido";
  return STATUS_LABELS[status] ?? status;
}

/** Rango de progreso global (0–100) que ocupa cada etapa del pipeline. */
export const PIPELINE_STAGES = [
  { id: "ingest", label: "Descarga", from: 0, to: 25 },
  { id: "transcribe", label: "Transcripción", from: 25, to: 60 },
  { id: "select", label: "Selección", from: 60, to: 70 },
  { id: "render", label: "Render", from: 70, to: 100 },
] as const;

export type PipelineStageId = (typeof PIPELINE_STAGES)[number]["id"];

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
