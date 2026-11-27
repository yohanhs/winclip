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
export type RuleViolation = Components["schemas"]["RuleViolation"];
export type CampaignRules = Components["schemas"]["CampaignRules"];
export type CampaignOut = Components["schemas"]["CampaignOut"];
export type CampaignCreate = Components["schemas"]["CampaignCreate"];
export type CampaignUpdate = Components["schemas"]["CampaignUpdate"];
export type CampaignTemplateOut = Components["schemas"]["CampaignTemplateOut"];
export type CampaignParseRequest = Components["schemas"]["CampaignParseRequest"];
export type CampaignParseOut = Components["schemas"]["CampaignParseOut"];
export type WatermarkUploadOut = Components["schemas"]["WatermarkUploadOut"];
export type SocialAccountOut = Components["schemas"]["SocialAccountOut"];
export type SocialAccountUpdate = Components["schemas"]["SocialAccountUpdate"];
export type AccountsOAuthConfigOut = Components["schemas"]["AccountsOAuthConfigOut"];
export type PlatformOAuthConfigOut = Components["schemas"]["PlatformOAuthConfigOut"];
export type OAuthStartRequest = Components["schemas"]["OAuthStartRequest"];
export type OAuthStartOut = Components["schemas"]["OAuthStartOut"];
export type InstagramCandidateOut = Components["schemas"]["InstagramCandidateOut"];
export type InstagramSelectionOut = Components["schemas"]["InstagramSelectionOut"];
export type InstagramSelectRequest = Components["schemas"]["InstagramSelectRequest"];
export type BrowserLoginStartRequest = Components["schemas"]["BrowserLoginStartRequest"];
export type BrowserLoginOut = Components["schemas"]["BrowserLoginOut"];
export type TokenImportRequest = Components["schemas"]["TokenImportRequest"];
export type AccountPlatform = SocialAccountOut["platform"];
export type AccountAuthMethod = SocialAccountOut["auth_method"];
export type AccountStatus = SocialAccountOut["status"];

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
