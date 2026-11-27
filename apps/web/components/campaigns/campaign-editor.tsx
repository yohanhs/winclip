"use client";

import { useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  FileText,
  Image as ImageIcon,
  Loader2,
  Sliders,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";
import type {
  CampaignRules,
  SubtitlePreset,
} from "@winclip/api-client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { errorMessage, mediaUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

export type TargetPlatform = "youtube" | "tiktok" | "instagram";
export type RuleLanguage = "auto" | "es" | "en";

export interface CampaignDraft {
  name: string;
  rules: CampaignRules;
  sourceText: string;
}

export interface CampaignEditorProps {
  mode: "new" | "edit";
  draft: CampaignDraft;
  presets: SubtitlePreset[];
  inferredFields: string[];
  parseWarnings: string[];
  parseProvider: string | null;
  parseError: string | null;
  isParsing: boolean;
  isSaving: boolean;
  isUploadingWatermark: boolean;
  editorTab: "form" | "brief";
  onEditorTabChange: (tab: "form" | "brief") => void;
  onDraftChange: (next: CampaignDraft, editedField?: string) => void;
  onParseBrief: (briefText: string) => void;
  onUploadWatermark: (file: File) => void;
  onSave: () => void;
}

const SAMPLE_BRIEF_ES = `Campaña: Podcast Finanzas Q4
Idioma: español
Duración: entre 25 y 55 segundos, máximo 8 clips por episodio.
Hook: los primeros 3 segundos deben abrir con una cifra o pregunta directa.
Temas prioritarios: ahorro automático, interés compuesto, errores financieros comunes.
Temas prohibidos: criptomonedas especulativas, política.
Palabras prohibidas: garantizado, dinero fácil, sin riesgo.
Palabras clave obligatorias: inversión.
Tono: educativo, cercano y directo.
CTA: Guarda este clip y suscríbete al canal.
Hashtags: #finanzas #inversion #shorts
Subtítulos: hormozi
Plataformas: YouTube y TikTok.`;

const PLATFORM_OPTIONS: Array<{ id: TargetPlatform; label: string }> = [
  { id: "youtube", label: "YouTube" },
  { id: "tiktok", label: "TikTok" },
  { id: "instagram", label: "Instagram" },
];

function splitCommaList(raw: string): string[] {
  return raw
    .split(/[,\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitHashtags(raw: string): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const part of raw.split(/[\s,]+/)) {
    const cleaned = part.trim().replace(/^#+/, "").replace(/#/g, "");
    if (!cleaned) continue;
    const tag = `#${cleaned}`;
    const key = tag.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    tags.push(tag);
  }
  return tags;
}

function validateDraft(draft: CampaignDraft): string[] {
  const errors: string[] = [];
  const rules = draft.rules;
  const minDur = rules.min_duration ?? 20;
  const maxDur = rules.max_duration ?? 60;
  const hookMax = rules.hook_max_seconds ?? 3;

  if (!draft.name.trim()) {
    errors.push("El nombre de la campaña es obligatorio.");
  }
  if (minDur < 5 || minDur > 179) {
    errors.push("La duración mínima debe estar entre 5 y 179 segundos.");
  }
  if (maxDur < 6 || maxDur > 180) {
    errors.push("La duración máxima debe estar entre 6 y 180 segundos.");
  }
  if (minDur >= maxDur) {
    errors.push("La duración máxima debe ser mayor que la duración mínima.");
  }
  if (rules.max_clips != null && (rules.max_clips < 1 || rules.max_clips > 50)) {
    errors.push("El máximo de clips debe estar entre 1 y 50.");
  }
  if (hookMax < 1 || hookMax > 15) {
    errors.push("La ventana de hook debe estar entre 1 y 15 segundos.");
  } else if (hookMax > minDur) {
    errors.push("La ventana de hook no puede superar la duración mínima.");
  }
  return errors;
}

export function CampaignEditor({
  mode,
  draft,
  presets,
  inferredFields,
  parseWarnings,
  parseProvider,
  parseError,
  isParsing,
  isSaving,
  isUploadingWatermark,
  editorTab,
  onEditorTabChange,
  onDraftChange,
  onParseBrief,
  onUploadWatermark,
  onSave,
}: CampaignEditorProps) {
  const [showJson, setShowJson] = useState(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const rules = draft.rules;
  const validationErrors = useMemo(() => validateDraft(draft), [draft]);
  const canSave = validationErrors.length === 0 && !isSaving;

  const updateRules = (
    patch: Partial<CampaignRules>,
    editedField?: string,
    overrideName?: string,
  ) => {
    const nextName = overrideName !== undefined ? overrideName : draft.name;
    onDraftChange(
      {
        ...draft,
        name: nextName,
        rules: {
          ...draft.rules,
          ...patch,
          name: nextName || draft.rules.name || "default",
        },
      },
      editedField,
    );
  };

  const togglePlatform = (platform: TargetPlatform) => {
    const current = (rules.target_platforms ?? []) as TargetPlatform[];
    const next = current.includes(platform)
      ? current.filter((item) => item !== platform)
      : [...current, platform];
    updateRules({ target_platforms: next }, "target_platforms");
  };

  const jsonPreview = useMemo(() => {
    const normalized: CampaignRules = {
      ...rules,
      name: draft.name.trim() || rules.name || "default",
    };
    return JSON.stringify(normalized, null, 2);
  }, [draft.name, rules]);

  const isInferred = (field: string) => inferredFields.includes(field);

  const renderAIBadge = (field: string) =>
    isInferred(field) ? (
      <span
        data-testid={`ai-badge-${field}`}
        className="ml-1.5 rounded border border-violet-400/30 bg-violet-500/15 px-1.5 py-0.5 font-mono text-[10px] text-violet-300"
      >
        IA
      </span>
    ) : null;

  const watermarkPreviewUrl = useMemo(() => {
    const wm = rules.watermark_path;
    if (!wm) return null;
    const filename = wm.split("/").pop();
    if (!filename) return null;
    return mediaUrl(`/api/campaigns/watermarks/${filename}`);
  }, [rules.watermark_path]);

  const handleWatermarkFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    event.target.value = "";
    if (!selected) return;
    if (!["image/png", "image/webp"].includes(selected.type)) {
      toast.error("Formato no permitido", {
        description: "La marca de agua debe ser una imagen PNG o WebP.",
      });
      return;
    }
    if (selected.size > 5 * 1024 * 1024) {
      toast.error("Imagen demasiado grande", {
        description: "El tamaño máximo permitido para la marca de agua es 5 MB.",
      });
      return;
    }
    onUploadWatermark(selected);
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSave) {
      toast.error("Revisa los campos de la campaña", {
        description: validationErrors[0],
      });
      return;
    }
    onSave();
  };

  return (
    <section className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#111114] lg:col-span-8">
      {/* Header + Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] px-5 py-3.5">
        <div>
          <h2 className="text-[15px] font-semibold text-zinc-100">
            {mode === "new"
              ? "Nueva campaña de clipping"
              : draft.name || "Editar campaña"}
          </h2>
          <p className="text-[12px] text-zinc-400">
            Reglas aplicadas automáticamente a la selección IA, detección de
            alertas y renderizado 9:16.
          </p>
        </div>

        <div className="inline-flex rounded-md border border-white/[0.08] bg-[#09090B] p-0.5">
          <button
            type="button"
            onClick={() => onEditorTabChange("form")}
            className={cn(
              "inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[5px] px-3 py-1.5 text-[12px] font-medium transition-colors",
              editorTab === "form"
                ? "bg-white/[0.1] text-zinc-100"
                : "text-zinc-400 hover:text-zinc-200",
            )}
          >
            <Sliders className="size-3.5" aria-hidden="true" />
            <span>Formulario estructurado</span>
          </button>
          <button
            type="button"
            onClick={() => onEditorTabChange("brief")}
            className={cn(
              "inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[5px] px-3 py-1.5 text-[12px] font-medium transition-colors",
              editorTab === "brief"
                ? "bg-violet-500/20 text-violet-200"
                : "text-zinc-400 hover:text-zinc-200",
            )}
          >
            <Sparkles className="size-3.5 text-violet-300" aria-hidden="true" />
            <span>Pegar brief (IA)</span>
          </button>
        </div>
      </div>

      {/* Tab Body */}
      {editorTab === "brief" ? (
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-200">
              <FileText className="size-4 text-violet-400" aria-hidden="true" />
              <span>
                Pega el brief en texto libre (Notion, Slack, correo de cliente)
              </span>
            </div>
            <button
              type="button"
              onClick={() =>
                onDraftChange({ ...draft, sourceText: SAMPLE_BRIEF_ES })
              }
              className="cursor-pointer text-[12px] text-amber-400 underline underline-offset-4 hover:text-amber-300"
            >
              Cargar brief de ejemplo
            </button>
          </div>

          <textarea
            aria-label="Brief de campaña en texto libre"
            rows={11}
            value={draft.sourceText}
            onChange={(event) =>
              onDraftChange({ ...draft, sourceText: event.target.value })
            }
            placeholder="Pega aquí las reglas de duración, temas prohibidos, CTA, hashtags y tono en español o inglés..."
            className="w-full rounded-lg border border-white/[0.1] bg-[#09090B] p-4 font-mono text-[13px] leading-relaxed text-zinc-200 placeholder:text-zinc-600 focus:border-violet-400/60 focus:outline-none"
          />

          {parseError ? (
            <Alert variant="destructive">
              <AlertCircle className="size-4" aria-hidden="true" />
              <AlertDescription className="text-xs">
                <span className="block font-medium">
                  No se pudo analizar el brief con IA
                </span>
                {parseError}. Tu texto sigue intacto; puedes reintentar o pasar
                al formulario estructurado para completarlo manualmente.
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-[12px] text-zinc-500">
              Los campos inferidos se marcarán con el distintivo{" "}
              <span className="font-mono text-violet-300">IA</span> para tu
              revisión antes de guardar.
            </span>
            <Button
              type="button"
              onClick={() => onParseBrief(draft.sourceText)}
              disabled={isParsing || !draft.sourceText.trim()}
              className="h-10 gap-2 bg-amber-400 px-4 text-[13px] font-semibold text-zinc-950 hover:bg-amber-300"
            >
              {isParsing ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>Extrayendo reglas…</span>
                </>
              ) : (
                <>
                  <Sparkles className="size-4" aria-hidden="true" />
                  <span>Extraer reglas con IA</span>
                </>
              )}
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5 p-5">
          {inferredFields.length > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-violet-400/25 bg-violet-500/10 px-3.5 py-2.5 text-xs text-violet-200">
              <span>
                Propuesta generada{" "}
                {parseProvider ? (
                  <span className="font-mono text-violet-300">
                    ({parseProvider})
                  </span>
                ) : null}
                : revisa los{" "}
                <span className="font-mono font-semibold">
                  {inferredFields.length}
                </span>{" "}
                campos marcados con <span className="font-mono">IA</span> antes
                de guardar.
              </span>
            </div>
          ) : null}

          {parseWarnings.length > 0 ? (
            <div className="space-y-1 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3.5 py-2.5 text-xs text-amber-200">
              <p className="flex items-center gap-1.5 font-medium">
                <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
                Avisos del análisis de brief
              </p>
              <ul className="list-disc pl-5 text-[11px] text-amber-200/90">
                {parseWarnings.map((warning, idx) => (
                  <li key={idx}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Nombre e idioma */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-2">
              <label
                htmlFor="campaign-name"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Nombre de campaña {renderAIBadge("name")}
              </label>
              <input
                id="campaign-name"
                type="text"
                maxLength={120}
                value={draft.name}
                onChange={(event) =>
                  updateRules({}, "name", event.target.value)
                }
                placeholder="Ej. HookVault — Finanzas Q4"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[13px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-language"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Idioma {renderAIBadge("language")}
              </label>
              <select
                id="campaign-language"
                value={rules.language ?? "auto"}
                onChange={(event) =>
                  updateRules(
                    { language: event.target.value as RuleLanguage },
                    "language",
                  )
                }
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-2.5 text-[12px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              >
                <option value="auto" className="bg-[#111114]">
                  Automático (auto)
                </option>
                <option value="es" className="bg-[#111114]">
                  Español (es)
                </option>
                <option value="en" className="bg-[#111114]">
                  English (en)
                </option>
              </select>
            </div>
          </div>

          {/* Numeric constraints */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <label
                htmlFor="campaign-min-duration"
                className="flex items-center text-[12px] text-zinc-400"
              >
                Duración mín. (s) {renderAIBadge("min_duration")}
              </label>
              <input
                id="campaign-min-duration"
                type="number"
                min={5}
                max={179}
                value={rules.min_duration ?? 20}
                onChange={(event) =>
                  updateRules(
                    { min_duration: Number(event.target.value) },
                    "min_duration",
                  )
                }
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-[13px] tabular-nums text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-max-duration"
                className="flex items-center text-[12px] text-zinc-400"
              >
                Duración máx. (s) {renderAIBadge("max_duration")}
              </label>
              <input
                id="campaign-max-duration"
                type="number"
                min={6}
                max={180}
                value={rules.max_duration ?? 60}
                onChange={(event) =>
                  updateRules(
                    { max_duration: Number(event.target.value) },
                    "max_duration",
                  )
                }
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-[13px] tabular-nums text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-max-clips"
                className="flex items-center text-[12px] text-zinc-400"
              >
                Máx. clips {renderAIBadge("max_clips")}
              </label>
              <input
                id="campaign-max-clips"
                type="number"
                min={1}
                max={50}
                value={rules.max_clips ?? ""}
                placeholder="Sin tope"
                onChange={(event) => {
                  const raw = event.target.value.trim();
                  updateRules(
                    { max_clips: raw === "" ? null : Number(raw) },
                    "max_clips",
                  );
                }}
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-[13px] tabular-nums text-zinc-100 placeholder:text-zinc-600 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-hook-max"
                className="flex items-center text-[12px] text-zinc-400"
              >
                Hook máx. (s) {renderAIBadge("hook_max_seconds")}
              </label>
              <input
                id="campaign-hook-max"
                type="number"
                step={0.5}
                min={1}
                max={15}
                value={rules.hook_max_seconds ?? 3}
                onChange={(event) =>
                  updateRules(
                    { hook_max_seconds: Number(event.target.value) },
                    "hook_max_seconds",
                  )
                }
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-[13px] tabular-nums text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>
          </div>

          {/* Topics & Keywords */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label
                htmlFor="campaign-priority-topics"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Temas prioritarios (separados por coma){" "}
                {renderAIBadge("priority_topics")}
              </label>
              <input
                id="campaign-priority-topics"
                type="text"
                value={(rules.priority_topics ?? []).join(", ")}
                onChange={(event) =>
                  updateRules(
                    { priority_topics: splitCommaList(event.target.value) },
                    "priority_topics",
                  )
                }
                placeholder="anécdotas, consejos accionables"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-banned-topics"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Temas prohibidos {renderAIBadge("banned_topics")}
              </label>
              <input
                id="campaign-banned-topics"
                type="text"
                value={(rules.banned_topics ?? []).join(", ")}
                onChange={(event) =>
                  updateRules(
                    { banned_topics: splitCommaList(event.target.value) },
                    "banned_topics",
                  )
                }
                placeholder="política, patrocinadores"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-banned-words"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Palabras prohibidas {renderAIBadge("banned_words")}
              </label>
              <input
                id="campaign-banned-words"
                type="text"
                value={(rules.banned_words ?? []).join(", ")}
                onChange={(event) =>
                  updateRules(
                    { banned_words: splitCommaList(event.target.value) },
                    "banned_words",
                  )
                }
                placeholder="garantizado, dinero fácil"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-rose-200 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-required-keywords"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Palabras clave obligatorias {renderAIBadge("required_keywords")}
              </label>
              <input
                id="campaign-required-keywords"
                type="text"
                value={(rules.required_keywords ?? []).join(", ")}
                onChange={(event) =>
                  updateRules(
                    { required_keywords: splitCommaList(event.target.value) },
                    "required_keywords",
                  )
                }
                placeholder="inversión, ahorro"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-emerald-200 focus:border-amber-400/60 focus:outline-none"
              />
            </div>
          </div>

          {/* Tone & CTA */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label
                htmlFor="campaign-tone"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Tono editorial {renderAIBadge("tone")}
              </label>
              <input
                id="campaign-tone"
                type="text"
                maxLength={120}
                value={rules.tone ?? ""}
                onChange={(event) =>
                  updateRules({ tone: event.target.value || null }, "tone")
                }
                placeholder="directo, educativo y con ritmo"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-cta"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                CTA de cierre (últimos 3s) {renderAIBadge("cta_text")}
              </label>
              <input
                id="campaign-cta"
                type="text"
                maxLength={200}
                value={rules.cta_text ?? ""}
                onChange={(event) =>
                  updateRules(
                    { cta_text: event.target.value || null },
                    "cta_text",
                  )
                }
                placeholder="Episodio completo en el canal"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>
          </div>

          {/* Hashtags, Preset, Platforms */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label
                htmlFor="campaign-hashtags"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Hashtags {renderAIBadge("hashtags")}
              </label>
              <input
                id="campaign-hashtags"
                type="text"
                value={(rules.hashtags ?? []).join(" ")}
                onChange={(event) =>
                  updateRules(
                    { hashtags: splitHashtags(event.target.value) },
                    "hashtags",
                  )
                }
                placeholder="#shorts #finanzas"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-[12px] text-zinc-200 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="campaign-preset"
                className="flex items-center text-[12px] font-medium text-zinc-300"
              >
                Preset de subtítulos {renderAIBadge("subtitle_preset")}
              </label>
              <select
                id="campaign-preset"
                value={rules.subtitle_preset ?? ""}
                onChange={(event) =>
                  updateRules(
                    { subtitle_preset: event.target.value || null },
                    "subtitle_preset",
                  )
                }
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-[12px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              >
                <option value="" className="bg-[#111114]">
                  Sin preset forzado
                </option>
                {presets.map((preset) => (
                  <option
                    key={preset.id}
                    value={preset.id}
                    className="bg-[#111114]"
                  >
                    {preset.name} ({preset.id})
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <span className="flex items-center text-[12px] font-medium text-zinc-300">
                Plataformas objetivo {renderAIBadge("target_platforms")}
              </span>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {PLATFORM_OPTIONS.map((platform) => {
                  const active = (rules.target_platforms ?? []).includes(
                    platform.id,
                  );
                  return (
                    <button
                      key={platform.id}
                      type="button"
                      onClick={() => togglePlatform(platform.id)}
                      aria-pressed={active}
                      className={cn(
                        "h-8 cursor-pointer rounded-md border px-2.5 text-[11px] font-medium transition-colors",
                        active
                          ? "border-amber-400/50 bg-amber-400/15 text-amber-300"
                          : "border-white/10 bg-[#09090B] text-zinc-400 hover:border-white/20 hover:text-zinc-200",
                      )}
                    >
                      {platform.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Watermark PNG/WebP Upload */}
          <div className="space-y-1.5">
            <span className="flex items-center text-[12px] font-medium text-zinc-300">
              Marca de agua (PNG o WebP, máx. 5 MB){" "}
              {renderAIBadge("watermark_path")}
            </span>
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-white/[0.08] bg-[#09090B] p-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/webp,.png,.webp"
                onChange={handleWatermarkFile}
                aria-label="Subir marca de agua PNG o WebP"
                className="hidden"
              />
              {watermarkPreviewUrl ? (
                <div className="flex items-center gap-2.5">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={watermarkPreviewUrl}
                    alt="Vista previa de marca de agua"
                    className="h-10 w-16 rounded border border-white/10 bg-zinc-900 object-contain p-1"
                  />
                  <span className="max-w-[240px] truncate font-mono text-[11px] text-zinc-300">
                    {rules.watermark_path}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <ImageIcon className="size-4" aria-hidden="true" />
                  <span>Sin marca de agua configurada</span>
                </div>
              )}

              <div className="ml-auto flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isUploadingWatermark}
                  onClick={() => fileInputRef.current?.click()}
                  className="h-8 gap-1.5 border-white/10 bg-[#141418] text-xs text-zinc-200 hover:bg-white/[0.08]"
                >
                  {isUploadingWatermark ? (
                    <>
                      <Loader2
                        className="size-3.5 animate-spin"
                        aria-hidden="true"
                      />
                      <span>Subiendo…</span>
                    </>
                  ) : (
                    <>
                      <Upload className="size-3.5" aria-hidden="true" />
                      <span>
                        {rules.watermark_path ? "Cambiar imagen" : "Subir PNG/WebP"}
                      </span>
                    </>
                  )}
                </Button>
                {rules.watermark_path ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      updateRules({ watermark_path: null }, "watermark_path")
                    }
                    className="h-8 gap-1 text-xs text-zinc-400 hover:text-rose-400"
                  >
                    <X className="size-3.5" aria-hidden="true" />
                    <span>Quitar</span>
                  </Button>
                ) : null}
              </div>
            </div>
          </div>

          {/* Extra Instructions */}
          <div className="space-y-1.5">
            <label
              htmlFor="campaign-extra-instructions"
              className="flex items-center text-[12px] font-medium text-zinc-300"
            >
              Instrucciones extra para el selector IA{" "}
              {renderAIBadge("extra_instructions")}
            </label>
            <textarea
              id="campaign-extra-instructions"
              rows={3}
              maxLength={2000}
              value={rules.extra_instructions ?? ""}
              onChange={(event) =>
                updateRules(
                  { extra_instructions: event.target.value || null },
                  "extra_instructions",
                )
              }
              placeholder="Ej. Evita cortes a mitad de risa y prioriza momentos con cifras concretas."
              className="w-full rounded-md border border-white/[0.1] bg-[#09090B] p-3 text-[12px] text-zinc-100 placeholder:text-zinc-600 focus:border-amber-400/60 focus:outline-none"
            />
          </div>

          {/* Live Validation Errors */}
          {validationErrors.length > 0 ? (
            <div
              role="alert"
              className="rounded-lg border border-rose-500/35 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-300"
            >
              <ul className="list-disc space-y-0.5 pl-4">
                {validationErrors.map((err, idx) => (
                  <li key={idx}>{err}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex items-center justify-end gap-2.5 border-t border-white/[0.08] pt-3">
            <Button
              type="submit"
              disabled={!canSave}
              className="h-9 gap-1.5 bg-amber-400 px-4 text-[13px] font-semibold text-zinc-950 hover:bg-amber-300"
            >
              {isSaving ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>Guardando…</span>
                </>
              ) : (
                <>
                  <Check className="size-4 stroke-[2.5]" aria-hidden="true" />
                  <span>
                    {mode === "new" ? "Guardar campaña" : "Actualizar campaña"}
                  </span>
                </>
              )}
            </Button>
          </div>
        </form>
      )}

      {/* Collapsible Synchronized JSON Preview */}
      <div className="border-t border-white/[0.08] bg-[#0B0B0E]">
        <div className="flex items-center justify-between px-5 py-2.5">
          <button
            type="button"
            onClick={() => setShowJson((open) => !open)}
            className="inline-flex cursor-pointer items-center gap-2 font-mono text-[12px] text-zinc-400 hover:text-zinc-200"
          >
            {showJson ? (
              <ChevronUp className="size-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="size-3.5" aria-hidden="true" />
            )}
            <span>Vista JSON sincronizada (campaign_rules.json)</span>
          </button>

          <button
            type="button"
            onClick={() => {
              navigator.clipboard
                ?.writeText(jsonPreview)
                .then(() => toast.success("JSON copiado al portapapeles"))
                .catch((err) =>
                  toast.error("No se pudo copiar el JSON", {
                    description: errorMessage(err),
                  }),
                );
            }}
            className="inline-flex cursor-pointer items-center gap-1 font-mono text-[11px] text-zinc-400 hover:text-amber-300"
          >
            <Copy className="size-3" aria-hidden="true" />
            <span>Copiar JSON</span>
          </button>
        </div>

        {showJson ? (
          <pre
            data-testid="campaign-json-preview"
            className="max-h-60 overflow-x-auto px-5 pb-4 font-mono text-[11.5px] leading-relaxed text-zinc-300"
          >
            {jsonPreview}
          </pre>
        ) : null}
      </div>
    </section>
  );
}
