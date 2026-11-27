import { expect, test } from "@playwright/test";

import { createSampleAccount, setupMockApi } from "./helpers/mock-api";

test.describe("Gestión de cuentas sociales (/accounts)", () => {
  test("lista cuentas agrupadas, actualiza contador expirado en sidebar, renombra alias, cambia default y elimina", async ({
    page,
  }) => {
    await setupMockApi(page, {
      accounts: [
        createSampleAccount({
          id: "acc-yt-1",
          platform: "youtube",
          display_name: "HookVault",
          handle: "@hookvault",
          alias: "Principal",
          status: "connected",
          is_default: true,
        }),
        createSampleAccount({
          id: "acc-yt-2",
          platform: "youtube",
          display_name: "Dinero en Voz Baja",
          handle: "@dineroenvb",
          alias: null,
          status: "connected",
          is_default: false,
        }),
        createSampleAccount({
          id: "acc-tt-1",
          platform: "tiktok",
          display_name: "HookVault TT",
          handle: "@hookvault_tt",
          auth_method: "api",
          status: "expired",
          is_default: true,
          capabilities: { direct_post: false, inbox_only: true },
          last_error: "Token expirado",
        }),
      ],
    });

    await page.goto("/accounts");

    // Sidebar muestra badge rojo con 1 cuenta expirada
    await expect(page.getByTestId("sidebar-expired-accounts")).toHaveText("1");

    // Tarjetas agrupadas y badge Solo inbox
    await expect(page.getByText("Cuentas conectadas (3)")).toBeVisible();
    await expect(page.getByText("Solo inbox")).toBeVisible();

    // Renombrar alias inline
    await page.getByRole("button", { name: /Renombrar alias de Principal/i }).click();
    await page.getByLabel("Editar alias").fill("HookVault Oficial");
    await page.getByRole("button", { name: "Guardar alias" }).click();
    await expect(page.getByText("HookVault Oficial")).toBeVisible();

    // Marcar segunda cuenta de YouTube como Default
    await page
      .getByRole("button", { name: /Marcar Dinero en Voz Baja como predeterminada/i })
      .click();
    await expect(
      page.getByRole("button", { name: /Dinero en Voz Baja es predeterminada/i }),
    ).toBeVisible();

    // Probar conexión de la cuenta expirada -> el mock la refresca a conectada
    const ttCard = page.getByTestId("account-card-acc-tt-1");
    await ttCard.getByRole("button", { name: /Probar conexión/i }).click();
    await expect(ttCard.getByText("Conectada")).toBeVisible();
    await expect(page.getByTestId("sidebar-expired-accounts")).toHaveCount(0);

    // Eliminar cuenta con AlertDialog
    await page
      .getByRole("button", { name: /Eliminar cuenta Dinero en Voz Baja/i })
      .click();
    await page.getByRole("button", { name: "Eliminar cuenta" }).click();
    await expect(page.getByText("Cuentas conectadas (2)")).toBeVisible();
  });

  test("importa un token local y gestiona el diálogo Conectar con navegador", async ({
    page,
  }) => {
    await setupMockApi(page, { accounts: [] });
    await page.goto("/accounts");

    // Importar token local
    await page.getByRole("button", { name: /Conectar cuenta/i }).click();
    await page.getByRole("tab", { name: /Importar token/i }).click();
    await page
      .getByLabel(/Ruta local al archivo JSON/i)
      .fill("/tmp/fake_youtube_token.json");
    await page.getByLabel(/Alias interno/i).fill("Canal Importado");
    await page.getByRole("button", { name: /^Importar token$/i }).click();

    await expect(page.getByText("Canal Importado")).toBeVisible();

    // Conectar con navegador (Playwright) y confirmar sesión en vivo
    await page.getByRole("button", { name: /Conectar cuenta/i }).click();
    await page.getByRole("tab", { name: /Navegador/i }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /Conectar con navegador/i })
      .click();
    await expect(page.getByTestId("browser-login-live-panel")).toBeVisible();
    await page.getByRole("button", { name: /Confirmar sesión/i }).click();
    await expect(page.getByText("Playwright", { exact: true })).toBeVisible();
  });
});
