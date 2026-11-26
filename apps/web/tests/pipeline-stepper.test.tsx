import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { PipelineStepper } from "@/components/projects/pipeline-stepper";
import { makeJob } from "./mocks/fixtures";

describe("PipelineStepper", () => {
  it("muestra las cuatro etapas, transiciones y el porcentaje en vivo", () => {
    const { container } = render(
      <PipelineStepper
        projectStatus="processing"
        job={makeJob({ progress: 65, stage: "select", status: "running" })}
      />,
    );

    expect(screen.getByText("1. Descarga")).toBeInTheDocument();
    expect(screen.getByText("2. Transcripción")).toBeInTheDocument();
    expect(screen.getByText("3. Selección")).toBeInTheDocument();
    expect(screen.getByText("4. Render")).toBeInTheDocument();
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText("Selección")).toBeInTheDocument();

    expect(
      container.querySelector('[data-stage="ingest"]')?.getAttribute("data-state"),
    ).toBe("done");
    expect(
      container.querySelector('[data-stage="transcribe"]')?.getAttribute("data-state"),
    ).toBe("done");
    expect(
      container.querySelector('[data-stage="select"]')?.getAttribute("data-state"),
    ).toBe("active");
    expect(
      container.querySelector('[data-stage="render"]')?.getAttribute("data-state"),
    ).toBe("pending");
  });

  it("marca todas las etapas al 100 % cuando el trabajo termina", () => {
    render(
      <PipelineStepper
        projectStatus="ready"
        job={makeJob({ progress: 100, stage: "done", status: "done" })}
      />,
    );
    expect(screen.getAllByText("100%").length).toBeGreaterThanOrEqual(4);
  });

  it("muestra el banner de error y destaca la etapa fallida", () => {
    const { container } = render(
      <PipelineStepper
        projectStatus="failed"
        job={makeJob({
          progress: 35,
          stage: "transcribe",
          status: "failed",
          error: "Error en mlx-whisper",
        })}
      />,
    );
    expect(
      screen.getByText("El procesamiento ha fallado"),
    ).toBeInTheDocument();
    expect(screen.getByText("Error en mlx-whisper")).toBeInTheDocument();
    expect(
      container.querySelector('[data-stage="ingest"]')?.getAttribute("data-state"),
    ).toBe("done");
    expect(
      container.querySelector('[data-stage="transcribe"]')?.getAttribute("data-state"),
    ).toBe("failed");
  });

  it("pide confirmación antes de cancelar el trabajo y refleja el estado cancelado", () => {
    const onCancel = vi.fn();
    const { rerender } = render(
      <PipelineStepper
        projectStatus="processing"
        job={makeJob({ progress: 40, stage: "transcribe", status: "running" })}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/i }));
    expect(
      screen.getByText("¿Cancelar el procesamiento?"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar trabajo" }));
    expect(onCancel).toHaveBeenCalledTimes(1);

    rerender(
      <PipelineStepper
        projectStatus="cancelled"
        job={makeJob({ progress: 40, stage: "transcribe", status: "cancelled" })}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByText("Procesamiento cancelado")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Cancelar/i }),
    ).not.toBeInTheDocument();
  });
});
