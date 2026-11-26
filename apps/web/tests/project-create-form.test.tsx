import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProjectCreateForm } from "@/components/projects/project-create-form";

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

// Mock lucide-react
vi.mock("lucide-react", () => ({
  Video: () => <svg data-testid="video-icon" />,
  Upload: () => <svg data-testid="upload-icon" />,
  Music: () => <svg data-testid="music-icon" />,
  Settings: () => <svg data-testid="settings-icon" />,
  Users: () => <svg data-testid="users-icon" />,
  Globe: () => <svg data-testid="globe-icon" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
}));

// Mock the hooks - useApi client
vi.mock("@/hooks/use-api-client", () => ({
  useApiClient: () => ({
    GET: vi.fn().mockResolvedValue({ data: [], error: null }),
    POST: vi.fn().mockResolvedValue({ data: {}, error: null }),
  }),
  usePresets: () => ({
    data: [
      {
        id: "default",
        name: "Default",
        description: "Default preset",
        font: "Inter",
        fallback_font: "Arial",
        font_size: 24,
        uppercase: false,
        primary_color: "#FFFFFF",
        highlight_color: "#FFFF00",
        outline_color: "#000000",
        outline_width: 2,
        shadow_color: "#00000000",
        shadow_depth: 0,
        highlight_scale_pct: 100,
        y_pct: 85,
        margin_x: 20,
        max_lines: 2,
        max_chars_per_line: 40,
        max_words_per_cue: 8,
        max_pause_sec: 2,
        box_bg_color: null,
      },
    ],
    isLoading: false,
    isError: false,
  }),
  useProjects: () => ({
    data: [],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useHealth: () => ({
    data: { app: "winclip", version: "0.1.0", checks: [] },
    isLoading: false,
    isError: false,
  }),
  useProjectClips: () => ({
    data: [],
    isLoading: false,
    isError: false,
  }),
  useProjectEvents: () => ({ connected: false }),
}));

// Mock use-projects
vi.mock("@/hooks/use-projects", () => ({
  useCreateProject: () => ({
    mutateAsync: vi.fn().mockResolvedValue({
      project: { id: "new-project", title: "Test Project", status: "processing" },
      job: { id: "job-1", type: "download", status: "running" }
    }),
    isPending: false,
    isSuccess: true,
    isError: false,
    error: null,
  }),
  useDeleteProject: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
}));

// Types for mock component props
type FileDropzoneProps = {
  onFileSelected?: (file: File, previewUrl: string) => void;
  onUploadComplete?: (file: File, previewUrl: string) => void;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
};

type SubtitlePresetPreviewProps = {
  preset: "bold_yellow" | "hormozi" | "clean_white" | "mrbeast";
  presetData: {
    id: string;
    name: string;
    description: string;
    font: string;
    highlight_color: string;
    primary_color: string;
    box_bg_color?: string | null;
  };
  isPlaying?: boolean;
  onPlayToggle?: (playing: boolean) => void;
  className?: string;
};

type CardProps = { children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>;
type ButtonProps = { children: React.ReactNode; disabled?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>;
type SliderProps = { value?: number[]; onValueChange?: (value: number[]) => void } & React.HTMLAttributes<HTMLInputElement>;
type SelectProps = { children: React.ReactNode; value?: string; onValueChange?: (value: string) => void };

// Mock the child components
vi.mock("@/components/projects/file-dropzone", () => ({
  FileDropzone: ({ onFileSelected, onUploadComplete }: FileDropzoneProps) => (
    <div data-testid="file-dropzone">
      <button
        onClick={() =>
          onFileSelected?.(new File(["test"], "test.mp4", { type: "video/mp4" }), "test-url")
        }
        data-testid="mock-select-file"
      >
        Select File
      </button>
      <button
        onClick={() =>
          onUploadComplete?.(
            new File(["test"], "test.mp4", { type: "video/mp4" }),
            "test-url"
          )
        }
        data-testid="mock-upload-complete"
      >
        Upload Complete
      </button>
    </div>
  ),
}));

vi.mock("@/components/projects/subtitle-preset-preview", () => ({
  SubtitlePresetPreview: ({ preset }: SubtitlePresetPreviewProps) => (
    <div data-testid="subtitle-preset-preview">
      <span data-testid={`preset-${preset}`}>{preset}</span>
    </div>
  ),
}));

// Mock ui components - use unique testids for each instance
vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...props }: CardProps) => (
    <div data-testid="card" {...props}>
      {children}
    </div>
  ),
  CardContent: ({ children }: CardProps) => <div>{children}</div>,
  CardHeader: ({ children }: CardProps) => <div>{children}</div>,
  CardTitle: ({ children }: CardProps) => <h2>{children}</h2>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, disabled, ...props }: ButtonProps) => (
    <button disabled={disabled} {...props}>
      {children}
    </button>
  ),
}));

vi.mock("@/components/ui/slider", () => ({
  Slider: ({ value, onValueChange, ...props }: SliderProps) => (
    <input
      type="range"
      data-testid="slider"
      value={value?.[0] || 1}
      onChange={(e: React.ChangeEvent<HTMLInputElement>) => onValueChange?.([Number(e.target.value)])}
      {...props}
    />
  ),
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({ children, value, onValueChange, ...props }: SelectProps) => (
    <div data-testid="select-trigger" data-value={value || ""}>
      <input
        type="text"
        data-testid="select-input"
        value={value || ""}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onValueChange?.(e.target.value)}
      />
      {children}
    </div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, ...props }: { children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) => (
    <div {...props} data-testid="select-item">
      {children}
    </div>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="select-trigger-inner">{children}</div>
  ),
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}));

vi.mock("@/components/ui/input", () => ({
  Input: ({ id, value, onChange, ...props }: { id?: string; value?: string; onChange?: React.ChangeEventHandler<HTMLInputElement> } & React.HTMLAttributes<HTMLInputElement>) => (
    <input data-testid="input" id={id} value={value} onChange={onChange} {...props} />
  ),
}));

vi.mock("@/components/ui/label", () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}));

vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children, value, onValueChange, ...props }: { children: React.ReactNode; value?: string; onValueChange?: (value: string) => void }) => (
    <div data-testid="tabs">
      {children}
    </div>
  ),
  TabsContent: ({ children, value, ...props }: { children: React.ReactNode; value: string }) => (
    <div data-testid={`tabs-content-${value}`}>{children}</div>
  ),
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value, onClick, ...props }: { children: React.ReactNode; value: string; onClick?: React.MouseEventHandler<HTMLButtonElement> }) => (
    <button data-testid={`tabs-trigger-${value}`} onClick={onClick}>
      {children}
    </button>
  ),
}));

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialog: () => null,
  AlertDialogAction: () => null,
  AlertDialogCancel: () => null,
  AlertDialogContent: () => null,
  AlertDialogDescription: () => null,
  AlertDialogFooter: () => null,
  AlertDialogHeader: () => null,
  AlertDialogTitle: () => null,
  AlertDialogTrigger: () => null,
}));

describe("ProjectCreateForm", () => {
  const mockCampaigns = [
    {
      id: "campaign-1",
      name: "Test Campaign",
      language: "es",
      maxClips: 10,
      hookSeconds: 30,
      forbiddenWords: [],
      cta: "Call to action",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Initial rendering", () => {
    it("renders the form with all sections", () => {
      render(<ProjectCreateForm campaigns={mockCampaigns} />);

      expect(screen.getByText("1. Contenido fuente")).toBeInTheDocument();
      expect(screen.getByText("2. Selección IA y reglas de campaña")).toBeInTheDocument();
      expect(screen.getByText("3. Estilo de subtítulos")).toBeInTheDocument();
    });

    it("shows URL tab by default", () => {
      render(<ProjectCreateForm />);

      expect(screen.getByTestId("tabs-trigger-url")).toBeInTheDocument();
    });

    it("shows upload tab", () => {
      render(<ProjectCreateForm />);

      expect(screen.getByTestId("tabs-trigger-upload")).toBeInTheDocument();
    });
  });

  describe("URL Tab", () => {
    it("allows entering a video URL", async () => {
      render(<ProjectCreateForm />);

      // Get all inputs and change the first one (URL input)
      const inputs = screen.getAllByTestId("input");
      fireEvent.change(inputs[0]!, { target: { value: "https://youtube.com/watch?v=test123" } });

      expect(inputs[0]).toHaveValue("https://youtube.com/watch?v=test123");
    });

    it("allows entering a project title", async () => {
      render(<ProjectCreateForm />);

      // Get all inputs and change the second one (title input)
      const inputs = screen.getAllByTestId("input");
      fireEvent.change(inputs[1]!, { target: { value: "My Test Project" } });

      expect(inputs[1]).toHaveValue("My Test Project");
    });
  });

  describe("Upload Tab", () => {
    it("switches to upload tab when clicked", () => {
      render(<ProjectCreateForm />);

      const uploadTab = screen.getByTestId("tabs-trigger-upload");
      fireEvent.click(uploadTab);

      expect(screen.getByTestId("file-dropzone")).toBeInTheDocument();
    });

    it("shows file dropzone", () => {
      render(<ProjectCreateForm />);

      const uploadTab = screen.getByTestId("tabs-trigger-upload");
      fireEvent.click(uploadTab);

      expect(screen.getByTestId("file-dropzone")).toBeInTheDocument();
    });
  });

  describe("Clip count slider", () => {
    it("shows clip count slider", () => {
      render(<ProjectCreateForm />);

      const slider = screen.getByTestId("slider");
      expect(slider).toBeInTheDocument();
    });
  });

  describe("Language selector", () => {
    it("shows language selector with options", () => {
      render(<ProjectCreateForm />);

      // Check that select triggers exist (multiple selects on the page)
      const selectTriggers = screen.getAllByTestId("select-trigger");
      expect(selectTriggers.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("Campaign selector", () => {
    it("shows campaign selector when campaigns are provided", () => {
      render(<ProjectCreateForm campaigns={mockCampaigns} />);

      // Check that campaign is shown in select
      const selectTriggers = screen.getAllByTestId("select-trigger");
      expect(selectTriggers.length).toBeGreaterThanOrEqual(3);
    });
  });

  describe("Reframe mode selector", () => {
    it("shows reframe mode selector", () => {
      render(<ProjectCreateForm />);

      const selectTriggers = screen.getAllByTestId("select-trigger");
      expect(selectTriggers.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("Preset selection", () => {
    it("shows all preset options", () => {
      render(<ProjectCreateForm />);

      expect(screen.getByText("Bold Yellow")).toBeInTheDocument();
      expect(screen.getByText("Hormozi")).toBeInTheDocument();
      expect(screen.getByText("Clean White")).toBeInTheDocument();
      expect(screen.getByText("MrBeast")).toBeInTheDocument();
    });

    it("allows selecting a preset", () => {
      render(<ProjectCreateForm />);

      const hormoziPreset = screen.getByText("Hormozi");
      fireEvent.click(hormoziPreset.closest("div")!);

      // The preview should show the selected preset
      expect(screen.getByTestId("preset-hormozi")).toBeInTheDocument();
    });
  });

  describe("Preview section", () => {
    it("shows subtitle preview for selected preset", () => {
      render(<ProjectCreateForm />);

      expect(screen.getByTestId("subtitle-preset-preview")).toBeInTheDocument();
    });
  });

  describe("Actions", () => {
    it("shows cancel button linking to projects list", () => {
      render(<ProjectCreateForm />);

      // The Link wraps the Button, so we need to find the parent <a> element
      const cancelButton = screen.getByText("Cancelar");
      const linkElement = cancelButton.closest('a[href="/projects"]');
      expect(linkElement).toBeInTheDocument();
      expect(linkElement).toHaveAttribute("href", "/projects");
    });

    it("shows create project button", () => {
      render(<ProjectCreateForm />);

      expect(screen.getByText("Crear proyecto")).toBeInTheDocument();
    });

    it("disable create button when form is not valid (no URL)", () => {
      render(<ProjectCreateForm />);

      const createButtons = screen.getAllByText("Crear proyecto");
      expect(createButtons[0]).toBeDisabled();
    });

    it("enable create button when URL is entered", async () => {
      render(<ProjectCreateForm />);

      // Get all inputs and change the first one (URL input)
      const inputs = screen.getAllByTestId("input");
      fireEvent.change(inputs[0]!, { target: { value: "https://youtube.com/watch?v=test123" } });

      const createButtons = screen.getAllByText("Crear proyecto");
      expect(createButtons[0]).not.toBeDisabled();
    });
  });
});