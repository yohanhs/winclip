"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ClipOut,
  ClipUpdate,
  ClipWordsOut,
  JobOut,
} from "@winclip/api-client";

import { useApiClient } from "./use-api-client";

/** Palabras del tramo de un clip con sus overrides aplicados (`GET /api/clips/{id}/words`). */
export function useClipWords(
  clipId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  const api = useApiClient();
  return useQuery<ClipWordsOut>({
    queryKey: ["clip-words", clipId],
    queryFn: async () => {
      if (!clipId) throw new Error("Falta el id del clip");
      const { data } = await api.GET("/api/clips/{clip_id}/words", {
        params: { path: { clip_id: clipId } },
      });
      if (!data) {
        throw new Error("No se pudieron cargar las palabras del clip");
      }
      return data;
    },
    enabled: Boolean(clipId) && (options?.enabled ?? true),
  });
}

/** Clips de un proyecto, ordenados por score por el backend. */
export function useProjectClips(projectId: string | null | undefined) {
  const api = useApiClient();
  return useQuery<ClipOut[]>({
    queryKey: ["project-clips", projectId],
    queryFn: async () => {
      if (!projectId) throw new Error("Falta el id del proyecto");
      const { data } = await api.GET("/api/projects/{project_id}/clips", {
        params: { path: { project_id: projectId } },
      });
      return data ?? [];
    },
    enabled: Boolean(projectId),
    refetchInterval: 20_000,
  });
}

function useInvalidateClip(projectId: string | null | undefined) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({
      queryKey: ["project-clips", projectId],
    });
    void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
  };
}

/** `PATCH /api/clips/{id}`: título, descripción, hashtags, tiempos y overrides. */
export function useUpdateClip(projectId: string | null | undefined) {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateClip(projectId);

  return useMutation<ClipOut, Error, { clipId: string; data: ClipUpdate }>({
    mutationFn: async ({ clipId, data }) => {
      const response = await api.PATCH("/api/clips/{clip_id}", {
        params: { path: { clip_id: clipId } },
        body: data,
      });
      if (!response.data) throw new Error("No se pudo actualizar el clip");
      return response.data;
    },
    onSuccess: (_clip, { clipId }) => {
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ["clip-words", clipId] });
    },
  });
}

/** `DELETE /api/clips/{id}`. */
export function useDeleteClip(projectId: string | null | undefined) {
  const api = useApiClient();
  const invalidate = useInvalidateClip(projectId);

  return useMutation<void, Error, string>({
    mutationFn: async (clipId) => {
      await api.DELETE("/api/clips/{clip_id}", {
        params: { path: { clip_id: clipId } },
      });
    },
    onSuccess: invalidate,
  });
}

/** `POST /api/clips/{id}/rerender` tras recortar o cambiar tiempos. */
export function useRerenderClip(projectId: string | null | undefined) {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<JobOut, Error, string>({
    mutationFn: async (clipId) => {
      const response = await api.POST("/api/clips/{clip_id}/rerender", {
        params: { path: { clip_id: clipId } },
      });
      if (!response.data) throw new Error("No se pudo re-renderizar el clip");
      return response.data;
    },
    onSuccess: (_job, clipId) => {
      if (projectId) {
        queryClient.setQueryData<ClipOut[]>(
          ["project-clips", projectId],
          (clips) =>
            clips?.map((clip) =>
              clip.id === clipId ? { ...clip, status: "rendering" } : clip,
            ),
        );
        void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      }
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

/** `POST /api/jobs/{id}/cancel`: cancela el trabajo activo del proyecto. */
export function useCancelJob(projectId: string | null | undefined) {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<JobOut, Error, string>({
    mutationFn: async (jobId) => {
      const response = await api.POST("/api/jobs/{job_id}/cancel", {
        params: { path: { job_id: jobId } },
      });
      if (!response.data) throw new Error("No se pudo cancelar el trabajo");
      return response.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
