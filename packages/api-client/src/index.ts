/**
 * Cliente TypeScript tipado de la API de WinClip.
 * Los tipos se regeneran con `pnpm gen:api` desde el esquema OpenAPI.
 */

export { createApiClient, getApiBaseUrl, ApiError } from "./client";
export {
  uploadProjectWithProgress,
  createProjectFormData,
  type UploadProgress,
  type CreateProjectResponse,
  type ProjectFormDataInput,
  type ProjectLanguage,
  type ReframeMode,
  type RequestedClips,
} from "./upload";

export type { paths, components, operations, webhooks } from "./schema";

import type { paths as Paths, components as Components } from "./schema";

export type ProjectSummary = Paths["/api/projects"]["get"]["responses"]["200"]["content"]["application/json"];
export type ProjectDetail = Paths["/api/projects/{project_id}"]["get"]["responses"]["200"]["content"]["application/json"];
export type Clip = Paths["/api/projects/{project_id}/clips"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type Job = Paths["/api/jobs/{job_id}"]["get"]["responses"]["200"]["content"]["application/json"];
export type SubtitlePreset = Paths["/api/presets"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type HealthResponse = Paths["/api/health"]["get"]["responses"]["200"]["content"]["application/json"];

export type Project = Components["schemas"]["ProjectOut"];
export type ProjectOut = Components["schemas"]["ProjectOut"];
export type ProjectCreated = Components["schemas"]["ProjectCreated"];
export type ClipOut = Components["schemas"]["ClipOut"];
export type JobOut = Components["schemas"]["JobOut"];
export type JobSummary = Components["schemas"]["JobSummary"];
export type HealthCheck = Components["schemas"]["CheckOut"];
export type ClipUpdate = Components["schemas"]["ClipUpdate"];

/** Evento SSE tal y como lo entrega `GET /api/events`. */
export interface SseEvent {
  id?: string;
  event?: string;
  data: string;
  retry?: number;
}

/** Payload de los eventos SSE documentados en `docs/api.md`. */
export interface SseJobProgress {
  job_id: string;
  project_id: string | null;
  type: string;
  status: string;
  progress: number;
  stage: string;
}

export interface SseJobDone extends SseJobProgress {
  status: "done";
  progress: 100;
  stage: "done";
}

export interface SseJobFailed {
  job_id: string;
  project_id: string | null;
  type: string;
  status: "failed";
  stage: string;
  error?: string | null;
}

export interface SseClipReady {
  project_id: string;
  job_id: string;
  clip_id: string;
  status: "rendered";
  thumb_url?: string | null;
  video_url?: string | null;
}
