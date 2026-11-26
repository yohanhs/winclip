"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  Video,
  Upload,
  ChevronDown,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { FileDropzone } from "./file-dropzone";
import { SubtitlePresetPreview } from "./subtitle-preset-preview";
import { useCreateProject } from "@/hooks/use-projects";
import { usePresets } from "@/hooks/use-api-client";
import type { components } from "@winclip/api-client";

type CaptionPreset = "bold_yellow" | "hormozi" | "clean_white" | "mrbeast";

type ReframeMode = "face_track" | "center" | "blur_bg" | "passthrough";

// API reframe mode type
type ApiReframeMode = "face" | "center" | "blur" | "passthrough";

// Type for requested_clips parameter
type RequestedClips = number | "max";

interface ProjectCreateFormProps {
  campaigns?: Array<{
    id: string;
    name: string;
    language: string;
    maxClips: number;
    hookSeconds: number;
    forbiddenWords: string[];
    cta: string;
  }>;
  className?: string;
}

// Preset styling metadata
const PRESET_STYLES: Record<
  CaptionPreset,
  { name: string; subtitle: string; swatch: string }
> = {
  bold_yellow: {
    name: "Bold Yellow",
    subtitle: "Karaoke amarillo eléctrico · trazo negro",
    swatch: "#FFD600",
  },
  hormozi: {
    name: "Hormozi",
    subtitle: "Alto impacto · palabra activa verde/ámbar",
    swatch: "#10B981",
  },
  clean_white: {
    name: "Clean White",
    subtitle: "Editorial minimalista · pastilla translúcida",
    swatch: "#F4F4F5",
  },
  mrbeast: {
    name: "MrBeast",
    subtitle: "Display condensado · rebote pop en acento",
    swatch: "#F59E0B",
  },
};

// API preset data type
type PresetData = components["schemas"]["SubtitlePresetOut"];

// Reframe mode display names
const REFAME_MODE_OPTIONS: { value: ReframeMode; label: string; description: string }[] = [
  { value: "face_track", label: "Rostro en movimiento", description: "Enfoca rostros y personas" },
  { value: "center", label: "Centro automático", description: "Mantiene el centro del frame" },
  { value: "blur_bg", label: "Fondo desenfocado", description: "Desenfoca el fondo para foco en subjecto" },
  { value: "passthrough", label: "Sin reframe", description: "Mantiene el video original" },
];

// Map UI refame mode to API value
function mapReframeModeToApi(mode: ReframeMode): ApiReframeMode {
  const map: Record<ReframeMode, ApiReframeMode> = {
    face_track: "face",
    center: "center",
    blur_bg: "blur",
    passthrough: "passthrough",
  };
  return map[mode] || "face";
}

// Map API refame mode to UI value
function mapApiReframeModeToUI(mode: string): ReframeMode {
  const map: Record<string, ReframeMode> = {
    face: "face_track",
    center: "center",
    blur: "blur_bg",
    passthrough: "passthrough",
  };
  return map[mode] || "face_track";
}

export function ProjectCreateForm({ campaigns = [], className = "" }: ProjectCreateFormProps) {
  const [activeTab, setActiveTab] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [clipsCount, setClipsCount] = useState<number>(5);
  const [language, setLanguage] = useState<"auto" | "es" | "en">("auto");
  const [campaignId, setCampaignId] = useState<string>("");
  const [selectedPreset, setSelectedPreset] = useState<CaptionPreset>("bold_yellow");
  const [reframeMode, setReframeMode] = useState<ReframeMode>("face_track");
  const [title, setTitle] = useState("");

  const createProject = useCreateProject();

  const { data: presets } = usePresets();

  // Get preset data
  const presetData = useMemo((): PresetData | null => {
    if (!presets) return null;
    const preset = presets.find((p) => p.id === selectedPreset || p.id === "default");
    if (preset) {
      return {
        id: preset.id,
        name: preset.name,
        description: preset.description,
        font: preset.font || "Inter",
        fallback_font: preset.fallback_font || "Arial",
        font_size: preset.font_size || 24,
        uppercase: preset.uppercase || false,
        primary_color: preset.primary_color || "#FFFFFF",
        highlight_color: preset.highlight_color || "#FFD600",
        outline_color: preset.outline_color || "#000000",
        outline_width: preset.outline_width || 2,
        shadow_color: preset.shadow_color || "#00000000",
        shadow_depth: preset.shadow_depth || 0,
        highlight_scale_pct: preset.highlight_scale_pct || 100,
        y_pct: preset.y_pct || 85,
        margin_x: preset.margin_x || 20,
        max_lines: preset.max_lines || 2,
        max_chars_per_line: preset.max_chars_per_line || 40,
        max_words_per_cue: preset.max_words_per_cue || 8,
        max_pause_sec: preset.max_pause_sec || 2,
        box_bg_color: preset.box_bg_color || null,
      };
    }
    return null;
  }, [presets, selectedPreset]);

  // Calculate effective clips count
  const effectiveClipsCount: RequestedClips = clipsCount === 100 ? "max" : clipsCount;

  // Handle URL submission
  const handleUrlSubmit = async () => {
    if (!url.trim() || createProject.isPending) return;

    const params: {
      source_url: string;
      title: string;
      requested_clips: RequestedClips;
      language: "auto" | "es" | "en";
      campaign_id?: string;
      subtitle_preset: string;
      reframe_mode: ApiReframeMode;
    } = {
      source_url: url.trim(),
      title: title || "Nuevo proyecto",
      requested_clips: effectiveClipsCount,
      language: language,
      subtitle_preset: selectedPreset,
      reframe_mode: mapReframeModeToApi(reframeMode),
    };

    if (campaignId) params.campaign_id = campaignId;

    await createProject.mutateAsync(params);
  };

  // Handle file upload
  const handleFileUpload = async (selectedFile: File) => {
    if (createProject.isPending) return;

    await createProject.mutateAsync({
      file: selectedFile,
      title: title || selectedFile.name.replace(/\.[^/.]+$/, ""),
      requested_clips: effectiveClipsCount,
      language,
      campaign_id: campaignId || undefined,
      subtitle_preset: selectedPreset,
      reframe_mode: mapReframeModeToApi(reframeMode),
    });
  };

  // Handle file drop
  const handleDrop = (selectedFile: File, previewUrl: string) => {
    setFile(selectedFile);
    setPreviewUrl(previewUrl);
  };

  // Reset form
  const resetForm = () => {
    setUrl("");
    setTitle("");
    setFile(null);
    setPreviewUrl("");
    setClipsCount(5);
    setLanguage("auto");
    setCampaignId("");
    setSelectedPreset("bold_yellow");
    setReframeMode("face_track");
  };

  // Check if form is valid
  const isFormValid = activeTab === "url" ? url.trim().length > 0 : file !== null;

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      {/* Input section */}
      <section className="bg-[#111114] border border-white/[0.08] rounded-lg p-5 space-y-5">
        <h2 className="text-[15px] font-semibold text-zinc-100">
          1. Contenido fuente
        </h2>

        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as "url" | "upload")}
          className="w-full"
        >
          <TabsList className="bg-[#09090B] border border-white/[0.08] rounded-lg">
            <TabsTrigger
              value="url"
              className="data-[state=active]:bg-amber-500 data-[state=active]:text-zinc-950"
            >
              <Video className="w-4 h-4 mr-2" />
              URL
            </TabsTrigger>
            <TabsTrigger
              value="upload"
              className="data-[state=active]:bg-amber-500 data-[state=active]:text-zinc-950"
            >
              <Upload className="w-4 h-4 mr-2" />
              Subir archivo
            </TabsTrigger>
          </TabsList>

          {/* URL Tab */}
          <TabsContent value="url" className="mt-4">
            <div className="space-y-3">
              <div>
                <Label
                  htmlFor="url-input"
                  className="text-[13px] font-medium text-zinc-200"
                >
                  URL del video
                </Label>
                <Input
                  id="url-input"
                  type="url"
                  placeholder="https://youtube.com/watch?v=..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="mt-1 bg-[#09090B] border-white/[0.08] text-zinc-100"
                />
              </div>

              <div>
                <Label
                  htmlFor="title-input"
                  className="text-[13px] font-medium text-zinc-200"
                >
                  Título (opcional)
                </Label>
                <Input
                  id="title-input"
                  type="text"
                  placeholder="Título del proyecto"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="mt-1 bg-[#09090B] border-white/[0.08] text-zinc-100"
                />
              </div>
            </div>
          </TabsContent>

          {/* Upload Tab */}
          <TabsContent value="upload" className="mt-4">
            <FileDropzone
              accept="video/*"
              maxSizeMB={4000}
              onFileSelected={setFile}
              onUploadComplete={handleFileUpload}
              placeholder="Arrastra un video aquí o haz clic para seleccionar"
            />

            {/* Preview */}
            {previewUrl && (
              <div className="mt-4">
                <Label className="text-[13px] font-medium text-zinc-200">
                  Vista previa del archivo
                </Label>
                <img
                  src={previewUrl}
                  alt="Preview"
                  className="mt-2 max-h-[180px] rounded-lg object-contain bg-[#09090B]"
                />
              </div>
            )}
          </TabsContent>
        </Tabs>
      </section>

      {/* Clipping Parameters section */}
      <section className="bg-[#111114] border border-white/[0.08] rounded-lg p-5 space-y-5">
        <h2 className="text-[15px] font-semibold text-zinc-100">
          2. Selección IA y reglas de campaña
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Clip Count Slider */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <Label
                htmlFor="clip-count-slider"
                className="text-[13px] font-medium text-zinc-200"
              >
                Cantidad de clips
              </Label>
              <span className="text-[12px] font-mono text-zinc-300">
                {clipsCount === 100 ? "Máx" : clipsCount}
              </span>
            </div>
            <Slider
              id="clip-count-slider"
              min={1}
              max={100}
              step={1}
              value={[clipsCount]}
              onValueChange={(v) => setClipsCount(v[0] ?? 5)}
              className="w-full"
            />
            <p className="text-[11px] text-zinc-400">
              Usa el slider para ajustar cuántos clips generar. El valor máximo es ilimitado.
            </p>
          </div>

          {/* Language Selector */}
          <div className="space-y-2.5">
            <Label
              htmlFor="language-select"
              className="text-[13px] font-medium text-zinc-200"
            >
              Idioma
            </Label>
            <Select
              value={language}
              onValueChange={(v) => setLanguage(v as "auto" | "es" | "en")}
            >
              <SelectTrigger className="bg-[#09090B] border-white/[0.08] text-zinc-100">
                <SelectValue placeholder="Selecciona un idioma" />
                <ChevronDown className="h-4 w-4 opacity-50" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto detectar</SelectItem>
                <SelectItem value="es">Español (ES)</SelectItem>
                <SelectItem value="en">Inglés (EN)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Campaign Selector */}
          <div className="space-y-2.5">
            <Label
              htmlFor="campaign-select"
              className="text-[13px] font-medium text-zinc-200"
            >
              Campaña (opcional)
            </Label>
            <Select value={campaignId} onValueChange={setCampaignId}>
              <SelectTrigger className="bg-[#09090B] border-white/[0.08] text-zinc-100">
                <SelectValue placeholder="Sin campaña" />
                <ChevronDown className="h-4 w-4 opacity-50" />
              </SelectTrigger>
              <SelectContent>
                {campaigns.length === 0 ? (
                  <SelectItem value="" disabled>
                    Sin campañas disponibles
                  </SelectItem>
                ) : (
                  campaigns.map((campaign) => (
                    <SelectItem key={campaign.id} value={campaign.id}>
                      {campaign.name}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-zinc-400">
              Las reglas de campaña se aplicarán a los clips generados.
            </p>
          </div>

          {/* Reframe Mode Selector */}
          <div className="space-y-2.5">
            <Label
              htmlFor="reframe-mode-select"
              className="text-[13px] font-medium text-zinc-200"
            >
              Modo reframe
            </Label>
            <Select
              value={reframeMode}
              onValueChange={(v) => setReframeMode(v as ReframeMode)}
            >
              <SelectTrigger className="bg-[#09090B] border-white/[0.08] text-zinc-100">
                <SelectValue placeholder="Selecciona un modo" />
                <ChevronDown className="h-4 w-4 opacity-50" />
              </SelectTrigger>
              <SelectContent>
                {REFAME_MODE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    <div className="flex flex-col">
                      <span>{option.label}</span>
                      <span className="text-[11px] text-zinc-400">
                        {option.description}
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </section>

      {/* Preset Preview section */}
      <section className="bg-[#111114] border border-white/[0.08] rounded-lg p-5 space-y-5">
        <h2 className="text-[15px] font-semibold text-zinc-100">
          3. Estilo de subtítulos
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Preset Selection */}
          <div className="space-y-3">
            <Label className="text-[13px] font-medium text-zinc-200">
              Preset de subtítulos
            </Label>
            <div className="grid grid-cols-1 gap-2">
              {(Object.keys(PRESET_STYLES) as CaptionPreset[]).map((preset) => (
                <div
                  key={preset}
                  onClick={() => setSelectedPreset(preset)}
                  className={`
                    flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer
                    ${selectedPreset === preset
                      ? "border-amber-400 bg-amber-400/[0.05]"
                      : "border-white/[0.08] hover:border-white/[0.15] bg-[#09090B]"}
                  `}
                >
                  <div
                    className="w-10 h-10 rounded-full"
                    style={{ backgroundColor: PRESET_STYLES[preset].swatch }}
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-zinc-100">
                      {PRESET_STYLES[preset].name}
                    </div>
                    <div className="text-xs text-zinc-400">
                      {PRESET_STYLES[preset].subtitle}
                    </div>
                  </div>
                  {selectedPreset === preset && (
                    <div className="w-2 h-2 rounded-full bg-amber-400" />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Preview */}
          <div>
            <Label className="text-[13px] font-medium text-zinc-200 block mb-2">
              Vista previa
            </Label>
            {presetData && (
              <SubtitlePresetPreview
                preset={selectedPreset}
                presetData={presetData}
                isPlaying={true}
                className="aspect-video"
              />
            )}
          </div>
        </div>
      </section>

      {/* Actions */}
      <div className="flex gap-3">
        <Link href="/projects">
          <Button variant="outline" className="border-white/[0.08] text-zinc-200">
           Cancelar
          </Button>
        </Link>
        <Button
          onClick={activeTab === "url" ? handleUrlSubmit : () => file && handleFileUpload(file)}
          disabled={!isFormValid || createProject.isPending}
          className="bg-amber-500 hover:bg-amber-600 text-zinc-950"
        >
          {createProject.isPending ? "Creando proyecto..." : "Crear proyecto"}
        </Button>
      </div>
    </div>
  );
}