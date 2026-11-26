"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createApiClient } from "@winclip/api-client";

/**
 * Hook para obtener el cliente API tipado
 */
export function useApiClient() {
  const [client, setClient] = useState<ReturnType<typeof createApiClient> | null>(
    null
  );
  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    setClient(createApiClient(baseUrl));
  }, []);

  return client;
}

/**
 * Hook para health check - verifica GET /api/health real
 */
export function useHealth() {
  const apiClient = useApiClient();

  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.GET("/api/health");
      if (response.error) throw new Error("Health check failed");
      return response.data;
    },
    staleTime: 30_000, // 30 seconds cache
    retry: 3,
  });
}

/**
 * Hook para gestión de proyectos
 */
export function useProjects() {
  const apiClient = useApiClient();

  return useQuery({
    queryKey: ["projects"],
    queryFn: async () => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.GET("/api/projects");
      if (response.error) throw new Error("Failed to fetch projects");
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook para obtener presets de subtítulos
 */
export function usePresets() {
  const apiClient = useApiClient();

  return useQuery({
    queryKey: ["presets"],
    queryFn: async () => {
      if (!apiClient) throw new Error("API client not initialized");
      const response = await apiClient.GET("/api/presets");
      if (response.error) throw new Error("Failed to fetch presets");
      return response.data;
    },
    staleTime: 300_000, // 5 minutes cache
  });
}

/**
 * Hook para gestión de clips de un proyecto
 */
export function useProjectClips(projectId: string | undefined) {
  const apiClient = useApiClient();

  return useQuery({
    queryKey: ["projects", projectId, "clips"],
    queryFn: async () => {
      if (!apiClient) throw new Error("API client not initialized");
      if (!projectId) return [];
      const response = await apiClient.GET("/api/projects/{project_id}/clips", {
        params: { path: { project_id: projectId } },
      });
      if (response.error) throw new Error("Failed to fetch clips");
      return response.data;
    },
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

/**
 * Hook para escuchar eventos SSE de progreso de trabajos
 */
export function useProjectEvents(
  projectId: string | null,
  onEvent: (event: ProjectEvent) => void
) {
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;

  useEffect(() => {
    if (!projectId) return;

    const apiUrl =
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const url = `${apiUrl}/api/events?project_id=${projectId}`;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
      reconnectAttemptsRef.current = 0;
    };

    es.onerror = (error) => {
      console.error("SSE error:", error);
      setConnected(false);
      reconnectAttemptsRef.current += 1;

      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
      setTimeout(() => {
          // EventSource reconnects automatically on error
          // We just close and let it recreate
          es.close();
        }, 2000 * reconnectAttemptsRef.current);
      } else {
        es.close();
      }
    };

    es.addEventListener("job.progress", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      onEvent({ type: "job.progress", jobId: data.job_id, data: data.data });
    });

    es.addEventListener("job.done", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      onEvent({ type: "job.done", jobId: data.job_id });
    });

    es.addEventListener("job.failed", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      onEvent({
        type: "job.failed",
        jobId: data.job_id,
        error: data.data?.error,
      });
    });

    es.addEventListener("clip.ready", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      onEvent({ type: "clip.ready", clipId: data.clip_id });
    });

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [projectId, onEvent]);

  return { connected };
}

/**
 * Tipo para eventos de progreso
 */
export type ProjectEvent =
  | { type: "job.progress"; jobId: string; data: { progress: number } }
  | { type: "job.done"; jobId: string }
  | { type: "job.failed"; jobId: string; error?: string | null }
  | { type: "clip.ready"; clipId: string };