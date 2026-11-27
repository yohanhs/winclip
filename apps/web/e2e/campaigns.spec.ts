import { expect, test } from "@playwright/test";

import {
  createSampleClip,
  createSampleProject,
  setupMockApi,
} from "./helpers/mock-api";

test.describe("Campañas y alertas de reglas", () => {
  test("pega brief IA, revisa badges inferidos, guarda, duplica y elimina campaña", async ({
    page,
  }) => {
    await setupMockApi(page);
    await page.goto("/campaigns");

    await expect(page.getByText("Finanzas Educativo ES")).toBeVisible();

    // Ir a Nueva campaña (abre pestaña Pegar brief)
    await page.getByRole("button", { name: /Nueva campaña/i }).click();
    await page.getByRole("button", { name: /Cargar brief de ejemplo/i }).click();
    await page.getByRole("button", { name: /Extraer reglas con IA/i }).click();

    // Verifica badges violeta IA en campos inferidos y vista JSON sincronizada
    await expect(page.getByTestId("ai-badge-tone")).toBeVisible();
    await expect(page.getByTestId("ai-badge-subtitle_preset")).toBeVisible();
    await expect(page.getByTestId("campaign-json-preview")).toContainText(
      "Campaña desde Brief IA",
    );

    // Editar nombre y guardar
    const nameInput = page.getByLabel(/Nombre de campaña/i);
    await nameInput.fill("Campaña Brief Verificada");
    await expect(page.getByTestId("campaign-json-preview")).toContainText(
      "Campaña Brief Verificada",
    );
    await page.getByRole("button", { name: /Guardar campaña/i }).click();
    await expect(
      page.getByRole("heading", { name: "Campaña Brief Verificada" }).first(),
    ).toBeVisible();

    // Duplicar y eliminar con AlertDialog
    await page
      .locator('button[aria-label="Duplicar campaña Campaña Brief Verificada"]')
      .click();
    await expect(
      page.getByText("Campaña Brief Verificada (copia)").first(),
    ).toBeVisible();

    await page
      .locator(
        'button[aria-label="Eliminar campaña Campaña Brief Verificada (copia)"]',
      )
      .click();
    await expect(page.getByText(/¿Eliminar esta campaña\?/i)).toBeVisible();
    await page.getByRole("button", { name: /^Eliminar$/i }).click();
    await expect(
      page.getByText("Campaña Brief Verificada (copia)"),
    ).toHaveCount(0);
  });

  test("muestra alertas de rule_violations y filtro Alertas en /projects/[id]", async ({
    page,
  }) => {
    const project = createSampleProject({
      id: "proj-camp-1",
      campaign_id: "camp-e2e-1",
      campaign_name: "Finanzas Educativo ES",
    });
    const cleanClip = createSampleClip({
      id: "clip-clean",
      project_id: "proj-camp-1",
      title: "Clip limpio sin alertas",
      rule_violations: [],
    });
    const warnedClip = createSampleClip({
      id: "clip-warned",
      project_id: "proj-camp-1",
      title: "Clip con palabra prohibida",
      rule_violations: [
        {
          code: "banned_word_present",
          field: "banned_words",
          severity: "error",
          message: "Contiene la palabra prohibida 'garantizado'",
        },
      ],
    });

    await setupMockApi(page, {
      projects: [project],
      clipsByProject: { "proj-camp-1": [cleanClip, warnedClip] },
    });

    await page.goto("/projects/proj-camp-1");
    await expect(page.getByText("Finanzas Educativo ES")).toBeVisible();
    await expect(page.getByTestId("clip-card-clip-clean")).toBeVisible();
    await expect(page.getByTestId("clip-card-clip-warned")).toBeVisible();
    await expect(
      page.getByText("Contiene la palabra prohibida 'garantizado'"),
    ).toBeVisible();

    // Filtrar solo alertas
    await page.getByRole("button", { name: /^Alertas/i }).click();
    await expect(page.getByTestId("clip-card-clip-warned")).toBeVisible();
    await expect(page.getByTestId("clip-card-clip-clean")).toHaveCount(0);
  });
});
