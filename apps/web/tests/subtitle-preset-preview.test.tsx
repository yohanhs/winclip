import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { SubtitlePresetPreview } from "@/components/projects/subtitle-preset-preview";
import { makePreset } from "./mocks/fixtures";

describe("SubtitlePresetPreview", () => {
  it("renderiza el preset real con su nombre y color", () => {
    render(<SubtitlePresetPreview preset="bold-yellow" />);
    expect(screen.getByText("Bold Yellow")).toBeInTheDocument();
    expect(
      screen.getByText(/Karaoke blanco · palabra activa amarilla/i),
    ).toBeInTheDocument();
  });

  it("usa la descripción del preset de la API cuando existe", () => {
    render(
      <SubtitlePresetPreview
        preset="hormozi"
        presetData={makePreset({
          id: "hormozi",
          name: "Hormozi",
          description: "Descripción real del backend",
        })}
      />,
    );
    expect(screen.getByText("Hormozi")).toBeInTheDocument();
    expect(screen.getByText("Descripción real del backend")).toBeInTheDocument();
  });

  it("muestra la etiqueta de encuadre correspondiente", () => {
    const { rerender } = render(
      <SubtitlePresetPreview preset="mrbeast" reframeMode="face" />,
    );
    expect(screen.getByText("Cara centrada")).toBeInTheDocument();

    rerender(<SubtitlePresetPreview preset="mrbeast" reframeMode="blur" />);
    expect(screen.getByText("Fondo desenfocado")).toBeInTheDocument();
  });

  it("alterna la reproducción de la previsualización", () => {
    const onTogglePlay = vi.fn();
    render(
      <SubtitlePresetPreview
        preset="clean-white"
        isPlaying
        onTogglePlay={onTogglePlay}
      />,
    );

    fireEvent.click(screen.getByLabelText("Pausar previsualización"));
    expect(onTogglePlay).toHaveBeenCalledWith(false);
  });

  it("cae en Bold Yellow si el preset no existe", () => {
    render(<SubtitlePresetPreview preset="preset-inexistente" />);
    expect(screen.getByText("Bold Yellow")).toBeInTheDocument();
  });
});
