import { http, HttpResponse } from "msw";
import type { components } from "@winclip/api-client";

// Tipos exportados para uso en tests
export type { components };

// Fixtures tipados para proyectos
export const mockProject: components["schemas"]["ProjectOut"] = {
  id: "proj-test-1",
  workspace_id: "ws-1",
  campaign_id: null,
  source_type: "url",
  source_url: "https://example.com/video.mp4",
  title: "Video de Prueba",
  status: "ready",
  requested_clips: 5,
  language: "es",
  duration: 60,
  subtitle_preset: "default",
  reframe_mode: "face",
  clips_count: 5,
  thumb_url: "/thumbs/proj-test-1.jpg",
  active_job: null,
  latest_job: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

export const mockProjectWithJob: components["schemas"]["ProjectOut"] = {
  ...mockProject,
  id: "proj-job-1",
  active_job: {
    id: "job-123",
    type: "download",
    status: "running",
    progress: 45,
    stage: "Downloading",
    error: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
};

// Fixtures tipados para clips
export const mockClip: components["schemas"]["ClipOut"] = {
  id: "clip-1",
  project_id: "proj-test-1",
  status: "ready",
  title: "Clip de prueba",
  description: "Descripción del clip",
  hashtags: ["#test", "#clip"],
  score: 0.95,
  hook: "¿Sabías que...? This changes everything!",
  start_sec: 0,
  end_sec: 60,
  duration: 15,
  video_url: "/clips/clip-1.mp4",
  thumb_url: "/clips/clip-1-thumb.jpg",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

// Fixtures tipados para jobs (JobOut)
export const mockJobProgress: components["schemas"]["JobOut"] = {
  id: "job-progress-1",
  project_id: "proj-test-1",
  type: "transcription",
  status: "running",
  progress: 65,
  stage: "Transcribing",
  error: null,
  attempts: 1,
  max_attempts: 3,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

export const mockJobDone: components["schemas"]["JobOut"] = {
  id: "job-done-1",
  project_id: "proj-test-1",
  type: "render",
  status: "done",
  progress: 100,
  stage: "Complete",
  error: null,
  attempts: 1,
  max_attempts: 3,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

export const mockJobFailed: components["schemas"]["JobOut"] = {
  id: "job-failed-1",
  project_id: "proj-test-1",
  type: "download",
  status: "failed",
  progress: 0,
  stage: "Failed",
  error: "Network timeout",
  attempts: 3,
  max_attempts: 3,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

// Presets fixtures
export const mockPresets: components["schemas"]["SubtitlePresetOut"][] = [
  {
    id: "default",
    name: "Default",
    description: "Subtitle style default",
    font: "Inter",
    fallback_font: "Arial",
    font_size: 24,
    uppercase: false,
    primary_color: "#FFFFFF",
    highlight_color: "#FFFF00",
    outline_color: "#000000",
    outline_width: 2,
    shadow_color: "#00000000",
    shadow_depth: 0,
    highlight_scale_pct: 100,
    y_pct: 85,
    margin_x: 20,
    max_lines: 2,
    max_chars_per_line: 40,
    max_words_per_cue: 8,
    max_pause_sec: 2,
    box_bg_color: null,
  },
];

// MSW Handlers for MSW v2
export const mswHandlers = [
  // Health check - real GET /api/health
  http.get("/api/health", () => {
    return HttpResponse.json({
      app: "winclip",
      version: "0.1.0",
      checks: [
        { name: "api", status: "ok", detail: "OK" },
        { name: "storage", status: "ok", detail: "Disco disponible" },
        { name: "transcription", status: "ok", detail: "Servicio online" },
      ],
    });
  }),

  // List projects
  http.get("/api/projects", () => {
    return HttpResponse.json([mockProject]);
  }),

  // Get project by ID
  http.get("/api/projects/:project_id", ({ params }) => {
    const { project_id } = params;
    if (project_id === "proj-job-1") {
      return HttpResponse.json(mockProjectWithJob);
    }
    return HttpResponse.json(mockProject);
  }),

  // Get clips for project
  http.get("/api/projects/:project_id/clips", () => {
    return HttpResponse.json([mockClip]);
  }),

  // Get job by ID
  http.get("/api/jobs/:job_id", ({ params }) => {
    const { job_id } = params;
    if (job_id === "job-progress-1") {
      return HttpResponse.json(mockJobProgress);
    }
    if (job_id === "job-done-1") {
      return HttpResponse.json(mockJobDone);
    }
    if (job_id === "job-failed-1") {
      return HttpResponse.json(mockJobFailed);
    }
    return HttpResponse.json(mockJobProgress);
  }),

  // Get presets
  http.get("/api/presets", () => {
    return HttpResponse.json(mockPresets);
  }),
];