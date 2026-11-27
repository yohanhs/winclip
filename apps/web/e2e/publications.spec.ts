import { expect, test } from "@playwright/test";

import {
  createSampleAccount,
  createSamplePublication,
  emitSseEvent,
  setupMockApi,
} from "./helpers/mock-api";

test.describe("Publicación multi-cuenta y página /publications", () => {
  test("abre PublishDialog desde /projects/[id], encola publicaciones y actualiza /publications", async ({
    page,
  }) => {
    const ytAcc = createSampleAccount({
      id: "acc-yt-1",
      platform: "youtube",
      auth_method: "api",
      alias: "Canal YT Principal",
      handle: "@canalyt",
      is_default: true,
    });
    const ttAcc = createSampleAccount({
      id: "acc-tt-1",
      platform: "tiktok",
      auth_method: "api",
      alias: "TikTok Inbox",
      handle: "@ttinbox",
      is_default: true,
      capabilities: { direct_post: false },
    });

    const state = await setupMockApi(page, {
      accounts: [ytAcc, ttAcc],
      publications: [],
    });

    await page.goto("/projects/proj-e2e-1");
    await expect(
      page.getByText("El error que te cuesta 500 al mes"),
    ).toBeVisible();

    // Seleccionar clip y abrir PublishDialog
    await page
      .getByLabel("Seleccionar El error que te cuesta 500 al mes")
      .click();
    await page.getByRole("button", { name: /Publicar en redes/i }).click();

    const dialog = page.getByRole("dialog", {
      name: "Publicar clips en redes sociales",
    });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Canal YT Principal")).toBeVisible();
    await expect(dialog.getByText(/Borrador Inbox/i)).toBeVisible();

    await dialog.getByRole("button", { name: /Enviar ahora/i }).click();
    await expect(dialog).toBeHidden();
    expect(state.publications).toHaveLength(2);

    // Navegar a /publications y verificar los registros creados
    await page.goto("/publications");
    const table = page.getByRole("table");
    await expect(table.getByText("Canal YT Principal")).toBeVisible();
    await expect(table.getByText("TikTok Inbox")).toBeVisible();
  });

  test("filtra por estado, inspecciona captura de error, reintenta fallida y cancela programada en /publications", async ({
    page,
  }) => {
    const pubScheduled = createSamplePublication({
      id: "pub-sched-1",
      clip_title: "Clip Programado E2E",
      status: "scheduled",
      account_platform: "tiktok",
      account_alias: "TT Cuenta",
      delivery_mode: "inbox",
    });
    const pubFailed = createSamplePublication({
      id: "pub-fail-1",
      clip_title: "Clip Fallido E2E",
      status: "failed",
      account_platform: "instagram",
      account_auth_method: "playwright",
      account_alias: "IG Browser",
      error: "Desafío CAPTCHA detectado",
      error_code: "challenge_required",
      has_screenshot: true,
      screenshot_url: "/api/publications/pub-fail-1/screenshot",
    });
    const pubDone = createSamplePublication({
      id: "pub-done-1",
      clip_title: "Clip Publicado E2E",
      status: "published",
      account_platform: "youtube",
      account_alias: "Canal YT",
      external_url: "https://www.youtube.com/shorts/e2e123",
    });

    const state = await setupMockApi(page, {
      publications: [pubScheduled, pubFailed, pubDone],
    });

    await page.goto("/publications");

    // Verificar enlace externo
    const link = page.getByRole("link", { name: /Ver enlace/i });
    await expect(link).toHaveAttribute(
      "href",
      "https://www.youtube.com/shorts/e2e123",
    );

    // Cancelar publicación programada
    const schedRow = page.getByTestId("publication-row-pub-sched-1");
    await schedRow.getByRole("button", { name: /^Cancelar$/i }).click();
    await expect(schedRow.getByText("Cancelada")).toBeVisible();

    // Filtrar por Canceladas
    await page.getByRole("tab", { name: /Canceladas/i }).click();
    const table = page.getByRole("table");
    await expect(table.getByText("Clip Programado E2E")).toBeVisible();
    await expect(table.getByText("Clip Fallido E2E")).toBeHidden();

    // Volver a Todas, abrir modal Ver captura y reintentar
    await page.getByRole("tab", { name: /Todas/i }).click();
    const failRow = page.getByTestId("publication-row-pub-fail-1");
    await failRow.getByRole("button", { name: /Ver captura/i }).click();

    const modal = page.getByRole("dialog", {
      name: "Diagnóstico y captura de error",
    });
    await expect(modal).toBeVisible();
    await expect(modal.getByText("challenge_required").first()).toBeVisible();
    await modal.getByRole("button", { name: /Reintentar envío/i }).click();
    await expect(modal).toBeHidden();

    // Evento SSE publication.updated actualiza en vivo
    state.publications = state.publications.map((p) =>
      p.id === "pub-fail-1" ? { ...p, status: "published" } : p,
    );
    await emitSseEvent(page, "publication.updated", {
      publication_id: "pub-fail-1",
      clip_id: "clip-e2e-1",
      account_id: "acc-e2e-1",
      project_id: "proj-e2e-1",
      job_id: "job-1",
      status: "published",
      delivery_mode: "direct",
    });
    await expect(
      page.getByTestId("publication-row-pub-fail-1").getByText("Publicada"),
    ).toBeVisible();
  });
});
