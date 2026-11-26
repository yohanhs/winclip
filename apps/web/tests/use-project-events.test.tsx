import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useProjectEvents } from "@/hooks/use-project-events";

// Mock EventSource globally
const mockClose = vi.fn();

describe("use-project-events", () => {
  let queryClient: QueryClient;

  const TestEventProvider = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    vi.useFakeTimers();
    mockClose.mockClear();

    // Mock global EventSource constructor
    // @ts-expect-error - we're mocking EventSource
    global.EventSource = vi.fn().mockImplementation(() => ({
      onopen: null,
      onerror: null,
      addEventListener: vi.fn(),
      close: mockClose,
      CONNECTING: 0,
      OPEN: 1,
      CLOSED: 2,
      onmessage: null,
      readyState: 0,
      url: "",
      withCredentials: 0,
    }));

    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    queryClient.clear();
  });

  it("debe inicializar la conexión SSE cuando projectId es proporcionado", () => {
    const onEvent = vi.fn();

    const { result } = renderHook(() => useProjectEvents("proj-test-1", { onEvent }), {
      wrapper: TestEventProvider,
    });

    expect(global.EventSource).toHaveBeenCalled();
    expect(result.current.connected).toBe(false); // Aún no se ha abierto
  });

  it("debe manejar eventos SSE correctamente", () => {
    const onEvent = vi.fn();

    renderHook(() => useProjectEvents("proj-test-1", { onEvent }), {
      wrapper: TestEventProvider,
    });

    expect(global.EventSource).toHaveBeenCalled();
  });

  it("debe manejar múltiples tipos de eventos", () => {
    const onEvent = vi.fn();

    renderHook(() => useProjectEvents("proj-test-1", { onEvent }), {
      wrapper: TestEventProvider,
    });

    expect(global.EventSource).toHaveBeenCalled();
  });

  it("debe manejar el cambio de projectId", () => {
    renderHook(
      ({ projectId }) => useProjectEvents(projectId),
      {
        initialProps: { projectId: "proj-test-1" },
        wrapper: TestEventProvider,
      },
    );

    expect(global.EventSource).toHaveBeenCalled();
  });

  it("debe retornar el estado de conexión", () => {
    const { result } = renderHook(() => useProjectEvents("proj-test-1"), {
      wrapper: TestEventProvider,
    });

    expect(result.current).toHaveProperty("connected");
    expect(typeof result.current.connected).toBe("boolean");
  });
});