/**
 * Helper para subida de archivos con progreso real usando XMLHttpRequest
 * Permite reportar progreso 0-100 en subidas multipart grandes
 */

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface UploadOptions {
  baseUrl: string;
  formData: FormData;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}

/**
 * Respuesta del endpoint createProject
 */
export interface CreateProjectResponse {
  project: {
    id: string;
    workspace_id: string;
    campaign_id: string | null;
    source_type: "url" | "file";
    source_url: string | null;
    title: string;
    status: string;
    requested_clips: number | null;
    language: string;
    duration: number | null;
    created_at: string;
  };
  job: {
    id: string;
    project_id: string;
    type: string;
    payload: Record<string, unknown>;
    status: string;
    progress: number;
    stage: string | null;
    error: string | null;
    attempts: number;
    created_at: string;
    updated_at: string;
    started_at: string | null;
    completed_at: string | null;
  };
}

/**
 * Sube un proyecto con progreso real usando XMLHttpRequest
 * Necesario porque fetch no expone eventos de progreso de subida en navegadores
 *
 * @param options Opciones de subida
 * @returns Respuesta tipada del endpoint createProject
 */
export async function uploadProjectWithProgress(
  options: UploadOptions
): Promise<CreateProjectResponse> {
  const { baseUrl, formData, onProgress, signal } = options;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    // Configurar progreso de subida
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percentage: Math.round((event.loaded / event.total) * 100),
        });
      }
    });

    // Manejar respuesta
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          resolve(response);
        } catch (e) {
          reject(new Error("Respuesta inválida del servidor"));
        }
      } else {
        try {
          const errorData = JSON.parse(xhr.responseText);
          reject(new ApiError(xhr.status, errorData));
        } catch {
          reject(new ApiError(xhr.status, { message: xhr.statusText }));
        }
      }
    });

    // Manejar errores de red
    xhr.addEventListener("error", () => {
      reject(new Error("Error de red durante la subida"));
    });

    // Manejar abort
    xhr.addEventListener("abort", () => {
      reject(new Error("Subida cancelada"));
    });

    // Manejar timeout
    xhr.addEventListener("timeout", () => {
      reject(new Error("Tiempo de espera agotado"));
    });

    // Soporte para AbortSignal
    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort());
    }

    // Abrir conexión y enviar
    xhr.open("POST", `${baseUrl}/api/projects`);
    xhr.timeout = 0; // Sin timeout para archivos grandes
    xhr.send(formData);
  });
}

/**
 * Error tipado de la API para uploads
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly data: unknown
  ) {
    super(`API Error ${status}: ${JSON.stringify(data)}`);
    this.name = "ApiError";
  }
}

/**
 * Crea el FormData para crear un proyecto
 */
export function createProjectFormData(data: {
  source_url?: string;
  file?: File;
  requested_clips: number | "max";
  language: "auto" | "es" | "en";
  subtitle_preset: string;
  reframe_mode: "face" | "center" | "blur" | "passthrough";
  campaign_id?: string;
}): FormData {
  const formData = new FormData();

  if (data.source_url) {
    formData.append("source_url", data.source_url);
  }
  if (data.file) {
    formData.append("file", data.file);
  }
  formData.append("requested_clips", data.requested_clips.toString());
  formData.append("language", data.language);
  formData.append("subtitle_preset", data.subtitle_preset);
  formData.append("reframe_mode", data.reframe_mode);
  if (data.campaign_id) {
    formData.append("campaign_id", data.campaign_id);
  }

  return formData;
}