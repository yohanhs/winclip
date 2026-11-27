import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CampaignCreate,
  CampaignOut,
  CampaignParseOut,
} from "@winclip/api-client";

import { CampaignsWorkspace } from "@/components/campaigns/campaigns-workspace";
import {
  makeCampaign,
  makeCampaignRules,
  makeCampaignTemplate,
  makePreset,
} from "./mocks/fixtures";

const mocks = vi.hoisted(() => ({
  campaigns: [] as CampaignOut[],
  createMutate: vi.fn(),
  updateMutate: vi.fn(),
  duplicateMutate: vi.fn(),
  deleteMutate: vi.fn(),
  parseMutate: vi.fn(),
  uploadWatermarkMutate: vi.fn(),
}));

vi.mock("@/hooks/use-campaigns", () => ({
  useCampaigns: () => ({
    data: mocks.campaigns,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCampaignTemplates: () => ({
    data: [
      makeCampaignTemplate(),
      makeCampaignTemplate({
        id: "creator-en",
        title: "Creator Bounty (EN)",
        language: "en",
        rules: makeCampaignRules({
          name: "Creator Bounty EN",
          language: "en",
        }),
      }),
    ],
    isLoading: false,
  }),
  useCreateCampaign: () => ({
    mutate: mocks.createMutate,
    isPending: false,
  }),
  useUpdateCampaign: () => ({
    mutate: mocks.updateMutate,
    isPending: false,
  }),
  useDuplicateCampaign: () => ({
    mutate: mocks.duplicateMutate,
    isPending: false,
  }),
  useDeleteCampaign: () => ({
    mutate: mocks.deleteMutate,
    isPending: false,
  }),
  useParseCampaignBrief: () => ({
    mutate: mocks.parseMutate,
    isPending: false,
  }),
  useUploadCampaignWatermark: () => ({
    mutate: mocks.uploadWatermarkMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-projects", () => ({
  usePresets: () => ({
    data: [makePreset()],
    isLoading: false,
  }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    message: vi.fn(),
  },
}));

describe("CampaignsWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.campaigns = [makeCampaign()];
  });

  it("lista campañas, parsea brief con badges IA y guarda la propuesta editada", () => {
    mocks.parseMutate.mockImplementation(
      (
        _brief: string,
        options?: { onSuccess?: (result: CampaignParseOut) => void },
      ) => {
        options?.onSuccess?.({
          rules: makeCampaignRules({
            name: "Brief Finanzas IA",
            tone: "directo",
            subtitle_preset: "bold-yellow",
          }),
          inferred_fields: ["tone", "subtitle_preset"],
          warnings: ["Revisa el preset sugerido."],
          provider: "fake:gemini",
        });
      },
    );

    render(<CampaignsWorkspace />);

    expect(screen.getByText("Podcast Finanzas ES")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Pegar brief \(IA\)/i }));
    const textarea = screen.getByLabelText(/Brief de campaña en texto libre/i);
    fireEvent.change(textarea, {
      target: { value: "Clips en español con #finanzas" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Extraer reglas con IA/i }),
    );

    expect(screen.getByTestId("ai-badge-tone")).toBeInTheDocument();
    expect(screen.getByTestId("ai-badge-subtitle_preset")).toBeInTheDocument();
    expect(screen.getByTestId("campaign-json-preview")).toHaveTextContent(
      "Brief Finanzas IA",
    );

    const nameInput = screen.getByLabelText(/Nombre de campaña/i);
    fireEvent.change(nameInput, { target: { value: "Finanzas Editada" } });
    expect(screen.getByTestId("campaign-json-preview")).toHaveTextContent(
      "Finanzas Editada",
    );

    fireEvent.click(screen.getByRole("button", { name: /Guardar campaña/i }));
    expect(mocks.createMutate).toHaveBeenCalledTimes(1);
    const [payload] = mocks.createMutate.mock.calls[0] as [CampaignCreate];
    expect(payload.name).toBe("Finanzas Editada");
    expect(payload.source_text).toBe("Clips en español con #finanzas");
  });

  it("duplica y elimina una campaña con confirmación AlertDialog", () => {
    render(<CampaignsWorkspace />);
    expect(screen.getByText("Podcast Finanzas ES")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /Duplicar campaña Podcast Finanzas ES/i,
      }),
    );
    expect(mocks.duplicateMutate).toHaveBeenCalledWith(
      "camp-1",
      expect.any(Object),
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /Eliminar campaña Podcast Finanzas ES/i,
      }),
    );
    expect(screen.getByText(/¿Eliminar esta campaña\?/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Eliminar$/i }));
    expect(mocks.deleteMutate).toHaveBeenCalledWith(
      "camp-1",
      expect.any(Object),
    );
  });
});
