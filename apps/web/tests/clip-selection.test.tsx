import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ClipGrid } from "@/components/projects/clip-grid";
import { makeClip } from "./mocks/fixtures";

vi.mock("@/hooks/use-clips", () => ({
  useUpdateClip: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteClip: () => ({ mutate: vi.fn(), isPending: false }),
  useRerenderClip: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProjectClips: () => ({ data: [], isLoading: false }),
  useCancelJob: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const CLIPS = [
  makeClip({ id: "clip-1", title: "Primer clip" }),
  makeClip({ id: "clip-2", title: "Segundo clip", score: 80 }),
];

describe("multiselección de clips", () => {
  it("selecciona varios clips y muestra el contador", () => {
    render(<ClipGrid projectId="proj-1" clips={CLIPS} projectDuration={600} />);

    fireEvent.click(screen.getByLabelText("Seleccionar Primer clip"));
    fireEvent.click(screen.getByLabelText("Seleccionar Segundo clip"));

    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/de 2 seleccionados/)).toBeInTheDocument();
  });

  it("selecciona todos y limpia la selección", () => {
    render(<ClipGrid projectId="proj-1" clips={CLIPS} projectDuration={600} />);

    fireEvent.click(screen.getByLabelText("Seleccionar Primer clip"));
    expect(screen.getByText(/de 2 seleccionados/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Todos" }));
    expect(screen.getByText("2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Limpiar/i }));
    expect(
      screen.queryByRole("region", { name: "Acciones de selección" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Seleccionar todos" }));
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("mantiene Publicar en redes deshabilitado hasta el change 8", () => {
    render(<ClipGrid projectId="proj-1" clips={CLIPS} projectDuration={600} />);
    fireEvent.click(screen.getByLabelText("Seleccionar Primer clip"));

    const publish = screen.getByRole("button", {
      name: /Publicar en redes/i,
    });
    expect(publish).toBeDisabled();
    expect(publish).toHaveAttribute("aria-disabled", "true");
  });

  it("muestra el estado vacío cuando no hay clips", () => {
    render(<ClipGrid projectId="proj-1" clips={[]} projectDuration={600} />);
    expect(
      screen.getByText("Aún no hay clips en este proyecto"),
    ).toBeInTheDocument();
  });
});
