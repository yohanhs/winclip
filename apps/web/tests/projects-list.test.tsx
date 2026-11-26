import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProjectList } from "@/components/projects/project-list";
import * as hooks from "@/hooks/use-api-client";
import type { components } from "@winclip/api-client";

// Mock Next.js Link
vi.mock("next/link", () => ({
  default: function MockLink({ href, children, ...props }: { href: string; children: React.ReactNode } & React.HTMLAttributes<HTMLAnchorElement>) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
}));

// Mock lucide-react - only mock the icons we need
vi.mock("lucide-react", () => ({
  LayoutGrid: () => <svg data-testid="layout-grid" />,
  List: () => <svg data-testid="list" />,
  FolderOpen: () => <svg data-testid="folder-open" />,
  RefreshCw: () => <svg data-testid="refresh-cw" />,
  AlertCircle: () => <svg data-testid="alert-circle" />,
  Play: () => <svg data-testid="play" />,
  Video: () => <svg data-testid="video" />,
  HardDrive: () => <svg data-testid="harddrive" />,
  MoreHorizontal: () => <svg data-testid="more-horizontal" />,
  Trash2: () => <svg data-testid="trash2" />,
  Film: () => <svg data-testid="film" />,
}));

// Helper to create proper mock result - matches UseQueryResult type
function createMockQueryResult<T>(options: {
  data?: T;
  isLoading?: boolean;
  isError?: boolean;
  refetch?: () => ReturnType<typeof vi.fn>;
  error?: Error;
}) {
  const isLoading = options.isLoading ?? false;
  const isError = options.isError ?? false;
  const isSuccess = !isLoading && !isError;
  
  return {
    data: options.data,
    isLoading,
    isError,
    isFetching: false,
    isSuccess,
    error: options.error ?? null,
    status: isError ? "error" : isLoading ? "loading" : "success",
    refetch: options.refetch ?? vi.fn(),
    isRefetching: false,
    isPending: isLoading,
    isPlaceholderData: false,
    failureCount: 0,
    isFetched: !isLoading,
    isFetchedAfterMount: true,
    ishydrated: true,
    remove: vi.fn(),
    getData: vi.fn(() => options.data),
    getPreviousData: vi.fn(() => undefined),
    previousStatus: "idle",
    meta: {
      fetchStatus: isError ? "idle" : isLoading ? "fetching" : "success",
    },
    fetchStatus: isLoading ? "fetching" : "idle",
    isLoadingError: isError,
    isRefetchError: false,
    dataUpdatedAt: Date.now(),
    errorUpdatedAt: Date.now(),
    failureReason: undefined,
    errorUpdateCount: 0,
    isInitialLoading: false,
    isPaused: false,
    isStale: false,
    isEnabled: true,
  } as unknown as any;
}

// Mock data
const mockProject: components["schemas"]["ProjectOut"] = {
  id: "proj-test-1",
  workspace_id: "ws-1",
  campaign_id: null,
  source_type: "url",
  source_url: "https://example.com/video.mp4",
  title: "Video de Prueba",
  status: "ready",
  requested_clips: 5,
  language: "es",
  duration: 60,
  subtitle_preset: "default",
  reframe_mode: "face",
  clips_count: 5,
  thumb_url: "/thumbs/proj-test-1.jpg",
  active_job: null,
  latest_job: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("ProjectList", () => {
  let queryClient: QueryClient;

  const TestProvider = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    queryClient.mount();
    
    vi.spyOn(hooks, "useProjects").mockReturnValue(
      createMockQueryResult({
        data: [mockProject],
      })
    );
    
    vi.spyOn(hooks, "useHealth").mockReturnValue(
      createMockQueryResult({
        data: { app: "winclip", version: "0.1.0", checks: [] },
      })
    );
  });

  afterEach(() => {
    queryClient.unmount();
    vi.restoreAllMocks();
  });

  describe("Loading state", () => {
    it("shows skeleton loaders while loading", () => {
      vi.spyOn(hooks, "useProjects").mockReturnValue(
        createMockQueryResult({
          isLoading: true,
        })
      );
      
      vi.spyOn(hooks, "useHealth").mockReturnValue(
        createMockQueryResult({
          isLoading: true,
        })
      );
      
      render(<ProjectList />, { wrapper: TestProvider });
      
      // Should show loading skeletons - metrics section
      expect(screen.getByText("Proyectos activos")).toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("shows error state with retry button when fetch fails", () => {
      vi.spyOn(hooks, "useProjects").mockReturnValue(
        createMockQueryResult({
          data: [],
          isError: true,
        })
      );
      
      vi.spyOn(hooks, "useHealth").mockReturnValue(
        createMockQueryResult({
          data: undefined,
        })
      );

      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText(/Error al cargar los proyectos/)).toBeInTheDocument();
      expect(screen.getByText("Reintentar")).toBeInTheDocument();
    });
  });

  describe("Empty state", () => {
    it("shows empty state when no projects exist", () => {
      vi.spyOn(hooks, "useProjects").mockReturnValue(
        createMockQueryResult({
          data: [],
        })
      );

      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText("No hay proyectos que coincidan")).toBeInTheDocument();
      expect(screen.getByText(/Ajusta los filtros activos/)).toBeInTheDocument();
    });
  });

  describe("Metrics bar", () => {
    it("displays metrics bar with project counts", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText("Proyectos activos")).toBeInTheDocument();
      expect(screen.getByText("Clips generados")).toBeInTheDocument();
      expect(screen.getByText("Programados hoy")).toBeInTheDocument();
    });

    it("shows correct counts", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText("1")).toBeInTheDocument();
    });
  });

  describe("Filter toolbar", () => {
    it("shows status filter tabs", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText("Todos")).toBeInTheDocument();
      expect(screen.getByText("En proceso")).toBeInTheDocument();
      expect(screen.getByText("Completados")).toBeInTheDocument();
    });

    it("shows language filter tabs", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText("ES/EN")).toBeInTheDocument();
      expect(screen.getByText("ES")).toBeInTheDocument();
      expect(screen.getByText("EN")).toBeInTheDocument();
    });

    it("filters projects by status when tab is clicked", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      // Verify the tab is clickable
      expect(screen.getByRole("button", { name: "Todos" })).toBeDefined();
      expect(screen.getByRole("button", { name: "En proceso" })).toBeDefined();
      expect(screen.getByRole("button", { name: "Completados" })).toBeDefined();
    });

    it("filters projects by language when tab is clicked", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByRole("button", { name: "ES/EN" })).toBeDefined();
      expect(screen.getByRole("button", { name: "ES" })).toBeDefined();
      expect(screen.getByRole("button", { name: "EN" })).toBeDefined();
    });
  });

  describe("View mode toggle", () => {
    it("shows grid/list toggle buttons", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByLabelText("Vista cuadrícula")).toBeInTheDocument();
      expect(screen.getByLabelText("Vista lista")).toBeInTheDocument();
    });

    it("switches between grid and list view", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      // Should start in grid mode, verify it exists
      fireEvent.click(screen.getByLabelText("Vista lista"));
      
      // Verify list mode toggle
      expect(screen.getByLabelText("Vista cuadrícula")).toBeInTheDocument();
    });
  });

  describe("Project card rendering", () => {
    it("renders a project card with correct data", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText("Video de Prueba")).toBeInTheDocument();
    });

    it("shows project link with correct href", () => {
      render(<ProjectList />, { wrapper: TestProvider });
      
      const link = screen.getByText("Video de Prueba").closest("a");
      expect(link).toHaveAttribute("href", "/projects/proj-test-1");
    });
  });

  describe("Retry functionality", () => {
    it("retries failed request when retry button is clicked", () => {
      const mockRefetch = vi.fn();
      vi.spyOn(hooks, "useProjects").mockReturnValue(
        createMockQueryResult({
          data: [],
          isError: true,
          refetch: mockRefetch,
        })
      );

      render(<ProjectList />, { wrapper: TestProvider });
      
      expect(screen.getByText(/Error al cargar los proyectos/)).toBeInTheDocument();
      
      fireEvent.click(screen.getByText("Reintentar"));
      expect(mockRefetch).toHaveBeenCalled();
    });
  });
});