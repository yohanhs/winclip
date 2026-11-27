import { expect, test } from "@playwright/test";

import {
  createSampleProject,
  emitSseEvent,
  setupMockApi,
} from "./helpers/mock-api";

test.describe("Listado de proyectos (/projects)", () => {
  test("muestra métricas reales, filtra por idioma/estado, actualiza progreso SSE y elimina con confirmación", async ({
    page,
  }) => {
    const state = await setupMockApi(page, {
      projects: [
        createSampleProject({
          id: "proj-es",
          title: "Finanzas en Español",
          language: "es",
          status: "ready",
          clips_count: 4,
        }),
        createSampleProject({
          id: "proj-en",
          title: "Founder Breakdown EN",
          language: "en",
          status: "processing",
          clips_count: 1,
          active_job: {
            id: "job-en",
            type: "pipeline",
            status: "running",
            progress: 25,
            stage: "ingest",
            error: null,
            created_at: "2026-11-26T10:00:00Z",
            updated_at: "2026-11-26T10:01:00Z",
          },
        }),
      ],
    });

    await page.goto("/projects");

    await expect(page.getByText("Finanzas en Español")).toBeVisible();
    await expect(page.getByText("Founder Breakdown EN")).toBeVisible();
    await expect(page.getByText("1 procesando")).toBeVisible();
    await expect(page.getByText("25%")).toBeVisible();

    // Evento SSE en vivo actualiza el porcentaje sin recargar
    await emitSseEvent(page, "job.progress", {
      job_id: "job-en",
      project_id: "proj-en",
      type: "pipeline",
      status: "running",
      progress: 68,
      stage: "select",
    });
    await expect(page.getByText("68%")).toBeVisible();

    // Filtro por idioma en minúsculas de la API
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await expect(page.getByText("Founder Breakdown EN")).toBeVisible();
    await expect(page.getByText("Finanzas en Español")).toBeHidden();

    await page.getByRole("button", { name: "ES", exact: true }).click();
    await expect(page.getByText("Finanzas en Español")).toBeVisible();
    await expect(page.getByText("Founder Breakdown EN")).toBeHidden();

    // Eliminar proyecto con AlertDialog desde vista lista
    await page.getByRole("button", { name: "Vista de lista" }).click();
    await page
      .getByRole("button", { name: "Eliminar Finanzas en Español" })
      .click();
    await expect(page.getByText("¿Eliminar este proyecto?")).toBeVisible();
    await page.getByRole("button", { name: "Eliminar", exact: true }).click();

    await expect(
      page.getByRole("link", { name: "Finanzas en Español" }),
    ).toBeHidden();
    expect(state.deletedProjectIds).toEqual(["proj-es"]);
  });

  test("muestra estado vacío y recupera ante error de API", async ({ page }) => {
    const state = await setupMockApi(page, {
      projects: [],
      failProjectsList: true,
    });

    await page.goto("/projects");
    await expect(
      page.getByText("No se pudieron cargar los proyectos"),
    ).toBeVisible();

    state.failProjectsList = false;
    await page.getByRole("button", { name: "Reintentar" }).click();
    await expect(page.getByText("Aún no hay proyectos")).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Crear el primero/i }),
    ).toHaveAttribute("href", "/projects/new");
  });

  test("se adapta a móvil sin desbordamiento horizontal", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMockApi(page);

    await page.goto("/projects");
    await expect(page.getByText("Podcast Finanzas Personales")).toBeVisible();

    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
