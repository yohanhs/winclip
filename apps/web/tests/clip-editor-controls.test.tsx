import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { CropControls } from "@/components/projects/crop-controls";
import { SubtitleWordEditor } from "@/components/projects/subtitle-word-editor";
import { makeClipWords, makePreset } from "./mocks/fixtures";

describe("SubtitleWordEditor", () => {
  it("permite editar palabras inline, marca las editadas y restablece el texto", () => {
    const words = makeClipWords().words ?? [];
    const onChange = vi.fn();

    const { rerender } = render(
      <SubtitleWordEditor words={words} overrides={{}} onChange={onChange} />,
    );

    expect(screen.getByText("3 palabras")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Restablecer texto/i }),
    ).toBeDisabled();

    // Clic en "Juc" -> input inline
    fireEvent.click(screen.getByRole("button", { name: "Juc" }));
    const input = screen.getByLabelText("Editar palabra Juc");
    fireEvent.change(input, { target: { value: "Hook" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith({ "10600:11000": "Hook" });

    // Rerender con el override aplicado
    rerender(
      <SubtitleWordEditor
        words={words}
        overrides={{ "10600:11000": "Hook" }}
        onChange={onChange}
      />,
    );

    expect(screen.getByText("1 editada")).toBeInTheDocument();
    const editedBtn = screen.getByRole("button", { name: /Hook/i });
    expect(editedBtn).toHaveAttribute("data-edited", "true");

    // Restablecer texto
    const resetBtn = screen.getByRole("button", { name: /Restablecer texto/i });
    expect(resetBtn).toBeEnabled();
    fireEvent.click(resetBtn);
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it("muestra estado de carga y error", () => {
    const { rerender } = render(
      <SubtitleWordEditor words={[]} overrides={{}} onChange={vi.fn()} isLoading />,
    );
    expect(screen.getByText(/Cargando palabras/i)).toBeInTheDocument();

    rerender(
      <SubtitleWordEditor
        words={[]}
        overrides={{}}
        onChange={vi.fn()}
        errorMessage="Sin transcripción"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Sin transcripción");
  });
});

describe("CropControls", () => {
  const presets = [
    makePreset({ id: "bold-yellow", name: "Bold Yellow" }),
    makePreset({ id: "clean-white", name: "Clean White" }),
  ];

  it("muestra selectores de preset y modo de reencuadre, y oculta crop/zoom fuera de center", () => {
    const onPreset = vi.fn();
    const onReframe = vi.fn();

    render(
      <CropControls
        presets={presets}
        projectPreset="bold-yellow"
        projectReframeMode="face"
        subtitlePreset={null}
        reframeMode={null}
        cropXPct={50}
        cropYPct={50}
        zoomPct={100}
        onSubtitlePresetChange={onPreset}
        onReframeModeChange={onReframe}
        onCropXChange={vi.fn()}
        onCropYChange={vi.fn()}
        onZoomChange={vi.fn()}
        onReset={vi.fn()}
      />,
    );

    expect(
      screen.queryByLabelText("Posición horizontal (Crop X)"),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Preset de subtítulos"), {
      target: { value: "clean-white" },
    });
    expect(onPreset).toHaveBeenCalledWith("clean-white");

    fireEvent.click(screen.getByRole("button", { name: /Manual/i }));
    expect(onReframe).toHaveBeenCalledWith("center");
  });

  it("muestra sliders de Crop X, Crop Y y Zoom cuando el modo efectivo es center", () => {
    const onReset = vi.fn();

    render(
      <CropControls
        presets={presets}
        projectPreset="bold-yellow"
        projectReframeMode="face"
        subtitlePreset="clean-white"
        reframeMode="center"
        cropXPct={35}
        cropYPct={25}
        zoomPct={120}
        onSubtitlePresetChange={vi.fn()}
        onReframeModeChange={vi.fn()}
        onCropXChange={vi.fn()}
        onCropYChange={vi.fn()}
        onZoomChange={vi.fn()}
        onReset={onReset}
      />,
    );

    expect(screen.getByText("35%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("120%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Restablecer estilo/i }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
