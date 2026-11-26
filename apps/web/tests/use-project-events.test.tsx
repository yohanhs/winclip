import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useProjectEvents, type ProjectEvent } from "@/hooks/use-project-events";
import { makeJob, makeProject } from "./mocks/fixtures";

type Listener = (event: MessageEvent<string>) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, Set<Listener>>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: EventListener) {
    const set = this.listeners.get(name) ?? new Set<Listener>();
    set.add(listener as Listener);
    this.listeners.set(name, set);
  }

  removeEventListener(name: string, listener: EventListener) {
    this.listeners.get(name)?.delete(listener as Listener);
  }

  close() {
    this.closed = true;
  }

  emit(name: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    this.listeners.get(name)?.forEach((listener) => listener(event));
  }
}

function Harness({
  projectId,
  onEvent,
}: {
  projectId: string | null;
  onEvent?: (event: ProjectEvent) => void;
}) {
  useProjectEvents(projectId, { onEvent });
  return null;
}

function setup(projectId: string | null, onEvent?: (event: ProjectEvent) => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <Harness projectId={projectId} onEvent={onEvent} />
    </QueryClientProvider>,
  );
  return { queryClient, ...view };
}

const progressPayload = {
  job_id: "job-1",
  project_id: "proj-1",
  type: "pipeline",
  status: "running",
  progress: 42,
  stage: "transcribe",
};

describe("useProjectEvents", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("conecta al stream global sin filtro de proyecto", async () => {
    setup(null);
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(MockEventSource.instances[0]!.url).toBe(
      "http://localhost:8000/api/events",
    );
  });

  it("filtra el stream por project_id", async () => {
    setup("proj-1");
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(MockEventSource.instances[0]!.url).toContain("project_id=proj-1");
  });

  it("actualiza el progreso del proyecto en la caché", async () => {
    const { queryClient } = setup("proj-1");
    const activeJob = makeJob({ id: "job-1", progress: 10, stage: "ingest" });
    queryClient.setQueryData(["project", "proj-1"], makeProject({
      id: "proj-1",
      status: "processing",
      active_job: activeJob,
    }));
    queryClient.setQueryData(["projects"], [
      makeProject({ id: "proj-1", status: "processing", active_job: activeJob }),
    ]);

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0]!.emit("job.progress", progressPayload);
    });

    const project = queryClient.getQueryData<ReturnType<typeof makeProject>>([
      "project",
      "proj-1",
    ]);
    expect(project?.active_job?.progress).toBe(42);
    expect(project?.active_job?.stage).toBe("transcribe");
  });

  it("invalida los clips cuando llega clip.ready", async () => {
    const { queryClient } = setup("proj-1");
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0]!.emit("clip.ready", {
        project_id: "proj-1",
        job_id: "job-1",
        clip_id: "clip-1",
        status: "rendered",
        thumb_url: "/api/clips/clip-1/thumb",
        video_url: "/api/clips/clip-1/file",
      });
    });

    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["project-clips", "proj-1"],
    });
  });

  it("no reconecta cuando cambia la identidad del callback", async () => {
    const first = vi.fn();
    const { queryClient, rerender } = setup("proj-1", first);
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));

    const second = vi.fn();
    rerender(
      <QueryClientProvider client={queryClient}>
        <Harness projectId="proj-1" onEvent={second} />
      </QueryClientProvider>,
    );

    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("cierra la conexión al desmontar", async () => {
    const { unmount } = setup("proj-1");
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    unmount();
    expect(MockEventSource.instances[0]!.closed).toBe(true);
  });

  it("actualiza el estado a ready e invalida al recibir job.done", async () => {
    const { queryClient } = setup("proj-1");
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const activeJob = makeJob({ id: "job-1", progress: 80, stage: "render" });
    queryClient.setQueryData(
      ["project", "proj-1"],
      makeProject({ id: "proj-1", status: "processing", active_job: activeJob }),
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0]!.emit("job.done", {
        job_id: "job-1",
        project_id: "proj-1",
        type: "pipeline",
        status: "done",
        progress: 100,
        stage: "done",
      });
    });

    const project = queryClient.getQueryData<ReturnType<typeof makeProject>>([
      "project",
      "proj-1",
    ]);
    expect(project?.status).toBe("ready");
    expect(project?.active_job).toBeNull();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["project", "proj-1"] });
  });

  it("marca error en el proyecto al recibir job.failed", async () => {
    const { queryClient } = setup("proj-1");
    const activeJob = makeJob({ id: "job-1", progress: 30, stage: "transcribe" });
    queryClient.setQueryData(
      ["project", "proj-1"],
      makeProject({ id: "proj-1", status: "processing", active_job: activeJob }),
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0]!.emit("job.failed", {
        job_id: "job-1",
        project_id: "proj-1",
        type: "pipeline",
        status: "failed",
        progress: 30,
        stage: "transcribe",
        error: "Error en Whisper",
      });
    });

    const project = queryClient.getQueryData<ReturnType<typeof makeProject>>([
      "project",
      "proj-1",
    ]);
    expect(project?.status).toBe("failed");
    expect(project?.latest_job?.error).toBe("Error en Whisper");
  });
});
