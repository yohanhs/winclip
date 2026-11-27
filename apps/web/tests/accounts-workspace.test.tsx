import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AccountsOAuthConfigOut,
  BrowserLoginOut,
  SocialAccountOut,
} from "@winclip/api-client";

import { AccountsWorkspace } from "@/components/accounts/accounts-workspace";
import { makeSocialAccount } from "./mocks/fixtures";

const mocks = vi.hoisted(() => ({
  accounts: [] as SocialAccountOut[],
  oauthConfig: {
    platforms: [
      { platform: "youtube", configured: true, missing: [] },
      {
        platform: "tiktok",
        configured: false,
        missing: ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
      },
      { platform: "instagram", configured: true, missing: [] },
    ],
  } as AccountsOAuthConfigOut,
  updateMutate: vi.fn(),
  deleteMutate: vi.fn(),
  checkMutate: vi.fn(),
  startOAuthMutate: vi.fn(),
  startBrowserMutate: vi.fn(),
  confirmBrowserMutate: vi.fn(),
  cancelBrowserMutate: vi.fn(),
  importMutate: vi.fn(),
  selectIgMutate: vi.fn(),
  browserStatus: null as BrowserLoginOut | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/hooks/use-accounts", () => ({
  useAccounts: () => ({
    data: mocks.accounts,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useAccountsOAuthConfig: () => ({
    data: mocks.oauthConfig,
    isLoading: false,
  }),
  useUpdateAccount: () => ({
    mutate: mocks.updateMutate,
    isPending: false,
  }),
  useDeleteAccount: () => ({
    mutate: mocks.deleteMutate,
    isPending: false,
  }),
  useCheckAccount: () => ({
    mutate: mocks.checkMutate,
    isPending: false,
  }),
  useStartAccountOAuth: () => ({
    mutate: mocks.startOAuthMutate,
    isPending: false,
  }),
  usePendingInstagramSelection: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useSelectInstagramAccounts: () => ({
    mutate: mocks.selectIgMutate,
    isPending: false,
  }),
  useStartBrowserLogin: () => ({
    mutate: mocks.startBrowserMutate,
    isPending: false,
  }),
  useBrowserLoginStatus: () => ({
    data: mocks.browserStatus,
  }),
  useConfirmBrowserLogin: () => ({
    mutate: mocks.confirmBrowserMutate,
    isPending: false,
  }),
  useCancelBrowserLogin: () => ({
    mutate: mocks.cancelBrowserMutate,
    isPending: false,
  }),
  useImportAccountTokens: () => ({
    mutate: mocks.importMutate,
    isPending: false,
  }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    message: vi.fn(),
  },
}));

describe("AccountsWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.accounts = [
      makeSocialAccount({
        id: "acc-yt-1",
        platform: "youtube",
        display_name: "HookVault",
        handle: "@hookvault",
        alias: "Canal Principal",
        auth_method: "api",
        status: "connected",
        is_default: true,
      }),
      makeSocialAccount({
        id: "acc-tt-1",
        platform: "tiktok",
        display_name: "HookVault Clips",
        handle: "@hookvault_tt",
        alias: null,
        auth_method: "api",
        status: "expired",
        is_default: false,
        capabilities: { direct_post: false, inbox_only: true },
        last_error: "Token expirado",
      }),
    ];
  });

  it("muestra secciones agrupadas, badges de método/estado/capacidades y acciones en tarjetas", () => {
    render(<AccountsWorkspace />);

    expect(screen.getByText(/Cuentas conectadas \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText("Canal Principal")).toBeInTheDocument();
    expect(screen.getByText("@hookvault")).toBeInTheDocument();
    expect(screen.getByText("HookVault Clips")).toBeInTheDocument();
    expect(screen.getByText("Solo inbox")).toBeInTheDocument();
    expect(screen.getByText("Expirada")).toBeInTheDocument();

    // Renombrar alias inline
    fireEvent.click(screen.getByRole("button", { name: /Renombrar alias de Canal Principal/i }));
    const aliasInput = screen.getByLabelText("Editar alias");
    fireEvent.change(aliasInput, { target: { value: "HookVault Main" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar alias" }));

    expect(mocks.updateMutate).toHaveBeenCalledWith(
      { accountId: "acc-yt-1", body: { alias: "HookVault Main" } },
      expect.any(Object),
    );

    // Probar conexión
    const checkButtons = screen.getAllByRole("button", { name: /Probar conexión/i });
    fireEvent.click(checkButtons[0]!);
    expect(mocks.checkMutate).toHaveBeenCalledWith("acc-yt-1", expect.any(Object));

    // Eliminar con AlertDialog
    fireEvent.click(screen.getByRole("button", { name: /Eliminar cuenta HookVault Clips/i }));
    expect(screen.getByText(/¿Eliminar cuenta HookVault Clips\?/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Eliminar cuenta" }));
    expect(mocks.deleteMutate).toHaveBeenCalledWith("acc-tt-1", expect.any(Object));
  });

  it("muestra guía de variables faltantes en OAuth e importa token local desde el modal", () => {
    render(<AccountsWorkspace />);

    fireEvent.click(screen.getByRole("button", { name: /Conectar cuenta/i }));

    // Seleccionar TikTok en OAuth (configuración faltante)
    const tiktokButtons = screen.getAllByRole("button", { name: "TikTok" });
    fireEvent.click(tiktokButtons[tiktokButtons.length - 1]!);
    expect(screen.getByTestId("oauth-missing-config-guide")).toHaveTextContent(
      "TIKTOK_CLIENT_KEY",
    );

    // Cambiar a pestaña Importar token (Radix Tabs activa en mouseDown con button 0)
    const importTab = screen.getByRole("tab", { name: /Importar token/i });
    fireEvent.mouseDown(importTab, { button: 0 });
    fireEvent.click(importTab);
    const pathInput = screen.getByLabelText(/Ruta local al archivo JSON/i);
    fireEvent.change(pathInput, { target: { value: "/tmp/fake_token.json" } });
    fireEvent.click(screen.getByRole("button", { name: /^Importar token$/i }));

    expect(mocks.importMutate).toHaveBeenCalledWith(
      { path: "/tmp/fake_token.json", platform: null, alias: null },
      expect.any(Object),
    );
  });
});
