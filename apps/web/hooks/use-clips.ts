"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "./use-api-client";
import type { components } from "@winclip/api-client";

/**
 * Hook para actualizar un clip (PATCH /api/clips/{id})
 */
export function useUpdateClip() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    components["schemas"]["ClipOut"],
    Error,
    { clipId: string; data: components["schemas"]["ClipUpdate"] }
  >({
    mutationFn: async ({ clipId, data }) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.PATCH("/api/clips/{clip_id}", {
        params: { path: { clip_id: clipId } },
        body: data,
      });
      if (response.error) throw new Error("Failed to update clip");
      return response.data as components["schemas"]["ClipOut"];
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
    },
  });
}

/**
 * Hook para eliminar un clip (DELETE /api/clips/{id})
 */
export function useDeleteClip() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (clipId) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.DELETE("/api/clips/{clip_id}", {
        params: { path: { clip_id: clipId } },
      });
      if (response.error) throw new Error("Failed to delete clip");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

/**
 * Hook para descargar un clip (GET /api/clips/{id}/file)
 */
export function useDownloadClip() {
  const apiClient = useApiClient();

  return useMutation({
    mutationFn: async (clipId: string) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.GET("/api/clips/{clip_id}/file", {
        params: { path: { clip_id: clipId } },
      });
      if (response.error) throw new Error("Failed to download clip");
      return response;
    },
    onError: (error) => {
      console.error("Download error:", error);
    },
  });
}

/**
 * Hook para re-renderizar un clip (POST /api/clips/{id}/rerender)
 */
export function useRerenderClip() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    components["schemas"]["JobOut"],
    Error,
    string
  >({
    mutationFn: async (clipId) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.POST("/api/clips/{clip_id}/rerender", {
        params: { path: { clip_id: clipId } },
      });
      if (response.error) throw new Error("Failed to rerender clip");
      return response.data as components["schemas"]["JobOut"];
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
    },
  });
}

/**
 * Hook para actualizar tiempos de un clip (PATCH con start_sec/end_sec)
 */
export function useUpdateClipTimes() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    components["schemas"]["ClipOut"],
    Error,
    { clipId: string; startSec: number; endSec: number }
  >({
    mutationFn: async ({ clipId, startSec, endSec }) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.PATCH("/api/clips/{clip_id}", {
        params: { path: { clip_id: clipId } },
        body: { start_sec: startSec, end_sec: endSec },
      });
      if (response.error) throw new Error("Failed to update clip times");
      return response.data as components["schemas"]["ClipOut"];
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
    },
  });
}

/**
 * Hook para obtener estado de un job (GET /api/jobs/{id})
 */
export function useJob(jobId: string | undefined) {
  const apiClient = useApiClient();

  return useQuery({
    queryKey: ["jobs", jobId],
    queryFn: async () => {
      if (!apiClient) throw new Error("API client not initialized");
      if (!jobId) return null;
      const response = await apiClient.GET("/api/jobs/{job_id}", {
        params: { path: { job_id: jobId } },
      });
      if (response.error) throw new Error("Failed to fetch job");
      return response.data;
    },
    enabled: !!jobId,
    refetchInterval: 2000, // Polling every 2 seconds
  });
}

/**
 * Hook para cancelar un job (POST /api/jobs/{id}/cancel)
 */
export function useCancelJob() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    components["schemas"]["JobOut"],
    Error,
    string
  >({
    mutationFn: async (jobId) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.POST("/api/jobs/{job_id}/cancel", {
        params: { path: { job_id: jobId } },
      });
      if (response.error) throw new Error("Failed to cancel job");
      return response.data as components["schemas"]["JobOut"];
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}