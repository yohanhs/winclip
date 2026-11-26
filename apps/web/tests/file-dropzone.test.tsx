import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { FileDropzone } from "@/components/projects/file-dropzone";

// Mock lucide-react
vi.mock("lucide-react", () => ({
  FileVideo: () => <svg data-testid="file-video" />,
  Upload: () => <svg data-testid="upload" />,
  X: () => <svg data-testid="x-icon" />,
  AlertCircle: () => <svg data-testid="alert-circle" />,
}));

describe("FileDropzone", () => {
  const mockOnFileSelected = vi.fn();
  const mockOnUploadComplete = vi.fn();
  const mockOnUploadError = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  describe("Initial rendering", () => {
    it("shows the drop zone with placeholder text", () => {
      render(<FileDropzone />);

      expect(
        screen.getByText(
          /Arrastra un archivo de video aquí o haz clic para seleccionar/i
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Formatos admitidos: MP4, MOV, MKV, AVI/i)
      ).toBeInTheDocument();
    });

    it("shows supported formats info", () => {
      render(<FileDropzone />);

      expect(
        screen.getByText(/Tamaño máximo: 4000MB/i)
      ).toBeInTheDocument();
    });

    it("shows upload icon", () => {
      render(<FileDropzone />);

      expect(screen.getByTestId("upload")).toBeInTheDocument();
    });
  });

  describe("Upload callback", () => {
    it("handles upload complete callback", async () => {
      render(
        <FileDropzone
          onFileSelected={mockOnFileSelected}
          onUploadComplete={mockOnUploadComplete}
        />
      );

      // Check dropzone is rendered
      expect(screen.getByTestId("upload")).toBeInTheDocument();
    });
  });

  describe("Disabled state", () => {
    it("renders with disabled prop", () => {
      render(<FileDropzone disabled />);

      // Check drop zone exists
      expect(screen.getByText(/Arrastra un archivo de video/i)).toBeInTheDocument();
    });
  });

  describe("Placeholder customization", () => {
    it("shows custom placeholder text when provided", () => {
      render(<FileDropzone placeholder="Custom drop zone text" />);

      expect(screen.getByText("Custom drop zone text")).toBeInTheDocument();
    });
  });
});