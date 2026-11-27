import { expect, test } from "@playwright/test";

import { setupMockApi } from "./helpers/mock-api";

test.describe("Creación de proyecto (/projects/new)", () => {
  test("crea proyecto por URL con preset actualizado, modo max y redirige al detalle", async ({
    page,
  }) => {
    const state = await setupMockApi(page);

    await page.goto("/projects/new");

    await expect(page.getByText("Previsualización 9:16")).toBeVisible();
    await expect(page.getByText("Bold Yellow").first()).toBeVisible();

    // Campaña visible pero deshabilitada hasta change 6
    await expect(
      page.getByRole("combobox", { name: "Campaña (próximamente)" }),
    ).toBeDisabled();

    // Cambiar preset a Hormozi y comprobar actualización de la preview en vivo
    await page.getByRole("combobox", { name: "Preset de subtítulos" }).click();
    await page.getByRole("option", { name: "Hormozi" }).click();
    await expect(
      page.getByText("Alto impacto con palabra activa verde"),
    ).toBeVisible();

    // Activar Máximo posible
    await page.getByRole("switch", { name: "Máximo posible" }).click();
    await expect(page.getByText("Máx.")).toBeVisible();

    // Rellenar URL y enviar
    await page
      .getByLabel("Enlace del vídeo")
      .fill("https://www.youtube.com/watch?v=winclip-demo");
    await page.getByRole("button", { name: /Generar clips/i }).click();

    await expect(page).toHaveURL(/\/projects\/proj-created-2$/);
    expect(state.createdPayloads).toHaveLength(1);
    expect(state.createdPayloads[0]?.contentType).toContain("application/json");
    expect(state.createdPayloads[0]?.body).toMatchObject({
      source_type: "url",
      source_url: "https://www.youtube.com/watch?v=winclip-demo",
      requested_clips: "max",
      subtitle_preset: "hormozi",
      reframe_mode: "face",
    });
  });

  test("sube archivo local mediante dropzone y redirige al detalle", async ({
    page,
  }) => {
    const state = await setupMockApi(page);

    await page.goto("/projects/new");
    await page.getByRole("tab", { name: /Subir archivo/i }).click();

    const fileInput = page.getByLabel("Seleccionar archivo de vídeo");
    await fileInput.setInputFiles({
      name: "entrevista-master.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("fake-video-content"),
    });

    await expect(page.getByText("entrevista-master.mp4")).toBeVisible();
    await page.getByRole("button", { name: /Generar clips/i }).click();

    await expect(page).toHaveURL(/\/projects\/proj-created-2$/);
    expect(state.createdPayloads).toHaveLength(1);
    expect(state.createdPayloads[0]?.contentType).toContain(
      "multipart/form-data",
    );
  });

  test("mantiene diseño responsive en móvil sin scroll horizontal", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMockApi(page);

    await page.goto("/projects/new");
    await expect(page.getByText("Previsualización 9:16")).toBeVisible();

    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
