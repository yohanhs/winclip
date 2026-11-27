import type { Page } from "@playwright/test";
import type {
  ClipOut,
  ClipUpdate,
  HealthResponse,
  JobOut,
  ProjectOut,
  SubtitlePreset,
} from "@winclip/api-client";

/** PNG 1x1 válido para evitar peticiones rotas en miniaturas. */
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

export const DEFAULT_PRESETS: SubtitlePreset[] = [
  {
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
  },
  {
    id: "hormozi",
    name: "Hormozi",
    description: "Alto impacto con palabra activa verde",
    font: "Montserrat Black",
    fallback_font: "Montserrat ExtraBold",
    font_size: 82,
    uppercase: true,
    primary_color: "#FFFFFF",
    highlight_color: "#10B981",
    outline_color: "#000000",
    outline_width: 7,
    shadow_color: "#000000",
    shadow_depth: 4,
    highlight_scale_pct: 115,
    y_pct: 0.64,
    margin_x: 80,
    max_lines: 2,
    max_chars_per_line: 30,
    max_words_per_cue: 5,
    max_pause_sec: 0.55,
    box_bg_color: null,
  },
  {
    id: "clean-white",
    name: "Clean White",
    description: "Caja limpia minimalista",
    font: "Inter Bold",
    fallback_font: "Inter",
    font_size: 64,
    uppercase: false,
    primary_color: "#FFFFFF",
    highlight_color: "#38BDF8",
    outline_color: "#000000",
    outline_width: 2,
    shadow_color: "#000000",
    shadow_depth: 2,
    highlight_scale_pct: 104,
    y_pct: 0.72,
    margin_x: 100,
    max_lines: 2,
    max_chars_per_line: 42,
    max_words_per_cue: 8,
    max_pause_sec: 0.7,
    box_bg_color: "rgba(0,0,0,0.6)",
  },
  {
    id: "mrbeast",
    name: "MrBeast",
    description: "Display condensado de alto impacto",
    font: "Anton",
    fallback_font: "Bebas Neue",
    font_size: 92,
    uppercase: true,
    primary_color: "#FFFFFF",
    highlight_color: "#FACC15",
    outline_color: "#000000",
    outline_width: 8,
    shadow_color: "#000000",
    shadow_depth: 5,
    highlight_scale_pct: 120,
    y_pct: 0.62,
    margin_x: 70,
    max_lines: 2,
    max_chars_per_line: 26,
    max_words_per_cue: 4,
    max_pause_sec: 0.5,
    box_bg_color: null,
  },
];

export const DEFAULT_HEALTH: HealthResponse = {
  app: "WinClip",
  version: "0.1.0",
  checks: [
    { name: "ffmpeg", status: "ok", detail: "ffmpeg-full 9.1 (libass ok)" },
    { name: "whisper", status: "ok", detail: "mlx-whisper cache listo" },
    { name: "storage", status: "ok", detail: "./storage escribible" },
  ],
};

export interface MockApiState {
  projects: ProjectOut[];
  clipsByProject: Record<string, ClipOut[]>;
  presets: SubtitlePreset[];
  health: HealthResponse;
  failProjectsList: boolean;
  createdPayloads: Array<{
    contentType: string;
    body: unknown;
  }>;
  patchPayloads: Array<{ clipId: string; body: ClipUpdate }>;
  rerenderCalls: string[];
  cancelledJobIds: string[];
  deletedProjectIds: string[];
}

export function createSampleProject(
  overrides: Partial<ProjectOut> = {},
): ProjectOut {
  return {
    id: "proj-e2e-1",
    workspace_id: "ws-default",
    campaign_id: null,
    source_type: "url",
    source_url: "https://www.youtube.com/watch?v=demo123",
    title: "Podcast Finanzas Personales",
    status: "ready",
    requested_clips: 5,
    language: "es",
    duration: 1800,
    subtitle_preset: "bold-yellow",
    reframe_mode: "face",
    clips_count: 2,
    thumb_url: "/api/clips/clip-e2e-1/thumb",
    active_job: null,
    latest_job: {
      id: "job-e2e-1",
      type: "pipeline",
      status: "done",
      progress: 100,
      stage: "done",
      error: null,
      created_at: "2026-11-26T10:00:00Z",
      updated_at: "2026-11-26T10:05:00Z",
    },
    created_at: "2026-11-26T10:00:00Z",
    updated_at: "2026-11-26T10:05:00Z",
    ...overrides,
  };
}

export function createSampleClip(overrides: Partial<ClipOut> = {}): ClipOut {
  return {
    id: "clip-e2e-1",
    project_id: "proj-e2e-1",
    status: "rendered",
    title: "El error que te cuesta 500 al mes",
    description: "Cómo evitar las fugas silenciosas en tu cuenta bancaria.",
    hashtags: ["#finanzas", "#ahorro", "#shorts"],
    score: 94,
    hook: "No es el café, es tu piloto automático bancario.",
    start_sec: 120,
    end_sec: 165,
    duration: 45,
    video_url: "/api/clips/clip-e2e-1/file",
    thumb_url: "/api/clips/clip-e2e-1/thumb",
    created_at: "2026-11-26T10:04:00Z",
    updated_at: "2026-11-26T10:05:00Z",
    ...overrides,
  };
}

/**
 * Instala un EventSource determinista en la página para `/api/events` y
 * registra rutas Playwright para todos los endpoints `/api/**`.
 */
export async function setupMockApi(
  page: Page,
  initial?: Partial<Pick<MockApiState, "projects" | "clipsByProject" | "failProjectsList">>,
): Promise<MockApiState> {
  const state: MockApiState = {
    projects: initial?.projects ?? [createSampleProject()],
    clipsByProject: initial?.clipsByProject ?? {
      "proj-e2e-1": [
        createSampleClip(),
        createSampleClip({
          id: "clip-e2e-2",
          title: "Regla del 50/30/20 en 40 segundos",
          score: 86,
          hook: "Si no automatizas tu ahorro el día 1, desaparece.",
          start_sec: 410,
          end_sec: 450,
          duration: 40,
          video_url: "/api/clips/clip-e2e-2/file",
          thumb_url: "/api/clips/clip-e2e-2/thumb",
        }),
      ],
    },
    presets: DEFAULT_PRESETS,
    health: DEFAULT_HEALTH,
    failProjectsList: initial?.failProjectsList ?? false,
    createdPayloads: [],
    patchPayloads: [],
    rerenderCalls: [],
    cancelledJobIds: [],
    deletedProjectIds: [],
  };

  await page.addInitScript(() => {
    interface ControlledSource {
      url: string;
      listeners: Map<string, Set<EventListener>>;
      onopen: ((ev: Event) => void) | null;
      onerror: ((ev: Event) => void) | null;
      readyState: number;
      close: () => void;
    }

    const sources: ControlledSource[] = [];

    class DeterministicEventSource {
      readonly url: string;
      readonly withCredentials = false;
      readonly CONNECTING = 0;
      readonly OPEN = 1;
      readonly CLOSED = 2;
      readyState = 0;
      onopen: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      readonly listeners = new Map<string, Set<EventListener>>();

      constructor(url: string | URL) {
        this.url = String(url);
        sources.push(this);
        queueMicrotask(() => {
          if (this.readyState === 2) return;
          this.readyState = 1;
          this.onopen?.(new Event("open"));
        });
      }

      addEventListener(type: string, listener: EventListener) {
        const set = this.listeners.get(type) ?? new Set<EventListener>();
        set.add(listener);
        this.listeners.set(type, set);
      }

      removeEventListener(type: string, listener: EventListener) {
        this.listeners.get(type)?.delete(listener);
      }

      dispatchEvent(): boolean {
        return true;
      }

      close() {
        this.readyState = 2;
      }
    }

    (window as unknown as Record<string, unknown>).EventSource =
      DeterministicEventSource;
    (window as unknown as Record<string, unknown>).__winclipSseEmit = (
      eventName: string,
      payload: unknown,
    ) => {
      const data = JSON.stringify(payload);
      for (const source of sources) {
        if (source.readyState === 2) continue;
        const ev = new MessageEvent(eventName, { data });
        source.listeners.get(eventName)?.forEach((listener) => listener(ev));
      }
    };
  });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const method = request.method();

    if (pathname === "/api/health" && method === "GET") {
      await route.fulfill({ json: state.health });
      return;
    }

    if (pathname === "/api/presets" && method === "GET") {
      await route.fulfill({ json: state.presets });
      return;
    }

    if (pathname === "/api/projects" && method === "GET") {
      if (state.failProjectsList) {
        await route.fulfill({
          status: 503,
          json: { detail: "Backend temporalmente no disponible" },
        });
        return;
      }
      await route.fulfill({ json: state.projects });
      return;
    }

    if (pathname === "/api/projects" && method === "POST") {
      const contentType = request.headers()["content-type"] ?? "";
      let createdTitle = "Nuevo proyecto E2E";
      let language = "auto";
      let preset = "bold-yellow";
      let reframe = "face";
      let sourceType = "url";
      let sourceUrl: string | null = null;
      let requestedClips: number | null = 5;

      if (contentType.includes("application/json")) {
        const parsed = request.postDataJSON() as Record<string, unknown>;
        state.createdPayloads.push({ contentType, body: parsed });
        sourceUrl =
          typeof parsed.source_url === "string" ? parsed.source_url : null;
        createdTitle =
          typeof parsed.title === "string" && parsed.title.trim()
            ? parsed.title
            : sourceUrl ?? createdTitle;
        language =
          typeof parsed.language === "string" ? parsed.language : "auto";
        preset =
          typeof parsed.subtitle_preset === "string"
            ? parsed.subtitle_preset
            : "bold-yellow";
        reframe =
          typeof parsed.reframe_mode === "string"
            ? parsed.reframe_mode
            : "face";
        requestedClips =
          typeof parsed.requested_clips === "number"
            ? parsed.requested_clips
            : null;
      } else {
        const raw = request.postData() ?? "";
        state.createdPayloads.push({ contentType, body: raw });
        sourceType = "file";
        createdTitle = "archivo-subido.mp4";
      }

      const newId = `proj-created-${state.projects.length + 1}`;
      const job: JobOut = {
        id: `job-created-${state.projects.length + 1}`,
        project_id: newId,
        type: "pipeline",
        status: "queued",
        progress: 0,
        stage: "queued",
        error: null,
        attempts: 0,
        max_attempts: 3,
        created_at: "2026-11-26T11:00:00Z",
        updated_at: "2026-11-26T11:00:00Z",
      };
      const project = createSampleProject({
        id: newId,
        title: createdTitle,
        source_type: sourceType,
        source_url: sourceUrl,
        status: "queued",
        language,
        subtitle_preset: preset,
        reframe_mode: reframe,
        requested_clips: requestedClips,
        clips_count: 0,
        thumb_url: null,
        active_job: {
          id: job.id,
          type: job.type,
          status: job.status,
          progress: job.progress,
          stage: job.stage,
          error: null,
          created_at: job.created_at,
          updated_at: job.updated_at,
        },
        latest_job: {
          id: job.id,
          type: job.type,
          status: job.status,
          progress: job.progress,
          stage: job.stage,
          error: null,
          created_at: job.created_at,
          updated_at: job.updated_at,
        },
      });
      state.projects = [project, ...state.projects];
      state.clipsByProject[newId] = [];

      await route.fulfill({ status: 201, json: { project, job } });
      return;
    }

    const projectClipsMatch = pathname.match(/^\/api\/projects\/([^/]+)\/clips$/);
    if (projectClipsMatch && method === "GET") {
      const projectId = projectClipsMatch[1]!;
      await route.fulfill({ json: state.clipsByProject[projectId] ?? [] });
      return;
    }

    const projectMatch = pathname.match(/^\/api\/projects\/([^/]+)$/);
    if (projectMatch) {
      const projectId = projectMatch[1]!;
      if (method === "GET") {
        const found = state.projects.find((item) => item.id === projectId);
        if (!found) {
          await route.fulfill({ status: 404, json: { detail: "No encontrado" } });
          return;
        }
        await route.fulfill({ json: found });
        return;
      }
      if (method === "DELETE") {
        state.deletedProjectIds.push(projectId);
        state.projects = state.projects.filter((item) => item.id !== projectId);
        delete state.clipsByProject[projectId];
        await route.fulfill({ status: 204 });
        return;
      }
    }

    const clipThumbMatch = pathname.match(/^\/api\/clips\/([^/]+)\/thumb$/);
    if (clipThumbMatch && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        body: TINY_PNG,
      });
      return;
    }

    const clipFileMatch = pathname.match(/^\/api\/clips\/([^/]+)\/file$/);
    if (clipFileMatch && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "video/mp4",
        body: Buffer.from("fake-mp4-bytes"),
      });
      return;
    }

    const clipRerenderMatch = pathname.match(/^\/api\/clips\/([^/]+)\/rerender$/);
    if (clipRerenderMatch && method === "POST") {
      const clipId = clipRerenderMatch[1]!;
      state.rerenderCalls.push(clipId);
      for (const clips of Object.values(state.clipsByProject)) {
        const target = clips.find((clip) => clip.id === clipId);
        if (target) target.status = "rendering";
      }
      const job: JobOut = {
        id: `job-rerender-${clipId}`,
        project_id: "proj-e2e-1",
        type: "render",
        status: "queued",
        progress: 0,
        stage: "render",
        error: null,
        attempts: 0,
        max_attempts: 3,
        created_at: "2026-11-26T12:00:00Z",
        updated_at: "2026-11-26T12:00:00Z",
      };
      await route.fulfill({ status: 202, json: job });
      return;
    }

    const clipMatch = pathname.match(/^\/api\/clips\/([^/]+)$/);
    if (clipMatch) {
      const clipId = clipMatch[1]!;
      if (method === "PATCH") {
        const body = request.postDataJSON() as ClipUpdate;
        state.patchPayloads.push({ clipId, body });
        for (const clips of Object.values(state.clipsByProject)) {
          const target = clips.find((clip) => clip.id === clipId);
          if (target) {
            if (body.title != null) target.title = body.title;
            if (body.description != null) target.description = body.description;
            if (body.hashtags != null) target.hashtags = body.hashtags;
            if (body.start_sec != null) target.start_sec = body.start_sec;
            if (body.end_sec != null) target.end_sec = body.end_sec;
            target.duration = Math.max(0, target.end_sec - target.start_sec);
            target.updated_at = new Date().toISOString();
            await route.fulfill({ json: target });
            return;
          }
        }
        await route.fulfill({ status: 404, json: { detail: "Clip no encontrado" } });
        return;
      }
      if (method === "DELETE") {
        for (const [pid, clips] of Object.entries(state.clipsByProject)) {
          state.clipsByProject[pid] = clips.filter((clip) => clip.id !== clipId);
        }
        await route.fulfill({ status: 204 });
        return;
      }
    }

    const jobCancelMatch = pathname.match(/^\/api\/jobs\/([^/]+)\/cancel$/);
    if (jobCancelMatch && method === "POST") {
      const jobId = jobCancelMatch[1]!;
      state.cancelledJobIds.push(jobId);
      for (const project of state.projects) {
        if (project.active_job?.id === jobId) {
          project.status = "cancelled";
          project.latest_job = {
            ...project.active_job,
            status: "cancelled",
            stage: "cancelled",
          };
          project.active_job = null;
        }
      }
      await route.fulfill({
        json: {
          id: jobId,
          project_id: "proj-e2e-1",
          type: "pipeline",
          status: "cancelled",
          progress: 40,
          stage: "cancelled",
          error: null,
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-11-26T10:00:00Z",
          updated_at: "2026-11-26T10:03:00Z",
        } satisfies JobOut,
      });
      return;
    }

    await route.continue();
  });

  return state;
}

export async function emitSseEvent(
  page: Page,
  eventName: string,
  payload: unknown,
): Promise<void> {
  await page.evaluate(
    ([name, data]) => {
      const emitter = (
        window as unknown as {
          __winclipSseEmit?: (event: string, body: unknown) => void;
        }
      ).__winclipSseEmit;
      emitter?.(name as string, data);
    },
    [eventName, payload] as const,
  );
}
