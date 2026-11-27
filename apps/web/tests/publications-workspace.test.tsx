import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { PublicationsWorkspace } from "@/components/publications/publications-workspace";
import { makePublication } from "./mocks/fixtures";

const mockRetryMutate = vi.fn();
const mockCancelMutate = vi.fn();

const PUBLICATIONS = [
  makePublication({
    id: "pub-sched",
    clip_title: "Clip Programado",
    status: "scheduled",
    account_platform: "tiktok",
    account_alias: "TT Principal",
    delivery_mode: "inbox",
  }),
  makePublication({
    id: "pub-done",
    clip_title: "Clip Publicado",
    status: "published",
    account_platform: "youtube",
    account_alias: "YT Principal",
    external_url: "https://www.youtube.com/shorts/abc123",
  }),
  makePublication({
    id: "pub-fail",
    clip_title: "Clip Fallido",
    status: "failed",
    account_platform: "instagram",
    account_auth_method: "playwright",
    account_alias: "IG Browser",
    error: "CAPTCHA detectado en Instagram",
    error_code: "challenge_required",
    has_screenshot: true,
    screenshot_url: "/api/publications/pub-fail/screenshot",
  }),
  makePublication({
    id: "pub-cancel",
    clip_title: "Clip Cancelado",
    status: "cancelled",
    account_platform: "tiktok",
    account_alias: "TT Principal",
  }),
];

vi.mock("@/hooks/use-publications", () => ({
  usePublications: () => ({
    data: PUBLICATIONS,
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  usePublicationsQuota: () => ({
    data: {
      youtube_units_used: 1600,
      youtube_units_limit: 10000,
      youtube_upload_cost: 1600,
      youtube_uploads_today: 1,
      accounts: [],
    },
    refetch: vi.fn(),
  }),
  useRetryPublication: () => ({ mutate: mockRetryMutate, isPending: false }),
  useCancelPublication: () => ({ mutate: mockCancelMutate, isPending: false }),
}));

vi.mock("@/hooks/use-accounts", () => ({
  useAccounts: () => ({ data: [] }),
}));

vi.mock("@/hooks/use-projects", () => ({
  useProjects: () => ({ data: [] }),
}));

vi.mock("@/hooks/use-project-events", () => ({
  useProjectEvents: () => ({ connected: true }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe("PublicationsWorkspace", () => {
  beforeEach(() => {
    mockRetryMutate.mockReset();
    mockCancelMutate.mockReset();
  });

  it("filtra por estado incluyendo Canceladas y muestra enlace externo", () => {
    render(<PublicationsWorkspace />);

    expect(screen.getByText("Clip Programado")).toBeInTheDocument();
    expect(screen.getByText("Clip Publicado")).toBeInTheDocument();
    expect(screen.getByText("Clip Fallido")).toBeInTheDocument();
    expect(screen.getByText("Clip Cancelado")).toBeInTheDocument();

    const extLink = screen.getByRole("link", { name: /Ver enlace/i });
    expect(extLink).toHaveAttribute("href", "https://www.youtube.com/shorts/abc123");

    fireEvent.click(screen.getByRole("tab", { name: /Canceladas/i }));
    expect(screen.getByText("Clip Cancelado")).toBeInTheDocument();
    expect(screen.queryByText("Clip Programado")).not.toBeInTheDocument();
  });

  it("permite cancelar una publicación programada, inspeccionar captura y reintentar fallida", () => {
    render(<PublicationsWorkspace />);

    fireEvent.click(screen.getByRole("button", { name: /^Cancelar$/i }));
    expect(mockCancelMutate).toHaveBeenCalledWith(
      { publicationId: "pub-sched", body: { delete_remote: false } },
      expect.any(Object),
    );

    fireEvent.click(screen.getByRole("button", { name: /Ver captura/i }));
    expect(
      screen.getByRole("dialog", { name: "Diagnóstico y captura de error" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("challenge_required").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByAltText("Captura de error para Clip Fallido"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Reintentar envío/i }));
    expect(mockRetryMutate).toHaveBeenCalledWith("pub-fail", expect.any(Object));
  });
});
