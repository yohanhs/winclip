"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  getApiBaseUrl,
  type CampaignCreate,
  type CampaignOut,
  type CampaignParseOut,
  type CampaignTemplateOut,
  type CampaignUpdate,
  type WatermarkUploadOut,
} from "@winclip/api-client";

import { useApiClient } from "./use-api-client";

/** Lista de campañas del workspace (`GET /api/campaigns`). */
export function useCampaigns() {
  const api = useApiClient();
  return useQuery<CampaignOut[]>({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const { data } = await api.GET("/api/campaigns");
      return data ?? [];
    },
  });
}

/** Plantillas predefinidas ES/EN (`GET /api/campaigns/templates`). */
export function useCampaignTemplates() {
  const api = useApiClient();
  return useQuery<CampaignTemplateOut[]>({
    queryKey: ["campaign-templates"],
    queryFn: async () => {
      const { data } = await api.GET("/api/campaigns/templates");
      return data ?? [];
    },
    staleTime: 5 * 60_000,
  });
}

/** Crea una nueva campaña (`POST /api/campaigns`). */
export function useCreateCampaign() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<CampaignOut, Error, CampaignCreate>({
    mutationFn: async (body) => {
      const { data } = await api.POST("/api/campaigns", { body });
      if (!data) throw new Error("Respuesta vacía al crear la campaña");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });
}

/** Actualiza una campaña existente (`PATCH /api/campaigns/{campaign_id}`). */
export function useUpdateCampaign() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    CampaignOut,
    Error,
    { campaignId: string; body: CampaignUpdate }
  >({
    mutationFn: async ({ campaignId, body }) => {
      const { data } = await api.PATCH("/api/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
        body,
      });
      if (!data) throw new Error("Respuesta vacía al actualizar la campaña");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

/** Duplica una campaña existente (`POST /api/campaigns/{campaign_id}/duplicate`). */
export function useDuplicateCampaign() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<CampaignOut, Error, string>({
    mutationFn: async (campaignId) => {
      const { data } = await api.POST(
        "/api/campaigns/{campaign_id}/duplicate",
        {
          params: { path: { campaign_id: campaignId } },
        },
      );
      if (!data) throw new Error("Respuesta vacía al duplicar la campaña");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });
}

/** Elimina una campaña (`DELETE /api/campaigns/{campaign_id}`). */
export function useDeleteCampaign() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (campaignId) => {
      await api.DELETE("/api/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

/** Analiza un brief en texto libre vía LLM (`POST /api/campaigns/parse`) sin guardar. */
export function useParseCampaignBrief() {
  const api = useApiClient();

  return useMutation<CampaignParseOut, Error, string>({
    mutationFn: async (sourceText) => {
      const { data } = await api.POST("/api/campaigns/parse", {
        body: { source_text: sourceText },
      });
      if (!data) throw new Error("Respuesta vacía al analizar el brief");
      return data;
    },
  });
}

/** Sube una marca de agua PNG/WebP (`POST /api/campaigns/watermarks`). */
export function useUploadCampaignWatermark() {
  return useMutation<WatermarkUploadOut, Error, File>({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${getApiBaseUrl()}/api/campaigns/watermarks`, {
        method: "POST",
        body: formData,
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new ApiError(response.status, payload);
      }
      const result = payload as WatermarkUploadOut | null;
      if (!result?.watermark_path) {
        throw new Error("Respuesta inválida al subir la marca de agua");
      }
      return result;
    },
  });
}
