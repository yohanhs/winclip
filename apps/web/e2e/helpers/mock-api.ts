import type { Page } from "@playwright/test";
import type {
  AccountsOAuthConfigOut,
  BrowserLoginStartRequest,
  CampaignCreate,
  CampaignOut,
  CampaignParseOut,
  CampaignTemplateOut,
  CampaignUpdate,
  ClipOut,
  ClipUpdate,
  HealthResponse,
  JobOut,
  PreviewMetaRequest,
  ProjectOut,
  PublicationOut,
  PublicationsCreateRequest,
  SocialAccountOut,
  SocialAccountUpdate,
  SubtitlePreset,
  TokenImportRequest,
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

export const DEFAULT_CAMPAIGN_TEMPLATES: CampaignTemplateOut[] = [
  {
    id: "podcast-entrevistas-es",
    title: "Podcast y Entrevistas (ES)",
    description: "Clips dinámicos en español con ganchos rápidos.",
    language: "es",
    rules: {
      name: "Podcast & Entrevistas ES",
      language: "es",
      min_duration: 25,
      max_duration: 65,
      max_clips: 10,
      priority_topics: ["anécdotas"],
      banned_topics: ["patrocinadores"],
      banned_words: ["garantizado"],
      required_keywords: ["podcast"],
      tone: "directo y cercano",
      hook_max_seconds: 3,
      cta_text: "Episodio completo en el canal",
      hashtags: ["#podcast", "#shorts"],
      subtitle_preset: "bold-yellow",
      watermark_path: null,
      target_platforms: ["youtube", "tiktok"],
      extra_instructions: "Cierra ideas completas.",
    },
  },
  {
    id: "creator-clipping-bounty-en",
    title: "Creator Clipping Bounty (EN)",
    description: "High-retention creator clips in English.",
    language: "en",
    rules: {
      name: "Creator Clipping Bounty EN",
      language: "en",
      min_duration: 18,
      max_duration: 58,
      max_clips: 12,
      priority_topics: ["viral moments"],
      banned_topics: ["gambling"],
      banned_words: ["scam"],
      required_keywords: ["creator"],
      tone: "punchy and fast",
      hook_max_seconds: 3,
      cta_text: "Watch full episode",
      hashtags: ["#shorts", "#creator"],
      subtitle_preset: "mrbeast",
      watermark_path: null,
      target_platforms: ["youtube", "tiktok", "instagram"],
      extra_instructions: "Open with tension.",
    },
  },
];

export function createSampleCampaign(
  overrides: Partial<CampaignOut> = {},
): CampaignOut {
  return {
    id: "camp-e2e-1",
    workspace_id: "ws-default",
    name: "Finanzas Educativo ES",
    rules: {
      name: "Finanzas Educativo ES",
      language: "es",
      min_duration: 20,
      max_duration: 55,
      max_clips: 7,
      priority_topics: ["ahorro", "inversión"],
      banned_topics: ["cripto"],
      banned_words: ["garantizado"],
      required_keywords: ["inversión"],
      tone: "educativo",
      hook_max_seconds: 3,
      cta_text: "Suscríbete al canal",
      hashtags: ["#finanzas", "#shorts"],
      subtitle_preset: "hormozi",
      watermark_path: null,
      target_platforms: ["youtube", "tiktok"],
      extra_instructions: "Sin relleno.",
    },
    source_text: "Brief original",
    projects_count: 1,
    created_at: "2026-11-26T09:00:00Z",
    updated_at: "2026-11-26T09:30:00Z",
    ...overrides,
  };
}

export function createSampleAccount(
  overrides: Partial<SocialAccountOut> = {},
): SocialAccountOut {
  return {
    id: "acc-e2e-1",
    workspace_id: "ws-default",
    platform: "youtube",
    display_name: "HookVault",
    handle: "@hookvault",
    alias: "Canal Principal",
    avatar_url: null,
    auth_method: "api",
    status: "connected",
    is_default: true,
    capabilities: { direct_post: true },
    external_account_id: "UC_E2E_1",
    token_expires_at: "2027-01-01T00:00:00Z",
    last_check_at: "2026-11-26T10:00:00Z",
    last_error: null,
    created_at: "2026-11-26T09:00:00Z",
    updated_at: "2026-11-26T10:00:00Z",
    ...overrides,
  };
}

export function createSamplePublication(
  overrides: Partial<PublicationOut> = {},
): PublicationOut {
  return {
    id: "pub-e2e-1",
    workspace_id: "ws-default",
    clip_id: "clip-e2e-1",
    project_id: "proj-e2e-1",
    project_title: "Podcast Finanzas Personales",
    clip_title: "El error que te cuesta 500 al mes",
    clip_thumb_url: "/api/clips/clip-e2e-1/thumb",
    account_id: "acc-e2e-1",
    account_platform: "youtube",
    account_auth_method: "api",
    account_display_name: "HookVault",
    account_handle: "@hookvault",
    account_alias: "Canal Principal",
    job_id: "job-pub-e2e-1",
    job_progress: 0,
    job_stage: "queued",
    status: "scheduled",
    delivery_mode: "direct",
    scheduled_at: "2026-11-27T18:30:00Z",
    published_at: null,
    meta: {
      title: "El error que te cuesta 500 al mes #Shorts",
      description: "Descripción #Shorts",
      caption: "",
      hashtags: ["#Shorts"],
      scheduled_at: "2026-11-27T18:30:00Z",
      delivery_mode: "direct",
      language: "es",
      tags: ["Shorts"],
      category_id: "22",
      privacy_status: "public",
      pinned_comment: null,
      upload_thumbnail: true,
      privacy_level: "PUBLIC_TO_EVERYONE",
      disable_comment: false,
      disable_duet: false,
      disable_stitch: false,
      share_to_feed: true,
      thumb_offset_ms: null,
      publication_id: null,
      existing_external_id: null,
      existing_external_url: null,
    },
    external_id: null,
    external_url: null,
    error: null,
    error_code: null,
    warnings: [],
    has_screenshot: false,
    screenshot_url: null,
    attempts: 0,
    created_at: "2026-11-26T10:00:00Z",
    updated_at: "2026-11-26T10:00:00Z",
    ...overrides,
  };
}

export interface MockApiState {
  projects: ProjectOut[];
  clipsByProject: Record<string, ClipOut[]>;
  campaigns: CampaignOut[];
  accounts: SocialAccountOut[];
  publications: PublicationOut[];
  accountsOAuthConfig: AccountsOAuthConfigOut;
  browserLoginStatuses: Record<string, "waiting" | "connected" | "cancelled">;
  campaignTemplates: CampaignTemplateOut[];
  parseResponse: CampaignParseOut;
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
    campaign_name: null,
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
    rule_violations: [],
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
  initial?: Partial<
    Pick<
      MockApiState,
      | "projects"
      | "clipsByProject"
      | "campaigns"
      | "accounts"
      | "publications"
      | "failProjectsList"
    >
  >,
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
    campaigns: initial?.campaigns ?? [createSampleCampaign()],
    accounts: initial?.accounts ?? [],
    publications: initial?.publications ?? [],
    accountsOAuthConfig: {
      platforms: [
        { platform: "youtube", configured: true, missing: [] },
        {
          platform: "tiktok",
          configured: false,
          missing: ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
        },
        {
          platform: "instagram",
          configured: false,
          missing: ["META_APP_ID", "META_APP_SECRET"],
        },
      ],
    },
    browserLoginStatuses: {},
    campaignTemplates: DEFAULT_CAMPAIGN_TEMPLATES,
    parseResponse: {
      rules: {
        name: "Campaña desde Brief IA",
        language: "es",
        min_duration: 22,
        max_duration: 50,
        max_clips: 6,
        priority_topics: ["ahorro"],
        banned_topics: [],
        banned_words: ["garantizado"],
        required_keywords: ["inversión"],
        tone: "directo",
        hook_max_seconds: 3,
        cta_text: "Suscríbete hoy",
        hashtags: ["#finanzas", "#shorts"],
        subtitle_preset: "hormozi",
        watermark_path: null,
        target_platforms: ["youtube", "tiktok"],
        extra_instructions: null,
      },
      inferred_fields: ["tone", "subtitle_preset"],
      warnings: [],
      provider: "fake:gemini-flash",
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

    if (pathname === "/api/publications/quota" && method === "GET") {
      const ytCount = state.publications.filter(
        (p) =>
          p.account_platform === "youtube" &&
          p.account_auth_method === "api" &&
          p.status !== "cancelled" &&
          p.status !== "failed",
      ).length;
      await route.fulfill({
        json: {
          youtube_units_used: ytCount * 1600,
          youtube_units_limit: 10000,
          youtube_upload_cost: 1600,
          youtube_uploads_today: ytCount,
          accounts: state.accounts.map((a) => ({
            account_id: a.id,
            platform: a.platform,
            auth_method: a.auth_method,
            display_name: a.display_name,
            handle: a.handle,
            alias: a.alias ?? null,
            used_today: 0,
            daily_limit: a.auth_method === "playwright" ? 5 : 6,
            remaining_today: a.auth_method === "playwright" ? 5 : 6,
          })),
        },
      });
      return;
    }

    if (pathname === "/api/publications/preview-meta" && method === "POST") {
      const body = request.postDataJSON() as PreviewMetaRequest;
      const items = body.clip_ids.flatMap((clipId) => {
        const clip = Object.values(state.clipsByProject)
          .flat()
          .find((c) => c.id === clipId);
        return body.account_ids.map((accountId) => {
          const acc = state.accounts.find((a) => a.id === accountId);
          const platform = acc?.platform ?? "youtube";
          const authMethod = acc?.auth_method ?? "api";
          const deliveryMode =
            platform === "tiktok" &&
            authMethod === "api" &&
            !Boolean(acc?.capabilities?.direct_post)
              ? "inbox"
              : "direct";
          return {
            clip_id: clipId,
            account_id: accountId,
            platform,
            auth_method: authMethod,
            delivery_mode: deliveryMode,
            meta: {
              title: `${clip?.title ?? "Short"} #Shorts`.slice(0, 100),
              description: `${clip?.description ?? ""} #Shorts`.trim(),
              caption: `${clip?.title ?? ""} #shorts`.trim(),
              hashtags: clip?.hashtags ?? ["#Shorts"],
              scheduled_at: null,
              delivery_mode: deliveryMode,
              language: "es",
              tags: ["Shorts"],
              category_id: "22",
              privacy_status: "public",
              pinned_comment: null,
              upload_thumbnail: true,
              privacy_level: "PUBLIC_TO_EVERYONE",
              disable_comment: false,
              disable_duet: false,
              disable_stitch: false,
              share_to_feed: true,
              thumb_offset_ms: null,
              publication_id: null,
              existing_external_id: null,
              existing_external_url: null,
            },
            warnings: [],
          };
        });
      });
      await route.fulfill({
        json: {
          items,
          warnings: [],
          quota: {
            youtube_units_used: 0,
            youtube_units_limit: 10000,
            youtube_upload_cost: 1600,
            youtube_uploads_today: 0,
            accounts: [],
          },
        },
      });
      return;
    }

    if (pathname === "/api/publications" && method === "GET") {
      await route.fulfill({ json: state.publications });
      return;
    }

    if (pathname === "/api/publications" && method === "POST") {
      const body = request.postDataJSON() as PublicationsCreateRequest;
      const created: PublicationOut[] = body.items.map((item, idx) => {
        const clip = Object.values(state.clipsByProject)
          .flat()
          .find((c) => c.id === item.clip_id);
        const acc = state.accounts.find((a) => a.id === item.account_id);
        const proj = state.projects.find((p) => p.id === clip?.project_id);
        return createSamplePublication({
          id: `pub-e2e-${state.publications.length + idx + 1}`,
          clip_id: item.clip_id,
          project_id: clip?.project_id ?? "proj-e2e-1",
          project_title: proj?.title ?? "Proyecto",
          clip_title: clip?.title ?? "Clip",
          clip_thumb_url: clip?.thumb_url ?? null,
          account_id: item.account_id,
          account_platform: acc?.platform ?? "youtube",
          account_auth_method: acc?.auth_method ?? "api",
          account_display_name: acc?.display_name ?? "Cuenta",
          account_handle: acc?.handle ?? "@cuenta",
          account_alias: acc?.alias ?? null,
          status: "scheduled",
          delivery_mode: item.meta.delivery_mode ?? "direct",
          scheduled_at: item.scheduled_at ?? null,
          meta: item.meta,
        });
      });
      state.publications = [...created, ...state.publications];
      await route.fulfill({ status: 201, json: created });
      return;
    }

    const pubShotMatch = pathname.match(/^\/api\/publications\/([^/]+)\/screenshot$/);
    if (pubShotMatch && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        body: TINY_PNG,
      });
      return;
    }

    const pubRetryMatch = pathname.match(/^\/api\/publications\/([^/]+)\/retry$/);
    if (pubRetryMatch && method === "POST") {
      const pubId = pubRetryMatch[1]!;
      let updated: PublicationOut | undefined;
      state.publications = state.publications.map((p) => {
        if (p.id !== pubId) return p;
        updated = { ...p, status: "scheduled", error: null, error_code: null };
        return updated;
      });
      if (!updated) {
        await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
        return;
      }
      await route.fulfill({ json: updated });
      return;
    }

    const pubCancelMatch = pathname.match(/^\/api\/publications\/([^/]+)\/cancel$/);
    if (pubCancelMatch && method === "POST") {
      const pubId = pubCancelMatch[1]!;
      let updated: PublicationOut | undefined;
      state.publications = state.publications.map((p) => {
        if (p.id !== pubId) return p;
        updated = { ...p, status: "cancelled" };
        return updated;
      });
      if (!updated) {
        await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
        return;
      }
      await route.fulfill({ json: updated });
      return;
    }

    if (pathname === "/api/accounts" && method === "GET") {
      await route.fulfill({ json: state.accounts });
      return;
    }

    if (pathname === "/api/accounts/config" && method === "GET") {
      await route.fulfill({ json: state.accountsOAuthConfig });
      return;
    }

    if (pathname === "/api/accounts/import" && method === "POST") {
      const body = request.postDataJSON() as TokenImportRequest;
      const created = createSampleAccount({
        id: `acc-imp-${state.accounts.length + 1}`,
        platform: body.platform ?? "youtube",
        display_name: body.alias || "Cuenta Importada",
        alias: body.alias ?? null,
        handle: "@imported_channel",
        status: "connected",
        is_default: !state.accounts.some(
          (a) => a.platform === (body.platform ?? "youtube") && a.is_default,
        ),
      });
      state.accounts = [...state.accounts, created];
      await route.fulfill({ status: 201, json: [created] });
      return;
    }

    if (pathname === "/api/accounts/browser-login/start" && method === "POST") {
      const body = request.postDataJSON() as BrowserLoginStartRequest;
      const accId = body.account_id ?? `acc-pw-${state.accounts.length + 1}`;
      if (!body.account_id) {
        state.accounts = [
          ...state.accounts,
          createSampleAccount({
            id: accId,
            platform: body.platform,
            display_name: `${body.platform} (navegador)`,
            handle: "",
            alias: body.alias ?? null,
            auth_method: "playwright",
            status: "pending",
            is_default: !state.accounts.some(
              (a) => a.platform === body.platform && a.is_default,
            ),
          }),
        ];
      }
      state.browserLoginStatuses[accId] = "waiting";
      await route.fulfill({
        json: {
          account_id: accId,
          platform: body.platform,
          session_status: "waiting",
          error: null,
        },
      });
      return;
    }

    const accBrowserStatusMatch = pathname.match(
      /^\/api\/accounts\/([^/]+)\/browser-login\/status$/,
    );
    if (accBrowserStatusMatch && method === "GET") {
      const accId = accBrowserStatusMatch[1]!;
      const acc = state.accounts.find((a) => a.id === accId);
      await route.fulfill({
        json: {
          account_id: accId,
          platform: acc?.platform ?? "tiktok",
          session_status: state.browserLoginStatuses[accId] ?? "connected",
          error: null,
        },
      });
      return;
    }

    const accBrowserConfirmMatch = pathname.match(
      /^\/api\/accounts\/([^/]+)\/browser-login\/confirm$/,
    );
    if (accBrowserConfirmMatch && method === "POST") {
      const accId = accBrowserConfirmMatch[1]!;
      state.browserLoginStatuses[accId] = "connected";
      state.accounts = state.accounts.map((a) =>
        a.id === accId ? { ...a, status: "connected", last_error: null } : a,
      );
      const acc = state.accounts.find((a) => a.id === accId);
      await route.fulfill({
        json: {
          account_id: accId,
          platform: acc?.platform ?? "tiktok",
          session_status: "connected",
          error: null,
        },
      });
      return;
    }

    const accBrowserCancelMatch = pathname.match(
      /^\/api\/accounts\/([^/]+)\/browser-login\/cancel$/,
    );
    if (accBrowserCancelMatch && method === "POST") {
      const accId = accBrowserCancelMatch[1]!;
      state.browserLoginStatuses[accId] = "cancelled";
      const acc = state.accounts.find((a) => a.id === accId);
      await route.fulfill({
        json: {
          account_id: accId,
          platform: acc?.platform ?? "tiktok",
          session_status: "cancelled",
          error: null,
        },
      });
      return;
    }

    const accCheckMatch = pathname.match(/^\/api\/accounts\/([^/]+)\/check$/);
    if (accCheckMatch && method === "POST") {
      const accId = accCheckMatch[1]!;
      let updated: SocialAccountOut | undefined;
      state.accounts = state.accounts.map((a) => {
        if (a.id !== accId) return a;
        updated = {
          ...a,
          status: "connected",
          last_error: null,
          last_check_at: new Date().toISOString(),
        };
        return updated;
      });
      if (!updated) {
        await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
        return;
      }
      await route.fulfill({ json: updated });
      return;
    }

    const accMatch = pathname.match(/^\/api\/accounts\/([^/]+)$/);
    if (accMatch) {
      const accId = accMatch[1]!;
      if (method === "PATCH") {
        const body = request.postDataJSON() as SocialAccountUpdate;
        const target = state.accounts.find((a) => a.id === accId);
        if (!target) {
          await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
          return;
        }
        let updated: SocialAccountOut = target;
        state.accounts = state.accounts.map((a) => {
          if (a.id === accId) {
            updated = {
              ...a,
              alias: body.alias !== undefined ? body.alias : a.alias,
              is_default: body.is_default !== undefined ? Boolean(body.is_default) : a.is_default,
              updated_at: new Date().toISOString(),
            };
            return updated;
          }
          if (body.is_default === true && a.platform === target.platform) {
            return { ...a, is_default: false };
          }
          return a;
        });
        await route.fulfill({ json: updated });
        return;
      }
      if (method === "DELETE") {
        state.accounts = state.accounts.filter((a) => a.id !== accId);
        await route.fulfill({ status: 204 });
        return;
      }
    }

    if (pathname === "/api/campaigns" && method === "GET") {
      await route.fulfill({ json: state.campaigns });
      return;
    }

    if (pathname === "/api/campaigns/templates" && method === "GET") {
      await route.fulfill({ json: state.campaignTemplates });
      return;
    }

    if (pathname === "/api/campaigns/parse" && method === "POST") {
      await route.fulfill({ json: state.parseResponse });
      return;
    }

    if (pathname === "/api/campaigns/watermarks" && method === "POST") {
      await route.fulfill({
        status: 201,
        json: { watermark_path: "campaigns/watermarks/01e2ewm.png" },
      });
      return;
    }

    if (pathname.startsWith("/api/campaigns/watermarks/") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        body: TINY_PNG,
      });
      return;
    }

    if (pathname === "/api/campaigns" && method === "POST") {
      const body = request.postDataJSON() as CampaignCreate;
      const created: CampaignOut = {
        id: `camp-e2e-${state.campaigns.length + 1}`,
        workspace_id: "ws-default",
        name: body.name,
        rules: { ...body.rules, name: body.name },
        source_text: body.source_text ?? null,
        projects_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      state.campaigns = [created, ...state.campaigns];
      await route.fulfill({ status: 201, json: created });
      return;
    }

    const campDupMatch = pathname.match(/^\/api\/campaigns\/([^/]+)\/duplicate$/);
    if (campDupMatch && method === "POST") {
      const source = state.campaigns.find((c) => c.id === campDupMatch[1]);
      if (!source) {
        await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
        return;
      }
      const copy: CampaignOut = {
        ...source,
        id: `camp-copy-${state.campaigns.length + 1}`,
        name: `${source.name} (copia)`,
        rules: { ...source.rules, name: `${source.name} (copia)` },
        projects_count: 0,
        updated_at: new Date().toISOString(),
      };
      state.campaigns = [copy, ...state.campaigns];
      await route.fulfill({ status: 201, json: copy });
      return;
    }

    const campMatch = pathname.match(/^\/api\/campaigns\/([^/]+)$/);
    if (campMatch) {
      const campId = campMatch[1]!;
      if (method === "GET") {
        const found = state.campaigns.find((c) => c.id === campId);
        if (!found) {
          await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
          return;
        }
        await route.fulfill({ json: found });
        return;
      }
      if (method === "PATCH") {
        const body = request.postDataJSON() as CampaignUpdate;
        const found = state.campaigns.find((c) => c.id === campId);
        if (!found) {
          await route.fulfill({ status: 404, json: { detail: "No encontrada" } });
          return;
        }
        const nextName = body.name ?? found.name;
        const updated: CampaignOut = {
          ...found,
          name: nextName,
          rules: body.rules ? { ...body.rules, name: nextName } : found.rules,
          source_text:
            body.source_text !== undefined ? body.source_text : found.source_text,
          updated_at: new Date().toISOString(),
        };
        state.campaigns = state.campaigns.map((c) =>
          c.id === campId ? updated : c,
        );
        await route.fulfill({ json: updated });
        return;
      }
      if (method === "DELETE") {
        state.campaigns = state.campaigns.filter((c) => c.id !== campId);
        state.projects = state.projects.map((p) =>
          p.campaign_id === campId
            ? { ...p, campaign_id: null, campaign_name: null }
            : p,
        );
        await route.fulfill({ status: 204 });
        return;
      }
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
      let campaignId: string | null = null;

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
        campaignId =
          typeof parsed.campaign_id === "string" ? parsed.campaign_id : null;
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
      const matchedCampaign = campaignId
        ? state.campaigns.find((c) => c.id === campaignId) ?? null
        : null;
      const project = createSampleProject({
        id: newId,
        campaign_id: campaignId,
        campaign_name: matchedCampaign?.name ?? null,
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
