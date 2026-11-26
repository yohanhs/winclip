import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ClipCard } from "@/components/projects/clip-card";
import { ClipPlayerDialog } from "@/components/projects/clip-player-dialog";
import { makeClip } from "./mocks/fixtures";

function renderCard(overrides: Partial<Parameters<typeof ClipCard>[0]> = {}) {
  const props = {
    clip: makeClip(),
    selected: false,
    onToggleSelect: vi.fn(),
    onPlay: vi.fn(),
    onEdit: vi.fn(),
    onTrim: vi.fn(),
    onDelete: vi.fn(),
    onDownload: vi.fn(),
    ...overrides,
  };
  const view = render(<ClipCard {...props} />);
  return { ...props, ...view };
}

describe("ClipCard y ClipPlayerDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("muestra score, título, hook, duración y hashtags", () => {
    renderCard();
    expect(screen.getByText("92/100")).toBeInTheDocument();
    expect(
      screen.getByText("El error que te cuesta 500 al mes"),
    ).toBeInTheDocument();
    expect(screen.getByText("Nadie te cuenta esto")).toBeInTheDocument();
    expect(screen.getByText("0:20")).toBeInTheDocument();
    expect(screen.getByText("#shorts #finanzas")).toBeInTheDocument();
  });

  it("reproduce silenciado al pasar el cursor (hover-play) y pausa al salir", () => {
    const playSpy = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockResolvedValue(undefined);
    const pauseSpy = vi
      .spyOn(HTMLMediaElement.prototype, "pause")
      .mockImplementation(() => undefined);

    const { container } = renderCard();
    const preview = container.querySelector(".aspect-\\[9\\/16\\]")!;
    expect(container.querySelector("video")).toBeNull();

    fireEvent.mouseEnter(preview);
    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.muted).toBe(true);
    expect(playSpy).toHaveBeenCalledTimes(1);

    fireEvent.mouseLeave(preview);
    expect(pauseSpy).toHaveBeenCalled();
    expect(container.querySelector("video")).toBeNull();
  });

  it("abre el reproductor al pulsar play y muestra el vídeo con controles", () => {
    const props = renderCard();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Reproducir El error que te cuesta 500 al mes",
      }),
    );
    expect(props.onPlay).toHaveBeenCalledWith(props.clip);

    render(
      <ClipPlayerDialog
        clip={props.clip}
        open
        onOpenChange={vi.fn()}
        onDownload={props.onDownload}
      />,
    );
    const playerVideo = document.querySelector("video[controls]");
    expect(playerVideo).not.toBeNull();
    expect(playerVideo?.getAttribute("src")).toContain("/api/clips/clip-1/file");
  });

  it("marca y desmarca la selección con el checkbox", () => {
    const props = renderCard();
    fireEvent.click(
      screen.getByLabelText("Seleccionar El error que te cuesta 500 al mes"),
    );
    expect(props.onToggleSelect).toHaveBeenCalledWith("clip-1", true);
  });

  it("muestra el estado de re-renderizado y bloquea el play", () => {
    renderCard({ clip: makeClip({ status: "rendering" }) });
    expect(screen.getByText("Re-renderizando…")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Reproducir El error que te cuesta 500 al mes",
      }),
    ).not.toBeInTheDocument();
  });

  it("lanza las acciones de editar, recortar y descargar", () => {
    const props = renderCard();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Editar El error que te cuesta 500 al mes",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Recortar El error que te cuesta 500 al mes",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Descargar El error que te cuesta 500 al mes",
      }),
    );
    expect(props.onEdit).toHaveBeenCalledWith(props.clip);
    expect(props.onTrim).toHaveBeenCalledWith(props.clip);
    expect(props.onDownload).toHaveBeenCalledWith(props.clip);
  });

  it("confirma antes de eliminar el clip", () => {
    const props = renderCard();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Eliminar El error que te cuesta 500 al mes",
      }),
    );
    expect(screen.getByText("¿Eliminar este clip?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(props.onDelete).toHaveBeenCalledWith(props.clip);
  });
});
