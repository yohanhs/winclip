"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AccountPlatform,
  PreviewMetaOut,
  PreviewMetaRequest,
  PublicationCancelRequest,
  PublicationOut,
  PublicationsCreateRequest,
  PublicationStatus,
  QuotaSummaryOut,
} from "@winclip/api-client";

import { useApiClient } from "./use-api-client";

export interface PublicationsFilter {
  project_id?: string;
  clip_id?: string;
  account_id?: string;
  platform?: AccountPlatform;
  status?: PublicationStatus;
}

/** Lista de publicaciones filtrable (`GET /api/publications`). */
export function usePublications(filters?: PublicationsFilter) {
  const api = useApiClient();
  return useQuery<PublicationOut[]>({
    queryKey: ["publications", filters ?? {}],
    queryFn: async () => {
      const { data } = await api.GET("/api/publications", {
        params: {
          query: filters
            ? {
                project_id: filters.project_id || undefined,
                clip_id: filters.clip_id || undefined,
                account_id: filters.account_id || undefined,
                platform: filters.platform || undefined,
                status: filters.status || undefined,
              }
            : undefined,
        },
      });
      return data ?? [];
    },
  });
}

/** Resumen de cuota diaria YouTube y límites por cuenta (`GET /api/publications/quota`). */
export function usePublicationsQuota() {
  const api = useApiClient();
  return useQuery<QuotaSummaryOut>({
    queryKey: ["publications-quota"],
    queryFn: async () => {
      const { data } = await api.GET("/api/publications/quota");
      return (
        data ?? {
          youtube_units_used: 0,
          youtube_units_limit: 10000,
          youtube_upload_cost: 1600,
          youtube_uploads_today: 0,
          accounts: [],
        }
      );
    },
  });
}

/** Precalcula metadatos propuestos por `(clip, cuenta)` (`POST /api/publications/preview-meta`). */
export function usePreviewPublicationMeta() {
  const api = useApiClient();
  return useMutation<PreviewMetaOut, Error, PreviewMetaRequest>({
    mutationFn: async (body) => {
      const { data } = await api.POST("/api/publications/preview-meta", { body });
      if (!data) throw new Error("Respuesta vacía al previsualizar metadatos");
      return data;
    },
  });
}

/** Encola publicaciones multi-clip y multi-cuenta (`POST /api/publications`). */
export function useCreatePublications() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<PublicationOut[], Error, PublicationsCreateRequest>({
    mutationFn: async (body) => {
      const { data } = await api.POST("/api/publications", { body });
      return data ?? [];
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["publications"] });
      void queryClient.invalidateQueries({ queryKey: ["publications-quota"] });
    },
  });
}

/** Reintenta una publicación fallida (`POST /api/publications/{publication_id}/retry`). */
export function useRetryPublication() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<PublicationOut, Error, string>({
    mutationFn: async (publicationId) => {
      const { data } = await api.POST("/api/publications/{publication_id}/retry", {
        params: { path: { publication_id: publicationId } },
      });
      if (!data) throw new Error("Respuesta vacía al reintentar publicación");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["publications"] });
      void queryClient.invalidateQueries({ queryKey: ["publications-quota"] });
    },
  });
}

/** Cancela una publicación programada (`POST /api/publications/{publication_id}/cancel`). */
export function useCancelPublication() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    PublicationOut,
    Error,
    { publicationId: string; body?: PublicationCancelRequest }
  >({
    mutationFn: async ({ publicationId, body }) => {
      const { data } = await api.POST("/api/publications/{publication_id}/cancel", {
        params: { path: { publication_id: publicationId } },
        body: body ?? { delete_remote: false },
      });
      if (!data) throw new Error("Respuesta vacía al cancelar publicación");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["publications"] });
      void queryClient.invalidateQueries({ queryKey: ["publications-quota"] });
    },
  });
}
