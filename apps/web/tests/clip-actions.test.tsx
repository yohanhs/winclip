import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { ClipEditDialog } from "@/components/projects/clip-edit-dialog";
import { ClipGrid } from "@/components/projects/clip-grid";
import { downloadClipFile } from "@/lib/download";
import { makeClip } from "./mocks/fixtures";

const mocks = vi.hoisted(() => ({
  updateMutate: vi.fn(),
  deleteMutate: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@/hooks/use-clips", () => ({
  useUpdateClip: () => ({ mutate: mocks.updateMutate, isPending: false }),
  useDeleteClip: () => ({ mutate: mocks.deleteMutate, isPending: false }),
  useRerenderClip: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProjectClips: () => ({ data: [], isLoading: false }),
  useCancelJob: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("sonner", () => ({
  toast: { success: mocks.toastSuccess, error: mocks.toastError },
}));

describe("acciones de clip", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("guarda título, descripción y hashtags con PATCH", () => {
    const clip = makeClip();
    render(
      <ClipEditDialog clip={clip} open onOpenChange={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo título" },
    });
    fireEvent.change(screen.getByLabelText("Descripción"), {
      target: { value: "Nueva descripción" },
    });
    fireEvent.change(screen.getByLabelText("Hashtags"), {
      target: { value: "#shorts, dinero #ahorro" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(mocks.updateMutate).toHaveBeenCalledWith(
      {
        clipId: clip.id,
        data: {
          title: "Nuevo título",
          description: "Nueva descripción",
          hashtags: ["shorts", "dinero", "ahorro"],
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("muestra toast de error si falla PATCH y mantiene los valores editados", () => {
    mocks.updateMutate.mockImplementation(
      (
        _vars: unknown,
        options: { onError: (error: Error) => void },
      ) => {
        options.onError(new Error("API 500: fallo al guardar"));
      },
    );
    const onOpenChange = vi.fn();
    render(
      <ClipEditDialog clip={makeClip()} open onOpenChange={onOpenChange} />,
    );

    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Título pendiente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(mocks.toastError).toHaveBeenCalledWith(
      "No se pudo actualizar el clip",
      expect.objectContaining({ description: "API 500: fallo al guardar" }),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByLabelText("Título")).toHaveValue("Título pendiente");
  });

  it("elimina el clip solo tras confirmar en el AlertDialog", () => {
    const clip = makeClip();
    render(
      <ClipGrid projectId="proj-1" clips={[clip]} projectDuration={600} />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: `Eliminar ${clip.title}` }),
    );
    expect(mocks.deleteMutate).not.toHaveBeenCalled();
    expect(screen.getByText("¿Eliminar este clip?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(mocks.deleteMutate).toHaveBeenCalledWith(
      clip.id,
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("descarga el MP4 como blob", async () => {
    const clip = makeClip();
    const blob = new Blob(["video"], { type: "video/mp4" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
    });
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:clip");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    await downloadClipFile(clip);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/clips/clip-1/file?v=2026-01-01T10%3A05%3A00Z",
    ));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:clip");
    vi.unstubAllGlobals();
  });
});
