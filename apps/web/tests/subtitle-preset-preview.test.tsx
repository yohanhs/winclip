import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SubtitlePresetPreview } from "@/components/projects/subtitle-preset-preview";

// Mock lucide-react
vi.mock("lucide-react", () => ({
  Play: () => <svg data-testid="play-icon" />,
  Pause: () => <svg data-testid="pause-icon" />,
}));

describe("SubtitlePresetPreview", () => {
  const mockPresetData = {
    id: "bold_yellow",
    name: "Bold Yellow",
    description: "Karaoke amarillo eléctrico",
    font: "Inter",
    highlight_color: "#FFD600",
    primary_color: "#FFFFFF",
    box_bg_color: null,
    fallback_font: "Arial",
    font_size: 24,
    uppercase: false,
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
  };

  const defaultProps = {
    preset: "bold_yellow" as const,
    presetData: mockPresetData,
  };

  describe("Initial rendering", () => {
    it("renders the preview with video background", () => {
      render(<SubtitlePresetPreview {...defaultProps} />);

      // Should show the preview
      const preview = screen.getByRole("img", { name: /video preview/i });
      expect(preview).toBeInTheDocument();
    });

    it("does not crash with minimal props", () => {
      render(<SubtitlePresetPreview preset="bold_yellow" presetData={mockPresetData} />);

      expect(screen.getByRole("img", { name: /video preview/i })).toBeInTheDocument();
    });
  });

  describe("Animation and playback", () => {
    it("shows play icon when not playing", () => {
      render(<SubtitlePresetPreview {...defaultProps} isPlaying={false} />);

      expect(screen.getByTestId("play-icon")).toBeInTheDocument();
    });

    it("does not show play icon when playing", () => {
      render(<SubtitlePresetPreview {...defaultProps} isPlaying={true} />);

      expect(screen.queryByTestId("play-icon")).not.toBeInTheDocument();
    });
  });

  describe("Preset styles", () => {
    it("renders bold_yellow preset", () => {
      render(<SubtitlePresetPreview preset="bold_yellow" presetData={mockPresetData} />);

      expect(screen.getByRole("img", { name: /video preview/i })).toBeInTheDocument();
    });

    it("renders hormozi preset", () => {
      render(
        <SubtitlePresetPreview
          preset="hormozi"
          presetData={{ ...mockPresetData, id: "hormozi", name: "Hormozi" }}
        />
      );

      expect(screen.getByRole("img", { name: /video preview/i })).toBeInTheDocument();
    });

    it("renders clean_white preset", () => {
      render(
        <SubtitlePresetPreview
          preset="clean_white"
          presetData={{ ...mockPresetData, id: "clean_white", name: "Clean White" }}
        />
      );

      expect(screen.getByRole("img", { name: /video preview/i })).toBeInTheDocument();
    });

    it("renders mrbeast preset", () => {
      render(
        <SubtitlePresetPreview
          preset="mrbeast"
          presetData={{ ...mockPresetData, id: "mrbeast", name: "MrBeast" }}
        />
      );

      expect(screen.getByRole("img", { name: /video preview/i })).toBeInTheDocument();
    });
  });

  describe("Progress scrub bar", () => {
    it("shows progress bar when playing", () => {
      render(<SubtitlePresetPreview {...defaultProps} isPlaying={true} />);

      // Progress bar should be visible when playing
      const progressBar = document.querySelector('[style*="width:"].bg-amber-400');
      expect(progressBar).toBeInTheDocument();
    });

    it("hides progress bar when not playing", () => {
      render(<SubtitlePresetPreview {...defaultProps} isPlaying={false} />);

      // Progress bar should not be visible
      const progressBar = document.querySelector('[style*="width:"].bg-amber-400');
      expect(progressBar).not.toBeInTheDocument();
    });
  });

  describe("Custom styling", () => {
    it("applies custom className", () => {
      render(
        <SubtitlePresetPreview
          {...defaultProps}
          className="custom-class-name"
        />
      );

      const container = screen.getByRole("img", { name: /video preview/i })
        .parentElement;
      expect(container).toHaveClass("custom-class-name");
    });
  });

  describe("Caption animations", () => {
    it("renders captions when playing", () => {
      render(<SubtitlePresetPreview {...defaultProps} isPlaying={true} />);

      // Check that captions are rendered - they animate through words
      const captions = document.querySelectorAll(".text-#FFD600, .text-white\\/95");
      expect(captions.length).toBeGreaterThan(0);
    });

    it("has transition styles for playing preview", () => {
      render(<SubtitlePresetPreview {...defaultProps} isPlaying={true} />);

      // When playing, there should be transition classes
      const container = document.querySelector(".transition-transform");
      expect(container).toBeInTheDocument();
    });
  });
});