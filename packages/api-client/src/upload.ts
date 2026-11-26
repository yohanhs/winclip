/**
 * Subida de archivos con progreso real.
 *
 * `fetch` no expone eventos de progreso de subida en los navegadores, así que
 * los archivos grandes (varios GB) se envían con `XMLHttpRequest` tipado.
 */

import { ApiError } from "./errors";
import type { components } from "./schema";

export type CreateProjectResponse = components["schemas"]["ProjectCreated"];

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export type RequestedClips = number | "max";
export type ProjectLanguage = "auto" | "es" | "en";
export type ReframeMode = "face" | "center" | "blur" | "passthrough";

export interface ProjectFormDataInput {
  source_url?: string;
  file?: File;
  requested_clips: RequestedClips;
  language: ProjectLanguage;
  subtitle_preset: string;
  reframe_mode: ReframeMode;
  campaign_id?: string;
  title?: string;
}

function isProjectCreated(value: unknown): value is CreateProjectResponse {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as { project?: unknown; job?: unknown };
  return (
    typeof candidate.project === "object" &&
    candidate.project !== null &&
    typeof candidate.job === "object" &&
    candidate.job !== null
  );
}

/**
 * Sube un proyecto multipart con progreso 0..100 y soporte de `AbortSignal`.
 */
export function uploadProjectWithProgress(
  baseUrl: string,
  formData: FormData,
  onProgress?: (progress: UploadProgress) => void,
  signal?: AbortSignal
): Promise<CreateProjectResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      onProgress?.({
        loaded: event.loaded,
        total: event.total,
        percentage: Math.round((event.loaded / event.total) * 100),
      });
    });

    xhr.addEventListener("load", () => {
      let payload: unknown = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && isProjectCreated(payload)) {
        resolve(payload);
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        reject(new Error("Respuesta inválida del servidor"));
        return;
      }
      reject(new ApiError(xhr.status, payload));
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Error de red durante la subida"));
    });

    xhr.addEventListener("abort", () => {
      reject(new DOMException("Subida cancelada", "AbortError"));
    });

    xhr.addEventListener("timeout", () => {
      reject(new Error("Tiempo de espera agotado"));
    });

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException("Subida cancelada", "AbortError"));
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.open("POST", `${baseUrl}/api/projects`);
    xhr.timeout = 0;
    xhr.send(formData);
  });
}

/** Construye el `FormData` que espera `POST /api/projects`. */
export function createProjectFormData(data: ProjectFormDataInput): FormData {
  const formData = new FormData();

  if (data.file) {
    formData.append("file", data.file);
    formData.append("source_type", "file");
  }
  if (data.source_url) {
    formData.append("source_url", data.source_url);
    formData.append("source_type", "url");
  }
  if (data.title) formData.append("title", data.title);
  formData.append("requested_clips", String(data.requested_clips));
  formData.append("language", data.language);
  formData.append("subtitle_preset", data.subtitle_preset);
  formData.append("reframe_mode", data.reframe_mode);
  if (data.campaign_id) formData.append("campaign_id", data.campaign_id);

  return formData;
}
