"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  Film,
  Layers,
  Link2,
  Loader2,
  Maximize2,
  ScanFace,
  Sparkles,
  Upload,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCampaigns } from "@/hooks/use-campaigns";
import { useCreateProject, usePresets } from "@/hooks/use-projects";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { FileDropzone } from "./file-dropzone";
import {
  PRESET_STYLES,
  SubtitlePresetPreview,
} from "./subtitle-preset-preview";

type SourceType = "url" | "file";
type Language = "auto" | "es" | "en";
type ReframeMode = "face" | "center" | "blur" | "passthrough";

const PRESET_IDS = ["bold-yellow", "hormozi", "clean-white", "mrbeast", "none"] as const;

const REFRAME_OPTIONS: Array<{
  id: ReframeMode;
  label: string;
  description: string;
  icon: typeof ScanFace;
}> = [
  {
    id: "face",
    label: "Cara centrada",
    description: "OpenCV YuNet sigue al hablante",
    icon: ScanFace,
  },
  {
    id: "center",
    label: "Centrado",
    description: "Recorte fijo 9:16",
    icon: Maximize2,
  },
  {
    id: "blur",
    label: "Fondo blur",
    description: "Rellena con desenfoque",
    icon: Layers,
  },
  {
    id: "passthrough",
    label: "Sin recorte",
    description: "Vídeo original",
    icon: Film,
  },
];

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-white/10 bg-[#111114] p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        {description ? (
          <p className="mt-0.5 text-xs text-zinc-500">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function ProjectCreateForm() {
  const router = useRouter();
  const createProject = useCreateProject();
  const presetsQuery = usePresets();
  const campaignsQuery = useCampaigns();

  const [sourceType, setSourceType] = useState<SourceType>("url");
  const [sourceUrl, setSourceUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [clipCount, setClipCount] = useState(5);
  const [maxClips, setMaxClips] = useState(false);
  const [language, setLanguage] = useState<Language>("auto");
  const [preset, setPreset] = useState<string>("bold-yellow");
  const [reframeMode, setReframeMode] = useState<ReframeMode>("face");
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [urlError, setUrlError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const campaigns = campaignsQuery.data ?? [];
  const selectedCampaign =
    campaigns.find((item) => item.id === campaignId) ?? null;

  const handleCampaignChange = (value: string) => {
    if (value === "none") {
      setCampaignId(null);
      return;
    }
    setCampaignId(value);
    const chosen = campaigns.find((item) => item.id === value);
    if (!chosen) return;
    const rules = chosen.rules;
    if (rules.max_clips != null && rules.max_clips >= 1) {
      setMaxClips(false);
      setClipCount(Math.min(20, Math.max(1, rules.max_clips)));
    }
    if (
      rules.language === "auto" ||
      rules.language === "es" ||
      rules.language === "en"
    ) {
      setLanguage(rules.language);
    }
    if (
      rules.subtitle_preset &&
      PRESET_IDS.includes(rules.subtitle_preset as (typeof PRESET_IDS)[number])
    ) {
      setPreset(rules.subtitle_preset);
    }
  };

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleCancelUpload = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setUploadProgress(0);
  };

  const presetOptions = useMemo(() => {
    const fromApi = presetsQuery.data ?? [];
    return PRESET_IDS.map((id) => {
      const apiPreset = fromApi.find((item) => item.id === id);
      const style = PRESET_STYLES[id];
      return {
        id,
        name: apiPreset?.name ?? style?.name ?? id,
        description: apiPreset?.description ?? style?.subtitle ?? "",
        swatch: style?.swatch ?? "#F59E0B",
        data: apiPreset ?? null,
      };
    });
  }, [presetsQuery.data]);

  const selectedPreset = presetOptions.find((option) => option.id === preset);
  const isPending = createProject.isPending;
  const canSubmit =
    sourceType === "url" ? sourceUrl.trim().length > 0 : file !== null;

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setUrlError(null);

    if (sourceType === "url") {
      try {
        const parsed = new URL(sourceUrl.trim());
        if (!["http:", "https:"].includes(parsed.protocol)) {
          throw new Error("protocolo no soportado");
        }
      } catch {
        const message = "Pega un enlace http(s) a un vídeo o a YouTube.";
        setUrlError(message);
        toast.error("URL no válida", {
          description: message,
        });
        return;
      }
    }
    if (sourceType === "file" && !file) {
      toast.error("Selecciona un archivo de vídeo antes de continuar.");
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    createProject.mutate(
      {
        input: {
          source_url: sourceType === "url" ? sourceUrl.trim() : undefined,
          file: sourceType === "file" ? file : undefined,
          title: title.trim() || undefined,
          requested_clips: maxClips ? "max" : clipCount,
          language,
          subtitle_preset: preset,
          reframe_mode: reframeMode,
          campaign_id: campaignId ?? undefined,
        },
        onProgress: (progress) => setUploadProgress(progress.percentage),
        signal: controller.signal,
      },
      {
        onSuccess: (created) => {
          abortRef.current = null;
          toast.success("Proyecto creado", {
            description: "El pipeline ha empezado a procesar el vídeo.",
          });
          router.push(`/projects/${created.project.id}`);
        },
        onError: (error) => {
          abortRef.current = null;
          setUploadProgress(0);
          if (error instanceof DOMException && error.name === "AbortError") {
            toast.message("Subida cancelada");
            return;
          }
          toast.error("No se pudo crear el proyecto", {
            description: errorMessage(error),
          });
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <Section
            title="Origen del vídeo"
            description="Pega un enlace o sube un archivo local. El vídeo se procesa en tu máquina."
          >
            <Tabs
              value={sourceType}
              onValueChange={(value) => setSourceType(value as SourceType)}
            >
              <TabsList className="mb-4 grid w-full grid-cols-2 sm:w-[320px]">
                <TabsTrigger value="url" disabled={isPending}>
                  <Link2 className="mr-1.5 size-4" aria-hidden="true" />
                  URL
                </TabsTrigger>
                <TabsTrigger value="file" disabled={isPending}>
                  <Upload className="mr-1.5 size-4" aria-hidden="true" />
                  Subir archivo
                </TabsTrigger>
              </TabsList>

              <TabsContent value="url" className="mt-0 space-y-2">
                <Label htmlFor="source-url">Enlace del vídeo</Label>
                <div className="relative">
                  <Link2
                    className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-500"
                    aria-hidden="true"
                  />
                  <Input
                    id="source-url"
                    type="url"
                    inputMode="url"
                    placeholder="https://www.youtube.com/watch?v=…"
                    value={sourceUrl}
                    onChange={(event) => {
                      setSourceUrl(event.target.value);
                      if (urlError) setUrlError(null);
                    }}
                    disabled={isPending}
                    aria-invalid={Boolean(urlError)}
                    className="pl-9"
                  />
                </div>
                {urlError ? (
                  <p role="alert" className="text-xs text-rose-400">
                    {urlError}
                  </p>
                ) : (
                  <p className="text-xs text-zinc-500">
                    Compatible con YouTube, X, TikTok y enlaces directos a MP4.
                  </p>
                )}
              </TabsContent>

              <TabsContent value="file" className="mt-0">
                <FileDropzone
                  file={file}
                  onFileChange={setFile}
                  onCancelUpload={handleCancelUpload}
                  progress={uploadProgress}
                  uploading={isPending && sourceType === "file"}
                  disabled={isPending}
                />
              </TabsContent>
            </Tabs>
          </Section>

          <Section title="Detalles" description="Opcional: ponle un nombre al proyecto.">
            <Label htmlFor="project-title">Título</Label>
            <Input
              id="project-title"
              placeholder="Se autogenera desde el vídeo"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={isPending}
            />
          </Section>

          <Section
            title="Cantidad de clips"
            description="Cuántos shorts quieres extraer del vídeo."
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-mono text-2xl font-semibold tabular-nums text-zinc-100">
                  {maxClips ? "Máx." : clipCount}
                </p>
                <p className="text-xs text-zinc-500">
                  {maxClips
                    ? "Se generarán todos los clips válidos que encuentre el modelo."
                    : `${clipCount} ${clipCount === 1 ? "clip" : "clips"} solicitados`}
                </p>
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-300">
                <Switch
                  checked={maxClips}
                  onCheckedChange={setMaxClips}
                  disabled={isPending}
                  aria-label="Máximo posible"
                />
                Máximo posible
              </label>
            </div>
            <div className="mt-4 px-1">
              <Slider
                value={[clipCount]}
                min={1}
                max={20}
                step={1}
                disabled={maxClips || isPending}
                onValueChange={(values) => setClipCount(values[0] ?? 1)}
                aria-label="Cantidad de clips"
              />
              <div className="mt-1.5 flex justify-between font-mono text-[10px] tabular-nums text-zinc-600">
                <span>1</span>
                <span>20</span>
              </div>
            </div>
          </Section>

          <Section title="Estilo y encuadre">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Idioma</Label>
                <Select
                  value={language}
                  onValueChange={(value) => setLanguage(value as Language)}
                  disabled={isPending}
                >
                  <SelectTrigger aria-label="Idioma del contenido">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Detección automática</SelectItem>
                    <SelectItem value="es">Español</SelectItem>
                    <SelectItem value="en">Inglés</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Preset de subtítulos</Label>
                <Select
                  value={preset}
                  onValueChange={setPreset}
                  disabled={isPending}
                >
                  <SelectTrigger aria-label="Preset de subtítulos">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {presetOptions.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        <span className="flex items-center gap-2">
                          <span
                            className="size-2.5 rounded-full"
                            style={{ backgroundColor: option.swatch }}
                            aria-hidden="true"
                          />
                          {option.name}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="mt-4 space-y-2">
              <Label>Encuadre vertical</Label>
              <div className="grid grid-cols-2 gap-2">
                {REFRAME_OPTIONS.map((option) => {
                  const Icon = option.icon;
                  const active = reframeMode === option.id;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      disabled={isPending}
                      onClick={() => setReframeMode(option.id)}
                      aria-pressed={active}
                      className={cn(
                        "flex items-start gap-2.5 rounded-lg border p-2.5 text-left transition-colors",
                        active
                          ? "border-amber-500/50 bg-amber-500/5"
                          : "border-white/10 bg-[#0d0d10] hover:border-white/20",
                      )}
                    >
                      <Icon
                        className={cn(
                          "mt-0.5 size-4 shrink-0",
                          active ? "text-amber-400" : "text-zinc-500",
                        )}
                        aria-hidden="true"
                      />
                      <span>
                        <span className="block text-xs font-medium text-zinc-200">
                          {option.label}
                        </span>
                        <span className="block text-[11px] text-zinc-500">
                          {option.description}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="campaign">Campaña</Label>
                <Link
                  href="/campaigns"
                  className="text-[11px] text-amber-400 hover:text-amber-300"
                >
                  Gestionar campañas →
                </Link>
              </div>
              <Select
                value={campaignId ?? "none"}
                onValueChange={handleCampaignChange}
                disabled={isPending}
              >
                <SelectTrigger id="campaign" aria-label="Campaña">
                  <SelectValue placeholder="Sin campaña" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Sin campaña</SelectItem>
                  {campaigns.map((camp) => (
                    <SelectItem key={camp.id} value={camp.id}>
                      {camp.name} ({camp.rules.min_duration ?? 20}–
                      {camp.rules.max_duration ?? 60}s)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedCampaign ? (
                <p className="flex flex-wrap items-center gap-1.5 text-xs text-zinc-400">
                  <Users className="size-3.5 text-amber-400" aria-hidden="true" />
                  <span>
                    Reglas activas: {selectedCampaign.rules.min_duration ?? 20}–
                    {selectedCampaign.rules.max_duration ?? 60}s
                    {selectedCampaign.rules.hashtags?.length
                      ? ` · ${selectedCampaign.rules.hashtags.slice(0, 3).join(" ")}`
                      : ""}
                    {selectedCampaign.rules.banned_words?.length
                      ? ` · ${selectedCampaign.rules.banned_words.length} prohibidas`
                      : ""}
                  </span>
                </p>
              ) : (
                <p className="flex items-center gap-1.5 text-xs text-zinc-500">
                  <Users className="size-3.5" aria-hidden="true" />
                  {campaigns.length > 0
                    ? "Selecciona una campaña para pre-rellenar idioma, clips y preset."
                    : "Aún no tienes campañas creadas; puedes crearlas en Campañas."}
                </p>
              )}
            </div>
          </Section>

          <div className="flex flex-col-reverse items-stretch justify-between gap-3 sm:flex-row sm:items-center">
            <Button asChild type="button" variant="ghost" disabled={isPending}>
              <Link href="/projects">Cancelar</Link>
            </Button>
            <Button type="submit" size="lg" disabled={!canSubmit || isPending}>
              {isPending ? (
                <>
                  <Loader2 className="animate-spin" aria-hidden="true" />
                  {sourceType === "file" && uploadProgress > 0
                    ? `Subiendo ${uploadProgress}%…`
                    : "Creando proyecto…"}
                </>
              ) : (
                <>
                  <Sparkles aria-hidden="true" />
                  Generar clips
                  <ArrowRight aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        </div>

        <aside className="lg:sticky lg:top-6">
          <div className="space-y-3 rounded-xl border border-white/10 bg-[#111114] p-4">
            <p className="text-center text-xs font-medium uppercase tracking-wide text-zinc-500">
              Previsualización 9:16
            </p>
            <SubtitlePresetPreview
              preset={preset}
              presetData={selectedPreset?.data ?? null}
              reframeMode={reframeMode}
            />
            <p className="mx-auto max-w-[286px] text-center text-[11px] leading-relaxed text-zinc-600">
              Así se verán los subtítulos y el encuadre en el clip final. Puedes
              cambiarlo después en el editor de cada clip.
            </p>
          </div>
        </aside>
      </div>
    </form>
  );
}
