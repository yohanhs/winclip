import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ProjectList } from "@/components/projects/project-list";
import { makeProject } from "./mocks/fixtures";

const mocks = vi.hoisted(() => ({
  useProjects: vi.fn(),
  deleteMutate: vi.fn(),
}));

vi.mock("@/hooks/use-projects", () => ({
  useProjects: mocks.useProjects,
  useDeleteProject: () => ({
    mutate: mocks.deleteMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-project-events", () => ({
  useProjectEvents: () => ({ connected: true }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("next/link", () => ({
  default: function MockLink({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
}));

const PROJECTS = [
  makeProject({
    id: "proj-es",
    title: "Finanzas en español",
    language: "es",
    status: "ready",
    clips_count: 4,
  }),
  makeProject({
    id: "proj-en",
    title: "Money in English",
    language: "en",
    status: "processing",
    clips_count: 2,
    active_job: {
      id: "job-en",
      type: "pipeline",
      status: "running",
      progress: 55,
      stage: "transcribe",
      error: null,
      created_at: "2026-01-01T10:00:00Z",
      updated_at: "2026-01-01T10:00:00Z",
    },
  }),
  makeProject({
    id: "proj-auto",
    title: "Detección automática",
    language: "auto",
    status: "failed",
    clips_count: 0,
    active_job: null,
  }),
];

function mockProjects(overrides: Record<string, unknown> = {}) {
  mocks.useProjects.mockReturnValue({
    data: PROJECTS,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
    ...overrides,
  });
}

describe("ProjectList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProjects();
  });

  it("muestra métricas reales de proyectos y clips", () => {
    render(<ProjectList />);
    expect(screen.getByText("Proyectos activos")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("1 procesando")).toBeInTheDocument();
    expect(screen.getByText("Completados")).toBeInTheDocument();
    expect(screen.getByText("En vivo")).toBeInTheDocument();
  });

  it("filtra por idioma normalizando a minúsculas", () => {
    render(<ProjectList />);
    expect(screen.getByText("Finanzas en español")).toBeInTheDocument();
    expect(screen.getByText("Money in English")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.queryByText("Finanzas en español")).not.toBeInTheDocument();
    expect(screen.getByText("Money in English")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "ES" }));
    expect(screen.getByText("Finanzas en español")).toBeInTheDocument();
    expect(screen.queryByText("Money in English")).not.toBeInTheDocument();
  });

  it("filtra por estado y permite volver a todos", () => {
    render(<ProjectList />);
    fireEvent.click(screen.getByRole("button", { name: "Con error" }));
    expect(screen.getByText("Detección automática")).toBeInTheDocument();
    expect(screen.queryByText("Money in English")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getAllByRole("button", { name: "Todos" })[0]!,
    );
    expect(screen.getByText("Money in English")).toBeInTheDocument();
  });

  it("busca por título", () => {
    render(<ProjectList />);
    fireEvent.change(screen.getByLabelText("Buscar proyectos"), {
      target: { value: "english" },
    });
    expect(screen.getByText("Money in English")).toBeInTheDocument();
    expect(screen.queryByText("Finanzas en español")).not.toBeInTheDocument();
  });

  it("elimina un proyecto desde la vista de lista con confirmación", () => {
    render(<ProjectList />);
    fireEvent.click(screen.getByLabelText("Vista de lista"));
    fireEvent.click(
      screen.getByRole("button", { name: "Eliminar Finanzas en español" }),
    );
    expect(screen.getByText("¿Eliminar este proyecto?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(mocks.deleteMutate).toHaveBeenCalledWith(
      "proj-es",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("muestra el estado vacío cuando no hay proyectos", () => {
    mockProjects({ data: [] });
    render(<ProjectList />);
    expect(screen.getByText("Aún no hay proyectos")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Crear el primero/i }),
    ).toHaveAttribute("href", "/projects/new");
  });

  it("muestra el error de la API con opción de reintentar", () => {
    const refetch = vi.fn();
    mockProjects({
      data: undefined,
      isError: true,
      error: new Error("connection refused"),
      refetch,
    });
    render(<ProjectList />);
    expect(
      screen.getByText(/No se pudieron cargar los proyectos/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Reintentar/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
