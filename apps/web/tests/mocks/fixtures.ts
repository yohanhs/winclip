import type {
  ClipOut,
  JobSummary,
  ProjectOut,
  SubtitlePreset,
} from "@winclip/api-client";

export function makeJob(overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    id: "job-1",
    type: "pipeline",
    status: "running",
    progress: 0,
    stage: "ingest",
    error: null,
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-01T10:00:00Z",
    ...overrides,
  };
}

export function makeProject(overrides: Partial<ProjectOut> = {}): ProjectOut {
  return {
    id: "proj-1",
    workspace_id: "ws-1",
    campaign_id: null,
    source_type: "url",
    source_url: "https://example.com/video",
    title: "Proyecto de prueba",
    status: "ready",
    requested_clips: 5,
    language: "es",
    duration: 600,
    subtitle_preset: "bold-yellow",
    reframe_mode: "face",
    clips_count: 5,
    thumb_url: "/api/clips/clip-1/thumb",
    active_job: null,
    latest_job: makeJob({ status: "done", progress: 100, stage: "done" }),
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-01T10:05:00Z",
    ...overrides,
  };
}

export function makeClip(overrides: Partial<ClipOut> = {}): ClipOut {
  return {
    id: "clip-1",
    project_id: "proj-1",
    status: "rendered",
    title: "El error que te cuesta 500 al mes",
    description: "Descripción del clip",
    hashtags: ["shorts", "finanzas"],
    score: 92,
    hook: "Nadie te cuenta esto",
    start_sec: 10,
    end_sec: 30,
    duration: 20,
    video_url: "/api/clips/clip-1/file",
    thumb_url: "/api/clips/clip-1/thumb",
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-01T10:05:00Z",
    ...overrides,
  };
}

export function makePreset(overrides: Partial<SubtitlePreset> = {}): SubtitlePreset {
  return {
    id: "bold-yellow",
    name: "Bold Yellow",
    description: "Karaoke blanco con palabra activa amarilla",
    font: "Montserrat ExtraBold",
    fallback_font: "Montserrat ExtraBold",
    font_size: 76,
    uppercase: false,
    primary_color: "#FFFFFF",
    highlight_color: "#FFD600",
    outline_color: "#000000",
    outline_width: 6,
    shadow_color: "#000000",
    shadow_depth: 3,
    highlight_scale_pct: 112,
    y_pct: 0.66,
    margin_x: 90,
    max_lines: 2,
    max_chars_per_line: 38,
    max_words_per_cue: 7,
    max_pause_sec: 0.65,
    box_bg_color: null,
    ...overrides,
  };
}
