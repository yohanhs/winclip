"use client";

import { useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import type {
  CampaignOut,
  CampaignRules,
  CampaignTemplateOut,
} from "@winclip/api-client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  useCampaigns,
  useCampaignTemplates,
  useCreateCampaign,
  useDeleteCampaign,
  useDuplicateCampaign,
  useParseCampaignBrief,
  useUpdateCampaign,
  useUploadCampaignWatermark,
} from "@/hooks/use-campaigns";
import { usePresets } from "@/hooks/use-projects";
import { errorMessage } from "@/lib/api";

import { CampaignEditor, type CampaignDraft } from "./campaign-editor";
import { CampaignList } from "./campaign-list";

function emptyRules(): CampaignRules {
  return {
    name: "Nueva campaña",
    language: "auto",
    min_duration: 20,
    max_duration: 60,
    max_clips: 10,
    priority_topics: [],
    banned_topics: [],
    banned_words: [],
    required_keywords: [],
    tone: null,
    hook_max_seconds: 3,
    cta_text: null,
    hashtags: [],
    subtitle_preset: "bold-yellow",
    watermark_path: null,
    target_platforms: ["youtube", "tiktok"],
    extra_instructions: null,
  };
}

function emptyDraft(): CampaignDraft {
  return {
    name: "",
    rules: emptyRules(),
    sourceText: "",
  };
}

function draftFromCampaign(campaign: CampaignOut): CampaignDraft {
  return {
    name: campaign.name,
    rules: { ...campaign.rules },
    sourceText: campaign.source_text ?? "",
  };
}

export function CampaignsWorkspace() {
  const campaignsQuery = useCampaigns();
  const templatesQuery = useCampaignTemplates();
  const presetsQuery = usePresets();

  const createCampaign = useCreateCampaign();
  const updateCampaign = useUpdateCampaign();
  const duplicateCampaign = useDuplicateCampaign();
  const deleteCampaign = useDeleteCampaign();
  const parseBrief = useParseCampaignBrief();
  const uploadWatermark = useUploadCampaignWatermark();

  const [selectedId, setSelectedId] = useState<string | "new">("new");
  const [draft, setDraft] = useState<CampaignDraft>(() => emptyDraft());
  const [editorTab, setEditorTab] = useState<"form" | "brief">("form");
  const [inferredFields, setInferredFields] = useState<string[]>([]);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [parseProvider, setParseProvider] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const campaigns = campaignsQuery.data ?? [];
  const templates = templatesQuery.data ?? [];
  const presets = presetsQuery.data ?? [];

  const clearParseState = () => {
    setInferredFields([]);
    setParseWarnings([]);
    setParseProvider(null);
    setParseError(null);
  };

  const handleSelectCampaign = (campaign: CampaignOut) => {
    setSelectedId(campaign.id);
    setDraft(draftFromCampaign(campaign));
    setEditorTab("form");
    clearParseState();
  };

  const handleCreateNew = () => {
    setSelectedId("new");
    setDraft(emptyDraft());
    setEditorTab("brief");
    clearParseState();
  };

  const handleApplyTemplate = (template: CampaignTemplateOut) => {
    setSelectedId("new");
    setDraft({
      name: template.rules.name ?? template.title,
      rules: { ...template.rules },
      sourceText: "",
    });
    setEditorTab("form");
    clearParseState();
    toast.success("Plantilla cargada", {
      description: `«${template.title}» lista para personalizar y guardar.`,
    });
  };

  const handleDraftChange = (next: CampaignDraft, editedField?: string) => {
    setDraft(next);
    if (editedField) {
      setInferredFields((prev) => prev.filter((item) => item !== editedField));
    }
  };

  const handleParseBrief = (briefText: string) => {
    setParseError(null);
    parseBrief.mutate(briefText, {
      onSuccess: (result) => {
        setDraft((prev) => ({
          name: result.rules.name || prev.name || "Campaña desde brief",
          rules: { ...result.rules },
          sourceText: briefText,
        }));
        setInferredFields(result.inferred_fields ?? []);
        setParseWarnings(result.warnings ?? []);
        setParseProvider(result.provider);
        setEditorTab("form");
        toast.success("Reglas extraídas con IA", {
          description: `${result.inferred_fields?.length ?? 0} campos inferidos marcados para revisión.`,
        });
      },
      onError: (error) => {
        const message = errorMessage(error);
        setParseError(message);
        toast.error("No se pudo analizar el brief", { description: message });
      },
    });
  };

  const handleUploadWatermark = (file: File) => {
    uploadWatermark.mutate(file, {
      onSuccess: (result) => {
        setDraft((prev) => ({
          ...prev,
          rules: { ...prev.rules, watermark_path: result.watermark_path },
        }));
        setInferredFields((prev) =>
          prev.filter((item) => item !== "watermark_path"),
        );
        toast.success("Marca de agua subida");
      },
      onError: (error) => {
        toast.error("No se pudo subir la marca de agua", {
          description: errorMessage(error),
        });
      },
    });
  };

  const handleSave = () => {
    const cleanName = draft.name.trim();
    const normalizedRules: CampaignRules = {
      ...draft.rules,
      name: cleanName,
    };
    const sourceText = draft.sourceText.trim() || null;

    if (selectedId === "new") {
      createCampaign.mutate(
        {
          name: cleanName,
          rules: normalizedRules,
          source_text: sourceText,
        },
        {
          onSuccess: (created) => {
            setSelectedId(created.id);
            setDraft(draftFromCampaign(created));
            clearParseState();
            toast.success("Campaña guardada", { description: created.name });
          },
          onError: (error) => {
            toast.error("No se pudo guardar la campaña", {
              description: errorMessage(error),
            });
          },
        },
      );
      return;
    }

    updateCampaign.mutate(
      {
        campaignId: selectedId,
        body: {
          name: cleanName,
          rules: normalizedRules,
          source_text: sourceText,
        },
      },
      {
        onSuccess: (updated) => {
          setDraft(draftFromCampaign(updated));
          clearParseState();
          toast.success("Campaña actualizada", { description: updated.name });
        },
        onError: (error) => {
          toast.error("No se pudo actualizar la campaña", {
            description: errorMessage(error),
          });
        },
      },
    );
  };

  const handleDuplicate = (campaign: CampaignOut) => {
    setDuplicatingId(campaign.id);
    duplicateCampaign.mutate(campaign.id, {
      onSuccess: (copy) => {
        setSelectedId(copy.id);
        setDraft(draftFromCampaign(copy));
        setEditorTab("form");
        clearParseState();
        toast.success("Campaña duplicada", { description: copy.name });
      },
      onError: (error) => {
        toast.error("No se pudo duplicar la campaña", {
          description: errorMessage(error),
        });
      },
      onSettled: () => setDuplicatingId(null),
    });
  };

  const handleDelete = (campaign: CampaignOut) => {
    setDeletingId(campaign.id);
    deleteCampaign.mutate(campaign.id, {
      onSuccess: () => {
        if (selectedId === campaign.id) {
          const remaining = campaigns.filter((item) => item.id !== campaign.id);
          if (remaining[0]) {
            setSelectedId(remaining[0].id);
            setDraft(draftFromCampaign(remaining[0]));
          } else {
            setSelectedId("new");
            setDraft(emptyDraft());
          }
          clearParseState();
        }
        toast.success("Campaña eliminada", { description: campaign.name });
      },
      onError: (error) => {
        toast.error("No se pudo eliminar la campaña", {
          description: errorMessage(error),
        });
      },
      onSettled: () => setDeletingId(null),
    });
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4">
      {campaignsQuery.isError ? (
        <Alert variant="destructive">
          <AlertCircle className="size-4" aria-hidden="true" />
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span>
              No se pudieron cargar las campañas:{" "}
              {errorMessage(campaignsQuery.error)}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void campaignsQuery.refetch()}
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        <CampaignList
          campaigns={campaigns}
          templates={templates}
          selectedId={selectedId}
          isLoading={campaignsQuery.isLoading}
          duplicatingId={duplicatingId}
          deletingId={deletingId}
          onSelect={handleSelectCampaign}
          onCreateNew={handleCreateNew}
          onApplyTemplate={handleApplyTemplate}
          onDuplicate={handleDuplicate}
          onDelete={handleDelete}
        />

        <CampaignEditor
          mode={selectedId === "new" ? "new" : "edit"}
          draft={draft}
          presets={presets}
          inferredFields={inferredFields}
          parseWarnings={parseWarnings}
          parseProvider={parseProvider}
          parseError={parseError}
          isParsing={parseBrief.isPending}
          isSaving={createCampaign.isPending || updateCampaign.isPending}
          isUploadingWatermark={uploadWatermark.isPending}
          editorTab={editorTab}
          onEditorTabChange={setEditorTab}
          onDraftChange={handleDraftChange}
          onParseBrief={handleParseBrief}
          onUploadWatermark={handleUploadWatermark}
          onSave={handleSave}
        />
      </div>
    </div>
  );
}
