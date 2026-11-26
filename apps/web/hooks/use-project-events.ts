"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "@winclip/api-client";

/**
 * Tipos de eventos SSE
 */
export type ProjectEvent =
  | { type: "job.progress"; job_id: string; data: { progress: number } }
  | { type: "job.done"; job_id: string }
  | { type: "job.failed"; job_id: string; error?: string | null }
  | { type: "clip.ready"; clip_id: string }
  | { type: "clip.failed"; clip_id: string; error?: string | null };

/**
 * Hook para escuchar eventos SSE de progreso de trabajos
 * Actualiza la caché de TanStack Query según los eventos recibidos
 */
export function useProjectEvents(
  projectId: string | null,
  options?: {
    onEvent?: (event: ProjectEvent) => void;
    onError?: (error: Error) => void;
  }
) {
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  const queryClient = useQueryClient();

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

      if (options?.onError) {
        options.onError(new Error("SSE connection error"));
      }

      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        setTimeout(() => {
          es.close();
          eventSourceRef.current = new EventSource(url);
        }, 2000 * reconnectAttemptsRef.current);
      } else {
        es.close();
        eventSourceRef.current = null;
      }
    };

    es.addEventListener("job.progress", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as { job_id: string; progress: number };
      
      // Actualizar la caché del job
      queryClient.setQueryData(["jobs", data.job_id], (old: components["schemas"]["JobOut"] | undefined) => {
        if (!old) return undefined;
        return {
          ...old,
          progress: data.progress,
          status: data.progress < 100 ? "running" : "done",
          updated_at: new Date().toISOString(),
        };
      });

      options?.onEvent?.({ type: "job.progress", job_id: data.job_id, data });
    });

    es.addEventListener("job.done", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as { job_id: string };
      
      queryClient.setQueryData(["jobs", data.job_id], (old: components["schemas"]["JobOut"] | undefined) => {
        if (!old) return undefined;
        return {
          ...old,
          status: "done",
          progress: 100,
          finished_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      });

      options?.onEvent?.({ type: "job.done", job_id: data.job_id });
    });

    es.addEventListener("job.failed", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as { job_id: string; error?: string | null };
      
      queryClient.setQueryData(["jobs", data.job_id], (old: components["schemas"]["JobOut"] | undefined) => {
        if (!old) return undefined;
        return {
          ...old,
          status: "failed",
          error: data.error || "Unknown error",
          finished_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      });

      options?.onEvent?.({ type: "job.failed", job_id: data.job_id, error: data.error });
    });

    es.addEventListener("clip.ready", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as { clip_id: string };
      
      // Invalidar clips para forzar refresco
      queryClient.invalidateQueries({ queryKey: ["clips"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });

      options?.onEvent?.({ type: "clip.ready", clip_id: data.clip_id });
    });

    es.addEventListener("clip.failed", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as { clip_id: string; error?: string | null };
      
      options?.onEvent?.({ type: "clip.failed", clip_id: data.clip_id, error: data.error });
    });

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [projectId, options, queryClient]);

  return { connected };
}