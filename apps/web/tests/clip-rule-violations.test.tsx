import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ClipCard } from "@/components/projects/clip-card";
import { makeClip } from "./mocks/fixtures";

describe("ClipCard rule_violations", () => {
  it("muestra alertas de rule_violations sin bloquear reproducción ni edición", () => {
    const onPlay = vi.fn();
    const onEdit = vi.fn();

    const clip = makeClip({
      id: "clip-alert-1",
      rule_violations: [
        {
          code: "banned_word_present",
          field: "banned_words",
          severity: "error",
          message: "Contiene la palabra prohibida 'garantizado'",
        },
        {
          code: "missing_required_hashtag",
          field: "hashtags",
          severity: "warning",
          message: "Faltan hashtags de la campaña: #finanzas",
        },
      ],
    });

    render(
      <ClipCard
        clip={clip}
        selected={false}
        onToggleSelect={vi.fn()}
        onPlay={onPlay}
        onEdit={onEdit}
        onTrim={vi.fn()}
        onDelete={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(
      screen.getByTestId("clip-violations-badge-clip-alert-1"),
    ).toHaveTextContent("2 alertas");
    expect(
      screen.getByText("Contiene la palabra prohibida 'garantizado'"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Faltan hashtags de la campaña: #finanzas"),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: `Reproducir ${clip.title}` }),
    );
    expect(onPlay).toHaveBeenCalledWith(clip);

    fireEvent.click(
      screen.getByRole("button", { name: `Editar ${clip.title}` }),
    );
    expect(onEdit).toHaveBeenCalledWith(clip);
  });
});
