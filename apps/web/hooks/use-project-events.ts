"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { ProjectOut, SsePublicationUpdated } from "@winclip/api-client";
import { toast } from "sonner";

import { API_URL } from "@/lib/api";

export interface JobEventPayload {
  job_id: string;
  project_id: string | null;
  type: string;
  status: string;
  progress: number;
  stage: string;
  error?: string | null;
}

export interface ClipReadyPayload {
  project_id: string;
  job_id: string;
  clip_id: string;
  status: string;
  thumb_url?: string | null;
  video_url?: string | null;
}

export type ProjectEvent =
  | { type: "job.progress"; payload: JobEventPayload }
  | { type: "job.done"; payload: JobEventPayload }
  | { type: "job.failed"; payload: JobEventPayload }
  | { type: "clip.ready"; payload: ClipReadyPayload }
  | { type: "publication.updated"; payload: SsePublicationUpdated }
  | { type: "heartbeat"; payload: { ts: string } };

interface UseProjectEventsOptions {
  onEvent?: (event: ProjectEvent) => void;
  enabled?: boolean;
  silent?: boolean;
}

function deriveProjectStatus(
  currentStatus: string,
  payload: JobEventPayload,
): string {
  if (payload.type !== "pipeline") return currentStatus;
  if (payload.status === "done") return "ready";
  if (payload.status === "failed") return "failed";
  if (payload.status === "cancelled" || payload.status === "canceled") {
    return "cancelled";
  }
  if (payload.status === "running") return "processing";
  return currentStatus;
}

function patchProject(
  project: ProjectOut,
  payload: JobEventPayload,
): ProjectOut {
  if (payload.project_id && project.id !== payload.project_id) return project;
  const isActive = project.active_job?.id === payload.job_id;
  const isLatest = project.latest_job?.id === payload.job_id;
  const matchesProject = Boolean(payload.project_id && project.id === payload.project_id);
  if (!isActive && !isLatest && !matchesProject) return project;

  const patchJob = <T extends { progress: number; stage: string; status: string }>(
    job: T,
  ): T => ({
    ...job,
    progress: payload.progress,
    stage: payload.stage,
    status: payload.status,
  });

  const isTerminal =
    payload.status === "done" ||
    payload.status === "failed" ||
    payload.status === "cancelled" ||
    payload.status === "canceled";

  const nextLatestJob =
    isLatest && project.latest_job
      ? {
          ...patchJob(project.latest_job),
          error: payload.error ?? project.latest_job.error,
        }
      : isActive && project.active_job
        ? {
            ...patchJob(project.active_job),
            error: payload.error ?? project.active_job.error,
          }
        : project.latest_job;

  return {
    ...project,
    status: deriveProjectStatus(project.status, payload),
    active_job:
      isActive && project.active_job
        ? isTerminal
          ? null
          : {
              ...patchJob(project.active_job),
              error: payload.error ?? project.active_job.error,
            }
        : project.active_job,
    latest_job: nextLatestJob,
  };
}

function applyJobEvent(
  queryClient: QueryClient,
  projectId: string | null,
  payload: JobEventPayload,
) {
  queryClient.setQueryData<ProjectOut[]>(["projects"], (projects) =>
    projects?.map((project) => patchProject(project, payload)),
  );
  if (payload.project_id) {
    queryClient.setQueryData<ProjectOut>(
      ["project", payload.project_id],
      (project) => (project ? patchProject(project, payload) : project),
    );
  }
  if (projectId && projectId !== payload.project_id) {
    queryClient.setQueryData<ProjectOut>(
      ["project", projectId],
      (project) => (project ? patchProject(project, payload) : project),
    );
  }
}

function invalidateProjectData(
  queryClient: QueryClient,
  projectId: string | null,
) {
  void queryClient.invalidateQueries({ queryKey: ["projects"] });
  if (projectId) {
    void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["project-clips", projectId] });
  }
}

/**
 * Suscripción SSE a `GET /api/events`.
 *
 * Con `projectId = null` escucha todos los proyectos (vista de listado); con un
 * id concreto filtra el stream y actualiza la caché de ese proyecto. Los
 * callbacks se guardan en una ref para que cambiar su identidad no reconecte.
 */
export function useProjectEvents(
  projectId: string | null,
  options?: UseProjectEventsOptions,
) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(options?.onEvent);
  const silentRef = useRef(options?.silent ?? false);
  const hadErrorRef = useRef(false);
  const enabled = options?.enabled ?? true;

  useEffect(() => {
    onEventRef.current = options?.onEvent;
    silentRef.current = options?.silent ?? false;
  }, [options?.onEvent, options?.silent]);

  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    const url = new URL("/api/events", API_URL);
    if (projectId) url.searchParams.set("project_id", projectId);

    const source = new EventSource(url.toString());
    const listeners: Array<[string, EventListener]> = [];

    const listen = (name: string, handler: (payload: unknown) => void) => {
      const listener: EventListener = (event) => {
        const message = event as MessageEvent<string>;
        let payload: unknown;
        try {
          payload = JSON.parse(message.data);
        } catch {
          return;
        }
        handler(payload);
      };
      source.addEventListener(name, listener);
      listeners.push([name, listener]);
    };

    const emit = (event: ProjectEvent) => {
      onEventRef.current?.(event);
    };

    listen("job.progress", (payload) => {
      const data = payload as JobEventPayload;
      applyJobEvent(queryClient, projectId, data);
      emit({ type: "job.progress", payload: data });
    });

    listen("job.done", (payload) => {
      const data = payload as JobEventPayload;
      applyJobEvent(queryClient, projectId, data);
      invalidateProjectData(queryClient, projectId ?? data.project_id);
      if (!silentRef.current) {
        toast.success(
          data.type === "render"
            ? "Clip re-renderizado"
            : "Procesamiento completado",
        );
      }
      emit({ type: "job.done", payload: data });
    });

    listen("job.failed", (payload) => {
      const data = payload as JobEventPayload;
      applyJobEvent(queryClient, projectId, data);
      invalidateProjectData(queryClient, projectId ?? data.project_id);
      if (!silentRef.current) {
        toast.error("El procesamiento ha fallado", {
          description: data.error ?? undefined,
        });
      }
      emit({ type: "job.failed", payload: data });
    });

    listen("clip.ready", (payload) => {
      const data = payload as ClipReadyPayload;
      invalidateProjectData(queryClient, projectId ?? data.project_id);
      if (!silentRef.current) {
        toast.message("Nuevo clip listo");
      }
      emit({ type: "clip.ready", payload: data });
    });

    listen("publication.updated", (payload) => {
      const data = payload as SsePublicationUpdated;
      void queryClient.invalidateQueries({ queryKey: ["publications"] });
      void queryClient.invalidateQueries({ queryKey: ["publications-quota"] });
      emit({ type: "publication.updated", payload: data });
    });

    listen("heartbeat", (payload) => {
      setConnected(true);
      emit({ type: "heartbeat", payload: payload as { ts: string } });
    });

    source.onopen = () => {
      setConnected(true);
      if (hadErrorRef.current) {
        hadErrorRef.current = false;
        invalidateProjectData(queryClient, projectId);
      }
    };
    source.onerror = () => {
      hadErrorRef.current = true;
      setConnected(false);
    };

    return () => {
      for (const [name, listener] of listeners) {
        source.removeEventListener(name, listener);
      }
      source.close();
      setConnected(false);
    };
  }, [enabled, projectId, queryClient]);

  return { connected };
}
