"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProjectFormData,
  getApiBaseUrl,
  uploadProjectWithProgress,
  type CreateProjectResponse,
  type ProjectFormDataInput,
  type ProjectOut,
  type SubtitlePreset,
  type UploadProgress,
} from "@winclip/api-client";

import { useApiClient } from "./use-api-client";

export type CreateProjectInput = Omit<ProjectFormDataInput, "file"> & {
  file?: File | null;
};

export interface CreateProjectVariables {
  input: CreateProjectInput;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}

/** Lista de proyectos con refresco de respaldo (SSE es la vía principal). */
export function useProjects() {
  const api = useApiClient();
  return useQuery<ProjectOut[]>({
    queryKey: ["projects"],
    queryFn: async () => {
      const { data } = await api.GET("/api/projects");
      return data ?? [];
    },
    refetchInterval: 20_000,
  });
}

/** Detalle de un proyecto. */
export function useProject(projectId: string | null | undefined) {
  const api = useApiClient();
  return useQuery<ProjectOut>({
    queryKey: ["project", projectId],
    queryFn: async () => {
      if (!projectId) throw new Error("Falta el id del proyecto");
      const { data } = await api.GET("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      });
      if (!data) throw new Error("Proyecto no encontrado");
      return data;
    },
    enabled: Boolean(projectId),
    refetchInterval: 20_000,
  });
}

/** Catálogo real de presets de subtítulos (`GET /api/presets`). */
export function usePresets() {
  const api = useApiClient();
  return useQuery<SubtitlePreset[]>({
    queryKey: ["presets"],
    queryFn: async () => {
      const { data } = await api.GET("/api/presets");
      return data ?? [];
    },
    staleTime: 5 * 60_000,
  });
}

/** Crea un proyecto (JSON para URL, multipart con progreso para archivo). */
export function useCreateProject() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<CreateProjectResponse, Error, CreateProjectVariables>({
    mutationFn: async ({ input, onProgress, signal }) => {
      if (input.file) {
        const formData = createProjectFormData({
          file: input.file,
          requested_clips: input.requested_clips,
          language: input.language,
          subtitle_preset: input.subtitle_preset,
          reframe_mode: input.reframe_mode,
          campaign_id: input.campaign_id,
          title: input.title,
        });
        return uploadProjectWithProgress(
          getApiBaseUrl(),
          formData,
          onProgress,
          signal,
        );
      }

      if (!input.source_url) {
        throw new Error("Debes indicar una URL o un archivo de vídeo");
      }

      const { data } = await api.POST("/api/projects", {
        body: {
          source_type: "url",
          source_url: input.source_url,
          title: input.title,
          requested_clips: input.requested_clips,
          language: input.language,
          subtitle_preset: input.subtitle_preset,
          reframe_mode: input.reframe_mode,
          campaign_id: input.campaign_id,
        },
        signal,
      });
      if (!data) {
        throw new Error("Respuesta vacía al crear el proyecto");
      }
      return data;
    },
    onSuccess: (created) => {
      queryClient.setQueryData<ProjectOut>(
        ["project", created.project.id],
        created.project,
      );
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

/** Elimina un proyecto y purga sus cachés asociadas. */
export function useDeleteProject() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (projectId) => {
      await api.DELETE("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      });
    },
    onSuccess: (_data, projectId) => {
      queryClient.removeQueries({ queryKey: ["project", projectId] });
      queryClient.removeQueries({ queryKey: ["project-clips", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
