import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { ProjectCreateForm } from "@/components/projects/project-create-form";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  push: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastMessage: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn(), refresh: vi.fn() }),
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

vi.mock("@/hooks/use-projects", () => ({
  useCreateProject: () => ({ mutate: mocks.mutate, isPending: false }),
  usePresets: () => ({
    data: [],
    isLoading: false,
  }),
}));

vi.mock("@/hooks/use-campaigns", () => ({
  useCampaigns: () => ({
    data: [
      {
        id: "camp-1",
        workspace_id: "ws-1",
        name: "Finanzas ES",
        rules: {
          name: "Finanzas ES",
          language: "es",
          min_duration: 20,
          max_duration: 55,
          max_clips: 7,
          priority_topics: [],
          banned_topics: [],
          banned_words: ["garantizado"],
          required_keywords: [],
          tone: null,
          hook_max_seconds: 3,
          cta_text: null,
          hashtags: ["#finanzas"],
          subtitle_preset: "hormozi",
          watermark_path: null,
          target_platforms: ["youtube"],
          extra_instructions: null,
        },
        source_text: null,
        projects_count: 0,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("sonner", () => ({
  toast: {
    error: mocks.toastError,
    success: mocks.toastSuccess,
    message: mocks.toastMessage,
  },
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({
    value,
    onValueChange,
    disabled,
    children,
  }: {
    value?: string;
    onValueChange?: (value: string) => void;
    disabled?: boolean;
    children: React.ReactNode;
  }) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(event) => onValueChange?.(event.target.value)}
    >
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value }: { value: string; children: React.ReactNode }) => (
    <option value={value}>{value}</option>
  ),
}));

function fillUrl(value: string) {
  fireEvent.change(screen.getByLabelText("Enlace del vídeo"), {
    target: { value },
  });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /Generar clips/i }));
}

describe("ProjectCreateForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza el layout de dos columnas con preview 9:16", () => {
    render(<ProjectCreateForm />);
    expect(
      screen.getAllByText("Previsualización 9:16").length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: "URL" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Subir archivo/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Bold Yellow")).toBeInTheDocument();
  });

  it("envía los IDs reales del backend con los valores por defecto", () => {
    render(<ProjectCreateForm />);
    fillUrl("https://www.youtube.com/watch?v=abc123");
    submit();

    expect(mocks.mutate).toHaveBeenCalledTimes(1);
    const [variables] = mocks.mutate.mock.calls[0]!;
    expect(variables.input).toMatchObject({
      source_url: "https://www.youtube.com/watch?v=abc123",
      requested_clips: 5,
      language: "auto",
      subtitle_preset: "bold-yellow",
      reframe_mode: "face",
    });
  });

  it("envía requested_clips='max' al activar Máximo posible", () => {
    render(<ProjectCreateForm />);
    fillUrl("https://example.com/video.mp4");
    fireEvent.click(screen.getByRole("switch", { name: "Máximo posible" }));
    submit();

    const [variables] = mocks.mutate.mock.calls[0]!;
    expect(variables.input.requested_clips).toBe("max");
  });

  it("habilita el selector de campaña y pre-rellena clips, idioma y preset", () => {
    render(<ProjectCreateForm />);
    const selects = screen.getAllByRole("combobox");
    expect(selects).toHaveLength(3);
    const campaignSelect = selects[2]!;
    expect(campaignSelect).not.toBeDisabled();

    fireEvent.change(campaignSelect, { target: { value: "camp-1" } });
    fillUrl("https://example.com/video.mp4");
    submit();

    const [variables] = mocks.mutate.mock.calls[0]!;
    expect(variables.input.campaign_id).toBe("camp-1");
    expect(variables.input.requested_clips).toBe(7);
    expect(variables.input.language).toBe("es");
    expect(variables.input.subtitle_preset).toBe("hormozi");
  });

  it("valida la URL antes de llamar a la API", () => {
    render(<ProjectCreateForm />);
    fillUrl("no-es-una-url");
    submit();

    expect(mocks.mutate).not.toHaveBeenCalled();
    expect(mocks.toastError).toHaveBeenCalledWith(
      "URL no válida",
      expect.anything(),
    );
  });

  it("redirige al detalle del proyecto al crearlo", () => {
    mocks.mutate.mockImplementation(
      (
        _variables: unknown,
        options: { onSuccess: (created: unknown) => void },
      ) => {
        options.onSuccess({ project: { id: "proj-nuevo" } });
      },
    );
    render(<ProjectCreateForm />);
    fillUrl("https://example.com/video.mp4");
    submit();

    expect(mocks.push).toHaveBeenCalledWith("/projects/proj-nuevo");
  });

  it("permite subir un archivo y lo incluye en el payload", async () => {
    render(<ProjectCreateForm />);
    const fileTab = screen.getByRole("tab", { name: /Subir archivo/i });
    fireEvent.mouseDown(fileTab, { button: 0 });
    fireEvent.click(fileTab);

    const file = new File(["video"], "demo.mp4", { type: "video/mp4" });
    fireEvent.change(
      await screen.findByLabelText("Seleccionar archivo de vídeo"),
      { target: { files: [file] } },
    );

    await waitFor(() => {
      expect(screen.getByText("demo.mp4")).toBeInTheDocument();
    });

    submit();
    const [variables] = mocks.mutate.mock.calls[0]!;
    expect(variables.input.file).toBe(file);
    expect(variables.input.source_url).toBeUndefined();
    expect(variables.signal).toBeInstanceOf(AbortSignal);
  });

  it("muestra notificación de error cuando la API falla sin perder los valores", () => {
    mocks.mutate.mockImplementation(
      (
        _variables: unknown,
        options: { onError: (error: Error) => void },
      ) => {
        options.onError(new Error("API 422: preset inválido"));
      },
    );
    render(<ProjectCreateForm />);
    fillUrl("https://example.com/video.mp4");
    submit();

    expect(mocks.toastError).toHaveBeenCalledWith(
      "No se pudo crear el proyecto",
      expect.objectContaining({ description: "API 422: preset inválido" }),
    );
    expect(screen.getByLabelText("Enlace del vídeo")).toHaveValue(
      "https://example.com/video.mp4",
    );
  });
});
