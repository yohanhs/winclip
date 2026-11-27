import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { PublishDialog } from "@/components/publications/publish-dialog";
import { makeClip, makeSocialAccount } from "./mocks/fixtures";

const mockCreateMutate = vi.fn();
const mockPreviewMutate = vi.fn();

const ACCOUNTS = [
  makeSocialAccount({
    id: "acc-yt",
    platform: "youtube",
    auth_method: "api",
    alias: "Canal YT",
    handle: "@canalyt",
    status: "connected",
    is_default: true,
  }),
  makeSocialAccount({
    id: "acc-tt",
    platform: "tiktok",
    auth_method: "api",
    alias: "TikTok Inbox",
    handle: "@ttinbox",
    status: "connected",
    is_default: true,
    capabilities: { direct_post: false },
  }),
  makeSocialAccount({
    id: "acc-ig-pw",
    platform: "instagram",
    auth_method: "playwright",
    alias: "IG Browser",
    handle: "@igbrowser",
    status: "connected",
    is_default: false,
  }),
  makeSocialAccount({
    id: "acc-ig-exp",
    platform: "instagram",
    auth_method: "api",
    alias: "IG Expirada",
    handle: "@igexp",
    status: "expired",
    is_default: false,
  }),
];

vi.mock("@/hooks/use-accounts", () => ({
  useAccounts: () => ({ data: ACCOUNTS, isLoading: false }),
}));

vi.mock("@/hooks/use-publications", () => ({
  usePublicationsQuota: () => ({
    data: {
      youtube_units_used: 3200,
      youtube_units_limit: 10000,
      youtube_upload_cost: 1600,
      youtube_uploads_today: 2,
      accounts: [],
    },
    isLoading: false,
  }),
  usePreviewPublicationMeta: () => ({ mutate: mockPreviewMutate, isPending: false }),
  useCreatePublications: () => ({ mutate: mockCreateMutate, isPending: false }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe("PublishDialog", () => {
  beforeEach(() => {
    mockCreateMutate.mockReset();
    mockPreviewMutate.mockReset();
  });

  it("preselecciona cuentas Default, deshabilita expiradas y muestra avisos de cuota/inbox/Playwright", () => {
    const clip = makeClip({ id: "clip-1", title: "Short de prueba" });
    render(
      <PublishDialog clips={[clip]} open={true} onOpenChange={vi.fn()} />,
    );

    expect(screen.getByText(/2 seleccionadas/i)).toBeInTheDocument();
    expect(screen.getByText("Sesión expirada")).toBeInTheDocument();
    expect(screen.getByText(/Cuota diaria YouTube API/i)).toBeInTheDocument();
    expect(screen.getByText(/Borrador Inbox/i)).toBeInTheDocument();

    // Seleccionar cuenta Playwright muestra aviso ToS
    const igCheckbox = screen
      .getByText("IG Browser")
      .closest("label")
      ?.querySelector('input[type="checkbox"]');
    expect(igCheckbox).toBeTruthy();
    fireEvent.click(igCheckbox!);
    expect(screen.getByText(/Aviso ToS \(Playwright\)/i)).toBeInTheDocument();
  });

  it("valida título de YouTube <= 100 caracteres y envía payload con privacidad/tags/comentario", () => {
    const clip = makeClip({ id: "clip-1", title: "Short válido" });
    render(
      <PublishDialog clips={[clip]} open={true} onOpenChange={vi.fn()} />,
    );

    const titleInput = screen.getByLabelText(/Título \(YouTube Shorts\)/i);
    fireEvent.change(titleInput, { target: { value: "x".repeat(105) } });
    expect(screen.getByText("105/100")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enviar ahora/i })).toBeDisabled();

    fireEvent.change(titleInput, { target: { value: "Short optimizado #Shorts" } });
    fireEvent.change(screen.getByLabelText(/Privacidad/i), {
      target: { value: "unlisted" },
    });
    fireEvent.change(screen.getByLabelText(/Comentario fijado/i), {
      target: { value: "Link en bio" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Enviar ahora/i }));
    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    const [payload] = mockCreateMutate.mock.calls[0]!;
    expect(payload.items).toHaveLength(2);
    const ytItem = payload.items.find(
      (i: { account_id: string }) => i.account_id === "acc-yt",
    );
    expect(ytItem.meta.title).toBe("Short optimizado #Shorts");
    expect(ytItem.meta.privacy_status).toBe("unlisted");
    expect(ytItem.meta.pinned_comment).toBe("Link en bio");
  });
});
