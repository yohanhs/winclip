"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient } from "./use-api-client";
import type { components } from "@winclip/api-client";

/**
 * Hook para crear un proyecto
 */
export function useCreateProject() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    components["schemas"]["ProjectCreated"],
    Error,
    FileCreationParams | URLCreationParams
  >({
    mutationFn: async (params) => {
      if (!apiClient) throw new Error("API client not initialized");

      if ("file" in params && params.file) {
        // Uso de XMLHttpRequest para progreso de upload
        return new Promise((resolve, reject) => {
          const formData = new FormData();
          formData.append("file", params.file);
          formData.append("source_type", "file");
          if (params.title) formData.append("title", params.title);
          if (params.requested_clips !== undefined)
            formData.append("requested_clips", String(params.requested_clips));
          if (params.language) formData.append("language", params.language);
          if (params.subtitle_preset)
            formData.append("subtitle_preset", params.subtitle_preset);
          if (params.reframe_mode)
            formData.append("reframe_mode", params.reframe_mode);
          if (params.campaign_id)
            formData.append("campaign_id", params.campaign_id);

          const xhr = new XMLHttpRequest();
          const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

          xhr.open("POST", `${baseUrl}/api/projects`);
          xhr.responseType = "json";

          xhr.onload = () => {
            if (xhr.status === 201) {
              resolve(xhr.response as components["schemas"]["ProjectCreated"]);
            } else {
              reject(new Error(`HTTP ${xhr.status}: ${JSON.stringify(xhr.response)}`));
            }
          };

          xhr.onerror = () => reject(new Error("Network error"));

          if (params.onProgress) {
            xhr.upload.onprogress = (e) => {
              if (e.lengthComputable) {
                params.onProgress!(e.loaded, e.total);
              }
            };
          }

          if (params.abortSignal) {
            params.abortSignal.addEventListener("abort", () => {
              xhr.abort();
            });
          }

          xhr.send(formData);
        });
      } else {
        // URL-based creation
        const response = await apiClient.POST("/api/projects", {
          body: {
            source_type: "url",
            source_url: (params as URLCreationParams).source_url,
            title: params.title,
            requested_clips: params.requested_clips as number | "max" | undefined,
            language: params.language,
            campaign_id: params.campaign_id,
            subtitle_preset: params.subtitle_preset,
            reframe_mode: params.reframe_mode,
          },
        });

        if (response.error || !response.data) throw new Error("Failed to create project");
        return response.data;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

/**
 * Hook para eliminar un proyecto
 */
export function useDeleteProject() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (projectId: string) => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.DELETE("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      });
      if (response.error) throw new Error("Failed to delete project");
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

type BaseCreationParams = {
  title?: string;
  requested_clips?: number | "max";
  language?: "auto" | "es" | "en";
  subtitle_preset?: string;
  reframe_mode?: "face" | "center" | "blur" | "passthrough";
  campaign_id?: string;
};

export type URLCreationParams = BaseCreationParams & {
  source_url: string;
  file?: never;
};

export type FileCreationParams = BaseCreationParams & {
  file: File;
  onProgress?: (loaded: number, total: number) => void;
  abortSignal?: AbortSignal;
};