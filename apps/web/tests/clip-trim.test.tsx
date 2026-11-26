import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { ClipTrimDialog } from "@/components/projects/clip-trim-dialog";
import { MiniTimeline } from "@/components/projects/mini-timeline";
import { makeClip } from "./mocks/fixtures";

const mocks = vi.hoisted(() => ({
  updateAsync: vi.fn(),
  rerenderAsync: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@/hooks/use-clips", () => ({
  useUpdateClip: () => ({ mutateAsync: mocks.updateAsync, isPending: false }),
  useRerenderClip: () => ({
    mutateAsync: mocks.rerenderAsync,
    isPending: false,
  }),
}));

vi.mock("sonner", () => ({
  toast: { success: mocks.toastSuccess, error: mocks.toastError },
}));

describe("ClipTrimDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.updateAsync.mockResolvedValue({});
    mocks.rerenderAsync.mockResolvedValue({});
  });

  it("muestra la waveform y la duración seleccionada", () => {
    render(<MiniTimeline duration={120} start={10} end={30} />);
    expect(screen.getByText("IN")).toBeInTheDocument();
    expect(screen.getByText("OUT")).toBeInTheDocument();
    expect(screen.getByText("0:20 seleccionados")).toBeInTheDocument();
    expect(screen.getByText("2:00")).toBeInTheDocument();
  });

  it("guarda los tiempos editados y lanza el re-render", async () => {
    const clip = makeClip({ start_sec: 10, end_sec: 30 });
    const onOpenChange = vi.fn();
    render(
      <ClipTrimDialog
        clip={clip}
        open
        onOpenChange={onOpenChange}
        maxDuration={120}
      />,
    );

    fireEvent.change(screen.getByLabelText("Entrada (IN · s)"), {
      target: { value: "12.5" },
    });
    fireEvent.change(screen.getByLabelText("Salida (OUT · s)"), {
      target: { value: "42" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Guardar y re-renderizar" }),
    );

    await waitFor(() => {
      expect(mocks.updateAsync).toHaveBeenCalledWith({
        clipId: clip.id,
        data: { start_sec: 12.5, end_sec: 42 },
      });
    });
    expect(mocks.rerenderAsync).toHaveBeenCalledWith(clip.id);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mocks.toastSuccess).toHaveBeenCalled();
  });

  it("impide guardar un rango temporal inválido (start >= end)", () => {
    const clip = makeClip({ start_sec: 10, end_sec: 30 });
    render(
      <ClipTrimDialog
        clip={clip}
        open
        onOpenChange={vi.fn()}
        maxDuration={120}
      />,
    );

    fireEvent.change(screen.getByLabelText("Entrada (IN · s)"), {
      target: { value: "35" },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/El rango no es válido/i);
    const saveButton = screen.getByRole("button", {
      name: "Guardar y re-renderizar",
    });
    expect(saveButton).toBeDisabled();
    fireEvent.click(saveButton);
    expect(mocks.updateAsync).not.toHaveBeenCalled();
    expect(mocks.rerenderAsync).not.toHaveBeenCalled();
  });

  it("restablece los tiempos originales del clip", () => {
    const clip = makeClip({ start_sec: 12, end_sec: 28 });
    render(
      <ClipTrimDialog
        clip={clip}
        open
        onOpenChange={vi.fn()}
        maxDuration={120}
      />,
    );
    fireEvent.change(screen.getByLabelText("Entrada (IN · s)"), {
      target: { value: "20" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Restablecer/i }));
    expect(screen.getByLabelText("Entrada (IN · s)")).toHaveValue(12);
    expect(screen.getByText("0:16 seleccionados")).toBeInTheDocument();
  });
});
