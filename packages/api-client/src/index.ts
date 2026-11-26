/**
 * Cliente TypeScript tipado de la API de WinClip
 * Generado automáticamente con `pnpm gen:api` desde el esquema OpenAPI de la API
 */

export { createApiClient, getApiBaseUrl, ApiError } from "./client";
export { uploadProjectWithProgress, createProjectFormData, type UploadProgress, type UploadOptions, type CreateProjectResponse, ApiError as UploadApiError } from "./upload";

// Re-exportar tipos generados para consumo externo
export type {
  paths,
  components,
  operations,
  webhooks,
} from "./schema";

// Tipos de conveniencia para uso común (usando los tipos generados)
import type { paths as Paths, components as Components } from "./schema.js";

export type ProjectSummary = Paths["/api/projects"]["get"]["responses"]["200"]["content"]["application/json"];
export type ProjectDetail = Paths["/api/projects/{project_id}"]["get"]["responses"]["200"]["content"]["application/json"];
export type Clip = Paths["/api/projects/{project_id}/clips"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type Job = Paths["/api/jobs/{job_id}"]["get"]["responses"]["200"]["content"]["application/json"];
export type SubtitlePreset = Paths["/api/presets"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type HealthResponse = Paths["/api/health"]["get"]["responses"]["200"]["content"]["application/json"];

// Tipo para eventos SSE (streaming text/event-stream, no JSON)
export interface SseEvent {
  id?: string;
  event?: string;
  data: string;
  retry?: number;
}